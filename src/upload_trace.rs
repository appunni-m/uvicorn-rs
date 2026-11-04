//! Bounded request-body observations for opt-in diagnostic builds.

use std::collections::VecDeque;
use std::fmt::Write as _;
use std::io::Write as _;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const RETAINED_EVENTS: usize = 128;
const DEFAULT_SLOW_REQUEST_TRACE_THRESHOLD_MS: u64 = 100;
const MIN_SLOW_REQUEST_TRACE_THRESHOLD_MS: u64 = 1;
const MAX_SLOW_REQUEST_TRACE_THRESHOLD_MS: u64 = 1_000;
static SLOW_REQUEST_TRACE_THRESHOLD: OnceLock<Duration> = OnceLock::new();

struct Event {
    offset_ns: u128,
    kind: &'static str,
    bytes: usize,
    flag: bool,
    value: Option<u64>,
    duration_ns: Option<u64>,
}

#[derive(Default)]
struct Events {
    seen: u64,
    read_bytes: usize,
    offered_bytes: usize,
    delivered_bytes: usize,
    abnormal: bool,
    rows: VecDeque<Event>,
}

/// Keep the tail of each request independently, including stalled requests.
///
/// One busy connection cannot evict another connection's observations. The
/// origin samples wall time for correlation, with the sampling window retained.
/// Cross-process comparisons must also account for clock resolution and wall
/// clock adjustments; the request ID and within-process order are authoritative.
pub(crate) struct RequestUploadTrace {
    request_id: String,
    lane: &'static str,
    expected_bytes: Option<usize>,
    started: Instant,
    unix_origin_ns: u128,
    origin_uncertainty_ns: u128,
    events: Mutex<Events>,
}

impl RequestUploadTrace {
    pub(crate) fn new(
        request_id: &str,
        lane: &'static str,
        expected_bytes: Option<usize>,
    ) -> Option<Self> {
        // IDs are diagnostic correlation data, never arbitrary header contents.
        if request_id.is_empty()
            || request_id.len() > 64
            || !request_id.bytes().all(|b| b.is_ascii_digit() || b == b'-')
        {
            return None;
        }
        let started = Instant::now();
        let unix_origin_ns = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .ok()?
            .as_nanos();
        let origin_uncertainty_ns = started.elapsed().as_nanos();
        let trace = Self {
            request_id: request_id.to_owned(),
            lane,
            expected_bytes,
            started,
            unix_origin_ns,
            origin_uncertainty_ns,
            events: Mutex::new(Events::default()),
        };
        trace.record("start", 0, false);
        Some(trace)
    }

    pub(crate) fn record(&self, kind: &'static str, bytes: usize, flag: bool) {
        self.record_inner(kind, bytes, flag, None, None);
    }

    pub(crate) fn record_with_value(
        &self,
        kind: &'static str,
        bytes: usize,
        flag: bool,
        value: u64,
    ) {
        self.record_inner(kind, bytes, flag, Some(value), None);
    }

    pub(crate) fn record_with_duration(
        &self,
        kind: &'static str,
        bytes: usize,
        flag: bool,
        duration_ns: u64,
    ) {
        self.record_inner(kind, bytes, flag, None, Some(duration_ns));
    }

    fn record_inner(
        &self,
        kind: &'static str,
        bytes: usize,
        flag: bool,
        value: Option<u64>,
        duration_ns: Option<u64>,
    ) {
        let mut events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        events.seen = events.seen.saturating_add(1);
        match kind {
            "read-data" => events.read_bytes = events.read_bytes.saturating_add(bytes),
            "queue-offer" => events.offered_bytes = events.offered_bytes.saturating_add(bytes),
            "asgi-deliver" => events.delivered_bytes = events.delivered_bytes.saturating_add(bytes),
            _ => {}
        }
        events.abnormal |= is_abnormal_event(kind, flag);
        if events.rows.len() == RETAINED_EVENTS {
            events.rows.pop_front();
        }
        events.rows.push_back(Event {
            offset_ns: self.started.elapsed().as_nanos(),
            kind,
            bytes,
            flag,
            value,
            duration_ns,
        });
    }

