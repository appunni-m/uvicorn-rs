#![forbid(unsafe_code)]
//! Minimal native `uvicorn-rs` server example.

use std::{
    convert::Infallible,
    error::Error,
    future::{ready, Ready},
    task::{Context, Poll},
};

use bytes::Bytes;
use http::{Request, Response, StatusCode};
use http_body_util::Full;
use hyper::body::Incoming;
use tokio::{net::TcpListener, sync::oneshot};
use tower_service::Service;
use uvicorn_rs::{serve_tcp, ServerConfig};

#[derive(Clone)]
struct App;

impl Service<Request<Incoming>> for App {
    type Response = Response<Full<Bytes>>;
    type Error = Infallible;
    type Future = Ready<Result<Self::Response, Self::Error>>;

    fn poll_ready(&mut self, _cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, request: Request<Incoming>) -> Self::Future {
        let (status, body) = if request.uri().path() == "/health" {
            (StatusCode::OK, Bytes::from_static(b"ok\n"))
        } else {
            (StatusCode::NOT_FOUND, Bytes::from_static(b"not found\n"))
        };
        let mut response = Response::new(Full::new(body));
        *response.status_mut() = status;
        ready(Ok(response))
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error + Send + Sync>> {
    let listener = TcpListener::bind("127.0.0.1:8080").await?;
    let (shutdown_sender, shutdown_receiver) = oneshot::channel::<()>();
    let server = serve_tcp(
        listener,
        App,
        async move {
            let _ = shutdown_receiver.await;
        },
        ServerConfig::default(),
    );
    tokio::pin!(server);

    tokio::select! {
        result = &mut server => result?,
        signal = tokio::signal::ctrl_c() => {
            signal?;
            let _ = shutdown_sender.send(());
            server.await?;
        }
    }

    Ok(())
}
