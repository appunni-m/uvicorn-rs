//! Quinn bidirectional streams with request-scoped passive stop observation.
//!
//! The stream buffering and error conversions are adapted from h3-quinn 0.0.10.
//! See the packaged THIRD_PARTY_NOTICES.md for its source and MIT license.

#[cfg(coverage)]
use std::io;
use std::{
    collections::HashMap,
    future::Future,
    pin::{Pin, pin},
    sync::{Arc, Mutex},
    task::{Context, Poll, ready},
};

use super::{h3, h3_quinn};
use bytes::{Buf, Bytes};
use h3::{
    error::Code,
    quic::{self, ConnectionErrorIncoming, StreamErrorIncoming, StreamId, WriteBuf},
};
use h3_quinn::quinn;

pub(super) type PeerStopped = Pin<
    Box<dyn Future<Output = Result<Option<quinn::VarInt>, quinn::StoppedError>> + Send + 'static>,
>;

type BidiFuture = Pin<
    Box<
        dyn Future<Output = Result<(quinn::SendStream, quinn::RecvStream), quinn::ConnectionError>>
            + Send,
    >,
>;

#[derive(Clone, Default)]
pub(super) struct PeerStops(Arc<Mutex<HashMap<StreamId, PeerStopped>>>);

impl PeerStops {
    pub(super) fn take(&self, id: StreamId) -> Option<PeerStopped> {
        self.0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .remove(&id)
    }

    fn register(&self, id: StreamId, stream: &quinn::SendStream) -> Registration {
        // Quinn returns an owned future. Capturing it neither borrows the send
        // half nor polls it, and a stop received before its first poll is kept
        // in Quinn's stream state.
        self.register_observer(id, Box::pin(stream.stopped()))
    }

    fn register_observer(&self, id: StreamId, observer: PeerStopped) -> Registration {
        self.0
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .insert(id, observer);
        Registration {
            id,
            stops: self.clone(),
        }
    }
}

struct Registration {
    id: StreamId,
    stops: PeerStops,
}

impl Drop for Registration {
    fn drop(&mut self) {
        // Malformed or abandoned resolvers never reach the request handler.
        // Keep their connection-owning observers from accumulating in the map.
        // After the handler takes its observer this removal is a no-op.
        self.stops.take(self.id);
    }
}

pub(super) struct Connection {
    connection: quinn::Connection,
    inner: h3_quinn::Connection,
    accepting: Option<BidiFuture>,
    opening: Option<BidiFuture>,
    stops: PeerStops,
}

impl Connection {
    pub(super) fn new(connection: quinn::Connection) -> (Self, PeerStops) {
        let stops = PeerStops::default();
        (
            Self {
                inner: h3_quinn::Connection::new(connection.clone()),
                connection,
                accepting: None,
                opening: None,
                stops: stops.clone(),
            },
            stops,
        )
    }
}

impl quic::Connection<Bytes> for Connection {
    type RecvStream = h3_quinn::RecvStream;
    type OpenStreams = OpenStreams;

