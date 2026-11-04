/* Threaded libcurl HTTP/1.1 client for low-overhead, body-checked benchmarks. */
#define _POSIX_C_SOURCE 200809L

#include <curl/curl.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define MAX_UPLOAD_TRACE_EVENTS 256
#define MAX_SUCCESSFUL_UPLOAD_TRACES_PER_WORKER 32
#define MAX_UPLOAD_TRACE_REQUEST_SELECTORS 32

typedef struct {
    unsigned int worker_index;
    unsigned long long worker_attempt;
} UploadTraceRequestSelector;

typedef struct {
    const char *event;
    unsigned long long offset_ns;
    unsigned long long callback_calls;
    size_t callback_bytes;
    curl_off_t curl_uploaded_bytes;
    curl_off_t curl_downloaded_bytes;
} UploadTraceEvent;

typedef struct {
    double elapsed_seconds;
    unsigned long long worker_attempt;
    unsigned long long callback_calls;
    size_t callback_bytes;
    double started_monotonic;
    double first_callback_monotonic;
    double last_callback_monotonic;
    double completed_monotonic;
    double last_progress_monotonic;
    unsigned long long trace_events_seen;
    size_t trace_event_count;
    size_t trace_event_head;
    curl_off_t curl_uploaded_bytes;
    curl_off_t curl_downloaded_bytes;
    long response_code;
    long new_connections;
    UploadTraceEvent trace_events[MAX_UPLOAD_TRACE_EVENTS];
} SuccessfulUploadTrace;

typedef struct {
    const char *url;
    const char *method;
    const char *upload_body;
    size_t upload_bytes;
    size_t upload_chunk_bytes;
    int upload_trace;
    size_t upload_trace_selector_count;
    UploadTraceRequestSelector upload_trace_selectors[MAX_UPLOAD_TRACE_REQUEST_SELECTORS];
    unsigned long long max_requests;
    const char *expected_body;
    size_t expected_bytes;
    long expected_status;
    double deadline;
    struct curl_slist *headers;
    atomic_ullong *request_count;
    atomic_ullong *requests_completed_in_window;
    atomic_ullong *request_bytes;
    atomic_ullong *response_bytes;
    atomic_uint *failures;
    pthread_mutex_t *failure_lock;
    struct FirstFailure *first_failure;
} Shared;

typedef struct {
    Shared *shared;
    unsigned int worker_index;
    double *latencies;
    size_t latency_count;
    size_t latency_capacity;
    double last_transfer_completed_at;
    unsigned long long trace_callback_calls;
    unsigned long long trace_callback_bytes;
    unsigned long long trace_successful_transfers;
    unsigned long long trace_new_connections;
    unsigned long long trace_reused_transfers;
    size_t successful_trace_count;
    SuccessfulUploadTrace *successful_traces;
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
    int upload_trace;
    unsigned long long callback_calls;
    double request_started_monotonic;
    double first_callback_monotonic;
    double last_callback_monotonic;
    double completed_monotonic;
    double last_progress_monotonic;
    size_t trace_event_count;
    size_t trace_event_head;
    unsigned long long trace_events_seen;
    UploadTraceEvent trace_events[MAX_UPLOAD_TRACE_EVENTS];
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
    int trace_enabled;
    unsigned long long callback_calls;
    double started_monotonic;
    double first_callback_monotonic;
    double last_callback_monotonic;
    double last_progress_monotonic;
    curl_off_t last_progress_uploaded_bytes;
    curl_off_t last_progress_downloaded_bytes;
    double last_progress_sample_monotonic;
    curl_off_t last_progress_sample_uploaded_bytes;
    unsigned long long trace_events_seen;
    UploadTraceEvent *trace_events;
} UploadCursor;

static double now_seconds(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)now.tv_sec + (double)now.tv_nsec / 1e9;
}

static int is_decimal_number(const char *value) {
    if (value == NULL || value[0] == '\0') return 0;
    for (const char *cursor = value; *cursor != '\0'; cursor++) {
        if (*cursor < '0' || *cursor > '9') return 0;
    }
    return 1;
}

