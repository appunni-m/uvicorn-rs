use std::{
    future::Future,
    io,
    pin::Pin,
    task::{Context, Poll},
};

#[cfg(feature = "runtime-diagnostics")]
use std::{
    net::SocketAddr,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use bytes::{Buf, BufMut, Bytes, BytesMut};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    net::{tcp::OwnedReadHalf, tcp::OwnedWriteHalf, TcpStream},
    sync::{mpsc, watch},
};

use super::{PeerReadHalfCloseMode, PeerReadHalfClosed};

const READ_CHUNK_SIZE: usize = 16 * 1024;
const READ_QUEUE_CAPACITY: usize = 2;

#[cfg(feature = "runtime-diagnostics")]
const READ_WAIT_TRACE_THRESHOLD: Duration = Duration::from_millis(10);

#[cfg(feature = "runtime-diagnostics")]
const READ_WAIT_TRACE_LIMIT: u64 = 128;

pub(super) enum PeerReadPumpOutcome {
    ReceiverClosed,
    ReadHalfClosed,
    ReadFailed(io::ErrorKind),
}

pub(super) struct PeerReadIo {
    inner: ReadMode,
    #[cfg(feature = "runtime-diagnostics")]
    diagnostics: Option<Arc<PeerReadDiagnosticCounters>>,
    #[cfg(feature = "runtime-diagnostics")]
    direct_read_pending_since: Option<Instant>,
    #[cfg(feature = "runtime-diagnostics")]
    direct_read_pending_unix_ns: Option<u64>,
}

enum ReadMode {
    OnRead {
        stream: TcpStream,
        closed: watch::Sender<bool>,
        failed: watch::Sender<Option<io::ErrorKind>>,
    },
    Proactive(BufferedReadIo),
}

struct BufferedReadIo {
    writer: OwnedWriteHalf,
    receiver: mpsc::Receiver<ReadEvent>,
    current: Bytes,
    terminal: ReadTerminal,
    #[cfg(feature = "runtime-diagnostics")]
    diagnostics: Option<Arc<PeerReadDiagnosticCounters>>,
    #[cfg(feature = "runtime-diagnostics")]
    receiver_pending_since: Option<Instant>,
}

enum ReadEvent {
    Data(Bytes),
    Eof,
    Error(io::Error),
}

enum ReadTerminal {
    Open,
    Eof,
    Failed(io::ErrorKind),
}

/// Read-path counters exist only in the diagnostic build and only when the
/// focused peer-read mode setting is present. They separate raw socket wait
/// from bounded-channel backpressure without changing the serving protocol.
pub(super) struct PeerReadDiagnosticsHandle {
    #[cfg(feature = "runtime-diagnostics")]
    inner: Option<Arc<PeerReadDiagnosticCounters>>,
}

#[cfg(feature = "runtime-diagnostics")]
struct PeerReadDiagnosticCounters {
    id: u64,
    mode: PeerReadHalfCloseMode,
    peer: Option<SocketAddr>,
    trace_read_events: bool,
    direct_read_polls: AtomicU64,
    direct_read_pending_polls: AtomicU64,
    direct_read_wait_ns: AtomicU64,
    direct_read_wait_max_ns: AtomicU64,
    direct_read_bytes: AtomicU64,
    raw_read_calls: AtomicU64,
    raw_read_bytes: AtomicU64,
    raw_read_wait_ns: AtomicU64,
    raw_read_wait_max_ns: AtomicU64,
    raw_read_waits_over_1ms: AtomicU64,
    raw_read_waits_over_100ms: AtomicU64,
    reserve_calls: AtomicU64,
    reserve_full_calls: AtomicU64,
    reserve_wait_ns: AtomicU64,
    reserve_wait_max_ns: AtomicU64,
    reserve_waits_over_1ms: AtomicU64,
    reserve_waits_over_100ms: AtomicU64,
    queue_high_water: AtomicU64,
    data_events_sent: AtomicU64,
    data_events_received: AtomicU64,
    eof_events: AtomicU64,
    read_errors: AtomicU64,
    receiver_pending_polls: AtomicU64,
    receiver_wait_ns: AtomicU64,
    receiver_wait_max_ns: AtomicU64,
    bytes_delivered_to_http: AtomicU64,
}

