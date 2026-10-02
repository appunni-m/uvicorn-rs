/* Threaded libcurl HTTP/1.1 client for low-overhead, body-checked benchmarks. */
#define _POSIX_C_SOURCE 200809L

#include <curl/curl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    const char *url;
    const char *method;
    const char *upload_body;
    size_t upload_bytes;
    size_t upload_chunk_bytes;
    unsigned long long max_requests;
    const char *expected_body;
    size_t expected_bytes;
    long expected_status;
    double deadline;
    struct curl_slist *headers;
    atomic_ullong *request_count;
    atomic_ullong *request_bytes;
    atomic_ullong *response_bytes;
    atomic_uint *failures;
    pthread_mutex_t *failure_lock;
    char *first_failure;
} Shared;

typedef struct {
    Shared *shared;
    double *latencies;
    size_t latency_count;
    size_t latency_capacity;
} Worker;

typedef struct {
    const char *expected;
    size_t expected_bytes;
    size_t offset;
    int valid;
} ResponseCheck;

typedef struct {
    const char *body;
    size_t bytes;
    size_t chunk_bytes;
    size_t offset;
} UploadCursor;

static double now_seconds(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)now.tv_sec + (double)now.tv_nsec / 1e9;
}

static size_t check_response(char *data, size_t size, size_t count, void *user_data) {
    ResponseCheck *check = (ResponseCheck *)user_data;
    size_t bytes = size * count;
    if (bytes > check->expected_bytes - (check->offset <= check->expected_bytes ? check->offset : check->expected_bytes)) {
        check->valid = 0;
    } else if (check->valid && memcmp(data, check->expected + check->offset, bytes) != 0) {
        check->valid = 0;
    }
    check->offset += bytes;
    return bytes;
}

static size_t read_upload(char *buffer, size_t size, size_t count, void *user_data) {
    UploadCursor *upload = (UploadCursor *)user_data;
    size_t capacity = size * count;
    if (upload->offset >= upload->bytes || capacity == 0) return 0;
    size_t length = upload->bytes - upload->offset;
    if (length > capacity) length = capacity;
    if (upload->chunk_bytes > 0 && length > upload->chunk_bytes) length = upload->chunk_bytes;
    memcpy(buffer, upload->body + upload->offset, length);
    upload->offset += length;
    return length;
}

static void set_failure(Shared *shared, const char *reason) {
    atomic_fetch_add(shared->failures, 1);
    pthread_mutex_lock(shared->failure_lock);
    if (shared->first_failure[0] == '\0') {
        snprintf(shared->first_failure, 256, "%s", reason);
    }
    pthread_mutex_unlock(shared->failure_lock);
}

static int append_latency(Worker *worker, double latency) {
    if (worker->latency_count == worker->latency_capacity) {
        size_t capacity = worker->latency_capacity == 0 ? 4096 : worker->latency_capacity * 2;
        double *next = realloc(worker->latencies, capacity * sizeof(*next));
        if (next == NULL) return 0;
        worker->latencies = next;
        worker->latency_capacity = capacity;
    }
    worker->latencies[worker->latency_count++] = latency;
    return 1;
}

