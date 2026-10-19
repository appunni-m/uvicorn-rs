/* Threaded libcurl HTTP/1.1 client for low-overhead, body-checked benchmarks. */
#define _POSIX_C_SOURCE 200809L

#include <curl/curl.h>
#include <pthread.h>
#include <stddef.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef __linux__
#include <netinet/in.h>
#include <linux/tcp.h>
#include <sys/socket.h>
#endif

typedef struct {
    curl_socket_t socket;
    int available;
    uint64_t bytes_acked;
    uint32_t notsent_bytes;
    uint32_t unacked_segments;
    double sampled_at_seconds;
} SocketSnapshot;

#define MAX_UPLOAD_TRACE_EVENTS 2048
#define UPLOAD_TRACE_MIN_SECONDS 0.010

typedef struct {
    uint64_t unix_time_ns;
    uint64_t cumulative_bytes;
    size_t bytes;
} UploadTraceEvent;

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
    struct FirstFailure *first_failure;
    int tcp_diagnostics;
    int upload_trace;
    atomic_uint upload_trace_claimed;
} Shared;

typedef struct {
    Shared *shared;
    unsigned int worker_index;
    double *latencies;
    size_t latency_count;
    size_t latency_capacity;
    curl_socket_t diagnostic_socket;
    SocketSnapshot latest_tcp_snapshot;
    unsigned int tcp_snapshot_count;
    UploadTraceEvent upload_trace_events[MAX_UPLOAD_TRACE_EVENTS];
    unsigned int upload_trace_event_count;
    unsigned int upload_trace_dropped_events;
    uint64_t upload_trace_bytes;
    int upload_trace_selected;
    unsigned long long upload_trace_attempt;
    uint64_t upload_trace_elapsed_ns;
    long upload_trace_local_port;
} Worker;

typedef struct FirstFailure {
    char reason[256];
    int has_transfer_diagnostics;
    unsigned int worker_index;
    unsigned long long worker_attempt;
    size_t expected_upload_bytes;
    size_t upload_callback_bytes;
    curl_off_t curl_uploaded_bytes;
    curl_off_t curl_downloaded_bytes;
    long response_code;
    long new_connections;
    double connect_time_seconds;
    double starttransfer_time_seconds;
    double total_time_seconds;
    long local_port;
    int tcp_info_available;
    int tcp_info_before_available;
    unsigned int tcp_snapshot_count;
    unsigned long long tcp_bytes_acked;
    unsigned long long tcp_bytes_acked_before;
    long long tcp_bytes_acked_delta;
    unsigned int tcp_notsent_bytes;
    unsigned int tcp_unacked_segments;
    double tcp_snapshot_age_ms;
} FirstFailure;

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

static uint64_t unix_time_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_REALTIME, &now) != 0 || now.tv_sec < 0) return 0;
    return (uint64_t)now.tv_sec * 1000000000ULL + (uint64_t)now.tv_nsec;
}

static SocketSnapshot read_socket_snapshot(curl_socket_t socket) {
    SocketSnapshot snapshot = {
        .socket = socket,
        .sampled_at_seconds = now_seconds(),
    };
#ifdef __linux__
    if (socket != CURL_SOCKET_BAD) {
        struct tcp_info info = {0};
        socklen_t info_length = sizeof(info);
        const socklen_t required_length =
            (socklen_t)(offsetof(struct tcp_info, tcpi_notsent_bytes)
                + sizeof(info.tcpi_notsent_bytes));
        if (getsockopt(socket, IPPROTO_TCP, TCP_INFO, &info, &info_length) == 0
            && info_length >= required_length) {
            snapshot.available = 1;
            snapshot.bytes_acked = info.tcpi_bytes_acked;
            snapshot.notsent_bytes = info.tcpi_notsent_bytes;
            snapshot.unacked_segments = info.tcpi_unacked;
        }
    }
#else
    (void)socket;
#endif
    return snapshot;
}

static int record_client_socket(void *client_data, curl_socket_t socket, curlsocktype purpose) {
    Worker *worker = (Worker *)client_data;
    (void)purpose;
    if (worker != NULL && worker->shared->tcp_diagnostics) {
        worker->diagnostic_socket = socket;
    }
    return CURL_SOCKOPT_OK;
}

static int sample_transfer_progress(
    void *client_data,
    curl_off_t download_total,
    curl_off_t download_now,
    curl_off_t upload_total,
    curl_off_t upload_now
) {
    Worker *worker = (Worker *)client_data;
    (void)download_total;
    (void)download_now;
    (void)upload_total;
    (void)upload_now;
    if (worker != NULL && worker->shared->tcp_diagnostics) {
        SocketSnapshot snapshot = read_socket_snapshot(worker->diagnostic_socket);
        if (snapshot.available) {
            worker->latest_tcp_snapshot = snapshot;
            worker->tcp_snapshot_count++;
        }
    }
    return 0;
}