#[cfg(feature = "runtime-diagnostics")]
static NEXT_PEER_READ_DIAGNOSTIC_ID: AtomicU64 = AtomicU64::new(1);

#[cfg(feature = "runtime-diagnostics")]
static READ_WAIT_TRACE_EVENTS: AtomicU64 = AtomicU64::new(0);

impl PeerReadDiagnosticsHandle {
    fn new(stream: &TcpStream, mode: PeerReadHalfCloseMode) -> Self {
        #[cfg(feature = "runtime-diagnostics")]
        {
            let inner = std::env::var_os("UVICORN_RS_DIAGNOSTIC_PEER_READ_MODE").map(|_| {
                Arc::new(PeerReadDiagnosticCounters::new(
                    mode,
                    stream.peer_addr().ok(),
                    std::env::var_os("UVICORN_RS_DIAGNOSTIC_PEER_READ_TRACE")
                        .is_some_and(|value| value != "0"),
                ))
            });
            Self { inner }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        {
            let _ = (stream, mode);
            Self {}
        }
    }

    pub(super) fn report(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(counters) = &self.inner {
            counters.report();
        }
    }
}

impl Drop for PeerReadDiagnosticsHandle {
    fn drop(&mut self) {
        // Connection tasks can be cancelled during shutdown or after a peer
        // reset. A drop guard preserves the partial read-path evidence.
        self.report();
    }
}

#[cfg(feature = "runtime-diagnostics")]
impl PeerReadDiagnosticCounters {
    fn new(mode: PeerReadHalfCloseMode, peer: Option<SocketAddr>, trace_read_events: bool) -> Self {
        Self {
            id: NEXT_PEER_READ_DIAGNOSTIC_ID.fetch_add(1, Ordering::Relaxed),
            mode,
            peer,
            trace_read_events,
            direct_read_polls: AtomicU64::new(0),
            direct_read_pending_polls: AtomicU64::new(0),
            direct_read_wait_ns: AtomicU64::new(0),
            direct_read_wait_max_ns: AtomicU64::new(0),
            direct_read_bytes: AtomicU64::new(0),
            raw_read_calls: AtomicU64::new(0),
            raw_read_bytes: AtomicU64::new(0),
            raw_read_wait_ns: AtomicU64::new(0),
            raw_read_wait_max_ns: AtomicU64::new(0),
            raw_read_waits_over_1ms: AtomicU64::new(0),
            raw_read_waits_over_100ms: AtomicU64::new(0),
            reserve_calls: AtomicU64::new(0),
            reserve_full_calls: AtomicU64::new(0),
            reserve_wait_ns: AtomicU64::new(0),
            reserve_wait_max_ns: AtomicU64::new(0),
            reserve_waits_over_1ms: AtomicU64::new(0),
            reserve_waits_over_100ms: AtomicU64::new(0),
            queue_high_water: AtomicU64::new(0),
            data_events_sent: AtomicU64::new(0),
            data_events_received: AtomicU64::new(0),
            eof_events: AtomicU64::new(0),
            read_errors: AtomicU64::new(0),
            receiver_pending_polls: AtomicU64::new(0),
            receiver_wait_ns: AtomicU64::new(0),
            receiver_wait_max_ns: AtomicU64::new(0),
            bytes_delivered_to_http: AtomicU64::new(0),
        }
    }

    fn record_raw_read(&self, bytes: usize, elapsed: Duration) {
        self.raw_read_calls.fetch_add(1, Ordering::Relaxed);
        self.raw_read_bytes
            .fetch_add(bytes as u64, Ordering::Relaxed);
        let elapsed_ns = duration_ns(elapsed);
        self.raw_read_wait_ns
            .fetch_add(elapsed_ns, Ordering::Relaxed);
        self.raw_read_wait_max_ns
            .fetch_max(elapsed_ns, Ordering::Relaxed);
        if elapsed >= Duration::from_millis(1) {
            self.raw_read_waits_over_1ms.fetch_add(1, Ordering::Relaxed);
        }
        if elapsed >= Duration::from_millis(100) {
            self.raw_read_waits_over_100ms
                .fetch_add(1, Ordering::Relaxed);
        }
    }

