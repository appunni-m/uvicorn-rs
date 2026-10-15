//! Coverage-runner support for exercising the HTTP/3 adapter.
//!
//! This module is compiled only for the unified coverage runner. Its helper
//! control flow is not part of the production region-coverage denominator.

use std::{error::Error, io};

use bytes::{Buf, Bytes};
use h3::error::Code;
use h3::quic::{ConnectionErrorIncoming, StreamErrorIncoming};
use h3_quinn::quinn;
use http::{Request, StatusCode};

use super::transport;

pub(crate) struct CoverageClient {
    driver: tokio::task::JoinHandle<()>,
    sender: h3::client::SendRequest<transport::OpenStreams, Bytes>,
}

impl CoverageClient {
    pub(crate) async fn connect(
        connection: quinn::Connection,
    ) -> Result<Self, Box<dyn Error + Send + Sync + 'static>> {
        let transport = transport::Connection::new(connection).0;
        let (mut driver, sender) = h3::client::new(transport).await?;
        let driver = tokio::spawn(async move {
            let _ = std::future::poll_fn(|context| driver.poll_close(context)).await;
        });
        Ok(Self { driver, sender })
    }

    pub(crate) async fn request(
        &mut self,
        request: Request<()>,
        body: Bytes,
        trailers: Option<http::HeaderMap>,
    ) -> Result<(StatusCode, Bytes, Option<http::HeaderMap>), Box<dyn Error + Send + Sync + 'static>>
    {
        let mut stream = self.sender.send_request(request).await?;
        if !body.is_empty() {
            stream.send_data(body).await?;
        }
        if let Some(trailers) = trailers {
            stream.send_trailers(trailers).await?;
        } else {
            stream.finish().await?;
        }

        let response = stream.recv_response().await?;
        let mut response_body = Vec::new();
        while let Some(mut data) = stream.recv_data().await? {
            let length = data.remaining();
            response_body.extend_from_slice(data.chunk());
            data.advance(length);
        }
        let response_trailers = stream.recv_trailers().await?;
        Ok((
            response.status(),
            Bytes::from(response_body),
            response_trailers,
        ))
    }

    pub(crate) async fn close(self) {
        self.driver.abort();
        let _ = self.driver.await;
    }
}

pub(crate) async fn coverage_open_bidi_application_close_code(
    connection: quinn::Connection,
) -> Result<u64, Box<dyn Error + Send + Sync + 'static>> {
    let (mut connection, _) = transport::Connection::new(connection);
    match std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_bidi(&mut connection, context)
    })
    .await
    {
        Err(StreamErrorIncoming::ConnectionErrorIncoming {
            connection_error: ConnectionErrorIncoming::ApplicationClose { error_code },
        }) => Ok(error_code),
        Err(error) => Err(Box::new(error)),
        Ok(_stream) => Err(Box::new(io::Error::other(
            "HTTP/3 QUIC connection remained open while probing its close mapping",
        ))),
    }
}

pub(crate) async fn coverage_accept_bidi_error(
    connection: quinn::Connection,
) -> Result<h3::quic::StreamId, h3::quic::ConnectionErrorIncoming> {
    let (mut connection, _) = transport::Connection::new(connection);
    std::future::poll_fn(|context| {
        h3::quic::Connection::<Bytes>::poll_accept_bidi(&mut connection, context)
    })
    .await
    .map(|stream| h3::quic::SendStream::<Bytes>::send_id(&stream))
}

pub(crate) async fn coverage_finish_after_reset(
    connection: quinn::Connection,
) -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    use h3::quic::{BidiStream as _, OpenStreams as _, RecvStream as _, SendStream as _};

    let (mut connection, _) = transport::Connection::new(connection);
    let stream = std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_bidi(&mut connection, context)
    })
    .await?;
    let (mut send, mut recv) = stream.split();
    send.reset(Code::H3_REQUEST_CANCELLED.value());
    let result = std::future::poll_fn(|context| {
        h3::quic::SendStream::<Bytes>::poll_finish(&mut send, context)
    })
    .await;
    match result {
        Err(StreamErrorIncoming::Unknown(error))
            if error.downcast_ref::<quinn::ClosedStream>().is_some() => {}
        Ok(()) => {
            return Err(
                io::Error::other("HTTP/3 adapter finished a stream after it was reset").into(),
            );
        }
        Err(error) => {
            return Err(io::Error::other(format!(
                "HTTP/3 adapter returned the wrong finish-after-reset error: {error}"
            ))
            .into());
        }
    }
    recv.stop_sending(Code::H3_REQUEST_CANCELLED.value());

    let mut recovery = std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_bidi(&mut connection, context)
    })
    .await?;
    h3::quic::SendStream::<Bytes>::reset(&mut recovery, Code::H3_REQUEST_CANCELLED.value());
    h3::quic::RecvStream::stop_sending(&mut recovery, Code::H3_REQUEST_CANCELLED.value());
    h3::quic::OpenStreams::<Bytes>::close(
        &mut connection,
        Code::H3_NO_ERROR,
        b"invalid-send-sequence contract complete",
    );
    Ok(())
}

pub(crate) async fn coverage_exercise_client_adapter_methods(
    connection: quinn::Connection,
) -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    use h3::quic::{BidiStream as _, RecvStream as _, SendStream as _};

    let (mut connection, _) = transport::Connection::new(connection);
    let mut opener = h3::quic::Connection::<Bytes>::opener(&connection);
    let mut unidirectional = std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_send(&mut opener, context)
    })
    .await?;
    std::future::poll_fn(|context| {
        h3::quic::SendStream::<Bytes>::poll_ready(&mut unidirectional, context)
    })
    .await?;
    std::future::poll_fn(|context| {
        h3::quic::SendStream::<Bytes>::poll_finish(&mut unidirectional, context)
    })
    .await?;

    let mut bidi = std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_bidi(&mut connection, context)
    })
    .await?;
    let send_id = h3::quic::SendStream::<Bytes>::send_id(&bidi);
    let recv_id = h3::quic::RecvStream::recv_id(&bidi);
    if send_id != recv_id {
        return Err(Box::new(io::Error::other(
            "HTTP/3 adapter reported different IDs for one bidirectional stream",
        )));
    }
    std::future::poll_fn(|context| h3::quic::SendStream::<Bytes>::poll_ready(&mut bidi, context))
        .await?;
    h3::quic::RecvStream::stop_sending(&mut bidi, Code::H3_REQUEST_CANCELLED.value());
    h3::quic::SendStream::<Bytes>::reset(&mut bidi, Code::H3_REQUEST_CANCELLED.value());

    let stream = std::future::poll_fn(|context| {
        h3::quic::OpenStreams::<Bytes>::poll_open_bidi(&mut connection, context)
    })
    .await?;
    let (mut send, mut recv) = stream.split();
    if send.send_id() != recv.recv_id() {
        return Err(Box::new(io::Error::other(
            "HTTP/3 split streams reported different IDs",
        )));
    }
    recv.stop_sending(Code::H3_REQUEST_CANCELLED.value());
    send.reset(Code::H3_REQUEST_CANCELLED.value());

    h3::quic::OpenStreams::<Bytes>::close(
        &mut opener,
        Code::H3_NO_ERROR,
        b"adapter contract complete",
    );
    Ok(())
}
