#![forbid(unsafe_code)]

//! Runs manifest-driven socket contracts through the Rust-native web stack.

use std::{
    convert::Infallible,
    error::Error,
    io::{self, Write as _},
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    time::Duration,
};

use bytes::Bytes;
use fastapi_rs::native::{
    FastApiNativeBuilder, NativeApplication, NativeApplicationError, NativeHttpResponse,
    NativeRequest, NativeRequestError, json_body, json_response, optional_query_parameter,
    path_parameter, streaming_response,
};
use futures_util::stream;
use http::{Request, StatusCode};
use http_body::Frame;
use http_body_util::{BodyExt, Full, StreamBody};
use hyper::client::conn;
use hyper_util::rt::{TokioExecutor, TokioIo};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::oneshot,
    task::JoinHandle,
    time::{Instant, timeout},
};
use uvicorn_rs::{ServeError, ServerConfig, serve_tcp};

type ProbeResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

#[derive(Deserialize)]
struct Manifest {
    schema_version: u32,
    cases: Vec<Value>,
}

#[derive(Serialize)]
struct ItemOutput {
    item_id: u64,
    tag: Option<String>,
}

#[derive(Deserialize, Serialize)]
struct EchoInput {
    message: String,
}

#[derive(Serialize)]
struct RequestHeadOutput {
    content_length_present: bool,
}

struct AppState {
    backpressure_chunk_size: usize,
    backpressure_total_chunks: usize,
    backpressure_chunks_polled: Arc<AtomicUsize>,
    backpressure_streams_dropped: Arc<AtomicUsize>,
    upload_bytes_received: Arc<AtomicUsize>,
    upload_body_errors: Arc<AtomicUsize>,
    upload_handlers_cancelled: Arc<AtomicUsize>,
    stream_upload_bytes_received: Arc<AtomicUsize>,
    stream_upload_handlers_completed: Arc<AtomicUsize>,
}

impl AppState {
    fn new(backpressure_chunk_size: usize, backpressure_total_chunks: usize) -> Self {
        Self {
            backpressure_chunk_size,
            backpressure_total_chunks,
            backpressure_chunks_polled: Arc::default(),
            backpressure_streams_dropped: Arc::default(),
            upload_bytes_received: Arc::default(),
            upload_body_errors: Arc::default(),
            upload_handlers_cancelled: Arc::default(),
            stream_upload_bytes_received: Arc::default(),
            stream_upload_handlers_completed: Arc::default(),
        }
    }
}

#[derive(Serialize, Deserialize)]
struct StateSnapshot {
    backpressure_chunks_polled: usize,
    backpressure_streams_dropped: usize,
    upload_bytes_received: usize,
    upload_body_errors: usize,
    upload_handlers_cancelled: usize,
    stream_upload_bytes_received: usize,
    stream_upload_handlers_completed: usize,
}

struct DropSignal(Arc<AtomicUsize>);

impl Drop for DropSignal {
    fn drop(&mut self) {
        self.0.fetch_add(1, Ordering::AcqRel);
    }
}

struct UploadTaskGuard {
    handled: bool,
    cancelled: Arc<AtomicUsize>,
}

impl Drop for UploadTaskGuard {
    fn drop(&mut self) {
        if !self.handled {
            self.cancelled.fetch_add(1, Ordering::AcqRel);
        }
    }
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> ProbeResult<()> {
    let manifest_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "examples/native-fastapi-contracts/manifest.json".to_owned());
    let manifest: Manifest = serde_json::from_slice(&std::fs::read(manifest_path)?)?;
    if manifest.schema_version != 1 {
        return Err(
            io::Error::new(io::ErrorKind::InvalidData, "unsupported manifest version").into(),
        );
    }

    let (chunk_size, total_chunks) = backpressure_config(&manifest)?;
    let state = Arc::new(AppState::new(chunk_size, total_chunks));
    let application = build_application(Arc::clone(&state))?;
    let (address, shutdown_sender, server) = start_server(application.clone()).await?;
    let mut graceful_cases = Vec::new();

    for case in &manifest.cases {
        let id = required_str(case, "id")?;
        let operation = required_str(case, "operation")?;
        let protocol = required_str(case, "protocol")?;
        if !matches!(
            operation,
            "request"
                | "response-backpressure"
                | "http2-upload-progress"
                | "http2-upload-reset"
                | "graceful-drain"
        ) && protocol != "http/1.1"
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("{id}: {operation} is only implemented for HTTP/1.1"),
            )
            .into());
        }
        if operation == "graceful-drain" {
            graceful_cases.push(case.clone());
            continue;
        }

        match operation {
            "request" => run_request_case(address, case).await?,
            "stream-progress" => run_stream_progress_case(address, case).await?,
            "upload-progress" => run_stream_upload_progress_case(address, case).await?,
            "upload-disconnect" => run_upload_disconnect_case(address, case).await?,
            "http2-upload-progress" => run_http2_stream_upload_progress_case(address, case).await?,
            "http2-upload-reset" => run_http2_upload_reset_case(address, case).await?,
            "response-backpressure" => run_backpressure_case(address, case).await?,
            other => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("{id}: unsupported operation {other:?}"),
                )
                .into());
            }
        }
        writeln!(io::stdout().lock(), "PASS {id}")?;
    }

    let _ = shutdown_sender.send(());
    await_server(server).await?;

    for case in graceful_cases {
        let app = build_application(Arc::clone(&state))?;
        let (address, shutdown_sender, server) = start_server(app).await?;
        match required_str(&case, "protocol")? {
            "http/1.1" => run_graceful_drain_case(address, &case, shutdown_sender, server).await?,
            "h2c-prior-knowledge" => {
                run_http2_graceful_drain_case(address, &case, shutdown_sender, server).await?
            }
            protocol => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("unsupported graceful-drain protocol {protocol:?}"),
                )
                .into());
            }
        }
        writeln!(io::stdout().lock(), "PASS {}", required_str(&case, "id")?)?;
    }

    Ok(())
}