    fn record_reserve_wait(&self, was_full: bool, elapsed: Duration) {
        self.reserve_calls.fetch_add(1, Ordering::Relaxed);
        if was_full {
            self.reserve_full_calls.fetch_add(1, Ordering::Relaxed);
        }
        let elapsed_ns = duration_ns(elapsed);
        self.reserve_wait_ns
            .fetch_add(elapsed_ns, Ordering::Relaxed);
        self.reserve_wait_max_ns
            .fetch_max(elapsed_ns, Ordering::Relaxed);
        if elapsed >= Duration::from_millis(1) {
            self.reserve_waits_over_1ms.fetch_add(1, Ordering::Relaxed);
        }
        if elapsed >= Duration::from_millis(100) {
            self.reserve_waits_over_100ms
                .fetch_add(1, Ordering::Relaxed);
        }
    }

    fn record_queue_depth(&self, sender: &mpsc::Sender<ReadEvent>) {
        let depth = sender.max_capacity().saturating_sub(sender.capacity()) as u64;
        self.queue_high_water.fetch_max(depth, Ordering::Relaxed);
    }

    fn record_receiver_wait(&self, elapsed: Duration) {
        let elapsed_ns = duration_ns(elapsed);
        self.receiver_wait_ns
            .fetch_add(elapsed_ns, Ordering::Relaxed);
        self.receiver_wait_max_ns
            .fetch_max(elapsed_ns, Ordering::Relaxed);
    }

    fn report(&self) {
        let mode = match self.mode {
            PeerReadHalfCloseMode::OnRead => "on-read",
            PeerReadHalfCloseMode::Proactive => "proactive",
        };
        let _ = io::Write::write_fmt(
            &mut io::stderr().lock(),
            format_args!(
                concat!(
                    "uvicorn-rs-peer-read-diagnostics ",
                    "id={} mode={} peer={:?} ",
                    "direct_polls={} direct_pending_polls={} direct_wait_ns={} direct_wait_max_ns={} direct_bytes={} ",
                    "raw_read_calls={} raw_read_bytes={} raw_read_wait_ns={} raw_read_wait_max_ns={} ",
                    "raw_reads_over_1ms={} raw_reads_over_100ms={} ",
                    "reserve_calls={} reserve_full_calls={} reserve_wait_ns={} reserve_wait_max_ns={} ",
                    "reserve_waits_over_1ms={} reserve_waits_over_100ms={} queue_high_water={} ",
                    "data_events_sent={} data_events_received={} eof_events={} read_errors={} ",
                    "receiver_pending_polls={} receiver_wait_ns={} receiver_wait_max_ns={} bytes_delivered_to_http={}\n"
                ),
                self.id,
                mode,
                self.peer,
                self.direct_read_polls.load(Ordering::Relaxed),
                self.direct_read_pending_polls.load(Ordering::Relaxed),
                self.direct_read_wait_ns.load(Ordering::Relaxed),
                self.direct_read_wait_max_ns.load(Ordering::Relaxed),
                self.direct_read_bytes.load(Ordering::Relaxed),
                self.raw_read_calls.load(Ordering::Relaxed),
                self.raw_read_bytes.load(Ordering::Relaxed),
                self.raw_read_wait_ns.load(Ordering::Relaxed),
                self.raw_read_wait_max_ns.load(Ordering::Relaxed),
                self.raw_read_waits_over_1ms.load(Ordering::Relaxed),
                self.raw_read_waits_over_100ms.load(Ordering::Relaxed),
                self.reserve_calls.load(Ordering::Relaxed),
                self.reserve_full_calls.load(Ordering::Relaxed),
                self.reserve_wait_ns.load(Ordering::Relaxed),
                self.reserve_wait_max_ns.load(Ordering::Relaxed),
                self.reserve_waits_over_1ms.load(Ordering::Relaxed),
                self.reserve_waits_over_100ms.load(Ordering::Relaxed),
                self.queue_high_water.load(Ordering::Relaxed),
                self.data_events_sent.load(Ordering::Relaxed),
                self.data_events_received.load(Ordering::Relaxed),
                self.eof_events.load(Ordering::Relaxed),
                self.read_errors.load(Ordering::Relaxed),
                self.receiver_pending_polls.load(Ordering::Relaxed),
                self.receiver_wait_ns.load(Ordering::Relaxed),
                self.receiver_wait_max_ns.load(Ordering::Relaxed),
                self.bytes_delivered_to_http.load(Ordering::Relaxed),
            ),
        );
    }