static int record_upload_data_out(
    CURL *curl,
    curl_infotype type,
    char *data,
    size_t size,
    void *client_data
) {
    /* Record libcurl's protocol-data callback, not TCP packet boundaries. */
    Worker *worker = (Worker *)client_data;
    (void)curl;
    (void)data;
    if (worker == NULL || type != CURLINFO_DATA_OUT || size == 0
        || !worker->shared->upload_trace
        || atomic_load(&worker->shared->upload_trace_claimed) != 0) {
        return 0;
    }

    worker->upload_trace_bytes += (uint64_t)size;
    if (worker->upload_trace_event_count >= MAX_UPLOAD_TRACE_EVENTS) {
        worker->upload_trace_dropped_events++;
        return 0;
    }

    UploadTraceEvent *event =
        &worker->upload_trace_events[worker->upload_trace_event_count++];
    event->unix_time_ns = unix_time_ns();
    event->bytes = size;
    event->cumulative_bytes = worker->upload_trace_bytes;
    return 0;
}

static void select_slow_upload_trace(
    CURL *curl,
    Worker *worker,
    unsigned long long worker_attempt,
    double elapsed
) {
    Shared *shared = worker->shared;
    if (!shared->upload_trace || shared->upload_bytes == 0
        || elapsed < UPLOAD_TRACE_MIN_SECONDS) return;

    /* Keep at most one slow request trace per client process. */
    unsigned int unclaimed = 0;
    if (!atomic_compare_exchange_strong(
            &shared->upload_trace_claimed,
            &unclaimed,
            1
        )) {
        return;
    }

    worker->upload_trace_selected = 1;
    worker->upload_trace_attempt = worker_attempt;
    worker->upload_trace_elapsed_ns = (uint64_t)(elapsed * 1000000000.0);
    worker->upload_trace_local_port = -1;
    (void)curl_easy_getinfo(curl, CURLINFO_LOCAL_PORT, &worker->upload_trace_local_port);
}

static void print_upload_traces(const Worker *workers, int worker_count) {
    int first = 1;
    putchar('[');
    for (int worker_index = 0; worker_index < worker_count; worker_index++) {
        const Worker *worker = &workers[worker_index];
        if (!worker->upload_trace_selected) continue;
        if (!first) putchar(',');
        first = 0;
        printf(
            "{\"worker_index\":%u,\"worker_attempt\":%llu,\"local_port\":%ld,"
            "\"elapsed_ns\":%llu,\"event_count\":%u,\"dropped_events\":%u,\"events\":[",
            worker->worker_index,
            worker->upload_trace_attempt,
            worker->upload_trace_local_port,
            (unsigned long long)worker->upload_trace_elapsed_ns,
            worker->upload_trace_event_count,
            worker->upload_trace_dropped_events
        );
        for (unsigned int event_index = 0;
             event_index < worker->upload_trace_event_count;
             event_index++) {
            const UploadTraceEvent *event = &worker->upload_trace_events[event_index];
            if (event_index != 0) putchar(',');
            printf(
                "{\"unix_ns\":%llu,\"bytes\":%zu,\"cumulative_bytes\":%llu}",
                (unsigned long long)event->unix_time_ns,
                event->bytes,
                (unsigned long long)event->cumulative_bytes
            );
        }
        printf("]}");
    }
    putchar(']');
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
    /* This caps bytes returned to libcurl per read callback; it does not
       guarantee the same socket-write or TCP packet boundaries. */
    if (upload->chunk_bytes > 0 && length > upload->chunk_bytes) length = upload->chunk_bytes;
    memcpy(buffer, upload->body + upload->offset, length);
    upload->offset += length;
    return length;
}

static void set_failure(Shared *shared, const char *reason) {
    atomic_fetch_add(shared->failures, 1);
    pthread_mutex_lock(shared->failure_lock);
    if (shared->first_failure->reason[0] == '\0') {
        snprintf(
            shared->first_failure->reason,
            sizeof(shared->first_failure->reason),
            "%s",
            reason
        );
    }
    pthread_mutex_unlock(shared->failure_lock);
}