fn build_application(state: Arc<AppState>) -> Result<NativeApplication, NativeApplicationError> {
    let stats_state = Arc::clone(&state);
    let upload_state = Arc::clone(&state);
    let stream_upload_state = Arc::clone(&state);
    let backpressure_polled = Arc::clone(&state.backpressure_chunks_polled);
    let backpressure_dropped = Arc::clone(&state.backpressure_streams_dropped);
    let backpressure_chunk_size = state.backpressure_chunk_size;
    let backpressure_total_chunks = state.backpressure_total_chunks;

    FastApiNativeBuilder::new()
        .route(
            "/items/{item_id}",
            ["GET"],
            |request: NativeRequest| async move {
                let item_id = path_parameter(&request, "item_id")?;
                let tag = optional_query_parameter(&request, "tag")?;
                json_response(&ItemOutput { item_id, tag }, StatusCode::OK).map_err(Into::into)
            },
        )
        .route("/echo", ["POST"], |mut request| async move {
            let input: EchoInput = json_body(&mut request, 1024 * 1024).await?;
            json_response(&input, StatusCode::OK).map_err(Into::into)
        })
        .route("/stream-upload", ["POST"], move |mut request| {
            let state = Arc::clone(&stream_upload_state);
            async move {
                let mut received = 0_usize;
                loop {
                    match request.body_mut().frame().await {
                        Some(Ok(frame)) => {
                            if let Ok(data) = frame.into_data() {
                                received = match received.checked_add(data.len()) {
                                    Some(total) => total,
                                    None => {
                                        return Err(NativeRequestError::new(
                                            StatusCode::PAYLOAD_TOO_LARGE,
                                            "request body byte count overflowed",
                                        ));
                                    }
                                };
                                state
                                    .stream_upload_bytes_received
                                    .fetch_add(data.len(), Ordering::AcqRel);
                            }
                        }
                        Some(Err(_error)) => {
                            return Err(NativeRequestError::new(
                                StatusCode::BAD_REQUEST,
                                "request body stream failed",
                            ));
                        }
                        None => {
                            state
                                .stream_upload_handlers_completed
                                .fetch_add(1, Ordering::AcqRel);
                            break;
                        }
                    }
                }
                json_response(&received, StatusCode::OK).map_err(Into::into)
            }
        })
        .route(
            "/request-head",
            ["GET"],
            |request: NativeRequest| async move {
                let content_length_present =
                    request.headers().contains_key(http::header::CONTENT_LENGTH);
                json_response(
                    &RequestHeadOutput {
                        content_length_present,
                    },
                    StatusCode::OK,
                )
                .map_err(Into::into)
            },
        )
        .route("/failure", ["GET"], |_request| async move {
            Err::<NativeHttpResponse, _>(NativeRequestError::new(
                StatusCode::INTERNAL_SERVER_ERROR,
                "native application failure",
            ))
        })
        .route("/stream", ["GET"], move |_request| {
            let dropped = Arc::clone(&state.backpressure_streams_dropped);
            async move {
                let frames =
                    stream::unfold((0_u8, DropSignal(dropped)), |(index, signal)| async move {
                        let data = match index {
                            0 => Bytes::from_static(b"first\n"),
                            1 => {
                                tokio::time::sleep(Duration::from_millis(100)).await;
                                Bytes::from_static(b"second\n")
                            }
                            _ => return None,
                        };
                        Some((Ok::<_, Infallible>(Frame::data(data)), (index + 1, signal)))
                    });
                Ok::<_, NativeRequestError>(streaming_response(
                    StatusCode::OK,
                    StreamBody::new(frames),
                ))
            }
        })
        .route("/backpressure", ["GET"], move |_request| {
            let polled = Arc::clone(&backpressure_polled);
            let dropped = Arc::clone(&backpressure_dropped);
            let chunk_size = backpressure_chunk_size;
            let total_chunks = backpressure_total_chunks;
            async move {
                let frames = stream::unfold(
                    (
                        0_usize,
                        DropSignal(dropped),
                        polled,
                        chunk_size,
                        total_chunks,
                    ),
                    |(index, signal, polled, chunk_size, total_chunks)| async move {
                        if index >= total_chunks {
                            return None;
                        }
                        polled.fetch_add(1, Ordering::AcqRel);
                        let data = Bytes::from(vec![b'x'; chunk_size]);
                        Some((
                            Ok::<_, Infallible>(Frame::data(data)),
                            (index + 1, signal, polled, chunk_size, total_chunks),
                        ))
                    },
                );
                Ok::<_, NativeRequestError>(streaming_response(
                    StatusCode::OK,
                    StreamBody::new(frames),
                ))
            }
        })
        .route("/drain", ["GET"], |_request| async move {
            let frames = stream::unfold(0_u8, |index| async move {
                let data = match index {
                    0 => Bytes::from_static(b"drain-first\n"),
                    1 => {
                        tokio::time::sleep(Duration::from_millis(150)).await;
                        Bytes::from_static(b"drain-second\n")
                    }
                    _ => return None,
                };
                Some((Ok::<_, Infallible>(Frame::data(data)), index + 1))
            });
            Ok::<_, NativeRequestError>(streaming_response(StatusCode::OK, StreamBody::new(frames)))
        })
        .route("/upload", ["POST"], move |mut request| {
            let state = Arc::clone(&upload_state);
            async move {
                let mut guard = UploadTaskGuard {
                    handled: false,
                    cancelled: Arc::clone(&state.upload_handlers_cancelled),
                };
                loop {
                    match request.body_mut().frame().await {
                        Some(Ok(frame)) => {
                            if let Ok(data) = frame.into_data() {
                                state
                                    .upload_bytes_received
                                    .fetch_add(data.len(), Ordering::AcqRel);
                            }
                        }
                        Some(Err(_error)) => {
                            state.upload_body_errors.fetch_add(1, Ordering::AcqRel);
                            guard.handled = true;
                            return Err(NativeRequestError::new(
                                StatusCode::BAD_REQUEST,
                                "request body disconnected",
                            ));
                        }
                        None => {
                            guard.handled = true;
                            break;
                        }
                    }
                }
                json_response(&"upload-complete", StatusCode::OK).map_err(Into::into)
            }
        })
        .route("/stats", ["GET"], move |_request| {
            let state = Arc::clone(&stats_state);
            async move {
                let snapshot = StateSnapshot {
                    backpressure_chunks_polled: state
                        .backpressure_chunks_polled
                        .load(Ordering::Acquire),
                    backpressure_streams_dropped: state
                        .backpressure_streams_dropped
                        .load(Ordering::Acquire),
                    upload_bytes_received: state.upload_bytes_received.load(Ordering::Acquire),
                    upload_body_errors: state.upload_body_errors.load(Ordering::Acquire),
                    upload_handlers_cancelled: state
                        .upload_handlers_cancelled
                        .load(Ordering::Acquire),
                    stream_upload_bytes_received: state
                        .stream_upload_bytes_received
                        .load(Ordering::Acquire),
                    stream_upload_handlers_completed: state
                        .stream_upload_handlers_completed
                        .load(Ordering::Acquire),
                };
                json_response(&snapshot, StatusCode::OK).map_err(Into::into)
            }
        })
        .build()
}