static void *run_worker(void *argument) {
    Worker *worker = (Worker *)argument;
    Shared *shared = worker->shared;
    CURL *curl = curl_easy_init();
    if (curl == NULL) {
        set_failure(shared, "curl_easy_init failed");
        return NULL;
    }

    curl_easy_setopt(curl, CURLOPT_URL, shared->url);
    curl_easy_setopt(curl, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, 3000L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 15000L);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, shared->headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, check_response);
    UploadCursor upload = {
        .body = shared->upload_body,
        .bytes = shared->upload_bytes,
        .chunk_bytes = shared->upload_chunk_bytes,
        .offset = 0,
    };
    if (strcmp(shared->method, "POST") == 0) {
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_READFUNCTION, read_upload);
        curl_easy_setopt(curl, CURLOPT_READDATA, &upload);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE, (curl_off_t)shared->upload_bytes);
    }

    while (now_seconds() < shared->deadline
        && (shared->max_requests == 0
            || atomic_load(shared->request_count) < shared->max_requests)) {
        ResponseCheck check = {
            .expected = shared->expected_body,
            .expected_bytes = shared->expected_bytes,
            .offset = 0,
            .valid = 1,
        };
        upload.offset = 0;
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &check);
        double started = now_seconds();
        CURLcode result = curl_easy_perform(curl);
        double elapsed = now_seconds() - started;
        if (result != CURLE_OK) {
            char reason[256];
            snprintf(reason, sizeof(reason), "libcurl: %s", curl_easy_strerror(result));
            set_failure(shared, reason);
            break;
        }

        long status = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
        if (status != shared->expected_status) {
            char reason[256];
            snprintf(reason, sizeof(reason), "unexpected HTTP status %ld (wanted %ld)", status, shared->expected_status);
            set_failure(shared, reason);
        }
        if (!check.valid || check.offset != shared->expected_bytes) {
            set_failure(shared, "response body differs from the complete expected bytes");
        }

        atomic_fetch_add(shared->request_count, 1);
        if (shared->upload_bytes != 0) atomic_fetch_add(shared->request_bytes, shared->upload_bytes);
        atomic_fetch_add(shared->response_bytes, check.offset);
        if (!append_latency(worker, elapsed)) {
            set_failure(shared, "could not grow client latency sample buffer");
            break;
        }
    }

    curl_easy_cleanup(curl);
    return NULL;
}