    /// Emits a bounded timestamp record for long waits in either TCP read path.
    fn trace_read_wait(
        &self,
        pending_unix_ns: u64,
        ready_unix_ns: u64,
        wait_ns: u64,
        bytes: usize,
        outcome: &str,
    ) {
        if !self.trace_read_events
            || wait_ns < duration_ns(READ_WAIT_TRACE_THRESHOLD)
            || READ_WAIT_TRACE_EVENTS.fetch_add(1, Ordering::Relaxed) >= READ_WAIT_TRACE_LIMIT
        {
            return;
        }

        let peer_port = self.peer.map_or(0, |peer| peer.port());
        let _ = io::Write::write_fmt(
            &mut io::stderr().lock(),
            format_args!(
                concat!(
                    "uvicorn-rs-read-wait-event ",
                    "connection_id={} mode={} peer_port={} pending_unix_ns={} ",
                    "ready_unix_ns={} wait_ns={} bytes={} outcome={}\n"
                ),
                self.id,
                match self.mode {
                    PeerReadHalfCloseMode::OnRead => "on-read",
                    PeerReadHalfCloseMode::Proactive => "proactive",
                },
                peer_port,
                pending_unix_ns,
                ready_unix_ns,
                wait_ns,
                bytes,
                outcome,
            ),
        );
    }

    fn read_wait_trace_started_at(&self) -> Option<u64> {
        self.trace_read_events.then(unix_timestamp_ns)
    }
}

#[cfg(feature = "runtime-diagnostics")]
fn duration_ns(duration: Duration) -> u64 {
    duration.as_nanos().min(u64::MAX as u128) as u64
}

#[cfg(feature = "runtime-diagnostics")]
fn unix_timestamp_ns() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
        .min(u64::MAX as u128) as u64
}

/// Creates one socket reader. The optional pump must be driven alongside the
/// entire connection, including TLS acceptance and registered upgrade sessions.
pub(super) fn observe_peer_read(
    stream: TcpStream,
    mode: PeerReadHalfCloseMode,
) -> (
    PeerReadIo,
    PeerReadHalfClosed,
    super::PeerReadFailed,
    Option<impl Future<Output = PeerReadPumpOutcome> + Send>,
    bool,
    PeerReadDiagnosticsHandle,
) {
    let diagnostics = PeerReadDiagnosticsHandle::new(&stream, mode);
    #[cfg(feature = "runtime-diagnostics")]
    let diagnostic_counters = diagnostics.inner.clone();
    let (closed, receiver) = watch::channel(false);
    let (failed, failed_receiver) = watch::channel(None);
    let observer = PeerReadHalfClosed {
        closed: receiver,
        mode,
    };
    let failed_observer = super::PeerReadFailed {
        failed: failed_receiver,
    };
    let (inner, pump, prioritize_receiver_close_fault) = match mode {
        PeerReadHalfCloseMode::OnRead => (
            ReadMode::OnRead {
                stream,
                closed,
                failed,
            },
            None,
            false,
        ),
        PeerReadHalfCloseMode::Proactive => {
            let (reader, writer) = stream.into_split();
            let (sender, receiver) = mpsc::channel(READ_QUEUE_CAPACITY);
            #[cfg(coverage)]
            let (receiver, prioritize_receiver_close_fault) = {
                let mut receiver = receiver;
                if super::take_http1_peer_read_receiver_closed_fault() {
                    receiver.close();
                    (receiver, true)
                } else {
                    (receiver, false)
                }
            };
            #[cfg(not(coverage))]
            let (receiver, prioritize_receiver_close_fault) = (receiver, false);
            (
                ReadMode::Proactive(BufferedReadIo {
                    writer,
                    receiver,
                    current: Bytes::new(),
                    terminal: ReadTerminal::Open,
                    #[cfg(feature = "runtime-diagnostics")]
                    diagnostics: diagnostic_counters.clone(),
                    #[cfg(feature = "runtime-diagnostics")]
                    receiver_pending_since: None,
                }),
                Some(pump_peer_read(
                    reader,
                    sender,
                    closed,
                    failed,
                    #[cfg(feature = "runtime-diagnostics")]
                    diagnostic_counters.clone(),
                )),
                prioritize_receiver_close_fault,
            )
        }
    };
    (
        PeerReadIo {
            inner,
            #[cfg(feature = "runtime-diagnostics")]
            diagnostics: diagnostic_counters,
            #[cfg(feature = "runtime-diagnostics")]
            direct_read_pending_since: None,
            #[cfg(feature = "runtime-diagnostics")]
            direct_read_pending_unix_ns: None,
        },
        observer,
        failed_observer,
        pump,
        prioritize_receiver_close_fault,
        diagnostics,
    )
}