    fn poll_accept_recv(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::RecvStream, ConnectionErrorIncoming>> {
        quic::Connection::<Bytes>::poll_accept_recv(&mut self.inner, cx)
    }

    fn poll_accept_bidi(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::BidiStream, ConnectionErrorIncoming>> {
        let accepting = self.accepting.get_or_insert_with(|| {
            let connection = self.connection.clone();
            Box::pin(async move { connection.accept_bi().await })
        });
        let result = ready!(accepting.as_mut().poll(cx));
        self.accepting = None;
        let (send, recv) = result.map_err(connection_error)?;
        Poll::Ready(BidiStream::new(send, recv, Some(&self.stops)))
    }

    fn opener(&self) -> Self::OpenStreams {
        OpenStreams {
            connection: self.connection.clone(),
            inner: quic::Connection::<Bytes>::opener(&self.inner),
            opening: None,
        }
    }
}

impl quic::OpenStreams<Bytes> for Connection {
    type BidiStream = BidiStream;
    type SendStream = h3_quinn::SendStream<Bytes>;

    fn poll_open_bidi(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::BidiStream, StreamErrorIncoming>> {
        poll_open_bidi(&self.connection, &mut self.opening, cx)
    }

    fn poll_open_send(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::SendStream, StreamErrorIncoming>> {
        quic::OpenStreams::<Bytes>::poll_open_send(&mut self.inner, cx)
    }

    fn close(&mut self, code: Code, reason: &[u8]) {
        quic::OpenStreams::<Bytes>::close(&mut self.inner, code, reason);
    }
}

pub(super) struct OpenStreams {
    connection: quinn::Connection,
    inner: h3_quinn::OpenStreams,
    opening: Option<BidiFuture>,
}

impl quic::OpenStreams<Bytes> for OpenStreams {
    type BidiStream = BidiStream;
    type SendStream = h3_quinn::SendStream<Bytes>;

    fn poll_open_bidi(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::BidiStream, StreamErrorIncoming>> {
        poll_open_bidi(&self.connection, &mut self.opening, cx)
    }

    fn poll_open_send(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Self::SendStream, StreamErrorIncoming>> {
        quic::OpenStreams::<Bytes>::poll_open_send(&mut self.inner, cx)
    }

    fn close(&mut self, code: Code, reason: &[u8]) {
        quic::OpenStreams::<Bytes>::close(&mut self.inner, code, reason);
    }
}

fn poll_open_bidi(
    connection: &quinn::Connection,
    opening: &mut Option<BidiFuture>,
    cx: &mut Context<'_>,
) -> Poll<Result<BidiStream, StreamErrorIncoming>> {
    let future = opening.get_or_insert_with(|| {
        let connection = connection.clone();
        Box::pin(async move { connection.open_bi().await })
    });
    let result = ready!(future.as_mut().poll(cx));
    *opening = None;
    let (send, recv) = result.map_err(|error| stream_connection_error(connection_error(error)))?;
    Poll::Ready(BidiStream::new(send, recv, None).map_err(stream_connection_error))
}

pub(super) struct BidiStream {
    send: SendStream,
    recv: RecvStream,
}

pub(super) fn checked_stream_id(raw_id: u64) -> Result<StreamId, ConnectionErrorIncoming> {
    raw_id.try_into().map_err(|error| {
        ConnectionErrorIncoming::InternalError(format!("invalid QUIC stream ID: {error}"))
    })
}

impl BidiStream {
    fn new(
        send: quinn::SendStream,
        recv: quinn::RecvStream,
        stops: Option<&PeerStops>,
    ) -> Result<Self, ConnectionErrorIncoming> {
        // Both stream IDs use QUIC varints. Validate once at the adapter
        // boundary rather than panicking in the infallible ID accessors.
        let actual_raw_id = u64::from(send.id());
        #[cfg(coverage)]
        let invalid_stream_id_injected =
            stops.is_some() && crate::take_http3_invalid_stream_id_fault();
        #[cfg(coverage)]
        let raw_id = if invalid_stream_id_injected {
            u64::MAX
        } else {
            actual_raw_id
        };
        #[cfg(not(coverage))]
        let raw_id = actual_raw_id;
        let id_result = checked_stream_id(raw_id);
        #[cfg(coverage)]
        if invalid_stream_id_injected && id_result.is_err() {
            crate::observe_http3_invalid_stream_id_fault();
        }
        let id = id_result?;
        let registration = stops
            .filter(|_| {
                #[cfg(coverage)]
                {
                    !crate::take_http3_peer_stop_observer_unavailable_fault()
                }
                #[cfg(not(coverage))]
                {
                    true
                }
            })
            .map(|stops| {
                #[cfg(coverage)]
                if let Some(fault) = crate::take_http3_peer_stop_observer_outcome_fault() {
                    let outcome = match fault {
                        crate::Http3PeerStopObserverOutcomeFault::Error => {
                            Err(quinn::StoppedError::ZeroRttRejected)
                        }
                        crate::Http3PeerStopObserverOutcomeFault::LocalRetirement => Ok(None),
                    };
                    let observer: PeerStopped = Box::pin(std::future::ready(outcome));
                    return stops.register_observer(id, observer);
                }
                stops.register(id, &send)
            });
        Ok(Self {
            send: SendStream {
                stream: send,
                id,
                writing: None,
                _registration: registration,
            },
            recv: RecvStream { stream: recv, id },
        })
    }
}

impl quic::BidiStream<Bytes> for BidiStream {
    type SendStream = SendStream;
    type RecvStream = RecvStream;

    fn split(self) -> (Self::SendStream, Self::RecvStream) {
        (self.send, self.recv)
    }
}

impl quic::SendStream<Bytes> for BidiStream {
    fn poll_ready(&mut self, cx: &mut Context<'_>) -> Poll<Result<(), StreamErrorIncoming>> {
        self.send.poll_ready(cx)
    }

    fn send_data<T: Into<WriteBuf<Bytes>>>(&mut self, data: T) -> Result<(), StreamErrorIncoming> {
        self.send.send_data(data)
    }

    fn poll_finish(&mut self, cx: &mut Context<'_>) -> Poll<Result<(), StreamErrorIncoming>> {
        self.send.poll_finish(cx)
    }

    fn reset(&mut self, code: u64) {
        self.send.reset(code);
    }

    fn send_id(&self) -> StreamId {
        self.send.id
    }
}

impl quic::RecvStream for BidiStream {
    type Buf = Bytes;

    fn poll_data(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Option<Bytes>, StreamErrorIncoming>> {
        self.recv.poll_data(cx)
    }

    fn stop_sending(&mut self, code: u64) {
        self.recv.stop_sending(code);
    }

    fn recv_id(&self) -> StreamId {
        self.recv.id
    }
}

pub(super) struct SendStream {
    stream: quinn::SendStream,
    id: StreamId,
    writing: Option<WriteBuf<Bytes>>,
    _registration: Option<Registration>,
}

impl quic::SendStream<Bytes> for SendStream {
    fn poll_ready(&mut self, cx: &mut Context<'_>) -> Poll<Result<(), StreamErrorIncoming>> {
        if let Some(data) = &mut self.writing {
            while data.has_remaining() {
                let write = {
                    #[cfg(coverage)]
                    if crate::take_http3_write_closed_stream_fault() {
                        Poll::Ready(Err(quinn::WriteError::ClosedStream))
                    } else {
                        Pin::new(&mut self.stream).poll_write(cx, data.chunk())
                    }
                    #[cfg(not(coverage))]
                    {
                        Pin::new(&mut self.stream).poll_write(cx, data.chunk())
                    }
                };
                let written = ready!(write).map_err(write_error)?;
                data.advance(written);
            }
        }
        self.writing = None;
        Poll::Ready(Ok(()))
    }

    fn send_data<T: Into<WriteBuf<Bytes>>>(&mut self, data: T) -> Result<(), StreamErrorIncoming> {
        #[cfg(coverage)]
        let mut data = Some(data.into());
        #[cfg(coverage)]
        if crate::take_http3_send_data_pending_fault() {
            self.writing = data.take();
        }
        if self.writing.is_some() {
            return Err(stream_connection_error(
                ConnectionErrorIncoming::InternalError(
                    "HTTP/3 send_data called before the stream was ready".to_owned(),
                ),
            ));
        }
        #[cfg(coverage)]
        if crate::take_http3_response_send_data_fault() {
            return Err(StreamErrorIncoming::Unknown(Box::new(io::Error::other(
                "injected HTTP/3 response send failure",
            ))));
        }
        #[cfg(coverage)]
        {
            self.writing = data;
        }
        #[cfg(not(coverage))]
        {
            self.writing = Some(data.into());
        }
        Ok(())
    }

    fn poll_finish(&mut self, _cx: &mut Context<'_>) -> Poll<Result<(), StreamErrorIncoming>> {
        #[cfg(coverage)]
        if crate::take_http3_response_finish_fault() {
            return Poll::Ready(Err(StreamErrorIncoming::Unknown(Box::new(
                quinn::ClosedStream::default(),
            ))));
        }
        Poll::Ready(
            self.stream
                .finish()
                .map_err(|error| StreamErrorIncoming::Unknown(Box::new(error))),
        )
    }

    fn reset(&mut self, code: u64) {
        let _ = self
            .stream
            .reset(quinn::VarInt::from_u64(code).unwrap_or(quinn::VarInt::MAX));
    }

    fn send_id(&self) -> StreamId {
        self.id
    }
}

pub(super) struct RecvStream {
    stream: quinn::RecvStream,
    id: StreamId,
}

impl quic::RecvStream for RecvStream {
    type Buf = Bytes;

    fn poll_data(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Result<Option<Bytes>, StreamErrorIncoming>> {
        // Quinn documents read_chunk as cancel-safe and keeps the registered
        // reader waker in connection state. Dropping a Pending future here
        // leaves the stream available to stop_sending and avoids a heap copy.
        let read = {
            #[cfg(coverage)]
            if crate::take_http3_read_closed_stream_fault() {
                Poll::Ready(Err(quinn::ReadError::ClosedStream))
            } else {
                pin!(self.stream.read_chunk(usize::MAX, true)).poll(cx)
            }
            #[cfg(not(coverage))]
            {
                pin!(self.stream.read_chunk(usize::MAX, true)).poll(cx)
            }
        };
        let chunk = ready!(read);
        Poll::Ready(
            chunk
                .map(|chunk| chunk.map(|chunk| chunk.bytes))
                .map_err(read_error),
        )
    }

    fn stop_sending(&mut self, code: u64) {
        let _ = self
            .stream
            .stop(quinn::VarInt::from_u64(code).unwrap_or(quinn::VarInt::MAX));
    }

    fn recv_id(&self) -> StreamId {
        self.id
    }
}

fn stream_connection_error(connection_error: ConnectionErrorIncoming) -> StreamErrorIncoming {
    StreamErrorIncoming::ConnectionErrorIncoming { connection_error }
}

fn connection_error(error: quinn::ConnectionError) -> ConnectionErrorIncoming {
    match error {
        quinn::ConnectionError::ApplicationClosed(error) => {
            ConnectionErrorIncoming::ApplicationClose {
                error_code: error.error_code.into_inner(),
            }
        }
        quinn::ConnectionError::TimedOut => ConnectionErrorIncoming::Timeout,
        error => ConnectionErrorIncoming::Undefined(Arc::new(error)),
    }
}

fn write_error(error: quinn::WriteError) -> StreamErrorIncoming {
    match error {
        quinn::WriteError::Stopped(code) => StreamErrorIncoming::StreamTerminated {
            error_code: code.into_inner(),
        },
        quinn::WriteError::ConnectionLost(error) => {
            stream_connection_error(connection_error(error))
        }
        error => StreamErrorIncoming::Unknown(Box::new(error)),
    }
}

fn read_error(error: quinn::ReadError) -> StreamErrorIncoming {
    match error {
        quinn::ReadError::Reset(code) => StreamErrorIncoming::StreamTerminated {
            error_code: code.into_inner(),
        },
        quinn::ReadError::ConnectionLost(error) => stream_connection_error(connection_error(error)),
        error => StreamErrorIncoming::Unknown(Box::new(error)),
    }
}
