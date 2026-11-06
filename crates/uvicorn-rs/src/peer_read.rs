#[cfg(feature = "runtime-diagnostics")]
use std::{
    collections::VecDeque,
    fmt::Write as FmtWrite,
    io::Write as IoWrite,
    net::SocketAddr,
    sync::atomic::{AtomicU64, Ordering},
    time::{Instant, SystemTime, UNIX_EPOCH},
};
use std::{
    future::Future,
    io,
    pin::Pin,
    task::{Context, Poll},
};

use bytes::{BufMut, BytesMut};
#[cfg(unix)]
use tokio::net::{
    UnixStream, unix::OwnedReadHalf as UnixOwnedReadHalf,
    unix::OwnedWriteHalf as UnixOwnedWriteHalf,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    net::{TcpStream, tcp::OwnedWriteHalf},
    sync::{mpsc, watch},
};

use super::{PeerReadHalfCloseMode, PeerReadHalfClosed};

const READ_CHUNK_SIZE: usize = 64 * 1024;
const READ_QUEUE_CAPACITY: usize = 2;

fn peer_read_chunk_size() -> usize {
    #[cfg(feature = "runtime-diagnostics")]
    if let Some(size) = std::env::var_os("UVICORN_RS_DIAGNOSTIC_PEER_READ_CHUNK_SIZE") {
        match size.to_str() {
            Some("16k") => return 16 * 1024,
            Some("32k") => return 32 * 1024,
            Some("64k") => return 64 * 1024,
            _ => {}
        }
    }

    READ_CHUNK_SIZE
}

pub(super) enum PeerReadPumpOutcome {
    ReceiverClosed,
    ReadHalfClosed,
    ReadFailed(io::ErrorKind),
}

pub(super) struct PeerReadIo {
    inner: ReadMode,
}

enum ReadMode {
    OnRead {
        stream: TcpStream,
        closed: watch::Sender<bool>,
        failed: watch::Sender<Option<io::ErrorKind>>,
    },
    Proactive(BufferedReadIo<OwnedWriteHalf>),
}

struct BufferedReadIo<W> {
    writer: W,
    receiver: mpsc::Receiver<ReadEvent>,
    current: Option<(BytesMut, usize)>,
    terminal: ReadTerminal,
}

#[cfg(unix)]
pub(super) struct UnixPeerReadIo {
    inner: UnixReadMode,
}

#[cfg(unix)]
enum UnixReadMode {
    OnRead {
        stream: UnixStream,
        closed: watch::Sender<bool>,
        failed: watch::Sender<Option<io::ErrorKind>>,
    },
    Proactive(BufferedReadIo<UnixOwnedWriteHalf>),
}

enum ReadEvent {
    Data(BytesMut),
    Eof,
    Error(io::Error),
}

enum ReadTerminal {
    Open,
    Eof,
    Failed(io::ErrorKind),
}

#[cfg(feature = "runtime-diagnostics")]
type PeerReadTraceOption = Option<PeerReadTrace>;
#[cfg(not(feature = "runtime-diagnostics"))]
type PeerReadTraceOption = ();

#[cfg(feature = "runtime-diagnostics")]
const RETAINED_PEER_READ_EVENTS: usize = 64;

#[cfg(feature = "runtime-diagnostics")]
static NEXT_PEER_READ_TRACE_ID: AtomicU64 = AtomicU64::new(1);

#[cfg(feature = "runtime-diagnostics")]
struct PeerReadEvent {
    offset_ns: u64,
    kind: &'static str,
    bytes: u64,
    duration_ns: u64,
}

/// Bounded observations inside the proactive reader, below its bounded queue.
#[cfg(feature = "runtime-diagnostics")]
struct PeerReadTrace {
    id: u64,
    peer_addr: SocketAddr,
    started: Instant,
    origin_unix_ns: u128,
    origin_uncertainty_ns: u128,
    socket_read_bytes: u64,
    socket_read_calls: u64,
    socket_read_eof: u64,
    socket_read_errors: u64,
    max_socket_read_wait_ns: u64,
    queue_reserve_full_observations: u64,
    max_queue_reserve_wait_ns: u64,
    queue_reserve_pending_since: Option<Instant>,
    socket_read_pending_since: Option<Instant>,
    events_seen: u64,
    events: VecDeque<PeerReadEvent>,
}

