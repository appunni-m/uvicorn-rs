//! Opt-in, bounded HTTP-driver stream observations for diagnosing stalled HTTP/1 requests.

use std::{
    collections::VecDeque,
    fmt::Write as FmtWrite,
    io::{self, IoSlice, Write as IoWrite},
    net::SocketAddr,
    pin::Pin,
    sync::{
        Arc, Mutex,
        atomic::{AtomicU64, Ordering},
    },
    task::{Context, Poll},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

const RETAINED_EVENTS: usize = 64;
static NEXT_CONNECTION_ID: AtomicU64 = AtomicU64::new(1);

struct Event {
    offset_ns: u64,
    kind: &'static str,
    bytes: u64,
    wait_ns: Option<u64>,
    request_id: Option<String>,
    read_total: u64,
    write_total: u64,
}

/// Shared counters for a cleartext TCP connection.
pub(crate) struct ConnectionTrace {
    id: u64,
    peer_addr: SocketAddr,
    started: Instant,
    origin_unix_ns: u128,
    origin_uncertainty_ns: u128,
    read_bytes: AtomicU64,
    write_bytes: AtomicU64,
    read_ready_polls: AtomicU64,
    read_pending_polls: AtomicU64,
    read_eof: AtomicU64,
    read_errors: AtomicU64,
    write_ready_polls: AtomicU64,
    write_pending_polls: AtomicU64,
    write_errors: AtomicU64,
    max_read_wait_ns: AtomicU64,
    max_write_wait_ns: AtomicU64,
    events_seen: AtomicU64,
    events: Mutex<VecDeque<Event>>,
}

impl ConnectionTrace {
    pub(crate) fn new(peer_addr: SocketAddr) -> Self {
        let started = Instant::now();
        let origin_unix_ns = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let origin_uncertainty_ns = started.elapsed().as_nanos();
        Self {
            id: NEXT_CONNECTION_ID.fetch_add(1, Ordering::Relaxed),
            peer_addr,
            started,
            origin_unix_ns,
            origin_uncertainty_ns,
            read_bytes: AtomicU64::new(0),
            write_bytes: AtomicU64::new(0),
            read_ready_polls: AtomicU64::new(0),
            read_pending_polls: AtomicU64::new(0),
            read_eof: AtomicU64::new(0),
            read_errors: AtomicU64::new(0),
            write_ready_polls: AtomicU64::new(0),
            write_pending_polls: AtomicU64::new(0),
            write_errors: AtomicU64::new(0),
            max_read_wait_ns: AtomicU64::new(0),
            max_write_wait_ns: AtomicU64::new(0),
            events_seen: AtomicU64::new(0),
            events: Mutex::new(VecDeque::with_capacity(RETAINED_EVENTS)),
        }
    }

    pub(crate) fn request_dispatched(&self, request_id: &str) {
        if !valid_request_id(request_id) {
            return;
        }
        self.record_event("request-dispatched", 0, None, Some(request_id));
    }

    fn read_pending(&self) {
        self.read_pending_polls.fetch_add(1, Ordering::Relaxed);
    }

    fn read_ready(&self, bytes: u64, wait_ns: Option<u64>) {
        self.read_ready_polls.fetch_add(1, Ordering::Relaxed);
        self.read_bytes.fetch_add(bytes, Ordering::Relaxed);
        if let Some(wait_ns) = wait_ns {
            self.max_read_wait_ns.fetch_max(wait_ns, Ordering::Relaxed);
        }
        self.record_event("read-ready", bytes, wait_ns, None);
    }

    fn read_eof(&self, wait_ns: Option<u64>) {
        self.read_eof.fetch_add(1, Ordering::Relaxed);
        self.record_event("read-eof", 0, wait_ns, None);
    }

    fn read_error(&self, wait_ns: Option<u64>) {
        self.read_errors.fetch_add(1, Ordering::Relaxed);
        self.record_event("read-error", 0, wait_ns, None);
    }

    fn write_pending(&self) {
        self.write_pending_polls.fetch_add(1, Ordering::Relaxed);
    }

    fn write_ready(&self, bytes: u64, wait_ns: Option<u64>) {
        self.write_ready_polls.fetch_add(1, Ordering::Relaxed);
        self.write_bytes.fetch_add(bytes, Ordering::Relaxed);
        if let Some(wait_ns) = wait_ns {
            self.max_write_wait_ns.fetch_max(wait_ns, Ordering::Relaxed);
        }
        self.record_event("write-ready", bytes, wait_ns, None);
    }

    fn write_error(&self, wait_ns: Option<u64>) {
        self.write_errors.fetch_add(1, Ordering::Relaxed);
        self.record_event("write-error", 0, wait_ns, None);
    }

    fn record_event(
        &self,
        kind: &'static str,
        bytes: u64,
        wait_ns: Option<u64>,
        request_id: Option<&str>,
    ) {
        self.events_seen.fetch_add(1, Ordering::Relaxed);
        let mut events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if events.len() == RETAINED_EVENTS {
            events.pop_front();
        }
        events.push_back(Event {
            offset_ns: self.started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
            kind,
            bytes,
            wait_ns,
            request_id: request_id.map(str::to_owned),
            read_total: self.read_bytes.load(Ordering::Relaxed),
            write_total: self.write_bytes.load(Ordering::Relaxed),
        });
    }
}

impl Drop for ConnectionTrace {
    fn drop(&mut self) {
        let mut output = String::new();
        let _ = writeln!(
            output,
            "uvicorn-rs-connection-trace schema=1 read_layer=after-peer-read-adapter pid={} connection={} peer={} peer_port={} origin_unix_ns={} origin_uncertainty_ns={} elapsed_ns={} read_bytes={} write_bytes={} read_ready_polls={} read_pending_polls={} read_eof={} read_errors={} write_ready_polls={} write_pending_polls={} write_errors={} max_read_wait_ns={} max_write_wait_ns={} events_seen={} events_retained={} events_dropped={}",
            std::process::id(),
            self.id,
            self.peer_addr,
            self.peer_addr.port(),
            self.origin_unix_ns,
            self.origin_uncertainty_ns,
            self.started.elapsed().as_nanos(),
            self.read_bytes.load(Ordering::Relaxed),
            self.write_bytes.load(Ordering::Relaxed),
            self.read_ready_polls.load(Ordering::Relaxed),
            self.read_pending_polls.load(Ordering::Relaxed),
            self.read_eof.load(Ordering::Relaxed),
            self.read_errors.load(Ordering::Relaxed),
            self.write_ready_polls.load(Ordering::Relaxed),
            self.write_pending_polls.load(Ordering::Relaxed),
            self.write_errors.load(Ordering::Relaxed),
            self.max_read_wait_ns.load(Ordering::Relaxed),
            self.max_write_wait_ns.load(Ordering::Relaxed),
            self.events_seen.load(Ordering::Relaxed),
            self.events
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .len(),
            self.events_seen
                .load(Ordering::Relaxed)
                .saturating_sub(RETAINED_EVENTS as u64),
        );
        let events = self
            .events
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        for event in events.iter() {
            let _ = write!(
                output,
                "uvicorn-rs-connection-event schema=1 pid={} connection={} peer_port={} offset_ns={} event={} bytes={} read_total={} write_total={}",
                std::process::id(),
                self.id,
                self.peer_addr.port(),
                event.offset_ns,
                event.kind,
                event.bytes,
                event.read_total,
                event.write_total,
            );
            if let Some(wait_ns) = event.wait_ns {
                let _ = write!(output, " wait_ns={wait_ns}");
            }
            if let Some(request_id) = &event.request_id {
                let _ = write!(output, " request_id={request_id}");
            }
            output.push('\n');
        }
        let _ = io::stderr().lock().write_all(output.as_bytes());
    }
}

/// An opt-in wrapper that observes socket bytes without changing them.
pub(crate) struct ConnectionTraceIo<I> {
    inner: I,
    trace: Option<Arc<ConnectionTrace>>,
    read_pending_since: Option<Instant>,
    write_pending_since: Option<Instant>,
}

impl<I> ConnectionTraceIo<I> {
    pub(crate) fn new(inner: I, trace: Option<Arc<ConnectionTrace>>) -> Self {
        Self {
            inner,
            trace,
            read_pending_since: None,
            write_pending_since: None,
        }
    }
}

impl<I: AsyncRead + Unpin> AsyncRead for ConnectionTraceIo<I> {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        let filled_before = buffer.filled().len();
        let result = Pin::new(&mut this.inner).poll_read(context, buffer);
        if let Some(trace) = &this.trace {
            match &result {
                Poll::Pending => {
                    trace.read_pending();
                    if this.read_pending_since.is_none() {
                        this.read_pending_since = Some(Instant::now());
                    }
                }
                Poll::Ready(Ok(())) => {
                    let wait_ns = this.read_pending_since.take().map(duration_ns_since);
                    let bytes = buffer.filled().len().saturating_sub(filled_before) as u64;
                    if bytes > 0 {
                        trace.read_ready(bytes, wait_ns);
                    } else if buffer.remaining() > 0 {
                        trace.read_eof(wait_ns);
                    } else {
                        trace.read_ready(0, wait_ns);
                    }
                }
                Poll::Ready(Err(_)) => {
                    let wait_ns = this.read_pending_since.take().map(duration_ns_since);
                    trace.read_error(wait_ns);
                }
            }
        }
        result
    }
}

