#![forbid(unsafe_code)]

use std::{error::Error, io, io::Write, net::SocketAddr};

use bytes::Bytes;
use futures_util::stream;
use http::{Response, StatusCode};
use http_body::Frame;
use http_body_util::{BodyExt, StreamBody};
use starlette_rs::{
    NativeApplication, NativeApplicationError, NativeHttpResponse, NativeRequest, NativeRoute,
    box_native_body,
};
use tokio::{net::TcpListener, sync::oneshot, time::sleep};
use uvicorn_rs::{ServerConfig, serve_tcp};

type AppResult = Result<NativeHttpResponse, NativeApplicationError>;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn Error + Send + Sync>> {
    let address = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "127.0.0.1:8080".to_owned())
        .parse::<SocketAddr>()?;
    let listener = TcpListener::bind(address).await?;
    let address = listener.local_addr()?;
    let application = NativeApplication::new([
        NativeRoute::new("/items/{item_id:int}", ["POST"], item_endpoint),
        NativeRoute::new("/fail", ["GET"], failing_endpoint),
        NativeRoute::new("/body-error", ["GET"], body_error_endpoint),
    ])?;

    writeln!(io::stdout().lock(), "listening on {address}")?;

    let (shutdown_sender, shutdown_receiver) = oneshot::channel::<()>();
    let server = serve_tcp(
        listener,
        application,
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

async fn item_endpoint(mut request: NativeRequest) -> AppResult {
    let item_id = request
        .path_params()
        .iter()
        .find(|(name, _)| name == "item_id")
        .map(|(_, value)| value.clone())
        .unwrap_or_else(|| "missing".to_owned());
    let query = request.query().unwrap_or_default().to_owned();
    let mut request_chunks = Vec::new();
    while let Some(frame) = request.body_mut().frame().await {
        let frame = frame.map_err(NativeApplicationError::Endpoint)?;
        if let Ok(data) = frame.into_data() {
            request_chunks.push(data);
        }
    }

    let mut response_chunks = Vec::with_capacity(request_chunks.len() + 1);
    response_chunks.push(Bytes::from(format!("id={item_id};query={query};body=")));
    response_chunks.extend(request_chunks);
    let response_stream = stream::iter(
        response_chunks
            .into_iter()
            .map(|chunk| Ok::<_, io::Error>(Frame::data(chunk))),
    );
    response(StatusCode::OK, StreamBody::new(response_stream))
}

async fn failing_endpoint(_request: NativeRequest) -> AppResult {
    Err(NativeApplicationError::Endpoint(Box::new(
        io::Error::other("native service failure before response commitment"),
    )))
}

async fn body_error_endpoint(_request: NativeRequest) -> AppResult {
    let body_stream = stream::unfold(0, |state| async move {
        match state {
            0 => Some((
                Ok::<_, io::Error>(Frame::data(Bytes::from_static(b"partial-response"))),
                1,
            )),
            1 => {
                sleep(std::time::Duration::from_millis(50)).await;
                Some((
                    Err(io::Error::other(
                        "native response body failure after response commitment",
                    )),
                    2,
                ))
            }
            _ => None,
        }
    });
    response(StatusCode::OK, StreamBody::new(body_stream))
}

fn response<B>(status: StatusCode, body: B) -> AppResult
where
    B: http_body::Body<Data = Bytes> + Send + 'static,
    B::Error: Error + Send + Sync + 'static,
{
    Response::builder()
        .status(status)
        .body(box_native_body(body))
        .map_err(|error| NativeApplicationError::Endpoint(Box::new(error)))
}