#[cfg(feature = "runtime-diagnostics")]
impl PeerReadTrace {
    fn new(peer_addr: SocketAddr) -> Self {
        let started = Instant::now();
        let origin_unix_ns = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let origin_uncertainty_ns = started.elapsed().as_nanos();
        Self {
            id: NEXT_PEER_READ_TRACE_ID.fetch_add(1, Ordering::Relaxed),
            peer_addr,
            started,
            origin_unix_ns,
            origin_uncertainty_ns,
            socket_read_bytes: 0,
            socket_read_calls: 0,
            socket_read_eof: 0,
            socket_read_errors: 0,
            max_socket_read_wait_ns: 0,
            queue_reserve_full_observations: 0,
            max_queue_reserve_wait_ns: 0,
            queue_reserve_pending_since: None,
            socket_read_pending_since: None,
            events_seen: 0,
            events: VecDeque::with_capacity(RETAINED_PEER_READ_EVENTS),
        }
    }

    fn socket_read_started(&mut self) {
        self.socket_read_pending_since = Some(Instant::now());
        self.record("socket-read-start", 0, 0);
    }

    fn socket_read(&mut self, kind: &'static str, bytes: u64, duration_ns: u64) {
        self.socket_read_pending_since = None;
        match kind {
            "data" => {
                self.socket_read_calls += 1;
                self.socket_read_bytes += bytes;
            }
            "eof" => self.socket_read_eof += 1,
            "error" => self.socket_read_errors += 1,
            _ => {}
        }
        self.max_socket_read_wait_ns = self.max_socket_read_wait_ns.max(duration_ns);
        self.record(kind, bytes, duration_ns);
    }

    fn queue_reserve_started(&mut self, was_full: bool) {
        self.queue_reserve_pending_since = Some(Instant::now());
        self.record(
            if was_full {
                "queue-reserve-start-full"
            } else {
                "queue-reserve-start-ready"
            },
            0,
            0,
        );
    }

    fn queue_reserve(&mut self, duration_ns: u64, was_full: bool) {
        self.queue_reserve_pending_since = None;
        if was_full {
            self.queue_reserve_full_observations += 1;
        }
        self.max_queue_reserve_wait_ns = self.max_queue_reserve_wait_ns.max(duration_ns);
        self.record(
            if was_full {
                "queue-reserve-full"
            } else {
                "queue-reserve-ready"
            },
            0,
            duration_ns,
        );
    }

    fn record(&mut self, kind: &'static str, bytes: u64, duration_ns: u64) {
        self.events_seen += 1;
        if self.events.len() == RETAINED_PEER_READ_EVENTS {
            self.events.pop_front();
        }
        self.events.push_back(PeerReadEvent {
            offset_ns: self.started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
            kind,
            bytes,
            duration_ns,
        });
    }
}

#[cfg(feature = "runtime-diagnostics")]
impl Drop for PeerReadTrace {
    fn drop(&mut self) {
        let mut output = String::new();
        let _ = writeln!(
            output,
            "uvicorn-rs-peer-read-trace schema=1 pid={} connection={} peer={} peer_port={} origin_unix_ns={} origin_uncertainty_ns={} elapsed_ns={} socket_read_bytes={} socket_read_calls={} socket_read_eof={} socket_read_errors={} max_socket_read_wait_ns={} socket_read_pending_ns={} queue_reserve_full_observations={} max_queue_reserve_wait_ns={} queue_reserve_pending_ns={} events_seen={} events_retained={} events_dropped={}",
            std::process::id(),
            self.id,
            self.peer_addr,
            self.peer_addr.port(),
            self.origin_unix_ns,
            self.origin_uncertainty_ns,
            self.started.elapsed().as_nanos(),
            self.socket_read_bytes,
            self.socket_read_calls,
            self.socket_read_eof,
            self.socket_read_errors,
            self.max_socket_read_wait_ns,
            self.socket_read_pending_since.map_or(0, duration_ns_since),
            self.queue_reserve_full_observations,
            self.max_queue_reserve_wait_ns,
            self.queue_reserve_pending_since
                .map_or(0, duration_ns_since),
            self.events_seen,
            self.events.len(),
            self.events_seen
                .saturating_sub(RETAINED_PEER_READ_EVENTS as u64),
        );
        for event in &self.events {
            let _ = writeln!(
                output,
                "uvicorn-rs-peer-read-event schema=1 pid={} connection={} peer_port={} offset_ns={} event={} bytes={} duration_ns={}",
                std::process::id(),
                self.id,
                self.peer_addr.port(),
                event.offset_ns,
                event.kind,
                event.bytes,
                event.duration_ns,
            );
        }
        let _ = io::stderr().lock().write_all(output.as_bytes());
    }
}