impl<I: AsyncWrite + Unpin> AsyncWrite for ConnectionTraceIo<I> {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        let result = Pin::new(&mut this.inner).poll_write(context, buffer);
        observe_write_result(this, &result);
        result
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffers: &[IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        let result = Pin::new(&mut this.inner).poll_write_vectored(context, buffers);
        observe_write_result(this, &result);
        result
    }

    fn is_write_vectored(&self) -> bool {
        self.inner.is_write_vectored()
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(context)
    }

    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(context)
    }
}

impl<I> Drop for ConnectionTraceIo<I> {
    fn drop(&mut self) {
        if let (Some(trace), Some(started)) = (&self.trace, self.read_pending_since) {
            let wait_ns = duration_ns_since(started);
            trace.max_read_wait_ns.fetch_max(wait_ns, Ordering::Relaxed);
            trace.record_event("read-pending-at-close", 0, Some(wait_ns), None);
        }
        if let (Some(trace), Some(started)) = (&self.trace, self.write_pending_since) {
            let wait_ns = duration_ns_since(started);
            trace
                .max_write_wait_ns
                .fetch_max(wait_ns, Ordering::Relaxed);
            trace.record_event("write-pending-at-close", 0, Some(wait_ns), None);
        }
    }
}

fn observe_write_result<I>(this: &mut ConnectionTraceIo<I>, result: &Poll<io::Result<usize>>) {
    let Some(trace) = &this.trace else {
        return;
    };
    match result {
        Poll::Pending => {
            trace.write_pending();
            if this.write_pending_since.is_none() {
                this.write_pending_since = Some(Instant::now());
            }
        }
        Poll::Ready(Ok(bytes)) => {
            let wait_ns = this.write_pending_since.take().map(duration_ns_since);
            trace.write_ready(*bytes as u64, wait_ns);
        }
        Poll::Ready(Err(_)) => {
            let wait_ns = this.write_pending_since.take().map(duration_ns_since);
            trace.write_error(wait_ns);
        }
    }
}

fn duration_ns_since(started: Instant) -> u64 {
    started.elapsed().as_nanos().min(u64::MAX as u128) as u64
}

fn valid_request_id(request_id: &str) -> bool {
    !request_id.is_empty()
        && request_id.len() <= 64
        && request_id
            .bytes()
            .all(|byte| byte.is_ascii_digit() || byte == b'-')
}