async fn pump_peer_read(
    mut reader: OwnedReadHalf,
    sender: mpsc::Sender<ReadEvent>,
    closed: watch::Sender<bool>,
    failed: watch::Sender<Option<io::ErrorKind>>,
    #[cfg(feature = "runtime-diagnostics")] diagnostics: Option<Arc<PeerReadDiagnosticCounters>>,
) -> PeerReadPumpOutcome {
    #[cfg(coverage)]
    let mut delivered_data = false;
    loop {
        // Reserve before reading so pressure from HTTP/TLS also bounds socket
        // read-ahead. The consumer may hold one additional, partly read chunk.
        #[cfg(feature = "runtime-diagnostics")]
        let reserve_was_full = sender.capacity() == 0;
        #[cfg(feature = "runtime-diagnostics")]
        let reserve_started = diagnostics.as_ref().map(|_| Instant::now());
        let reservation = sender.reserve().await;
        #[cfg(feature = "runtime-diagnostics")]
        if let (Some(diagnostics), Some(started)) = (diagnostics.as_ref(), reserve_started) {
            diagnostics.record_reserve_wait(reserve_was_full, started.elapsed());
        }
        let Ok(permit) = reservation else {
            #[cfg(coverage)]
            super::observe_http1_peer_read_receiver_closed_fault();
            return PeerReadPumpOutcome::ReceiverClosed;
        };
        #[cfg(coverage)]
        if delivered_data && super::take_http1_peer_read_failure_after_data_fault() {
            let error = io::Error::new(
                io::ErrorKind::ConnectionReset,
                "injected peer-read failure after request data",
            );
            let kind = error.kind();
            failed.send_replace(Some(kind));
            permit.send(ReadEvent::Error(error));
            super::observe_http1_peer_read_failure_after_data_fault();
            return PeerReadPumpOutcome::ReadFailed(kind);
        }
        let mut chunk = BytesMut::with_capacity(READ_CHUNK_SIZE);
        #[cfg(feature = "runtime-diagnostics")]
        let read_started = diagnostics.as_ref().map(|_| Instant::now());
        #[cfg(feature = "runtime-diagnostics")]
        let read_pending_unix_ns = diagnostics
            .as_ref()
            .and_then(|counters| counters.read_wait_trace_started_at());
        let read_result = {
            let mut destination = (&mut chunk).limit(READ_CHUNK_SIZE);
            reader.read_buf(&mut destination).await
        };
        #[cfg(feature = "runtime-diagnostics")]
        if let (Some(diagnostics), Some(started)) = (diagnostics.as_ref(), read_started) {
            let elapsed = started.elapsed();
            diagnostics.record_raw_read(chunk.len(), elapsed);
            if let Some(pending_unix_ns) = read_pending_unix_ns {
                let outcome = match &read_result {
                    Ok(0) => "eof",
                    Ok(_) => "ready",
                    Err(_) => "error",
                };
                diagnostics.trace_read_wait(
                    pending_unix_ns,
                    unix_timestamp_ns(),
                    duration_ns(elapsed),
                    chunk.len(),
                    outcome,
                );
            }
        }
        match read_result {
            Ok(0) => {
                // Only this nonempty raw socket read establishes peer EOF.
                // Queue it after all data; observing it never closes writes.
                closed.send_replace(true);
                permit.send(ReadEvent::Eof);
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(diagnostics) = diagnostics.as_ref() {
                    diagnostics.eof_events.fetch_add(1, Ordering::Relaxed);
                    diagnostics.record_queue_depth(&sender);
                }
                return PeerReadPumpOutcome::ReadHalfClosed;
            }
            Ok(_) => {
                #[cfg(coverage)]
                {
                    delivered_data = true;
                }
                permit.send(ReadEvent::Data(chunk.freeze()));
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(diagnostics) = diagnostics.as_ref() {
                    diagnostics.data_events_sent.fetch_add(1, Ordering::Relaxed);
                    diagnostics.record_queue_depth(&sender);
                }
            }
            Err(error) => {
                let kind = error.kind();
                failed.send_replace(Some(kind));
                permit.send(ReadEvent::Error(error));
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(diagnostics) = diagnostics.as_ref() {
                    diagnostics.read_errors.fetch_add(1, Ordering::Relaxed);
                    diagnostics.record_queue_depth(&sender);
                }
                return PeerReadPumpOutcome::ReadFailed(kind);
            }
        }
    }
}