async fn start_server(
    application: NativeApplication,
) -> ProbeResult<(
    SocketAddr,
    oneshot::Sender<()>,
    JoinHandle<Result<(), ServeError>>,
)> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = oneshot::channel::<()>();
    let server = tokio::spawn(async move {
        serve_tcp(
            listener,
            application,
            async move {
                let _ = shutdown_receiver.await;
            },
            ServerConfig {
                graceful_shutdown_timeout: Duration::from_secs(2),
                ..ServerConfig::default()
            },
        )
        .await
    });
    Ok((address, shutdown_sender, server))
}

async fn await_server(server: JoinHandle<Result<(), ServeError>>) -> ProbeResult<()> {
    timeout(Duration::from_secs(3), server).await???;
    Ok(())
}

async fn run_request_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let body = case.get("body").and_then(Value::as_str).map(str::as_bytes);
    let (status, response_body) = match required_str(case, "protocol")? {
        "http/1.1" => http1_request(address, method, path, body).await?,
        "h2c-prior-knowledge" => http2_request(address, method, path, body).await?,
        protocol => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported request protocol {protocol:?}"),
            )
            .into());
        }
    };
    let expected_status = required_u64(case, "expected_status")?;
    let expected_json = case
        .get("expected_json")
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no expected_json"))?;
    let actual_json: Value = serde_json::from_slice(&response_body)?;
    if u64::from(status) != expected_status || &actual_json != expected_json {
        return Err(io::Error::other(format!(
            "{}: expected status/JSON {expected_status}/{expected_json}; got {status}/{actual_json}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn http1_request(
    address: SocketAddr,
    method: &str,
    path: &str,
    body: Option<&[u8]>,
) -> ProbeResult<(u16, Vec<u8>)> {
    let mut stream = TcpStream::connect(address).await?;
    write_http1_request(&mut stream, method, path, body).await?;
    let (status, _headers, response_body) =
        timeout(Duration::from_secs(3), read_http1_response(&mut stream)).await??;
    Ok((status, response_body))
}

async fn http2_request(
    address: SocketAddr,
    method: &str,
    path: &str,
    body: Option<&[u8]>,
) -> ProbeResult<(u16, Vec<u8>)> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let mut request = Request::builder()
        .method(method)
        .uri(format!("http://localhost{path}"));
    if let Some(body) = body {
        request = request.header("content-length", body.len());
    }
    let request = request.body(Full::new(Bytes::copy_from_slice(body.unwrap_or_default())))?;
    let response = sender.send_request(request).await?;
    let status = response.status().as_u16();
    let response_body = response.into_body().collect().await?.to_bytes().to_vec();
    drop(sender);
    driver.abort();
    let _ = driver.await;
    Ok((status, response_body))
}

async fn run_stream_progress_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let mut stream = start_http1_stream(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
    )
    .await?;
    let expected_first = required_str(case, "first_chunk")?.as_bytes();
    let expected_second = required_str(case, "second_chunk")?.as_bytes();
    let first = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "stream ended before first chunk",
        )
    })?;
    if first != expected_first {
        return Err(io::Error::other("first response frame differed from the manifest").into());
    }
    let second = timeout(Duration::from_secs(2), read_next_chunk(&mut stream))
        .await??
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "stream ended before second chunk",
            )
        })?;
    if second != expected_second || read_next_chunk(&mut stream).await?.is_some() {
        return Err(io::Error::other("stream order or final-frame behavior differed").into());
    }
    Ok(())
}