    fn emission_reason(&self) -> Option<&'static str> {
        let elapsed = self.started.elapsed();
        let events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let body_mismatch = self.expected_bytes.is_some_and(|expected| match self.lane {
            "pump" => events.read_bytes != expected || events.offered_bytes != expected,
            "asgi" => events.delivered_bytes != expected,
            _ => false,
        });
        trace_emission_reason(
            elapsed,
            events.abnormal,
            body_mismatch,
            slow_request_trace_threshold(),
        )
    }

    fn snapshot(&self, reason: &str) -> String {
        let events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let mut output = format!(
            "uvicorn-rs-upload-trace schema=1 request={} lane={} origin_unix_ns={} origin_uncertainty_ns={} expected_bytes={} emission_reason={} read_bytes={} offered_bytes={} delivered_bytes={} events_seen={} events_retained={} events_dropped={}\n",
            self.request_id,
            self.lane,
            self.unix_origin_ns,
            self.origin_uncertainty_ns,
            self.expected_bytes
                .map_or_else(|| "unknown".to_owned(), |bytes| bytes.to_string()),
            reason,
            events.read_bytes,
            events.offered_bytes,
            events.delivered_bytes,
            events.seen,
            events.rows.len(),
            events.seen.saturating_sub(events.rows.len() as u64),
        );
        for event in &events.rows {
            let _ = write!(
                output,
                "uvicorn-rs-upload-event request={} lane={} offset_ns={} event={} bytes={} flag={}",
                self.request_id, self.lane, event.offset_ns, event.kind, event.bytes, event.flag,
            );
            if let Some(value) = event.value {
                let _ = write!(output, " value={value}");
            }
            if let Some(duration_ns) = event.duration_ns {
                let _ = write!(output, " duration_ns={duration_ns}");
            }
            output.push('\n');
        }
        output
    }
}

impl Drop for RequestUploadTrace {
    fn drop(&mut self) {
        self.record("trace-drop", 0, false);
        let Some(reason) = self.emission_reason() else {
            return;
        };
        // Write a complete request under one stderr lock. A killed process may
        // lack a terminal trace; collectors must retain that as missing evidence.
        let _ = std::io::stderr()
            .lock()
            .write_all(self.snapshot(reason).as_bytes());
    }
}

fn trace_emission_reason(
    elapsed: Duration,
    abnormal_event: bool,
    body_mismatch: bool,
    slow_threshold: Duration,
) -> Option<&'static str> {
    if abnormal_event {
        Some("abnormal-event")
    } else if body_mismatch {
        Some("body-size-mismatch")
    } else if elapsed >= slow_threshold {
        Some("slow")
    } else {
        None
    }
}

fn slow_request_trace_threshold() -> Duration {
    *SLOW_REQUEST_TRACE_THRESHOLD.get_or_init(|| {
        let configured = std::env::var("UVICORN_RS_UPLOAD_TRACE_MIN_MS").ok();
        parse_slow_request_trace_threshold(configured.as_deref())
    })
}

fn parse_slow_request_trace_threshold(value: Option<&str>) -> Duration {
    let milliseconds = value
        .and_then(|value| value.parse::<u64>().ok())
        .filter(|value| {
            (MIN_SLOW_REQUEST_TRACE_THRESHOLD_MS..=MAX_SLOW_REQUEST_TRACE_THRESHOLD_MS)
                .contains(value)
        });
    Duration::from_millis(milliseconds.unwrap_or(DEFAULT_SLOW_REQUEST_TRACE_THRESHOLD_MS))
}