impl BufferedReadIo {
    fn poll_read(
        &mut self,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        loop {
            if !self.current.is_empty() {
                let count = buffer.remaining().min(self.current.len());
                buffer.put_slice(&self.current[..count]);
                self.current.advance(count);
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(diagnostics) = self.diagnostics.as_ref() {
                    diagnostics
                        .bytes_delivered_to_http
                        .fetch_add(count as u64, Ordering::Relaxed);
                }
                return Poll::Ready(Ok(()));
            }
            match self.terminal {
                ReadTerminal::Eof => return Poll::Ready(Ok(())),
                ReadTerminal::Failed(kind) => {
                    return Poll::Ready(Err(io::Error::new(
                        kind,
                        "raw TCP reader previously failed",
                    )));
                }
                ReadTerminal::Open => {}
            }
            let event = match self.receiver.poll_recv(context) {
                Poll::Pending => {
                    #[cfg(feature = "runtime-diagnostics")]
                    if let Some(diagnostics) = self.diagnostics.as_ref() {
                        diagnostics
                            .receiver_pending_polls
                            .fetch_add(1, Ordering::Relaxed);
                        if self.receiver_pending_since.is_none() {
                            self.receiver_pending_since = Some(Instant::now());
                        }
                    }
                    return Poll::Pending;
                }
                Poll::Ready(event) => {
                    #[cfg(feature = "runtime-diagnostics")]
                    if let (Some(diagnostics), Some(started)) = (
                        self.diagnostics.as_ref(),
                        self.receiver_pending_since.take(),
                    ) {
                        diagnostics.record_receiver_wait(started.elapsed());
                    }
                    event
                }
            };
            match event {
                Some(ReadEvent::Data(chunk)) => {
                    #[cfg(feature = "runtime-diagnostics")]
                    if let Some(diagnostics) = self.diagnostics.as_ref() {
                        diagnostics
                            .data_events_received
                            .fetch_add(1, Ordering::Relaxed);
                    }
                    self.current = chunk;
                }
                Some(ReadEvent::Eof) => self.terminal = ReadTerminal::Eof,
                Some(ReadEvent::Error(error)) => {
                    self.terminal = ReadTerminal::Failed(error.kind());
                    return Poll::Ready(Err(error));
                }
                None => {
                    // A dropped producer does not establish peer EOF. Preserve
                    // that distinction even if its owner ends unexpectedly.
                    self.terminal = ReadTerminal::Failed(io::ErrorKind::ConnectionAborted);
                    return Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::ConnectionAborted,
                        "raw TCP reader ended without an EOF or error",
                    )));
                }
            }
        }
    }
}