async fn run_upload_disconnect_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let path = required_str(case, "path")?;
    let partial_body = required_str(case, "partial_body")?.as_bytes();
    let declared_length = required_u64(case, "declared_content_length")?;
    if u64::try_from(partial_body.len())
        .ok()
        .is_none_or(|length| length >= declared_length)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "upload body must be shorter than the declared Content-Length",
        )
        .into());
    }

    let mut stream = TcpStream::connect(address).await?;
    let headers = format!(
        "POST {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {declared_length}\r\n\r\n"
    );
    stream.write_all(headers.as_bytes()).await?;
    stream.write_all(partial_body).await?;
    stream.flush().await?;
    stream.shutdown().await?;
    let (status, _headers, _body) =
        timeout(Duration::from_secs(3), read_http1_response(&mut stream)).await??;
    if u64::from(status) != required_u64(case, "expected_status")? {
        return Err(io::Error::other(format!(
            "{}: incomplete upload returned status {status}",
            required_str(case, "id")?
        ))
        .into());
    }

    let expected_errors = usize::try_from(required_u64(case, "expected_body_errors")?)?;
    let expected_cancelled = usize::try_from(required_u64(case, "expected_cancelled_handlers")?)?;
    let state = wait_for_stats(address, |snapshot| {
        snapshot.upload_body_errors == expected_errors
            && snapshot.upload_handlers_cancelled == expected_cancelled
    })
    .await?;
    let expected_bytes = usize::try_from(required_u64(case, "expected_received_bytes")?)?;
    if state.upload_bytes_received != expected_bytes {
        return Err(io::Error::other(format!(
            "{}: observed {} upload bytes, expected {expected_bytes}",
            required_str(case, "id")?,
            state.upload_bytes_received
        ))
        .into());
    }

    let (recovery_status, _recovery_body) = http1_request(address, "GET", "/items/1", None).await?;
    if recovery_status != StatusCode::OK.as_u16() {
        return Err(io::Error::other("server did not recover after request disconnect").into());
    }
    Ok(())
}

async fn run_stream_upload_progress_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let id = required_str(case, "id")?;
    let path = required_str(case, "path")?;
    let first_chunk = required_str(case, "first_chunk")?.as_bytes();
    let remaining_body = required_str(case, "remaining_body")?.as_bytes();
    let body_length = first_chunk
        .len()
        .checked_add(remaining_body.len())
        .ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "request body length overflow")
        })?;
    let declared_length = usize::try_from(required_u64(case, "declared_content_length")?)?;
    let expected_received = usize::try_from(required_u64(case, "expected_received_bytes")?)?;
    if first_chunk.is_empty() || remaining_body.is_empty() || body_length != declared_length {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "streaming upload chunks must be non-empty and match Content-Length",
        )
        .into());
    }

    let baseline = read_stats(address, required_str(case, "stats_path")?).await?;
    let expected_prefix_bytes = baseline
        .stream_upload_bytes_received
        .checked_add(first_chunk.len())
        .ok_or_else(|| io::Error::other("streaming upload byte counter overflow"))?;
    let expected_completed = baseline
        .stream_upload_handlers_completed
        .checked_add(1)
        .ok_or_else(|| io::Error::other("streaming upload completion counter overflow"))?;
    let expected_total_bytes = baseline
        .stream_upload_bytes_received
        .checked_add(expected_received)
        .ok_or_else(|| io::Error::other("streaming upload byte counter overflow"))?;

    let mut stream = TcpStream::connect(address).await?;
    let headers = format!(
        "POST {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {declared_length}\r\n\r\n"
    );
    stream.write_all(headers.as_bytes()).await?;
    stream.write_all(first_chunk).await?;
    stream.flush().await?;

    let prefix_state = wait_for_stats(address, |snapshot| {
        snapshot.stream_upload_bytes_received == expected_prefix_bytes
            && snapshot.stream_upload_handlers_completed
                == baseline.stream_upload_handlers_completed
    })
    .await?;
    if prefix_state.stream_upload_handlers_completed != baseline.stream_upload_handlers_completed {
        return Err(
            io::Error::other("upload handler completed before the body suffix arrived").into(),
        );
    }

    stream.write_all(remaining_body).await?;
    stream.flush().await?;
    // Content-Length completes the request body; keep the read side open for
    // the server response instead of introducing an unrelated write-half EOF.
    let response = timeout(Duration::from_secs(3), read_http1_response(&mut stream))
        .await
        .map_err(|error| io::Error::new(io::ErrorKind::TimedOut, error))?;
    let (status, _headers, response_body) = response.map_err(|error| {
        io::Error::other(format!(
            "{id}: failed to read the response after the remaining upload bytes were sent: {error}"
        ))
    })?;
    if u64::from(status) != required_u64(case, "expected_status")? {
        return Err(
            io::Error::other(format!("{id}: streamed upload returned HTTP {status}")).into(),
        );
    }
    let response_bytes: usize = serde_json::from_slice(&response_body)?;
    if response_bytes != expected_received || response_bytes != body_length {
        return Err(io::Error::other(format!(
            "{id}: handler counted {response_bytes} body bytes, expected {expected_received}"
        ))
        .into());
    }

    let completed_state = wait_for_stats(address, |snapshot| {
        snapshot.stream_upload_bytes_received == expected_total_bytes
            && snapshot.stream_upload_handlers_completed == expected_completed
    })
    .await?;
    if completed_state.stream_upload_bytes_received != expected_total_bytes {
        return Err(
            io::Error::other("streaming upload byte counter differed after completion").into(),
        );
    }
    Ok(())
}

