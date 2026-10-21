use std::{
    future::Future,
    io,
    pin::Pin,
    task::{Context, Poll},
};

use bytes::{Buf, BufMut, Bytes, BytesMut};
#[cfg(unix)]
use tokio::net::{
    unix::OwnedReadHalf as UnixOwnedReadHalf, unix::OwnedWriteHalf as UnixOwnedWriteHalf,
    UnixStream,
};
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    net::{tcp::OwnedWriteHalf, TcpStream},
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
    current: Bytes,
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
    Data(Bytes),
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
                }),
                Some(pump_peer_read(reader, sender, closed, failed)),
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
        let mut chunk = BytesMut::with_capacity(READ_CHUNK_SIZE);
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
                permit.send(ReadEvent::Data(chunk.freeze()));
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
                    current: Bytes::new(),
                    terminal: ReadTerminal::Open,
                }),
                Some(pump_peer_read(reader, sender, closed, failed)),
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
            if !self.current.is_empty() {
                let count = buffer.remaining().min(self.current.len());
                buffer.put_slice(&self.current[..count]);
                self.current.advance(count);
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
                Poll::Ready(Some(ReadEvent::Data(chunk))) => self.current = chunk,
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