impl AsyncRead for PeerReadIo {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if buffer.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        let this = self.get_mut();
        match &mut this.inner {
            ReadMode::OnRead {
                stream,
                closed,
                failed,
            } => {
                let filled_before = buffer.filled().len();
                let result = Pin::new(stream).poll_read(context, buffer);
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(diagnostics) = this.diagnostics.as_ref() {
                    diagnostics
                        .direct_read_polls
                        .fetch_add(1, Ordering::Relaxed);
                    match &result {
                        Poll::Pending => {
                            diagnostics
                                .direct_read_pending_polls
                                .fetch_add(1, Ordering::Relaxed);
                            if this.direct_read_pending_since.is_none() {
                                this.direct_read_pending_since = Some(Instant::now());
                                this.direct_read_pending_unix_ns =
                                    diagnostics.trace_read_events.then(unix_timestamp_ns);
                            }
                        }
                        Poll::Ready(Ok(())) => {
                            let bytes = buffer.filled().len().saturating_sub(filled_before);
                            diagnostics
                                .direct_read_bytes
                                .fetch_add(bytes as u64, Ordering::Relaxed);
                            if let Some(started) = this.direct_read_pending_since.take() {
                                let wait_ns = duration_ns(started.elapsed());
                                diagnostics
                                    .direct_read_wait_ns
                                    .fetch_add(wait_ns, Ordering::Relaxed);
                                diagnostics
                                    .direct_read_wait_max_ns
                                    .fetch_max(wait_ns, Ordering::Relaxed);
                                if let Some(pending_unix_ns) =
                                    this.direct_read_pending_unix_ns.take()
                                {
                                    diagnostics.trace_read_wait(
                                        pending_unix_ns,
                                        unix_timestamp_ns(),
                                        wait_ns,
                                        buffer.filled().len().saturating_sub(filled_before),
                                        "ready",
                                    );
                                }
                            }
                        }
                        Poll::Ready(Err(_)) => {
                            if let Some(started) = this.direct_read_pending_since.take() {
                                let wait_ns = duration_ns(started.elapsed());
                                diagnostics
                                    .direct_read_wait_ns
                                    .fetch_add(wait_ns, Ordering::Relaxed);
                                diagnostics
                                    .direct_read_wait_max_ns
                                    .fetch_max(wait_ns, Ordering::Relaxed);
                                if let Some(pending_unix_ns) =
                                    this.direct_read_pending_unix_ns.take()
                                {
                                    diagnostics.trace_read_wait(
                                        pending_unix_ns,
                                        unix_timestamp_ns(),
                                        wait_ns,
                                        0,
                                        "error",
                                    );
                                }
                            }
                        }
                    }
                }
                if matches!(&result, Poll::Ready(Ok(())))
                    && buffer.remaining() > 0
                    && buffer.filled().len() == filled_before
                {
                    closed.send_replace(true);
                }
                if let Poll::Ready(Err(error)) = &result {
                    failed.send_replace(Some(error.kind()));
                }
                result
            }
            ReadMode::Proactive(stream) => stream.poll_read(context, buffer),
        }
    }
}

impl AsyncWrite for PeerReadIo {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        match &mut self.get_mut().inner {
            ReadMode::OnRead { stream, .. } => Pin::new(stream).poll_write(context, buffer),
            ReadMode::Proactive(stream) => Pin::new(&mut stream.writer).poll_write(context, buffer),
        }
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffers: &[io::IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        match &mut self.get_mut().inner {
            ReadMode::OnRead { stream, .. } => {
                Pin::new(stream).poll_write_vectored(context, buffers)
            }
            ReadMode::Proactive(stream) => {
                Pin::new(&mut stream.writer).poll_write_vectored(context, buffers)
            }
        }
    }

    fn is_write_vectored(&self) -> bool {
        match &self.inner {
            ReadMode::OnRead { stream, .. } => stream.is_write_vectored(),
            ReadMode::Proactive(stream) => stream.writer.is_write_vectored(),
        }
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        match &mut self.get_mut().inner {
            ReadMode::OnRead { stream, .. } => Pin::new(stream).poll_flush(context),
            ReadMode::Proactive(stream) => Pin::new(&mut stream.writer).poll_flush(context),
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        match &mut self.get_mut().inner {
            ReadMode::OnRead { stream, .. } => Pin::new(stream).poll_shutdown(context),
            ReadMode::Proactive(stream) => Pin::new(&mut stream.writer).poll_shutdown(context),
        }
    }
}