async fn run_http2_upload_reset_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let stats_path = required_str(case, "stats_path")?;
    let baseline = read_stats(address, stats_path).await?;
    let partial_body = required_str(case, "partial_body")?.as_bytes();
    let declared_length = required_u64(case, "declared_content_length")?;
    if u64::try_from(partial_body.len())
        .ok()
        .is_none_or(|length| length >= declared_length)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "HTTP/2 upload prefix must be shorter than the declared Content-Length",
        )
        .into());
    }

    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) = h2::client::handshake(socket).await?;
    let driver = tokio::spawn(connection);
    let request = Request::builder()
        .method("POST")
        .uri(format!("http://localhost{}", required_str(case, "path")?))
        .header("host", "localhost")
        .header("content-length", declared_length)
        .body(())?;
    let (response, mut body_sender) = sender.send_request(request, false)?;
    body_sender.send_data(Bytes::copy_from_slice(partial_body), false)?;

    let expected_bytes = baseline
        .upload_bytes_received
        .saturating_add(usize::try_from(required_u64(
            case,
            "expected_received_bytes",
        )?)?);
    let received_prefix = wait_for_stats(address, |snapshot| {
        snapshot.upload_bytes_received == expected_bytes
            && snapshot.upload_body_errors == baseline.upload_body_errors
    })
    .await?;
    if received_prefix.upload_handlers_cancelled != baseline.upload_handlers_cancelled {
        return Err(io::Error::other(
            "HTTP/2 upload handler stopped before the client reset the stream",
        )
        .into());
    }

    body_sender.send_reset(h2::Reason::CANCEL);
    if let Ok(Ok(response)) = timeout(Duration::from_secs(2), response).await {
        let mut response_body = response.into_body();
        while let Some(data) = timeout(Duration::from_secs(2), response_body.data()).await? {
            let _ = data?;
        }
    }

    let expected_body_errors =
        baseline
            .upload_body_errors
            .saturating_add(usize::try_from(required_u64(
                case,
                "expected_body_error_delta",
            )?)?);
    let expected_cancelled = baseline
        .upload_handlers_cancelled
        .saturating_add(usize::try_from(required_u64(
            case,
            "expected_cancelled_handlers_delta",
        )?)?);
    let state = wait_for_stats(address, |snapshot| {
        snapshot.upload_bytes_received == expected_bytes
            && snapshot.upload_body_errors == expected_body_errors
            && snapshot.upload_handlers_cancelled == expected_cancelled
    })
    .await?;
    if state.upload_handlers_cancelled != baseline.upload_handlers_cancelled {
        return Err(io::Error::other(
            "HTTP/2 upload reset cancelled the handler instead of delivering a body error",
        )
        .into());
    }

    let recovery = Request::builder()
        .method("GET")
        .uri(format!(
            "http://localhost{}",
            required_str(case, "recovery_path")?
        ))
        .header("host", "localhost")
        .body(())?;
    let (recovery_response, _request_body) = sender.send_request(recovery, true)?;
    let recovery_response = timeout(Duration::from_secs(3), recovery_response).await??;
    let recovery_status = recovery_response.status();
    let mut recovery_body = recovery_response.into_body();
    let mut received = Vec::new();
    while let Some(data) = timeout(Duration::from_secs(3), recovery_body.data()).await? {
        received.extend_from_slice(&data?);
    }
    let actual_json: Value = serde_json::from_slice(&received)?;
    let expected_json = case.get("expected_recovery_json").ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_recovery_json",
        )
    })?;
    if recovery_status != StatusCode::OK || &actual_json != expected_json {
        return Err(io::Error::other(format!(
            "{}: same-connection recovery expected HTTP 200/{expected_json}; got {recovery_status}/{actual_json}",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(sender);
    driver.abort();
    let _ = driver.await;
    Ok(())
}

async fn run_http2_stream_upload_progress_case(
    address: SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let id = required_str(case, "id")?;
    let first_chunk = required_str(case, "first_chunk")?.as_bytes();
    let remaining_body = required_str(case, "remaining_body")?.as_bytes();
    let body_length = first_chunk
        .len()
        .checked_add(remaining_body.len())
        .ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "request body length overflow")
        })?;
    let declared_length = usize::try_from(required_u64(case, "declared_content_length")?)?;
    let expected_received = usize::try_from(required_u64(case, "expected_received_bytes")?)?;
    if first_chunk.is_empty() || remaining_body.is_empty() || body_length != declared_length {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "HTTP/2 streaming upload chunks must be non-empty and match Content-Length",
        )
        .into());
    }

    let baseline = read_stats(address, required_str(case, "stats_path")?).await?;
    let expected_prefix_bytes = baseline
        .stream_upload_bytes_received
        .checked_add(first_chunk.len())
        .ok_or_else(|| io::Error::other("streaming upload byte counter overflow"))?;
    let expected_completed = baseline
        .stream_upload_handlers_completed
        .checked_add(1)
        .ok_or_else(|| io::Error::other("streaming upload completion counter overflow"))?;
    let expected_total_bytes = baseline
        .stream_upload_bytes_received
        .checked_add(expected_received)
        .ok_or_else(|| io::Error::other("streaming upload byte counter overflow"))?;

    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) = h2::client::handshake(socket).await?;
    let driver = tokio::spawn(connection);
    let request = Request::builder()
        .method("POST")
        .uri(format!("http://localhost{}", required_str(case, "path")?))
        .header("host", "localhost")
        .header("content-length", declared_length)
        .body(())?;
    let (response, mut body_sender) = sender.send_request(request, false)?;
    body_sender.send_data(Bytes::copy_from_slice(first_chunk), false)?;

    let prefix_state = wait_for_stats(address, |snapshot| {
        snapshot.stream_upload_bytes_received == expected_prefix_bytes
            && snapshot.stream_upload_handlers_completed
                == baseline.stream_upload_handlers_completed
    })
    .await?;
    if prefix_state.stream_upload_handlers_completed != baseline.stream_upload_handlers_completed {
        return Err(io::Error::other(
            "HTTP/2 upload handler completed before the body suffix arrived",
        )
        .into());
    }

    body_sender.send_data(Bytes::copy_from_slice(remaining_body), true)?;
    let response = timeout(Duration::from_secs(3), response).await??;
    let status = response.status();
    let mut response_body = response.into_body();
    let mut received_body = Vec::new();
    while let Some(data) = timeout(Duration::from_secs(3), response_body.data()).await? {
        received_body.extend_from_slice(&data?);
    }
    if u64::from(status.as_u16()) != required_u64(case, "expected_status")? {
        return Err(io::Error::other(format!(
            "{id}: streamed HTTP/2 upload returned HTTP {status}"
        ))
        .into());
    }
    let response_bytes: usize = serde_json::from_slice(&received_body)?;
    if response_bytes != expected_received || response_bytes != body_length {
        return Err(io::Error::other(format!(
            "{id}: handler counted {response_bytes} body bytes, expected {expected_received}"
        ))
        .into());
    }

    let completed_state = wait_for_stats(address, |snapshot| {
        snapshot.stream_upload_bytes_received == expected_total_bytes
            && snapshot.stream_upload_handlers_completed == expected_completed
    })
    .await?;
    if completed_state.stream_upload_bytes_received != expected_total_bytes {
        return Err(io::Error::other(
            "HTTP/2 streaming upload byte counter differed after completion",
        )
        .into());
    }

    drop(sender);
    driver.abort();
    let _ = driver.await;
    Ok(())
}