static int compare_double(const void *left, const void *right) {
    double a = *(const double *)left;
    double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double percentile(const double *values, size_t count, double p) {
    if (count == 0) return 0.0;
    size_t index = (size_t)(p * (double)count + 0.999999999) - 1;
    if (index >= count) index = count - 1;
    return values[index] * 1000.0;
}

static char *expected_for_mode(const char *mode, const char *expected_override, size_t *length) {
    if (expected_override != NULL && expected_override[0] != '\0') {
        *length = strlen(expected_override);
        return strdup(expected_override);
    }
    const char *body = "Hello World!";
    if (strcmp(mode, "scope") == 0) body = "scope-ok";
    else if (strcmp(mode, "context") == 0) body = "request-context";
    else if (strcmp(mode, "exception") == 0) body = "Internal Server Error";
    *length = strlen(body);
    return strdup(body);
}

int main(int argc, char **argv) {
    if (argc < 13) {
        fprintf(stderr, "usage: client host port seconds concurrency mode path response_bytes upload_bytes expected_status expected_body upload_chunk_bytes max_requests [header:value ...]\n");
        return 2;
    }

    const char *host = argv[1];
    long port = strtol(argv[2], NULL, 10);
    double seconds = strtod(argv[3], NULL);
    int concurrency = (int)strtol(argv[4], NULL, 10);
    const char *mode = argv[5];
    const char *path = argv[6];
    size_t response_bytes = (size_t)strtoull(argv[7], NULL, 10);
    size_t upload_bytes = (size_t)strtoull(argv[8], NULL, 10);
    long expected_status = strtol(argv[9], NULL, 10);
    const char *body_override = argv[10];
    size_t upload_chunk_bytes = (size_t)strtoull(argv[11], NULL, 10);
    unsigned long long max_requests = strtoull(argv[12], NULL, 10);
    if (port <= 0 || concurrency <= 0 || seconds <= 0) return 2;

    size_t expected_bytes = 0;
    char *expected_body = NULL;
    char *upload_body = NULL;
    if (response_bytes > 0) {
        expected_body = malloc(response_bytes);
        if (expected_body == NULL) return 2;
        memset(expected_body, 'x', response_bytes);
        expected_bytes = response_bytes;
    } else if (strcmp(mode, "upload") == 0) {
        char generated[64];
        snprintf(generated, sizeof(generated), "bytes=%zu", upload_bytes);
        expected_body = strdup(generated);
        expected_bytes = strlen(generated);
    } else {
        expected_body = expected_for_mode(mode, body_override, &expected_bytes);
    }
    if (expected_body == NULL) return 2;
    if (upload_bytes > 0) {
        upload_body = malloc(upload_bytes);
        if (upload_body == NULL) return 2;
        memset(upload_body, 'a', upload_bytes);
    }

    char url[4096];
    snprintf(url, sizeof(url), "http://%s:%ld%s", host, port, path);
    struct curl_slist *headers = NULL;
    for (int index = 13; index < argc; index++) headers = curl_slist_append(headers, argv[index]);
    atomic_ullong requests = 0, request_bytes = 0, response_bytes_total = 0;
    atomic_uint failures = 0;
    pthread_mutex_t failure_lock = PTHREAD_MUTEX_INITIALIZER;
    char first_failure[256] = "";
    double started = now_seconds();
    Shared shared = {
        .url = url,
        .method = upload_bytes > 0 ? "POST" : "GET",
        .upload_body = upload_body,
        .upload_bytes = upload_bytes,
        .upload_chunk_bytes = upload_chunk_bytes,
        .max_requests = max_requests,
        .expected_body = expected_body,
        .expected_bytes = expected_bytes,
        .expected_status = expected_status,
        .deadline = started + seconds,
        .headers = headers,
        .request_count = &requests,
        .request_bytes = &request_bytes,
        .response_bytes = &response_bytes_total,
        .failures = &failures,
        .failure_lock = &failure_lock,
        .first_failure = first_failure,
    };

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 2;
    pthread_t *threads = calloc((size_t)concurrency, sizeof(*threads));
    Worker *workers = calloc((size_t)concurrency, sizeof(*workers));
    if (threads == NULL || workers == NULL) return 2;
    int created = 0;
    for (int index = 0; index < concurrency; index++) {
        workers[index].shared = &shared;
        if (pthread_create(&threads[index], NULL, run_worker, &workers[index]) != 0) {
            set_failure(&shared, "pthread_create failed");
            break;
        }
        created++;
    }
    for (int index = 0; index < created; index++) pthread_join(threads[index], NULL);
    double elapsed = now_seconds() - started;

    size_t latency_count = 0;
    for (int index = 0; index < created; index++) latency_count += workers[index].latency_count;
    double *latencies = malloc(latency_count * sizeof(*latencies));
    if (latencies == NULL && latency_count > 0) return 2;
    size_t offset = 0;
    for (int index = 0; index < created; index++) {
        memcpy(latencies + offset, workers[index].latencies, workers[index].latency_count * sizeof(*latencies));
        offset += workers[index].latency_count;
        free(workers[index].latencies);
    }
    qsort(latencies, latency_count, sizeof(*latencies), compare_double);

    unsigned long long count = atomic_load(&requests);
    unsigned long long sent = atomic_load(&request_bytes);
    unsigned long long received = atomic_load(&response_bytes_total);
    unsigned int failure_count = atomic_load(&failures);
    printf("{\"requests\":%llu,\"duration_seconds\":%.9f,\"requests_per_second\":%.3f,\"request_body_bytes\":%llu,\"response_body_bytes\":%llu,\"application_bytes_per_second\":%.3f,\"p50_ms\":%.6f,\"p95_ms\":%.6f,\"p99_ms\":%.6f,\"failures\":%u,\"first_failure\":",
        count, elapsed, count / elapsed, sent, received, (sent + received) / elapsed,
        percentile(latencies, latency_count, 0.50), percentile(latencies, latency_count, 0.95), percentile(latencies, latency_count, 0.99), failure_count);
    if (first_failure[0] == '\0') printf("null");
    else {
        printf("{\"reason\":\"");
        for (const char *p = first_failure; *p != '\0'; p++) {
            if (*p == '"' || *p == '\\') putchar('\\');
            if (*p >= 0x20) putchar(*p);
        }
        printf("\"}");
    }
    printf("}\n");

    free(latencies);
    free(workers);
    free(threads);
    free(expected_body);
    free(upload_body);
    curl_slist_free_all(headers);
    pthread_mutex_destroy(&failure_lock);
    curl_global_cleanup();
    return failure_count == 0 && count > 0 ? 0 : 1;
}