static int parse_upload_trace_request_selectors(
    const char *value,
    UploadTraceRequestSelector *selectors,
    size_t *selector_count
) {
    *selector_count = 0;
    if (value == NULL || value[0] == '\0') return 1;
    size_t length = strlen(value);
    if (value[0] == ',' || value[length - 1] == ',' || strstr(value, ",,") != NULL) {
        return 0;
    }

    char *copy = strdup(value);
    if (copy == NULL) return 0;
    char *save = NULL;
    for (char *token = strtok_r(copy, ",", &save); token != NULL;
         token = strtok_r(NULL, ",", &save)) {
        if (*selector_count == MAX_UPLOAD_TRACE_REQUEST_SELECTORS) {
            free(copy);
            return 0;
        }
        char *separator = strchr(token, ':');
        if (separator == NULL || strchr(separator + 1, ':') != NULL) {
            free(copy);
            return 0;
        }
        *separator = '\0';
        if (!is_decimal_number(token) || !is_decimal_number(separator + 1)) {
            free(copy);
            return 0;
        }
        errno = 0;
        char *worker_end = NULL;
        unsigned long worker_index = strtoul(token, &worker_end, 10);
        if (errno != 0 || worker_end == token || *worker_end != '\0' || worker_index > UINT_MAX) {
            free(copy);
            return 0;
        }
        errno = 0;
        char *attempt_end = NULL;
        unsigned long long worker_attempt = strtoull(separator + 1, &attempt_end, 10);
        if (errno != 0 || attempt_end == separator + 1 || *attempt_end != '\0'
            || worker_attempt == 0) {
            free(copy);
            return 0;
        }
        for (size_t index = 0; index < *selector_count; index++) {
            if (selectors[index].worker_index == (unsigned int)worker_index
                && selectors[index].worker_attempt == worker_attempt) {
                free(copy);
                return 0;
            }
        }
        selectors[*selector_count] = (UploadTraceRequestSelector){
            .worker_index = (unsigned int)worker_index,
            .worker_attempt = worker_attempt,
        };
        (*selector_count)++;
    }
    free(copy);
    return 1;
}

static int upload_trace_request_selected(
    const Shared *shared,
    unsigned int worker_index,
    unsigned long long worker_attempt
) {
    if (shared->upload_trace_selector_count == 0) return 1;
    for (size_t index = 0; index < shared->upload_trace_selector_count; index++) {
        const UploadTraceRequestSelector *selector = &shared->upload_trace_selectors[index];
        if (selector->worker_index == worker_index
            && selector->worker_attempt == worker_attempt) {
            return 1;
        }
    }
    return 0;
}

static void record_upload_trace_event(
    UploadCursor *upload,
    const char *event,
    double now,
    curl_off_t uploaded_bytes,
    curl_off_t downloaded_bytes
) {
    if (!upload->trace_enabled) return;
    size_t slot = (size_t)(upload->trace_events_seen % MAX_UPLOAD_TRACE_EVENTS);
    UploadTraceEvent *trace = &upload->trace_events[slot];
    double elapsed = now > upload->started_monotonic
        ? now - upload->started_monotonic
        : 0.0;
    trace->event = event;
    trace->offset_ns = (unsigned long long)(elapsed * 1e9);
    trace->callback_calls = upload->callback_calls;
    trace->callback_bytes = upload->offset;
    trace->curl_uploaded_bytes = (long long)uploaded_bytes;
    trace->curl_downloaded_bytes = (long long)downloaded_bytes;
    upload->trace_events_seen++;
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
    double now = 0.0;
    if (upload->trace_enabled) {
        now = now_seconds();
        if (upload->callback_calls == 0) upload->first_callback_monotonic = now;
        upload->last_callback_monotonic = now;
        upload->callback_calls++;
    }
    size_t capacity = size * count;
    if (upload->offset >= upload->bytes || capacity == 0) {
        if (upload->trace_enabled) {
            record_upload_trace_event(upload, "read-eof", now, -1, -1);
        }
        return 0;
    }
    size_t length = upload->bytes - upload->offset;
    if (length > capacity) length = capacity;
    /* This caps bytes returned to libcurl per read callback; it does not
       guarantee the same socket-write or TCP packet boundaries. */
    if (upload->chunk_bytes > 0 && length > upload->chunk_bytes) length = upload->chunk_bytes;
    memcpy(buffer, upload->body + upload->offset, length);
    upload->offset += length;
    if (upload->trace_enabled
        && (upload->callback_calls == 1
            || upload->callback_calls % 32 == 0
            || upload->offset == upload->bytes)) {
        record_upload_trace_event(upload, "read-callback", now, -1, -1);
    }
    return length;
}