async fn run_backpressure_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let protocol = required_str(case, "protocol")?;
    let total_chunks = usize::try_from(required_u64(case, "total_chunks")?)?;
    let max_polled_chunks = usize::try_from(required_u64(case, "max_polled_chunks")?)?;
    if total_chunks <= max_polled_chunks {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "backpressure workload must exceed its polling bound",
        )
        .into());
    }
    let baseline = read_stats(address, required_str(case, "stats_path")?).await?;
    match protocol {
        "http/1.1" => run_http1_backpressure(address, case, &baseline).await?,
        "h2c-prior-knowledge" => run_http2_backpressure(address, case, &baseline).await?,
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported backpressure protocol {other:?}"),
            )
            .into());
        }
    }
    Ok(())
}

async fn run_http1_backpressure(
    address: SocketAddr,
    case: &Value,
    baseline: &StateSnapshot,
) -> ProbeResult<()> {
    let mut stream = start_http1_stream(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
    )
    .await?;
    let first = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "backpressure stream had no first chunk",
        )
    })?;
    if first.len() != usize::try_from(required_u64(case, "chunk_size")?)? {
        return Err(io::Error::other("backpressure stream chunk size differed").into());
    }
    observe_backpressure(address, case, baseline).await?;
    drop(stream);
    wait_for_stream_drop(address, case, baseline).await
}

async fn run_http2_backpressure(
    address: SocketAddr,
    case: &Value,
    baseline: &StateSnapshot,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let path = required_str(case, "path")?;
    let request = Request::builder()
        .method(required_str(case, "method")?)
        .uri(format!("http://localhost{path}"))
        .body(Full::new(Bytes::new()))?;
    let response = sender.send_request(request).await?;
    if response.status() != StatusCode::OK {
        return Err(io::Error::other("HTTP/2 backpressure response was not 200").into());
    }
    let mut body = response.into_body();
    let first = timeout(Duration::from_secs(2), body.frame())
        .await?
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "HTTP/2 stream had no first frame",
            )
        })??
        .into_data()
        .map_err(|_| io::Error::other("HTTP/2 stream began with a non-data frame"))?;
    if first.is_empty() {
        return Err(io::Error::other("HTTP/2 stream's first data frame was empty").into());
    }
    observe_backpressure(address, case, baseline).await?;
    drop(body);
    drop(sender);
    driver.abort();
    let _ = driver.await;
    wait_for_stream_drop(address, case, baseline).await
}