#[cfg(feature = "runtime-diagnostics")]
fn duration_ns_since(started: Instant) -> u64 {
    started.elapsed().as_nanos().min(u64::MAX as u128) as u64
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
) {
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
            #[cfg(feature = "runtime-diagnostics")]
            let trace = if std::env::var_os("UVICORN_RS_UPLOAD_TRACE").as_deref()
                == Some(std::ffi::OsStr::new("1"))
            {
                stream.peer_addr().ok().map(PeerReadTrace::new)
            } else {
                None
            };
            #[cfg(not(feature = "runtime-diagnostics"))]
            let trace = ();
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
                    current: None,
                    terminal: ReadTerminal::Open,
                }),
                Some(pump_peer_read(reader, sender, closed, failed, trace)),
                prioritize_receiver_close_fault,
            )
        }
    };
    (
        PeerReadIo { inner },
        observer,
        failed_observer,
        pump,
        prioritize_receiver_close_fault,
    )
}

async fn pump_peer_read<R>(
    mut reader: R,
    sender: mpsc::Sender<ReadEvent>,
    closed: watch::Sender<bool>,
    failed: watch::Sender<Option<io::ErrorKind>>,
    _trace: PeerReadTraceOption,
) -> PeerReadPumpOutcome
where
    R: AsyncRead + Unpin,
{
    let read_chunk_size = peer_read_chunk_size();
    #[cfg(feature = "runtime-diagnostics")]
    let mut trace = _trace;
    #[cfg(coverage)]
    let mut delivered_data = false;
    loop {
        // Reserve before reading so pressure from HTTP/TLS also bounds socket
        // read-ahead. The consumer may hold one additional, partly read chunk.
        #[cfg(feature = "runtime-diagnostics")]
        let queue_was_full = sender.capacity() == 0;
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(trace) = trace.as_mut() {
            trace.queue_reserve_started(queue_was_full);
        }
        #[cfg(feature = "runtime-diagnostics")]
        let reserve_started = trace.as_ref().map(|_| Instant::now());
        let reserve_result = sender.reserve().await;
        #[cfg(feature = "runtime-diagnostics")]
        let reserve_wait_ns = reserve_started
            .map(|started| started.elapsed().as_nanos().min(u64::MAX as u128) as u64)
            .unwrap_or(0);
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(trace) = trace.as_mut() {
            trace.queue_reserve(reserve_wait_ns, queue_was_full);
        }
        let Ok(permit) = reserve_result else {
            #[cfg(feature = "runtime-diagnostics")]
            if let Some(trace) = trace.as_mut() {
                trace.record("queue-reserve-closed", 0, reserve_wait_ns);
            }
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
        let mut chunk = BytesMut::with_capacity(read_chunk_size);
        let mut destination = (&mut chunk).limit(read_chunk_size);
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(trace) = trace.as_mut() {
            trace.socket_read_started();
        }
        #[cfg(feature = "runtime-diagnostics")]
        let read_started = trace.as_ref().map(|_| Instant::now());
        let read_result = reader.read_buf(&mut destination).await;
        #[cfg(feature = "runtime-diagnostics")]
        let read_wait_ns = read_started
            .map(|started| started.elapsed().as_nanos().min(u64::MAX as u128) as u64)
            .unwrap_or(0);
        match read_result {
            Ok(0) => {
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(trace) = trace.as_mut() {
                    trace.socket_read("eof", 0, read_wait_ns);
                }
                // Only this nonempty raw socket read establishes peer EOF.
                // Queue it after all data; observing it never closes writes.
                closed.send_replace(true);
                permit.send(ReadEvent::Eof);
                return PeerReadPumpOutcome::ReadHalfClosed;
            }
            Ok(_) => {
                #[cfg(feature = "runtime-diagnostics")]
                let read_bytes = chunk.len() as u64;
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(trace) = trace.as_mut() {
                    trace.socket_read("data", read_bytes, read_wait_ns);
                }
                #[cfg(coverage)]
                {
                    delivered_data = true;
                }
                permit.send(ReadEvent::Data(chunk));
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(trace) = trace.as_mut() {
                    trace.record("queue-enqueued", read_bytes, 0);
                }
            }
            Err(error) => {
                #[cfg(feature = "runtime-diagnostics")]
                if let Some(trace) = trace.as_mut() {
                    trace.socket_read("error", 0, read_wait_ns);
                }
                let kind = error.kind();
                failed.send_replace(Some(kind));
                permit.send(ReadEvent::Error(error));
                return PeerReadPumpOutcome::ReadFailed(kind);
            }
        }
    }
}

#[cfg(unix)]
pub(super) fn observe_peer_read_unix(
    stream: UnixStream,
    mode: PeerReadHalfCloseMode,
) -> (
    UnixPeerReadIo,
    PeerReadHalfClosed,
    super::PeerReadFailed,
    Option<impl Future<Output = PeerReadPumpOutcome> + Send>,
    bool,
) {
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
            UnixReadMode::OnRead {
                stream,
                closed,
                failed,
            },
            None,
            false,
        ),
        PeerReadHalfCloseMode::Proactive => {
            let (reader, writer): (UnixOwnedReadHalf, UnixOwnedWriteHalf) = stream.into_split();
            #[cfg(feature = "runtime-diagnostics")]
            let trace: PeerReadTraceOption = None;
            #[cfg(not(feature = "runtime-diagnostics"))]
            let trace: PeerReadTraceOption = ();
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
                UnixReadMode::Proactive(BufferedReadIo {
                    writer,
                    receiver,
                    current: None,
                    terminal: ReadTerminal::Open,
                }),
                Some(pump_peer_read(reader, sender, closed, failed, trace)),
                prioritize_receiver_close_fault,
            )
        }
    };
    (
        UnixPeerReadIo { inner },
        observer,
        failed_observer,
        pump,
        prioritize_receiver_close_fault,
    )
}