fn is_abnormal_event(kind: &str, flag: bool) -> bool {
    matches!(
        kind,
        "read-error"
            | "read-cancelled"
            | "queue-closed"
            | "queue-send-cancelled"
            | "pump-stop"
            | "http-response-poll-abandoned"
    ) || (flag
        && matches!(
            kind,
            "queue-send-result"
                | "connection-closed"
                | "server-cancelled"
                | "request-cancelled"
                | "service-response-error"
                | "protocol-request-lifetime-missing"
                | "protocol-request-ended-without-reason"
                | "protocol-request-ended-service-future-dropped"
                | "protocol-request-ended-service-failed"
                | "protocol-request-ended-response-body-failed"
                | "protocol-request-ended-response-body-dropped"
        ))
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::panic)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unbounded_or_log_injecting_ids() {
        for id in ["", "1\nother=2", "secret", &"1".repeat(65)] {
            assert!(RequestUploadTrace::new(id, "pump", None).is_none());
        }
    }

    #[test]
    fn retains_a_separate_bounded_tail_for_each_request() {
        let Some(first) = RequestUploadTrace::new("0-1", "pump", None) else {
            unreachable!();
        };
        let Some(stalled) = RequestUploadTrace::new("1-1", "pump", None) else {
            unreachable!();
        };
        stalled.record("read-wait", 0, false);
        for index in 0..1000 {
            first.record("read-data", index, false);
        }
        let rows = first.events.lock().unwrap();
        assert_eq!(rows.rows.len(), RETAINED_EVENTS);
        assert_eq!(rows.seen, 1001);
        assert_eq!(rows.read_bytes, (0..1000).sum::<usize>());
        assert_eq!(rows.rows.back().unwrap().bytes, 999);
        assert!(rows.rows.iter().map(|row| row.offset_ns).is_sorted());
        drop(rows);
        let snapshot = stalled.snapshot("test");
        assert!(snapshot.contains("events_seen=2 events_retained=2 events_dropped=0"));
        assert!(snapshot.contains("event=read-wait"));
    }

    #[test]
    fn emits_only_slow_abnormal_or_incomplete_request_traces() {
        assert_eq!(
            trace_emission_reason(
                Duration::from_millis(30),
                false,
                false,
                Duration::from_millis(100),
            ),
            None
        );
        assert_eq!(
            trace_emission_reason(
                Duration::from_millis(30),
                true,
                false,
                Duration::from_millis(100),
            ),
            Some("abnormal-event")
        );
        assert_eq!(
            trace_emission_reason(
                Duration::from_millis(30),
                false,
                true,
                Duration::from_millis(100),
            ),
            Some("body-size-mismatch")
        );
        assert_eq!(
            trace_emission_reason(
                Duration::from_millis(101),
                false,
                false,
                Duration::from_millis(100),
            ),
            Some("slow")
        );
        assert_eq!(
            trace_emission_reason(
                Duration::from_millis(30),
                false,
                false,
                Duration::from_millis(20),
            ),
            Some("slow")
        );
        assert!(is_abnormal_event("request-cancelled", true));
        assert!(!is_abnormal_event("request-cancelled", false));
        assert!(is_abnormal_event("pump-stop", true));
        assert!(!is_abnormal_event("queue-offer", true));
    }

    #[test]
    fn bounds_the_configurable_slow_trace_threshold() {
        assert_eq!(
            parse_slow_request_trace_threshold(Some("20")),
            Duration::from_millis(20),
        );
        assert_eq!(
            parse_slow_request_trace_threshold(Some("0")),
            Duration::from_millis(DEFAULT_SLOW_REQUEST_TRACE_THRESHOLD_MS),
        );
        assert_eq!(
            parse_slow_request_trace_threshold(Some("1001")),
            Duration::from_millis(DEFAULT_SLOW_REQUEST_TRACE_THRESHOLD_MS),
        );
        assert_eq!(
            parse_slow_request_trace_threshold(Some("invalid")),
            Duration::from_millis(DEFAULT_SLOW_REQUEST_TRACE_THRESHOLD_MS),
        );
    }

    #[test]
    fn retains_response_status_values_in_the_trace() {
        let Some(trace) = RequestUploadTrace::new("1-0-1", "asgi", Some(1024)) else {
            unreachable!();
        };
        trace.record_with_value("asgi-response-start-queued", 0, false, 200);

        let snapshot = trace.snapshot("test");
        assert!(snapshot.contains("event=asgi-response-start-queued bytes=0 flag=false value=200"));
    }

    #[test]
    fn retains_stage_durations_as_nanoseconds() {
        let Some(trace) = RequestUploadTrace::new("1-0-2", "pump", Some(1024)) else {
            unreachable!();
        };
        trace.record_with_duration("queue-send-finished", 0, true, 12_345);

        let snapshot = trace.snapshot("test");
        assert!(snapshot.contains("event=queue-send-finished bytes=0 flag=true duration_ns=12345"));
    }
}