async fn observe_backpressure(
    address: SocketAddr,
    case: &Value,
    baseline: &StateSnapshot,
) -> ProbeResult<()> {
    tokio::time::sleep(Duration::from_millis(required_u64(
        case,
        "observe_delay_ms",
    )?))
    .await;
    let after = read_stats(address, required_str(case, "stats_path")?).await?;
    let polled = after
        .backpressure_chunks_polled
        .saturating_sub(baseline.backpressure_chunks_polled);
    let max_polled = usize::try_from(required_u64(case, "max_polled_chunks")?)?;
    let dropped = after
        .backpressure_streams_dropped
        .saturating_sub(baseline.backpressure_streams_dropped);
    if polled == 0 || polled >= max_polled || dropped != 0 {
        return Err(io::Error::other(format!(
            "{}: slow reader observed {polled} polled frames and {dropped} drops before disconnect",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn wait_for_stream_drop(
    address: SocketAddr,
    case: &Value,
    baseline: &StateSnapshot,
) -> ProbeResult<()> {
    let expected = usize::try_from(required_u64(case, "expected_dropped_streams")?)?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let snapshot = read_stats(address, required_str(case, "stats_path")?).await?;
        let dropped = snapshot
            .backpressure_streams_dropped
            .saturating_sub(baseline.backpressure_streams_dropped);
        if dropped == expected {
            return Ok(());
        }
        if dropped > expected || Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: response producer drop was not observed",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

async fn wait_for_stats(
    address: SocketAddr,
    predicate: impl Fn(&StateSnapshot) -> bool,
) -> ProbeResult<StateSnapshot> {
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let snapshot = read_stats(address, "/stats").await?;
        if predicate(&snapshot) {
            return Ok(snapshot);
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "application state did not reach the expected upload outcome",
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

async fn read_stats(address: SocketAddr, path: &str) -> ProbeResult<StateSnapshot> {
    let (status, body) = http1_request(address, "GET", path, None).await?;
    if status != StatusCode::OK.as_u16() {
        return Err(io::Error::other(format!("state request returned HTTP {status}")).into());
    }
    Ok(serde_json::from_slice(&body)?)
}

async fn run_graceful_drain_case(
    address: SocketAddr,
    case: &Value,
    shutdown_sender: oneshot::Sender<()>,
    server: JoinHandle<Result<(), ServeError>>,
) -> ProbeResult<()> {
    let mut stream = start_http1_stream(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
    )
    .await?;
    let first = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "drain stream ended before first chunk",
        )
    })?;
    if first != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other("graceful drain first chunk differed").into());
    }
    let _ = shutdown_sender.send(());
    let second = timeout(Duration::from_secs(2), read_next_chunk(&mut stream))
        .await??
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "drain stream ended before second chunk",
            )
        })?;
    if second != required_str(case, "second_chunk")?.as_bytes()
        || timeout(Duration::from_secs(2), read_next_chunk(&mut stream))
            .await??
            .is_some()
    {
        return Err(io::Error::other(
            "graceful shutdown did not drain exactly two response frames",
        )
        .into());
    }
    drop(stream);
    await_server(server).await
}

async fn run_http2_graceful_drain_case(
    address: SocketAddr,
    case: &Value,
    shutdown_sender: oneshot::Sender<()>,
    server: JoinHandle<Result<(), ServeError>>,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) = h2::client::handshake(socket).await?;
    let driver = tokio::spawn(connection);
    let request = Request::builder()
        .method(required_str(case, "method")?)
        .uri(format!("http://localhost{}", required_str(case, "path")?))
        .header("host", "localhost")
        .body(())?;
    let (response, _request_body) = sender.send_request(request, true)?;
    let response = timeout(Duration::from_secs(2), response).await??;
    if response.status() != StatusCode::OK {
        return Err(io::Error::other(format!(
            "{}: active HTTP/2 response returned {}",
            required_str(case, "id")?,
            response.status()
        ))
        .into());
    }
    let mut body = response.into_body();
    let first = timeout(Duration::from_secs(2), body.data())
        .await?
        .ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "H2 drain ended early"))??;
    if first.as_ref() != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other("HTTP/2 graceful-drain first frame differed").into());
    }

    let _ = shutdown_sender.send(());
    let second = timeout(Duration::from_secs(2), body.data())
        .await?
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "HTTP/2 graceful shutdown did not drain the active response",
            )
        })??;
    if second.as_ref() != required_str(case, "second_chunk")?.as_bytes() {
        return Err(io::Error::other("HTTP/2 graceful-drain second frame differed").into());
    }
    loop {
        match timeout(Duration::from_secs(2), body.data()).await? {
            Some(Ok(data)) if data.is_empty() => {}
            Some(Ok(_)) => {
                return Err(io::Error::other(
                    "HTTP/2 graceful shutdown produced an unexpected trailing data frame",
                )
                .into());
            }
            Some(Err(error)) => return Err(error.into()),
            None => break,
        }
    }
    if timeout(Duration::from_secs(2), body.trailers())
        .await??
        .is_some()
    {
        return Err(
            io::Error::other("HTTP/2 graceful shutdown produced unexpected trailers").into(),
        );
    }

    drop(body);
    drop(sender);
    driver.abort();
    let _ = driver.await;
    await_server(server).await
}