impl<W: AsyncWrite + Unpin> BufferedReadIo<W> {
    fn poll_read(
        &mut self,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        loop {
            if let Some((current, offset)) = self.current.take() {
                let count = buffer.remaining().min(current.len() - offset);
                buffer.put_slice(&current[offset..offset + count]);
                let next_offset = offset + count;
                if next_offset != current.len() {
                    self.current = Some((current, next_offset));
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
            match self.receiver.poll_recv(context) {
                Poll::Pending => return Poll::Pending,
                Poll::Ready(Some(ReadEvent::Data(chunk))) => self.current = Some((chunk, 0)),
                Poll::Ready(Some(ReadEvent::Eof)) => self.terminal = ReadTerminal::Eof,
                Poll::Ready(Some(ReadEvent::Error(error))) => {
                    self.terminal = ReadTerminal::Failed(error.kind());
                    return Poll::Ready(Err(error));
                }
                Poll::Ready(None) => {
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

#[cfg(unix)]
impl AsyncRead for UnixPeerReadIo {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if buffer.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        match &mut self.get_mut().inner {
            UnixReadMode::OnRead {
                stream,
                closed,
                failed,
            } => {
                let filled_before = buffer.filled().len();
                #[cfg(coverage)]
                let result = if super::coverage::take_http1_unix_peer_read_on_read_error_fault() {
                    super::coverage::observe_http1_unix_peer_read_on_read_error_fault();
                    Poll::Ready(Err(io::Error::new(
                        io::ErrorKind::ConnectionReset,
                        "injected Unix peer-read failure",
                    )))
                } else {
                    Pin::new(stream).poll_read(context, buffer)
                };
                #[cfg(not(coverage))]
                let result = Pin::new(stream).poll_read(context, buffer);
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
            UnixReadMode::Proactive(stream) => stream.poll_read(context, buffer),
        }
    }
}

#[cfg(unix)]
impl AsyncWrite for UnixPeerReadIo {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        match &mut self.get_mut().inner {
            UnixReadMode::OnRead { stream, .. } => Pin::new(stream).poll_write(context, buffer),
            UnixReadMode::Proactive(stream) => {
                Pin::new(&mut stream.writer).poll_write(context, buffer)
            }
        }
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffers: &[io::IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        match &mut self.get_mut().inner {
            UnixReadMode::OnRead { stream, .. } => {
                Pin::new(stream).poll_write_vectored(context, buffers)
            }
            UnixReadMode::Proactive(stream) => {
                Pin::new(&mut stream.writer).poll_write_vectored(context, buffers)
            }
        }
    }

    fn is_write_vectored(&self) -> bool {
        match &self.inner {
            UnixReadMode::OnRead { stream, .. } => stream.is_write_vectored(),
            UnixReadMode::Proactive(stream) => stream.writer.is_write_vectored(),
        }
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        match &mut self.get_mut().inner {
            UnixReadMode::OnRead { stream, .. } => Pin::new(stream).poll_flush(context),
            UnixReadMode::Proactive(stream) => Pin::new(&mut stream.writer).poll_flush(context),
        }
    }

    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        match &mut self.get_mut().inner {
            UnixReadMode::OnRead { stream, .. } => Pin::new(stream).poll_shutdown(context),
            UnixReadMode::Proactive(stream) => Pin::new(&mut stream.writer).poll_shutdown(context),
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
        match &mut self.get_mut().inner {
            ReadMode::OnRead {
                stream,
                closed,
                failed,
            } => {
                let filled_before = buffer.filled().len();
                let result = Pin::new(stream).poll_read(context, buffer);
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

#[cfg(test)]
mod tests {
    use std::{collections::VecDeque, sync::Arc};

    use super::*;

    struct ChunkReader {
        chunks: VecDeque<&'static [u8]>,
        reads: usize,
        second_chunk_read: Arc<tokio::sync::Notify>,
    }

    impl AsyncRead for ChunkReader {
        fn poll_read(
            self: Pin<&mut Self>,
            _context: &mut Context<'_>,
            buffer: &mut ReadBuf<'_>,
        ) -> Poll<io::Result<()>> {
            let this = self.get_mut();
            let Some(chunk) = this.chunks.pop_front() else {
                return Poll::Ready(Ok(()));
            };
            let count = buffer.remaining().min(chunk.len());
            buffer.put_slice(&chunk[..count]);
            this.reads += 1;
            if this.reads == 2 {
                this.second_chunk_read.notify_one();
            }
            Poll::Ready(Ok(()))
        }
    }

    struct BufferedReadAdapter<W>(BufferedReadIo<W>);

    impl<W: AsyncWrite + Unpin> AsyncRead for BufferedReadAdapter<W> {
        fn poll_read(
            self: Pin<&mut Self>,
            context: &mut Context<'_>,
            buffer: &mut ReadBuf<'_>,
        ) -> Poll<io::Result<()>> {
            self.get_mut().0.poll_read(context, buffer)
        }
    }

    #[tokio::test]
    async fn pump_preserves_partial_chunk_while_reading_ahead() {
        // A one-slot queue pauses the pump until the consumer dequeues each
        // event, letting the test hold one buffer partially consumed while
        // the pump performs the following read.
        let (sender, receiver) = mpsc::channel(1);
        let (closed, _) = watch::channel(false);
        let (failed, _) = watch::channel(None);
        let second_chunk_read = Arc::new(tokio::sync::Notify::new());
        #[cfg(feature = "runtime-diagnostics")]
        let trace: PeerReadTraceOption = None;
        #[cfg(not(feature = "runtime-diagnostics"))]
        let trace: PeerReadTraceOption = ();
        let pump = tokio::spawn(pump_peer_read(
            ChunkReader {
                chunks: VecDeque::from([&b"first"[..], &b"second"[..], &b"third"[..]]),
                reads: 0,
                second_chunk_read: Arc::clone(&second_chunk_read),
            },
            sender,
            closed,
            failed,
            trace,
        ));
        let mut reader = BufferedReadAdapter(BufferedReadIo {
            writer: tokio::io::sink(),
            receiver,
            current: None,
            terminal: ReadTerminal::Open,
        });

        let mut first_prefix = [0; 2];
        assert!(reader.read_exact(&mut first_prefix).await.is_ok());
        assert_eq!(&first_prefix, b"fi");
        second_chunk_read.notified().await;
        let mut first_suffix = [0; 3];
        assert!(reader.read_exact(&mut first_suffix).await.is_ok());
        assert_eq!(&first_suffix, b"rst");
        let mut second = [0; 6];
        assert!(reader.read_exact(&mut second).await.is_ok());
        assert_eq!(&second, b"second");
        let mut third = [0; 5];
        assert!(reader.read_exact(&mut third).await.is_ok());
        assert_eq!(&third, b"third");
        assert!(matches!(
            pump.await,
            Ok(PeerReadPumpOutcome::ReadHalfClosed)
        ));

        let mut after_eof = [0; 1];
        assert_eq!(reader.read(&mut after_eof).await.ok(), Some(0));
    }
}
