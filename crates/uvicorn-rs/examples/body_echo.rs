//! Demonstrates a body-aware Tower service on the Rust-native HTTP server.

use std::{
    convert::Infallible,
    error::Error,
    future::Future,
    io,
    pin::Pin,
    task::{Context, Poll},
};

use bytes::{Buf, Bytes};
use http::{Request, Response};
use http_body::Body;
use http_body_util::StreamBody;
use tokio::net::TcpListener;
use tower_service::Service;

type EchoStream =
    futures_util::stream::Iter<std::vec::IntoIter<Result<http_body::Frame<Bytes>, Infallible>>>;
type EchoBody = StreamBody<EchoStream>;
type EchoFuture = Pin<Box<dyn Future<Output = Result<Response<EchoBody>, io::Error>> + Send>>;

#[derive(Clone, Copy)]
struct BodyCounter;

impl<B> Service<Request<B>> for BodyCounter
where
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Error + Send + Sync + 'static,
{
    type Response = Response<EchoBody>;
    type Error = io::Error;
    type Future = EchoFuture;

    fn poll_ready(&mut self, _context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, request: Request<B>) -> Self::Future {
        let mut body = Box::pin(request.into_body());
        Box::pin(async move {
            let mut received_bytes = 0_usize;
            while let Some(frame) =
                std::future::poll_fn(|context| body.as_mut().poll_frame(context)).await
            {
                let frame = frame.map_err(|error| io::Error::other(error.to_string()))?;
                if let Ok(data) = frame.into_data() {
                    received_bytes =
                        received_bytes
                            .checked_add(data.remaining())
                            .ok_or_else(|| {
                                io::Error::new(
                                    io::ErrorKind::InvalidData,
                                    "request body size overflow",
                                )
                            })?;
                }
            }

            let chunks = vec![
                Ok(http_body::Frame::data(Bytes::from_static(b"received="))),
                Ok(http_body::Frame::data(Bytes::from(
                    received_bytes.to_string(),
                ))),
                Ok(http_body::Frame::data(Bytes::from_static(b"\n"))),
            ];
            let mut response = Response::new(StreamBody::new(futures_util::stream::iter(chunks)));
            *response.status_mut() = http::StatusCode::OK;
            Ok(response)
        })
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error + Send + Sync>> {
    let listener = TcpListener::bind("127.0.0.1:8001").await?;
    let shutdown = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    uvicorn_rs::serve_tcp(
        listener,
        BodyCounter,
        shutdown,
        uvicorn_rs::ServerConfig::default(),
    )
    .await?;
    Ok(())
}