async fn start_http1_stream(
    address: SocketAddr,
    method: &str,
    path: &str,
) -> ProbeResult<TcpStream> {
    let mut stream = TcpStream::connect(address).await?;
    write_http1_request(&mut stream, method, path, None).await?;
    let (status, headers) = read_http1_head(&mut stream).await?;
    if status != StatusCode::OK.as_u16()
        || !headers
            .get("transfer-encoding")
            .is_some_and(|value| value.eq_ignore_ascii_case("chunked"))
    {
        return Err(io::Error::other(format!(
            "expected a chunked HTTP/1.1 200 stream; got status {status} and headers {headers:?}"
        ))
        .into());
    }
    Ok(stream)
}

async fn write_http1_request(
    stream: &mut TcpStream,
    method: &str,
    path: &str,
    body: Option<&[u8]>,
) -> ProbeResult<()> {
    let mut request =
        format!("{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n");
    if let Some(body) = body {
        request.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    request.push_str("\r\n");
    stream.write_all(request.as_bytes()).await?;
    if let Some(body) = body {
        stream.write_all(body).await?;
    }
    stream.flush().await?;
    Ok(())
}

async fn read_http1_response(
    stream: &mut TcpStream,
) -> ProbeResult<(u16, std::collections::HashMap<String, String>, Vec<u8>)> {
    let (status, headers) = read_http1_head(stream).await?;
    let body = if headers
        .get("transfer-encoding")
        .is_some_and(|value| value.eq_ignore_ascii_case("chunked"))
    {
        let mut body = Vec::new();
        while let Some(chunk) = read_next_chunk(stream).await.map_err(|error| {
            io::Error::other(format!(
                "chunked response failed after {} bytes (status {status}, headers {headers:?}): {error}",
                body.len()
            ))
        })? {
            body.extend_from_slice(&chunk);
        }
        body
    } else if let Some(length) = headers.get("content-length") {
        let length = length.parse::<usize>()?;
        let mut body = vec![0; length];
        stream.read_exact(&mut body).await.map_err(|error| {
            io::Error::new(
                error.kind(),
                format!("response ended before its declared {length}-byte body: {error}"),
            )
        })?;
        body
    } else {
        let mut body = Vec::new();
        stream.read_to_end(&mut body).await?;
        body
    };
    Ok((status, headers, body))
}

async fn read_http1_head(
    stream: &mut TcpStream,
) -> ProbeResult<(u16, std::collections::HashMap<String, String>)> {
    let status_line = read_crlf_line(stream).await?;
    let status = std::str::from_utf8(&status_line)?
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "HTTP response had no status"))?
        .parse::<u16>()?;
    let mut headers = std::collections::HashMap::new();
    loop {
        let line = read_crlf_line(stream).await?;
        if line.is_empty() {
            break;
        }
        let line = std::str::from_utf8(&line)?;
        let (name, value) = line.split_once(':').ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "malformed HTTP response header")
        })?;
        headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_owned());
    }
    Ok((status, headers))
}

async fn read_next_chunk(stream: &mut TcpStream) -> ProbeResult<Option<Vec<u8>>> {
    let line = read_crlf_line(stream).await?;
    let size_text = std::str::from_utf8(&line)?
        .split(';')
        .next()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "missing HTTP chunk size"))?;
    let size = usize::from_str_radix(size_text.trim(), 16)?;
    if size == 0 {
        loop {
            if read_crlf_line(stream).await?.is_empty() {
                break;
            }
        }
        return Ok(None);
    }
    let mut data = vec![0; size];
    stream.read_exact(&mut data).await?;
    let mut terminator = [0; 2];
    stream.read_exact(&mut terminator).await?;
    if terminator != *b"\r\n" {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "invalid chunk terminator").into());
    }
    Ok(Some(data))
}

async fn read_crlf_line(stream: &mut TcpStream) -> ProbeResult<Vec<u8>> {
    let mut line = Vec::new();
    loop {
        let mut byte = [0; 1];
        stream.read_exact(&mut byte).await?;
        line.push(byte[0]);
        if line.ends_with(b"\r\n") {
            line.truncate(line.len().saturating_sub(2));
            return Ok(line);
        }
        if line.len() > 64 * 1024 {
            return Err(
                io::Error::new(io::ErrorKind::InvalidData, "HTTP line exceeded 64 KiB").into(),
            );
        }
    }
}

fn required_str<'a>(value: &'a Value, key: &str) -> ProbeResult<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("case has no {key}")))
        .map_err(Into::into)
}

fn required_u64(value: &Value, key: &str) -> ProbeResult<u64> {
    value
        .get(key)
        .and_then(Value::as_u64)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("case has no {key}")))
        .map_err(Into::into)
}

fn backpressure_config(manifest: &Manifest) -> ProbeResult<(usize, usize)> {
    let mut config = None;
    for case in &manifest.cases {
        if case.get("operation").and_then(Value::as_str) != Some("response-backpressure") {
            continue;
        }
        let current = (
            usize::try_from(required_u64(case, "chunk_size")?)?,
            usize::try_from(required_u64(case, "total_chunks")?)?,
        );
        if let Some(previous) = config {
            if previous != current {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "backpressure cases must share one application stream configuration",
                )
                .into());
            }
        }
        config = Some(current);
    }
    config.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "manifest has no response-backpressure input",
        )
        .into()
    })
}
