//! Bounded request-body observations for opt-in diagnostic builds.

use std::collections::VecDeque;
use std::fmt::Write as _;
use std::io::Write as _;
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const RETAINED_EVENTS: usize = 128;

struct Event {
    offset_ns: u128,
    kind: &'static str,
    bytes: usize,
    flag: bool,
}

#[derive(Default)]
struct Events {
    seen: u64,
    read_bytes: usize,
    offered_bytes: usize,
    delivered_bytes: usize,
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
    started: Instant,
    unix_origin_ns: u128,
    origin_uncertainty_ns: u128,
    events: Mutex<Events>,
}

impl RequestUploadTrace {
    pub(crate) fn new(request_id: &str, lane: &'static str) -> Option<Self> {
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
            started,
            unix_origin_ns,
            origin_uncertainty_ns,
            events: Mutex::new(Events::default()),
        };
        trace.record("start", 0, false);
        Some(trace)
    }

    pub(crate) fn record(&self, kind: &'static str, bytes: usize, flag: bool) {
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
        if events.rows.len() == RETAINED_EVENTS {
            events.rows.pop_front();
        }
        events.rows.push_back(Event {
            offset_ns: self.started.elapsed().as_nanos(),
            kind,
            bytes,
            flag,
        });
    }

    fn snapshot(&self) -> String {
        let events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let mut output = format!(
            "uvicorn-rs-upload-trace schema=1 request={} lane={} origin_unix_ns={} origin_uncertainty_ns={} read_bytes={} offered_bytes={} delivered_bytes={} events_seen={} events_retained={} events_dropped={}\n",
            self.request_id,
            self.lane,
            self.unix_origin_ns,
            self.origin_uncertainty_ns,
            events.read_bytes,
            events.offered_bytes,
            events.delivered_bytes,
            events.seen,
            events.rows.len(),
            events.seen.saturating_sub(events.rows.len() as u64),
        );
        for event in &events.rows {
            let _ = writeln!(
                output,
                "uvicorn-rs-upload-event request={} lane={} offset_ns={} event={} bytes={} flag={}",
                self.request_id, self.lane, event.offset_ns, event.kind, event.bytes, event.flag,
            );
        }
        output
    }
}

impl Drop for RequestUploadTrace {
    fn drop(&mut self) {
        self.record("trace-drop", 0, false);
        // Write a complete request under one stderr lock. A killed process may
        // lack a terminal trace; collectors must retain that as missing evidence.
        let _ = std::io::stderr()
            .lock()
            .write_all(self.snapshot().as_bytes());
    }
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::panic)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unbounded_or_log_injecting_ids() {
        for id in ["", "1\nother=2", "secret", &"1".repeat(65)] {
            assert!(RequestUploadTrace::new(id, "pump").is_none());
        }
    }

    #[test]
    fn retains_a_separate_bounded_tail_for_each_request() {
        let Some(first) = RequestUploadTrace::new("0-1", "pump") else {
            unreachable!();
        };
        let Some(stalled) = RequestUploadTrace::new("1-1", "pump") else {
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
        let snapshot = stalled.snapshot();
        assert!(snapshot.contains("events_seen=2 events_retained=2 events_dropped=0"));
        assert!(snapshot.contains("event=read-wait"));
    }
}
