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
    recycled: mpsc::Sender<BytesMut>,
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
            let (reader, writer) = stream.into_split();
            let (sender, receiver) = mpsc::channel(READ_QUEUE_CAPACITY);
            let (recycled, recycled_receiver) = mpsc::channel(READ_QUEUE_CAPACITY + 1);
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
                    recycled,
                    current: None,
                    terminal: ReadTerminal::Open,
                }),
                Some(pump_peer_read(
                    reader,
                    sender,
                    recycled_receiver,
                    closed,
                    failed,
                )),
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
    mut recycled: mpsc::Receiver<BytesMut>,
    closed: watch::Sender<bool>,
    failed: watch::Sender<Option<io::ErrorKind>>,
) -> PeerReadPumpOutcome
where
    R: AsyncRead + Unpin,
{
    #[cfg(coverage)]
    let mut delivered_data = false;
    loop {
        // Reserve before reading so pressure from HTTP/TLS also bounds socket
        // read-ahead. The consumer may hold one additional, partly read chunk.
        let Ok(permit) = sender.reserve().await else {
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
        // Reserving before each read bounds queued plus in-flight chunks to
        // READ_QUEUE_CAPACITY; the connection reader may hold one more partial
        // chunk. Recycling therefore stays within those three allocations.
        let mut chunk = recycled
            .try_recv()
            .unwrap_or_else(|_| BytesMut::with_capacity(READ_CHUNK_SIZE));
        chunk.clear();
        let mut destination = (&mut chunk).limit(READ_CHUNK_SIZE);
        match reader.read_buf(&mut destination).await {
            Ok(0) => {
                // Only this nonempty raw socket read establishes peer EOF.
                // Queue it after all data; observing it never closes writes.
                closed.send_replace(true);
                permit.send(ReadEvent::Eof);
                return PeerReadPumpOutcome::ReadHalfClosed;
            }
            Ok(_) => {
                #[cfg(coverage)]
                {
                    delivered_data = true;
                }
                permit.send(ReadEvent::Data(chunk));
            }
            Err(error) => {
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
            let (sender, receiver) = mpsc::channel(READ_QUEUE_CAPACITY);
            let (recycled, recycled_receiver) = mpsc::channel(READ_QUEUE_CAPACITY + 1);
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
                    recycled,
                    current: None,
                    terminal: ReadTerminal::Open,
                }),
                Some(pump_peer_read(
                    reader,
                    sender,
                    recycled_receiver,
                    closed,
                    failed,
                )),
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
            if let Some((mut current, offset)) = self.current.take() {
                let count = buffer.remaining().min(current.len() - offset);
                buffer.put_slice(&current[offset..offset + count]);
                let next_offset = offset + count;
                if next_offset == current.len() {
                    current.clear();
                    let _ = self.recycled.try_send(current);
                } else {
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
    use std::{
        collections::VecDeque,
        sync::{Arc, Mutex},
    };

    use super::*;

    struct ChunkReader {
        chunks: VecDeque<&'static [u8]>,
        destinations: Arc<Mutex<Vec<usize>>>,
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
            let destination = {
                let unfilled = buffer.initialize_unfilled();
                unfilled[..count].copy_from_slice(&chunk[..count]);
                unfilled.as_ptr() as usize
            };
            buffer.advance(count);
            let second_chunk_was_read = match this.destinations.lock() {
                Ok(mut destinations) => {
                    destinations.push(destination);
                    destinations.len() == 2
                }
                Err(_) => false,
            };
            if second_chunk_was_read {
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
    async fn pump_reuses_chunk_after_partial_consumer_read_finishes() {
        // A one-slot queue pauses the pump until the consumer dequeues each
        // event, letting the test hold one buffer partially consumed while
        // the pump performs the following read.
        let (sender, receiver) = mpsc::channel(1);
        let (recycled, recycled_receiver) = mpsc::channel(READ_QUEUE_CAPACITY + 1);
        let (closed, _) = watch::channel(false);
        let (failed, _) = watch::channel(None);
        let destinations = Arc::new(Mutex::new(Vec::new()));
        let second_chunk_read = Arc::new(tokio::sync::Notify::new());
        let pump = tokio::spawn(pump_peer_read(
            ChunkReader {
                chunks: VecDeque::from([&b"first"[..], &b"second"[..], &b"third"[..]]),
                destinations: Arc::clone(&destinations),
                second_chunk_read: Arc::clone(&second_chunk_read),
            },
            sender,
            recycled_receiver,
            closed,
            failed,
        ));
        let mut reader = BufferedReadAdapter(BufferedReadIo {
            writer: tokio::io::sink(),
            receiver,
            recycled,
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

        let destinations = destinations
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        assert_eq!(destinations.len(), 3);
        assert_ne!(destinations[0], destinations[1]);
        assert_eq!(destinations[0], destinations[2]);
    }
}
