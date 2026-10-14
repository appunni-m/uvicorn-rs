//! Runs input-driven, black-box contracts against the Python-free server API.
//!
//! This is an executable probe rather than a unit-test target. Cases observe
//! real TCP, TLS, and QUIC workflows or public server-API results.

use std::{
    error::Error,
    future::Future,
    io::{self, Write as _},
    net::SocketAddr,
    pin::Pin,
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Arc, Condvar, Mutex,
    },
    task::{Context, Poll, Waker},
    time::Duration,
};

use bytes::{Buf, Bytes};
use futures_util::{stream, SinkExt, StreamExt};
use h3::error::Code;
use h3_quinn::quinn::{self, rustls as quic_rustls};
use http::{
    header::{SEC_WEBSOCKET_ACCEPT, SEC_WEBSOCKET_VERSION},
    HeaderName, HeaderValue, Method, Request, Response, StatusCode,
};
use http_body::{Body, SizeHint};
use http_body_util::{combinators::UnsyncBoxBody, BodyExt, Empty, Full, StreamBody};
use hyper_util::rt::{TokioExecutor, TokioIo};
use serde_json::Value;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::watch,
    time::{sleep, timeout, Instant},
};
use tokio_rustls::{
    rustls::{self, pki_types::ServerName},
    TlsAcceptor, TlsConnector,
};
use tower_service::Service;
use uvicorn_rs::{
    ApplicationLifecycle, ApplicationLifecycleError, ApplicationLifecycleFuture,
    ApplicationLifecycleStage, ConnectionInfo, ConnectionLifetime, ConnectionUpgrade,
    PeerReadHalfClosed, RequestEndReason, RequestLifetime, ServerErrorEvent, ServerErrorObserver,
    ServerErrorPhase, TransportKind, WebSocketCloseCode, WebSocketCloseFrame, WebSocketError,
    WebSocketMessage, WebSocketSession, WebSocketUpgrade, WebSocketUpgradeError,
};

type AppBody = UnsyncBoxBody<Bytes, io::Error>;
type AppFuture = Pin<Box<dyn Future<Output = Result<Response<AppBody>, io::Error>> + Send>>;
type ProbeResult<T> = Result<T, Box<dyn Error + Send + Sync>>;
type ShutdownSignal = Pin<Box<dyn Future<Output = ()> + Send>>;

trait AsyncReadWrite: AsyncRead + AsyncWrite {}

impl<T> AsyncReadWrite for T where T: AsyncRead + AsyncWrite {}

type BoxedIo = Box<dyn AsyncReadWrite + Send + Unpin>;

fn shutdown_on_change(mut receiver: watch::Receiver<bool>) -> ShutdownSignal {
    Box::pin(async move {
        let _ = receiver.changed().await;
    })
}

#[derive(Clone, Debug)]
struct ObservedServerError {
    phase: ServerErrorPhase,
    peer_addr: Option<SocketAddr>,
    is_io_error: bool,
    is_direct_io_error: bool,
    has_error_source: bool,
    h3_error_code: Option<u64>,
    message: String,
}

#[derive(Clone)]
struct ContractApp {
    state: Arc<AppState>,
}

struct AppState {
    fail_next_readiness: AtomicBool,
    panic_next_readiness: AtomicBool,
    readiness_gate: Mutex<ReadinessGate>,
    stream_complete: AtomicBool,
    graceful_timeout_stream_drops: Arc<AtomicUsize>,
    cancelled_streams: Arc<AtomicUsize>,
    cancelled_h2_streams: Arc<AtomicUsize>,
    http3_cancelled_streams: Arc<AtomicUsize>,
    request_lifetime_waiters: AtomicUsize,
    request_lifetime_reason_checks: Arc<AtomicUsize>,
    request_future_drops: Arc<AtomicUsize>,
    request_ends_while_connection_open: Arc<AtomicUsize>,
    request_connections_closed: Arc<AtomicUsize>,
    request_lifetime_peer_eof_available: Arc<AtomicBool>,
    request_lifetime_peer_eof: Arc<AtomicBool>,
    peer_write_half_close_started: AtomicBool,
    peer_write_half_close_release: watch::Sender<bool>,
    peer_read_half_close_observation: watch::Sender<Option<String>>,
    peer_read_half_close_unavailable_result: watch::Sender<Option<String>>,
    response_chunks_polled: Arc<AtomicUsize>,
    response_streams_dropped: Arc<AtomicUsize>,
    upload_bytes_received: AtomicUsize,
    upload_body_errors: AtomicUsize,
    http3_body_pending: AtomicBool,
    http3_body_errors: AtomicUsize,
    http3_response_cancel_pending: AtomicBool,
    http3_response_cancel_waiters: AtomicUsize,
    http3_response_cancel_release: watch::Sender<bool>,
    upload_tasks_dropped: Arc<AtomicUsize>,
    shutdown: watch::Sender<bool>,
    upgrade_registration_outcome: watch::Sender<Option<String>>,
    websocket_error_observation: watch::Sender<Option<String>>,
}

enum UpgradeSessionBehavior {
    Graceful(ConnectionLifetime),
    HandlerError,
    HandlerPanic,
}

#[derive(Default)]
struct ReadinessGate {
    armed: bool,
    waiting: bool,
    released: bool,
    wake_started: bool,
    pending_polls: usize,
    wakers: Vec<Waker>,
}

#[derive(Clone)]
struct TlsClients {
    http1: TlsConnector,
    http2: TlsConnector,
    http3: quinn::ClientConfig,
    http3_non_h3: quinn::ClientConfig,
}

#[derive(Clone)]
struct LifecycleApp {
    state: Arc<LifecycleState>,
}

struct LifecycleState {
    startup_completed: AtomicBool,
    shutdown_completed: AtomicBool,
    startup_hook_dropped: Arc<AtomicBool>,
    shutdown_hook_dropped: Arc<AtomicBool>,
    requests_started: AtomicUsize,
    http3_response_cancel_pending: AtomicBool,
    http3_response_cancel_release: watch::Sender<bool>,
    readiness_error_armed: AtomicBool,
    readiness_gate: Mutex<ReadinessGate>,
    response_body_dropped: Arc<AtomicBool>,
    shutdown_saw_response_body_drop: AtomicBool,
    active_request: watch::Sender<bool>,
    release_request: watch::Sender<bool>,
    events: Mutex<Vec<&'static str>>,
    observed_lifecycle_errors: Mutex<Vec<(ServerErrorPhase, String, bool)>>,
    readiness_errors: Mutex<Vec<(ServerErrorPhase, bool, String)>>,
    application_errors: Mutex<Vec<(ServerErrorPhase, bool, String)>>,
    connection_errors: Mutex<Vec<(ServerErrorPhase, Option<SocketAddr>)>>,
}

struct LifecycleHooks {
    state: Arc<LifecycleState>,
    startup_behavior: LifecycleHookBehavior,
    shutdown_behavior: LifecycleHookBehavior,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum LifecycleHookBehavior {
    Complete,
    Fail,
    Panic,
    Wait,
}

struct HookCancellationSignal(Arc<AtomicBool>);

struct LifecycleBody {
    inner: Pin<Box<dyn Body<Data = Bytes, Error = io::Error> + Send>>,
    drop_flag: Option<Arc<AtomicBool>>,
}

struct LifecycleFixture {
    app: LifecycleApp,
    hooks: Arc<LifecycleHooks>,
    state: Arc<LifecycleState>,
    shutdown_sender: watch::Sender<bool>,
    shutdown_receiver: watch::Receiver<bool>,
}

struct DropSignal(Arc<AtomicUsize>);

impl Drop for DropSignal {
    fn drop(&mut self) {
        self.0.fetch_add(1, Ordering::AcqRel);
    }
}

impl Drop for HookCancellationSignal {
    fn drop(&mut self) {
        self.0.store(true, Ordering::Release);
    }
}

impl ApplicationLifecycle for LifecycleHooks {
    fn startup(&self) -> ApplicationLifecycleFuture<'_> {
        let state = Arc::clone(&self.state);
        let behavior = self.startup_behavior;
        let dropped = Arc::clone(&state.startup_hook_dropped);
        Box::pin(async move {
            record_lifecycle_event(&state, "startup")?;
            if behavior == LifecycleHookBehavior::Wait {
                let _signal = HookCancellationSignal(dropped);
                std::future::pending::<()>().await;
            }
            if behavior == LifecycleHookBehavior::Panic {
                inject_native_contract_panic("injected lifecycle startup panic");
            }
            if behavior == LifecycleHookBehavior::Fail {
                return Err(
                    Box::new(io::Error::other("injected lifecycle startup failure"))
                        as ApplicationLifecycleError,
                );
            }
            state.startup_completed.store(true, Ordering::Release);
            Ok(())
        })
    }

    fn shutdown(&self) -> ApplicationLifecycleFuture<'_> {
        let state = Arc::clone(&self.state);
        let behavior = self.shutdown_behavior;
        let dropped = Arc::clone(&state.shutdown_hook_dropped);
        Box::pin(async move {
            record_lifecycle_event(&state, "shutdown")?;
            if behavior == LifecycleHookBehavior::Wait {
                let _signal = HookCancellationSignal(dropped);
                std::future::pending::<()>().await;
            }
            if behavior == LifecycleHookBehavior::Panic {
                inject_native_contract_panic("injected lifecycle shutdown panic");
            }
            if behavior == LifecycleHookBehavior::Fail {
                return Err(
                    Box::new(io::Error::other("injected lifecycle shutdown failure"))
                        as ApplicationLifecycleError,
                );
            }
            let response_body_dropped = state.response_body_dropped.load(Ordering::Acquire);
            state
                .shutdown_saw_response_body_drop
                .store(response_body_dropped, Ordering::Release);
            state.shutdown_completed.store(true, Ordering::Release);
            Ok(())
        })
    }
}

fn inject_native_contract_panic(message: &str) -> ! {
    std::panic::resume_unwind(Box::new(message.to_owned()));
}

impl<B> Service<Request<B>> for LifecycleApp {
    type Response = Response<LifecycleBody>;
    type Error = io::Error;
    type Future = AppFutureLifecycle;

    fn poll_ready(&mut self, context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        if self
            .state
            .readiness_error_armed
            .swap(false, Ordering::AcqRel)
        {
            return Poll::Ready(Err(io::Error::other(
                "injected lifecycle readiness failure",
            )));
        }
        let mut readiness = match self.state.readiness_gate.lock() {
            Ok(readiness) => readiness,
            Err(_) => {
                return Poll::Ready(Err(io::Error::other(
                    "lifecycle readiness state was poisoned",
                )));
            }
        };
        if readiness.armed {
            readiness.armed = false;
            readiness.waiting = true;
            readiness.released = false;
            readiness.wake_started = false;
            readiness.pending_polls = 0;
            readiness.wakers.clear();
        }
        if readiness.waiting && !readiness.released {
            readiness.pending_polls = readiness.pending_polls.saturating_add(1);
            readiness.wakers.push(context.waker().clone());
            if !readiness.wake_started {
                readiness.wake_started = true;
                let state = Arc::clone(&self.state);
                let _wake_task = tokio::spawn(async move {
                    tokio::time::sleep(Duration::from_millis(40)).await;
                    let wakers = match state.readiness_gate.lock() {
                        Ok(mut readiness) => {
                            readiness.waiting = false;
                            readiness.released = true;
                            readiness.wake_started = false;
                            std::mem::take(&mut readiness.wakers)
                        }
                        Err(_) => return,
                    };
                    for waker in wakers {
                        waker.wake();
                    }
                });
            }
            return Poll::Pending;
        }
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, mut request: Request<B>) -> Self::Future {
        let path = request.uri().path().to_owned();
        let websocket_upgrade = (path == "/lifecycle-websocket").then(|| {
            WebSocketUpgrade::from_request(&mut request)
                .map_err(|error| io::Error::other(error.to_string()))
        });
        drop(request);
        let state = Arc::clone(&self.state);
        Box::pin(async move {
            state.requests_started.fetch_add(1, Ordering::AcqRel);
            if !state.startup_completed.load(Ordering::Acquire) {
                return Err(io::Error::other("request reached service before startup"));
            }
            let readiness_pending = {
                let readiness = state
                    .readiness_gate
                    .lock()
                    .map_err(|_| io::Error::other("lifecycle readiness state was poisoned"))?;
                readiness.pending_polls > 0 && !readiness.released
            };
            if readiness_pending {
                return Err(io::Error::other(
                    "request reached lifecycle service before readiness recovered",
                ));
            }
            match path.as_str() {
                "/arm-readiness-error" => {
                    state.readiness_error_armed.store(true, Ordering::Release);
                    lifecycle_response(b"armed\n", None)
                }
                "/service-error" => Err(io::Error::other("injected lifecycle service error")),
                "/body-error" => {
                    let body = stream::unfold(0_u8, |step| async move {
                        match step {
                            0 => Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"partial\n"))),
                                1,
                            )),
                            1 => {
                                tokio::time::sleep(Duration::from_millis(30)).await;
                                Some((
                                    Err(io::Error::other("injected lifecycle response body error")),
                                    2,
                                ))
                            }
                            _ => None,
                        }
                    });
                    let body = LifecycleBody {
                        inner: Box::pin(StreamBody::new(body)),
                        drop_flag: Some(Arc::clone(&state.response_body_dropped)),
                    };
                    Response::builder()
                        .status(StatusCode::OK)
                        .body(body)
                        .map_err(|error| io::Error::other(error.to_string()))
                }
                "/ready" => lifecycle_response(b"started\n", None),
                "/lifecycle-websocket" => {
                    let upgrade = websocket_upgrade
                        .ok_or_else(|| io::Error::other("WebSocket request was not prepared"))??;
                    let body = lifecycle_response(b"", None)?.into_body();
                    upgrade
                        .accept(body, |mut session| async move {
                            while let Some(message) = session.receive().await? {
                                match message {
                                    WebSocketMessage::Text(text) => {
                                        session.send(WebSocketMessage::Text(text)).await?;
                                    }
                                    WebSocketMessage::Close(_) => break,
                                    _ => {}
                                }
                            }
                            Ok::<(), WebSocketError>(())
                        })
                        .map_err(|error| io::Error::other(error.to_string()))
                }
                "/http3-response-cancel-pending" => lifecycle_response(
                    if state.http3_response_cancel_pending.load(Ordering::Acquire) {
                        b"waiting\n"
                    } else {
                        b"ready\n"
                    },
                    None,
                ),
                "/http3-response-cancel-release" => {
                    state
                        .http3_response_cancel_pending
                        .store(false, Ordering::Release);
                    state.http3_response_cancel_release.send_replace(true);
                    lifecycle_response(b"released\n", None)
                }
                "/http3-response-hold-before-headers" => {
                    let mut release = state.http3_response_cancel_release.subscribe();
                    state
                        .http3_response_cancel_pending
                        .store(true, Ordering::Release);
                    while !*release.borrow_and_update() {
                        release.changed().await.map_err(|_| {
                            io::Error::other("HTTP/3 response release channel closed")
                        })?;
                    }
                    state
                        .http3_response_cancel_pending
                        .store(false, Ordering::Release);
                    lifecycle_response(b"released response\n", None)
                }
                "/http3-response-hold-before-trailers" => {
                    let release = state.http3_response_cancel_release.subscribe();
                    let response_state = Arc::clone(&state);
                    let body = stream::unfold(
                        (0_u8, release, response_state),
                        |(step, mut release, response_state)| async move {
                            match step {
                                0 => Some((
                                    Ok(http_body::Frame::data(Bytes::from_static(
                                        b"before-trailers\n",
                                    ))),
                                    (1, release, response_state),
                                )),
                                1 => {
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(true, Ordering::Release);
                                    while !*release.borrow_and_update() {
                                        if release.changed().await.is_err() {
                                            response_state
                                                .http3_response_cancel_pending
                                                .store(false, Ordering::Release);
                                            return Some((
                                                Err(io::Error::other(
                                                    "HTTP/3 trailer release channel closed",
                                                )),
                                                (2, release, response_state),
                                            ));
                                        }
                                    }
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(false, Ordering::Release);
                                    let mut trailers = http::HeaderMap::new();
                                    let value = match http::HeaderValue::from_bytes(b"complete") {
                                        Ok(value) => value,
                                        Err(error) => {
                                            return Some((
                                                Err(io::Error::other(error.to_string())),
                                                (2, release, response_state),
                                            ));
                                        }
                                    };
                                    trailers.insert("x-contract-trailer", value);
                                    Some((
                                        Ok(http_body::Frame::trailers(trailers)),
                                        (2, release, response_state),
                                    ))
                                }
                                _ => None,
                            }
                        },
                    );
                    let body = LifecycleBody {
                        inner: Box::pin(StreamBody::new(body)),
                        drop_flag: None,
                    };
                    Response::builder()
                        .status(StatusCode::OK)
                        .body(body)
                        .map_err(|error| io::Error::other(error.to_string()))
                }
                "/http3-response-hold-before-finish" => {
                    let release = state.http3_response_cancel_release.subscribe();
                    let response_state = Arc::clone(&state);
                    let body = stream::unfold((), move |_| {
                        let mut release = release.clone();
                        let response_state = Arc::clone(&response_state);
                        async move {
                            response_state
                                .http3_response_cancel_pending
                                .store(true, Ordering::Release);
                            while !*release.borrow_and_update() {
                                if release.changed().await.is_err() {
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(false, Ordering::Release);
                                    return None::<(Result<http_body::Frame<Bytes>, io::Error>, ())>;
                                }
                            }
                            response_state
                                .http3_response_cancel_pending
                                .store(false, Ordering::Release);
                            None::<(Result<http_body::Frame<Bytes>, io::Error>, ())>
                        }
                    });
                    let body = LifecycleBody {
                        inner: Box::pin(StreamBody::new(body)),
                        drop_flag: None,
                    };
                    Response::builder()
                        .status(StatusCode::OK)
                        .body(body)
                        .map_err(|error| io::Error::other(error.to_string()))
                }
                "/hold" => {
                    state.active_request.send_replace(true);
                    let mut release = state.release_request.subscribe();
                    while !*release.borrow() {
                        release.changed().await.map_err(|_| {
                            io::Error::other("lifecycle request release channel closed")
                        })?;
                    }
                    lifecycle_response(
                        b"released\n",
                        Some(Arc::clone(&state.response_body_dropped)),
                    )
                }
                _ => lifecycle_response(b"not found\n", None).and_then(|response| {
                    Response::builder()
                        .status(StatusCode::NOT_FOUND)
                        .body(response.into_body())
                        .map_err(|error| io::Error::other(error.to_string()))
                }),
            }
        })
    }
}

type AppFutureLifecycle =
    Pin<Box<dyn Future<Output = Result<Response<LifecycleBody>, io::Error>> + Send>>;

impl Body for LifecycleBody {
    type Data = Bytes;
    type Error = io::Error;

    fn poll_frame(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Option<Result<http_body::Frame<Self::Data>, Self::Error>>> {
        self.get_mut().inner.as_mut().poll_frame(context)
    }

    fn is_end_stream(&self) -> bool {
        self.inner.as_ref().get_ref().is_end_stream()
    }

    fn size_hint(&self) -> SizeHint {
        self.inner.as_ref().get_ref().size_hint()
    }
}

impl Drop for LifecycleBody {
    fn drop(&mut self) {
        if let Some(drop_flag) = &self.drop_flag {
            drop_flag.store(true, Ordering::Release);
        }
    }
}

fn lifecycle_response(
    body: &[u8],
    drop_flag: Option<Arc<AtomicBool>>,
) -> Result<Response<LifecycleBody>, io::Error> {
    let body = LifecycleBody {
        inner: Box::pin(Full::new(Bytes::copy_from_slice(body)).map_err(|never| match never {})),
        drop_flag,
    };
    Response::builder()
        .status(StatusCode::OK)
        .body(body)
        .map_err(|error| io::Error::other(error.to_string()))
}

fn record_lifecycle_event(state: &LifecycleState, event: &'static str) -> io::Result<()> {
    state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event log was poisoned"))?
        .push(event);
    Ok(())
}

impl<B> Service<Request<B>> for ContractApp
where
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: std::fmt::Display + Send + Sync + 'static,
{
    type Response = Response<AppBody>;
    type Error = io::Error;
    type Future = AppFuture;

    fn poll_ready(&mut self, context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        if self
            .state
            .panic_next_readiness
            .swap(false, Ordering::AcqRel)
        {
            inject_native_contract_panic("injected HTTP/3 application readiness panic");
        }
        let mut readiness = match self.state.readiness_gate.lock() {
            Ok(readiness) => readiness,
            Err(_) => {
                return Poll::Ready(Err(io::Error::other(
                    "readiness contract state was poisoned",
                )));
            }
        };
        if readiness.armed {
            readiness.armed = false;
            readiness.waiting = true;
            readiness.released = false;
            readiness.wake_started = false;
            readiness.pending_polls = 0;
            readiness.wakers.clear();
        }
        if readiness.waiting && !readiness.released {
            readiness.pending_polls = readiness.pending_polls.saturating_add(1);
            readiness.wakers.push(context.waker().clone());
            if !readiness.wake_started {
                readiness.wake_started = true;
                let state = Arc::clone(&self.state);
                let _wake_task = tokio::spawn(async move {
                    tokio::time::sleep(Duration::from_millis(40)).await;
                    let wakers = match state.readiness_gate.lock() {
                        Ok(mut readiness) => {
                            readiness.waiting = false;
                            readiness.released = true;
                            readiness.wake_started = false;
                            std::mem::take(&mut readiness.wakers)
                        }
                        Err(_) => return,
                    };
                    for waker in wakers {
                        waker.wake();
                    }
                });
            }
            return Poll::Pending;
        }
        drop(readiness);
        if self.state.fail_next_readiness.swap(false, Ordering::AcqRel) {
            Poll::Ready(Err(io::Error::other("injected readiness failure")))
        } else {
            Poll::Ready(Ok(()))
        }
    }

    fn call(&mut self, mut request: Request<B>) -> Self::Future {
        let path = request.uri().path().to_owned();
        let connection_info = request.extensions().get::<ConnectionInfo>().cloned();
        let request_lifetime = request.extensions().get::<RequestLifetime>().cloned();
        let connection_lifetime = request.extensions().get::<ConnectionLifetime>().cloned();
        let connection_upgrade = request.extensions().get::<ConnectionUpgrade>().cloned();
        let peer_read_half_closed = request.extensions().get::<PeerReadHalfClosed>().cloned();
        let peer_address = connection_info.as_ref().map(ConnectionInfo::peer_addr);
        let connection_security = connection_info.as_ref().map(|info| {
            let alpn = info
                .tls()
                .and_then(|tls| tls.alpn_protocol())
                .map(String::from_utf8_lossy)
                .map(|value| value.into_owned())
                .unwrap_or_else(|| "none".to_owned());
            format!("tls={};alpn={alpn}\n", info.tls().is_some())
        });
        let connection_details = connection_info.as_ref().map(|info| {
            let transport = match info.transport() {
                TransportKind::Tcp => "tcp",
                TransportKind::Quic => "quic",
            };
            let alpn = info
                .tls()
                .and_then(|tls| tls.alpn_protocol())
                .map(String::from_utf8_lossy)
                .map(|value| value.into_owned())
                .unwrap_or_else(|| "none".to_owned());
            let version = match request.version() {
                http::Version::HTTP_09 => "0.9",
                http::Version::HTTP_10 => "1.0",
                http::Version::HTTP_11 => "1.1",
                http::Version::HTTP_2 => "2",
                http::Version::HTTP_3 => "3",
                _ => "unknown",
            };
            format!(
                "transport={transport};tls={};alpn={alpn};version={version}\n",
                info.tls().is_some()
            )
        });
        let state = Arc::clone(&self.state);
        let bodyless_get_has_content_length = request.method() == Method::GET
            && request.headers().contains_key(http::header::CONTENT_LENGTH);
        Box::pin(async move {
            if bodyless_get_has_content_length {
                return response(
                    StatusCode::BAD_REQUEST,
                    b"bodyless GET must omit Content-Length\n",
                );
            }
            match path.as_str() {
                "/peer-address" => match peer_address {
                    Some(address) => response(StatusCode::OK, address.to_string().as_bytes()),
                    None => Err(io::Error::other("TCP peer address extension is missing")),
                },
                "/connection-security" => match connection_security {
                    Some(security) => response(StatusCode::OK, security.as_bytes()),
                    None => Err(io::Error::other("connection metadata extension is missing")),
                },
                "/connection-details" => match connection_details {
                    Some(details) => response(StatusCode::OK, details.as_bytes()),
                    None => Err(io::Error::other("connection metadata extension is missing")),
                },
                "/peer-read-half-close-availability" => response(
                    StatusCode::OK,
                    format!("available={}\n", peer_read_half_closed.is_some()).as_bytes(),
                ),
                "/empty" => empty_response(),
                "/peer-write-half-close" => {
                    let Some(connection_lifetime) = connection_lifetime else {
                        return Err(io::Error::other("connection lifetime extension is missing"));
                    };
                    state
                        .peer_write_half_close_started
                        .store(true, Ordering::Release);
                    let mut release = state.peer_write_half_close_release.subscribe();
                    let body = stream::once(async move {
                        while !*release.borrow_and_update() {
                            release.changed().await.map_err(|_| {
                                io::Error::other("half-close response release channel closed")
                            })?;
                        }
                        let connection_open = !connection_lifetime.is_closed();
                        let body = format!("connection_open={connection_open}\n");
                        Ok::<_, io::Error>(http_body::Frame::data(Bytes::from(body)))
                    });
                    stream_response(body)
                }
                "/peer-write-half-close-state" => response(
                    StatusCode::OK,
                    format!(
                        "started={}\n",
                        state.peer_write_half_close_started.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/peer-write-half-close-release" => {
                    state.peer_write_half_close_release.send_replace(true);
                    response(StatusCode::OK, b"released\n")
                }
                "/peer-read-half-close-full"
                | "/peer-read-half-close-empty"
                | "/peer-read-half-close-stream" => {
                    let Some(peer_read_half_closed) = peer_read_half_closed else {
                        return Err(io::Error::other(
                            "peer read-half-close observation extension is missing",
                        ));
                    };
                    state.peer_read_half_close_observation.send_replace(None);
                    tokio::spawn(record_peer_read_half_close_observation(
                        Arc::clone(&state),
                        peer_read_half_closed,
                    ));
                    match path.as_str() {
                        "/peer-read-half-close-full" => {
                            response(StatusCode::OK, b"complete\n")
                        }
                        "/peer-read-half-close-empty" => {
                            let mut response = empty_response()?;
                            response.headers_mut().insert(
                                http::header::CONTENT_LENGTH,
                                HeaderValue::from_static("0"),
                            );
                            Ok(response)
                        }
                        "/peer-read-half-close-stream" => stream_response(stream::once(async {
                            Ok::<_, io::Error>(http_body::Frame::data(Bytes::from_static(
                                b"complete\n",
                            )))
                        })),
                        _ => Err(io::Error::other(
                            "unknown peer read-half-close response shape",
                        )),
                    }
                }
                "/peer-read-half-close-state" => {
                    let mut observation = state.peer_read_half_close_observation.subscribe();
                    let result = tokio::time::timeout(Duration::from_secs(3), async {
                        loop {
                            if let Some(value) = observation.borrow_and_update().clone() {
                                return Ok::<_, io::Error>(value);
                            }
                            observation.changed().await.map_err(|_| {
                                io::Error::other("peer read-half-close observation channel closed")
                            })?;
                        }
                    })
                    .await;
                    match result {
                        Ok(Ok(value)) => response(StatusCode::OK, value.as_bytes()),
                        Ok(Err(error)) => Err(error),
                        Err(_) => response(
                            StatusCode::GATEWAY_TIMEOUT,
                            b"peer read-half-close observation timed out\n",
                        ),
                    }
                }
                "/peer-read-half-close-shutdown-watch" => {
                    let Some(mut peer_read_half_closed) = peer_read_half_closed else {
                        return Err(io::Error::other(
                            "peer read-half-close observation extension is missing",
                        ));
                    };
                    state
                        .peer_read_half_close_unavailable_result
                        .send_replace(None);
                    let outcome = state.peer_read_half_close_unavailable_result.clone();
                    tokio::spawn(async move {
                        let result = peer_read_half_closed.wait_until_read_half_closed().await;
                        let value = match result {
                            Ok(()) => format!(
                                "read_half_closed={};error=none;source_none=true\n",
                                peer_read_half_closed.is_read_half_closed()
                            ),
                            Err(error) => format!(
                                "read_half_closed={};error={error};source_none={}\n",
                                peer_read_half_closed.is_read_half_closed(),
                                error.source().is_none()
                            ),
                        };
                        outcome.send_replace(Some(value));
                    });
                    response(StatusCode::OK, b"watching\n")
                }
                "/upgrade-session" | "/upgrade-session-pending-response" => {
                    let (Some(connection_upgrade), Some(connection_lifetime)) =
                        (connection_upgrade, connection_lifetime)
                    else {
                        return Err(io::Error::other(
                            "HTTP/1 upgrade or connection lifetime extension is missing",
                        ));
                    };
                    let on_upgrade = hyper::upgrade::on(&mut request);
                    register_contract_upgrade_session(
                        connection_upgrade,
                        on_upgrade,
                        UpgradeSessionBehavior::Graceful(connection_lifetime),
                    )
                        .map_err(|error| io::Error::other(error.to_string()))?;
                    if path == "/upgrade-session-pending-response" {
                        tokio::task::yield_now().await;
                    }
                    upgrade_response()
                }
                "/upgrade-session-handler-error"
                | "/upgrade-session-handler-error-pending-response"
                | "/upgrade-session-handler-panic" => {
                    let Some(connection_upgrade) = connection_upgrade else {
                        return Err(io::Error::other(
                            "HTTP/1 upgrade extension is missing",
                        ));
                    };
                    let on_upgrade = hyper::upgrade::on(&mut request);
                    register_contract_upgrade_session(
                        connection_upgrade,
                        on_upgrade,
                        if path == "/upgrade-session-handler-panic" {
                            UpgradeSessionBehavior::HandlerPanic
                        } else {
                            UpgradeSessionBehavior::HandlerError
                        },
                    )
                        .map_err(|error| io::Error::other(error.to_string()))?;
                    if path == "/upgrade-session-handler-error-pending-response" {
                        tokio::task::yield_now().await;
                    }
                    upgrade_response()
                }
                "/upgrade-session-not-accepted" => {
                    let Some(connection_upgrade) = connection_upgrade else {
                        return Err(io::Error::other(
                            "HTTP/1 upgrade extension is missing",
                        ));
                    };
                    let on_upgrade = hyper::upgrade::on(&mut request);
                    register_contract_upgrade_session(
                        connection_upgrade,
                        on_upgrade,
                        UpgradeSessionBehavior::HandlerError,
                    )
                        .map_err(|error| io::Error::other(error.to_string()))?;
                    response(StatusCode::OK, b"upgrade was not accepted\n")
                }
                "/upgrade-registration-after-close" => {
                    let (Some(connection_upgrade), Some(mut connection_lifetime)) =
                        (connection_upgrade, connection_lifetime)
                    else {
                        return Err(io::Error::other(
                            "HTTP/1 upgrade or connection lifetime extension is missing",
                        ));
                    };
                    let on_upgrade = hyper::upgrade::on(&mut request);
                    let registration_outcome = state.upgrade_registration_outcome.clone();
                    let _registration_task = tokio::spawn(async move {
                        connection_lifetime.wait_until_closed().await;
                        connection_upgrade.wait_for_shutdown().await;
                        let outcome = match register_contract_upgrade_session(
                            connection_upgrade,
                            on_upgrade,
                            UpgradeSessionBehavior::HandlerError,
                        ) {
                            Ok(()) => "registration unexpectedly succeeded".to_owned(),
                            Err(error) => error.to_string(),
                        };
                        registration_outcome.send_replace(Some(outcome));
                    });
                    response(StatusCode::OK, b"registration deferred\n")
                }
                "/native-websocket-accept-after-close" => {
                    native_websocket_accept_after_close(&mut request, &state)
                }
                "/native-websocket-echo"
                | "/native-websocket-unoffered-subprotocol"
                | "/native-websocket-invalid-method"
                | "/native-websocket-missing-upgrade-capability"
                | "/native-websocket-token-trim"
                | "/native-websocket-header-capacity"
                | "/native-websocket-accept-header-capacity"
                | "/native-websocket-echo-accept-header-capacity"
                | "/native-websocket-malformed-frame"
                | "/native-websocket-close-flush-error"
                | "/native-websocket-invalid-subprotocol-token"
                | "/native-websocket-invalid-selected-subprotocol-header-value"
                | "/native-websocket-invalid-version"
                | "/native-websocket-invalid-key-size"
                | "/native-websocket-missing-upgrade-token"
                | "/native-websocket-wrong-upgrade-token"
                | "/native-websocket-empty-subprotocol-token"
                | "/native-websocket-reserved-response-header"
                | "/native-websocket-duplicate-subprotocol"
                | "/native-websocket-custom-response-header" => {
                    if request.uri().path() == "/native-websocket-missing-upgrade-capability" {
                        request.extensions_mut().remove::<ConnectionUpgrade>();
                    }
                    let behavior = match request.uri().path() {
                        "/native-websocket-reserved-response-header" => {
                            NativeWebSocketBehavior::ReservedHeader
                        }
                        "/native-websocket-duplicate-subprotocol" => {
                            NativeWebSocketBehavior::DuplicateSubprotocol
                        }
                        "/native-websocket-custom-response-header" => {
                            NativeWebSocketBehavior::EchoWithHeader
                        }
                        "/native-websocket-header-capacity" => {
                            NativeWebSocketBehavior::HeaderCapacity
                        }
                        "/native-websocket-accept-header-capacity" => {
                            NativeWebSocketBehavior::AcceptHeaderCapacity
                        }
                        "/native-websocket-echo-accept-header-capacity" => {
                            NativeWebSocketBehavior::EchoAcceptHeaderCapacity
                        }
                        "/native-websocket-malformed-frame"
                        | "/native-websocket-close-flush-error" => {
                            NativeWebSocketBehavior::ObserveReceiveError(
                                state.websocket_error_observation.clone(),
                            )
                        }
                        _ => NativeWebSocketBehavior::Echo,
                    };
                    let subprotocol = match request.uri().path() {
                        "/native-websocket-token-trim" => Some("Native+Echo"),
                        "/native-websocket-invalid-selected-subprotocol-header-value" => {
                            Some("native\r.echo")
                        }
                        "/native-websocket-accept-header-capacity"
                        | "/native-websocket-echo-accept-header-capacity"
                        | "/native-websocket-malformed-frame"
                        | "/native-websocket-close-flush-error" => None,
                        _ => Some("native.echo.v1"),
                    };
                    native_websocket_route(
                        &mut request,
                        subprotocol,
                        behavior,
                    )
                }
                "/native-websocket-shutdown" => native_websocket_route(
                    &mut request,
                    None,
                    NativeWebSocketBehavior::Shutdown,
                ),
                "/native-websocket-invalid-key" => native_websocket_route(
                    &mut request,
                    Some("native.echo.v1"),
                    NativeWebSocketBehavior::Echo,
                ),
                "/ready" => response(StatusCode::OK, b"ready\n"),
                "/arm-readiness-pending" => {
                    let mut readiness = state
                        .readiness_gate
                        .lock()
                        .map_err(|_| io::Error::other("readiness contract state was poisoned"))?;
                    readiness.armed = true;
                    readiness.waiting = false;
                    readiness.released = false;
                    readiness.wake_started = false;
                    readiness.pending_polls = 0;
                    readiness.wakers.clear();
                    response(StatusCode::OK, b"armed\n")
                }
                "/readiness-pending-state" => {
                    let readiness = state
                        .readiness_gate
                        .lock()
                        .map_err(|_| io::Error::other("readiness contract state was poisoned"))?;
                    response(
                        StatusCode::OK,
                        format!(
                            "pending={};released={}\n",
                            readiness.pending_polls > 0,
                            readiness.released
                        )
                        .as_bytes(),
                    )
                }
                "/request-lifetime-hold" => {
                    let (Some(mut request_lifetime), Some(mut connection_lifetime)) =
                        (request_lifetime, connection_lifetime)
                    else {
                        return Err(io::Error::other("request lifetime extensions are missing"));
                    };
                    let peer_eof_available =
                        Arc::clone(&state.request_lifetime_peer_eof_available);
                    if peer_read_half_closed.is_some() {
                        peer_eof_available.store(true, Ordering::Release);
                    }
                    let peer_eof_observation = Arc::clone(&state.request_lifetime_peer_eof);
                    state
                        .request_lifetime_waiters
                        .fetch_add(1, Ordering::AcqRel);
                    let request_lifetime_reason_checks =
                        Arc::clone(&state.request_lifetime_reason_checks);
                    if request_lifetime.end_reason().is_none() {
                        request_lifetime_reason_checks.fetch_add(1, Ordering::AcqRel);
                    }
                    let request_future_drops = Arc::clone(&state.request_future_drops);
                    let request_ends_while_connection_open =
                        Arc::clone(&state.request_ends_while_connection_open);
                    let request_connections_closed = Arc::clone(&state.request_connections_closed);
                    let peer_read_half_closed = peer_read_half_closed.clone();
                    tokio::spawn(async move {
                        let reason = request_lifetime.wait_until_ended().await;
                        if reason == Some(RequestEndReason::ServiceFutureDropped) {
                            if let Some(peer_read_half_closed) = peer_read_half_closed {
                                peer_eof_observation.store(
                                    peer_read_half_closed.is_read_half_closed(),
                                    Ordering::Release,
                                );
                            }
                            if request_lifetime.end_reason() == reason {
                                request_lifetime_reason_checks.fetch_add(1, Ordering::AcqRel);
                            }
                            request_future_drops.fetch_add(1, Ordering::AcqRel);
                            if !connection_lifetime.is_closed() {
                                request_ends_while_connection_open.fetch_add(1, Ordering::AcqRel);
                            }
                            connection_lifetime.wait_until_closed().await;
                            request_connections_closed.fetch_add(1, Ordering::AcqRel);
                        }
                    });
                    std::future::pending::<Result<Response<AppBody>, io::Error>>().await
                }
                "/request-lifetime-state" => response(
                    StatusCode::OK,
                    format!(
                        "started={};dropped={};connection_open={};connection_closed={};reason_checks={};peer_eof_available={};peer_eof={}\n",
                        state.request_lifetime_waiters.load(Ordering::Acquire),
                        state.request_future_drops.load(Ordering::Acquire),
                        state
                            .request_ends_while_connection_open
                            .load(Ordering::Acquire),
                        state.request_connections_closed.load(Ordering::Acquire),
                        state.request_lifetime_reason_checks.load(Ordering::Acquire),
                        state
                            .request_lifetime_peer_eof_available
                            .load(Ordering::Acquire),
                        state.request_lifetime_peer_eof.load(Ordering::Acquire),
                    )
                    .as_bytes(),
                ),
                "/arm-readiness" => {
                    state.fail_next_readiness.store(true, Ordering::Release);
                    response(StatusCode::OK, b"armed\n")
                }
                "/arm-readiness-panic" => {
                    state
                        .panic_next_readiness
                        .store(true, Ordering::Release);
                    response(StatusCode::OK, b"armed\n")
                }
                "/body-state" => {
                    let mut body = Box::pin(request.into_body());
                    let initially_ended = body.is_end_stream();
                    let size_hint = body.size_hint();
                    let mut received = 0_usize;
                    while let Some(frame) = body.frame().await {
                        let frame = frame.map_err(|error| io::Error::other(error.to_string()))?;
                        if let Ok(data) = frame.into_data() {
                            received = received.checked_add(data.len()).ok_or_else(|| {
                                io::Error::new(io::ErrorKind::InvalidData, "body size overflow")
                            })?;
                        }
                    }
                    response(
                        StatusCode::OK,
                        format!(
                            "initially_ended={initially_ended};size_lower={};size_upper={:?};ended={};received={received}\n",
                            size_hint.lower(),
                            size_hint.upper(),
                            body.is_end_stream(),
                        )
                        .as_bytes(),
                    )
                }
                "/consume" => {
                    let mut body = Box::pin(request.into_body());
                    let mut received = 0_usize;
                    while let Some(frame) = body.frame().await {
                        let frame = frame.map_err(|error| io::Error::other(error.to_string()))?;
                        if let Ok(data) = frame.into_data() {
                            received = received.checked_add(data.len()).ok_or_else(|| {
                                io::Error::new(io::ErrorKind::InvalidData, "body size overflow")
                            })?;
                        }
                    }
                    response(StatusCode::OK, format!("received={received}\n").as_bytes())
                }
                "/http3-pending-consume" => {
                    state.http3_body_pending.store(false, Ordering::Release);
                    let mut body = Box::pin(request.into_body());
                    let mut received = 0_usize;
                    loop {
                        let frame = std::future::poll_fn(|context| {
                            match body.as_mut().poll_frame(context) {
                                Poll::Pending => {
                                    state.http3_body_pending.store(true, Ordering::Release);
                                    Poll::Pending
                                }
                                ready => ready,
                            }
                        })
                        .await;
                        let Some(frame) = frame else { break };
                        let frame = frame.map_err(|error| io::Error::other(error.to_string()))?;
                        if let Ok(data) = frame.into_data() {
                            received = received.checked_add(data.len()).ok_or_else(|| {
                                io::Error::new(io::ErrorKind::InvalidData, "body size overflow")
                            })?;
                        }
                    }
                    response(StatusCode::OK, format!("received={received}\n").as_bytes())
                }
                "/http3-body-pending-state" => response(
                    StatusCode::OK,
                    format!(
                        "pending={}\n",
                        state.http3_body_pending.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/http3-reset-consume" => {
                    state.http3_body_pending.store(false, Ordering::Release);
                    let mut body = Box::pin(request.into_body());
                    loop {
                        let frame = std::future::poll_fn(|context| {
                            match body.as_mut().poll_frame(context) {
                                Poll::Pending => {
                                    state.http3_body_pending.store(true, Ordering::Release);
                                    Poll::Pending
                                }
                                ready => ready,
                            }
                        })
                        .await;
                        let Some(frame) = frame else { break };
                        match frame {
                            Ok(_) => {}
                            Err(_) => {
                                state.http3_body_errors.fetch_add(1, Ordering::AcqRel);
                                return Err(io::Error::other("injected HTTP/3 request body reset"));
                            }
                        }
                    }
                    response(StatusCode::OK, b"upload-complete\n")
                }
                "/http3-body-error-state" => response(
                    StatusCode::OK,
                    format!(
                        "errors={}\n",
                        state.http3_body_errors.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/http3-response-error" => {
                    let body = stream::unfold(0_u8, |step| async move {
                        match step {
                            0 => Some((
                                Ok(http_body::Frame::data(Bytes::from_static(
                                    b"before-error\n",
                                ))),
                                1,
                            )),
                            1 => {
                                tokio::time::sleep(Duration::from_millis(50)).await;
                                Some((
                                    Err(io::Error::other("injected HTTP/3 response body error")),
                                    2,
                                ))
                            }
                            _ => None,
                        }
                    });
                    stream_response(body)
                }
                "/consume-trailers" => {
                    let mut body = Box::pin(request.into_body());
                    let mut received = 0_usize;
                    let mut trailer_value = None;
                    while let Some(frame) = body.frame().await {
                        let frame = frame.map_err(|error| io::Error::other(error.to_string()))?;
                        match frame.into_data() {
                            Ok(data) => {
                                received = received.checked_add(data.len()).ok_or_else(|| {
                                    io::Error::new(io::ErrorKind::InvalidData, "body size overflow")
                                })?;
                            }
                            Err(frame) => {
                                if let Ok(trailers) = frame.into_trailers() {
                                    trailer_value = trailers
                                        .get("x-contract-trailer")
                                        .and_then(|value| value.to_str().ok())
                                        .map(str::to_owned);
                                }
                            }
                        }
                    }
                    response(
                        StatusCode::OK,
                        format!(
                            "received={received};trailer={}\n",
                            trailer_value.as_deref().unwrap_or("missing")
                        )
                        .as_bytes(),
                    )
                }
                "/response-trailers" => {
                    let mut trailers = http::HeaderMap::new();
                    trailers.insert(
                        "x-contract-trailer",
                        "complete".parse().map_err(io::Error::other)?,
                    );
                    let body = stream::iter([
                        Ok(http_body::Frame::data(Bytes::from_static(b"body\n"))),
                        Ok(http_body::Frame::trailers(trailers)),
                    ]);
                    stream_response(body)
                }
                "/upload-cancel" => {
                    state.upload_bytes_received.store(0, Ordering::Release);
                    state.upload_body_errors.store(0, Ordering::Release);
                    state.upload_tasks_dropped.store(0, Ordering::Release);
                    let mut body = Box::pin(request.into_body());
                    let upload_state = Arc::clone(&state);
                    let _signal = DropSignal(Arc::clone(&state.upload_tasks_dropped));
                    while let Some(frame) = body.frame().await {
                        match frame {
                            Ok(frame) => {
                                if let Ok(data) = frame.into_data() {
                                    upload_state
                                        .upload_bytes_received
                                        .fetch_add(data.len(), Ordering::AcqRel);
                                }
                            }
                            Err(error) => {
                                upload_state
                                    .upload_body_errors
                                    .fetch_add(1, Ordering::AcqRel);
                                return Err(io::Error::other(error.to_string()));
                            }
                        }
                    }
                    response(StatusCode::OK, b"upload-complete\n")
                }
                "/upload-cancel-state" => response(
                    StatusCode::OK,
                    format!(
                        "bytes={};errors={};dropped={}\n",
                        state.upload_bytes_received.load(Ordering::Acquire),
                        state.upload_body_errors.load(Ordering::Acquire),
                        state.upload_tasks_dropped.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/stream" => {
                    state.stream_complete.store(false, Ordering::Release);
                    let stream_state = Arc::clone(&state);
                    let body = stream::unfold(0_u8, move |step| {
                        let stream_state = Arc::clone(&stream_state);
                        async move {
                            match step {
                                0 => Some((
                                    Ok(http_body::Frame::data(Bytes::from_static(b"first\n"))),
                                    1,
                                )),
                                1 => {
                                    tokio::time::sleep(Duration::from_millis(400)).await;
                                    stream_state.stream_complete.store(true, Ordering::Release);
                                    Some((
                                        Ok(http_body::Frame::data(Bytes::from_static(b"second\n"))),
                                        2,
                                    ))
                                }
                                _ => None,
                            }
                        }
                    });
                    stream_response(body)
                }
                "/stream-state" => {
                    let body = if state.stream_complete.load(Ordering::Acquire) {
                        b"complete\n".as_slice()
                    } else {
                        b"pending\n".as_slice()
                    };
                    response(StatusCode::OK, body)
                }
                "/service-error" => Err(io::Error::other("injected service error")),
                "/http3-service-panic" => {
                    // This route exists only in the contract runner so a real
                    // QUIC request can exercise request-task panic isolation.
                    std::panic::resume_unwind(Box::new(
                        "injected HTTP/3 application service panic",
                    ));
                }
                "/http1-service-panic" => {
                    // Keep this fault inside the contract runner: the
                    // connection task must unwind without taking down the
                    // listener that accepts subsequent requests.
                    std::panic::resume_unwind(Box::new(
                        "injected HTTP/1 application service panic",
                    ));
                }
                "/body-error" => {
                    let body = stream::unfold(0_u8, |step| async move {
                        match step {
                            0 => Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"partial\n"))),
                                1,
                            )),
                            1 => {
                                tokio::time::sleep(Duration::from_millis(100)).await;
                                Some((Err(io::Error::other("injected response body error")), 2))
                            }
                            _ => None,
                        }
                    });
                    stream_response(body)
                }
                "/disconnect" => {
                    let signal = DropSignal(Arc::clone(&state.cancelled_streams));
                    let body = stream::unfold((0_u8, signal), |(step, signal)| async move {
                        if step == 0 {
                            Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"first\n"))),
                                (1, signal),
                            ))
                        } else {
                            tokio::time::sleep(Duration::from_millis(50)).await;
                            Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"later\n"))),
                                (step.saturating_add(1), signal),
                            ))
                        }
                    });
                    stream_response(body)
                }
                "/cancel-count" => response(
                    StatusCode::OK,
                    format!("{}\n", state.cancelled_streams.load(Ordering::Acquire)).as_bytes(),
                ),
                "/h2-disconnect" => {
                    let signal = DropSignal(Arc::clone(&state.cancelled_h2_streams));
                    let body = stream::unfold((0_u8, signal), |(step, signal)| async move {
                        if step == 0 {
                            Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"first\n"))),
                                (1, signal),
                            ))
                        } else {
                            tokio::time::sleep(Duration::from_millis(50)).await;
                            Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"later\n"))),
                                (step.saturating_add(1), signal),
                            ))
                        }
                    });
                    stream_response(body)
                }
                "/h2-disconnect-count" => response(
                    StatusCode::OK,
                    format!("{}\n", state.cancelled_h2_streams.load(Ordering::Acquire)).as_bytes(),
                ),
                "/http3-disconnect" => {
                    let signal = DropSignal(Arc::clone(&state.http3_cancelled_streams));
                    let body = stream::unfold((0_u8, signal), |(step, signal)| async move {
                        if step == 0 {
                            Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"first\n"))),
                                (1, signal),
                            ))
                        } else {
                            std::future::pending().await
                        }
                    });
                    stream_response(body)
                }
                "/http3-disconnect-count" => response(
                    StatusCode::OK,
                    format!("{}\n", state.http3_cancelled_streams.load(Ordering::Acquire))
                        .as_bytes(),
                ),
                "/http3-response-cancel-pending" => response(
                    StatusCode::OK,
                    if state
                        .http3_response_cancel_pending
                        .load(Ordering::Acquire)
                    {
                        b"waiting\n"
                    } else {
                        b"ready\n"
                    },
                ),
                "/http3-response-cancel-waiters" => response(
                    StatusCode::OK,
                    format!(
                        "waiting={}\n",
                        state.http3_response_cancel_waiters.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/http3-response-cancel-release" => {
                    state
                        .http3_response_cancel_pending
                        .store(false, Ordering::Release);
                    state.http3_response_cancel_release.send_replace(true);
                    response(StatusCode::OK, b"released\n")
                }
                "/http3-response-hold-before-headers" => {
                    let mut release = state.http3_response_cancel_release.subscribe();
                    state
                        .http3_response_cancel_waiters
                        .fetch_add(1, Ordering::AcqRel);
                    state
                        .http3_response_cancel_pending
                        .store(true, Ordering::Release);
                    while !*release.borrow_and_update() {
                        if release.changed().await.is_err() {
                            state
                                .http3_response_cancel_waiters
                                .fetch_sub(1, Ordering::AcqRel);
                            return Err(io::Error::other(
                                "HTTP/3 response release channel closed",
                            ));
                        }
                    }
                    state
                        .http3_response_cancel_waiters
                        .fetch_sub(1, Ordering::AcqRel);
                    state
                        .http3_response_cancel_pending
                        .store(false, Ordering::Release);
                    response(StatusCode::OK, b"released response\n")
                }
                "/http3-response-hold-before-trailers" => {
                    let release = state.http3_response_cancel_release.subscribe();
                    let response_state = Arc::clone(&state);
                    let body = stream::unfold(
                        (0_u8, release, response_state),
                        |(step, mut release, response_state)| async move {
                            match step {
                                0 => Some((
                                    Ok(http_body::Frame::data(Bytes::from_static(
                                        b"before-trailers\n",
                                    ))),
                                    (1, release, response_state),
                                )),
                                1 => {
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(true, Ordering::Release);
                                    while !*release.borrow_and_update() {
                                        if release.changed().await.is_err() {
                                            response_state
                                                .http3_response_cancel_pending
                                                .store(false, Ordering::Release);
                                            return Some((
                                                Err(io::Error::other(
                                                    "HTTP/3 trailer release channel closed",
                                                )),
                                                (2, release, response_state),
                                            ));
                                        }
                                    }
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(false, Ordering::Release);
                                    let mut trailers = http::HeaderMap::new();
                                    let value = match http::HeaderValue::from_bytes(b"complete") {
                                        Ok(value) => value,
                                        Err(error) => {
                                            return Some((
                                                Err(io::Error::other(error.to_string())),
                                                (2, release, response_state),
                                            ));
                                        }
                                    };
                                    trailers.insert("x-contract-trailer", value);
                                    Some((
                                        Ok(http_body::Frame::trailers(trailers)),
                                        (2, release, response_state),
                                    ))
                                }
                                _ => None,
                            }
                        },
                    );
                    stream_response(body)
                }
                "/http3-response-hold-before-finish" => {
                    let release = state.http3_response_cancel_release.subscribe();
                    let response_state = Arc::clone(&state);
                    let body = stream::unfold((), move |_| {
                        let mut release = release.clone();
                        let response_state = Arc::clone(&response_state);
                        async move {
                            response_state
                                .http3_response_cancel_pending
                                .store(true, Ordering::Release);
                            while !*release.borrow_and_update() {
                                if release.changed().await.is_err() {
                                    response_state
                                        .http3_response_cancel_pending
                                        .store(false, Ordering::Release);
                                    return None::<(
                                        Result<http_body::Frame<Bytes>, io::Error>,
                                        (),
                                    )>;
                                }
                            }
                            response_state
                                .http3_response_cancel_pending
                                .store(false, Ordering::Release);
                            None::<(Result<http_body::Frame<Bytes>, io::Error>, ())>
                        }
                    });
                    stream_response(body)
                }
                "/backpressure" => {
                    const CHUNK_SIZE: usize = 32 * 1024;
                    const TOTAL_CHUNKS: usize = 2_048;

                    state.response_chunks_polled.store(0, Ordering::Release);
                    state.response_streams_dropped.store(0, Ordering::Release);
                    let body_state = Arc::clone(&state);
                    let chunk = Bytes::from(vec![b'x'; CHUNK_SIZE]);
                    let signal = DropSignal(Arc::clone(&state.response_streams_dropped));
                    let body = stream::unfold((0_usize, signal), move |(step, signal)| {
                        let body_state = Arc::clone(&body_state);
                        let chunk = chunk.clone();
                        async move {
                            if step >= TOTAL_CHUNKS {
                                return None;
                            }
                            body_state
                                .response_chunks_polled
                                .fetch_add(1, Ordering::AcqRel);
                            Some((Ok(http_body::Frame::data(chunk)), (step + 1, signal)))
                        }
                    });
                    stream_response(body)
                }
                "/backpressure-state" => response(
                    StatusCode::OK,
                    format!(
                        "polled={};dropped={}\n",
                        state.response_chunks_polled.load(Ordering::Acquire),
                        state.response_streams_dropped.load(Ordering::Acquire)
                    )
                    .as_bytes(),
                ),
                "/slow" => {
                    let body = stream::unfold(0_u8, |step| async move {
                        match step {
                            0 => Some((
                                Ok(http_body::Frame::data(Bytes::from_static(b"first\n"))),
                                1,
                            )),
                            1 => {
                                tokio::time::sleep(Duration::from_millis(400)).await;
                                Some((
                                    Ok(http_body::Frame::data(Bytes::from_static(b"second\n"))),
                                    2,
                                ))
                            }
                            _ => None,
                        }
                    });
                    stream_response(body)
                }
                "/graceful-timeout-hold" => {
                    let signal = DropSignal(Arc::clone(&state.graceful_timeout_stream_drops));
                    let body = stream::unfold((false, signal), |(sent, signal)| async move {
                        if sent {
                            return std::future::pending::<Option<_>>().await;
                        }
                        Some((
                            Ok(http_body::Frame::data(Bytes::from_static(b"held\n"))),
                            (true, signal),
                        ))
                    });
                    stream_response(body)
                }
                "/shutdown" => {
                    let shutdown = state.shutdown.clone();
                    let body = stream::once(async move {
                        tokio::time::sleep(Duration::from_millis(25)).await;
                        shutdown.send_replace(true);
                        Ok(http_body::Frame::data(Bytes::from_static(
                            b"shutting down\n",
                        )))
                    });
                    stream_response(body)
                }
                _ => response(StatusCode::NOT_FOUND, b"not found\n"),
            }
        })
    }
}

enum NativeWebSocketBehavior {
    Echo,
    EchoWithHeader,
    ReservedHeader,
    DuplicateSubprotocol,
    Shutdown,
    HeaderCapacity,
    AcceptHeaderCapacity,
    EchoAcceptHeaderCapacity,
    ObserveReceiveError(watch::Sender<Option<String>>),
}

fn native_websocket_route<B>(
    request: &mut Request<B>,
    subprotocol: Option<&str>,
    behavior: NativeWebSocketBehavior,
) -> Result<Response<AppBody>, io::Error> {
    let upgrade = match WebSocketUpgrade::from_request(request) {
        Ok(upgrade) => upgrade,
        Err(error) => return websocket_bad_request(error),
    };
    let upgrade = match &behavior {
        NativeWebSocketBehavior::EchoWithHeader => upgrade.with_header(
            HeaderName::from_static("x-native-websocket"),
            HeaderValue::from_static("native"),
        ),
        NativeWebSocketBehavior::ReservedHeader => upgrade.with_header(
            SEC_WEBSOCKET_ACCEPT,
            HeaderValue::from_static("application-override"),
        ),
        NativeWebSocketBehavior::HeaderCapacity => {
            let error = native_websocket_header_capacity_error(upgrade)?;
            return websocket_bad_request(error);
        }
        _ => Ok(upgrade),
    };
    let upgrade = match upgrade {
        Ok(upgrade) => upgrade,
        Err(error) => return websocket_bad_request(error),
    };
    let upgrade = match subprotocol {
        Some(subprotocol) => match upgrade.with_subprotocol(subprotocol) {
            Ok(upgrade) => upgrade,
            Err(error) => return websocket_bad_request(error),
        },
        None => upgrade,
    };
    let upgrade = if matches!(&behavior, NativeWebSocketBehavior::DuplicateSubprotocol) {
        let Some(subprotocol) = subprotocol else {
            return websocket_bad_request(WebSocketUpgradeError::InvalidSubprotocol);
        };
        match upgrade.with_subprotocol(subprotocol) {
            Ok(upgrade) => upgrade,
            Err(error) => return websocket_bad_request(error),
        }
    } else {
        upgrade
    };

    match behavior {
        NativeWebSocketBehavior::Echo | NativeWebSocketBehavior::EchoWithHeader => upgrade
            .accept(empty_body(), echo_websocket_session)
            .map_err(|error| io::Error::other(error.to_string())),
        NativeWebSocketBehavior::Shutdown => upgrade
            .accept(empty_body(), |mut session| async move {
                session.wait_for_shutdown().await;
                session
                    .close(Some(WebSocketCloseFrame {
                        code: WebSocketCloseCode::Away,
                        reason: "server shutdown".into(),
                    }))
                    .await?;
                while let Some(message) = session.receive().await? {
                    if matches!(message, WebSocketMessage::Close(_)) {
                        break;
                    }
                }
                Ok::<(), uvicorn_rs::WebSocketError>(())
            })
            .map_err(|error| io::Error::other(error.to_string())),
        NativeWebSocketBehavior::AcceptHeaderCapacity => {
            native_websocket_accept_header_capacity(upgrade)
        }
        NativeWebSocketBehavior::EchoAcceptHeaderCapacity => {
            native_websocket_echo_accept_header_capacity(upgrade)
        }
        NativeWebSocketBehavior::HeaderCapacity => Err(io::Error::other(
            "WebSocket header-capacity check unexpectedly reached acceptance",
        )),
        NativeWebSocketBehavior::ObserveReceiveError(observation) => upgrade
            .accept(empty_body(), move |mut session| async move {
                let outcome = match session.receive().await {
                    Err(error) => format!("{};source={}", error, Error::source(&error).is_some()),
                    Ok(message) => format!("unexpected receive result: {message:?};source=false"),
                };
                observation.send_replace(Some(outcome));
                Ok::<(), io::Error>(())
            })
            .map_err(|error| io::Error::other(error.to_string())),
        NativeWebSocketBehavior::ReservedHeader => {
            websocket_bad_request(WebSocketUpgradeError::ReservedResponseHeader)
        }
        NativeWebSocketBehavior::DuplicateSubprotocol => {
            websocket_bad_request(WebSocketUpgradeError::SubprotocolAlreadySelected)
        }
    }
}

async fn echo_websocket_session(mut session: WebSocketSession) -> Result<(), WebSocketError> {
    while let Some(message) = session.receive().await? {
        match message {
            WebSocketMessage::Text(text) => session.send(WebSocketMessage::Text(text)).await?,
            WebSocketMessage::Binary(bytes) => {
                session.send(WebSocketMessage::Binary(bytes)).await?;
            }
            WebSocketMessage::Close(_) => break,
            WebSocketMessage::Ping(_) | WebSocketMessage::Pong(_) | WebSocketMessage::Frame(_) => {}
        }
    }
    Ok(())
}

fn native_websocket_header_capacity_error(
    mut upgrade: WebSocketUpgrade,
) -> Result<WebSocketUpgradeError, io::Error> {
    for index in 0..(1_usize << 15) {
        let name = native_websocket_capacity_header_name(index)?;
        match upgrade.with_header(name, HeaderValue::from_static("v")) {
            Ok(next) => upgrade = next,
            Err(error @ WebSocketUpgradeError::HeaderCapacity) => return Ok(error),
            Err(error) => {
                return Err(io::Error::other(format!(
                    "unexpected WebSocket header setup error: {error}"
                )))
            }
        }
    }
    Err(io::Error::other(
        "WebSocket response headers did not reach their finite capacity",
    ))
}

fn native_websocket_accept_header_capacity(
    mut upgrade: WebSocketUpgrade,
) -> Result<Response<AppBody>, io::Error> {
    let capacity = native_websocket_header_map_capacity()?;
    let response_headers_before_overflow = capacity.saturating_sub(2);
    for index in 0..response_headers_before_overflow {
        let name = native_websocket_capacity_header_name(index)?;
        upgrade = upgrade
            .with_header(name, HeaderValue::from_static("v"))
            .map_err(|error| {
                io::Error::other(format!(
                    "WebSocket custom headers reached capacity before accept: {error}"
                ))
            })?;
    }

    match upgrade.accept(empty_body(), |_| async { Ok::<(), io::Error>(()) }) {
        Err(error @ WebSocketUpgradeError::HeaderCapacity) => websocket_bad_request(error),
        Err(error) => Err(io::Error::other(format!(
            "unexpected WebSocket accept setup error: {error}"
        ))),
        Ok(_) => Err(io::Error::other(
            "WebSocket accept did not reach final response header capacity",
        )),
    }
}

fn native_websocket_echo_accept_header_capacity(
    mut upgrade: WebSocketUpgrade,
) -> Result<Response<AppBody>, io::Error> {
    let capacity = native_websocket_header_map_capacity()?;
    let response_headers_before_overflow = capacity.saturating_sub(2);
    for index in 0..response_headers_before_overflow {
        let name = native_websocket_capacity_header_name(index)?;
        upgrade = upgrade
            .with_header(name, HeaderValue::from_static("v"))
            .map_err(|error| {
                io::Error::other(format!(
                    "WebSocket custom headers reached capacity before accept: {error}"
                ))
            })?;
    }

    match upgrade.accept(empty_body(), echo_websocket_session) {
        Err(error @ WebSocketUpgradeError::HeaderCapacity) => websocket_bad_request(error),
        Err(error) => Err(io::Error::other(format!(
            "unexpected WebSocket accept setup error: {error}"
        ))),
        Ok(_) => Err(io::Error::other(
            "WebSocket accept did not reach final response header capacity",
        )),
    }
}

fn native_websocket_header_map_capacity() -> Result<usize, io::Error> {
    let mut headers = http::HeaderMap::new();
    for index in 0..(1_usize << 15) {
        let name = native_websocket_capacity_header_name(index)?;
        match headers.try_append(name, HeaderValue::from_static("v")) {
            Ok(_) => {}
            Err(_) => return Ok(index),
        }
    }
    Err(io::Error::other(
        "HTTP HeaderMap capacity probe did not reach its finite limit",
    ))
}

fn native_websocket_capacity_header_name(index: usize) -> Result<HeaderName, io::Error> {
    HeaderName::from_bytes(format!("x-native-capacity-{index}").as_bytes())
        .map_err(|error| io::Error::other(error.to_string()))
}

fn native_websocket_accept_after_close<B>(
    request: &mut Request<B>,
    state: &Arc<AppState>,
) -> Result<Response<AppBody>, io::Error> {
    let upgrade = match WebSocketUpgrade::from_request(request) {
        Ok(upgrade) => upgrade,
        Err(error) => return websocket_bad_request(error),
    };
    let Some(mut connection_lifetime) = request.extensions().get::<ConnectionLifetime>().cloned()
    else {
        return Err(io::Error::other(
            "HTTP connection lifetime extension is missing",
        ));
    };
    let Some(connection_upgrade) = request.extensions().get::<ConnectionUpgrade>().cloned() else {
        return Err(io::Error::other("HTTP upgrade extension is missing"));
    };
    let outcome = state.upgrade_registration_outcome.clone();
    let _accept_task = tokio::spawn(async move {
        connection_lifetime.wait_until_closed().await;
        connection_upgrade.wait_for_shutdown().await;
        let result = match upgrade.accept(empty_body(), echo_websocket_session) {
            Ok(_) => "WebSocket acceptance unexpectedly succeeded".to_owned(),
            Err(error) => error.to_string(),
        };
        outcome.send_replace(Some(result));
    });
    response(StatusCode::OK, b"deferred WebSocket accept\n")
}

fn websocket_bad_request(error: WebSocketUpgradeError) -> Result<Response<AppBody>, io::Error> {
    let mut response = response(StatusCode::BAD_REQUEST, error.to_string().as_bytes())?;
    if error == WebSocketUpgradeError::InvalidHandshake("Sec-WebSocket-Version must be 13") {
        response
            .headers_mut()
            .insert(SEC_WEBSOCKET_VERSION, HeaderValue::from_static("13"));
    }
    Ok(response)
}

fn response(status: StatusCode, body: &[u8]) -> Result<Response<AppBody>, io::Error> {
    let body = Full::new(Bytes::copy_from_slice(body))
        .map_err(|never| match never {})
        .boxed_unsync();
    Response::builder()
        .status(status)
        .body(body)
        .map_err(|error| io::Error::other(error.to_string()))
}

fn empty_response() -> Result<Response<AppBody>, io::Error> {
    let body = empty_body();
    Response::builder()
        .status(StatusCode::OK)
        .body(body)
        .map_err(|error| io::Error::other(error.to_string()))
}

fn empty_body() -> AppBody {
    Empty::<Bytes>::new()
        .map_err(|never| match never {})
        .boxed_unsync()
}

async fn record_peer_read_half_close_observation(
    state: Arc<AppState>,
    mut observer: PeerReadHalfClosed,
) {
    let value = match observer.wait_until_read_half_closed().await {
        Ok(()) => format!("observed={}\n", observer.is_read_half_closed()),
        Err(error) => format!(
            "observed={};error={error};source_none={}\n",
            observer.is_read_half_closed(),
            error.source().is_none()
        ),
    };
    state
        .peer_read_half_close_observation
        .send_replace(Some(value));
}

fn upgrade_response() -> Result<Response<AppBody>, io::Error> {
    let body = Empty::<Bytes>::new()
        .map_err(|never| match never {})
        .boxed_unsync();
    Response::builder()
        .status(StatusCode::SWITCHING_PROTOCOLS)
        .header(http::header::CONNECTION, "upgrade")
        .header(http::header::UPGRADE, "uvicorn-rs-test")
        .body(body)
        .map_err(|error| io::Error::other(error.to_string()))
}

fn register_contract_upgrade_session(
    connection_upgrade: ConnectionUpgrade,
    on_upgrade: hyper::upgrade::OnUpgrade,
    behavior: UpgradeSessionBehavior,
) -> Result<(), uvicorn_rs::ConnectionUpgradeClosed> {
    let session_shutdown = connection_upgrade.clone();
    connection_upgrade.register(on_upgrade, move |mut stream| async move {
        match behavior {
            UpgradeSessionBehavior::HandlerError => {
                Err(io::Error::other("upgrade handler sentinel"))
            }
            UpgradeSessionBehavior::HandlerPanic => {
                inject_native_contract_panic("injected upgraded-session handler panic");
            }
            UpgradeSessionBehavior::Graceful(connection_lifetime) => {
                let mut input = [0; 4];
                stream.read_exact(&mut input).await?;
                if input != *b"ping" {
                    return Err(io::Error::other("unexpected upgraded-session input"));
                }
                let response = format!(
                    "pong;connection-open={}\n",
                    !connection_lifetime.is_closed()
                );
                stream.write_all(response.as_bytes()).await?;
                session_shutdown.wait_for_shutdown().await;
                let response = format!(
                    "shutdown;connection-open={}\n",
                    !connection_lifetime.is_closed()
                );
                stream.write_all(response.as_bytes()).await?;
                Ok(())
            }
        }
    })
}

fn stream_response<S>(body: S) -> Result<Response<AppBody>, io::Error>
where
    S: futures_util::Stream<Item = Result<http_body::Frame<Bytes>, io::Error>> + Send + 'static,
{
    let body = StreamBody::new(body).boxed_unsync();
    Response::builder()
        .status(StatusCode::OK)
        .body(body)
        .map_err(|error| io::Error::other(error.to_string()))
}

#[tokio::main(flavor = "current_thread")]
async fn main() -> ProbeResult<()> {
    let manifest_path = match std::env::args_os().nth(1) {
        Some(path) => std::path::PathBuf::from(path),
        None => std::path::PathBuf::from("tests/native-core/manifest.json"),
    };
    let manifest: Value = serde_json::from_slice(&std::fs::read(manifest_path)?)?;
    let protocols = manifest["protocols"].as_array();
    if manifest["schema_version"].as_u64() != Some(1)
        || protocols.is_none_or(|protocols| {
            !protocols
                .iter()
                .any(|protocol| protocol.as_str() == Some("http/1.1"))
                || !protocols
                    .iter()
                    .any(|protocol| protocol.as_str() == Some("h2c-prior-knowledge"))
                || !protocols
                    .iter()
                    .any(|protocol| protocol.as_str() == Some("https/1.1"))
                || !protocols
                    .iter()
                    .any(|protocol| protocol.as_str() == Some("h2-tls"))
                || !protocols
                    .iter()
                    .any(|protocol| protocol.as_str() == Some("http3"))
        })
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "unsupported native-core manifest version or protocol",
        )
        .into());
    }
    let cases = manifest["cases"]
        .as_array()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "manifest has no cases"))?;
    if cases.is_empty() {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "manifest has no cases").into());
    }

    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let tls_listener = TcpListener::bind("127.0.0.1:0").await?;
    let tls_address = tls_listener.local_addr()?;
    let (tls_acceptor, tls_clients, quic_server_config) = test_tls_configs()?;
    let h3_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let h3_address = h3_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let app = contract_app(shutdown_sender.clone());
    let observed_errors = Arc::new(Mutex::new(Vec::new()));
    let error_log = Arc::clone(&observed_errors);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        let mut cause: Option<&(dyn Error + 'static)> = Some(event.error());
        let mut is_io_error = false;
        while let Some(error) = cause {
            if error.is::<io::Error>() {
                is_io_error = true;
                break;
            }
            cause = error.source();
        }
        if let Ok(mut observations) = error_log.lock() {
            observations.push(ObservedServerError {
                phase: event.phase(),
                peer_addr: event.peer_addr(),
                is_io_error,
                is_direct_io_error: event.error().is::<io::Error>(),
                has_error_source: event.error().source().is_some(),
                h3_error_code: h3_connection_error_code(event.error()),
                message: event.error().to_string(),
            });
        }
    });
    let clear_shutdown = shutdown_receiver.clone();
    let clear_errors = error_observer.clone();
    let clear_server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        app.clone(),
        shutdown_on_change(clear_shutdown),
        uvicorn_rs::ServerConfig {
            max_connections: 16,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: Some(clear_errors),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));
    let tls_errors = error_observer.clone();
    let tls_server = tokio::spawn(uvicorn_rs::serve_tls(
        tls_listener,
        tls_acceptor,
        app,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 16,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: Some(tls_errors),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));
    let h3_shutdown = shutdown_sender.subscribe();
    let h3_errors = error_observer;
    let h3_server = tokio::spawn(uvicorn_rs::serve_http3(
        h3_endpoint,
        contract_app(shutdown_sender.clone()),
        shutdown_on_change(h3_shutdown),
        uvicorn_rs::ServerConfig {
            max_connections: 16,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: Some(h3_errors),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let run_result = run_cases(
        address,
        tls_address,
        h3_address,
        &tls_clients,
        cases,
        &observed_errors,
    )
    .await;
    shutdown_sender.send_replace(true);
    let (clear_result, tls_result, h3_result) =
        tokio::time::timeout(Duration::from_secs(4), async {
            tokio::join!(clear_server, tls_server, h3_server)
        })
        .await?;
    run_result?;
    for server_result in [clear_result, tls_result, h3_result] {
        match server_result {
            Ok(Ok(())) => {}
            Ok(Err(error)) => return Err(error.into()),
            Err(error) => return Err(error.into()),
        }
    }

    for case in cases {
        let operation = required_str(case, "operation")?;
        if matches!(
            operation,
            "graceful-drain"
                | "http2-graceful-drain"
                | "http3-graceful-drain"
                | "graceful-timeout-abort"
                | "http3-graceful-timeout-abort"
        ) || operation.starts_with("native-lifecycle-")
            || operation == "native-service-error-propagation"
            || operation == "native-http3-alpn-contract"
            || operation == "native-http3-no-common-alpn-recovery"
            || operation == "native-http3-no-common-alpn-lifecycle-recovery"
            || operation == "native-http3-endpoint-close-lifecycle"
            || operation == "native-http3-idle-connection-shutdown-timeout"
            || operation == "native-http3-peer-goaway-drain"
            || operation == "native-http3-server-shutdown-open-connection"
            || operation == "native-http3-incomplete-request-recovery"
            || operation == "native-http3-response-send-cancel"
            || operation == "native-http1-tls-pending-handshake-shutdown"
            || operation == "native-http1-connection-slot-reuse"
            || operation == "native-http1-connection-task-reaping"
            || operation == "native-http1-service-panic-recovery"
            || operation == "native-http1-upgrade-session"
            || operation == "native-http1-websocket"
        {
            if operation.starts_with("native-lifecycle-") {
                run_isolated_lifecycle_case(case).await?;
            } else if operation == "native-service-error-propagation" {
                run_isolated_service_error_propagation_case(case).await?;
            } else if operation == "native-http1-connection-slot-reuse" {
                run_isolated_http1_connection_slot_reuse_case(case).await?;
            } else if operation == "native-http1-connection-task-reaping" {
                run_isolated_http1_connection_task_reaping_case(case).await?;
            } else if operation == "native-http1-service-panic-recovery" {
                run_isolated_http1_service_panic_recovery_case(case).await?;
            } else if operation == "native-http1-upgrade-session" {
                run_isolated_http1_upgrade_session_case(case).await?;
            } else if operation == "native-http1-websocket" {
                run_isolated_http1_websocket_case(case).await?;
            } else if operation == "native-http3-alpn-contract" {
                run_isolated_http3_alpn_case(case).await?;
            } else if operation == "native-http3-no-common-alpn-recovery" {
                run_isolated_http3_no_common_alpn_case(case).await?;
            } else if operation == "native-http3-no-common-alpn-lifecycle-recovery" {
                run_isolated_http3_no_common_alpn_lifecycle_case(case).await?;
            } else if operation == "native-http3-endpoint-close-lifecycle" {
                run_isolated_http3_endpoint_close_lifecycle_case(case).await?;
            } else if operation == "native-http3-idle-connection-shutdown-timeout" {
                run_isolated_http3_idle_connection_shutdown_timeout_case(case).await?;
            } else if operation == "native-http3-peer-goaway-drain" {
                run_isolated_http3_peer_goaway_case(case).await?;
            } else if operation == "native-http3-server-shutdown-open-connection" {
                run_isolated_http3_server_shutdown_case(case).await?;
            } else if operation == "native-http3-incomplete-request-recovery" {
                run_isolated_http3_incomplete_request_recovery_case(case).await?;
            } else if operation == "native-http3-response-send-cancel" {
                run_isolated_http3_response_send_cancel_case(case).await?;
            } else if operation == "native-http1-tls-pending-handshake-shutdown" {
                run_isolated_tls_pending_handshake_shutdown_case(case).await?;
            } else if operation == "graceful-timeout-abort" {
                run_isolated_graceful_timeout_case(case).await?;
            } else if operation == "http3-graceful-timeout-abort" {
                run_isolated_http3_graceful_timeout_case(case).await?;
            } else {
                run_isolated_graceful_case(case).await?;
            }
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {}", required_str(case, "id")?)?;
            output.flush()?;
        }
    }
    Ok(())
}

fn lifecycle_fixture() -> LifecycleFixture {
    lifecycle_fixture_with_behaviors(
        LifecycleHookBehavior::Complete,
        LifecycleHookBehavior::Complete,
    )
}

fn lifecycle_fixture_with_behaviors(
    startup_behavior: LifecycleHookBehavior,
    shutdown_behavior: LifecycleHookBehavior,
) -> LifecycleFixture {
    let (active_request, _) = watch::channel(false);
    let (release_request, _) = watch::channel(false);
    let (http3_response_cancel_release, _) = watch::channel(false);
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let state = Arc::new(LifecycleState {
        startup_completed: AtomicBool::new(false),
        shutdown_completed: AtomicBool::new(false),
        startup_hook_dropped: Arc::new(AtomicBool::new(false)),
        shutdown_hook_dropped: Arc::new(AtomicBool::new(false)),
        requests_started: AtomicUsize::new(0),
        http3_response_cancel_pending: AtomicBool::new(false),
        http3_response_cancel_release,
        readiness_error_armed: AtomicBool::new(false),
        readiness_gate: Mutex::new(ReadinessGate::default()),
        response_body_dropped: Arc::new(AtomicBool::new(false)),
        shutdown_saw_response_body_drop: AtomicBool::new(false),
        active_request,
        release_request,
        events: Mutex::new(Vec::new()),
        observed_lifecycle_errors: Mutex::new(Vec::new()),
        readiness_errors: Mutex::new(Vec::new()),
        application_errors: Mutex::new(Vec::new()),
        connection_errors: Mutex::new(Vec::new()),
    });
    LifecycleFixture {
        app: LifecycleApp {
            state: Arc::clone(&state),
        },
        hooks: Arc::new(LifecycleHooks {
            state: Arc::clone(&state),
            startup_behavior,
            shutdown_behavior,
        }),
        state,
        shutdown_sender,
        shutdown_receiver,
    }
}

fn lifecycle_server_config(
    hooks: Arc<LifecycleHooks>,
    case: &Value,
) -> ProbeResult<uvicorn_rs::ServerConfig> {
    let hook_timeout = case["hook_timeout_ms"]
        .as_u64()
        .map(Duration::from_millis)
        .unwrap_or(Duration::from_secs(2));
    let graceful_timeout = case["graceful_timeout_ms"]
        .as_u64()
        .map(Duration::from_millis)
        .unwrap_or(Duration::from_secs(2));
    let error_observer: Option<ServerErrorObserver> = match required_str(case, "operation")? {
        "native-lifecycle-startup-panic" | "native-lifecycle-shutdown-panic" => {
            let state = Arc::clone(&hooks.state);
            Some(Arc::new(move |event: ServerErrorEvent<'_>| {
                if let Ok(mut observations) = state.observed_lifecycle_errors.lock() {
                    observations.push((
                        event.phase(),
                        event.error().to_string(),
                        event.error().source().is_some(),
                    ));
                }
            }))
        }
        "native-lifecycle-readiness-error" => {
            let state = Arc::clone(&hooks.state);
            Some(Arc::new(move |event: ServerErrorEvent<'_>| {
                if let Ok(mut observations) = state.readiness_errors.lock() {
                    observations.push((
                        event.phase(),
                        event.error().is::<io::Error>(),
                        event.error().to_string(),
                    ));
                }
            }))
        }
        "native-lifecycle-service-and-response-body-errors" => {
            let state = Arc::clone(&hooks.state);
            Some(Arc::new(move |event: ServerErrorEvent<'_>| {
                if let Ok(mut observations) = state.application_errors.lock() {
                    observations.push((
                        event.phase(),
                        event.error().is::<io::Error>(),
                        event.error().to_string(),
                    ));
                }
            }))
        }
        "native-lifecycle-http3-connection-init-failure-recovery" => {
            let state = Arc::clone(&hooks.state);
            Some(Arc::new(move |event: ServerErrorEvent<'_>| {
                if let Ok(mut observations) = state.connection_errors.lock() {
                    observations.push((event.phase(), event.peer_addr()));
                }
            }))
        }
        _ => None,
    };
    Ok(uvicorn_rs::ServerConfig {
        max_connections: 8,
        graceful_shutdown_timeout: graceful_timeout,
        application_startup_timeout: hook_timeout,
        application_shutdown_timeout: hook_timeout,
        application_lifecycle: Some(hooks),
        error_observer,
        service_error_policy: uvicorn_rs::ServiceErrorPolicy::RespondInternalServerError,
    })
}

async fn run_isolated_lifecycle_case(case: &Value) -> ProbeResult<()> {
    match required_str(case, "operation")? {
        "native-lifecycle-startup-error" => {
            return run_lifecycle_startup_fault_case(case, LifecycleHookBehavior::Fail).await;
        }
        "native-lifecycle-startup-timeout" => {
            return run_lifecycle_startup_fault_case(case, LifecycleHookBehavior::Wait).await;
        }
        "native-lifecycle-startup-panic" => {
            return run_lifecycle_startup_fault_case(case, LifecycleHookBehavior::Panic).await;
        }
        "native-lifecycle-shutdown-error" => {
            return run_lifecycle_shutdown_fault_case(case, LifecycleHookBehavior::Fail).await;
        }
        "native-lifecycle-shutdown-timeout" => {
            return run_lifecycle_shutdown_fault_case(case, LifecycleHookBehavior::Wait).await;
        }
        "native-lifecycle-shutdown-panic" => {
            return run_lifecycle_shutdown_fault_case(case, LifecycleHookBehavior::Panic).await;
        }
        "native-lifecycle-server-and-shutdown-error" => {
            return run_lifecycle_server_and_shutdown_error_case(case).await;
        }
        "native-lifecycle-server-timeout" => {
            return run_lifecycle_server_timeout_case(case).await;
        }
        "native-lifecycle-service-and-response-body-errors" => {
            return run_lifecycle_service_and_response_body_errors_case(case).await;
        }
        "native-lifecycle-http3-connection-init-failure-recovery" => {
            return run_lifecycle_http3_connection_init_failure_case(case).await;
        }
        "native-lifecycle-http3-pending-handshake-shutdown" => {
            return run_lifecycle_http3_pending_handshake_shutdown_case(case).await;
        }
        "native-lifecycle-http3-invalid-config" => {
            return run_lifecycle_http3_invalid_config_case(case).await;
        }
        "native-lifecycle-hooks-omitted" => {
            return run_lifecycle_http3_without_hooks_case(case).await;
        }
        "native-lifecycle-websocket" => return run_lifecycle_websocket_case(case).await,
        "native-lifecycle-readiness-error" => {
            return run_lifecycle_readiness_error_case(case).await;
        }
        "native-lifecycle-readiness-pending" => {
            return run_lifecycle_readiness_case(case).await;
        }
        "native-lifecycle-drain" => {}
        operation => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown native lifecycle operation {operation:?}"),
            )
            .into());
        }
    }
    match required_str(case, "protocol")? {
        "http/1.1" => run_lifecycle_http1_case(case).await,
        "https/1.1" => run_lifecycle_https_case(case).await,
        "h2c-prior-knowledge" => run_lifecycle_http2_case(case).await,
        "http3" => run_lifecycle_http3_case(case).await,
        protocol => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("unsupported lifecycle protocol {protocol:?}"),
        )
        .into()),
    }
}

async fn run_isolated_http1_connection_slot_reuse_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 1,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow = async {
        let path = required_str(case, "path")?;
        let mut first = TcpStream::connect(address).await?;
        let first_request = format!("GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n");
        first.write_all(first_request.as_bytes()).await?;

        let (first_status, first_headers) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_head(&mut first),
        )
        .await
        .map_err(|_| {
            io::Error::new(io::ErrorKind::TimedOut, "first keep-alive response timed out")
        })??;
        let (first_body, first_complete) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_body(&mut first, &first_headers),
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "first keep-alive body timed out"))??;
        let expected_status = required_status(case, "expected_status")?;
        let expected_body = required_str(case, "expected_body")?;
        if first_status != expected_status
            || first_body != expected_body.as_bytes()
            || !first_complete
        {
            return Err(io::Error::other(format!(
                "{}: first persistent response did not match the configured contract",
                required_str(case, "id")?
            ))
            .into());
        }

        let mut waiting = TcpStream::connect(address).await?;
        let waiting_request = format!(
            "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
        );
        waiting.write_all(waiting_request.as_bytes()).await?;
        let blocked_ms = case["blocked_ms"].as_u64().ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "blocked_ms is missing")
        })?;
        let mut probe = [0_u8; 1];
        match tokio::time::timeout(Duration::from_millis(blocked_ms), waiting.peek(&mut probe)).await
        {
            Err(_) => {}
            Ok(Ok(0)) => {
                return Err(io::Error::other(format!(
                    "{}: waiting client was disconnected while the sole connection slot was occupied",
                    required_str(case, "id")?
                ))
                .into());
            }
            Ok(Ok(_)) => {
                return Err(io::Error::other(format!(
                    "{}: server responded while max_connections=1 was occupied",
                    required_str(case, "id")?
                ))
                .into());
            }
            Ok(Err(error)) => return Err(error.into()),
        }

        drop(first);
        let (status, headers) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_head(&mut waiting),
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "waiting response head timed out"))??;
        let (body, complete) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_body(&mut waiting, &headers),
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "waiting response body timed out"))??;
        if status != expected_status || body != expected_body.as_bytes() || !complete {
            return Err(io::Error::other(format!(
                "{}: queued client did not succeed after the keep-alive peer closed",
                required_str(case, "id")?
            ))
            .into());
        }

        let reconnect_requests = case["reconnect_requests"]
            .as_u64()
            .filter(|count| (1_u64..=128).contains(count))
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "reconnect_requests must be between 1 and 128",
                )
            })?;
        for request_index in 0..reconnect_requests {
            let mut reconnect = TcpStream::connect(address).await?;
            let request = format!(
                "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            );
            reconnect.write_all(request.as_bytes()).await?;
            let (reconnect_status, reconnect_headers) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_head(&mut reconnect),
            )
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!("reconnect {request_index} response head timed out"),
                )
            })??;
            let (reconnect_body, reconnect_complete) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_body(&mut reconnect, &reconnect_headers),
            )
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!("reconnect {request_index} response body timed out"),
                )
            })??;
            if reconnect_status != expected_status
                || reconnect_body != expected_body.as_bytes()
                || !reconnect_complete
            {
                return Err(io::Error::other(format!(
                    "{}: reconnect {request_index} returned an unexpected response",
                    required_str(case, "id")?
                ))
                .into());
            }

            let mut eof_probe = [0_u8; 1];
            match tokio::time::timeout(Duration::from_secs(2), reconnect.read(&mut eof_probe)).await
            {
                Err(_) => {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        format!("reconnect {request_index} did not close as requested"),
                    )
                    .into())
                }
                Ok(Ok(0)) => {}
                Ok(Ok(_)) => {
                    return Err(io::Error::other(format!(
                        "{}: reconnect {request_index} remained open after Connection: close",
                        required_str(case, "id")?
                    ))
                    .into())
                }
                Ok(Err(error)) => return Err(error.into()),
            }
        }
        shutdown_sender.send_replace(true);
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    if workflow.is_err() {
        shutdown_sender.send_replace(true);
    }
    let server_result = tokio::time::timeout(Duration::from_secs(2), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/1 slot-reuse server did not stop",
            )
        })??;
    workflow?;
    server_result?;
    Ok(())
}

async fn run_isolated_http1_connection_task_reaping_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let max_connections = required_u64(case, "max_connections")?
        .try_into()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "max_connections is too large"))?;
    let held_connection_count = case["held_connection_count"]
        .as_u64()
        .filter(|count| (1_u64..=64).contains(count))
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "held_connection_count must be between 1 and 64",
            )
        })?;
    if max_connections as u64 <= held_connection_count {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "max_connections must leave a slot for the completion probe",
        )
        .into());
    }
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow: ProbeResult<()> = async {
        let held_path = required_str(case, "held_path")?;
        let mut held_connections = Vec::with_capacity(held_connection_count as usize);
        for _ in 0..held_connection_count {
            let mut held = tokio::time::timeout(
                Duration::from_secs(2),
                TcpStream::connect(address),
            )
            .await??;
            let held_request = format!(
                "GET {held_path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            );
            held.write_all(held_request.as_bytes()).await?;
            held_connections.push(held);
        }

        let state_path = required_str(case, "state_path")?;
        let expected_hold_state = required_str(case, "expected_hold_state")?.as_bytes();
        let state_deadline = Instant::now() + Duration::from_secs(2);
        loop {
            let mut state = tokio::time::timeout(
                Duration::from_secs(2),
                request(address, "GET", state_path, b""),
            )
            .await??;
            let (status, headers) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_head(&mut state),
            )
            .await??;
            let (body, complete) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_body(&mut state, &headers),
            )
            .await??;
            if status != StatusCode::OK.as_u16() || !complete {
                return Err(io::Error::other(
                    "held-request state probe did not complete successfully",
                )
                .into());
            }
            if body == expected_hold_state {
                let mut eof_probe = [0_u8; 1];
                match tokio::time::timeout(Duration::from_secs(2), state.read(&mut eof_probe)).await
                {
                    Ok(Ok(0)) => {}
                    Ok(Ok(_)) => {
                        return Err(io::Error::other(
                            "held-request state probe stayed open after Connection: close",
                        )
                        .into());
                    }
                    Ok(Err(error)) => return Err(error.into()),
                    Err(_) => {
                        return Err(io::Error::new(
                            io::ErrorKind::TimedOut,
                            "held-request state probe did not close",
                        )
                        .into());
                    }
                }
                break;
            }
            if Instant::now() >= state_deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!("held request did not reach the configured state: {body:?}"),
                )
                .into());
            }
            tokio::task::yield_now().await;
        }

        let probe_path = required_str(case, "probe_path")?;
        let expected_status = required_status(case, "expected_status")?;
        let expected_body = required_str(case, "expected_body")?.as_bytes();
        let probe_count = case["probe_count"]
            .as_u64()
            .filter(|count| (1_u64..=128).contains(count))
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "probe_count must be between 1 and 128",
                )
            })?;
        for probe_index in 0..probe_count {
            let mut probe = tokio::time::timeout(
                Duration::from_secs(2),
                request(address, "GET", probe_path, b""),
            )
            .await??;
            let (status, headers) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_head(&mut probe),
            )
            .await??;
            let (body, complete) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_body(&mut probe, &headers),
            )
            .await??;
            if status != expected_status || body != expected_body || !complete {
                return Err(io::Error::other(format!(
                    "probe {probe_index} returned an unexpected response while its sibling request was held"
                ))
                .into());
            }
            let mut eof_probe = [0_u8; 1];
            match tokio::time::timeout(Duration::from_secs(2), probe.read(&mut eof_probe)).await {
                Ok(Ok(0)) => {}
                Ok(Ok(_)) => {
                    return Err(io::Error::other(format!(
                        "probe {probe_index} stayed open after Connection: close"
                    ))
                    .into());
                }
                Ok(Err(error)) => return Err(error.into()),
                Err(_) => {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        format!("probe {probe_index} did not close"),
                    )
                    .into());
                }
            }
            tokio::task::yield_now().await;
        }

        let mut release = tokio::time::timeout(
            Duration::from_secs(2),
            request(address, "GET", required_str(case, "release_path")?, b""),
        )
        .await??;
        let (release_status, release_headers) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_head(&mut release),
        )
        .await??;
        let (release_body, release_complete) = tokio::time::timeout(
            Duration::from_secs(2),
            read_response_body(&mut release, &release_headers),
        )
        .await??;
        if release_status != expected_status
            || release_body != required_str(case, "expected_release_body")?.as_bytes()
            || !release_complete
        {
            return Err(io::Error::other("held response release endpoint did not match its contract").into());
        }

        for (held_index, held) in held_connections.iter_mut().enumerate() {
            let (held_status, held_headers) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_head(held),
            )
            .await??;
            let (held_body, held_complete) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_body(held, &held_headers),
            )
            .await??;
            if held_status != expected_status
                || held_body != required_str(case, "expected_held_body")?.as_bytes()
                || !held_complete
            {
                return Err(io::Error::other(format!(
                    "released held response {held_index} did not complete"
                ))
                .into());
            }
            let mut eof_probe = [0_u8; 1];
            match tokio::time::timeout(Duration::from_secs(2), held.read(&mut eof_probe)).await {
                Ok(Ok(0)) => {}
                Ok(Ok(_)) => {
                    return Err(io::Error::other(format!(
                        "released held connection {held_index} remained open after Connection: close"
                    ))
                    .into());
                }
                Ok(Err(error)) => return Err(error.into()),
                Err(_) => {
                    return Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        format!("released held connection {held_index} did not close"),
                    )
                    .into());
                }
            }
        }
        drop(held_connections);
        tokio::time::sleep(Duration::from_millis(50)).await;
        Ok(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(
        Duration::from_millis(required_u64(case, "server_wait_ms")?),
        server,
    )
    .await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/1 connection-reaper server did not stop",
        )
        .into()),
    }
}

async fn run_isolated_http1_service_panic_recovery_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig::default(),
    ));

    let workflow: ProbeResult<()> = async {
        let mut failed_connection =
            tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
        let fault_request = format!(
            "GET {} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
            required_str(case, "path")?
        );
        failed_connection
            .write_all(fault_request.as_bytes())
            .await?;

        let mut fault_response = Vec::new();
        tokio::time::timeout(
            Duration::from_secs(2),
            failed_connection.read_to_end(&mut fault_response),
        )
        .await??;
        if !fault_response.is_empty() {
            return Err(io::Error::other(format!(
                "{}: panicking service unexpectedly wrote an HTTP response: {:?}",
                required_str(case, "id")?,
                String::from_utf8_lossy(&fault_response)
            ))
            .into());
        }

        let (status, body) = tokio::time::timeout(
            Duration::from_secs(2),
            lifecycle_http1_get(address, required_str(case, "recovery_path")?),
        )
        .await??;
        let expected_status = required_status(case, "recovery_status")?;
        let expected_body = required_str(case, "recovery_body")?;
        if status != expected_status || body != expected_body.as_bytes() {
            return Err(io::Error::other(format!(
                "{}: listener failed to recover after service panic: status={status}, body={:?}",
                required_str(case, "id")?,
                String::from_utf8_lossy(&body)
            ))
            .into());
        }
        Ok(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let shutdown_result = tokio::time::timeout(Duration::from_secs(3), server).await;
    workflow?;
    match shutdown_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(error) => Err(error.into()),
    }
}

async fn run_isolated_http1_upgrade_session_case(case: &Value) -> ProbeResult<()> {
    let scenario = required_str(case, "scenario")?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let observed_errors = Arc::new(Mutex::new(Vec::<ObservedServerError>::new()));
    let error_log = Arc::clone(&observed_errors);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        let mut cause: Option<&(dyn Error + 'static)> = Some(event.error());
        let mut is_io_error = false;
        while let Some(error) = cause {
            if error.is::<io::Error>() {
                is_io_error = true;
                break;
            }
            cause = error.source();
        }
        if let Ok(mut observations) = error_log.lock() {
            observations.push(ObservedServerError {
                phase: event.phase(),
                peer_addr: event.peer_addr(),
                is_io_error,
                is_direct_io_error: event.error().is::<io::Error>(),
                has_error_source: event.error().source().is_some(),
                h3_error_code: None,
                message: event.error().to_string(),
            });
        }
    });
    let mut server_config = uvicorn_rs::ServerConfig {
        graceful_shutdown_timeout: Duration::from_millis(500),
        ..uvicorn_rs::ServerConfig::default()
    };
    server_config.error_observer = Some(error_observer);
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        server_config,
    ));
    let mut registration_outcome = state.upgrade_registration_outcome.subscribe();

    let workflow: ProbeResult<()> = async {
        match scenario {
            "graceful-session" => {
                run_http1_graceful_upgrade_case(address, case, &shutdown_sender).await
            }
            "session-handler-error" => {
                run_http1_upgrade_error_case(address, case, &observed_errors, true).await
            }
            "session-handler-panic" => run_http1_upgrade_panic_case(address, case).await,
            "upgrade-not-available" => {
                run_http1_upgrade_error_case(address, case, &observed_errors, false).await
            }
            "registration-after-close" => {
                run_http1_upgrade_registration_after_close_case(
                    address,
                    case,
                    &mut registration_outcome,
                )
                .await
            }
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("unknown HTTP/1 upgrade scenario: {scenario}"),
            )
            .into()),
        }
    }
    .await;

    shutdown_sender.send_replace(true);
    let wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let server_result = tokio::time::timeout(Duration::from_millis(wait_ms), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/1 upgraded-session server did not stop",
            )
        })??;
    workflow?;
    server_result?;
    Ok(())
}

async fn open_http1_upgrade_case_connection(
    address: SocketAddr,
    case: &Value,
    request_upgrade: bool,
) -> ProbeResult<(TcpStream, u16, std::collections::HashMap<String, String>)> {
    let request_count = required_request_count(case)?;
    if request_upgrade && request_count != 1 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "upgraded HTTP/1 cases must send exactly one request",
        )
        .into());
    }
    let mut client =
        tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
    let request = if request_upgrade {
        format!(
            "GET {} HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: uvicorn-rs-test\r\n\r\n",
            required_str(case, "path")?
        )
    } else {
        let connection = if request_count > 1 {
            "keep-alive"
        } else {
            "close"
        };
        format!(
            "GET {} HTTP/1.1\r\nHost: localhost\r\nConnection: {connection}\r\n\r\n",
            required_str(case, "path")?
        )
    };
    client.write_all(request.as_bytes()).await?;
    let (status, headers) =
        tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client)).await??;
    Ok((client, status, headers))
}

fn verify_http1_upgrade_headers(
    case: &Value,
    status: u16,
    headers: &std::collections::HashMap<String, String>,
) -> ProbeResult<()> {
    let expected_status = required_status(case, "expected_status")?;
    let expected_upgrade = required_str(case, "expected_upgrade")?;
    let accepted_upgrade = headers
        .get("upgrade")
        .is_some_and(|value| value.eq_ignore_ascii_case(expected_upgrade));
    let accepted_connection = headers
        .get("connection")
        .is_some_and(|value| value.eq_ignore_ascii_case("upgrade"));
    if status != expected_status || !accepted_upgrade || !accepted_connection {
        return Err(io::Error::other(format!(
            "{}: server did not accept the configured HTTP/1 upgrade",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_http1_graceful_upgrade_case(
    address: SocketAddr,
    case: &Value,
    shutdown_sender: &watch::Sender<bool>,
) -> ProbeResult<()> {
    let (mut client, status, headers) =
        open_http1_upgrade_case_connection(address, case, true).await?;
    verify_http1_upgrade_headers(case, status, &headers)?;

    client.write_all(b"ping").await?;
    let expected_pong = required_str(case, "expected_pong")?.as_bytes();
    let mut pong = vec![0; expected_pong.len()];
    tokio::time::timeout(Duration::from_secs(2), client.read_exact(&mut pong)).await??;
    if pong != expected_pong {
        return Err(io::Error::other(format!(
            "{}: upgraded session did not echo its live connection state",
            required_str(case, "id")?
        ))
        .into());
    }

    shutdown_sender.send_replace(true);
    let expected_shutdown = required_str(case, "expected_shutdown")?.as_bytes();
    let mut shutdown = vec![0; expected_shutdown.len()];
    tokio::time::timeout(Duration::from_secs(2), client.read_exact(&mut shutdown)).await??;
    if shutdown != expected_shutdown {
        return Err(io::Error::other(format!(
            "{}: upgraded session did not observe graceful shutdown while its connection remained open",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut trailing = [0; 1];
    let read = tokio::time::timeout(Duration::from_secs(2), client.read(&mut trailing)).await??;
    if read != 0 {
        return Err(io::Error::other(format!(
            "{}: upgraded transport remained open after the registered session ended",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_http1_upgrade_error_case(
    address: SocketAddr,
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
    request_upgrade: bool,
) -> ProbeResult<()> {
    let (mut client, status, headers) =
        open_http1_upgrade_case_connection(address, case, request_upgrade).await?;
    let expected_status = required_status(case, "expected_status")?;
    if status != expected_status {
        return Err(io::Error::other(format!(
            "{}: expected status {expected_status}, got {status}",
            required_str(case, "id")?
        ))
        .into());
    }

    if request_upgrade {
        verify_http1_upgrade_headers(case, status, &headers)?;
        let mut trailing = Vec::new();
        tokio::time::timeout(Duration::from_secs(2), client.read_to_end(&mut trailing)).await??;
        if !trailing.is_empty() {
            return Err(io::Error::other(format!(
                "{}: failed upgrade session wrote unexpected bytes: {:?}",
                required_str(case, "id")?,
                trailing
            ))
            .into());
        }
    } else {
        let request_count = required_request_count(case)?;
        let expected_body = required_str(case, "expected_response_body")?.as_bytes();
        let mut response = Some((status, headers));
        for request_index in 0..request_count {
            let (response_status, response_headers) = match response.take() {
                Some(response) => response,
                None => {
                    let connection = if request_index + 1 == request_count {
                        "close"
                    } else {
                        "keep-alive"
                    };
                    let request = format!(
                        "GET {} HTTP/1.1\r\nHost: localhost\r\nConnection: {connection}\r\n\r\n",
                        required_str(case, "path")?
                    );
                    client.write_all(request.as_bytes()).await?;
                    tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client))
                        .await??
                }
            };
            if response_status != expected_status {
                return Err(io::Error::other(format!(
                    "{}: request {} expected status {expected_status}, got {response_status}",
                    required_str(case, "id")?,
                    request_index + 1
                ))
                .into());
            }
            let (body, complete) = tokio::time::timeout(
                Duration::from_secs(2),
                read_response_body(&mut client, &response_headers),
            )
            .await??;
            if !complete || body != expected_body {
                return Err(io::Error::other(format!(
                    "{}: non-upgrade response {} body mismatch: complete={complete}, body={:?}",
                    required_str(case, "id")?,
                    request_index + 1,
                    String::from_utf8_lossy(&body)
                ))
                .into());
            }
        }
    }

    let expected_error = required_str(case, "expected_session_error")?;
    let observation = wait_for_http1_upgrade_error(observed_errors, expected_error).await?;
    if observation.phase != ServerErrorPhase::Connection || observation.peer_addr.is_none() {
        return Err(io::Error::other(format!(
            "{}: expected a connection-phase upgrade error, got {observation:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    if let Some(expected_source_io_error) = case.get("expected_source_io_error") {
        let expected_source_io_error = expected_source_io_error.as_bool().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_source_io_error must be a boolean",
            )
        })?;
        if observation.is_io_error != expected_source_io_error {
            return Err(io::Error::other(format!(
                "{}: upgrade error source-chain contract differed: expected io error={expected_source_io_error}, observed={observation:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }

    verify_http1_upgrade_listener_recovers(address, case).await
}

async fn run_http1_upgrade_panic_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let (mut client, status, headers) =
        open_http1_upgrade_case_connection(address, case, true).await?;
    verify_http1_upgrade_headers(case, status, &headers)?;

    let mut trailing = Vec::new();
    tokio::time::timeout(Duration::from_secs(2), client.read_to_end(&mut trailing)).await??;
    if !trailing.is_empty() {
        return Err(io::Error::other(format!(
            "{}: panicking upgraded session wrote unexpected bytes: {:?}",
            required_str(case, "id")?,
            trailing
        ))
        .into());
    }

    verify_http1_upgrade_listener_recovers(address, case).await
}

async fn run_tls_http1_upgrade_session_error_case(
    address: SocketAddr,
    tls_clients: &TlsClients,
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
) -> ProbeResult<()> {
    let mut client = connect_tls_http1(address, &tls_clients.http1).await?;
    let request = format!(
        "GET {} HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: uvicorn-rs-test\r\n\r\n",
        required_str(case, "path")?
    );
    client.write_all(request.as_bytes()).await?;
    let (status, headers) =
        tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client)).await??;
    verify_http1_upgrade_headers(case, status, &headers)?;

    let mut trailing = Vec::new();
    match tokio::time::timeout(Duration::from_secs(2), client.read_to_end(&mut trailing)).await {
        Ok(Ok(_)) => {}
        Ok(Err(error)) if error.kind() == io::ErrorKind::UnexpectedEof => {}
        Ok(Err(error)) => return Err(error.into()),
        Err(error) => return Err(error.into()),
    }
    if !trailing.is_empty() {
        return Err(io::Error::other(format!(
            "{}: failed TLS upgrade session wrote unexpected bytes: {:?}",
            required_str(case, "id")?,
            trailing
        ))
        .into());
    }

    let expected_error = required_str(case, "expected_session_error")?;
    let observation = wait_for_http1_upgrade_error(observed_errors, expected_error).await?;
    if observation.phase != ServerErrorPhase::Connection || observation.peer_addr.is_none() {
        return Err(io::Error::other(format!(
            "{}: expected a TLS connection-phase upgrade error, got {observation:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    let expected_source_io_error = case["expected_source_io_error"].as_bool().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_source_io_error must be a boolean",
        )
    })?;
    if observation.is_io_error != expected_source_io_error {
        return Err(io::Error::other(format!(
            "{}: TLS upgrade error source-chain contract differed: expected io error={expected_source_io_error}, observed={observation:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn connect_tls_http1(
    address: SocketAddr,
    connector: &TlsConnector,
) -> ProbeResult<tokio_rustls::client::TlsStream<TcpStream>> {
    let tcp_stream =
        tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
    let server_name = ServerName::try_from("localhost".to_owned())?;
    Ok(tokio::time::timeout(
        Duration::from_secs(2),
        connector.connect(server_name, tcp_stream),
    )
    .await??)
}

async fn wait_for_http1_upgrade_error(
    observed_errors: &Mutex<Vec<ObservedServerError>>,
    expected_message: &str,
) -> ProbeResult<ObservedServerError> {
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let observed = observed_errors
            .lock()
            .map_err(|_| io::Error::other("upgrade error-observation lock was poisoned"))?
            .iter()
            .find(|error| {
                error.phase == ServerErrorPhase::Connection
                    && error.message.contains(expected_message)
            })
            .cloned();
        if let Some(observed) = observed {
            return Ok(observed);
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("no connection error contained {expected_message:?}"),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

async fn verify_http1_upgrade_listener_recovers(
    address: SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let mut client =
        tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
    client
        .write_all(b"GET /ready HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        .await?;
    let (status, headers) =
        tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client)).await??;
    let (body, complete) = tokio::time::timeout(
        Duration::from_secs(2),
        read_response_body(&mut client, &headers),
    )
    .await??;
    if status != 200 || body != b"ready\n" || !complete {
        return Err(io::Error::other(format!(
            "{}: listener failed recovery request after upgrade error: status={status}, body={:?}, complete={complete}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http1_upgrade_registration_after_close_case(
    address: SocketAddr,
    case: &Value,
    registration_outcome: &mut watch::Receiver<Option<String>>,
) -> ProbeResult<()> {
    let (mut client, status, headers) =
        open_http1_upgrade_case_connection(address, case, false).await?;
    let expected_status = required_status(case, "expected_status")?;
    let (body, complete) = tokio::time::timeout(
        Duration::from_secs(2),
        read_response_body(&mut client, &headers),
    )
    .await??;
    let expected_body = required_str(case, "expected_response_body")?.as_bytes();
    if status != expected_status || !complete || body != expected_body {
        return Err(io::Error::other(format!(
            "{}: registration setup response mismatch: status={status}, complete={complete}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let outcome = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if let Some(outcome) = registration_outcome.borrow_and_update().clone() {
                return Ok::<_, io::Error>(outcome);
            }
            registration_outcome
                .changed()
                .await
                .map_err(|_| io::Error::other("registration outcome channel closed"))?;
        }
    })
    .await??;
    let expected_outcome = required_str(case, "expected_registration_error")?;
    if outcome != expected_outcome {
        return Err(io::Error::other(format!(
            "{}: late upgrade registration result mismatch: {outcome:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_isolated_http1_websocket_case(case: &Value) -> ProbeResult<()> {
    let scenario = required_str(case, "scenario")?;
    let fault_point = case
        .get("fault")
        .and_then(|fault| fault.get("point"))
        .and_then(Value::as_str);
    if fault_point.is_some_and(|point| point != "websocket.receive.close-reply.flush")
        || (scenario == "close-reply-flush-failure"
            && fault_point != Some("websocket.receive.close-reply.flush"))
        || (fault_point.is_some() && scenario != "close-reply-flush-failure")
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "native WebSocket fault metadata differs from its scenario",
        )
        .into());
    }
    #[cfg(coverage)]
    let fault_armed = match fault_point {
        Some("websocket.receive.close-reply.flush") => uvicorn_rs::arm_close_reply_flush_fault(),
        None => false,
        Some(_) => false,
    };
    #[cfg(not(coverage))]
    if fault_point.is_some() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "native fault contracts require an instrumented coverage build",
        )
        .into());
    }
    #[cfg(coverage)]
    if fault_point.is_some() && !fault_armed {
        return Err(io::Error::other("native WebSocket coverage fault was already armed").into());
    }
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_millis(500),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let mut registration_outcome = state.upgrade_registration_outcome.subscribe();
    let mut websocket_error_observation = state.websocket_error_observation.subscribe();
    let workflow: ProbeResult<()> = async {
        match scenario {
            "message-exchange" => run_native_websocket_exchange_case(address, case).await,
            "malformed-client-frame" => {
                run_native_websocket_malformed_frame_case(
                    address,
                    case,
                    &mut websocket_error_observation,
                )
                .await
            }
            "close-reply-flush-failure" => {
                run_native_websocket_close_reply_flush_failure_case(
                    address,
                    case,
                    &mut websocket_error_observation,
                )
                .await
            }
            "accept-after-close" => {
                run_native_websocket_accept_after_close_case(
                    address,
                    case,
                    &mut registration_outcome,
                )
                .await
            }
            "graceful-shutdown" => {
                run_native_websocket_shutdown_case(address, case, &shutdown_sender).await
            }
            "invalid-key"
            | "unoffered-subprotocol"
            | "invalid-method"
            | "missing-upgrade-capability"
            | "invalid-version"
            | "missing-version-header"
            | "duplicate-version-header"
            | "invalid-key-size"
            | "missing-key-header"
            | "duplicate-key-header"
            | "header-capacity"
            | "accept-header-capacity"
            | "missing-upgrade-token"
            | "wrong-upgrade-token"
            | "empty-subprotocol-token"
            | "invalid-subprotocol-token"
            | "invalid-selected-subprotocol-header-value"
            | "reserved-response-header"
            | "duplicate-subprotocol" => run_native_websocket_rejection_case(address, case).await,
            _ => Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("unknown native WebSocket scenario: {scenario}"),
            )
            .into()),
        }
    }
    .await;

    shutdown_sender.send_replace(true);
    let wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let server_wait = tokio::time::timeout(Duration::from_millis(wait_ms), server).await;
    #[cfg(coverage)]
    if fault_armed {
        if !uvicorn_rs::finish_close_reply_flush_fault() {
            return Err(io::Error::other(
                "native WebSocket close-reply flush fault was not consumed",
            )
            .into());
        }
        println!("FAULT_CONSUMED websocket.receive.close-reply.flush");
    }
    let server_result = server_wait.map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            "native HTTP/1 WebSocket server did not stop",
        )
    })??;
    workflow?;
    server_result?;
    Ok(())
}

async fn open_native_websocket_handshake(
    address: SocketAddr,
    case: &Value,
) -> ProbeResult<(TcpStream, u16, std::collections::HashMap<String, String>)> {
    let mut client =
        tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
    let path = required_str(case, "path")?;
    let key = required_str(case, "request_key")?;
    let method = case.get("method").and_then(Value::as_str).unwrap_or("GET");
    let connection_header = case
        .get("connection_header")
        .and_then(Value::as_str)
        .unwrap_or("keep-alive, Upgrade");
    let upgrade_header = case
        .get("upgrade_header")
        .and_then(Value::as_str)
        .unwrap_or("websocket");
    let websocket_version = case
        .get("request_websocket_version")
        .and_then(Value::as_str)
        .unwrap_or("13");
    let key_values = input_string_values(case, "request_websocket_key_values", key)?;
    let version_values =
        input_string_values(case, "request_websocket_version_values", websocket_version)?;
    let key_headers = render_header_lines("Sec-WebSocket-Key", &key_values);
    let version_headers = render_header_lines("Sec-WebSocket-Version", &version_values);
    let protocol = case
        .get("offered_subprotocol")
        .and_then(Value::as_str)
        .map(|protocol| format!("Sec-WebSocket-Protocol: {protocol}\r\n"))
        .unwrap_or_default();
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: {connection_header}\r\nUpgrade: {upgrade_header}\r\n{key_headers}{version_headers}{protocol}\r\n"
    );
    client.write_all(request.as_bytes()).await?;
    let (status, headers) =
        tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client)).await??;
    Ok((client, status, headers))
}

fn render_header_lines(name: &str, values: &[&str]) -> String {
    let mut headers = String::new();
    for value in values {
        headers.push_str(name);
        headers.push_str(": ");
        headers.push_str(value);
        headers.push_str("\r\n");
    }
    headers
}

async fn run_native_websocket_exchange_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let (client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let expected_status = required_status(case, "expected_status")?;
    let expected_accept = required_str(case, "expected_accept")?;
    let expected_protocol = case
        .get("expected_subprotocol")
        .and_then(Value::as_str)
        .unwrap_or(required_str(case, "offered_subprotocol")?);
    if status != expected_status
        || !has_required_websocket_response_headers(&headers)
        || headers.get("sec-websocket-accept").map(String::as_str) != Some(expected_accept)
        || headers.get("sec-websocket-protocol").map(String::as_str) != Some(expected_protocol)
        || !expected_response_header_matches(&headers, case)
    {
        return Err(io::Error::other(format!(
            "{}: WebSocket handshake mismatch: status={status}, required_headers={}, expected_response_header={}, accept={:?}, protocol={:?}, headers={headers:?}",
            required_str(case, "id")?,
            has_required_websocket_response_headers(&headers),
            expected_response_header_matches(&headers, case),
            headers.get("sec-websocket-accept"),
            headers.get("sec-websocket-protocol")
        ))
        .into());
    }

    let mut websocket = tokio_tungstenite::WebSocketStream::from_raw_socket(
        client,
        tokio_tungstenite::tungstenite::protocol::Role::Client,
        None,
    )
    .await;
    let text = required_str(case, "text_payload")?;
    websocket
        .send(tokio_tungstenite::tungstenite::protocol::Message::Text(
            text.to_owned().into(),
        ))
        .await?;
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Text(received)))
            if received.as_str() == text => {}
        other => {
            return Err(io::Error::other(format!(
                "{}: WebSocket text echo mismatch: {other:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }

    let binary = required_byte_array(case, "binary_payload")?;
    websocket
        .send(tokio_tungstenite::tungstenite::protocol::Message::Binary(
            Bytes::from(binary.clone()),
        ))
        .await?;
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Binary(received)))
            if received.as_ref() == binary => {}
        other => {
            return Err(io::Error::other(format!(
                "{}: WebSocket binary echo mismatch: {other:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }

    let ping = required_str(case, "ping_payload")?;
    websocket
        .send(tokio_tungstenite::tungstenite::protocol::Message::Ping(
            Bytes::copy_from_slice(ping.as_bytes()),
        ))
        .await?;
    let pong = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            match websocket.next().await {
                Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Pong(payload)))
                    if payload.as_ref() == ping.as_bytes() =>
                {
                    return Ok::<_, io::Error>(())
                }
                Some(Ok(_)) => {}
                Some(Err(error)) => return Err(io::Error::other(error.to_string())),
                None => return Err(io::Error::other("WebSocket closed before pong")),
            }
        }
    })
    .await?;
    pong?;

    let close_code = required_u64(case, "expected_close_code")?;
    let close_reason = required_str(case, "expected_close_reason")?;
    websocket
        .send(tokio_tungstenite::tungstenite::protocol::Message::Close(
            Some(tokio_tungstenite::tungstenite::protocol::CloseFrame {
                code: tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode::Normal,
                reason: close_reason.into(),
            }),
        ))
        .await?;
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Close(Some(frame))))
            if u64::from(u16::from(frame.code)) == close_code
                && frame.reason.as_str() == close_reason => {}
        other => {
            return Err(io::Error::other(format!(
                "{}: WebSocket close echo mismatch: {other:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    Ok(())
}

async fn run_native_websocket_shutdown_case(
    address: SocketAddr,
    case: &Value,
    shutdown_sender: &watch::Sender<bool>,
) -> ProbeResult<()> {
    let (client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let expected_status = required_status(case, "expected_status")?;
    if status != expected_status
        || !headers.contains_key("sec-websocket-accept")
        || !has_required_websocket_response_headers(&headers)
    {
        return Err(io::Error::other(format!(
            "{}: WebSocket shutdown handshake was not accepted: status={status}",
            required_str(case, "id")?
        ))
        .into());
    }
    let mut websocket = tokio_tungstenite::WebSocketStream::from_raw_socket(
        client,
        tokio_tungstenite::tungstenite::protocol::Role::Client,
        None,
    )
    .await;
    shutdown_sender.send_replace(true);
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Close(Some(frame))))
            if u64::from(u16::from(frame.code)) == required_u64(case, "expected_close_code")?
                && frame.reason.as_str() == required_str(case, "expected_close_reason")? =>
        {
            futures_util::SinkExt::flush(&mut websocket).await?;
            Ok(())
        }
        other => Err(io::Error::other(format!(
            "{}: expected server shutdown close frame, got {other:?}",
            required_str(case, "id")?
        ))
        .into()),
    }
}

async fn run_native_websocket_rejection_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let (mut client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let (body, complete) = tokio::time::timeout(
        Duration::from_secs(2),
        read_response_body(&mut client, &headers),
    )
    .await??;
    let expected_status = required_status(case, "expected_status")?;
    let expected_error = required_str(case, "expected_error")?;
    if status != expected_status
        || headers.contains_key("sec-websocket-accept")
        || !complete
        || !String::from_utf8_lossy(&body).contains(expected_error)
        || !expected_response_header_matches(&headers, case)
    {
        return Err(io::Error::other(format!(
            "{}: rejected WebSocket handshake mismatch: status={status}, complete={complete}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    verify_http1_upgrade_listener_recovers(address, case).await
}

async fn run_native_websocket_accept_after_close_case(
    address: SocketAddr,
    case: &Value,
    registration_outcome: &mut watch::Receiver<Option<String>>,
) -> ProbeResult<()> {
    let (mut client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let (body, complete) = tokio::time::timeout(
        Duration::from_secs(2),
        read_response_body(&mut client, &headers),
    )
    .await??;
    let expected_status = required_status(case, "expected_status")?;
    let expected_body = required_str(case, "expected_response_body")?.as_bytes();
    if status != expected_status || !complete || body != expected_body {
        return Err(io::Error::other(format!(
            "{}: deferred WebSocket response differed: status={status}, complete={complete}, body={body:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    drop(client);

    let outcome = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if let Some(outcome) = registration_outcome.borrow_and_update().clone() {
                return Ok::<_, io::Error>(outcome);
            }
            registration_outcome
                .changed()
                .await
                .map_err(|_| io::Error::other("WebSocket acceptance outcome channel closed"))?;
        }
    })
    .await??;
    let expected_error = required_str(case, "expected_error")?;
    if outcome != expected_error {
        return Err(io::Error::other(format!(
            "{}: delayed WebSocket accept result differed: {outcome:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_native_websocket_malformed_frame_case(
    address: SocketAddr,
    case: &Value,
    observation: &mut watch::Receiver<Option<String>>,
) -> ProbeResult<()> {
    let (mut client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let expected_status = required_status(case, "expected_status")?;
    if status != expected_status || !has_required_websocket_response_headers(&headers) {
        return Err(io::Error::other(format!(
            "{}: malformed-frame WebSocket handshake differed: status={status}",
            required_str(case, "id")?
        ))
        .into());
    }

    // A client frame must be masked. This intentionally malformed frame lets
    // the public session API observe and preserve the protocol error source.
    client.write_all(&[0x81, 0x01, b'x']).await?;
    client.flush().await?;
    let observed = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if let Some(observed) = observation.borrow_and_update().clone() {
                return Ok::<_, io::Error>(observed);
            }
            observation
                .changed()
                .await
                .map_err(|_| io::Error::other("WebSocket error observation channel closed"))?;
        }
    })
    .await??;
    drop(client);

    let expected_prefix = required_str(case, "expected_error_prefix")?;
    let expected_source = case["expected_error_source"].as_bool().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_error_source must be a boolean",
        )
    })?;
    let expected_suffix = format!(";source={expected_source}");
    if !observed.starts_with(expected_prefix) || !observed.ends_with(&expected_suffix) {
        return Err(io::Error::other(format!(
            "{}: WebSocket error observation differed: {observed:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_native_websocket_close_reply_flush_failure_case(
    address: SocketAddr,
    case: &Value,
    observation: &mut watch::Receiver<Option<String>>,
) -> ProbeResult<()> {
    let (mut client, status, headers) = open_native_websocket_handshake(address, case).await?;
    let expected_status = required_status(case, "expected_status")?;
    if status != expected_status || !has_required_websocket_response_headers(&headers) {
        return Err(io::Error::other(format!(
            "{}: close-reply fault handshake differed: status={status}",
            required_str(case, "id")?
        ))
        .into());
    }

    client
        .write_all(&[0x88, 0x82, 0x37, 0xfa, 0x21, 0x3d, 0x34, 0x12])
        .await?;
    client.flush().await?;
    let observed = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if let Some(observed) = observation.borrow_and_update().clone() {
                return Ok::<_, io::Error>(observed);
            }
            observation
                .changed()
                .await
                .map_err(|_| io::Error::other("WebSocket error observation channel closed"))?;
        }
    })
    .await??;
    drop(client);

    let expected_prefix = required_str(case, "expected_error_prefix")?;
    let expected_source = case["expected_error_source"].as_bool().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_error_source must be a boolean",
        )
    })?;
    let expected_suffix = format!(";source={expected_source}");
    if !observed.starts_with(expected_prefix) || !observed.ends_with(&expected_suffix) {
        return Err(io::Error::other(format!(
            "{}: close-reply error observation differed: {observed:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

fn has_required_websocket_response_headers(
    headers: &std::collections::HashMap<String, String>,
) -> bool {
    headers
        .get("upgrade")
        .is_some_and(|value| value.eq_ignore_ascii_case("websocket"))
        && headers.get("connection").is_some_and(|value| {
            value
                .split(',')
                .any(|token| token.trim().eq_ignore_ascii_case("upgrade"))
        })
}

fn expected_response_header_matches(
    headers: &std::collections::HashMap<String, String>,
    case: &Value,
) -> bool {
    let Some(name) = case
        .get("expected_response_header_name")
        .and_then(Value::as_str)
    else {
        return true;
    };
    let Some(expected_value) = case
        .get("expected_response_header_value")
        .and_then(Value::as_str)
    else {
        return false;
    };
    headers
        .get(&name.to_ascii_lowercase())
        .is_some_and(|value| value == expected_value)
}

fn required_byte_array(case: &Value, key: &str) -> ProbeResult<Vec<u8>> {
    case.get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("{key} must be a byte array"),
            )
        })?
        .iter()
        .map(|value| {
            value
                .as_u64()
                .and_then(|value| u8::try_from(value).ok())
                .ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::InvalidData,
                        format!("{key} contains a value outside the byte range"),
                    )
                })
                .map_err(Into::into)
        })
        .collect()
}

fn required_request_count(case: &Value) -> ProbeResult<usize> {
    let Some(value) = case.get("request_count") else {
        return Ok(1);
    };
    value
        .as_u64()
        .and_then(|count| usize::try_from(count).ok())
        .filter(|count| *count > 0)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "request_count must be a positive integer",
            )
            .into()
        })
}

async fn run_isolated_http3_alpn_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) =
        test_tls_configs_with_quic_alpns(vec![b"h3".to_vec(), b"http/1.1".to_vec()])?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (app, _) = contract_app_with_state(shutdown_sender.clone());
    let observed_errors = Arc::new(Mutex::new(Vec::<ObservedServerError>::new()));
    let error_log = Arc::clone(&observed_errors);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        if let Ok(mut observations) = error_log.lock() {
            observations.push(ObservedServerError {
                phase: event.phase(),
                peer_addr: event.peer_addr(),
                is_io_error: error_chain_contains::<io::Error>(event.error()),
                is_direct_io_error: event.error().is::<io::Error>(),
                has_error_source: event.error().source().is_some(),
                h3_error_code: h3_connection_error_code(event.error()),
                message: event.error().to_string(),
            });
        }
    });
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        app,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            error_observer: Some(error_observer),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let mut non_h3_endpoint = quinn::Endpoint::client("127.0.0.1:0".parse()?)?;
    non_h3_endpoint.set_default_client_config(tls_clients.http3_non_h3.clone());
    let non_h3_connection = non_h3_endpoint.connect(address, "localhost")?.await?;
    let negotiated_alpn = non_h3_connection
        .handshake_data()
        .and_then(|data| data.downcast::<quinn::crypto::rustls::HandshakeData>().ok())
        .and_then(|data| data.protocol);
    if negotiated_alpn.as_deref() != Some(b"http/1.1") {
        return Err(io::Error::other(format!(
            "non-HTTP/3 test connection negotiated unexpected ALPN: {negotiated_alpn:?}"
        ))
        .into());
    }
    non_h3_connection.close(quinn::VarInt::from_u32(0), b"non-HTTP/3 ALPN contract");
    non_h3_endpoint.wait_idle().await;

    let observation = tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if let Some(observation) = observed_errors
                .lock()
                .map_err(|_| io::Error::other("HTTP/3 error observation lock was poisoned"))?
                .first()
                .cloned()
            {
                return Ok::<_, io::Error>(observation);
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await??;
    let observed_error_type = if observation.is_io_error {
        "io"
    } else if observation.h3_error_code.is_some() {
        "h3"
    } else {
        "http3"
    };
    let expected_error_has_source = case["expected_server_error_has_source"]
        .as_bool()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_server_error_has_source must be a boolean",
            )
        })?;
    if server_error_phase_name(observation.phase)
        != required_str(case, "expected_server_error_phase")?
        || observed_error_type != required_str(case, "expected_server_error_type")?
        || observation.peer_addr.is_none()
        || observation.has_error_source != expected_error_has_source
        || observation.message != required_str(case, "expected_server_error_message")?
    {
        return Err(io::Error::other(format!(
            "{}: non-HTTP/3 ALPN error observation differed: {observation:?}",
            required_str(case, "id")?
        ))
        .into());
    }

    let (valid_endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
    let mut stream = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let (status, body, _) = collect_http3_response(&mut stream).await?;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: valid HTTP/3 request did not recover after non-h3 ALPN: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    valid_endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 ALPN recovery complete");
    valid_endpoint.wait_idle().await;
    shutdown_sender.send_replace(true);
    join_lifecycle_server(server).await
}

async fn run_isolated_http3_no_common_alpn_case(case: &Value) -> ProbeResult<()> {
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (app, _) = contract_app_with_state(shutdown_sender.clone());
    run_http3_no_common_alpn_recovery(
        case,
        app,
        shutdown_sender,
        shutdown_receiver,
        uvicorn_rs::ServerConfig::default(),
    )
    .await
}

async fn run_isolated_http3_no_common_alpn_lifecycle_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let lifecycle: Arc<dyn uvicorn_rs::ApplicationLifecycle> = fixture.hooks.clone();
    let server_config = uvicorn_rs::ServerConfig {
        application_lifecycle: Some(lifecycle),
        ..uvicorn_rs::ServerConfig::default()
    };
    run_http3_no_common_alpn_recovery(
        case,
        fixture.app.clone(),
        fixture.shutdown_sender.clone(),
        fixture.shutdown_receiver.clone(),
        server_config,
    )
    .await?;

    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || !fixture.state.shutdown_completed.load(Ordering::Acquire)
    {
        return Err(io::Error::other(
            "HTTP/3 lifecycle hooks did not bracket ALPN rejection and recovery",
        )
        .into());
    }
    let events = fixture
        .state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event log was poisoned"))?;
    if events.as_slice() != ["startup", "shutdown"] {
        return Err(io::Error::other(format!(
            "{}: lifecycle events differed: expected [\"startup\", \"shutdown\"], got {events:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_isolated_http3_endpoint_close_lifecycle_case(case: &Value) -> ProbeResult<()> {
    let startup_wait_ms = case["startup_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "startup_wait_ms is missing"))?;
    let close_code = case["endpoint_close_code"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "endpoint_close_code is missing")
    })?;
    let close_code = u32::try_from(close_code).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "endpoint_close_code exceeds the QUIC test input range",
        )
    })?;
    let close_reason = required_str(case, "endpoint_close_reason")?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let expected_events = case["expected_lifecycle_events"]
        .as_array()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_lifecycle_events is missing",
            )
        })?
        .iter()
        .map(|event| {
            event.as_str().ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "expected lifecycle events must be strings",
                )
            })
        })
        .collect::<Result<Vec<_>, _>>()?;

    let fixture = lifecycle_fixture();
    // These shutdown inputs never dispatch an application request. Use the
    // regular contract service so the HTTP/3 accept-loop behavior is covered
    // for the same service type used by ordinary HTTP/3 requests, while the
    // separate lifecycle object still verifies startup/shutdown ordering.
    let (application, _) = contract_app_with_state(fixture.shutdown_sender.clone());
    let (_, _, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let owner_endpoint = server_endpoint.clone();
    let lifecycle: Arc<dyn ApplicationLifecycle> = fixture.hooks.clone();
    let config = uvicorn_rs::ServerConfig {
        application_lifecycle: Some(lifecycle),
        ..uvicorn_rs::ServerConfig::default()
    };
    let mut server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(fixture.shutdown_receiver.clone()),
        config,
    ));

    let startup = tokio::time::timeout(Duration::from_millis(startup_wait_ms), async {
        while !fixture.state.startup_completed.load(Ordering::Acquire) {
            tokio::time::sleep(Duration::from_millis(1)).await;
        }
    })
    .await;
    if startup.is_err() {
        owner_endpoint.close(quinn::VarInt::from_u32(0), b"startup observation timed out");
        server.abort();
        let _ = server.await;
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 lifecycle startup did not complete before endpoint close",
        )
        .into());
    }

    owner_endpoint.close(quinn::VarInt::from_u32(close_code), close_reason.as_bytes());

    match tokio::time::timeout(Duration::from_millis(server_wait_ms), &mut server).await {
        Ok(Ok(Ok(()))) => {}
        Ok(Ok(Err(error))) => return Err(error.into()),
        Ok(Err(error)) => return Err(error.into()),
        Err(_) => {
            server.abort();
            let _ = server.await;
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "closing the HTTP/3 endpoint did not stop the accept loop",
            )
            .into());
        }
    }

    owner_endpoint.wait_idle().await;
    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || !fixture.state.shutdown_completed.load(Ordering::Acquire)
        || fixture.state.requests_started.load(Ordering::Acquire) != 0
    {
        return Err(io::Error::other(
            "endpoint closure did not complete lifecycle shutdown without serving a request",
        )
        .into());
    }

    let events = fixture
        .state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event log was poisoned"))?;
    let observed_events = events.iter().copied().collect::<Vec<_>>();
    if observed_events != expected_events {
        return Err(io::Error::other(format!(
            "{}: endpoint-close lifecycle events differed: expected {expected_events:?}, got {observed_events:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_no_common_alpn_recovery<S, B>(
    case: &Value,
    app: S,
    shutdown_sender: watch::Sender<bool>,
    shutdown_receiver: watch::Receiver<bool>,
    mut server_config: uvicorn_rs::ServerConfig,
) -> ProbeResult<()>
where
    S: Service<Request<uvicorn_rs::Http3RequestBody>, Response = Response<B>>
        + Clone
        + Send
        + 'static,
    S::Future: Send + 'static,
    S::Error: Error + std::fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<Box<dyn Error + Send + Sync + 'static>> + Send + Sync + 'static,
{
    let server_alpns = case["server_alpn_protocols"]
        .as_array()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "server_alpn_protocols is missing",
            )
        })?
        .iter()
        .map(|protocol| {
            protocol
                .as_str()
                .map(str::as_bytes)
                .map(<[u8]>::to_vec)
                .ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::InvalidData,
                        "server ALPN protocol must be a string",
                    )
                })
        })
        .collect::<Result<Vec<_>, _>>()?;
    let (_, tls_clients, quic_server_config) = test_tls_configs_with_quic_alpns(server_alpns)?;
    let client_config = match required_str(case, "client_alpn_protocol")? {
        "h3" => tls_clients.http3.clone(),
        "http/1.1" => tls_clients.http3_non_h3.clone(),
        protocol => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported test client ALPN protocol {protocol:?}"),
            )
            .into());
        }
    };

    if required_str(case, "expected_server_error_phase")? != "connection"
        || required_str(case, "expected_server_error_type")? != "quic"
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "no-common-ALPN case has unsupported server error expectations",
        )
        .into());
    }
    let expected_error_has_source = case["expected_server_error_has_source"]
        .as_bool()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_server_error_has_source must be a boolean",
            )
        })?;

    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let observed_errors = Arc::new(Mutex::new(Vec::<(
        ServerErrorPhase,
        Option<SocketAddr>,
        bool,
        bool,
        String,
    )>::new()));
    let error_log = Arc::clone(&observed_errors);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        if let Ok(mut observations) = error_log.lock() {
            observations.push((
                event.phase(),
                event.peer_addr(),
                error_chain_contains::<quinn::ConnectionError>(event.error()),
                event.error().source().is_some(),
                event.error().to_string(),
            ));
        }
    });
    server_config.error_observer = Some(error_observer);
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        app,
        shutdown_on_change(shutdown_receiver),
        server_config,
    ));

    let mut client_endpoint = quinn::Endpoint::client("127.0.0.1:0".parse()?)?;
    client_endpoint.set_default_client_config(client_config);
    let workflow = async {
        let connecting = client_endpoint.connect(address, "localhost")?;
        match tokio::time::timeout(Duration::from_secs(2), connecting).await {
            Ok(Err(_)) => {}
            Ok(Ok(connection)) => {
                connection.close(quinn::VarInt::from_u32(0), b"unexpected ALPN success");
                return Err(io::Error::other(
                    "QUIC handshake succeeded despite there being no common ALPN",
                )
                .into());
            }
            Err(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "no-common-ALPN handshake did not complete with an error",
                )
                .into());
            }
        }

        let observation = tokio::time::timeout(Duration::from_secs(2), async {
            loop {
                if let Some(observation) = observed_errors
                    .lock()
                    .map_err(|_| io::Error::other("HTTP/3 error observation lock was poisoned"))?
                    .first()
                    .cloned()
                {
                    return Ok::<_, io::Error>(observation);
                }
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await??;
        if observation.0 != ServerErrorPhase::Connection
            || observation.1.is_none()
            || !observation.2
            || observation.3 != expected_error_has_source
        {
            return Err(io::Error::other(format!(
                "{}: expected an observed QUIC connection error with peer metadata, got {observation:?}",
                required_str(case, "id")?
            ))
            .into());
        }

        client_endpoint.close(quinn::VarInt::from_u32(0), b"no common ALPN");
        let observations = observed_errors
            .lock()
            .map_err(|_| io::Error::other("HTTP/3 error observation lock was poisoned"))?
            .clone();
        if observations.is_empty()
            || observations.iter().any(
                |(phase, peer_addr, is_quic, has_error_source, _)| {
                    *phase != ServerErrorPhase::Connection
                        || peer_addr.is_none()
                        || !is_quic
                        || *has_error_source != expected_error_has_source
                },
            )
        {
            return Err(io::Error::other(format!(
                "{}: no-common-ALPN attempts produced unexpected server error observations: {observations:?}",
                required_str(case, "id")?
            ))
            .into());
        }
        run_http3_request_case(address, &tls_clients.http3, case).await?;
        Ok::<_, Box<dyn Error + Send + Sync>>(())
    }
    .await;

    client_endpoint.close(quinn::VarInt::from_u32(0), b"ALPN recovery case complete");
    shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result
}

async fn run_isolated_tls_pending_handshake_shutdown_case(case: &Value) -> ProbeResult<()> {
    let (tls_acceptor, _, _) = test_tls_configs()?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let graceful_timeout_ms = case["graceful_timeout_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "graceful_timeout_ms is missing")
    })?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let settle_ms = case["pending_handshake_settle_ms"]
        .as_u64()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "pending_handshake_settle_ms is missing",
            )
        })?;
    let expected_server_error = required_str(case, "expected_server_error")?;
    let partial_tls_record = case["partial_tls_record_bytes"]
        .as_array()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "partial_tls_record_bytes is missing",
            )
        })?
        .iter()
        .map(|value| {
            value
                .as_u64()
                .and_then(|byte| u8::try_from(byte).ok())
                .ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::InvalidData,
                        "partial TLS record byte must be in the u8 range",
                    )
                })
        })
        .collect::<Result<Vec<_>, _>>()?;

    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let mut server = tokio::spawn(uvicorn_rs::serve_tls(
        listener,
        tls_acceptor,
        contract_app(shutdown_sender.clone()),
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_millis(graceful_timeout_ms),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));
    let mut server_joined = false;
    let result = async {
        let mut client = TcpStream::connect(address).await?;
        client.write_all(&partial_tls_record).await?;

        // The record header declares more handshake bytes than this client
        // sends, keeping the accepted TLS connection pending at shutdown.
        tokio::time::sleep(Duration::from_millis(settle_ms)).await;
        shutdown_sender.send_replace(true);
        let server_result =
            tokio::time::timeout(Duration::from_millis(server_wait_ms), &mut server)
                .await
                .map_err(|_| {
                    io::Error::new(
                        io::ErrorKind::TimedOut,
                        "server did not finish the pending TLS handshake shutdown",
                    )
                })??;
        server_joined = true;
        drop(client);

        match server_result {
            Err(uvicorn_rs::ServeError::GracefulShutdownTimedOut)
                if expected_server_error
                    == "active connections exceeded the graceful-shutdown deadline" =>
            {
                Ok(())
            }
            Ok(()) => Err(io::Error::other(
                "server stopped without timing out the incomplete TLS handshake",
            )
            .into()),
            Err(error) => Err(io::Error::other(format!(
                "incomplete TLS handshake produced unexpected server error: {error}"
            ))
            .into()),
        }
    }
    .await;

    if !server_joined {
        shutdown_sender.send_replace(true);
        let _ = tokio::time::timeout(Duration::from_secs(1), &mut server).await;
    }
    result
}

async fn run_lifecycle_startup_fault_case(
    case: &Value,
    behavior: LifecycleHookBehavior,
) -> ProbeResult<()> {
    let fixture = lifecycle_fixture_with_behaviors(behavior, LifecycleHookBehavior::Complete);
    let config = lifecycle_server_config(Arc::clone(&fixture.hooks), case)?;
    let server = match required_str(case, "protocol")? {
        "http/1.1" => {
            let listener = TcpListener::bind("127.0.0.1:0").await?;
            let shutdown = fixture.shutdown_receiver.clone();
            tokio::spawn(uvicorn_rs::serve_tcp(
                listener,
                fixture.app.clone(),
                shutdown_on_change(shutdown),
                config,
            ))
        }
        "http3" => {
            let (_, _, quic_server_config) = test_tls_configs()?;
            let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
            let shutdown = fixture.shutdown_receiver.clone();
            tokio::spawn(uvicorn_rs::serve_http3(
                endpoint,
                fixture.app.clone(),
                shutdown_on_change(shutdown),
                config,
            ))
        }
        protocol => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported lifecycle startup-fault protocol {protocol:?}"),
            )
            .into());
        }
    };
    expect_lifecycle_server_error(server, ApplicationLifecycleStage::Startup, behavior).await?;
    if fixture.state.startup_completed.load(Ordering::Acquire)
        || fixture.state.shutdown_completed.load(Ordering::Acquire)
        || fixture.state.requests_started.load(Ordering::Acquire) != 0
    {
        return Err(io::Error::other(
            "startup fault did not prevent serving or unexpectedly ran shutdown",
        )
        .into());
    }
    if behavior == LifecycleHookBehavior::Wait
        && !fixture.state.startup_hook_dropped.load(Ordering::Acquire)
    {
        return Err(io::Error::other("startup timeout did not cancel the hook future").into());
    }
    if behavior == LifecycleHookBehavior::Panic {
        verify_lifecycle_error_observation(
            case,
            &fixture.state,
            ApplicationLifecycleStage::Startup,
        )?;
    }
    verify_lifecycle_events(case, &fixture.state)
}

async fn run_lifecycle_readiness_case(case: &Value) -> ProbeResult<()> {
    match required_str(case, "protocol")? {
        "http/1.1" => run_lifecycle_readiness_http1_case(case).await,
        "http3" => run_lifecycle_readiness_http3_case(case).await,
        protocol => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("unsupported lifecycle readiness protocol {protocol:?}"),
        )
        .into()),
    }
}

async fn run_lifecycle_readiness_error_case(case: &Value) -> ProbeResult<()> {
    if required_str(case, "protocol")? != "http/1.1" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "lifecycle readiness-error contract requires HTTP/1.1",
        )
        .into());
    }

    let fixture = lifecycle_fixture();
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(fixture.shutdown_receiver.clone()),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));

    let workflow = async {
        for (path_field, status_field, body_field) in [
            ("arm_path", "arm_status", "arm_body"),
            ("fault_path", "fault_status", "fault_body"),
            ("recovery_path", "recovery_status", "recovery_body"),
        ] {
            let response = tokio::time::timeout(
                Duration::from_secs(2),
                lifecycle_http1_get(address, required_str(case, path_field)?),
            )
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!("HTTP/1.1 lifecycle {path_field} request timed out"),
                )
            })??;
            let expected_status = required_status(case, status_field)?;
            let expected_body = required_str(case, body_field)?;
            if response.0 != expected_status || response.1 != expected_body.as_bytes() {
                return Err(io::Error::other(format!(
                    "{}: lifecycle {path_field} returned status {} and body {:?}, expected status {expected_status} and body {expected_body:?}",
                    required_str(case, "id")?,
                    response.0,
                    String::from_utf8_lossy(&response.1)
                ))
                .into());
            }
        }
        Ok::<_, Box<dyn Error + Send + Sync>>(())
    }
    .await;

    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;

    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || !fixture.state.shutdown_completed.load(Ordering::Acquire)
    {
        return Err(io::Error::other(
            "lifecycle readiness error prevented successful startup or shutdown",
        )
        .into());
    }
    verify_lifecycle_events(case, &fixture.state)?;
    verify_lifecycle_readiness_error_observation(case, &fixture.state)
}

async fn run_lifecycle_readiness_http1_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    arm_lifecycle_readiness(&fixture.state)?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let workflow = async {
        let started = Instant::now();
        let (status, body) = tokio::time::timeout(
            Duration::from_secs(2),
            lifecycle_http1_get(address, required_str(case, "ready_path")?),
        )
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/1.1 readiness request timed out",
            )
        })??;
        verify_lifecycle_response(case, b"started\n", status, &body)?;
        Ok::<_, Box<dyn Error + Send + Sync>>(started.elapsed())
    }
    .await;
    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    let elapsed = workflow?;
    server_result?;
    verify_lifecycle_readiness_state(case, &fixture.state, elapsed)
}

async fn run_lifecycle_readiness_http3_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    arm_lifecycle_readiness(&fixture.state)?;
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let workflow = lifecycle_http3_readiness_probe(case, address, &tls_clients.http3).await;
    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    let elapsed = workflow?;
    server_result?;
    verify_lifecycle_readiness_state(case, &fixture.state, elapsed)
}

async fn lifecycle_http3_readiness_probe(
    case: &Value,
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
) -> ProbeResult<Duration> {
    tokio::time::timeout(Duration::from_secs(2), async {
        let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
        let started = Instant::now();
        let request = async {
            let mut response = send_http3_request(
                &mut sender,
                address,
                "GET",
                required_str(case, "ready_path")?,
                b"",
            )
            .await?;
            let (status, body, _) = collect_http3_response(&mut response).await?;
            verify_lifecycle_response(case, b"started\n", status, &body)?;
            Ok::<_, Box<dyn Error + Send + Sync>>(started.elapsed())
        }
        .await;
        endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 lifecycle readiness case complete",
        );
        tokio::time::timeout(Duration::from_millis(250), endpoint.wait_idle())
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 lifecycle readiness client cleanup timed out",
                )
            })?;
        request
    })
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 readiness handshake, request, or cleanup timed out",
        )
    })?
}

fn arm_lifecycle_readiness(state: &LifecycleState) -> ProbeResult<()> {
    state
        .readiness_gate
        .lock()
        .map_err(|_| io::Error::other("lifecycle readiness state was poisoned"))?
        .armed = true;
    Ok(())
}

fn verify_lifecycle_readiness_state(
    case: &Value,
    state: &LifecycleState,
    elapsed: Duration,
) -> ProbeResult<()> {
    let minimum_pending_ms = case["minimum_pending_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "minimum_pending_ms is missing")
    })?;
    let readiness = state
        .readiness_gate
        .lock()
        .map_err(|_| io::Error::other("lifecycle readiness state was poisoned"))?;
    if elapsed < Duration::from_millis(minimum_pending_ms)
        || readiness.pending_polls == 0
        || !readiness.released
        || readiness.waiting
        || readiness.wake_started
        || !readiness.wakers.is_empty()
    {
        return Err(io::Error::other(format!(
            "{}: lifecycle readiness did not remain Pending and recover; elapsed={}ms, pending_polls={}, released={}, waiting={}, wake_started={}, saved_wakers={}",
            required_str(case, "id")?,
            elapsed.as_millis(),
            readiness.pending_polls,
            readiness.released,
            readiness.waiting,
            readiness.wake_started,
            readiness.wakers.len()
        ))
        .into());
    }
    drop(readiness);
    if !state.startup_completed.load(Ordering::Acquire)
        || !state.shutdown_completed.load(Ordering::Acquire)
        || state.requests_started.load(Ordering::Acquire) != 1
    {
        return Err(io::Error::other(format!(
            "{}: readiness request did not run between successful startup and shutdown",
            required_str(case, "id")?
        ))
        .into());
    }
    verify_lifecycle_events(case, state)
}

async fn run_lifecycle_shutdown_fault_case(
    case: &Value,
    behavior: LifecycleHookBehavior,
) -> ProbeResult<()> {
    match required_str(case, "protocol")? {
        "http3" => run_lifecycle_shutdown_http3_case(case, behavior).await,
        "http/1.1" => run_lifecycle_shutdown_http1_case(case, behavior).await,
        protocol => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("unsupported shutdown fault protocol {protocol:?}"),
        )
        .into()),
    }
}

async fn run_lifecycle_service_and_response_body_errors_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));

    let workflow: ProbeResult<()> = async {
        let (status, body) =
            lifecycle_http1_get(address, required_str(case, "service_path")?).await?;
        if status != required_status(case, "service_status")?
            || body != required_str(case, "service_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: service error response differed: status={status}, body={body:?}",
                required_str(case, "id")?
            ))
            .into());
        }

        let mut head_response = request(
            address,
            "HEAD",
            required_str(case, "head_error_path")?,
            b"",
        )
        .await?;
        let (head_status, head_headers) = read_response_head(&mut head_response).await?;
        let (head_body, head_complete) = read_response_body(&mut head_response, &head_headers).await?;
        if head_status != required_status(case, "head_error_status")?
            || !head_body.is_empty()
            || !head_complete
        {
            return Err(io::Error::other(format!(
                "{}: HEAD service error response differed: status={head_status}, body={head_body:?}, complete={head_complete}",
                required_str(case, "id")?
            ))
            .into());
        }

        let mut response = request(
            address,
            "GET",
            required_str(case, "body_error_path")?,
            b"",
        )
        .await?;
        let (status, headers) = read_response_head(&mut response).await?;
        let (body, complete) = read_response_body(&mut response, &headers).await?;
        let expected_complete = case["body_error_complete"].as_bool().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "body_error_complete must be a boolean",
            )
        })?;
        if status != required_status(case, "body_error_status")?
            || body != required_str(case, "body_error_prefix")?.as_bytes()
            || complete != expected_complete
        {
            return Err(io::Error::other(format!(
                "{}: response body error differed: status={status}, body={body:?}, complete={complete}",
                required_str(case, "id")?
            ))
            .into());
        }
        Ok(())
    }
    .await;

    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_state(case, &fixture.state)?;
    verify_lifecycle_application_error_observations(case, &fixture.state)
}

async fn run_lifecycle_server_and_shutdown_error_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture_with_behaviors(
        LifecycleHookBehavior::Complete,
        LifecycleHookBehavior::Fail,
    );
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let (client_endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
    let response_stream = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let mut active_request = fixture.state.active_request.subscribe();
    wait_for_lifecycle_signal(
        &mut active_request,
        "held HTTP/3 request did not reach the service",
    )
    .await?;

    fixture.shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 combined lifecycle failure server did not stop",
            )
        })??;
    let error = match server_result {
        Err(error) => error,
        Ok(()) => {
            return Err(
                io::Error::other("HTTP/3 combined lifecycle failure returned success").into(),
            );
        }
    };
    let (server_error, shutdown_error) = error.shutdown_failures().ok_or_else(|| {
        io::Error::other(format!(
            "server did not preserve both shutdown failures: {error}"
        ))
    })?;
    if !matches!(
        server_error,
        uvicorn_rs::ServeError::GracefulShutdownTimedOut
    ) {
        return Err(io::Error::other(format!(
            "HTTP/3 server failure was not a graceful-shutdown timeout: {server_error}"
        ))
        .into());
    }
    match shutdown_error {
        uvicorn_rs::ServeError::ApplicationLifecycleFailed { stage, error }
            if *stage == ApplicationLifecycleStage::Shutdown =>
        {
            if error.downcast_ref::<io::Error>().is_none() {
                return Err(io::Error::other(format!(
                    "shutdown hook error lost its original io::Error source: {error}"
                ))
                .into());
            }
        }
        error => {
            return Err(io::Error::other(format!(
                "unexpected application shutdown failure: {error}"
            ))
            .into());
        }
    }
    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || fixture.state.shutdown_completed.load(Ordering::Acquire)
        || fixture.state.requests_started.load(Ordering::Acquire) != 1
    {
        return Err(io::Error::other(
            "HTTP/3 combined failure did not preserve startup and held-request state",
        )
        .into());
    }

    client_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"combined lifecycle failure complete",
    );
    client_endpoint.wait_idle().await;
    drop(response_stream);
    verify_lifecycle_events(case, &fixture.state)
}

async fn run_lifecycle_server_timeout_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let (client_endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
    let response_stream = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let mut active_request = fixture.state.active_request.subscribe();
    wait_for_lifecycle_signal(
        &mut active_request,
        "held HTTP/3 request did not reach the service",
    )
    .await?;

    fixture.shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 lifecycle timeout server did not stop",
            )
        })??;
    let error = server_result.err().ok_or_else(|| {
        io::Error::other("HTTP/3 held request did not exceed the shutdown deadline")
    })?;
    let expected_display = required_str(case, "expected_error_display")?;
    if !matches!(&error, uvicorn_rs::ServeError::GracefulShutdownTimedOut)
        || error.to_string() != expected_display
        || error.source().is_some()
    {
        return Err(io::Error::other(format!(
            "{}: server timeout error differed: display={:?}, source={:?}",
            required_str(case, "id")?,
            error.to_string(),
            error.source()
        ))
        .into());
    }
    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || !fixture.state.shutdown_completed.load(Ordering::Acquire)
        || fixture.state.requests_started.load(Ordering::Acquire) != 1
    {
        return Err(io::Error::other(
            "HTTP/3 server timeout did not complete application shutdown after cancelling the held request",
        )
        .into());
    }

    client_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"lifecycle timeout case complete",
    );
    client_endpoint.wait_idle().await;
    drop(response_stream);
    verify_lifecycle_events(case, &fixture.state)
}

async fn run_lifecycle_shutdown_http1_case(
    case: &Value,
    behavior: LifecycleHookBehavior,
) -> ProbeResult<()> {
    let fixture = lifecycle_fixture_with_behaviors(LifecycleHookBehavior::Complete, behavior);
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let response = lifecycle_http1_get(address, required_str(case, "ready_path")?).await;
    fixture.shutdown_sender.send_replace(true);
    expect_lifecycle_server_error(server, ApplicationLifecycleStage::Shutdown, behavior).await?;
    let (status, body) = response?;
    verify_lifecycle_response(case, b"started\n", status, &body)?;
    if !fixture.state.startup_completed.load(Ordering::Acquire) {
        return Err(io::Error::other("shutdown fault case skipped startup").into());
    }
    if behavior == LifecycleHookBehavior::Wait
        && !fixture.state.shutdown_hook_dropped.load(Ordering::Acquire)
    {
        return Err(io::Error::other("shutdown timeout did not cancel the hook future").into());
    }
    if behavior == LifecycleHookBehavior::Panic {
        verify_lifecycle_error_observation(
            case,
            &fixture.state,
            ApplicationLifecycleStage::Shutdown,
        )?;
    }
    verify_lifecycle_events(case, &fixture.state)
}

async fn run_lifecycle_shutdown_http3_case(
    case: &Value,
    behavior: LifecycleHookBehavior,
) -> ProbeResult<()> {
    let fixture = lifecycle_fixture_with_behaviors(LifecycleHookBehavior::Complete, behavior);
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let response = async {
        let (client_endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
        let mut stream = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "ready_path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut stream).await?;
        client_endpoint.close(quinn::VarInt::from_u32(0), b"lifecycle shutdown fault case");
        client_endpoint.wait_idle().await;
        Ok::<_, Box<dyn Error + Send + Sync>>((status, body))
    }
    .await;
    fixture.shutdown_sender.send_replace(true);
    expect_lifecycle_server_error(server, ApplicationLifecycleStage::Shutdown, behavior).await?;
    let (status, body) = response?;
    verify_lifecycle_response(case, b"started\n", status, &body)?;
    if !fixture.state.startup_completed.load(Ordering::Acquire) {
        return Err(io::Error::other("HTTP/3 shutdown fault case skipped startup").into());
    }
    if behavior == LifecycleHookBehavior::Wait
        && !fixture.state.shutdown_hook_dropped.load(Ordering::Acquire)
    {
        return Err(
            io::Error::other("HTTP/3 shutdown timeout did not cancel the hook future").into(),
        );
    }
    verify_lifecycle_events(case, &fixture.state)
}

async fn expect_lifecycle_server_error(
    server: tokio::task::JoinHandle<Result<(), uvicorn_rs::ServeError>>,
    stage: ApplicationLifecycleStage,
    behavior: LifecycleHookBehavior,
) -> ProbeResult<()> {
    let result = tokio::time::timeout(Duration::from_secs(4), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "lifecycle fault server did not stop",
            )
        })??;
    let error = match result {
        Err(error) => error,
        Ok(()) => return Err(io::Error::other("lifecycle fault server returned success").into()),
    };
    match (behavior, error) {
        (
            LifecycleHookBehavior::Fail,
            uvicorn_rs::ServeError::ApplicationLifecycleFailed {
                stage: actual_stage,
                error,
            },
        ) if actual_stage == stage => {
            if error.downcast_ref::<io::Error>().is_none() {
                return Err(io::Error::other(format!(
                    "lifecycle error lost its original io::Error source: got {error}"
                ))
                .into());
            }
        }
        (
            LifecycleHookBehavior::Wait,
            uvicorn_rs::ServeError::ApplicationLifecycleTimedOut {
                stage: actual_stage,
            },
        ) if actual_stage == stage => {}
        (
            LifecycleHookBehavior::Panic,
            uvicorn_rs::ServeError::ApplicationLifecyclePanicked {
                stage: actual_stage,
            },
        ) if actual_stage == stage => {}
        (_, error) => {
            return Err(io::Error::other(format!(
                "unexpected lifecycle error at {stage:?}: {error}"
            ))
            .into());
        }
    }
    Ok(())
}

fn verify_lifecycle_error_observation(
    case: &Value,
    state: &LifecycleState,
    stage: ApplicationLifecycleStage,
) -> ProbeResult<()> {
    let (expected_phase, expected_message) = match stage {
        ApplicationLifecycleStage::Startup => (
            ServerErrorPhase::ApplicationStartup,
            "application startup hook panicked",
        ),
        ApplicationLifecycleStage::Shutdown => (
            ServerErrorPhase::ApplicationShutdown,
            "application shutdown hook panicked",
        ),
    };
    let observations = state
        .observed_lifecycle_errors
        .lock()
        .map_err(|_| io::Error::other("lifecycle error observations were poisoned"))?;
    if observations.as_slice() != [(expected_phase, expected_message.to_owned(), false)] {
        return Err(io::Error::other(format!(
            "{}: lifecycle panic observer mismatch: expected one {expected_phase:?} observation without a source, got {observations:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_lifecycle_http1_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let mut active_request = fixture.state.active_request.subscribe();
    let workflow =
        run_lifecycle_http1_workflow(case, address, &fixture, &server, &mut active_request, None)
            .await;
    fixture.shutdown_sender.send_replace(true);
    fixture.state.release_request.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_state(case, &fixture.state)
}

async fn run_lifecycle_https_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (tls_acceptor, tls_clients, _) = test_tls_configs()?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tls(
        listener,
        tls_acceptor,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let mut active_request = fixture.state.active_request.subscribe();
    let workflow = run_lifecycle_http1_workflow(
        case,
        address,
        &fixture,
        &server,
        &mut active_request,
        Some(tls_clients.http1.clone()),
    )
    .await;
    fixture.shutdown_sender.send_replace(true);
    fixture.state.release_request.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_state(case, &fixture.state)
}

async fn run_lifecycle_websocket_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (tls_acceptor, tls_clients, _) = test_tls_configs()?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let config = lifecycle_server_config(Arc::clone(&fixture.hooks), case)?;
    let server = match required_str(case, "protocol")? {
        "http/1.1" => tokio::spawn(uvicorn_rs::serve_tcp(
            listener,
            fixture.app.clone(),
            shutdown_on_change(shutdown),
            config,
        )),
        "https/1.1" => tokio::spawn(uvicorn_rs::serve_tls(
            listener,
            tls_acceptor,
            fixture.app.clone(),
            shutdown_on_change(shutdown),
            config,
        )),
        protocol => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported lifecycle WebSocket protocol {protocol:?}"),
            )
            .into());
        }
    };

    let workflow = run_lifecycle_websocket_probe(
        case,
        address,
        (required_str(case, "protocol")? == "https/1.1").then(|| tls_clients.http1.clone()),
    )
    .await;
    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_startup_shutdown(case, &fixture.state)
}

async fn run_lifecycle_websocket_probe(
    case: &Value,
    address: SocketAddr,
    tls_connector: Option<TlsConnector>,
) -> ProbeResult<()> {
    let (ready_status, ready_body) = lifecycle_http1_get_with_tls(
        address,
        required_str(case, "ready_path")?,
        tls_connector.clone(),
    )
    .await?;
    verify_lifecycle_response(case, b"started\n", ready_status, &ready_body)?;

    if let Some(connector) = tls_connector {
        let tcp_stream = TcpStream::connect(address).await?;
        let server_name = ServerName::try_from("localhost".to_owned())?;
        let stream = connector.connect(server_name, tcp_stream).await?;
        run_lifecycle_websocket_session(stream, case).await
    } else {
        let stream = TcpStream::connect(address).await?;
        run_lifecycle_websocket_session(stream, case).await
    }
}

async fn run_lifecycle_websocket_session<S>(mut stream: S, case: &Value) -> ProbeResult<()>
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let path = required_str(case, "path")?;
    let key = required_str(case, "request_key")?;
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    );
    stream.write_all(request.as_bytes()).await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    if status != required_status(case, "expected_status")?
        || !has_required_websocket_response_headers(&headers)
        || headers.get("sec-websocket-accept").map(String::as_str)
            != Some(required_str(case, "expected_accept")?)
    {
        return Err(io::Error::other(format!(
            "{}: lifecycle WebSocket handshake mismatch: status={status}, headers={headers:?}",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut websocket = tokio_tungstenite::WebSocketStream::from_raw_socket(
        stream,
        tokio_tungstenite::tungstenite::protocol::Role::Client,
        None,
    )
    .await;
    let text = required_str(case, "text_payload")?;
    websocket
        .send(tokio_tungstenite::tungstenite::protocol::Message::Text(
            text.to_owned().into(),
        ))
        .await?;
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Text(received)))
            if received.as_str() == text => {}
        other => {
            return Err(io::Error::other(format!(
                "{}: lifecycle WebSocket echo mismatch: {other:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    websocket.close(None).await?;
    match tokio::time::timeout(Duration::from_secs(2), websocket.next()).await? {
        Some(Ok(tokio_tungstenite::tungstenite::protocol::Message::Close(_))) | None => Ok(()),
        other => Err(io::Error::other(format!(
            "{}: lifecycle WebSocket close mismatch: {other:?}",
            required_str(case, "id")?
        ))
        .into()),
    }
}

async fn run_lifecycle_http1_workflow(
    case: &Value,
    address: SocketAddr,
    fixture: &LifecycleFixture,
    server: &tokio::task::JoinHandle<Result<(), uvicorn_rs::ServeError>>,
    active_request: &mut watch::Receiver<bool>,
    tls_connector: Option<TlsConnector>,
) -> ProbeResult<()> {
    let (ready_status, ready_body) = lifecycle_http1_get_with_tls(
        address,
        required_str(case, "ready_path")?,
        tls_connector.clone(),
    )
    .await?;
    verify_lifecycle_response(case, b"started\n", ready_status, &ready_body)?;
    tokio::time::sleep(Duration::from_millis(50)).await;

    let id = required_str(case, "id")?.to_owned();
    let path = required_str(case, "path")?.to_owned();
    let active_address = address;
    let active_connector = tls_connector.clone();
    let active = tokio::spawn(async move {
        lifecycle_http1_get_with_tls(active_address, &path, active_connector).await
    });
    wait_for_lifecycle_signal(active_request, "HTTP/1.1 held request did not start").await?;
    fixture.shutdown_sender.send_replace(true);
    tokio::time::sleep(lifecycle_release_delay(case)?).await;
    let drained_too_early =
        server.is_finished() || fixture.state.shutdown_completed.load(Ordering::Acquire);
    fixture.state.release_request.send_replace(true);
    let (status, body) = active.await??;
    if drained_too_early {
        return Err(io::Error::other(format!(
            "{id}: HTTP/1.1 shutdown completed before the held response was released"
        ))
        .into());
    }
    verify_lifecycle_response(case, b"released\n", status, &body)
}

async fn lifecycle_http1_get_with_tls(
    address: SocketAddr,
    path: &str,
    tls_connector: Option<TlsConnector>,
) -> ProbeResult<(u16, Vec<u8>)> {
    match tls_connector {
        Some(connector) => lifecycle_https_get(address, path, &connector).await,
        None => lifecycle_http1_get(address, path).await,
    }
}

async fn lifecycle_https_get(
    address: SocketAddr,
    path: &str,
    connector: &TlsConnector,
) -> ProbeResult<(u16, Vec<u8>)> {
    let tcp_stream = TcpStream::connect(address).await?;
    let server_name = ServerName::try_from("localhost")?;
    let mut stream = connector.connect(server_name, tcp_stream).await?;
    let request = format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).await?;
    stream.flush().await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    if !complete {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTPS lifecycle response was incomplete",
        )
        .into());
    }
    Ok((status, body))
}

async fn lifecycle_http1_get(address: SocketAddr, path: &str) -> ProbeResult<(u16, Vec<u8>)> {
    let mut stream = request(address, "GET", path, b"").await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    if !complete {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/1.1 lifecycle response was incomplete",
        )
        .into());
    }
    Ok((status, body))
}

async fn run_lifecycle_http2_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let mut active_request = fixture.state.active_request.subscribe();
    let workflow =
        run_lifecycle_http2_workflow(case, address, &fixture, &server, &mut active_request).await;
    fixture.shutdown_sender.send_replace(true);
    fixture.state.release_request.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_state(case, &fixture.state)
}

async fn run_lifecycle_http2_workflow(
    case: &Value,
    address: SocketAddr,
    fixture: &LifecycleFixture,
    server: &tokio::task::JoinHandle<Result<(), uvicorn_rs::ServeError>>,
    active_request: &mut watch::Receiver<bool>,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let _driver = tokio::spawn(connection);
    let ready_request = lifecycle_http2_request(address, required_str(case, "ready_path")?)?;
    let ready_response = sender.send_request(ready_request).await?;
    let ready_status = ready_response.status().as_u16();
    let ready_body = ready_response.into_body().collect().await?.to_bytes();
    verify_lifecycle_response(case, b"started\n", ready_status, ready_body.as_ref())?;

    let id = required_str(case, "id")?.to_owned();
    let path = required_str(case, "path")?.to_owned();
    let active = tokio::spawn(async move {
        let mut sender = sender;
        let response = sender
            .send_request(lifecycle_http2_request(address, &path)?)
            .await?;
        let status = response.status().as_u16();
        let body = response.into_body().collect().await?.to_bytes();
        Ok::<_, Box<dyn Error + Send + Sync>>((status, body.to_vec()))
    });
    wait_for_lifecycle_signal(active_request, "HTTP/2 held request did not start").await?;
    fixture.shutdown_sender.send_replace(true);
    tokio::time::sleep(lifecycle_release_delay(case)?).await;
    let drained_too_early =
        server.is_finished() || fixture.state.shutdown_completed.load(Ordering::Acquire);
    fixture.state.release_request.send_replace(true);
    let (status, body) = active.await??;
    if drained_too_early {
        return Err(io::Error::other(format!(
            "{id}: HTTP/2 shutdown completed before the held response was released"
        ))
        .into());
    }
    verify_lifecycle_response(case, b"released\n", status, &body)
}

fn lifecycle_http2_request(address: SocketAddr, path: &str) -> ProbeResult<Request<Full<Bytes>>> {
    Request::builder()
        .method("GET")
        .uri(format!("http://localhost:{}{path}", address.port()))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))
        .map_err(Into::into)
}

async fn run_lifecycle_http3_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));
    let mut active_request = fixture.state.active_request.subscribe();
    let workflow = run_lifecycle_http3_workflow(
        case,
        address,
        &tls_clients.http3,
        &fixture,
        &server,
        &mut active_request,
    )
    .await;
    fixture.shutdown_sender.send_replace(true);
    fixture.state.release_request.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_state(case, &fixture.state)
}

async fn run_lifecycle_http3_invalid_config_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (_, _, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let config = match required_str(case, "invalid_configuration")? {
        "zero-connection-limit" => uvicorn_rs::ServerConfig {
            max_connections: 0,
            application_lifecycle: Some(fixture.hooks.clone()),
            ..uvicorn_rs::ServerConfig::default()
        },
        "connection-limit-overflow" => uvicorn_rs::ServerConfig {
            max_connections: tokio::sync::Semaphore::MAX_PERMITS + 1,
            application_lifecycle: Some(fixture.hooks.clone()),
            ..uvicorn_rs::ServerConfig::default()
        },
        configuration => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported HTTP/3 server configuration {configuration:?}"),
            )
            .into());
        }
    };

    let error = tokio::time::timeout(
        Duration::from_secs(2),
        uvicorn_rs::serve_http3(endpoint, fixture.app, std::future::pending::<()>(), config),
    )
    .await
    .map_err(|_| io::Error::other("HTTP/3 invalid configuration did not return promptly"))?
    .err()
    .ok_or_else(|| io::Error::other("HTTP/3 server accepted an invalid connection limit"))?;
    let observed_error = match &error {
        uvicorn_rs::ServeError::InvalidConnectionLimit => "invalid-connection-limit",
        uvicorn_rs::ServeError::ConnectionLimitTooLarge => "connection-limit-too-large",
        other => {
            return Err(io::Error::other(format!(
                "HTTP/3 server returned an unexpected configuration error: {other}"
            ))
            .into());
        }
    };
    if observed_error != required_str(case, "expected_error")? {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 configuration error differed: {observed_error}",
            required_str(case, "id")?
        ))
        .into());
    }
    if let Some(expected_display) = case.get("expected_error_display") {
        if expected_display.as_str() != Some(error.to_string().as_str()) {
            return Err(io::Error::other("HTTP/3 configuration error display differed").into());
        }
    }
    if error.source().is_some() {
        return Err(io::Error::other("HTTP/3 configuration error had an unexpected source").into());
    }
    verify_configuration_rejected_before_lifecycle(&fixture.state)?;
    Ok(())
}

async fn run_lifecycle_http3_without_hooks_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    // This application is ready independently of server-managed lifecycle
    // hooks. The case verifies that omitting hooks leaves serving and shutdown
    // behavior available without invoking either callback.
    fixture
        .state
        .startup_completed
        .store(true, Ordering::Release);

    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let mut config = uvicorn_rs::ServerConfig::default();
    if let Some(limit) = case.get("max_connections") {
        if limit.as_str() != Some("runtime-maximum") {
            return Err(io::Error::other("unsupported lifecycle-free connection limit").into());
        }
        config.max_connections = tokio::sync::Semaphore::MAX_PERMITS;
    }
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(fixture.shutdown_receiver.clone()),
        config,
    ));

    let workflow: ProbeResult<()> = match tokio::time::timeout(Duration::from_secs(5), async {
        let (client_endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
        let mut response = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut response).await?;
        if status != required_status(case, "expected_status")?
            || body != required_str(case, "expected_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 request without lifecycle hooks differed: status={status}, body={body:?}",
                required_str(case, "id")?
            ))
            .into());
        }

        client_endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 lifecycle hooks omitted",
        );
        tokio::time::timeout(Duration::from_secs(2), client_endpoint.wait_idle())
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 client did not close after lifecycle-free request",
                )
            })?;
        Ok(())
    })
    .await
    {
        Ok(result) => result,
        Err(_) => Err(io::Error::other("HTTP/3 lifecycle-free request did not complete promptly").into()),
    };

    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;

    let events = fixture
        .state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event state was poisoned"))?;
    if !events.is_empty()
        || fixture.state.requests_started.load(Ordering::Acquire) != 1
        || !fixture.state.startup_completed.load(Ordering::Acquire)
        || fixture.state.shutdown_completed.load(Ordering::Acquire)
    {
        return Err(io::Error::other(format!(
            "{}: omitted lifecycle hooks were invoked or HTTP/3 serving did not complete; events={events:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_lifecycle_http3_connection_init_failure_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        endpoint,
        fixture.app.clone(),
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));

    let workflow = async {
        let (ready_endpoint, mut ready_sender) =
            new_http3_client(address, &tls_clients.http3).await?;
        let mut ready = send_http3_request(
            &mut ready_sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (ready_status, ready_body, _) = collect_http3_response(&mut ready).await?;
        verify_lifecycle_response(case, b"started\n", ready_status, &ready_body)?;
        ready_endpoint.close(quinn::VarInt::from_u32(0), b"lifecycle readiness complete");
        ready_endpoint.wait_idle().await;

        close_http3_peer_during_server_connection_creation(address, &tls_clients.http3, case)
            .await?;
        wait_for_lifecycle_http3_connection_error(&fixture.state, case).await?;

        let (recovery_endpoint, mut recovery_sender) =
            new_http3_client(address, &tls_clients.http3).await?;
        let mut recovery = send_http3_request(
            &mut recovery_sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (recovery_status, recovery_body, _) = collect_http3_response(&mut recovery).await?;
        recovery_endpoint.close(
            quinn::VarInt::from_u32(0),
            b"lifecycle HTTP/3 connection initialization recovery complete",
        );
        recovery_endpoint.wait_idle().await;
        verify_lifecycle_response(case, b"started\n", recovery_status, &recovery_body)
    }
    .await;

    fixture.shutdown_sender.send_replace(true);
    let server_result = join_lifecycle_server(server).await;
    workflow?;
    server_result?;
    verify_lifecycle_startup_shutdown(case, &fixture.state)
}

async fn run_lifecycle_http3_pending_handshake_shutdown_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    // The handshake is held before request dispatch, so the request service
    // is not observed by the peer. Keep lifecycle coverage while using the
    // regular HTTP/3 contract service instantiation.
    let (application, _) = contract_app_with_state(fixture.shutdown_sender.clone());
    let (_, _, quic_server_config) = test_tls_configs()?;
    let server_endpoint = quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse()?)?;
    let address = server_endpoint.local_addr()?;
    let shutdown = fixture.shutdown_receiver.clone();
    let mut server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown),
        lifecycle_server_config(Arc::clone(&fixture.hooks), case)?,
    ));

    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let (handshake_started_sender, handshake_started_receiver) = tokio::sync::oneshot::channel();
    let release_gate = Arc::new((Mutex::new(false), Condvar::new()));
    let client_config =
        blocking_http3_client_config(handshake_started_sender, Arc::clone(&release_gate))?;
    let client_thread = std::thread::Builder::new()
        .name("uvicorn-rs-pending-h3-handshake".into())
        .spawn(move || -> ProbeResult<()> {
            let runtime = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()?;
            runtime.block_on(async move {
                let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse()?)?;
                endpoint.set_default_client_config(client_config);
                let connecting = endpoint.connect(address, "localhost")?;
                let handshake = timeout(Duration::from_millis(server_wait_ms), connecting).await;
                endpoint.close(
                    quinn::VarInt::from_u32(0),
                    b"pending HTTP/3 handshake shutdown probe complete",
                );
                timeout(Duration::from_secs(2), endpoint.wait_idle())
                    .await
                    .map_err(|_| {
                        io::Error::new(
                            io::ErrorKind::TimedOut,
                            "pending HTTP/3 client endpoint did not become idle",
                        )
                    })?;
                match handshake {
                    // The server's shutdown result is observed before this
                    // verifier is released. Once released, a final handshake
                    // flight can race with the endpoint close packet, so both
                    // transport outcomes are valid for this probe.
                    Ok(Err(_)) | Ok(Ok(_)) => Ok(()),
                    Err(_) => Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "HTTP/3 handshake did not observe server shutdown",
                    )
                    .into()),
                }
            })
        })?;

    let handshake_started = timeout(
        Duration::from_millis(server_wait_ms),
        handshake_started_receiver,
    )
    .await;
    fixture.shutdown_sender.send_replace(true);
    let server_before_client_release =
        timeout(Duration::from_millis(server_wait_ms), &mut server).await;
    let stopped_while_handshake_pending = matches!(&server_before_client_release, Ok(Ok(_)));
    release_blocking_handshake_verifier(&release_gate);

    let server_result: ProbeResult<Result<(), uvicorn_rs::ServeError>> =
        match server_before_client_release {
            Ok(Ok(result)) => Ok(result),
            Ok(Err(error)) => Err(error.into()),
            Err(_) => match timeout(Duration::from_secs(2), &mut server).await {
                Ok(Ok(result)) => Ok(result),
                Ok(Err(error)) => Err(error.into()),
                Err(_) => {
                    server.abort();
                    Err(io::Error::new(
                        io::ErrorKind::TimedOut,
                        "HTTP/3 server did not stop after releasing the pending handshake",
                    )
                    .into())
                }
            },
        };
    let client_result = timeout(
        Duration::from_secs(3),
        tokio::task::spawn_blocking(move || client_thread.join()),
    )
    .await;

    if !matches!(handshake_started, Ok(Ok(()))) {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "client did not reach server certificate verification during the HTTP/3 handshake",
        )
        .into());
    }
    if !stopped_while_handshake_pending {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 server did not return while the client handshake was held pending",
        )
        .into());
    }
    match server_result? {
        Err(uvicorn_rs::ServeError::GracefulShutdownTimedOut)
            if required_str(case, "expected_server_error")?
                == "active connections exceeded the graceful-shutdown deadline" => {}
        Ok(()) => {
            return Err(io::Error::other(
                "HTTP/3 server drained a handshake while the peer verifier was still blocked",
            )
            .into())
        }
        Err(error) => {
            return Err(io::Error::other(format!(
                "pending HTTP/3 handshake produced unexpected server error: {error}"
            ))
            .into())
        }
    }
    match client_result {
        Ok(Ok(Ok(Ok(())))) => {}
        Ok(Ok(Ok(Err(error)))) => return Err(error),
        Ok(Ok(Err(_))) => {
            return Err(io::Error::other("HTTP/3 client probe thread panicked").into())
        }
        Ok(Err(error)) => return Err(error.into()),
        Err(error) => return Err(error.into()),
    }
    verify_lifecycle_startup_shutdown(case, &fixture.state)
}

fn release_blocking_handshake_verifier(gate: &Arc<(Mutex<bool>, Condvar)>) {
    let (released, condition) = &**gate;
    let mut released = match released.lock() {
        Ok(released) => released,
        Err(poisoned) => poisoned.into_inner(),
    };
    *released = true;
    condition.notify_all();
}

async fn wait_for_lifecycle_http3_connection_error(
    state: &LifecycleState,
    case: &Value,
) -> ProbeResult<()> {
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let observed = state
            .connection_errors
            .lock()
            .map_err(|_| io::Error::other("lifecycle connection error observations were poisoned"))?
            .iter()
            .any(|(phase, peer_addr)| {
                *phase == ServerErrorPhase::Connection && peer_addr.is_some()
            });
        if observed {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: HTTP/3 initialization failure produced no connection observation",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        sleep(Duration::from_millis(10)).await;
    }
}

async fn run_lifecycle_http3_workflow(
    case: &Value,
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    fixture: &LifecycleFixture,
    server: &tokio::task::JoinHandle<Result<(), uvicorn_rs::ServeError>>,
    active_request: &mut watch::Receiver<bool>,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let mut ready = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "ready_path")?,
        b"",
    )
    .await?;
    let (ready_status, ready_body, _) = collect_http3_response(&mut ready).await?;
    verify_lifecycle_response(case, b"started\n", ready_status, &ready_body)?;

    let id = required_str(case, "id")?.to_owned();
    let path = required_str(case, "path")?.to_owned();
    let active = tokio::spawn(async move {
        let mut sender = sender;
        let mut stream = send_http3_request(&mut sender, address, "GET", &path, b"").await?;
        let (status, body, _) = collect_http3_response(&mut stream).await?;
        Ok::<_, Box<dyn Error + Send + Sync>>((status, body))
    });
    wait_for_lifecycle_signal(active_request, "HTTP/3 held request did not start").await?;
    fixture.shutdown_sender.send_replace(true);
    tokio::time::sleep(lifecycle_release_delay(case)?).await;
    let drained_too_early =
        server.is_finished() || fixture.state.shutdown_completed.load(Ordering::Acquire);
    fixture.state.release_request.send_replace(true);
    let (status, body) = active.await??;
    endpoint.close(quinn::VarInt::from_u32(0), b"lifecycle case complete");
    endpoint.wait_idle().await;
    if drained_too_early {
        return Err(io::Error::other(format!(
            "{id}: HTTP/3 shutdown completed before the held response was released"
        ))
        .into());
    }
    verify_lifecycle_response(case, b"released\n", status, &body)
}

async fn wait_for_lifecycle_signal(
    receiver: &mut watch::Receiver<bool>,
    message: &'static str,
) -> ProbeResult<()> {
    tokio::time::timeout(Duration::from_secs(2), async {
        while !*receiver.borrow() {
            receiver.changed().await.map_err(|_| {
                io::Error::other("lifecycle observation channel closed before signal")
            })?;
        }
        Ok::<(), io::Error>(())
    })
    .await
    .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, message))??;
    Ok(())
}

fn verify_lifecycle_response(
    case: &Value,
    expected_body: &[u8],
    status: u16,
    body: &[u8],
) -> ProbeResult<()> {
    if status != StatusCode::OK.as_u16() || body != expected_body {
        return Err(io::Error::other(format!(
            "{}: lifecycle response mismatch: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(body)
        ))
        .into());
    }
    Ok(())
}

fn verify_lifecycle_state(case: &Value, state: &LifecycleState) -> ProbeResult<()> {
    verify_lifecycle_startup_shutdown(case, state)?;
    if !state
        .shutdown_saw_response_body_drop
        .load(Ordering::Acquire)
    {
        return Err(io::Error::other(
            "application shutdown ran before the active response body was dropped",
        )
        .into());
    }
    Ok(())
}

fn verify_lifecycle_startup_shutdown(case: &Value, state: &LifecycleState) -> ProbeResult<()> {
    if !state.startup_completed.load(Ordering::Acquire) {
        return Err(io::Error::other("application startup hook did not complete").into());
    }
    if !state.shutdown_completed.load(Ordering::Acquire) {
        return Err(io::Error::other("application shutdown hook did not complete").into());
    }
    verify_lifecycle_events(case, state)
}

fn verify_lifecycle_events(case: &Value, state: &LifecycleState) -> ProbeResult<()> {
    let expected: &[&str] = match required_str(case, "operation")? {
        "native-lifecycle-startup-error"
        | "native-lifecycle-startup-timeout"
        | "native-lifecycle-startup-panic" => &["startup"],
        "native-lifecycle-drain"
        | "native-lifecycle-websocket"
        | "native-lifecycle-readiness-pending"
        | "native-lifecycle-shutdown-error"
        | "native-lifecycle-shutdown-timeout"
        | "native-lifecycle-shutdown-panic"
        | "native-lifecycle-server-and-shutdown-error"
        | "native-lifecycle-server-timeout"
        | "native-lifecycle-readiness-error" => &["startup", "shutdown"],
        "native-lifecycle-http3-connection-init-failure-recovery"
        | "native-lifecycle-http3-pending-handshake-shutdown" => &["startup", "shutdown"],
        "native-lifecycle-service-and-response-body-errors" => &["startup", "shutdown"],
        operation => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown lifecycle event contract {operation:?}"),
            )
            .into());
        }
    };
    let actual = state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event log was poisoned"))?;
    if actual.as_slice() != expected {
        return Err(io::Error::other(format!(
            "{}: lifecycle events differed: expected {expected:?}, got {actual:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

fn verify_lifecycle_readiness_error_observation(
    case: &Value,
    state: &LifecycleState,
) -> ProbeResult<()> {
    if required_str(case, "expected_server_error_phase")? != "readiness"
        || required_str(case, "expected_server_error_type")? != "io"
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "lifecycle readiness-error case has unsupported server error expectations",
        )
        .into());
    }
    let expected_message = required_str(case, "expected_server_error_message")?;
    let observations = state
        .readiness_errors
        .lock()
        .map_err(|_| io::Error::other("readiness error observations were poisoned"))?;
    if observations.len() != 1
        || observations[0].0 != ServerErrorPhase::Readiness
        || !observations[0].1
        || observations[0].2 != expected_message
    {
        return Err(io::Error::other(format!(
            "{}: readiness error observer mismatch: expected one io readiness error {expected_message:?}, got {observations:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

fn verify_lifecycle_application_error_observations(
    case: &Value,
    state: &LifecycleState,
) -> ProbeResult<()> {
    let expected = case["expected_observations"].as_array().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_observations must be an array",
        )
    })?;
    let observations = state
        .application_errors
        .lock()
        .map_err(|_| io::Error::other("application error observations were poisoned"))?;
    if observations.len() != expected.len() {
        return Err(io::Error::other(format!(
            "{}: error observer event count differed: expected {}, got {}: {observations:?}",
            required_str(case, "id")?,
            expected.len(),
            observations.len()
        ))
        .into());
    }
    for (index, (phase, is_io_error, message)) in observations.iter().enumerate() {
        let expected = &expected[index];
        let expected_phase = required_str(expected, "phase")?;
        let expected_is_io_error = expected["is_io_error"].as_bool().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected observation is_io_error must be a boolean",
            )
        })?;
        let expected_message = required_str(expected, "message")?;
        if server_error_phase_name(*phase) != expected_phase
            || *is_io_error != expected_is_io_error
            || message != expected_message
        {
            return Err(io::Error::other(format!(
                "{}: error observer event {index} differed: expected {expected:?}, got {phase:?}/{is_io_error}/{message:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    Ok(())
}

fn lifecycle_release_delay(case: &Value) -> ProbeResult<Duration> {
    let delay = case["release_after_shutdown_ms"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "lifecycle drain case has no release delay",
        )
    })?;
    Ok(Duration::from_millis(delay))
}

async fn join_lifecycle_server(
    server: tokio::task::JoinHandle<Result<(), uvicorn_rs::ServeError>>,
) -> ProbeResult<()> {
    match tokio::time::timeout(Duration::from_secs(4), server).await {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "native lifecycle server did not stop",
        )
        .into()),
    }
}

#[derive(Debug)]
struct BlockingServerCertVerifier {
    inner: Arc<dyn quic_rustls::client::danger::ServerCertVerifier>,
    handshake_started: Mutex<Option<tokio::sync::oneshot::Sender<()>>>,
    release_gate: Arc<(Mutex<bool>, Condvar)>,
}

impl quic_rustls::client::danger::ServerCertVerifier for BlockingServerCertVerifier {
    fn verify_server_cert(
        &self,
        end_entity: &quic_rustls::pki_types::CertificateDer<'_>,
        intermediates: &[quic_rustls::pki_types::CertificateDer<'_>],
        server_name: &quic_rustls::pki_types::ServerName<'_>,
        ocsp_response: &[u8],
        now: quic_rustls::pki_types::UnixTime,
    ) -> Result<quic_rustls::client::danger::ServerCertVerified, quic_rustls::Error> {
        let verified = self.inner.verify_server_cert(
            end_entity,
            intermediates,
            server_name,
            ocsp_response,
            now,
        )?;
        let handshake_started = self
            .handshake_started
            .lock()
            .map_err(|_| quic_rustls::Error::General("handshake signal lock poisoned".into()))?
            .take();
        if let Some(handshake_started) = handshake_started {
            let _ = handshake_started.send(());
        }

        let (released, condition) = &*self.release_gate;
        let mut released = released
            .lock()
            .map_err(|_| quic_rustls::Error::General("handshake release lock poisoned".into()))?;
        while !*released {
            released = condition.wait(released).map_err(|_| {
                quic_rustls::Error::General("handshake release lock poisoned".into())
            })?;
        }
        Ok(verified)
    }

    fn verify_tls12_signature(
        &self,
        message: &[u8],
        cert: &quic_rustls::pki_types::CertificateDer<'_>,
        dss: &quic_rustls::DigitallySignedStruct,
    ) -> Result<quic_rustls::client::danger::HandshakeSignatureValid, quic_rustls::Error> {
        self.inner.verify_tls12_signature(message, cert, dss)
    }

    fn verify_tls13_signature(
        &self,
        message: &[u8],
        cert: &quic_rustls::pki_types::CertificateDer<'_>,
        dss: &quic_rustls::DigitallySignedStruct,
    ) -> Result<quic_rustls::client::danger::HandshakeSignatureValid, quic_rustls::Error> {
        self.inner.verify_tls13_signature(message, cert, dss)
    }

    fn supported_verify_schemes(&self) -> Vec<quic_rustls::SignatureScheme> {
        self.inner.supported_verify_schemes()
    }
}

fn blocking_http3_client_config(
    handshake_started: tokio::sync::oneshot::Sender<()>,
    release_gate: Arc<(Mutex<bool>, Condvar)>,
) -> ProbeResult<quinn::ClientConfig> {
    let certificate_dir =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/native-core/tls");
    let certificate_file = std::fs::File::open(certificate_dir.join("localhost-cert.pem"))?;
    let certificates = rustls_pemfile::certs(&mut std::io::BufReader::new(certificate_file))
        .collect::<Result<Vec<_>, _>>()?;
    if certificates.is_empty() {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "test certificate is empty").into());
    }
    let mut roots = quic_rustls::RootCertStore::empty();
    for certificate in certificates {
        roots.add(certificate)?;
    }
    let inner = quic_rustls::client::WebPkiServerVerifier::builder(Arc::new(roots)).build()?;
    let verifier = BlockingServerCertVerifier {
        inner,
        handshake_started: Mutex::new(Some(handshake_started)),
        release_gate,
    };
    let mut tls = quic_rustls::ClientConfig::builder()
        .dangerous()
        .with_custom_certificate_verifier(Arc::new(verifier))
        .with_no_client_auth();
    tls.alpn_protocols = vec![b"h3".to_vec()];
    let crypto = quinn::crypto::rustls::QuicClientConfig::try_from(tls)?;
    Ok(quinn::ClientConfig::new(Arc::new(crypto)))
}

fn test_tls_configs() -> ProbeResult<(TlsAcceptor, TlsClients, quinn::ServerConfig)> {
    test_tls_configs_with_quic_alpns(vec![b"h3".to_vec()])
}

fn test_tls_configs_with_quic_alpns(
    quic_alpn_protocols: Vec<Vec<u8>>,
) -> ProbeResult<(TlsAcceptor, TlsClients, quinn::ServerConfig)> {
    let certificate_dir =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/native-core/tls");
    let certificate_file = std::fs::File::open(certificate_dir.join("localhost-cert.pem"))?;
    let certificates = rustls_pemfile::certs(&mut std::io::BufReader::new(certificate_file))
        .collect::<Result<Vec<_>, _>>()?;
    if certificates.is_empty() {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "test certificate is empty").into());
    }
    let key_file = std::fs::File::open(certificate_dir.join("localhost-key.pem"))?;
    let key = rustls_pemfile::private_key(&mut std::io::BufReader::new(key_file))?
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "test key is missing"))?;

    let mut server_config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(certificates.clone(), key.clone_key())?;
    server_config.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];
    let acceptor = TlsAcceptor::from(Arc::new(server_config));

    let mut quic_server_config = quic_rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(certificates.clone(), key)?;
    quic_server_config.alpn_protocols = quic_alpn_protocols;
    let quic_server_config = quinn::crypto::rustls::QuicServerConfig::try_from(quic_server_config)?;
    let quic_server_config = quinn::ServerConfig::with_crypto(Arc::new(quic_server_config));

    let mut roots = rustls::RootCertStore::empty();
    for certificate in &certificates {
        roots.add(certificate.clone())?;
    }
    let connector = |protocol: &[u8]| {
        let mut client_config = rustls::ClientConfig::builder()
            .with_root_certificates(roots.clone())
            .with_no_client_auth();
        client_config.alpn_protocols = vec![protocol.to_vec()];
        TlsConnector::from(Arc::new(client_config))
    };
    let mut http3_tls = quic_rustls::ClientConfig::builder()
        .with_root_certificates(roots.clone())
        .with_no_client_auth();
    http3_tls.alpn_protocols = vec![b"h3".to_vec()];
    let http3 = quinn::ClientConfig::new(Arc::new(
        quinn::crypto::rustls::QuicClientConfig::try_from(http3_tls)?,
    ));
    let mut http3_non_h3_tls = quic_rustls::ClientConfig::builder()
        .with_root_certificates(roots.clone())
        .with_no_client_auth();
    http3_non_h3_tls.alpn_protocols = vec![b"http/1.1".to_vec()];
    let http3_non_h3 = quinn::ClientConfig::new(Arc::new(
        quinn::crypto::rustls::QuicClientConfig::try_from(http3_non_h3_tls)?,
    ));

    Ok((
        acceptor,
        TlsClients {
            http1: connector(b"http/1.1"),
            http2: connector(b"h2"),
            http3,
            http3_non_h3,
        },
        quic_server_config,
    ))
}

fn contract_app(shutdown: watch::Sender<bool>) -> ContractApp {
    contract_app_with_state(shutdown).0
}

fn contract_app_with_state(shutdown: watch::Sender<bool>) -> (ContractApp, Arc<AppState>) {
    let (peer_write_half_close_release, _) = watch::channel(false);
    let (peer_read_half_close_observation, _) = watch::channel(None);
    let (peer_read_half_close_unavailable_result, _) = watch::channel(None);
    let (http3_response_cancel_release, _) = watch::channel(false);
    let (upgrade_registration_outcome, _) = watch::channel(None);
    let (websocket_error_observation, _) = watch::channel(None);
    let state = Arc::new(AppState {
        fail_next_readiness: AtomicBool::new(false),
        panic_next_readiness: AtomicBool::new(false),
        readiness_gate: Mutex::new(ReadinessGate::default()),
        stream_complete: AtomicBool::new(false),
        graceful_timeout_stream_drops: Arc::new(AtomicUsize::new(0)),
        cancelled_streams: Arc::new(AtomicUsize::new(0)),
        cancelled_h2_streams: Arc::new(AtomicUsize::new(0)),
        http3_cancelled_streams: Arc::new(AtomicUsize::new(0)),
        request_lifetime_waiters: AtomicUsize::new(0),
        request_lifetime_reason_checks: Arc::new(AtomicUsize::new(0)),
        request_future_drops: Arc::new(AtomicUsize::new(0)),
        request_ends_while_connection_open: Arc::new(AtomicUsize::new(0)),
        request_connections_closed: Arc::new(AtomicUsize::new(0)),
        request_lifetime_peer_eof_available: Arc::new(AtomicBool::new(false)),
        request_lifetime_peer_eof: Arc::new(AtomicBool::new(false)),
        peer_write_half_close_started: AtomicBool::new(false),
        peer_write_half_close_release,
        peer_read_half_close_observation,
        peer_read_half_close_unavailable_result,
        response_chunks_polled: Arc::new(AtomicUsize::new(0)),
        response_streams_dropped: Arc::new(AtomicUsize::new(0)),
        upload_bytes_received: AtomicUsize::new(0),
        upload_body_errors: AtomicUsize::new(0),
        http3_body_pending: AtomicBool::new(false),
        http3_body_errors: AtomicUsize::new(0),
        http3_response_cancel_pending: AtomicBool::new(false),
        http3_response_cancel_waiters: AtomicUsize::new(0),
        http3_response_cancel_release,
        upload_tasks_dropped: Arc::new(AtomicUsize::new(0)),
        shutdown,
        upgrade_registration_outcome,
        websocket_error_observation,
    });
    (
        ContractApp {
            state: Arc::clone(&state),
        },
        state,
    )
}

async fn run_cases(
    address: SocketAddr,
    tls_address: SocketAddr,
    h3_address: SocketAddr,
    tls_clients: &TlsClients,
    cases: &[Value],
    observed_errors: &Arc<Mutex<Vec<ObservedServerError>>>,
) -> ProbeResult<()> {
    for case in cases {
        let id = required_str(case, "id")?;
        let operation = required_str(case, "operation")?;
        if matches!(
            operation,
            "graceful-drain"
                | "http2-graceful-drain"
                | "http3-graceful-drain"
                | "graceful-timeout-abort"
                | "http3-graceful-timeout-abort"
        ) || operation.starts_with("native-lifecycle-")
            || operation == "native-service-error-propagation"
            || operation == "native-http3-alpn-contract"
            || operation == "native-http3-no-common-alpn-recovery"
            || operation == "native-http3-no-common-alpn-lifecycle-recovery"
            || operation == "native-http3-endpoint-close-lifecycle"
            || operation == "native-http3-idle-connection-shutdown-timeout"
            || operation == "native-http3-peer-goaway-drain"
            || operation == "native-http3-server-shutdown-open-connection"
            || operation == "native-http3-incomplete-request-recovery"
            || operation == "native-http3-response-send-cancel"
            || operation == "native-http1-tls-pending-handshake-shutdown"
            || operation == "native-http1-connection-slot-reuse"
            || operation == "native-http1-connection-task-reaping"
            || operation == "native-http1-service-panic-recovery"
            || operation == "native-http1-upgrade-session"
            || operation == "native-http1-websocket"
        {
            continue;
        }
        if operation == "server-config-validation" {
            run_server_config_validation_case(case).await?;
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        if operation == "public-error-contract" {
            run_public_error_contract_case(case)?;
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        if operation == "server-error-observer-panic" {
            run_server_error_observer_panic_case(case).await?;
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        if case["protocol"].as_str() == Some("http3") {
            let error_count = observed_errors
                .lock()
                .map_err(|_| io::Error::other("error-observation lock was poisoned"))?
                .len();
            match operation {
                "request" => run_http3_request_case(h3_address, &tls_clients.http3, case).await?,
                "http3-service-panic-recovery" => {
                    run_http3_service_panic_recovery_case(h3_address, &tls_clients.http3, case)
                        .await?
                }
                "readiness" => {
                    run_http3_readiness_case(h3_address, &tls_clients.http3, case).await?
                }
                "readiness-pending" => {
                    run_http3_readiness_pending_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-upload-pending" => {
                    run_http3_upload_pending_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-upload-reset" => {
                    run_http3_upload_reset_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-response-error" => {
                    run_http3_response_error_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-request-trailers" => {
                    run_http3_request_trailers_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-connection-close" => {
                    run_http3_connection_close_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-invalid-trailer-sequence" => {
                    run_http3_invalid_trailer_sequence_case(h3_address, &tls_clients.http3, case)
                        .await?
                }
                "http3-invalid-control-frame" => {
                    run_http3_invalid_control_frame_case(h3_address, &tls_clients.http3, case)
                        .await?
                }
                "http3-connection-init-failure-recovery" => {
                    run_http3_connection_init_failure_case(
                        h3_address,
                        &tls_clients.http3,
                        case,
                        observed_errors.as_ref(),
                        error_count,
                    )
                    .await?
                }
                "http3-stream-progress" => {
                    run_http3_stream_progress_case(h3_address, &tls_clients.http3, case).await?
                }
                "http3-backpressure" => {
                    run_http3_backpressure_case(h3_address, &tls_clients.http3, case).await?
                }
                operation => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        format!("unknown HTTP/3 operation {operation:?} in case {id}"),
                    )
                    .into());
                }
            }
            verify_expected_server_error(case, observed_errors, error_count)?;
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        if matches!(
            case["protocol"].as_str(),
            Some("https/1.1") | Some("h2-tls")
        ) {
            match operation {
                "tls-invalid-handshake-recovery" => {
                    run_tls_invalid_handshake_recovery_case(
                        tls_address,
                        tls_clients,
                        case,
                        observed_errors,
                    )
                    .await?;
                }
                "native-https-upgrade-session-error" => {
                    run_tls_http1_upgrade_session_error_case(
                        tls_address,
                        tls_clients,
                        case,
                        observed_errors,
                    )
                    .await?;
                }
                "http1-write-half-close"
                    if case["observe_peer_read_half_close"].as_bool() == Some(true) =>
                {
                    run_http1_peer_read_half_close_case(
                        tls_address,
                        Some(&tls_clients.http1),
                        case,
                    )
                    .await?;
                }
                _ => run_tls_connection_security_case(tls_address, tls_clients, case).await?,
            }
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        let error_count = observed_errors
            .lock()
            .map_err(|_| io::Error::other("error-observation lock was poisoned"))?
            .len();
        if case["protocol"].as_str() == Some("h2c-prior-knowledge") {
            match operation {
                "request" => run_http2_request_case(address, case).await?,
                "peer-address" => run_http2_peer_address_case(address, case).await?,
                "http2-disconnect" => run_http2_disconnect_case(address, case).await?,
                "http2-request-lifetime" => run_http2_request_lifetime_case(address, case).await?,
                "http2-backpressure" => run_http2_backpressure_case(address, case).await?,
                operation => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        format!("unknown HTTP/2 operation {operation:?} in case {id}"),
                    )
                    .into());
                }
            }
            verify_expected_server_error(case, observed_errors, error_count)?;
            let mut output = io::stdout().lock();
            writeln!(output, "PASS {id}")?;
            output.flush()?;
            continue;
        }
        match operation {
            "request" => run_request_case(address, case).await?,
            "peer-address" => run_peer_address_case(address, case).await?,
            "http1-write-half-close" => run_http1_write_half_close_case(address, case).await?,
            "readiness" => run_readiness_case(address, case).await?,
            "readiness-pending" => run_readiness_pending_case(address, case).await?,
            "stream-progress" => run_stream_progress_case(address, case).await?,
            "incomplete-response" => run_incomplete_response_case(address, case).await?,
            "disconnect" => run_disconnect_case(address, case).await?,
            "response-backpressure" => run_response_backpressure_case(address, case).await?,
            "request-upload-disconnect" => {
                run_request_upload_disconnect_case(address, case).await?
            }
            "graceful-drain" => run_graceful_drain_case(address, case).await?,
            operation => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("unknown operation {operation:?} in case {id}"),
                )
                .into());
            }
        }
        verify_expected_server_error(case, observed_errors, error_count)?;
        let mut output = io::stdout().lock();
        writeln!(output, "PASS {id}")?;
        output.flush()?;
    }
    Ok(())
}

async fn run_server_config_validation_case(case: &Value) -> ProbeResult<()> {
    let fixture = lifecycle_fixture();
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let mut config = uvicorn_rs::ServerConfig {
        application_lifecycle: Some(fixture.hooks.clone()),
        ..uvicorn_rs::ServerConfig::default()
    };
    match required_str(case, "invalid_configuration")? {
        "zero-connection-limit" => config.max_connections = 0,
        "connection-limit-overflow" => {
            config.max_connections = tokio::sync::Semaphore::MAX_PERMITS + 1;
        }
        "graceful-timeout-overflow" => config.graceful_shutdown_timeout = Duration::MAX,
        "lifecycle-timeout-overflow" => {
            config.application_startup_timeout = Duration::MAX;
        }
        invalid_configuration => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown invalid server configuration {invalid_configuration:?}"),
            )
            .into());
        }
    }

    let shutdown = shutdown_on_change(fixture.shutdown_receiver.clone());
    let error: uvicorn_rs::ServeError = tokio::time::timeout(Duration::from_secs(2), async {
        let result = match case
            .get("protocol")
            .and_then(Value::as_str)
            .unwrap_or("http/1.1")
        {
            "http/1.1" => uvicorn_rs::serve_tcp(listener, fixture.app, shutdown, config).await,
            "https/1.1" => {
                let (tls_acceptor, _, _) = test_tls_configs()?;
                uvicorn_rs::serve_tls(listener, tls_acceptor, fixture.app, shutdown, config).await
            }
            protocol => {
                return Err(io::Error::other(format!(
                    "unsupported validation protocol {protocol:?}"
                ))
                .into())
            }
        };
        result.err().ok_or_else(|| -> Box<dyn Error + Send + Sync> {
            io::Error::other("invalid server configuration unexpectedly succeeded").into()
        })
    })
    .await
    .map_err(|_| io::Error::other("invalid server configuration did not return promptly"))??;
    let observed_variant = match &error {
        uvicorn_rs::ServeError::InvalidConnectionLimit => "invalid-connection-limit",
        uvicorn_rs::ServeError::ConnectionLimitTooLarge => "connection-limit-too-large",
        uvicorn_rs::ServeError::InvalidGracefulShutdownTimeout => {
            "invalid-graceful-shutdown-timeout"
        }
        uvicorn_rs::ServeError::InvalidApplicationLifecycleTimeout => {
            "invalid-application-lifecycle-timeout"
        }
        other => {
            return Err(io::Error::other(format!(
                "unexpected server configuration error: {other}"
            ))
            .into());
        }
    };
    if observed_variant != required_str(case, "expected_error")?
        || error.to_string() != required_str(case, "expected_error_display")?
        || error.source().is_some()
    {
        return Err(io::Error::other(format!(
            "server configuration error contract differed: variant={observed_variant}, error={error}"
        ))
        .into());
    }
    verify_configuration_rejected_before_lifecycle(&fixture.state)?;
    Ok(())
}

fn verify_configuration_rejected_before_lifecycle(state: &LifecycleState) -> ProbeResult<()> {
    let events = state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event state was poisoned"))?;
    if !events.is_empty()
        || state.startup_completed.load(Ordering::Acquire)
        || state.shutdown_completed.load(Ordering::Acquire)
        || state.requests_started.load(Ordering::Acquire) != 0
    {
        return Err(io::Error::other(format!(
            "invalid configuration invoked lifecycle hooks or served a request: {events:?}"
        ))
        .into());
    }
    Ok(())
}

fn run_public_error_contract_case(case: &Value) -> ProbeResult<()> {
    let default_config = uvicorn_rs::ServerConfig::default();
    if default_config.service_error_policy
        != uvicorn_rs::ServiceErrorPolicy::RespondInternalServerError
    {
        return Err(io::Error::other("default service error policy differed").into());
    }
    if format!("{default_config:?}") != required_str(case, "expected_default_config_debug")? {
        return Err(io::Error::other("default ServerConfig debug output differed").into());
    }

    let fixture = lifecycle_fixture();
    let configured_config = uvicorn_rs::ServerConfig {
        max_connections: 8,
        graceful_shutdown_timeout: Duration::from_millis(250),
        application_startup_timeout: Duration::from_millis(125),
        application_shutdown_timeout: Duration::from_millis(175),
        application_lifecycle: Some(fixture.hooks.clone()),
        error_observer: Some(Arc::new(|_| {})),
        service_error_policy: uvicorn_rs::ServiceErrorPolicy::Propagate,
    };
    if configured_config.service_error_policy != uvicorn_rs::ServiceErrorPolicy::Propagate {
        return Err(io::Error::other("configured service error policy differed").into());
    }
    if format!("{configured_config:?}") != required_str(case, "expected_configured_config_debug")? {
        return Err(io::Error::other("configured ServerConfig debug output differed").into());
    }

    let server_shutdown_error = || uvicorn_rs::ServeError::ServerAndApplicationShutdown {
        server: Box::new(uvicorn_rs::ServeError::Accept(io::Error::other(
            "accept sentinel",
        ))),
        application: Box::new(uvicorn_rs::ServeError::ApplicationLifecycleFailed {
            stage: uvicorn_rs::ApplicationLifecycleStage::Shutdown,
            error: Box::new(io::Error::other("shutdown sentinel")),
        }),
    };
    let cases = case["errors"].as_array().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "error expectations must be an array",
        )
    })?;
    for expected in cases {
        let variant = required_str(expected, "variant")?;
        let error = match variant {
            "invalid-connection-limit" => uvicorn_rs::ServeError::InvalidConnectionLimit,
            "invalid-graceful-shutdown-timeout" => {
                uvicorn_rs::ServeError::InvalidGracefulShutdownTimeout
            }
            "invalid-application-lifecycle-timeout" => {
                uvicorn_rs::ServeError::InvalidApplicationLifecycleTimeout
            }
            "startup-failed" => uvicorn_rs::ServeError::ApplicationLifecycleFailed {
                stage: uvicorn_rs::ApplicationLifecycleStage::Startup,
                error: Box::new(io::Error::other("startup sentinel")),
            },
            "shutdown-failed" => uvicorn_rs::ServeError::ApplicationLifecycleFailed {
                stage: uvicorn_rs::ApplicationLifecycleStage::Shutdown,
                error: Box::new(io::Error::other("shutdown sentinel")),
            },
            "startup-panicked" => uvicorn_rs::ServeError::ApplicationLifecyclePanicked {
                stage: uvicorn_rs::ApplicationLifecycleStage::Startup,
            },
            "shutdown-panicked" => uvicorn_rs::ServeError::ApplicationLifecyclePanicked {
                stage: uvicorn_rs::ApplicationLifecycleStage::Shutdown,
            },
            "startup-timed-out" => uvicorn_rs::ServeError::ApplicationLifecycleTimedOut {
                stage: uvicorn_rs::ApplicationLifecycleStage::Startup,
            },
            "shutdown-timed-out" => uvicorn_rs::ServeError::ApplicationLifecycleTimedOut {
                stage: uvicorn_rs::ApplicationLifecycleStage::Shutdown,
            },
            "server-and-application-shutdown" => server_shutdown_error(),
            "accept-failed" => uvicorn_rs::ServeError::Accept(io::Error::other("accept sentinel")),
            "graceful-shutdown-timed-out" => uvicorn_rs::ServeError::GracefulShutdownTimedOut,
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("unknown public ServeError variant {variant:?}"),
                )
                .into());
            }
        };

        let display = error.to_string();
        if display != required_str(expected, "display")? {
            return Err(
                io::Error::other(format!("{variant} display differed: {display:?}")).into(),
            );
        }
        match expected.get("source").and_then(Value::as_str) {
            Some("none") => {
                if Error::source(&error).is_some() {
                    return Err(io::Error::other(format!(
                        "{variant} unexpectedly exposed an error source"
                    ))
                    .into());
                }
            }
            Some(expected_source) => {
                let source = Error::source(&error)
                    .ok_or_else(|| io::Error::other(format!("{variant} omitted its source")))?;
                if source.to_string() != expected_source {
                    return Err(io::Error::other(format!(
                        "{variant} source differed: {:?}",
                        source.to_string()
                    ))
                    .into());
                }
            }
            None => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("{variant} is missing its expected source field"),
                )
                .into());
            }
        }

        match (error.shutdown_failures(), expected.get("shutdown_failures")) {
            (None, Some(Value::Null)) => {}
            (Some((server, application)), Some(Value::Array(failures)))
                if failures.len() == 2
                    && failures[0].as_str() == Some(server.to_string().as_str())
                    && failures[1].as_str() == Some(application.to_string().as_str()) => {}
            _ => {
                return Err(
                    io::Error::other(format!("{variant} shutdown failure pair differed")).into(),
                );
            }
        }
    }
    Ok(())
}

async fn run_isolated_service_error_propagation_case(case: &Value) -> ProbeResult<()> {
    if required_str(case, "operation")? != "native-service-error-propagation" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "service error propagation case has an unexpected operation",
        )
        .into());
    }
    let case_id = required_str(case, "id")?.to_owned();

    let failure_kind = required_str(case, "failure_kind")?;
    let (expected_phase, expected_message, expected_fault_path) = match failure_kind {
        "service" => ("service", "injected service error", "/service-error"),
        "readiness" => ("readiness", "injected readiness failure", "/ready"),
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown service error failure kind {other:?}"),
            )
            .into());
        }
    };
    if required_str(case, "expected_server_error_phase")? != expected_phase
        || required_str(case, "expected_server_error_type")? != "io"
        || required_str(case, "expected_server_error_message")? != expected_message
        || required_str(case, "fault_path")? != expected_fault_path
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "service error propagation expectations differ from the selected failure",
        )
        .into());
    }

    let service_error_policy = match required_str(case, "service_error_policy")? {
        "propagate" => uvicorn_rs::ServiceErrorPolicy::Propagate,
        "respond-internal-server-error" => {
            uvicorn_rs::ServiceErrorPolicy::RespondInternalServerError
        }
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown service_error_policy {other:?}"),
            )
            .into());
        }
    };
    let protocol = required_str(case, "protocol")?;
    let expected_recovery_scope = match protocol {
        "http/1.1" => "fresh-connection",
        "h2c-prior-knowledge" | "http3" => "same-connection",
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported service error propagation protocol {other:?}"),
            )
            .into());
        }
    };
    if required_str(case, "recovery_scope")? != expected_recovery_scope {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "service error recovery scope differs from its protocol",
        )
        .into());
    }
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .filter(|ms| (1..=5_000).contains(ms))
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "server_wait_ms must be between 1 and 5000",
            )
        })?;

    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let observed_errors = Arc::new(Mutex::new(Vec::<ObservedServerError>::new()));
    let error_log = Arc::clone(&observed_errors);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        let mut cause: Option<&(dyn Error + 'static)> = Some(event.error());
        let mut is_io_error = false;
        while let Some(error) = cause {
            if error.is::<io::Error>() {
                is_io_error = true;
                break;
            }
            cause = error.source();
        }
        if let Ok(mut observations) = error_log.lock() {
            observations.push(ObservedServerError {
                phase: event.phase(),
                peer_addr: event.peer_addr(),
                is_io_error,
                is_direct_io_error: event.error().is::<io::Error>(),
                has_error_source: event.error().source().is_some(),
                h3_error_code: h3_connection_error_code(event.error()),
                message: event.error().to_string(),
            });
        }
    });
    let config = uvicorn_rs::ServerConfig {
        max_connections: 8,
        graceful_shutdown_timeout: Duration::from_millis(500),
        error_observer: Some(error_observer),
        service_error_policy,
        ..uvicorn_rs::ServerConfig::default()
    };
    let application = contract_app(shutdown_sender.clone());
    let (address, mut server, http3_client_config) = match protocol {
        "http/1.1" | "h2c-prior-knowledge" => {
            let listener = TcpListener::bind("127.0.0.1:0").await?;
            let address = listener.local_addr()?;
            let server = tokio::spawn(uvicorn_rs::serve_tcp(
                listener,
                application,
                shutdown_on_change(shutdown_receiver),
                config,
            ));
            (address, server, None)
        }
        "http3" => {
            let (_, tls_clients, quic_server_config) = test_tls_configs()?;
            let endpoint =
                quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
            let address = endpoint.local_addr()?;
            let server = tokio::spawn(uvicorn_rs::serve_http3(
                endpoint,
                application,
                shutdown_on_change(shutdown_receiver),
                config,
            ));
            (address, server, Some(tls_clients.http3))
        }
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported service error propagation protocol {other:?}"),
            )
            .into());
        }
    };

    let workflow = match tokio::time::timeout(Duration::from_secs(5), async {
        match protocol {
            "http/1.1" => run_service_error_propagation_http1(address, case).await,
            "h2c-prior-knowledge" => run_service_error_propagation_http2(address, case).await,
            "http3" => match http3_client_config.as_ref() {
                Some(client_config) => {
                    run_service_error_propagation_http3(address, client_config, case).await
                }
                None => Err(io::Error::other("HTTP/3 client config is missing").into()),
            },
            other => Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsupported service error propagation protocol {other:?}"),
            )
            .into()),
        }
    })
    .await
    {
        Ok(workflow) => workflow,
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            format!(
                "{case_id}: native service error propagation protocol workflow exceeded 5 seconds"
            ),
        )
        .into()),
    };

    shutdown_sender.send_replace(true);
    let server_result =
        tokio::time::timeout(Duration::from_millis(server_wait_ms), &mut server).await;
    if server_result.is_err() {
        server.abort();
        let _ = tokio::time::timeout(Duration::from_secs(1), &mut server).await;
    }
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => {}
        Ok(Ok(Err(error))) => return Err(error.into()),
        Ok(Err(error)) => return Err(error.into()),
        Err(_) => {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{case_id}: native service error propagation server did not stop within {server_wait_ms} ms"
                ),
            )
            .into());
        }
    }
    verify_service_error_observation(case, &observed_errors)
}

async fn run_service_error_propagation_http1(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    if required_str(case, "failure_kind")? == "readiness" {
        let (status, body) =
            read_service_error_http1_response(address, required_str(case, "arm_path")?).await?;
        verify_service_error_http_response(case, status, &body, "arm_status", "arm_body")?;
    }

    let path = required_str(case, "fault_path")?;
    let mut client = tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address))
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/1.1 error probe connect timed out",
            )
        })??;
    let request = format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    client.write_all(request.as_bytes()).await?;
    let mut first_byte = [0_u8; 1];
    match tokio::time::timeout(Duration::from_secs(2), client.read(&mut first_byte)).await {
        Ok(Ok(0)) => {}
        Ok(Ok(_)) => {
            return Err(io::Error::other(format!(
                "{}: HTTP/1.1 propagated application error committed response bytes before aborting",
                required_str(case, "id")?
            ))
            .into());
        }
        Ok(Err(error)) if error.kind() == io::ErrorKind::ConnectionReset => {}
        Ok(Err(error)) => {
            return Err(io::Error::other(format!(
                "{}: HTTP/1.1 error probe ended with unexpected read error: {error}",
                required_str(case, "id")?
            ))
            .into());
        }
        Err(_) => {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: HTTP/1.1 propagated application error did not abort the connection before response headers",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
    }

    let (status, body) =
        read_service_error_http1_response(address, required_str(case, "recovery_path")?).await?;
    verify_service_error_http_response(case, status, &body, "recovery_status", "recovery_body")
}

async fn read_service_error_http1_response(
    address: SocketAddr,
    path: &str,
) -> ProbeResult<(u16, Vec<u8>)> {
    let mut client = tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address))
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/1.1 request connect timed out",
            )
        })??;
    let request = format!("GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    client.write_all(request.as_bytes()).await?;
    let (status, headers) =
        tokio::time::timeout(Duration::from_secs(2), read_response_head(&mut client)).await??;
    let (body, complete) = tokio::time::timeout(
        Duration::from_secs(2),
        read_response_body(&mut client, &headers),
    )
    .await??;
    if !complete {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            format!("HTTP/1.1 response for {path} ended before its body completed"),
        )
        .into());
    }
    Ok((status, body))
}

async fn run_service_error_propagation_http2(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) = h2::client::handshake(socket).await?;
    let mut driver = tokio::spawn(connection);
    let workflow: ProbeResult<()> = async {
        if required_str(case, "failure_kind")? == "readiness" {
            let (status, body) =
                read_http2_small_response(&mut sender, required_str(case, "arm_path")?).await?;
            verify_service_error_http_response(case, status.as_u16(), &body, "arm_status", "arm_body")?;
        }

        let expected_reset_reason = required_str(case, "expected_reset_reason")?;
        if expected_reset_reason != "INTERNAL_ERROR" {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "HTTP/2 error propagation requires the INTERNAL_ERROR stream reset",
            )
            .into());
        }
        sender = sender.clone().ready().await?;
        let request = http2_service_error_request(address, required_str(case, "fault_path")?)?;
        let (response, _request_body) = sender.send_request(request, true)?;
        match tokio::time::timeout(Duration::from_secs(2), response).await {
            Ok(Err(error)) if error.reason() == Some(h2::Reason::INTERNAL_ERROR) => {}
            Ok(Err(error)) => {
                return Err(io::Error::other(format!(
                    "{}: HTTP/2 error stream reset reason differed: {:?}",
                    required_str(case, "id")?,
                    error.reason()
                ))
                .into());
            }
            Ok(Ok(response)) => {
                return Err(io::Error::other(format!(
                    "{}: HTTP/2 service error returned response status {} instead of resetting the stream before headers",
                    required_str(case, "id")?,
                    response.status()
                ))
                .into());
            }
            Err(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!(
                        "{}: HTTP/2 error stream did not reset before response headers",
                        required_str(case, "id")?
                    ),
                )
                .into());
            }
        }

        let (status, body) =
            read_http2_small_response(&mut sender, required_str(case, "recovery_path")?).await?;
        verify_service_error_http_response(
            case,
            status.as_u16(),
            &body,
            "recovery_status",
            "recovery_body",
        )
    }
    .await;

    drop(sender);
    let driver_result = tokio::time::timeout(Duration::from_secs(2), &mut driver).await;
    if driver_result.is_err() {
        driver.abort();
        let _ = tokio::time::timeout(Duration::from_secs(1), &mut driver).await;
    }
    workflow?;
    match driver_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/2 client driver remained active after its sender closed",
        )
        .into()),
    }
}

fn http2_service_error_request(address: SocketAddr, path: &str) -> ProbeResult<Request<()>> {
    Ok(Request::builder()
        .method("GET")
        .uri(format!("http://localhost:{}{path}", address.port()))
        .header("host", "localhost")
        .body(())?)
}

async fn run_service_error_propagation_http3(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let workflow: ProbeResult<()> = async {
        if required_str(case, "failure_kind")? == "readiness" {
            let mut arm = send_http3_request(
                &mut sender,
                address,
                "GET",
                required_str(case, "arm_path")?,
                b"",
            )
            .await?;
            let (status, body, _) = collect_http3_response(&mut arm).await?;
            verify_service_error_http_response(case, status, &body, "arm_status", "arm_body")?;
        }

        if required_str(case, "expected_reset_reason")? != "H3_INTERNAL_ERROR" {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "HTTP/3 error propagation requires the H3_INTERNAL_ERROR stream reset",
            )
            .into());
        }
        let mut failed = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "fault_path")?,
            b"",
        )
        .await?;
        match tokio::time::timeout(Duration::from_secs(2), failed.recv_response()).await {
            Ok(Err(h3::error::StreamError::RemoteTerminate { code, .. }))
                if code == Code::H3_INTERNAL_ERROR => {}
            Ok(Err(error)) => {
                return Err(io::Error::other(format!(
                    "{}: HTTP/3 error stream reset differed from H3_INTERNAL_ERROR: {error:?}",
                    required_str(case, "id")?
                ))
                .into());
            }
            Ok(Ok(response)) => {
                return Err(io::Error::other(format!(
                    "{}: HTTP/3 service error returned response status {} instead of resetting the stream before headers",
                    required_str(case, "id")?,
                    response.status()
                ))
                .into());
            }
            Err(_) => {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    format!(
                        "{}: HTTP/3 error stream did not reset before response headers",
                        required_str(case, "id")?
                    ),
                )
                .into());
            }
        }

        let mut recovery = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut recovery).await?;
        verify_service_error_http_response(
            case,
            status,
            &body,
            "recovery_status",
            "recovery_body",
        )
    }
    .await;

    endpoint.close(
        quinn::VarInt::from_u32(0),
        b"service error propagation case complete",
    );
    let endpoint_result = tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle()).await;
    workflow?;
    if endpoint_result.is_err() {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 client endpoint did not become idle after stream recovery",
        )
        .into());
    }
    Ok(())
}

fn verify_service_error_http_response(
    case: &Value,
    status: u16,
    body: &[u8],
    status_field: &str,
    body_field: &str,
) -> ProbeResult<()> {
    let expected_status = required_status(case, status_field)?;
    let expected_body = required_str(case, body_field)?;
    if status != expected_status || body != expected_body.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: response differed: status={status}, body={:?}; expected status={expected_status}, body={expected_body:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(body)
        ))
        .into());
    }
    Ok(())
}

fn verify_service_error_observation(
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
) -> ProbeResult<()> {
    let expected_phase = required_str(case, "expected_server_error_phase")?;
    let expected_message = required_str(case, "expected_server_error_message")?;
    let observations = observed_errors
        .lock()
        .map_err(|_| io::Error::other("service error observations were poisoned"))?;
    let matching: Vec<_> = observations
        .iter()
        .filter(|observation| {
            server_error_phase_name(observation.phase) == expected_phase
                && observation.message == expected_message
        })
        .collect();
    if matching.len() != 1 {
        return Err(io::Error::other(format!(
            "{}: expected one {expected_phase} observer event with the original io::Error message {expected_message:?}, got {matching:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    let observation = matching[0];
    if !observation.is_io_error
        || !observation.is_direct_io_error
        || observation.peer_addr.is_none()
        || observation.h3_error_code.is_some()
    {
        return Err(io::Error::other(format!(
            "{}: propagated service error lost its direct io::Error observer type or peer metadata: {observation:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_server_error_observer_panic_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let observer: ServerErrorObserver = Arc::new(|_| {
        std::panic::resume_unwind(Box::new("injected server error observer panic"));
    });
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        contract_app(shutdown_sender.clone()),
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            error_observer: Some(observer),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let result: ProbeResult<()> = async {
        let mut failed = request(
            address,
            required_str(case, "method")?,
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let (status, headers) = read_response_head(&mut failed).await?;
        let (body, complete) = read_response_body(&mut failed, &headers).await?;
        if status != required_status(case, "expected_status")?
            || body != required_str(case, "expected_body")?.as_bytes()
            || !complete
        {
            return Err(
                io::Error::other("observer panic changed the service-error response").into(),
            );
        }

        let mut recovery =
            request(address, "GET", required_str(case, "recovery_path")?, b"").await?;
        let (status, headers) = read_response_head(&mut recovery).await?;
        let (body, complete) = read_response_body(&mut recovery, &headers).await?;
        if status != required_status(case, "recovery_status")?
            || body != required_str(case, "recovery_body")?.as_bytes()
            || !complete
        {
            return Err(io::Error::other("server did not recover after observer panic").into());
        }
        Ok(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(2), server).await;
    result?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "observer-panic contract server did not stop",
        )
        .into()),
    }
}

type Http3Sender = h3::client::SendRequest<h3_quinn::OpenStreams, Bytes>;

async fn new_http3_client(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
) -> ProbeResult<(quinn::Endpoint, Http3Sender)> {
    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(client_config.clone());
    let connection = endpoint.connect(address, "localhost")?.await?;
    let (mut driver, sender) = h3::client::new(h3_quinn::Connection::new(connection)).await?;
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|context| driver.poll_close(context)).await;
    });
    Ok((endpoint, sender))
}

async fn close_http3_peer_during_server_connection_creation(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let stream_limit = case["client_max_concurrent_uni_streams"]
        .as_u64()
        .ok_or("client_max_concurrent_uni_streams must be an unsigned integer")?;
    if stream_limit != 0 {
        return Err("connection creation probe requires zero server unidirectional streams".into());
    }
    let close_error_code = case["client_close_error_code"]
        .as_u64()
        .ok_or("client_close_error_code must be an unsigned integer")?;
    let mut transport = quinn::TransportConfig::default();
    transport.max_concurrent_uni_streams(quinn::VarInt::from_u64(stream_limit)?);
    let mut constrained_client_config = client_config.clone();
    constrained_client_config.transport_config(Arc::new(transport));

    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(constrained_client_config);
    let connection = timeout(
        Duration::from_secs(2),
        endpoint.connect(address, "localhost")?,
    )
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 connection-creation peer did not complete QUIC handshake",
        )
    })??;

    // A zero stream limit leaves the native H3 constructor waiting to open its
    // required control stream. Let the accepted QUIC connection reach that
    // point, then close the peer while Connection::new is still pending.
    sleep(Duration::from_millis(100)).await;
    connection.close(
        quinn::VarInt::from_u64(close_error_code)?,
        b"peer closes during HTTP/3 connection creation",
    );
    timeout(Duration::from_secs(2), endpoint.wait_idle())
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "QUIC peer did not close"))?;
    Ok(())
}

async fn send_http3_request(
    sender: &mut Http3Sender,
    address: SocketAddr,
    method: &str,
    path: &str,
    body: &[u8],
) -> ProbeResult<h3::client::RequestStream<h3_quinn::BidiStream<Bytes>, Bytes>> {
    send_http3_request_with_trailers(sender, address, method, path, body, None).await
}

async fn send_http3_request_with_trailers(
    sender: &mut Http3Sender,
    address: SocketAddr,
    method: &str,
    path: &str,
    body: &[u8],
    trailers: Option<http::HeaderMap>,
) -> ProbeResult<h3::client::RequestStream<h3_quinn::BidiStream<Bytes>, Bytes>> {
    let uri = format!("https://localhost:{}{path}", address.port());
    let request = Request::builder().method(method).uri(uri).body(())?;
    let mut stream = sender.send_request(request).await?;
    if !body.is_empty() {
        stream.send_data(Bytes::copy_from_slice(body)).await?;
    }
    if let Some(trailers) = trailers {
        stream.send_trailers(trailers).await?;
    }
    stream.finish().await?;
    Ok(stream)
}

async fn collect_http3_response(
    stream: &mut h3::client::RequestStream<h3_quinn::BidiStream<Bytes>, Bytes>,
) -> ProbeResult<(u16, Vec<u8>, Option<http::HeaderMap>)> {
    let response = stream.recv_response().await?;
    let status = response.status().as_u16();
    let mut body = Vec::new();
    while let Some(mut data) = stream.recv_data().await? {
        let len = data.remaining();
        body.extend_from_slice(data.chunk());
        data.advance(len);
    }
    let trailers = stream.recv_trailers().await?;
    Ok((status, body, trailers))
}

async fn run_http3_request_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let method = case["method"].as_str().unwrap_or("GET");
    let path = required_str(case, "path")?;
    let body = case["body"].as_str().unwrap_or("").as_bytes();
    let mut stream = send_http3_request(&mut sender, address, method, path, body).await?;
    let (status, response_body, response_trailers) = collect_http3_response(&mut stream).await?;
    let expected_status = case["expected_status"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "expected_status is missing"))?
        as u16;
    let expected_body = required_str(case, "expected_body")?;
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 case complete");
    endpoint.wait_idle().await;
    let trailers_match = case["expected_trailer"].as_str().is_none_or(|expected| {
        response_trailers
            .as_ref()
            .and_then(|trailers| trailers.get("x-contract-trailer"))
            .and_then(|value| value.to_str().ok())
            == Some(expected)
    });
    if status != expected_status || response_body != expected_body.as_bytes() || !trailers_match {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 response mismatch: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&response_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_service_panic_recovery_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    if case.get("arm_path").is_some() {
        let mut arm = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "arm_path")?,
            b"",
        )
        .await?;
        let (arm_status, arm_body, _) = collect_http3_response(&mut arm).await?;
        if arm_status != required_status(case, "arm_status")?
            || arm_body != required_str(case, "arm_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: readiness panic was not armed: status={arm_status}, body={:?}",
                required_str(case, "id")?,
                String::from_utf8_lossy(&arm_body)
            ))
            .into());
        }
    }

    let mut failed = timeout(
        Duration::from_secs(2),
        send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "path")?,
            b"",
        ),
    )
    .await??;
    let (status, body, _) =
        timeout(Duration::from_secs(2), collect_http3_response(&mut failed)).await??;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: panicking service response differed: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let mut recovery = timeout(
        Duration::from_secs(2),
        send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        ),
    )
    .await??;
    let (status, body, _) = timeout(
        Duration::from_secs(2),
        collect_http3_response(&mut recovery),
    )
    .await??;
    if status != required_status(case, "recovery_status")?
        || body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: same-connection recovery response differed: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 panic recovery case complete",
    );
    endpoint.wait_idle().await;
    Ok(())
}

async fn run_http3_readiness_pending_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;

    let mut arm = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "arm_path")?,
        b"",
    )
    .await?;
    let (arm_status, arm_body, _) = collect_http3_response(&mut arm).await?;
    if arm_status != required_status(case, "arm_status")?
        || arm_body != required_str(case, "arm_body")?.as_bytes()
    {
        return Err(io::Error::other("HTTP/3 readiness gate was not armed").into());
    }

    let started = Instant::now();
    let mut pending = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "request_path")?,
        b"",
    )
    .await?;
    let (status, body, _) = collect_http3_response(&mut pending).await?;
    let elapsed_ms = started.elapsed().as_millis();
    let minimum_pending_ms = case["minimum_pending_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "minimum_pending_ms is missing")
    })?;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
        || elapsed_ms < u128::from(minimum_pending_ms)
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 service did not resume after Pending readiness; status={status}, elapsed={elapsed_ms}ms, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let mut state = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "state_path")?,
        b"",
    )
    .await?;
    let (state_status, state_body, _) = collect_http3_response(&mut state).await?;
    endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 readiness case complete",
    );
    endpoint.wait_idle().await;
    if state_status != required_status(case, "state_status")?
        || state_body != required_str(case, "expected_state_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 readiness gate did not record Pending and recovery: status={state_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&state_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_readiness_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    tokio::time::timeout(Duration::from_secs(2), async {
        let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
        let result = async {
            for (path_field, status_field, body_field) in [
                ("arm_path", "arm_status", Some("arm_body")),
                ("fault_path", "fault_status", Some("fault_body")),
                ("recovery_path", "recovery_status", Some("recovery_body")),
            ] {
                let mut response = send_http3_request(
                    &mut sender,
                    address,
                    "GET",
                    required_str(case, path_field)?,
                    b"",
                )
                .await?;
                let (status, body, _) = collect_http3_response(&mut response).await?;
                let expected_status = required_status(case, status_field)?;
                let body_matches = body_field.is_none_or(|field| {
                    case[field]
                        .as_str()
                        .is_some_and(|expected| body == expected.as_bytes())
                });
                if status != expected_status || !body_matches {
                    return Err(io::Error::other(format!(
                        "{}: HTTP/3 {path_field} returned status {status} and body {:?}, expected status {expected_status} and the configured body",
                        required_str(case, "id")?,
                        String::from_utf8_lossy(&body)
                    ))
                    .into());
                }
            }
            Ok::<_, Box<dyn Error + Send + Sync>>(())
        }
        .await;
        endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 readiness error case complete",
        );
        tokio::time::timeout(Duration::from_millis(250), endpoint.wait_idle())
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 readiness error client cleanup timed out",
                )
            })?;
        result
    })
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 readiness error handshake, requests, or cleanup timed out",
        )
    })?
}

async fn run_http3_upload_pending_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let uri = format!(
        "https://localhost:{}{}",
        address.port(),
        required_str(case, "path")?
    );
    let request = Request::builder().method("POST").uri(uri).body(())?;
    let mut upload = sender.send_request(request).await?;

    if case
        .get("empty_data_frame_before_body")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        upload.send_data(Bytes::new()).await?;
    }

    let mut state = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "state_path")?,
        b"",
    )
    .await?;
    let (state_status, state_body, _) = collect_http3_response(&mut state).await?;
    if state_status != StatusCode::OK.as_u16()
        || state_body != required_str(case, "expected_pending_state")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 request body did not enter Pending before upload: status={state_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&state_body)
        ))
        .into());
    }

    upload
        .send_data(Bytes::copy_from_slice(
            required_str(case, "body")?.as_bytes(),
        ))
        .await?;
    upload.finish().await?;
    let (status, body, _) = collect_http3_response(&mut upload).await?;
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 upload case complete");
    endpoint.wait_idle().await;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: resumed HTTP/3 upload response differed: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_upload_reset_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let uri = format!(
        "https://localhost:{}{}",
        address.port(),
        required_str(case, "path")?
    );
    let request = Request::builder().method("POST").uri(uri).body(())?;
    let mut upload = sender.send_request(request).await?;

    let mut state = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "state_path")?,
        b"",
    )
    .await?;
    let (state_status, state_body, _) = collect_http3_response(&mut state).await?;
    if state_status != StatusCode::OK.as_u16()
        || state_body != required_str(case, "expected_pending_state")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: reset request body did not enter Pending before peer reset: status={state_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&state_body)
        ))
        .into());
    }

    upload.stop_stream(Code::H3_REQUEST_CANCELLED);
    let (status, body, _) = collect_http3_response(&mut upload).await?;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: reset HTTP/3 upload response differed: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let mut recovery = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (recovery_status, recovery_body, _) = collect_http3_response(&mut recovery).await?;
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 reset case complete");
    endpoint.wait_idle().await;
    if recovery_status != required_status(case, "recovery_status")?
        || recovery_body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: server did not recover after reset upload: status={recovery_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&recovery_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_response_error_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let uri = format!(
        "https://localhost:{}{}",
        address.port(),
        required_str(case, "path")?
    );
    let request = Request::builder().method("GET").uri(uri).body(())?;
    let mut stream = sender.send_request(request).await?;
    stream.finish().await?;
    let response = stream.recv_response().await?;
    if response.status().as_u16() != required_status(case, "expected_status")? {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 response error route returned status {}",
            required_str(case, "id")?,
            response.status()
        ))
        .into());
    }
    let mut first = stream.recv_data().await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/3 response ended before its initial data frame",
        )
    })?;
    let first_len = first.remaining();
    let first_chunk = first.copy_to_bytes(first_len);
    if first_chunk != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 error response prefix differed: {:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&first_chunk)
        ))
        .into());
    }
    if stream.recv_data().await.is_ok() {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 response body error was not propagated to the peer",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut recovery = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (recovery_status, recovery_body, _) = collect_http3_response(&mut recovery).await?;
    endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 response error case complete",
    );
    endpoint.wait_idle().await;
    if recovery_status != StatusCode::OK.as_u16()
        || recovery_body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: server did not recover after response body error: status={recovery_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&recovery_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_request_trailers_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let mut trailers = http::HeaderMap::new();
    trailers.insert("x-contract-trailer", "verified".parse()?);
    let mut stream = send_http3_request_with_trailers(
        &mut sender,
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        required_str(case, "body")?.as_bytes(),
        Some(trailers),
    )
    .await?;
    let (status, response_body, _) = collect_http3_response(&mut stream).await?;
    let expected_status = case["expected_status"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "expected_status is missing"))?
        as u16;
    let expected_body = required_str(case, "expected_body")?;
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 case complete");
    endpoint.wait_idle().await;
    if status != expected_status || response_body != expected_body.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 request trailer was not preserved: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&response_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_connection_close_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(client_config.clone());
    let connection = endpoint.connect(address, "localhost")?.await?;
    let (mut driver, mut sender) =
        h3::client::new(h3_quinn::Connection::new(connection.clone())).await?;
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|context| driver.poll_close(context)).await;
    });

    let mut active = send_http3_request(
        &mut sender,
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let response = active.recv_response().await?;
    let first = active.recv_data().await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/3 connection-close response has no first DATA frame",
        )
    })?;
    let mut first = first;
    let first_len = first.remaining();
    let first = first.copy_to_bytes(first_len);
    if response.status() != required_status(case, "expected_status")?
        || first.as_ref() != required_str(case, "first_chunk")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 response did not reach the expected first chunk before connection close",
            required_str(case, "id")?
        ))
        .into());
    }

    connection.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 client connection-close contract",
    );
    drop(active);
    endpoint.wait_idle().await;

    let (recovery_endpoint, mut recovery_sender) = new_http3_client(address, client_config).await?;
    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_dropped_streams is missing",
        )
    })?;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(2);
    let observed_dropped = loop {
        let mut state = tokio::time::timeout_at(
            deadline,
            send_http3_request(
                &mut recovery_sender,
                address,
                "GET",
                required_str(case, "state_path")?,
                b"",
            ),
        )
        .await??;
        let (state_status, state_body, _) =
            tokio::time::timeout_at(deadline, collect_http3_response(&mut state)).await??;
        if state_status != StatusCode::OK.as_u16() {
            return Err(io::Error::other("HTTP/3 connection-close state request failed").into());
        }
        let observed_dropped = std::str::from_utf8(&state_body)?.trim().parse::<u64>()?;
        if observed_dropped == expected_dropped {
            break observed_dropped;
        }
        if observed_dropped > expected_dropped {
            return Err(io::Error::other(format!(
                "{}: expected exactly {expected_dropped} cancelled HTTP/3 producer(s), observed {observed_dropped}",
                required_str(case, "id")?
            ))
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    };

    let mut recovery = send_http3_request(
        &mut recovery_sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (recovery_status, recovery_body, _) = collect_http3_response(&mut recovery).await?;
    recovery_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 connection-close recovery complete",
    );
    recovery_endpoint.wait_idle().await;
    if observed_dropped != expected_dropped
        || recovery_status != required_status(case, "recovery_status")?
        || recovery_body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 connection close did not cancel the producer and preserve recovery: dropped={observed_dropped}, recovery_status={recovery_status}, recovery_body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&recovery_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_invalid_control_frame_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(client_config.clone());
    let connection = endpoint.connect(address, "localhost")?.await?;
    let mut control_stream = connection.open_uni().await?;

    // A client control stream starts with its stream type and SETTINGS frame.
    // DATA is forbidden on that stream, so this must close the H3 connection.
    control_stream
        .write_all(&[0x00, 0x04, 0x00, 0x00, 0x00])
        .await?;
    control_stream.flush().await?;

    let expected_code = case["expected_connection_error_code"]
        .as_u64()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_connection_error_code is missing",
            )
        })?;
    let connection_error = timeout(Duration::from_secs(2), connection.closed()).await?;
    match connection_error {
        quinn::ConnectionError::ApplicationClosed(close)
            if close.error_code.into_inner() == expected_code => {}
        error => {
            return Err(io::Error::other(format!(
                "{}: invalid control frame closed with unexpected QUIC error: {error:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    drop(control_stream);
    endpoint.wait_idle().await;

    let (recovery_endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let mut recovery = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (status, body, _) = collect_http3_response(&mut recovery).await?;
    recovery_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 invalid-control-frame recovery complete",
    );
    recovery_endpoint.wait_idle().await;
    if status != required_status(case, "recovery_status")?
        || body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: listener did not recover after invalid HTTP/3 control frame: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_connection_init_failure_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
    error_start: usize,
) -> ProbeResult<()> {
    close_http3_peer_during_server_connection_creation(address, client_config, case).await?;
    wait_for_http3_connection_error_observation(observed_errors, error_start, case).await?;

    let (recovery_endpoint, mut recovery_sender) = new_http3_client(address, client_config).await?;
    let mut recovery = send_http3_request(
        &mut recovery_sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (status, body, _) = collect_http3_response(&mut recovery).await?;
    recovery_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 connection initialization recovery complete",
    );
    recovery_endpoint.wait_idle().await;
    if status != StatusCode::OK.as_u16() || body != b"ready\n" {
        return Err(io::Error::other(format!(
            "{}: listener did not recover after an HTTP/3 connection initialization failure: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_invalid_trailer_sequence_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(client_config.clone());
    let connection = endpoint.connect(address, "localhost")?.await?;
    let observed_connection = connection.clone();
    let (mut driver, mut sender) = h3::client::new(h3_quinn::Connection::new(connection)).await?;
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|context| driver.poll_close(context)).await;
    });

    let uri = format!(
        "https://localhost:{}{}",
        address.port(),
        required_str(case, "path")?
    );
    let request = Request::builder()
        .method(required_str(case, "method")?)
        .uri(uri)
        .body(())?;
    let mut stream = sender.send_request(request).await?;
    stream
        .send_data(Bytes::copy_from_slice(
            required_str(case, "body")?.as_bytes(),
        ))
        .await?;
    let mut trailers = http::HeaderMap::new();
    trailers.insert(
        "x-contract-trailer",
        required_str(case, "trailer_value")?.parse()?,
    );
    stream.send_trailers(trailers).await?;
    stream
        .send_data(Bytes::copy_from_slice(
            required_str(case, "data_after_trailers")?.as_bytes(),
        ))
        .await?;
    let _ = stream.finish().await;

    let connection_error =
        tokio::time::timeout(Duration::from_secs(2), observed_connection.closed()).await?;
    let expected_code = case["expected_connection_error_code"]
        .as_u64()
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected_connection_error_code is missing",
            )
        })?;
    let expected_code = u32::try_from(expected_code).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_connection_error_code exceeds u32",
        )
    })?;
    match connection_error {
        quinn::ConnectionError::ApplicationClosed(reason)
            if reason.error_code == quinn::VarInt::from_u32(expected_code) => {}
        error => {
            return Err(io::Error::other(format!(
                "{}: DATA after request trailers produced the wrong connection error: {error:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    endpoint.wait_idle().await;

    let (recovery_endpoint, mut recovery_sender) = new_http3_client(address, client_config).await?;
    let mut recovery = send_http3_request(
        &mut recovery_sender,
        address,
        "GET",
        required_str(case, "recovery_path")?,
        b"",
    )
    .await?;
    let (status, body, _) = collect_http3_response(&mut recovery).await?;
    recovery_endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 invalid trailer sequence case complete",
    );
    recovery_endpoint.wait_idle().await;
    if status != required_status(case, "recovery_status")?
        || body != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: valid HTTP/3 connection did not recover after malformed frame order: status={status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_stream_progress_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let mut active = send_http3_request(
        &mut sender,
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let response = active.recv_response().await?;
    let first = active.recv_data().await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/3 stream had no first DATA frame",
        )
    })?;
    let mut first = first;
    let first_len = first.remaining();
    let first_bytes = first.copy_to_bytes(first_len);
    if response.status() != StatusCode::OK
        || first_bytes.as_ref() != required_str(case, "first_chunk")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 first response frame did not match",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut state = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "state_path")?,
        b"",
    )
    .await?;
    let (state_status, state_body, _) = collect_http3_response(&mut state).await?;
    if state_status != StatusCode::OK.as_u16()
        || state_body != required_str(case, "pending_state")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: application finished before HTTP/3 first chunk was observed",
            required_str(case, "id")?
        ))
        .into());
    }

    let second = active.recv_data().await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/3 stream had no second DATA frame",
        )
    })?;
    let mut second = second;
    let second_len = second.remaining();
    let second_bytes = second.copy_to_bytes(second_len);
    if second_bytes.as_ref() != required_str(case, "second_chunk")?.as_bytes()
        || active.recv_data().await?.is_some()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 streamed response did not finish in order",
            required_str(case, "id")?
        ))
        .into());
    }
    let _trailers = active.recv_trailers().await?;
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 case complete");
    endpoint.wait_idle().await;
    Ok(())
}

async fn run_http3_backpressure_case(
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    case: &Value,
) -> ProbeResult<()> {
    let (endpoint, mut sender) = new_http3_client(address, client_config).await?;
    let mut active = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let response = active.recv_response().await?;
    let first = active.recv_data().await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "HTTP/3 response has no first DATA frame",
        )
    })?;
    if response.status() != StatusCode::OK || first.remaining() == 0 {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 backpressure response did not start with data",
            required_str(case, "id")?
        ))
        .into());
    }

    let observe_delay = case["observe_delay_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "observe_delay_ms is missing"))?;
    tokio::time::sleep(Duration::from_millis(observe_delay)).await;
    let mut state = send_http3_request(
        &mut sender,
        address,
        "GET",
        required_str(case, "state_path")?,
        b"",
    )
    .await?;
    let (state_status, state_body, _) = collect_http3_response(&mut state).await?;
    let (polled, _) = parse_backpressure_state(&state_body)?;
    let max_polled = case["max_polled_chunks"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "max_polled_chunks is missing")
    })?;
    if state_status != StatusCode::OK.as_u16() || polled == 0 || polled > max_polled {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 server polled {polled} chunks while the reader was stalled",
            required_str(case, "id")?
        ))
        .into());
    }

    active.stop_sending(Code::H3_REQUEST_CANCELLED);
    drop(active);
    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_dropped_streams is missing",
        )
    })?;
    let mut dropped = 0_u64;
    for _ in 0..20 {
        tokio::time::sleep(Duration::from_millis(25)).await;
        let mut state = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "state_path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut state).await?;
        if status != StatusCode::OK.as_u16() {
            return Err(io::Error::other("HTTP/3 state request failed after reset").into());
        }
        let (_, observed_dropped) = parse_backpressure_state(&body)?;
        dropped = observed_dropped;
        if dropped >= expected_dropped {
            break;
        }
    }
    endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 case complete");
    endpoint.wait_idle().await;
    if dropped < expected_dropped {
        return Err(io::Error::other(format!(
            "{}: reset did not cancel the HTTP/3 response producer",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_tls_connection_security_case(
    address: SocketAddr,
    tls_clients: &TlsClients,
    case: &Value,
) -> ProbeResult<()> {
    let protocol = required_str(case, "protocol")?;
    let (connector, expected_alpn) = match protocol {
        "https/1.1" => (&tls_clients.http1, b"http/1.1".as_slice()),
        "h2-tls" => (&tls_clients.http2, b"h2".as_slice()),
        other => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unknown TLS protocol {other:?}"),
            )
            .into());
        }
    };
    let tcp_stream = TcpStream::connect(address).await?;
    let server_name = ServerName::try_from("localhost".to_owned())?;
    let tls_stream = connector.connect(server_name, tcp_stream).await?;
    if tls_stream.get_ref().1.alpn_protocol() != Some(expected_alpn) {
        return Err(io::Error::other("TLS client negotiated unexpected ALPN").into());
    }

    let request = Request::builder()
        .method(Method::GET)
        .uri("https://localhost/connection-security")
        .body(Empty::<Bytes>::new())?;
    let expected_status = case["expected_status"]
        .as_u64()
        .and_then(|status| u16::try_from(status).ok())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "expected_status is missing"))?;
    let expected_body = required_str(case, "expected_body")?;

    let response = if protocol == "https/1.1" {
        let (mut sender, connection) =
            hyper::client::conn::http1::handshake(TokioIo::new(tls_stream)).await?;
        let connection_task = tokio::spawn(connection);
        let response = sender.send_request(request).await?;
        let status = response.status().as_u16();
        let body = response.into_body().collect().await?.to_bytes();
        drop(sender);
        tokio::time::timeout(Duration::from_secs(2), connection_task).await???;
        (status, body)
    } else {
        let builder = hyper::client::conn::http2::Builder::new(TokioExecutor::new());
        let (mut sender, connection) = builder.handshake(TokioIo::new(tls_stream)).await?;
        let connection_task = tokio::spawn(connection);
        let response = sender.send_request(request).await?;
        let status = response.status().as_u16();
        let body = response.into_body().collect().await?.to_bytes();
        drop(sender);
        tokio::time::timeout(Duration::from_secs(2), connection_task).await???;
        (status, body)
    };

    if response.0 != expected_status || response.1.as_ref() != expected_body.as_bytes() {
        return Err(io::Error::other(format!(
            "TLS connection metadata mismatch: status={}, body={:?}",
            response.0,
            String::from_utf8_lossy(&response.1)
        ))
        .into());
    }
    Ok(())
}

async fn run_tls_invalid_handshake_recovery_case(
    address: SocketAddr,
    tls_clients: &TlsClients,
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
) -> ProbeResult<()> {
    let start = observed_errors
        .lock()
        .map_err(|_| io::Error::other("error-observation lock was poisoned"))?
        .len();
    let mut invalid_stream = TcpStream::connect(address).await?;
    invalid_stream
        .write_all(required_str(case, "invalid_tls_bytes")?.as_bytes())
        .await?;
    invalid_stream.shutdown().await?;
    drop(invalid_stream);

    let expected_phase = required_str(case, "expected_server_error_phase")?;
    let expected_type = required_str(case, "expected_server_error_type")?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let observed = observed_errors
            .lock()
            .map_err(|_| io::Error::other("error-observation lock was poisoned"))?
            .get(start..)
            .unwrap_or_default()
            .iter()
            .find(|observation| {
                server_error_phase_name(observation.phase) == expected_phase
                    && observation.peer_addr.is_some()
            })
            .cloned();
        if let Some(observed) = observed {
            if expected_type != "io" || !observed.is_io_error {
                return Err(io::Error::other(format!(
                    "{}: expected an I/O cause for malformed TLS input; got {observed:?}",
                    required_str(case, "id")?
                ))
                .into());
            }
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: malformed TLS input produced no connection-phase observation",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    run_tls_connection_security_case(address, tls_clients, case).await
}

fn verify_expected_server_error(
    case: &Value,
    observed_errors: &Mutex<Vec<ObservedServerError>>,
    start: usize,
) -> ProbeResult<()> {
    let Some(expected_phase) = case["expected_server_error_phase"].as_str() else {
        return Ok(());
    };
    let expected_type = required_str(case, "expected_server_error_type")?;
    let expected_h3_error_code = case["expected_server_error_h3_code"].as_u64();
    let expected_message = if expected_type == "h3" {
        case["expected_server_error_message"].as_str()
    } else {
        Some(required_str(case, "expected_server_error_message")?)
    };
    let observations = observed_errors
        .lock()
        .map_err(|_| io::Error::other("error-observation lock was poisoned"))?;
    let observed = observations
        .get(start..)
        .unwrap_or_default()
        .iter()
        .find(|observation| server_error_phase_name(observation.phase) == expected_phase);
    let Some(observed) = observed else {
        return Err(io::Error::other(format!(
            "{}: server did not report an error in phase {expected_phase:?}",
            required_str(case, "id")?
        ))
        .into());
    };
    let expected_type_matches = match expected_type {
        "io" => observed.is_io_error && expected_h3_error_code.is_none(),
        "h3" => {
            !observed.is_io_error
                && expected_h3_error_code.is_some()
                && observed.h3_error_code == expected_h3_error_code
        }
        _ => false,
    };
    if !expected_type_matches
        || observed.peer_addr.is_none()
        || expected_message.is_some_and(|message| observed.message != message)
    {
        return Err(io::Error::other(format!(
            "{}: expected {expected_type} cause {expected_message:?} with peer metadata; got {observed:?}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn wait_for_http3_connection_error_observation(
    observed_errors: &Mutex<Vec<ObservedServerError>>,
    start: usize,
    case: &Value,
) -> ProbeResult<()> {
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let observed = observed_errors
            .lock()
            .map_err(|_| io::Error::other("server error observations were poisoned"))?
            .get(start..)
            .unwrap_or_default()
            .iter()
            .any(|error| error.phase == ServerErrorPhase::Connection && error.peer_addr.is_some());
        if observed {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: HTTP/3 initialization failure produced no connection-phase observation",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        sleep(Duration::from_millis(10)).await;
    }
}

fn h3_connection_error_code(error: &(dyn Error + 'static)) -> Option<u64> {
    let mut cause = Some(error);
    while let Some(error) = cause {
        if let Some(h3::error::ConnectionError::Local {
            error: h3::error::LocalError::Application { code, .. },
            ..
        }) = error.downcast_ref::<h3::error::ConnectionError>()
        {
            return Some(code.value());
        }
        cause = error.source();
    }
    None
}

fn error_chain_contains<T: Error + 'static>(error: &(dyn Error + 'static)) -> bool {
    let mut cause = Some(error);
    while let Some(error) = cause {
        if error.is::<T>() {
            return true;
        }
        cause = error.source();
    }
    false
}

fn server_error_phase_name(phase: ServerErrorPhase) -> &'static str {
    match phase {
        ServerErrorPhase::ApplicationStartup => "application_startup",
        ServerErrorPhase::ApplicationShutdown => "application_shutdown",
        ServerErrorPhase::Readiness => "readiness",
        ServerErrorPhase::Service => "service",
        ServerErrorPhase::ResponseBody => "response_body",
        ServerErrorPhase::Connection => "connection",
    }
}

async fn run_http2_request_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let body = case["body"].as_str();
    let mut request = Request::builder()
        .method(method)
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost");
    if let Some(body) = body {
        request = request.header("content-length", body.len());
    }
    let request = request.body(Full::new(Bytes::copy_from_slice(
        body.unwrap_or_default().as_bytes(),
    )))?;
    let response = sender.send_request(request).await?;
    let status = response.status().as_u16();
    let response_body = response.into_body().collect().await?.to_bytes();
    drop(sender);
    tokio::time::timeout(Duration::from_secs(2), driver).await???;
    let expected_status = required_status(case, "expected_status")?;
    let expected_body = required_str(case, "expected_body")?;
    if status != expected_status || response_body.as_ref() != expected_body.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: expected status/body {expected_status}/{expected_body:?}; got {status}/{:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&response_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http2_peer_address_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let expected_peer = socket.local_addr()?.to_string();
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let request = Request::builder()
        .method(method)
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let response = sender.send_request(request).await?;
    let status = response.status();
    let response_body = response.into_body().collect().await?.to_bytes();
    drop(sender);
    tokio::time::timeout(Duration::from_secs(2), driver).await???;
    if status != StatusCode::OK || response_body.as_ref() != expected_peer.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: expected peer address {expected_peer:?}; got status {status} and body {:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&response_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_peer_address_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let mut stream = TcpStream::connect(address).await?;
    let expected_peer = stream.local_addr()?.to_string();
    let request =
        format!("{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).await?;
    stream.flush().await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (response_body, complete) = read_response_body(&mut stream, &headers).await?;
    if status != StatusCode::OK.as_u16() || response_body != expected_peer.as_bytes() || !complete {
        return Err(io::Error::other(format!(
            "{}: expected peer address {expected_peer:?}; got status {status}, body {:?}, complete={complete}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&response_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http1_write_half_close_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    if case["observe_peer_read_half_close"].as_bool() == Some(true) {
        return run_http1_peer_read_half_close_case(address, None, case).await;
    }
    let mut stream = TcpStream::connect(address).await?;
    let method = required_str(case, "method")?;
    let case_id = required_str(case, "id")?;
    let request_bytes = format!(
        "{method} {} HTTP/1.1\r\nHost: localhost\r\n\r\n",
        required_str(case, "path")?
    );
    stream.write_all(request_bytes.as_bytes()).await?;

    let state_path = required_str(case, "state_path")?;
    let expected_started_state = required_str(case, "expected_started_state")?.as_bytes();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let mut state_stream = request(address, "GET", state_path, b"").await?;
        let (state_status, state_headers) = read_response_head(&mut state_stream).await?;
        let (state_body, state_complete) =
            read_response_body(&mut state_stream, &state_headers).await?;
        if state_status == StatusCode::OK.as_u16()
            && state_complete
            && state_body == expected_started_state
        {
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("{case_id}: service did not hold the half-close response"),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    stream.shutdown().await?;

    let mut release_stream =
        request(address, "GET", required_str(case, "release_path")?, b"").await?;
    let (release_status, release_headers) = read_response_head(&mut release_stream).await?;
    let (release_body, release_complete) =
        read_response_body(&mut release_stream, &release_headers).await?;
    if release_status != StatusCode::OK.as_u16()
        || !release_complete
        || release_body != required_str(case, "release_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{case_id}: failed to release the held response after half-close"
        ))
        .into());
    }

    let (status, headers) = timeout(Duration::from_secs(2), read_response_head(&mut stream))
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "half-close response headers timed out",
            )
        })?
        .map_err(|error| {
            io::Error::other(format!(
                "{case_id}: failed reading half-close response headers: {error}"
            ))
        })?;
    let (body, complete) = timeout(
        Duration::from_secs(2),
        read_response_body(&mut stream, &headers),
    )
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            "half-close response body timed out",
        )
    })?
    .map_err(|error| {
        io::Error::other(format!(
            "{case_id}: failed reading half-close response body: {error}"
        ))
    })?;
    let expected_status = case["expected_status"]
        .as_u64()
        .and_then(|status| u16::try_from(status).ok())
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "case has no valid expected_status",
            )
        })?;
    if status != expected_status
        || !complete
        || body != required_str(case, "expected_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: half-closed request did not receive the expected response (status={status}, complete={complete}, body={:?})",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn http1_case_request(
    address: SocketAddr,
    connector: Option<&TlsConnector>,
    method: &str,
    path: &str,
    body: &[u8],
) -> ProbeResult<BoxedIo> {
    if let Some(connector) = connector {
        let mut stream = connect_tls_http1(address, connector).await?;
        let request = http1_request_bytes(method, path, body, true);
        stream.write_all(&request).await?;
        stream.flush().await?;
        Ok(Box::new(stream))
    } else {
        Ok(Box::new(request(address, method, path, body).await?))
    }
}

async fn http1_half_closed_case_request(
    address: SocketAddr,
    connector: Option<&TlsConnector>,
    path: &str,
) -> ProbeResult<BoxedIo> {
    let request = http1_request_bytes("GET", path, b"", false);
    if let Some(connector) = connector {
        let mut stream = connect_tls_http1(address, connector).await?;
        stream.write_all(&request).await?;
        stream.flush().await?;
        stream.get_mut().0.shutdown().await?;
        Ok(Box::new(stream))
    } else {
        let mut stream = TcpStream::connect(address).await?;
        stream.write_all(&request).await?;
        stream.flush().await?;
        stream.shutdown().await?;
        Ok(Box::new(stream))
    }
}

fn http1_request_bytes(method: &str, path: &str, body: &[u8], close: bool) -> Vec<u8> {
    let mut request = format!("{method} {path} HTTP/1.1\r\nHost: localhost\r\n");
    if close {
        request.push_str("Connection: close\r\n");
    }
    if method == "POST" || !body.is_empty() {
        request.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    request.push_str("\r\n");
    let mut bytes = request.into_bytes();
    bytes.extend_from_slice(body);
    bytes
}

async fn read_http1_case_response(
    address: SocketAddr,
    connector: Option<&TlsConnector>,
    method: &str,
    path: &str,
    body: &[u8],
) -> ProbeResult<(u16, Vec<u8>, bool)> {
    let mut stream = http1_case_request(address, connector, method, path, body).await?;
    let (status, headers) = timeout(Duration::from_secs(4), read_response_head(&mut stream))
        .await
        .map_err(|_| {
            io::Error::new(io::ErrorKind::TimedOut, "HTTP/1 response headers timed out")
        })??;
    let (body, complete) = timeout(
        Duration::from_secs(4),
        read_response_body(&mut stream, &headers),
    )
    .await
    .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/1 response body timed out"))??;
    Ok((status, body, complete))
}

async fn run_http1_peer_read_half_close_case(
    address: SocketAddr,
    connector: Option<&TlsConnector>,
    case: &Value,
) -> ProbeResult<()> {
    let case_id = required_str(case, "id")?;
    let mut target =
        http1_half_closed_case_request(address, connector, required_str(case, "path")?).await?;
    let (status, headers) = timeout(Duration::from_secs(4), read_response_head(&mut target))
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                format!("{case_id}: half-closed response headers timed out"),
            )
        })??;
    let (body, complete) = timeout(
        Duration::from_secs(4),
        read_response_body(&mut target, &headers),
    )
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            format!("{case_id}: half-closed response body timed out"),
        )
    })??;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "expected_body")?.as_bytes()
        || !complete
    {
        return Err(io::Error::other(format!(
            "{case_id}: half-closed client did not receive the expected complete response (status={status}, complete={complete}, body={:?})",
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let (state_status, state_body, state_complete) = timeout(
        Duration::from_secs(4),
        read_http1_case_response(
            address,
            connector,
            "GET",
            required_str(case, "state_path")?,
            b"",
        ),
    )
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            format!("{case_id}: peer EOF observation did not become available"),
        )
    })??;
    if state_status != StatusCode::OK.as_u16()
        || !state_complete
        || state_body != required_str(case, "expected_state_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{case_id}: expected observed raw EOF state {:?}; got status={state_status}, complete={state_complete}, body={:?}",
            required_str(case, "expected_state_body")?,
            String::from_utf8_lossy(&state_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_http2_disconnect_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let request = Request::builder()
        .method(method)
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let response = sender.send_request(request).await?;
    if response.status() != StatusCode::OK {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 stream returned status {}",
            required_str(case, "id")?,
            response.status()
        ))
        .into());
    }
    let mut body = response.into_body();
    let first = tokio::time::timeout(Duration::from_secs(2), body.frame())
        .await?
        .ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "HTTP/2 body ended early"))??
        .into_data()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "expected an HTTP/2 DATA frame"))?;
    if first.as_ref() != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: received an unexpected first HTTP/2 body frame",
            required_str(case, "id")?
        ))
        .into());
    }
    drop(body);

    let state_path = required_str(case, "state_path")?;
    let expected_count = case["expected_count"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no expected_count"))?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let state_request = Request::builder()
            .method("GET")
            .uri(format!("http://localhost{state_path}"))
            .header("host", "localhost")
            .body(Full::new(Bytes::new()))?;
        let response = sender.send_request(state_request).await?;
        let count = response.into_body().collect().await?.to_bytes();
        if count == format!("{expected_count}\n").as_bytes() {
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: HTTP/2 client reset did not drop the response producer",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }

    drop(sender);
    tokio::time::timeout(Duration::from_secs(2), driver).await???;
    Ok(())
}

async fn run_http2_request_lifetime_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) = h2::client::handshake(socket).await?;
    let driver = tokio::spawn(connection);
    sender = sender.clone().ready().await?;
    let hold_request = Request::builder()
        .method(Method::GET)
        .uri(format!("http://localhost{}", required_str(case, "path")?))
        .header("host", "localhost")
        .body(())?;
    let (response, mut request_body) = sender.send_request(hold_request, true)?;
    let response_task = tokio::spawn(response);

    let state_path = required_str(case, "state_path")?;
    let starting_state = required_str(case, "expected_start_state")?.as_bytes();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let (_, observed) = read_http2_small_response(&mut sender, state_path).await?;
        if observed == starting_state {
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/2 request did not enter its pending service state",
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    request_body.send_reset(h2::Reason::CANCEL);
    match timeout(Duration::from_secs(2), response_task).await {
        Ok(Ok(Err(_))) => {}
        Ok(Ok(Ok(_))) => {
            return Err(
                io::Error::other("reset HTTP/2 request unexpectedly received a response").into(),
            );
        }
        Ok(Err(error)) => return Err(error.into()),
        Err(_) => {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "reset HTTP/2 response future did not finish",
            )
            .into());
        }
    }

    let (status, body) =
        read_http2_small_response(&mut sender, required_str(case, "recovery_path")?).await?;
    if status != StatusCode::OK
        || body.as_slice() != required_str(case, "recovery_body")?.as_bytes()
    {
        return Err(
            io::Error::other("reset HTTP/2 stream affected its healthy sibling request").into(),
        );
    }

    let ending_state = required_str(case, "expected_end_state")?.as_bytes();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let (_, observed) = read_http2_small_response(&mut sender, state_path).await?;
        if observed == ending_state {
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("request lifetime did not end independently: {observed:?}"),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    drop(request_body);
    drop(sender);
    timeout(Duration::from_secs(2), driver)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/2 client connection driver remained live after its sender closed",
            )
        })???;

    let closed_state = required_str(case, "expected_closed_state")?.as_bytes();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let mut state_stream = request(address, "GET", state_path, b"").await?;
        let (status, headers) = read_response_head(&mut state_stream).await?;
        let (observed, complete) = read_response_body(&mut state_stream, &headers).await?;
        if status == StatusCode::OK.as_u16() && complete && observed == closed_state {
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("connection lifetime did not end after H2 close: {observed:?}"),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    Ok(())
}

async fn read_http2_small_response(
    sender: &mut h2::client::SendRequest<Bytes>,
    path: &str,
) -> ProbeResult<(StatusCode, Vec<u8>)> {
    *sender = sender.clone().ready().await?;
    let request = Request::builder()
        .method(Method::GET)
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost")
        .body(())?;
    let (response, _request_body) = sender.send_request(request, true)?;
    let response = timeout(Duration::from_secs(2), response)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                format!("HTTP/2 response headers timed out for {path}"),
            )
        })??;
    let status = response.status();
    let mut body = response.into_body();
    let mut received = Vec::new();
    while let Some(chunk) = timeout(Duration::from_secs(2), body.data())
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                format!("HTTP/2 response body timed out for {path}"),
            )
        })?
    {
        received.extend_from_slice(&chunk?);
    }
    Ok((status, received))
}

async fn run_http2_backpressure_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let request = Request::builder()
        .method(method)
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let response = sender.send_request(request).await?;
    if response.status() != StatusCode::OK {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 backpressure stream returned status {}",
            required_str(case, "id")?,
            response.status()
        ))
        .into());
    }
    let mut body = response.into_body();
    let first = tokio::time::timeout(Duration::from_secs(2), body.frame())
        .await?
        .ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "HTTP/2 body ended early"))??
        .into_data()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "expected an HTTP/2 DATA frame"))?;
    let expected_chunk_size = case["chunk_size"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no chunk_size"))?;
    if first.is_empty()
        || u64::try_from(first.len())
            .ok()
            .is_none_or(|length| length > expected_chunk_size)
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 first DATA frame has {} bytes, expected between 1 and {expected_chunk_size}",
            required_str(case, "id")?,
            first.len()
        ))
        .into());
    }

    let observe_delay_ms = case["observe_delay_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "case has no observe_delay_ms")
    })?;
    tokio::time::sleep(Duration::from_millis(observe_delay_ms)).await;
    let state_path = required_str(case, "state_path")?;
    let (polled, dropped) = read_http2_backpressure_state(&mut sender, state_path).await?;
    let max_polled = case["max_polled_chunks"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "case has no max_polled_chunks")
    })?;
    let total_chunks = case["total_chunks"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no total_chunks"))?;
    if total_chunks <= max_polled || polled == 0 || polled >= max_polled || dropped != 0 {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 slow reader allowed {polled} frames and {dropped} drops before reset",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(body);
    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_dropped_streams",
        )
    })?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let (polled, dropped) = read_http2_backpressure_state(&mut sender, state_path).await?;
        if dropped == expected_dropped {
            break;
        }
        if dropped > expected_dropped || Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: HTTP/2 response producer remained active after reset (polled={polled}, dropped={dropped})",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }

    let health_request = Request::builder()
        .method("GET")
        .uri("http://localhost/ready")
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let health = sender.send_request(health_request).await?;
    let health_status = health.status();
    let health_body = health.into_body().collect().await?.to_bytes();
    if health_status != StatusCode::OK || health_body.as_ref() != b"ready\n" {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 connection did not recover after body reset",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(sender);
    tokio::time::timeout(Duration::from_secs(2), driver).await???;
    Ok(())
}

async fn read_http2_backpressure_state(
    sender: &mut hyper::client::conn::http2::SendRequest<Full<Bytes>>,
    path: &str,
) -> ProbeResult<(u64, u64)> {
    let request = Request::builder()
        .method("GET")
        .uri(format!("http://localhost{path}"))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let response = sender.send_request(request).await?;
    if response.status() != StatusCode::OK {
        return Err(io::Error::other("HTTP/2 backpressure state request failed").into());
    }
    let body = response.into_body().collect().await?.to_bytes();
    parse_backpressure_state(&body)
}

async fn run_request_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let method = required_str(case, "method")?;
    let path = required_str(case, "path")?;
    let body = case["body"].as_str().unwrap_or("").as_bytes();
    let shutdown_write = case
        .get("shutdown_write")
        .map(|value| {
            value.as_bool().ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "shutdown_write must be a boolean",
                )
            })
        })
        .transpose()?
        .unwrap_or(false);
    let mut stream = request_with_shutdown(address, method, path, body, shutdown_write).await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    let expected_status = required_status(case, "expected_status")?;
    let expected_body = required_str(case, "expected_body")?;
    if status != expected_status || body != expected_body.as_bytes() || !complete {
        return Err(io::Error::other(format!(
            "{}: expected status/body {expected_status}/{expected_body:?}; got {status}/{:?}, complete={complete}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }
    Ok(())
}

async fn run_readiness_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let arm_path = required_str(case, "arm_path")?;
    let fault_path = required_str(case, "fault_path")?;
    let recovery_path = required_str(case, "recovery_path")?;
    for (path, expected) in [
        (arm_path, case["arm_status"].as_u64()),
        (fault_path, case["fault_status"].as_u64()),
        (recovery_path, case["recovery_status"].as_u64()),
    ] {
        let mut stream = request(address, "GET", path, b"").await?;
        let (status, headers) = read_response_head(&mut stream).await?;
        let _ = read_response_body(&mut stream, &headers).await?;
        if Some(u64::from(status)) != expected {
            return Err(io::Error::other(format!(
                "{}: {path} returned {status}, expected {expected:?}",
                required_str(case, "id")?
            ))
            .into());
        }
    }
    Ok(())
}

async fn run_readiness_pending_case(address: SocketAddr, case: &Value) -> ProbeResult<()> {
    let mut arm = request(address, "GET", required_str(case, "arm_path")?, b"").await?;
    let (arm_status, arm_headers) = read_response_head(&mut arm).await?;
    let (arm_body, arm_complete) = read_response_body(&mut arm, &arm_headers).await?;
    if arm_status != required_status(case, "arm_status")?
        || arm_body.as_slice() != required_str(case, "arm_body")?.as_bytes()
        || !arm_complete
    {
        return Err(io::Error::other(format!(
            "{}: readiness gate was not armed",
            required_str(case, "id")?
        ))
        .into());
    }

    let started = Instant::now();
    let mut pending = request(address, "GET", required_str(case, "request_path")?, b"").await?;
    let (status, headers) = read_response_head(&mut pending).await?;
    let (body, complete) = read_response_body(&mut pending, &headers).await?;
    let elapsed_ms = started.elapsed().as_millis();
    if status != required_status(case, "expected_status")?
        || body.as_slice() != required_str(case, "expected_body")?.as_bytes()
        || !complete
        || elapsed_ms
            < u128::from(case["minimum_pending_ms"].as_u64().ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidData, "minimum_pending_ms is missing")
            })?)
    {
        return Err(io::Error::other(format!(
            "{}: service did not resume after Pending readiness; status={status}, elapsed={elapsed_ms}ms, body={:?}, complete={complete}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&body)
        ))
        .into());
    }

    let mut state = request(address, "GET", required_str(case, "state_path")?, b"").await?;
    let (state_status, state_headers) = read_response_head(&mut state).await?;
    let (state_body, state_complete) = read_response_body(&mut state, &state_headers).await?;
    if state_status != required_status(case, "state_status")?
        || state_body.as_slice() != required_str(case, "expected_state_body")?.as_bytes()
        || !state_complete
    {
        return Err(io::Error::other(format!(
            "{}: readiness gate did not record Pending and recovery: status={state_status}, body={:?}",
            required_str(case, "id")?,
            String::from_utf8_lossy(&state_body)
        ))
        .into());
    }
    Ok(())
}

async fn run_stream_progress_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let started = Instant::now();
    let mut stream = request(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let first = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "stream ended before first chunk",
        )
    })?;
    let expected_first = required_str(case, "first_chunk")?;
    let first_deadline_ms = case["first_chunk_deadline_ms"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no first_chunk_deadline_ms",
        )
    })?;
    if status != StatusCode::OK.as_u16()
        || !headers.contains_key("transfer-encoding")
        || first != expected_first.as_bytes()
        || started.elapsed() > Duration::from_millis(first_deadline_ms)
    {
        return Err(io::Error::other(format!(
            "{}: first response chunk did not stream promptly",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut state_stream = request(address, "GET", required_str(case, "state_path")?, b"").await?;
    let (_, state_headers) = read_response_head(&mut state_stream).await?;
    let (state, state_complete) = read_response_body(&mut state_stream, &state_headers).await?;
    if !state_complete || state != required_str(case, "pending_state")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: application completed before the later chunk was requested",
            required_str(case, "id")?
        ))
        .into());
    }

    let second = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "stream ended before second chunk",
        )
    })?;
    let ended = read_next_chunk(&mut stream).await?.is_none();
    if second != required_str(case, "second_chunk")?.as_bytes() || !ended {
        return Err(io::Error::other(format!(
            "{}: streamed response did not finish with its second chunk",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_incomplete_response_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let mut stream = request(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    if status != required_status(case, "expected_status")?
        || body != required_str(case, "body_prefix")?.as_bytes()
        || complete
    {
        return Err(io::Error::other(format!(
            "{}: expected committed partial response followed by connection termination",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_disconnect_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let mut stream = request(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let first = read_next_chunk(&mut stream).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "disconnect stream has no first chunk",
        )
    })?;
    if status != StatusCode::OK.as_u16() || first != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: unexpected first streaming response",
            required_str(case, "id")?
        ))
        .into());
    }
    drop(headers);
    drop(stream);

    let state_path = required_str(case, "state_path")?;
    let expected_count = case["expected_count"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no expected_count"))?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let mut state_stream = request(address, "GET", state_path, b"").await?;
        let (_, state_headers) = read_response_head(&mut state_stream).await?;
        let (body, complete) = read_response_body(&mut state_stream, &state_headers).await?;
        if complete && body == format!("{expected_count}\n").as_bytes() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: body stream was not dropped after disconnect",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
}

async fn run_response_backpressure_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let path = required_str(case, "path")?;
    let mut slow_reader = request(address, required_str(case, "method")?, path, b"").await?;
    let (status, headers) = read_response_head(&mut slow_reader).await?;
    let first_chunk = read_next_chunk(&mut slow_reader).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "backpressure response ended before its first chunk",
        )
    })?;
    let expected_chunk_size = case["chunk_size"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no chunk_size"))?;
    let total_chunks = case["total_chunks"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "case has no total_chunks"))?;
    let max_polled_chunks = case["max_polled_chunks"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "case has no max_polled_chunks")
    })?;
    let observe_delay_ms = case["observe_delay_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "case has no observe_delay_ms")
    })?;
    if status != StatusCode::OK.as_u16()
        || !headers
            .get("transfer-encoding")
            .is_some_and(|value| value.eq_ignore_ascii_case("chunked"))
        || u64::try_from(first_chunk.len()).ok() != Some(expected_chunk_size)
        || total_chunks <= max_polled_chunks
    {
        return Err(io::Error::other(format!(
            "{}: response did not begin as the declared streamed body",
            required_str(case, "id")?
        ))
        .into());
    }

    tokio::time::sleep(Duration::from_millis(observe_delay_ms)).await;
    let (polled_before_disconnect, dropped_before_disconnect) =
        read_backpressure_state(address, required_str(case, "state_path")?).await?;
    if polled_before_disconnect == 0
        || polled_before_disconnect >= max_polled_chunks
        || dropped_before_disconnect != 0
    {
        return Err(io::Error::other(format!(
            "{}: slow reader allowed {polled_before_disconnect} chunks and {dropped_before_disconnect} drops before disconnect",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(slow_reader);
    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_dropped_streams",
        )
    })?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let (polled, dropped) =
            read_backpressure_state(address, required_str(case, "state_path")?).await?;
        if dropped == expected_dropped {
            return Ok(());
        }
        if dropped > expected_dropped || Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: response producer did not stop after client disconnect (polled={polled}, dropped={dropped})",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
}

async fn run_request_upload_disconnect_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let path = required_str(case, "path")?;
    let partial_body = required_str(case, "partial_body")?.as_bytes();
    let declared_length = case["declared_content_length"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no declared_content_length",
        )
    })?;
    if u64::try_from(partial_body.len())
        .ok()
        .is_none_or(|length| length >= declared_length)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "partial upload must be shorter than its declared Content-Length",
        )
        .into());
    }

    let mut upload = TcpStream::connect(address).await?;
    let headers = format!(
        "{} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: {declared_length}\r\n\r\n",
        required_str(case, "method")?
    );
    upload.write_all(headers.as_bytes()).await?;
    upload.write_all(partial_body).await?;
    upload.flush().await?;

    let state_path = required_str(case, "state_path")?;
    let expected_received = case["expected_received_bytes"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_received_bytes",
        )
    })?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let (received, errors, dropped) = read_upload_state(address, state_path).await?;
        if received >= expected_received {
            if errors != 0 || dropped != 0 {
                return Err(io::Error::other(format!(
                    "{}: upload task ended before the client disconnected",
                    required_str(case, "id")?
                ))
                .into());
            }
            break;
        }
        if Instant::now() >= deadline {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: service did not consume the partial request body (received {received} bytes)",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    drop(upload);
    let disconnect_deadline = Instant::now() + Duration::from_secs(2);

    let expected_errors = case["expected_body_errors"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_body_errors",
        )
    })?;
    let expected_dropped = case["expected_dropped_tasks"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "case has no expected_dropped_tasks",
        )
    })?;
    loop {
        let (received, errors, dropped) = read_upload_state(address, state_path).await?;
        if errors == expected_errors && dropped == expected_dropped {
            if received != expected_received {
                return Err(io::Error::other(format!(
                    "{}: observed {received} upload bytes, expected exactly {expected_received}",
                    required_str(case, "id")?
                ))
                .into());
            }
            break;
        }
        if errors > expected_errors
            || dropped > expected_dropped
            || Instant::now() >= disconnect_deadline
        {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "{}: request upload cancellation was not observed (bytes={received}, errors={errors}, dropped={dropped})",
                    required_str(case, "id")?
                ),
            )
            .into());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }

    let mut recovery = request(address, "GET", required_str(case, "recovery_path")?, b"").await?;
    let (status, headers) = read_response_head(&mut recovery).await?;
    let (body, complete) = read_response_body(&mut recovery, &headers).await?;
    if u64::from(status) != case["recovery_status"].as_u64().unwrap_or_default()
        || body != required_str(case, "recovery_body")?.as_bytes()
        || !complete
    {
        return Err(io::Error::other(format!(
            "{}: server did not recover after the incomplete upload",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn read_upload_state(
    address: std::net::SocketAddr,
    path: &str,
) -> ProbeResult<(u64, u64, u64)> {
    let mut stream = request(address, "GET", path, b"").await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    if status != StatusCode::OK.as_u16() || !complete {
        return Err(io::Error::other("upload state request did not complete").into());
    }
    let state = std::str::from_utf8(&body)?;
    let mut fields = state.trim().split(';');
    let bytes = fields
        .next()
        .and_then(|value| value.strip_prefix("bytes="))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid upload byte state"))?
        .parse::<u64>()?;
    let errors = fields
        .next()
        .and_then(|value| value.strip_prefix("errors="))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid upload error state"))?
        .parse::<u64>()?;
    let dropped = fields
        .next()
        .and_then(|value| value.strip_prefix("dropped="))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid upload drop state"))?
        .parse::<u64>()?;
    if fields.next().is_some() {
        return Err(
            io::Error::new(io::ErrorKind::InvalidData, "upload state has extra fields").into(),
        );
    }
    Ok((bytes, errors, dropped))
}

async fn read_backpressure_state(
    address: std::net::SocketAddr,
    path: &str,
) -> ProbeResult<(u64, u64)> {
    let mut stream = request(address, "GET", path, b"").await?;
    let (status, headers) = read_response_head(&mut stream).await?;
    let (body, complete) = read_response_body(&mut stream, &headers).await?;
    if status != StatusCode::OK.as_u16() || !complete {
        return Err(io::Error::other("backpressure state request did not complete").into());
    }
    parse_backpressure_state(&body)
}

fn parse_backpressure_state(body: &[u8]) -> ProbeResult<(u64, u64)> {
    let text = std::str::from_utf8(body)?;
    let mut values = text.trim().split(';');
    let polled = values
        .next()
        .and_then(|value| value.strip_prefix("polled="))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid polled state"))?
        .parse::<u64>()?;
    let dropped = values
        .next()
        .and_then(|value| value.strip_prefix("dropped="))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "invalid dropped state"))?
        .parse::<u64>()?;
    if values.next().is_some() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "backpressure state has extra fields",
        )
        .into());
    }
    Ok((polled, dropped))
}

async fn run_graceful_drain_case(address: std::net::SocketAddr, case: &Value) -> ProbeResult<()> {
    let mut active = request(
        address,
        required_str(case, "method")?,
        required_str(case, "path")?,
        b"",
    )
    .await?;
    let (status, _) = read_response_head(&mut active).await?;
    let first = read_next_chunk(&mut active).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "drained stream has no first chunk",
        )
    })?;
    if status != StatusCode::OK.as_u16() || first != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: active response did not start before shutdown",
            required_str(case, "id")?
        ))
        .into());
    }

    let mut shutdown_stream =
        request(address, "GET", required_str(case, "shutdown_path")?, b"").await?;
    let (shutdown_status, shutdown_headers) = read_response_head(&mut shutdown_stream).await?;
    let (shutdown_body, shutdown_complete) =
        read_response_body(&mut shutdown_stream, &shutdown_headers).await?;
    if shutdown_status != StatusCode::OK.as_u16()
        || shutdown_body != required_str(case, "shutdown_body")?.as_bytes()
        || !shutdown_complete
    {
        return Err(io::Error::other(format!(
            "{}: shutdown trigger response did not complete",
            required_str(case, "id")?
        ))
        .into());
    }

    let second = read_next_chunk(&mut active).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "active stream was aborted during drain",
        )
    })?;
    let ended = read_next_chunk(&mut active).await?.is_none();
    if second != required_str(case, "second_chunk")?.as_bytes() || !ended {
        return Err(io::Error::other(format!(
            "{}: graceful shutdown did not drain the active response",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_isolated_graceful_case(case: &Value) -> ProbeResult<()> {
    if case["peer_read_half_close_unavailable"].as_bool() == Some(true) {
        return run_isolated_peer_read_half_close_unavailable_case(case).await;
    }
    if required_str(case, "operation")? == "http3-graceful-drain" {
        return run_isolated_http3_graceful_case(case).await;
    }
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        contract_app(shutdown_sender.clone()),
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 16,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: None,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let result = match required_str(case, "operation")? {
        "graceful-drain" => run_graceful_drain_case(address, case).await,
        "http2-graceful-drain" => run_http2_graceful_drain_case(address, case).await,
        operation => Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("unknown isolated graceful operation {operation:?}"),
        )
        .into()),
    };
    if result.is_err() {
        shutdown_sender.send_replace(true);
    }
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    result?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "isolated graceful-shutdown server did not stop",
        )
        .into()),
    }
}

async fn run_isolated_peer_read_half_close_unavailable_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let mut outcome = state.peer_read_half_close_unavailable_result.subscribe();
    let mut server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 8,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: None,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let result = async {
        let mut client =
            tokio::time::timeout(Duration::from_secs(2), TcpStream::connect(address)).await??;
        let request = http1_request_bytes(
            required_str(case, "method")?,
            required_str(case, "path")?,
            b"",
            false,
        );
        client.write_all(&request).await?;
        client.flush().await?;
        let (status, headers) = timeout(Duration::from_secs(2), read_response_head(&mut client))
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "observer watch response headers timed out",
                )
            })??;
        let (body, complete) = timeout(
            Duration::from_secs(2),
            read_response_body(&mut client, &headers),
        )
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "observer watch response body timed out",
            )
        })??;
        if status != StatusCode::OK.as_u16() || body.as_slice() != b"watching\n" || !complete {
            return Err(io::Error::other(format!(
                "{}: peer observer did not remain held on the live connection",
                required_str(case, "id")?
            ))
            .into());
        }

        let (shutdown_status, shutdown_body, shutdown_complete) = read_http1_case_response(
            address,
            None,
            "GET",
            required_str(case, "shutdown_path")?,
            b"",
        )
        .await?;
        if shutdown_status != StatusCode::OK.as_u16()
            || shutdown_body != required_str(case, "shutdown_body")?.as_bytes()
            || !shutdown_complete
        {
            return Err(io::Error::other(format!(
                "{}: server shutdown trigger response did not complete",
                required_str(case, "id")?
            ))
            .into());
        }

        let observed = timeout(Duration::from_secs(2), async {
            loop {
                if let Some(value) = outcome.borrow_and_update().clone() {
                    return Ok::<_, io::Error>(value);
                }
                outcome.changed().await.map_err(|_| {
                    io::Error::other("peer observer shutdown-result channel closed")
                })?;
            }
        })
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "peer observer did not finish after the server closed its connection",
            )
        })??;
        let expected = required_str(case, "expected_observer_state")?;
        if observed != expected {
            return Err(io::Error::other(format!(
                "{}: expected observer shutdown state {expected:?}, got {observed:?}",
                required_str(case, "id")?
            ))
            .into());
        }
        drop(client);
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;
    if result.is_err() {
        shutdown_sender.send_replace(true);
    }
    let server_result = timeout(Duration::from_millis(server_wait_ms), &mut server).await;
    match (result, server_result) {
        (Err(error), Ok(_)) => Err(error),
        (Err(error), Err(_)) => {
            server.abort();
            let _ = server.await;
            Err(error)
        }
        (Ok(()), Ok(Ok(Ok(())))) => Ok(()),
        (Ok(()), Ok(Ok(Err(error)))) => Err(error.into()),
        (Ok(()), Ok(Err(error))) => Err(error.into()),
        (Ok(()), Err(_)) => {
            server.abort();
            let _ = server.await;
            Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "peer observer server did not stop after cleanup",
            )
            .into())
        }
    }
}

async fn run_isolated_graceful_timeout_case(case: &Value) -> ProbeResult<()> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let graceful_timeout_ms = case["graceful_timeout_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "graceful_timeout_ms is missing")
    })?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_tcp(
        listener,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 8,
            graceful_shutdown_timeout: Duration::from_millis(graceful_timeout_ms),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let mut active = request(address, "GET", required_str(case, "path")?, b"").await?;
    let (status, _) = read_response_head(&mut active).await?;
    let first = read_next_chunk(&mut active).await?.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "held response ended before shutdown",
        )
    })?;
    if status != required_status(case, "expected_status")?
        || first != required_str(case, "first_chunk")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: held response did not start before shutdown",
            required_str(case, "id")?
        ))
        .into());
    }

    shutdown_sender.send_replace(true);
    let result = tokio::time::timeout(Duration::from_millis(server_wait_ms), server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "server did not finish its graceful timeout path",
            )
        })??;
    let server_error = match result {
        Err(error @ uvicorn_rs::ServeError::GracefulShutdownTimedOut) => error,
        Ok(()) => {
            return Err(io::Error::other(format!(
                "{}: server drained a response configured to remain pending",
                required_str(case, "id")?
            ))
            .into());
        }
        Err(error) => return Err(error.into()),
    };
    if server_error.to_string() != required_str(case, "expected_server_error")? {
        return Err(io::Error::other(format!(
            "{}: graceful shutdown returned an unexpected error: {server_error}",
            required_str(case, "id")?
        ))
        .into());
    }
    drop(active);

    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_dropped_streams is missing",
        )
    })?;
    let dropped = state.graceful_timeout_stream_drops.load(Ordering::Acquire);
    if u64::try_from(dropped).ok() != Some(expected_dropped) {
        return Err(io::Error::other(format!(
            "{}: response producer drop count was {dropped}, expected {expected_dropped}",
            required_str(case, "id")?
        ))
        .into());
    }
    Ok(())
}

async fn run_isolated_http3_graceful_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        contract_app(shutdown_sender.clone()),
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 8,
            graceful_shutdown_timeout: Duration::from_secs(2),
            error_observer: None,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let result = async {
        let (endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
        let mut active = send_http3_request(
            &mut sender,
            address,
            required_str(case, "method")?,
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let response = active.recv_response().await?;
        let first = active.recv_data().await?.ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "drained HTTP/3 stream has no first chunk",
            )
        })?;
        let mut first = first;
        let first_len = first.remaining();
        let first = first.copy_to_bytes(first_len);
        if response.status() != StatusCode::OK
            || first.as_ref() != required_str(case, "first_chunk")?.as_bytes()
        {
            return Err(io::Error::other("HTTP/3 response did not start before shutdown").into());
        }

        let mut shutdown = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "shutdown_path")?,
            b"",
        )
        .await?;
        let (shutdown_status, shutdown_body, _) = collect_http3_response(&mut shutdown).await?;
        if shutdown_status != StatusCode::OK.as_u16()
            || shutdown_body != required_str(case, "shutdown_body")?.as_bytes()
        {
            return Err(
                io::Error::other("HTTP/3 shutdown trigger response did not complete").into(),
            );
        }

        let second = active.recv_data().await?.ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "HTTP/3 active response was aborted",
            )
        })?;
        let mut second = second;
        let second_len = second.remaining();
        let second = second.copy_to_bytes(second_len);
        if second.as_ref() != required_str(case, "second_chunk")?.as_bytes()
            || active.recv_data().await?.is_some()
        {
            return Err(
                io::Error::other("HTTP/3 shutdown did not drain the active response").into(),
            );
        }
        let _trailers = active.recv_trailers().await?;
        endpoint.close(quinn::VarInt::from_u32(0), b"HTTP/3 graceful case complete");
        endpoint.wait_idle().await;
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    if result.is_err() {
        shutdown_sender.send_replace(true);
    }
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    result?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "isolated HTTP/3 graceful-shutdown server did not stop",
        )
        .into()),
    }
}

async fn run_isolated_http3_graceful_timeout_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let graceful_timeout_ms = case["graceful_timeout_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "graceful_timeout_ms is missing")
    })?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let expected_server_error = required_str(case, "expected_server_error")?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let mut server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 8,
            graceful_shutdown_timeout: Duration::from_millis(graceful_timeout_ms),
            error_observer: None,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let mut client_endpoint = None;
    let mut client_sender: Option<Http3Sender> = None;
    let mut active_stream = None;
    let workflow = async {
        let (endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
        let mut active = send_http3_request(
            &mut sender,
            address,
            required_str(case, "method")?,
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let response = active.recv_response().await?;
        let first = active.recv_data().await?.ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "held HTTP/3 response ended before shutdown",
            )
        })?;
        let mut first = first;
        let first_len = first.remaining();
        let first = first.copy_to_bytes(first_len);
        if response.status() != required_status(case, "expected_status")?
            || first.as_ref() != required_str(case, "first_chunk")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: held HTTP/3 response did not start before shutdown",
                required_str(case, "id")?
            ))
            .into());
        }
        client_endpoint = Some(endpoint);
        client_sender = Some(sender);
        active_stream = Some(active);
        shutdown_sender.send_replace(true);
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;
    if workflow.is_err() {
        shutdown_sender.send_replace(true);
    }

    let server_result = tokio::time::timeout(Duration::from_millis(server_wait_ms), &mut server)
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 server did not finish its graceful timeout path",
            )
        })??;
    workflow?;
    let server_error = match server_result {
        Err(error @ uvicorn_rs::ServeError::GracefulShutdownTimedOut) => error,
        Ok(()) => {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 server drained a response configured to remain pending",
                required_str(case, "id")?
            ))
            .into());
        }
        Err(error) => return Err(error.into()),
    };
    if server_error.to_string() != expected_server_error {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 graceful shutdown returned an unexpected error: {server_error}",
            required_str(case, "id")?
        ))
        .into());
    }

    let expected_dropped = case["expected_dropped_streams"].as_u64().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "expected_dropped_streams is missing",
        )
    })?;
    let dropped = state.graceful_timeout_stream_drops.load(Ordering::Acquire);
    if u64::try_from(dropped).ok() != Some(expected_dropped) {
        return Err(io::Error::other(format!(
            "{}: HTTP/3 response producer drop count was {dropped}, expected {expected_dropped}",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(active_stream);
    drop(client_sender);
    if let Some(endpoint) = client_endpoint {
        endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 graceful timeout case complete",
        );
        endpoint.wait_idle().await;
    }
    Ok(())
}

async fn run_isolated_http3_peer_goaway_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_secs(1),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow = async {
        let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
        endpoint.set_default_client_config(tls_clients.http3.clone());
        let connection = tokio::time::timeout(
            Duration::from_secs(2),
            endpoint.connect(address, "localhost")?,
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 peer did not connect"))??;
        let (mut driver, mut sender) =
            h3::client::new(h3_quinn::Connection::new(connection.clone())).await?;
        let (goaway_sender, goaway_receiver) = tokio::sync::oneshot::channel();
        let (goaway_ack_sender, goaway_ack_receiver) = tokio::sync::oneshot::channel();
        let client_driver = tokio::spawn(async move {
            let result: ProbeResult<()> = tokio::select! {
                terminal = std::future::poll_fn(|context| driver.poll_close(context)) => {
                    Err(io::Error::other(format!(
                        "HTTP/3 client connection ended before the test sent GOAWAY: {terminal}"
                    )).into())
                }
                requested = goaway_receiver => {
                    requested.map_err(|_| io::Error::other("HTTP/3 GOAWAY request was cancelled"))?;
                    driver.shutdown(0).await?;
                    let _ = goaway_ack_sender.send(());
                    let _terminal = std::future::poll_fn(|context| driver.poll_close(context)).await;
                    Ok(())
                }
            };
            result
        });

        let mut request = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut request).await?;
        if status != required_status(case, "expected_status")?
            || body != required_str(case, "expected_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 request did not complete before peer GOAWAY",
                required_str(case, "id")?
            ))
            .into());
        }
        drop(request);

        goaway_sender
            .send(())
            .map_err(|_| io::Error::other("HTTP/3 client driver stopped before GOAWAY"))?;
        tokio::time::timeout(Duration::from_secs(2), goaway_ack_receiver)
            .await
            .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 GOAWAY was not sent"))?
            .map_err(|_| io::Error::other("HTTP/3 client driver did not acknowledge GOAWAY"))?;

        let peer_close = tokio::time::timeout(Duration::from_secs(2), connection.closed())
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "server did not close the HTTP/3 connection after peer GOAWAY",
                )
            })?;
        match peer_close {
            quinn::ConnectionError::ApplicationClosed(close)
                if close.error_code == quinn::VarInt::from_u32(0) => {}
            error => {
                return Err(io::Error::other(format!(
                    "{}: HTTP/3 peer GOAWAY did not produce a clean connection close: {error:?}",
                    required_str(case, "id")?
                ))
                .into());
            }
        }

        tokio::time::timeout(Duration::from_secs(2), client_driver)
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 client driver did not finish after the clean close",
                )
            })???;
        drop(sender);
        endpoint.wait_idle().await;

        let (recovery_endpoint, mut recovery_sender) =
            new_http3_client(address, &tls_clients.http3).await?;
        let mut recovery = send_http3_request(
            &mut recovery_sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (recovery_status, recovery_body, _) = collect_http3_response(&mut recovery).await?;
        if recovery_status != required_status(case, "recovery_status")?
            || recovery_body != required_str(case, "recovery_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: a fresh HTTP/3 connection did not recover after peer GOAWAY",
                required_str(case, "id")?
            ))
            .into());
        }
        recovery_endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 peer GOAWAY recovery complete",
        );
        recovery_endpoint.wait_idle().await;
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 peer GOAWAY server did not stop",
        )
        .into()),
    }
}

async fn run_isolated_http3_server_shutdown_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_millis(server_wait_ms),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow = async {
        let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
        endpoint.set_default_client_config(tls_clients.http3.clone());
        let connection = tokio::time::timeout(
            Duration::from_secs(2),
            endpoint.connect(address, "localhost")?,
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 peer did not connect"))??;
        let (mut driver, mut sender) =
            h3::client::new(h3_quinn::Connection::new(connection.clone())).await?;
        let client_driver = tokio::spawn(async move {
            let _terminal = std::future::poll_fn(|context| driver.poll_close(context)).await;
        });

        let mut request = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut request).await?;
        if status != required_status(case, "expected_status")?
            || body != required_str(case, "expected_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 request did not complete before server shutdown",
                required_str(case, "id")?
            ))
            .into());
        }
        drop(request);

        shutdown_sender.send_replace(true);
        let peer_close =
            tokio::time::timeout(Duration::from_millis(server_wait_ms), connection.closed())
                .await
                .map_err(|_| {
                    io::Error::new(
                        io::ErrorKind::TimedOut,
                        "server did not close the HTTP/3 connection during graceful shutdown",
                    )
                })?;
        match peer_close {
            quinn::ConnectionError::ApplicationClosed(close)
                if close.error_code == quinn::VarInt::from_u32(0) => {}
            error => {
                return Err(io::Error::other(format!(
                    "{}: server shutdown did not close the HTTP/3 connection cleanly: {error:?}",
                    required_str(case, "id")?
                ))
                .into());
            }
        }

        tokio::time::timeout(Duration::from_millis(server_wait_ms), client_driver)
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 client driver did not finish after server shutdown",
                )
            })??;
        drop(sender);
        tokio::time::timeout(Duration::from_millis(server_wait_ms), endpoint.wait_idle())
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 client endpoint did not drain",
                )
            })?;
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_millis(server_wait_ms), server).await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 server did not stop after its active connection drained",
        )
        .into()),
    }
}

async fn run_isolated_http3_incomplete_request_recovery_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_secs(1),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow = async {
        let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
        endpoint.set_default_client_config(tls_clients.http3.clone());
        let connection = tokio::time::timeout(
            Duration::from_secs(2),
            endpoint.connect(address, "localhost")?,
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 peer did not connect"))??;
        let (mut driver, mut sender) =
            h3::client::new(h3_quinn::Connection::new(connection.clone())).await?;
        let client_driver = tokio::spawn(async move {
            std::future::poll_fn(|context| driver.poll_close(context)).await
        });

        let (mut incomplete_send, mut incomplete_response) = connection.open_bi().await?;
        incomplete_send.finish()?;
        let mut probe = [0_u8; 1];
        let reset = tokio::time::timeout(
            Duration::from_secs(2),
            incomplete_response.read(&mut probe),
        )
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "server did not reject the incomplete HTTP/3 request stream",
            )
        })?;
        match reset {
            Err(quinn::ReadError::Reset(code))
                if code.into_inner() == Code::H3_REQUEST_INCOMPLETE.value() => {}
            result => {
                return Err(io::Error::other(format!(
                    "{}: incomplete HTTP/3 request reset did not use H3_REQUEST_INCOMPLETE: {result:?}",
                    required_str(case, "id")?
                ))
                .into());
            }
        }

        let mut recovery = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut recovery).await?;
        if status != required_status(case, "recovery_status")?
            || body != required_str(case, "recovery_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: valid HTTP/3 request did not recover on the connection after an incomplete request",
                required_str(case, "id")?
            ))
            .into());
        }

        endpoint.close(
            quinn::VarInt::from_u32(0),
            b"HTTP/3 incomplete-request recovery complete",
        );
        endpoint.wait_idle().await;
        tokio::time::timeout(Duration::from_secs(2), client_driver)
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 client driver did not finish during cleanup",
                )
            })??;
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 incomplete-request recovery server did not stop",
        )
        .into()),
    }
}

async fn run_isolated_http3_response_send_cancel_case(case: &Value) -> ProbeResult<()> {
    run_http3_response_send_cancel_contract_app(case).await?;
    run_http3_response_send_cancel_lifecycle_app(case).await
}

async fn run_http3_response_send_cancel_contract_app(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, _) = contract_app_with_state(shutdown_sender.clone());
    let observed_phases = Arc::new(Mutex::new(Vec::<ServerErrorPhase>::new()));
    let phase_log = Arc::clone(&observed_phases);
    let error_observer: ServerErrorObserver = Arc::new(move |event: ServerErrorEvent<'_>| {
        if let Ok(mut phases) = phase_log.lock() {
            phases.push(event.phase());
        }
    });
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: Duration::from_secs(1),
            error_observer: Some(error_observer),
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let workflow = run_http3_response_send_cancel_client(
        case,
        address,
        &tls_clients.http3,
        &observed_phases,
        required_str(case, "recovery_body")?.as_bytes(),
    )
    .await;

    shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => Err(error.into()),
        Ok(Err(error)) => Err(error.into()),
        Err(_) => Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 response cancellation server did not stop",
        )
        .into()),
    }
}

async fn run_http3_response_send_cancel_lifecycle_app(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let address = server_endpoint.local_addr()?;
    let fixture = lifecycle_fixture();
    let observed_phases = Arc::new(Mutex::new(Vec::<ServerErrorPhase>::new()));
    let phase_log = Arc::clone(&observed_phases);
    let mut config = lifecycle_server_config(Arc::clone(&fixture.hooks), case)?;
    config.error_observer = Some(Arc::new(move |event: ServerErrorEvent<'_>| {
        if let Ok(mut phases) = phase_log.lock() {
            phases.push(event.phase());
        }
    }));
    let server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        fixture.app.clone(),
        shutdown_on_change(fixture.shutdown_receiver.clone()),
        config,
    ));

    let workflow = run_http3_response_send_cancel_client(
        case,
        address,
        &tls_clients.http3,
        &observed_phases,
        b"started\n",
    )
    .await;

    fixture.shutdown_sender.send_replace(true);
    let server_result = tokio::time::timeout(Duration::from_secs(4), server).await;
    workflow?;
    match server_result {
        Ok(Ok(Ok(()))) => {}
        Ok(Ok(Err(error))) => return Err(error.into()),
        Ok(Err(error)) => return Err(error.into()),
        Err(_) => {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 response cancellation lifecycle server did not stop",
            )
            .into());
        }
    }

    if !fixture.state.startup_completed.load(Ordering::Acquire)
        || !fixture.state.shutdown_completed.load(Ordering::Acquire)
    {
        return Err(io::Error::other(
            "HTTP/3 response cancellation did not complete application lifespan",
        )
        .into());
    }
    let events = fixture
        .state
        .events
        .lock()
        .map_err(|_| io::Error::other("lifecycle event log was poisoned"))?;
    if events.as_slice() != ["startup", "shutdown"] {
        return Err(io::Error::other(format!(
            "HTTP/3 response cancellation produced unexpected lifecycle events: {events:?}"
        ))
        .into());
    }
    Ok(())
}

async fn run_http3_response_send_cancel_client(
    case: &Value,
    address: SocketAddr,
    client_config: &quinn::ClientConfig,
    observed_phases: &Mutex<Vec<ServerErrorPhase>>,
    expected_recovery_body: &[u8],
) -> ProbeResult<()> {
    let mut endpoint = quinn::Endpoint::client("127.0.0.1:0".parse::<SocketAddr>()?)?;
    endpoint.set_default_client_config(client_config.clone());
    let mut client_driver = None;
    let workflow: ProbeResult<()> = async {
        let connection = tokio::time::timeout(
            Duration::from_secs(2),
            endpoint.connect(address, "localhost")?,
        )
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 peer did not connect"))??;
        let (mut driver, mut sender) =
            h3::client::new(h3_quinn::Connection::new(connection.clone())).await?;
        client_driver = Some(tokio::spawn(async move {
            let _ = std::future::poll_fn(|context| driver.poll_close(context)).await;
        }));

        match required_str(case, "cancel_phase")? {
            "before-headers" => {
                let mut active = send_http3_request(
                    &mut sender,
                    address,
                    "GET",
                    required_str(case, "request_path")?,
                    b"",
                )
                .await?;
                wait_http3_response_cancel_state(&mut sender, address, case).await?;
                active.stop_sending(Code::H3_REQUEST_CANCELLED);
            }
            "before-trailers" => {
                let (mut request_send, mut response_receive) = connection.open_bi().await?;
                let request = encode_raw_http3_get_request(
                    &format!("localhost:{}", address.port()),
                    required_str(case, "request_path")?,
                )?;
                request_send.write_all(&request).await?;
                request_send.finish()?;

                let mut response_buffer = Vec::new();
                let (headers_type, response_headers) = tokio::time::timeout(
                    Duration::from_secs(2),
                    read_raw_http3_frame(&mut response_receive, &mut response_buffer),
                )
                .await??;
                let (data_type, first_chunk) = tokio::time::timeout(
                    Duration::from_secs(2),
                    read_raw_http3_frame(&mut response_receive, &mut response_buffer),
                )
                .await??;
                if headers_type != 0x01
                    || raw_http3_static_status(&response_headers)
                        != Some(required_status(case, "expected_status")?)
                    || data_type != 0x00
                    || first_chunk != required_str(case, "expected_first_chunk")?.as_bytes()
                {
                    return Err(io::Error::other(format!(
                        "{}: response did not reach the pre-trailers checkpoint",
                        required_str(case, "id")?
                    ))
                    .into());
                }
                wait_http3_response_cancel_state(&mut sender, address, case).await?;
                let error_code = quinn::VarInt::from_u64(Code::H3_REQUEST_CANCELLED.value())?;
                response_receive.stop(error_code)?;
                drop(request_send);
            }
            "before-finish" => {
                let (mut request_send, mut response_receive) = connection.open_bi().await?;
                let request = encode_raw_http3_get_request(
                    &format!("localhost:{}", address.port()),
                    required_str(case, "request_path")?,
                )?;
                request_send.write_all(&request).await?;
                request_send.finish()?;

                let mut response_buffer = Vec::new();
                let (headers_type, response_headers) = tokio::time::timeout(
                    Duration::from_secs(2),
                    read_raw_http3_frame(&mut response_receive, &mut response_buffer),
                )
                .await??;
                if headers_type != 0x01
                    || raw_http3_static_status(&response_headers)
                        != Some(required_status(case, "expected_status")?)
                {
                    return Err(io::Error::other(format!(
                        "{}: response did not reach the pre-finish checkpoint",
                        required_str(case, "id")?
                    ))
                    .into());
                }
                wait_http3_response_cancel_state(&mut sender, address, case).await?;
                let error_code = quinn::VarInt::from_u64(Code::H3_REQUEST_CANCELLED.value())?;
                response_receive.stop(error_code)?;
                drop(request_send);
            }
            phase => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("unknown HTTP/3 response cancellation phase {phase:?}"),
                )
                .into());
            }
        }

        let mut release = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "release_path")?,
            b"",
        )
        .await?;
        let (release_status, release_body, _) = collect_http3_response(&mut release).await?;
        if release_status != required_status(case, "release_status")?
            || release_body != required_str(case, "release_body")?.as_bytes()
        {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 cancellation release request did not complete",
                required_str(case, "id")?
            ))
            .into());
        }

        let mut pending = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "pending_path")?,
            b"",
        )
        .await?;
        let (pending_status, pending_body, _) = collect_http3_response(&mut pending).await?;
        if pending_status != StatusCode::OK.as_u16() || pending_body != b"ready\n" {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 response cancellation release did not clear the pending state",
                required_str(case, "id")?
            ))
            .into());
        }

        wait_http3_connection_error(observed_phases, case).await?;

        let mut recovery = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "recovery_path")?,
            b"",
        )
        .await?;
        let (status, body, _) = collect_http3_response(&mut recovery).await?;
        if status != required_status(case, "recovery_status")? || body != expected_recovery_body {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 connection did not recover after response cancellation",
                required_str(case, "id")?
            ))
            .into());
        }

        Ok(())
    }
    .await;

    endpoint.close(
        quinn::VarInt::from_u32(0),
        b"HTTP/3 response cancellation case complete",
    );
    let idle_result = tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle())
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 response cancellation endpoint did not become idle",
            )
        });
    let driver_result = if let Some(client_driver) = client_driver {
        tokio::time::timeout(Duration::from_secs(2), client_driver)
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 response cancellation client driver did not stop",
                )
            })?
            .map_err(io::Error::other)
    } else {
        Ok(())
    };

    workflow?;
    idle_result?;
    driver_result?;
    Ok(())
}

fn raw_http3_static_status(field_section: &[u8]) -> Option<u16> {
    if field_section.len() < 3 || field_section[0] != 0 || field_section[1] != 0 {
        return None;
    }
    let first_field = *field_section.get(2)?;
    if first_field & 0xc0 != 0xc0 {
        return None;
    }
    match first_field & 0x3f {
        25 => Some(200),
        27 => Some(404),
        28 => Some(503),
        64 => Some(204),
        65 => Some(206),
        66 => Some(302),
        67 => Some(400),
        68 => Some(403),
        69 => Some(421),
        70 => Some(425),
        71 => Some(500),
        _ => None,
    }
}

fn encode_raw_http3_get_request(authority: &str, path: &str) -> ProbeResult<Vec<u8>> {
    let mut field_section = vec![0x00, 0x00, 0xd1, 0xd7, 0x50];
    append_qpack_literal(authority.as_bytes(), &mut field_section)?;
    field_section.push(0x51);
    append_qpack_literal(path.as_bytes(), &mut field_section)?;
    if field_section.len() > 63 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "raw HTTP/3 request field section exceeds the one-byte frame length",
        )
        .into());
    }

    let mut request = Vec::with_capacity(field_section.len() + 2);
    request.extend_from_slice(&[0x01, field_section.len() as u8]);
    request.extend_from_slice(&field_section);
    Ok(request)
}

fn append_qpack_literal(value: &[u8], output: &mut Vec<u8>) -> ProbeResult<()> {
    let length = u8::try_from(value.len())?;
    if length >= 0x80 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "raw HTTP/3 QPACK literal exceeds the supported length",
        )
        .into());
    }
    output.push(length);
    output.extend_from_slice(value);
    Ok(())
}

async fn read_raw_http3_frame(
    stream: &mut quinn::RecvStream,
    buffered: &mut Vec<u8>,
) -> ProbeResult<(u64, Vec<u8>)> {
    loop {
        if let Some((frame_type, type_length)) = decode_quic_varint(buffered) {
            if let Some((frame_length, length_length)) =
                decode_quic_varint(&buffered[type_length..])
            {
                let payload_length = usize::try_from(frame_length)?;
                if payload_length > 1024 * 1024 {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "raw HTTP/3 response frame exceeded the probe limit",
                    )
                    .into());
                }
                let header_length = type_length + length_length;
                let total_length = header_length + payload_length;
                if buffered.len() >= total_length {
                    let payload = buffered[header_length..total_length].to_vec();
                    buffered.drain(..total_length);
                    return Ok((frame_type, payload));
                }
            }
        }

        let chunk =
            tokio::time::timeout(Duration::from_secs(2), stream.read_chunk(usize::MAX, true))
                .await
                .map_err(|_| {
                    io::Error::new(io::ErrorKind::TimedOut, "HTTP/3 response frame timed out")
                })??
                .ok_or_else(|| {
                    io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "HTTP/3 response ended before the expected frame",
                    )
                })?;
        buffered.extend_from_slice(&chunk.bytes);
    }
}

fn decode_quic_varint(buffered: &[u8]) -> Option<(u64, usize)> {
    let first = *buffered.first()?;
    let encoded_length = 1_usize << usize::from(first >> 6);
    if buffered.len() < encoded_length {
        return None;
    }

    let mut value = u64::from(first & 0x3f);
    for byte in &buffered[1..encoded_length] {
        value = (value << 8) | u64::from(*byte);
    }
    Some((value, encoded_length))
}

async fn wait_http3_response_cancel_state(
    sender: &mut Http3Sender,
    address: SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            let mut state = send_http3_request(
                sender,
                address,
                "GET",
                required_str(case, "pending_path")?,
                b"",
            )
            .await?;
            let (status, body, _) = collect_http3_response(&mut state).await?;
            if status != StatusCode::OK.as_u16() {
                return Err(io::Error::other(format!(
                    "{}: HTTP/3 cancellation state request returned {status}",
                    required_str(case, "id")?
                ))
                .into());
            }
            if body == required_str(case, "pending_state")?.as_bytes() {
                return Ok::<(), Box<dyn Error + Send + Sync>>(());
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            format!(
                "{}: application did not reach its HTTP/3 response cancellation checkpoint",
                case["id"].as_str().unwrap_or("unknown case")
            ),
        )
    })??;
    Ok(())
}

async fn wait_http3_connection_error(
    observed_phases: &Mutex<Vec<ServerErrorPhase>>,
    case: &Value,
) -> ProbeResult<()> {
    tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if observed_phases
                .lock()
                .map_err(|_| io::Error::other("HTTP/3 error observer lock was poisoned"))?
                .contains(&ServerErrorPhase::Connection)
            {
                return Ok::<(), Box<dyn Error + Send + Sync>>(());
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::TimedOut,
            format!(
                "{}: cancellation did not reach an HTTP/3 response-send error",
                case["id"].as_str().unwrap_or("unknown case")
            ),
        )
    })??;
    Ok(())
}

async fn run_isolated_http3_idle_connection_shutdown_timeout_case(case: &Value) -> ProbeResult<()> {
    let (_, tls_clients, quic_server_config) = test_tls_configs()?;
    let server_endpoint =
        quinn::Endpoint::server(quic_server_config, "127.0.0.1:0".parse::<SocketAddr>()?)?;
    let server_endpoint_monitor = server_endpoint.clone();
    let address = server_endpoint.local_addr()?;
    let graceful_timeout_ms = case["graceful_timeout_ms"].as_u64().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidData, "graceful_timeout_ms is missing")
    })?;
    let server_wait_ms = case["server_wait_ms"]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "server_wait_ms is missing"))?;
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let (application, state) = contract_app_with_state(shutdown_sender.clone());
    let mut server = tokio::spawn(uvicorn_rs::serve_http3(
        server_endpoint,
        application,
        shutdown_on_change(shutdown_receiver),
        uvicorn_rs::ServerConfig {
            max_connections: 8,
            graceful_shutdown_timeout: Duration::from_millis(graceful_timeout_ms),
            error_observer: None,
            ..uvicorn_rs::ServerConfig::default()
        },
    ));

    let mut server_joined = false;
    let mut client_endpoint = None;
    let mut client_sender = None;
    let mut active_stream = None;
    let workflow = async {
        let (endpoint, mut sender) = new_http3_client(address, &tls_clients.http3).await?;
        client_endpoint = Some(endpoint.clone());
        let active = send_http3_request(
            &mut sender,
            address,
            "GET",
            required_str(case, "path")?,
            b"",
        )
        .await?;
        client_sender = Some(sender);
        active_stream = Some(active);

        tokio::time::timeout(Duration::from_secs(2), async {
            while state.request_lifetime_waiters.load(Ordering::Acquire) == 0 {
                sleep(Duration::from_millis(1)).await;
            }
        })
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "held HTTP/3 request did not reach the service",
            )
        })?;

        endpoint.close(
            quinn::VarInt::from_u32(0),
            b"client closes held HTTP/3 request",
        );
        tokio::time::timeout(Duration::from_secs(2), async {
            while state.request_connections_closed.load(Ordering::Acquire) == 0 {
                sleep(Duration::from_millis(1)).await;
            }
        })
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "HTTP/3 connection lifetime did not end after the client close",
            )
        })?;

        if server_endpoint_monitor.open_connections() == 0 {
            return Err(io::Error::other(
                "server endpoint became idle before the shutdown deadline began",
            )
            .into());
        }

        shutdown_sender.send_replace(true);

        let joined = tokio::time::timeout(Duration::from_millis(server_wait_ms), &mut server)
            .await
            .map_err(|_| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "HTTP/3 idle-connection shutdown did not finish within the outer bound",
                )
            })?;
        server_joined = true;
        let server_result = joined?;
        let server_error = server_result.err().ok_or_else(|| {
            io::Error::other("HTTP/3 endpoint shutdown completed despite the open connection")
        })?;
        let expected_server_error = required_str(case, "expected_server_error")?;
        if !matches!(
            server_error,
            uvicorn_rs::ServeError::GracefulShutdownTimedOut
        ) || server_error.to_string() != expected_server_error
            || server_error.source().is_some()
        {
            return Err(io::Error::other(format!(
                "{}: HTTP/3 idle-connection shutdown error differed: {server_error}",
                required_str(case, "id")?
            ))
            .into());
        }
        Ok::<(), Box<dyn Error + Send + Sync>>(())
    }
    .await;

    shutdown_sender.send_replace(true);
    if let Some(endpoint) = client_endpoint.as_ref() {
        endpoint.close(quinn::VarInt::from_u32(0), b"idle-connection case complete");
    }
    drop(active_stream);
    drop(client_sender);
    let client_idle = if let Some(endpoint) = client_endpoint {
        tokio::time::timeout(Duration::from_secs(2), endpoint.wait_idle())
            .await
            .is_ok()
    } else {
        true
    };
    if !server_joined
        && tokio::time::timeout(Duration::from_secs(1), &mut server)
            .await
            .is_err()
    {
        server.abort();
        let _ = server.await;
    }
    if workflow.is_ok() && !client_idle {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "HTTP/3 client endpoint did not become idle during test cleanup",
        )
        .into());
    }
    workflow
}

async fn run_http2_graceful_drain_case(
    address: std::net::SocketAddr,
    case: &Value,
) -> ProbeResult<()> {
    let socket = TcpStream::connect(address).await?;
    let (mut sender, connection) =
        hyper::client::conn::http2::handshake(TokioExecutor::new(), TokioIo::new(socket)).await?;
    let driver = tokio::spawn(connection);
    let active_request = Request::builder()
        .method(required_str(case, "method")?)
        .uri(format!("http://localhost{}", required_str(case, "path")?))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let active_response = sender.send_request(active_request).await?;
    if active_response.status() != StatusCode::OK {
        return Err(io::Error::other(format!(
            "{}: active HTTP/2 response returned {}",
            required_str(case, "id")?,
            active_response.status()
        ))
        .into());
    }
    let mut active_body = active_response.into_body();
    let first = tokio::time::timeout(Duration::from_secs(2), active_body.frame())
        .await?
        .ok_or_else(|| io::Error::new(io::ErrorKind::UnexpectedEof, "H2 stream ended early"))??
        .into_data()
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "expected an H2 DATA frame"))?;
    if first.as_ref() != required_str(case, "first_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: active HTTP/2 response had an unexpected first frame",
            required_str(case, "id")?
        ))
        .into());
    }

    let shutdown_request = Request::builder()
        .method("GET")
        .uri(format!(
            "http://localhost{}",
            required_str(case, "shutdown_path")?
        ))
        .header("host", "localhost")
        .body(Full::new(Bytes::new()))?;
    let shutdown_response = sender.send_request(shutdown_request).await?;
    let shutdown_status = shutdown_response.status();
    let shutdown_body = shutdown_response.into_body().collect().await?.to_bytes();
    if shutdown_status != StatusCode::OK
        || shutdown_body.as_ref() != required_str(case, "shutdown_body")?.as_bytes()
    {
        return Err(io::Error::other(format!(
            "{}: HTTP/2 shutdown trigger response did not finish",
            required_str(case, "id")?
        ))
        .into());
    }

    let second = tokio::time::timeout(Duration::from_secs(2), active_body.frame())
        .await?
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "active H2 response was not drained",
            )
        })??
        .into_data()
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "expected a second H2 DATA frame",
            )
        })?;
    loop {
        let Some(frame) = tokio::time::timeout(Duration::from_secs(2), active_body.frame()).await?
        else {
            break;
        };
        let frame = frame?;
        match frame.into_data() {
            Ok(data) if data.is_empty() => {}
            Ok(_) => {
                return Err(io::Error::other(format!(
                    "{}: graceful HTTP/2 shutdown produced unexpected trailing data",
                    required_str(case, "id")?
                ))
                .into());
            }
            Err(_) => {
                return Err(io::Error::other(format!(
                    "{}: graceful HTTP/2 shutdown produced unexpected trailers",
                    required_str(case, "id")?
                ))
                .into());
            }
        }
    }
    if second.as_ref() != required_str(case, "second_chunk")?.as_bytes() {
        return Err(io::Error::other(format!(
            "{}: graceful HTTP/2 shutdown did not drain the active response",
            required_str(case, "id")?
        ))
        .into());
    }

    drop(sender);
    tokio::time::timeout(Duration::from_secs(2), driver).await???;
    Ok(())
}

fn input_string_values<'a>(
    case: &'a Value,
    array_key: &str,
    default: &'a str,
) -> ProbeResult<Vec<&'a str>> {
    let Some(value) = case.get(array_key) else {
        return Ok(vec![default]);
    };
    let values = value.as_array().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("case field {array_key} must be an array"),
        )
    })?;
    let mut strings = Vec::with_capacity(values.len());
    for value in values {
        strings.push(value.as_str().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("case field {array_key} must contain only strings"),
            )
        })?);
    }
    Ok(strings)
}

fn required_str<'a>(value: &'a Value, key: &str) -> ProbeResult<&'a str> {
    value[key]
        .as_str()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("case has no {key}")))
        .map_err(Into::into)
}

fn required_status(value: &Value, key: &str) -> ProbeResult<u16> {
    let status = value[key]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("case has no {key}")))?;
    u16::try_from(status).map_err(|error| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("invalid {key}: {error}"),
        )
        .into()
    })
}

fn required_u64(value: &Value, key: &str) -> ProbeResult<u64> {
    value[key]
        .as_u64()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, format!("case has no {key}")))
        .map_err(Into::into)
}

async fn request(
    address: std::net::SocketAddr,
    method: &str,
    path: &str,
    body: &[u8],
) -> ProbeResult<TcpStream> {
    request_with_shutdown(address, method, path, body, false).await
}

async fn request_with_shutdown(
    address: std::net::SocketAddr,
    method: &str,
    path: &str,
    body: &[u8],
    shutdown_write: bool,
) -> ProbeResult<TcpStream> {
    let mut stream = TcpStream::connect(address).await?;
    let mut request =
        format!("{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n");
    // RFC 9110 §8.6: omit Content-Length for bodyless GETs; POST declares the
    // exact length of its content.
    if method == "POST" || !body.is_empty() {
        request.push_str(&format!("Content-Length: {}\r\n", body.len()));
    }
    request.push_str("\r\n");
    stream.write_all(request.as_bytes()).await?;
    stream.write_all(body).await?;
    stream.flush().await?;
    if shutdown_write {
        stream.shutdown().await?;
    }
    Ok(stream)
}

async fn read_response_head<R>(
    stream: &mut R,
) -> ProbeResult<(u16, std::collections::HashMap<String, String>)>
where
    R: AsyncRead + Unpin + ?Sized,
{
    let status_line = read_crlf_line(stream).await?;
    let status = std::str::from_utf8(&status_line)?
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "malformed HTTP status line"))?
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
        if headers.len() > 128 {
            return Err(
                io::Error::new(io::ErrorKind::InvalidData, "too many response headers").into(),
            );
        }
    }
    Ok((status, headers))
}

async fn read_response_body<R>(
    stream: &mut R,
    headers: &std::collections::HashMap<String, String>,
) -> ProbeResult<(Vec<u8>, bool)>
where
    R: AsyncRead + Unpin + ?Sized,
{
    if headers
        .get("transfer-encoding")
        .is_some_and(|value| value.eq_ignore_ascii_case("chunked"))
    {
        let mut body = Vec::new();
        loop {
            match read_next_chunk(stream).await {
                Ok(Some(chunk)) => body.extend_from_slice(&chunk),
                Ok(None) => return Ok((body, true)),
                Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => {
                    return Ok((body, false));
                }
                Err(error) => return Err(error.into()),
            }
        }
    }
    if let Some(length) = headers.get("content-length") {
        let length = length.parse::<usize>()?;
        let mut body = vec![0; length];
        stream.read_exact(&mut body).await?;
        return Ok((body, true));
    }
    let mut body = Vec::new();
    stream.read_to_end(&mut body).await?;
    Ok((body, true))
}

async fn read_next_chunk<R>(stream: &mut R) -> io::Result<Option<Vec<u8>>>
where
    R: AsyncRead + Unpin + ?Sized,
{
    let line = read_crlf_line(stream).await?;
    let line = std::str::from_utf8(&line)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
    let size = line
        .split(';')
        .next()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "HTTP chunk has no size"))?
        .trim();
    let size = usize::from_str_radix(size, 16)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error.to_string()))?;
    if size == 0 {
        loop {
            if read_crlf_line(stream).await?.is_empty() {
                break;
            }
        }
        return Ok(None);
    }
    let mut chunk = vec![0; size];
    stream.read_exact(&mut chunk).await?;
    let mut delimiter = [0_u8; 2];
    stream.read_exact(&mut delimiter).await?;
    if delimiter != *b"\r\n" {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "malformed chunk delimiter",
        ));
    }
    Ok(Some(chunk))
}

async fn read_crlf_line<R>(stream: &mut R) -> io::Result<Vec<u8>>
where
    R: AsyncRead + Unpin + ?Sized,
{
    let mut line = Vec::new();
    loop {
        let byte = stream.read_u8().await?;
        if byte == b'\n' {
            if line.pop() != Some(b'\r') {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "expected CRLF"));
            }
            return Ok(line);
        }
        line.push(byte);
        if line.len() > 64 * 1024 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "HTTP line exceeds 64 KiB",
            ));
        }
    }
}