static void set_transfer_failure(
    Shared *shared,
    CURL *curl,
    const UploadCursor *upload,
    Worker *worker,
    unsigned long long worker_attempt,
    const SocketSnapshot *tcp_before,
    const char *reason
) {
    atomic_fetch_add(shared->failures, 1);
    pthread_mutex_lock(shared->failure_lock);
    FirstFailure *failure = shared->first_failure;
    if (failure->reason[0] == '\0') {
        snprintf(failure->reason, sizeof(failure->reason), "%s", reason);
        failure->has_transfer_diagnostics = 1;
        failure->worker_index = worker->worker_index;
        failure->worker_attempt = worker_attempt;
        failure->expected_upload_bytes = shared->upload_bytes;
        failure->upload_callback_bytes = upload->offset;
        failure->curl_uploaded_bytes = -1;
        failure->curl_downloaded_bytes = -1;
        failure->response_code = 0;
        failure->new_connections = -1;
        failure->connect_time_seconds = -1.0;
        failure->starttransfer_time_seconds = -1.0;
        failure->total_time_seconds = -1.0;
        failure->local_port = -1;
        failure->tcp_info_available = 0;
        failure->tcp_info_before_available = 0;
        failure->tcp_snapshot_count = worker->tcp_snapshot_count;
        failure->tcp_bytes_acked = 0;
        failure->tcp_bytes_acked_before = 0;
        failure->tcp_bytes_acked_delta = -1;
        failure->tcp_notsent_bytes = 0;
        failure->tcp_unacked_segments = 0;
        failure->tcp_snapshot_age_ms = -1.0;
#if LIBCURL_VERSION_NUM >= 0x073700
        (void)curl_easy_getinfo(curl, CURLINFO_SIZE_UPLOAD_T, &failure->curl_uploaded_bytes);
        (void)curl_easy_getinfo(curl, CURLINFO_SIZE_DOWNLOAD_T, &failure->curl_downloaded_bytes);
#endif
        (void)curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &failure->response_code);
        (void)curl_easy_getinfo(curl, CURLINFO_NUM_CONNECTS, &failure->new_connections);
        if (shared->tcp_diagnostics) {
            (void)curl_easy_getinfo(curl, CURLINFO_LOCAL_PORT, &failure->local_port);
            if (tcp_before->available) {
                failure->tcp_info_before_available = 1;
                failure->tcp_bytes_acked_before =
                    (unsigned long long)tcp_before->bytes_acked;
            }
            const SocketSnapshot *tcp_after = &worker->latest_tcp_snapshot;
            if (tcp_after->available) {
                failure->tcp_info_available = 1;
                failure->tcp_bytes_acked = (unsigned long long)tcp_after->bytes_acked;
                failure->tcp_notsent_bytes = tcp_after->notsent_bytes;
                failure->tcp_unacked_segments = tcp_after->unacked_segments;
                failure->tcp_snapshot_age_ms =
                    (now_seconds() - tcp_after->sampled_at_seconds) * 1000.0;
                if (tcp_before->available && tcp_before->socket == tcp_after->socket) {
                    failure->tcp_bytes_acked_delta =
                        (long long)(tcp_after->bytes_acked - tcp_before->bytes_acked);
                }
            }
        }
        (void)curl_easy_getinfo(curl, CURLINFO_CONNECT_TIME, &failure->connect_time_seconds);
        (void)curl_easy_getinfo(
            curl,
            CURLINFO_STARTTRANSFER_TIME,
            &failure->starttransfer_time_seconds
        );
        (void)curl_easy_getinfo(curl, CURLINFO_TOTAL_TIME, &failure->total_time_seconds);
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
    if (shared->tcp_diagnostics) {
        curl_easy_setopt(curl, CURLOPT_SOCKOPTFUNCTION, record_client_socket);
        curl_easy_setopt(curl, CURLOPT_SOCKOPTDATA, worker);
        curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
        curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, sample_transfer_progress);
        curl_easy_setopt(curl, CURLOPT_XFERINFODATA, worker);
    }
    if (shared->upload_trace) {
        curl_easy_setopt(curl, CURLOPT_VERBOSE, 1L);
        curl_easy_setopt(curl, CURLOPT_DEBUGFUNCTION, record_upload_data_out);
        curl_easy_setopt(curl, CURLOPT_DEBUGDATA, worker);
    }
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

    unsigned long long worker_attempt = 0;
    while (now_seconds() < shared->deadline
        && (shared->max_requests == 0
            || atomic_load(shared->request_count) < shared->max_requests)) {
        worker_attempt++;
        ResponseCheck check = {
            .expected = shared->expected_body,
            .expected_bytes = shared->expected_bytes,
            .offset = 0,
            .valid = 1,
        };
        upload.offset = 0;
        if (shared->upload_trace && !worker->upload_trace_selected
            && atomic_load(&shared->upload_trace_claimed) == 0) {
            worker->upload_trace_event_count = 0;
            worker->upload_trace_dropped_events = 0;
            worker->upload_trace_bytes = 0;
        }
        worker->latest_tcp_snapshot = (SocketSnapshot){.socket = CURL_SOCKET_BAD};
        worker->tcp_snapshot_count = 0;
        SocketSnapshot tcp_before = {.socket = CURL_SOCKET_BAD};
        if (shared->tcp_diagnostics) {
            tcp_before = read_socket_snapshot(worker->diagnostic_socket);
        }
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &check);
        double started = now_seconds();
        CURLcode result = curl_easy_perform(curl);
        double elapsed = now_seconds() - started;
        select_slow_upload_trace(curl, worker, worker_attempt, elapsed);
        if (result != CURLE_OK) {
            char reason[256];
            snprintf(reason, sizeof(reason), "libcurl: %s", curl_easy_strerror(result));
            set_transfer_failure(
                shared,
                curl,
                &upload,
                worker,
                worker_attempt,
                &tcp_before,
                reason
            );
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
    FirstFailure first_failure = {0};
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
        .first_failure = &first_failure,
        .tcp_diagnostics = 0,
        .upload_trace = 0,
        .upload_trace_claimed = 0,
    };

    const char *tcp_diagnostics = getenv("UVICORN_RS_HTTP_CLIENT_TCP_DIAGNOSTICS");
    if (tcp_diagnostics != NULL && tcp_diagnostics[0] != '\0'
        && strcmp(tcp_diagnostics, "0") != 0) {
        shared.tcp_diagnostics = 1;
    }

    const char *upload_trace = getenv("UVICORN_RS_HTTP_CLIENT_UPLOAD_TRACE");
    if (upload_trace != NULL && upload_trace[0] != '\0'
        && strcmp(upload_trace, "0") != 0) {
        shared.upload_trace = 1;
    }

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 2;
    pthread_t *threads = calloc((size_t)concurrency, sizeof(*threads));
    Worker *workers = calloc((size_t)concurrency, sizeof(*workers));
    if (threads == NULL || workers == NULL) return 2;
    int created = 0;
    for (int index = 0; index < concurrency; index++) {
        workers[index].shared = &shared;
        workers[index].worker_index = (unsigned int)index;
        workers[index].diagnostic_socket = CURL_SOCKET_BAD;
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
    if (first_failure.reason[0] == '\0') printf("null");
    else {
        printf("{\"reason\":\"");
        for (const char *p = first_failure.reason; *p != '\0'; p++) {
            if (*p == '"' || *p == '\\') putchar('\\');
            if (*p >= 0x20) putchar(*p);
        }
        printf("\"");
        if (first_failure.has_transfer_diagnostics) {
            printf(
                ",\"transfer\":{\"worker_index\":%u,\"worker_attempt\":%llu,"
                "\"expected_upload_bytes\":%zu,\"upload_callback_bytes\":%zu,"
                "\"curl_uploaded_bytes\":%lld,\"curl_downloaded_bytes\":%lld,"
                "\"response_code\":%ld,\"new_connections\":%ld,"
                "\"connect_time_seconds\":%.9f,\"starttransfer_time_seconds\":%.9f,"
                "\"total_time_seconds\":%.9f}",
                first_failure.worker_index,
                first_failure.worker_attempt,
                first_failure.expected_upload_bytes,
                first_failure.upload_callback_bytes,
                (long long)first_failure.curl_uploaded_bytes,
                (long long)first_failure.curl_downloaded_bytes,
                first_failure.response_code,
                first_failure.new_connections,
                first_failure.connect_time_seconds,
                first_failure.starttransfer_time_seconds,
                first_failure.total_time_seconds);
            if (shared.tcp_diagnostics) {
                printf(
                    ",\"client_tcp\":{\"local_port\":%ld,\"tcp_info_available\":%s,"
                    "\"tcp_info_before_available\":%s,\"tcp_snapshot_count\":%u,"
                    "\"bytes_acked_total\":%llu,\"bytes_acked_delta\":%lld,"
                    "\"bytes_acked_before\":%llu,\"notsent_bytes\":%u,"
                    "\"unacked_segments\":%u,\"snapshot_age_ms\":%.3f}",
                    first_failure.local_port,
                    first_failure.tcp_info_available ? "true" : "false",
                    first_failure.tcp_info_before_available ? "true" : "false",
                    first_failure.tcp_snapshot_count,
                    first_failure.tcp_bytes_acked,
                    first_failure.tcp_bytes_acked_delta,
                    first_failure.tcp_bytes_acked_before,
                    first_failure.tcp_notsent_bytes,
                    first_failure.tcp_unacked_segments,
                    first_failure.tcp_snapshot_age_ms);
            }
        }
        printf("}");
    }
    if (shared.upload_trace) {
        printf(",\"upload_trace\":");
        print_upload_traces(workers, created);
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