static int record_transfer_progress(
    void *user_data,
    curl_off_t download_total,
    curl_off_t download_now,
    curl_off_t upload_total,
    curl_off_t upload_now
) {
    UploadCursor *upload = (UploadCursor *)user_data;
    if (!upload->trace_enabled) return 0;

    double now = now_seconds();
    int progress_changed = upload_now != upload->last_progress_uploaded_bytes
        || download_now != upload->last_progress_downloaded_bytes;
    if (progress_changed) {
        upload->last_progress_monotonic = now;
        upload->last_progress_uploaded_bytes = upload_now;
        upload->last_progress_downloaded_bytes = download_now;
    }

    int upload_sample_due = upload_now >= upload->last_progress_sample_uploaded_bytes
        && upload_now - upload->last_progress_sample_uploaded_bytes >= 65536;
    int time_sample_due = upload->last_progress_sample_monotonic == 0.0
        || now - upload->last_progress_sample_monotonic >= 0.100;
    int transfer_complete = upload_total > 0 && upload_now >= upload_total;
    if (upload_sample_due || time_sample_due || transfer_complete) {
        record_upload_trace_event(upload, "curl-progress", now, upload_now, download_now);
        upload->last_progress_sample_monotonic = now;
        upload->last_progress_sample_uploaded_bytes = upload_now;
    }
    (void)download_total;
    return 0;
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
    unsigned int worker_index,
    unsigned long long worker_attempt,
    const char *reason
) {
    atomic_fetch_add(shared->failures, 1);
    pthread_mutex_lock(shared->failure_lock);
    FirstFailure *failure = shared->first_failure;
    if (failure->reason[0] == '\0') {
        snprintf(failure->reason, sizeof(failure->reason), "%s", reason);
        failure->has_transfer_diagnostics = 1;
        failure->worker_index = worker_index;
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
        failure->upload_trace = upload->trace_enabled;
        failure->callback_calls = upload->callback_calls;
        failure->request_started_monotonic = upload->started_monotonic;
        failure->first_callback_monotonic = upload->first_callback_monotonic;
        failure->last_callback_monotonic = upload->last_callback_monotonic;
        failure->completed_monotonic = now_seconds();
        failure->last_progress_monotonic = upload->last_progress_monotonic;
        failure->trace_events_seen = upload->trace_events_seen;
        failure->trace_event_count = upload->trace_events_seen < MAX_UPLOAD_TRACE_EVENTS
            ? (size_t)upload->trace_events_seen
            : MAX_UPLOAD_TRACE_EVENTS;
        failure->trace_event_head = upload->trace_events_seen < MAX_UPLOAD_TRACE_EVENTS
            ? 0
            : (size_t)(upload->trace_events_seen % MAX_UPLOAD_TRACE_EVENTS);
        if (upload->trace_events != NULL) {
            memcpy(failure->trace_events, upload->trace_events, sizeof(failure->trace_events));
        }
#if LIBCURL_VERSION_NUM >= 0x073700
        (void)curl_easy_getinfo(curl, CURLINFO_SIZE_UPLOAD_T, &failure->curl_uploaded_bytes);
        (void)curl_easy_getinfo(curl, CURLINFO_SIZE_DOWNLOAD_T, &failure->curl_downloaded_bytes);
#endif
        (void)curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &failure->response_code);
        (void)curl_easy_getinfo(curl, CURLINFO_NUM_CONNECTS, &failure->new_connections);
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

static void retain_successful_upload_trace(
    Worker *worker,
    CURL *curl,
    const UploadCursor *upload,
    unsigned long long worker_attempt,
    double started,
    double completed,
    long response_code,
    long new_connections
) {
    if (!upload->trace_enabled) return;

    double elapsed = completed - started;
    size_t slot = worker->successful_trace_count;
    if (slot == MAX_SUCCESSFUL_UPLOAD_TRACES_PER_WORKER) {
        slot = 0;
        for (size_t index = 1; index < worker->successful_trace_count; index++) {
            if (worker->successful_traces[index].elapsed_seconds
                < worker->successful_traces[slot].elapsed_seconds) {
                slot = index;
            }
        }
        if (elapsed <= worker->successful_traces[slot].elapsed_seconds) return;
    } else {
        worker->successful_trace_count++;
    }

    SuccessfulUploadTrace *trace = &worker->successful_traces[slot];
    memset(trace, 0, sizeof(*trace));
    trace->elapsed_seconds = elapsed;
    trace->worker_attempt = worker_attempt;
    trace->callback_calls = upload->callback_calls;
    trace->callback_bytes = upload->offset;
    trace->started_monotonic = started;
    trace->first_callback_monotonic = upload->first_callback_monotonic;
    trace->last_callback_monotonic = upload->last_callback_monotonic;
    trace->completed_monotonic = completed;
    trace->last_progress_monotonic = upload->last_progress_monotonic;
    trace->trace_events_seen = upload->trace_events_seen;
    trace->trace_event_count = upload->trace_events_seen < MAX_UPLOAD_TRACE_EVENTS
        ? (size_t)upload->trace_events_seen
        : MAX_UPLOAD_TRACE_EVENTS;
    trace->trace_event_head = upload->trace_events_seen < MAX_UPLOAD_TRACE_EVENTS
        ? 0
        : (size_t)(upload->trace_events_seen % MAX_UPLOAD_TRACE_EVENTS);
    trace->response_code = response_code;
    trace->new_connections = new_connections;
    trace->curl_uploaded_bytes = (curl_off_t)-1;
    trace->curl_downloaded_bytes = (curl_off_t)-1;
    if (upload->trace_events != NULL) {
        memcpy(trace->trace_events, upload->trace_events, sizeof(trace->trace_events));
    }
#if LIBCURL_VERSION_NUM >= 0x073700
    (void)curl_easy_getinfo(curl, CURLINFO_SIZE_UPLOAD_T, &trace->curl_uploaded_bytes);
    (void)curl_easy_getinfo(curl, CURLINFO_SIZE_DOWNLOAD_T, &trace->curl_downloaded_bytes);
#endif
}

static void *run_worker(void *argument) {
    Worker *worker = (Worker *)argument;
    Shared *shared = worker->shared;
    CURL *curl = curl_easy_init();
    if (curl == NULL) {
        set_failure(shared, "curl_easy_init failed");
        return NULL;
    }
    if (shared->upload_trace) {
        worker->successful_traces = calloc(
            MAX_SUCCESSFUL_UPLOAD_TRACES_PER_WORKER,
            sizeof(*worker->successful_traces)
        );
        if (worker->successful_traces == NULL) {
            set_failure(shared, "could not allocate successful upload trace retention");
            curl_easy_cleanup(curl);
            return NULL;
        }
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
        .trace_enabled = shared->upload_trace,
    };
    if (shared->upload_trace) {
        upload.trace_events = calloc(MAX_UPLOAD_TRACE_EVENTS, sizeof(*upload.trace_events));
        if (upload.trace_events == NULL) {
            set_failure(shared, "could not allocate upload trace events");
            curl_easy_cleanup(curl);
            return NULL;
        }
        curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
        curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, record_transfer_progress);
        curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &upload);
    }
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
        upload.trace_enabled = shared->upload_trace
            && upload_trace_request_selected(shared, worker->worker_index, worker_attempt);
        if (shared->upload_trace) {
            curl_easy_setopt(curl, CURLOPT_NOPROGRESS, upload.trace_enabled ? 0L : 1L);
        }
        ResponseCheck check = {
            .expected = shared->expected_body,
            .expected_bytes = shared->expected_bytes,
            .offset = 0,
            .valid = 1,
        };
        upload.offset = 0;
        upload.callback_calls = 0;
        upload.first_callback_monotonic = 0;
        upload.last_callback_monotonic = 0;
        upload.last_progress_monotonic = 0;
        upload.last_progress_uploaded_bytes = 0;
        upload.last_progress_downloaded_bytes = 0;
        upload.last_progress_sample_monotonic = 0;
        upload.last_progress_sample_uploaded_bytes = 0;
        upload.trace_events_seen = 0;
        if (upload.trace_events != NULL) {
            memset(upload.trace_events, 0,
                MAX_UPLOAD_TRACE_EVENTS * sizeof(*upload.trace_events));
        }
        // libcurl borrows this list only during the synchronous transfer. The
        // stack node prepends one diagnostic header without copying base headers.
        char trace_header[128];
        struct curl_slist trace_node = {.data = trace_header, .next = shared->headers};
        if (upload.trace_enabled) {
            snprintf(trace_header, sizeof(trace_header),
                "X-Uvicorn-Rs-Upload-Trace: %ld-%u-%llu", (long)getpid(),
                worker->worker_index, worker_attempt);
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, &trace_node);
        } else if (shared->upload_trace) {
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, shared->headers);
        }
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &check);
        double started = now_seconds();
        upload.started_monotonic = started;
        upload.last_progress_monotonic = started;
        CURLcode result = curl_easy_perform(curl);
        if (shared->upload_trace) curl_easy_setopt(curl, CURLOPT_HTTPHEADER, shared->headers);
        double completed_at = now_seconds();
        worker->last_transfer_completed_at = completed_at;
        double elapsed = completed_at - started;
        worker->trace_callback_calls += upload.callback_calls;
        if (upload.trace_enabled) worker->trace_callback_bytes += upload.offset;
        if (result != CURLE_OK) {
            char reason[256];
            snprintf(reason, sizeof(reason), "libcurl: %s", curl_easy_strerror(result));
            set_transfer_failure(
                shared,
                curl,
                &upload,
                worker->worker_index,
                worker_attempt,
                reason
            );
            break;
        }

        long new_connections = 0;
        if (shared->upload_trace) {
            (void)curl_easy_getinfo(curl, CURLINFO_NUM_CONNECTS, &new_connections);
            worker->trace_successful_transfers++;
            if (new_connections > 0) {
                worker->trace_new_connections += (unsigned long long)new_connections;
            } else {
                worker->trace_reused_transfers++;
            }
        }

        long status = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
        retain_successful_upload_trace(
            worker, curl, &upload, worker_attempt, started, completed_at, status,
            new_connections
        );
        if (status != shared->expected_status) {
            char reason[256];
            snprintf(reason, sizeof(reason), "unexpected HTTP status %ld (wanted %ld)", status, shared->expected_status);
            set_failure(shared, reason);
        }
        if (!check.valid || check.offset != shared->expected_bytes) {
            set_failure(shared, "response body differs from the complete expected bytes");
        }

        atomic_fetch_add(shared->request_count, 1);
        if (completed_at <= shared->deadline) {
            atomic_fetch_add(shared->requests_completed_in_window, 1);
        }
        if (shared->upload_bytes != 0) atomic_fetch_add(shared->request_bytes, shared->upload_bytes);
        atomic_fetch_add(shared->response_bytes, check.offset);
        if (!append_latency(worker, elapsed)) {
            set_failure(shared, "could not grow client latency sample buffer");
            break;
        }
    }

    curl_easy_cleanup(curl);
    free(upload.trace_events);
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
    atomic_ullong requests = 0, requests_completed_in_window = 0;
    atomic_ullong request_bytes = 0, response_bytes_total = 0;
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
        .upload_trace = getenv("UVICORN_RS_UPLOAD_TRACE") != NULL
            && strcmp(getenv("UVICORN_RS_UPLOAD_TRACE"), "1") == 0,
        .max_requests = max_requests,
        .expected_body = expected_body,
        .expected_bytes = expected_bytes,
        .expected_status = expected_status,
        .deadline = started + seconds,
        .headers = headers,
        .request_count = &requests,
        .requests_completed_in_window = &requests_completed_in_window,
        .request_bytes = &request_bytes,
        .response_bytes = &response_bytes_total,
        .failures = &failures,
        .failure_lock = &failure_lock,
        .first_failure = &first_failure,
    };

    const char *trace_request_selection = getenv("UVICORN_RS_UPLOAD_TRACE_REQUESTS");
    if (!shared.upload_trace && trace_request_selection != NULL
        && trace_request_selection[0] != '\0') {
        fprintf(stderr, "UVICORN_RS_UPLOAD_TRACE_REQUESTS requires UVICORN_RS_UPLOAD_TRACE=1\n");
        return 2;
    }
    if (!parse_upload_trace_request_selectors(
            trace_request_selection,
            shared.upload_trace_selectors,
            &shared.upload_trace_selector_count)) {
        fprintf(stderr,
            "UVICORN_RS_UPLOAD_TRACE_REQUESTS must be comma-separated worker:attempt pairs "
            "with at most %d unique selectors\n",
            MAX_UPLOAD_TRACE_REQUEST_SELECTORS);
        return 2;
    }
    for (size_t index = 0; index < shared.upload_trace_selector_count; index++) {
        if (shared.upload_trace_selectors[index].worker_index >= (unsigned int)concurrency) {
            fprintf(stderr,
                "UVICORN_RS_UPLOAD_TRACE_REQUESTS contains worker %u, outside concurrency %d\n",
                shared.upload_trace_selectors[index].worker_index,
                concurrency);
            return 2;
        }
    }

    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 2;
    pthread_t *threads = calloc((size_t)concurrency, sizeof(*threads));
    Worker *workers = calloc((size_t)concurrency, sizeof(*workers));
    if (threads == NULL || workers == NULL) return 2;
    int created = 0;
    for (int index = 0; index < concurrency; index++) {
        workers[index].shared = &shared;
        workers[index].worker_index = (unsigned int)index;
        if (pthread_create(&threads[index], NULL, run_worker, &workers[index]) != 0) {
            set_failure(&shared, "pthread_create failed");
            break;
        }
        created++;
    }
    for (int index = 0; index < created; index++) pthread_join(threads[index], NULL);
    double elapsed = now_seconds() - started;
    double last_transfer_completed_at = started;
    for (int index = 0; index < created; index++) {
        if (workers[index].last_transfer_completed_at > last_transfer_completed_at) {
            last_transfer_completed_at = workers[index].last_transfer_completed_at;
        }
    }

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
    unsigned long long completed_in_window = atomic_load(&requests_completed_in_window);
    unsigned long long sent = atomic_load(&request_bytes);
    unsigned long long received = atomic_load(&response_bytes_total);
    unsigned int failure_count = atomic_load(&failures);
    double latency_sum = 0.0;
    for (size_t index = 0; index < latency_count; index++) latency_sum += latencies[index];
    double mean_ms = latency_count == 0 ? 0.0 : latency_sum * 1000.0 / (double)latency_count;
    double max_ms = latency_count == 0 ? 0.0 : latencies[latency_count - 1] * 1000.0;
    double deadline = started + seconds;
    double drain_seconds = last_transfer_completed_at > deadline
        ? last_transfer_completed_at - deadline
        : 0.0;
    printf("{\"requests\":%llu,\"duration_seconds\":%.9f,\"load_window_seconds\":%.9f,\"completion_drain_seconds\":%.9f,\"requests_per_second\":%.3f,\"requests_completed_in_window\":%llu,\"requests_completed_after_window\":%llu,\"requests_per_second_in_window\":%.3f,\"request_body_bytes\":%llu,\"response_body_bytes\":%llu,\"application_bytes_per_second\":%.3f,\"mean_ms\":%.6f,\"p50_ms\":%.6f,\"p95_ms\":%.6f,\"p99_ms\":%.6f,\"p99_9_ms\":%.6f,\"max_ms\":%.6f,\"failures\":%u,\"first_failure\":",
        count, elapsed, seconds, drain_seconds, count / elapsed, completed_in_window,
        count - completed_in_window, completed_in_window / seconds, sent, received, (sent + received) / elapsed,
        mean_ms, percentile(latencies, latency_count, 0.50), percentile(latencies, latency_count, 0.95),
        percentile(latencies, latency_count, 0.99), percentile(latencies, latency_count, 0.999), max_ms, failure_count);
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
            if (first_failure.upload_trace) {
                printf(
                    ",\"upload_trace\":{\"request_id\":\"%ld-%u-%llu\","
                    "\"callback_calls\":%llu,\"clock\":\"CLOCK_MONOTONIC seconds\","
                    "\"started\":%.9f,\"first_callback\":%.9f,"
                    "\"last_callback\":%.9f,\"completed\":%.9f,"
                    "\"last_progress\":%.9f,\"last_progress_age_ms\":%.3f,"
                    "\"events_seen\":%llu,\"events_retained\":%zu,"
                    "\"events_dropped\":%llu,\"events\":[",
                    (long)getpid(), first_failure.worker_index, first_failure.worker_attempt,
                    first_failure.callback_calls, first_failure.request_started_monotonic,
                    first_failure.first_callback_monotonic, first_failure.last_callback_monotonic,
                    first_failure.completed_monotonic, first_failure.last_progress_monotonic,
                    first_failure.completed_monotonic >= first_failure.last_progress_monotonic
                        ? (first_failure.completed_monotonic - first_failure.last_progress_monotonic) * 1000.0
                        : 0.0,
                    first_failure.trace_events_seen, first_failure.trace_event_count,
                    first_failure.trace_events_seen > first_failure.trace_event_count
                        ? first_failure.trace_events_seen - first_failure.trace_event_count
                        : 0ULL);
                for (size_t index = 0; index < first_failure.trace_event_count; index++) {
                    size_t slot = (first_failure.trace_event_head + index) % MAX_UPLOAD_TRACE_EVENTS;
                    const UploadTraceEvent *event = &first_failure.trace_events[slot];
                    if (index > 0) putchar(',');
                    printf(
                        "{\"event\":\"%s\",\"offset_ns\":%llu,"
                        "\"callback_calls\":%llu,\"callback_bytes\":%zu,"
                        "\"curl_uploaded_bytes\":%lld,\"curl_downloaded_bytes\":%lld}",
                        event->event != NULL ? event->event : "unknown",
                        event->offset_ns,
                        event->callback_calls,
                        event->callback_bytes,
                        (long long)event->curl_uploaded_bytes,
                        (long long)event->curl_downloaded_bytes);
                }
                putchar(']');
                putchar('}');
            }
        }
        printf("}");
    }
    if (shared.upload_trace) {
        unsigned long long calls = 0, bytes = 0;
        unsigned long long successful_transfers = 0, new_connections = 0;
        unsigned long long reused_transfers = 0;
        for (int index = 0; index < created; index++) {
            calls += workers[index].trace_callback_calls;
            bytes += workers[index].trace_callback_bytes;
            successful_transfers += workers[index].trace_successful_transfers;
            new_connections += workers[index].trace_new_connections;
            reused_transfers += workers[index].trace_reused_transfers;
        }
        struct timespec wall;
        double calibration_before = now_seconds();
        clock_gettime(CLOCK_REALTIME, &wall);
        double calibration_after = now_seconds();
        printf(
            ",\"upload_trace\":{\"schema\":1,\"diagnostic_only\":true,"
            "\"request_selection\":[");
        if (shared.upload_trace_selector_count == 0) {
            printf("\"all\"");
        } else {
            for (size_t index = 0; index < shared.upload_trace_selector_count; index++) {
                const UploadTraceRequestSelector *selector = &shared.upload_trace_selectors[index];
                if (index > 0) putchar(',');
                printf("\"%u:%llu\"", selector->worker_index, selector->worker_attempt);
            }
        }
        printf(
            "],\"callback_calls\":%llu,\"callback_bytes\":%llu,\"timeout_ms\":15000,"
            "\"connection_counts\":{\"curl_successful_transfers\":%llu,"
            "\"new_connections\":%llu,\"reused_transfers\":%llu},"
            "\"failure_event_limit\":%d,"
            "\"sampling\":\"upload callback first/every 32/final; curl progress every 64 KiB or 100 ms\","
            "\"calibration_monotonic_before\":%.9f,\"calibration_monotonic_after\":%.9f,"
            "\"calibration_unix\":%.9f,"
            "\"successful_transfer_trace_limit_per_worker\":%d,"
            "\"successful_transfers\":[",
            calls, bytes, successful_transfers, new_connections, reused_transfers,
            MAX_UPLOAD_TRACE_EVENTS, calibration_before, calibration_after,
            (double)wall.tv_sec + (double)wall.tv_nsec / 1e9,
            MAX_SUCCESSFUL_UPLOAD_TRACES_PER_WORKER);
        int first_successful_trace = 1;
        for (int worker_index = 0; worker_index < created; worker_index++) {
            Worker *worker = &workers[worker_index];
            for (size_t trace_index = 0; trace_index < worker->successful_trace_count; trace_index++) {
                const SuccessfulUploadTrace *trace = &worker->successful_traces[trace_index];
                if (!first_successful_trace) putchar(',');
                first_successful_trace = 0;
                printf(
                    "{\"request_id\":\"%ld-%u-%llu\",\"worker_index\":%u,"
                    "\"worker_attempt\":%llu,\"elapsed_ms\":%.6f,"
                    "\"expected_upload_bytes\":%zu,\"callback_calls\":%llu,"
                    "\"callback_bytes\":%zu,\"curl_uploaded_bytes\":%lld,"
                    "\"curl_downloaded_bytes\":%lld,\"response_code\":%ld,"
                    "\"new_connections\":%ld,\"started\":%.9f,"
                    "\"first_callback\":%.9f,\"last_callback\":%.9f,"
                    "\"completed\":%.9f,\"last_progress\":%.9f,"
                    "\"events_seen\":%llu,\"events_retained\":%zu,"
                    "\"events_dropped\":%llu,\"events\":[",
                    (long)getpid(), (unsigned int)worker_index, trace->worker_attempt,
                    (unsigned int)worker_index,
                    trace->worker_attempt, trace->elapsed_seconds * 1000.0,
                    shared.upload_bytes, trace->callback_calls, trace->callback_bytes,
                    (long long)trace->curl_uploaded_bytes,
                    (long long)trace->curl_downloaded_bytes,
                    trace->response_code, trace->new_connections, trace->started_monotonic,
                    trace->first_callback_monotonic, trace->last_callback_monotonic,
                    trace->completed_monotonic, trace->last_progress_monotonic,
                    trace->trace_events_seen, trace->trace_event_count,
                    trace->trace_events_seen > trace->trace_event_count
                        ? trace->trace_events_seen - trace->trace_event_count
                        : 0ULL);
                for (size_t event_index = 0; event_index < trace->trace_event_count; event_index++) {
                    size_t slot = (trace->trace_event_head + event_index) % MAX_UPLOAD_TRACE_EVENTS;
                    const UploadTraceEvent *event = &trace->trace_events[slot];
                    if (event_index > 0) putchar(',');
                    printf(
                        "{\"event\":\"%s\",\"offset_ns\":%llu,"
                        "\"callback_calls\":%llu,\"callback_bytes\":%zu,"
                        "\"curl_uploaded_bytes\":%lld,\"curl_downloaded_bytes\":%lld}",
                        event->event != NULL ? event->event : "unknown",
                        event->offset_ns, event->callback_calls, event->callback_bytes,
                        (long long)event->curl_uploaded_bytes,
                        (long long)event->curl_downloaded_bytes);
                }
                printf("]}");
            }
        }
        printf("]}");
    }
    printf("}\n");

    free(latencies);
    for (int index = 0; index < created; index++) free(workers[index].successful_traces);
    free(workers);
    free(threads);
    free(expected_body);
    free(upload_body);
    curl_slist_free_all(headers);
    pthread_mutex_destroy(&failure_lock);
    curl_global_cleanup();
    return failure_count == 0 && count > 0 ? 0 : 1;
}
