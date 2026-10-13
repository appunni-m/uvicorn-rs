#![forbid(unsafe_code)]
#![warn(missing_docs)]

//! Python-free HTTP/1.1, HTTP/2, and HTTP/3 server core.
//!
//! This crate accepts an application implementing [`tower_service::Service`]
//! over [`http::Request`] and [`http::Response`]. Request bodies remain generic
//! `http_body::Body` values, so applications do not need to depend on Hyper's
//! transport body type. Response frames are polled by Hyper as network flow
//! control permits; the core does not collect response bodies.
//!
//! The current prototype supports cleartext TCP and TLS HTTP/1.1 and HTTP/2,
//! plus HTTP/3 over a caller-configured QUIC endpoint. An optional
//! [`ApplicationLifecycle`] hook brackets server startup and shutdown; it is a
//! native framework hook, not an implementation of the ASGI lifespan message
//! protocol. HTTP/1.1 applications can register upgraded-session futures so
//! the server keeps them in its connection drain and cancellation policy. The
//! crate also exposes an initial RFC 6455 [`WebSocketUpgrade`] and
//! [`WebSocketSession`] API for native HTTP/1.1 services. This
//! transport-specific API is not yet a shared framework contract; WebSockets
//! over HTTP/2 or HTTP/3 and integration with the Python ASGI adapter are not
//! implemented.
//!
//! Each request receives [`ConnectionInfo`], [`ConnectionLifetime`], and
//! [`RequestLifetime`] values in its [`http::Extensions`]. The connection
//! handle ends when its protocol driver ends. The request handle identifies
//! when the service or response-body path ends, including when Hyper drops an
//! HTTP/2 service future after a stream reset. A dropped service future does
//! not identify its cause; adapters must not interpret it as a peer reset
//! unless the protocol layer provides that evidence. HTTP/3 request-reset
//! notification remains limited by the current `h3` driver and is not
//! guaranteed while neither request body nor response is being polled.

use std::{
    convert::Infallible,
    error::Error,
    fmt,
    future::Future,
    io,
    net::SocketAddr,
    panic::{catch_unwind, AssertUnwindSafe},
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
    time::Duration,
};

use bytes::Bytes;
use futures_util::{
    future::{ready, Either as FutureEither, Ready},
    FutureExt,
};
use http::{Request, Response, StatusCode};
use http_body::Body;
use http_body_util::Empty;
use hyper::body::Incoming;
use hyper::upgrade::{OnUpgrade, Upgraded};
use hyper_util::{
    rt::{TokioExecutor, TokioIo},
    server::conn::auto,
    service::TowerToHyperService,
};
pub use native_app_contract::{
    ApplicationLifecycle, ApplicationLifecycleError, ApplicationLifecycleFuture,
    ApplicationLifecycleStage,
};
use pin_project_lite::pin_project;
use tokio::{
    io::{AsyncRead, AsyncWrite},
    net::TcpListener,
    sync::{mpsc, watch, OwnedSemaphorePermit, Semaphore},
    task::{JoinError, JoinSet},
    time::Instant,
};
use tokio_rustls::TlsAcceptor;
use tower_service::Service;

type BoxBodyError = Box<dyn Error + Send + Sync + 'static>;

mod http3;
mod websocket;

pub use http3::{serve_http3, Http3RequestBody};
pub use websocket::{
    WebSocketCloseCode, WebSocketCloseFrame, WebSocketError, WebSocketMessage, WebSocketSession,
    WebSocketUpgrade, WebSocketUpgradeError,
};

/// An observer for errors handled by the Rust server boundary.
///
/// The callback receives a borrowed error while its original concrete type
/// and source chain are still available. It runs synchronously on the task
/// observing the error; leave it unset when no error telemetry is needed.
pub type ServerErrorObserver = Arc<dyn for<'a> Fn(ServerErrorEvent<'a>) + Send + Sync + 'static>;

/// The stage at which the server observed an application or transport error.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ServerErrorPhase {
    /// The application startup hook failed or exceeded its deadline.
    ApplicationStartup,
    /// The application shutdown hook failed or exceeded its deadline.
    ApplicationShutdown,
    /// The application service was not ready to accept a request.
    Readiness,
    /// The application service failed before response commitment.
    Service,
    /// A response body failed after response commitment.
    ResponseBody,
    /// The HTTP connection failed or exceeded its drain deadline.
    Connection,
}

/// A borrowed error notification emitted by the server error observer.
#[derive(Clone, Copy, Debug)]
pub struct ServerErrorEvent<'a> {
    phase: ServerErrorPhase,
    peer_addr: Option<SocketAddr>,
    error: &'a (dyn Error + Send + Sync + 'static),
}

impl ServerErrorEvent<'_> {
    /// Returns the stage at which the server observed the error.
    #[must_use]
    pub const fn phase(&self) -> ServerErrorPhase {
        self.phase
    }

    /// Returns the TCP peer address when the error belongs to a connection.
    #[must_use]
    pub const fn peer_addr(&self) -> Option<SocketAddr> {
        self.peer_addr
    }

    /// Returns the original typed error and its source chain.
    #[must_use]
    pub fn error(&self) -> &(dyn Error + Send + Sync + 'static) {
        self.error
    }
}

/// Server-level limits and optional lifecycle hooks for the HTTP service prototype.
#[derive(Clone)]
pub struct ServerConfig {
    /// Maximum number of accepted connections that may be active at once.
    pub max_connections: usize,
    /// Maximum time to drain active connections after shutdown begins.
    pub graceful_shutdown_timeout: Duration,
    /// Maximum time allowed for the application startup hook when lifecycle
    /// hooks are configured. The default is 30 seconds; expiration drops the
    /// hook future. Ignored when `application_lifecycle` is `None`.
    pub application_startup_timeout: Duration,
    /// Maximum time allowed for the application shutdown hook after serving
    /// has drained or cancelled active work. The default is 30 seconds;
    /// expiration drops the hook future. Ignored when `application_lifecycle`
    /// is `None`, and measured separately from the connection-drain timeout.
    pub application_shutdown_timeout: Duration,
    /// Optional framework lifecycle hooks, run before request acceptance and
    /// after the server's request loop drains or cancels active work.
    pub application_lifecycle: Option<Arc<dyn ApplicationLifecycle>>,
    /// Receives typed application and transport errors when configured.
    ///
    /// The observer runs synchronously on an error path. Its panic is caught
    /// and logged so it cannot unwind a connection task.
    pub error_observer: Option<ServerErrorObserver>,
}

impl fmt::Debug for ServerConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ServerConfig")
            .field("max_connections", &self.max_connections)
            .field("graceful_shutdown_timeout", &self.graceful_shutdown_timeout)
            .field(
                "application_startup_timeout",
                &self.application_startup_timeout,
            )
            .field(
                "application_shutdown_timeout",
                &self.application_shutdown_timeout,
            )
            .field(
                "application_lifecycle_configured",
                &self.application_lifecycle.is_some(),
            )
            .field("error_observer_configured", &self.error_observer.is_some())
            .finish()
    }
}

/// The transport used by a connection.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransportKind {
    /// A TCP connection carrying HTTP/1.1 or HTTP/2.
    Tcp,
    /// A QUIC connection carrying HTTP/3.
    Quic,
}

/// Connection metadata inserted into each request's extensions.
///
/// The HTTP version remains available through [`Request::version`]. The server
/// provides the peer address, transport kind, and negotiated ALPN
/// for TLS connections. QUIC connections always include TLS metadata.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConnectionInfo {
    peer_addr: SocketAddr,
    tls: Option<TlsInfo>,
    transport: TransportKind,
}

impl ConnectionInfo {
    /// Returns the remote socket address accepted by the server.
    #[must_use]
    pub const fn peer_addr(&self) -> SocketAddr {
        self.peer_addr
    }

    /// Returns negotiated TLS metadata, or `None` for cleartext TCP.
    #[must_use]
    pub const fn tls(&self) -> Option<&TlsInfo> {
        self.tls.as_ref()
    }

    /// Returns whether this connection uses TCP or QUIC.
    #[must_use]
    pub const fn transport(&self) -> TransportKind {
        self.transport
    }
}

/// A connection-scoped signal inserted into each request's extensions.
///
/// This handle describes the lifetime of the underlying HTTP connection. It
/// is independent of [`RequestLifetime`], which tracks one request or stream.
#[derive(Clone, Debug)]
pub struct ConnectionLifetime {
    closed: watch::Receiver<bool>,
}

impl ConnectionLifetime {
    /// Returns whether the connection driver has ended.
    #[must_use]
    pub fn is_closed(&self) -> bool {
        *self.closed.borrow()
    }

    /// Waits until the connection driver ends.
    pub async fn wait_until_closed(&mut self) {
        while !*self.closed.borrow_and_update() {
            if self.closed.changed().await.is_err() {
                return;
            }
        }
    }
}

/// Registers an HTTP/1.1 protocol-upgrade session with its connection.
///
/// The native server owns registered sessions until they finish. On graceful
/// shutdown, [`wait_for_shutdown`](Self::wait_for_shutdown) resolves so the
/// application can close its upgraded protocol cleanly. If a session does not
/// finish before the server's connection-drain deadline, the server cancels
/// it with the connection task.
///
/// This handle is inserted into HTTP/1.1 request extensions. It is not
/// inserted for HTTP/2 or HTTP/3 requests. Applications must still perform
/// their protocol handshake and framing; the handle only provides lifecycle
/// ownership for the upgraded stream.
#[derive(Clone)]
pub struct ConnectionUpgrade {
    sessions: mpsc::UnboundedSender<UpgradeSessionFuture>,
    shutdown: watch::Receiver<bool>,
}

impl ConnectionUpgrade {
    /// Registers a future that owns the stream returned by an HTTP upgrade.
    ///
    /// Call this before returning the response that completes the upgrade.
    /// The session future starts when the response upgrade is accepted. Its
    /// error is reported through the configured server error observer.
    ///
    /// Returns [`ConnectionUpgradeClosed`] if the HTTP connection has already
    /// ended and cannot own another upgraded session.
    ///
    /// # Errors
    ///
    /// Returns [`ConnectionUpgradeClosed`] when the server has stopped
    /// accepting upgrade sessions for this connection.
    pub fn register<F, Fut, E>(
        &self,
        on_upgrade: OnUpgrade,
        handler: F,
    ) -> Result<(), ConnectionUpgradeClosed>
    where
        F: FnOnce(TokioIo<Upgraded>) -> Fut + Send + 'static,
        Fut: Future<Output = Result<(), E>> + Send + 'static,
        E: Error + Send + Sync + 'static,
    {
        let session = Box::pin(async move {
            let upgraded = on_upgrade
                .await
                .map_err(|error| Box::new(error) as BoxBodyError)?;
            handler(TokioIo::new(upgraded))
                .await
                .map_err(|error| Box::new(error) as BoxBodyError)
        });
        self.sessions
            .send(session)
            .map_err(|_| ConnectionUpgradeClosed)
    }

    /// Waits for the server to begin graceful shutdown for this connection.
    ///
    /// The method also resolves if the server drops its internal signal while
    /// tearing down the connection.
    pub async fn wait_for_shutdown(&self) {
        let mut shutdown = self.shutdown.clone();
        while !*shutdown.borrow_and_update() {
            if shutdown.changed().await.is_err() {
                return;
            }
        }
    }
}

/// The HTTP connection ended before another upgrade session could be
/// registered.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ConnectionUpgradeClosed;

impl fmt::Display for ConnectionUpgradeClosed {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("HTTP connection ended before upgrade registration")
    }
}

impl Error for ConnectionUpgradeClosed {}

type UpgradeSessionFuture =
    Pin<Box<dyn Future<Output = Result<(), BoxBodyError>> + Send + 'static>>;

/// The terminal state observed for a request's service and response body.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RequestEndReason {
    /// The protocol driver dropped the request service future before it
    /// returned a response. This does not identify whether a peer reset, a
    /// connection error, or server cancellation caused the drop.
    ServiceFutureDropped,
    /// The application service returned an error.
    ServiceFailed,
    /// The response body was consumed to its end by the protocol driver.
    ResponseBodyConsumed,
    /// The response body returned an error to the protocol driver.
    ResponseBodyFailed,
    /// The protocol driver dropped the response body before consuming it.
    ResponseBodyDropped,
}

/// A request- or stream-scoped terminal signal inserted into request extensions.
///
/// A clone may be retained by an adapter task that outlives the Tower service
/// future. The signal is distinct for every request, including concurrent
/// streams on one HTTP/2 or HTTP/3 connection. A terminal reason describes
/// what the service boundary observed; it is not a protocol error code.
#[derive(Clone, Debug)]
pub struct RequestLifetime {
    ended: watch::Receiver<Option<RequestEndReason>>,
}

impl RequestLifetime {
    /// Returns the terminal reason if the request has ended.
    #[must_use]
    pub fn end_reason(&self) -> Option<RequestEndReason> {
        *self.ended.borrow()
    }

    /// Waits for and returns the terminal reason.
    ///
    /// Returns `None` only if the internal signal channel closes without a
    /// terminal reason, which indicates a server implementation error.
    pub async fn wait_until_ended(&mut self) -> Option<RequestEndReason> {
        loop {
            if let Some(reason) = *self.ended.borrow_and_update() {
                return Some(reason);
            }
            if self.ended.changed().await.is_err() {
                return None;
            }
        }
    }
}

struct ConnectionLifetimeGuard {
    closed: watch::Sender<bool>,
}

impl ConnectionLifetimeGuard {
    fn new() -> (ConnectionLifetime, Self) {
        let (closed, receiver) = watch::channel(false);
        (ConnectionLifetime { closed: receiver }, Self { closed })
    }
}

impl Drop for ConnectionLifetimeGuard {
    fn drop(&mut self) {
        self.closed.send_replace(true);
    }
}

struct RequestLifetimeGuard {
    ended: watch::Sender<Option<RequestEndReason>>,
    drop_reason: RequestEndReason,
    finished: bool,
}

impl RequestLifetimeGuard {
    fn new() -> (RequestLifetime, Self) {
        let (ended, receiver) = watch::channel(None);
        (
            RequestLifetime { ended: receiver },
            Self {
                ended,
                drop_reason: RequestEndReason::ServiceFutureDropped,
                finished: false,
            },
        )
    }

    fn finish(&mut self, reason: RequestEndReason) {
        if !self.finished {
            self.finished = true;
            self.ended.send_replace(Some(reason));
        }
    }

    fn set_drop_reason(&mut self, reason: RequestEndReason) {
        self.drop_reason = reason;
    }
}

impl Drop for RequestLifetimeGuard {
    fn drop(&mut self) {
        self.finish(self.drop_reason);
    }
}

pin_project! {
    struct RequestLifetimeFuture<F, B> {
        #[pin]
        future: F,
        guard: Option<RequestLifetimeGuard>,
        _body: std::marker::PhantomData<fn() -> B>,
    }
}

impl<F, B> RequestLifetimeFuture<F, B> {
    fn new(future: F, guard: RequestLifetimeGuard) -> Self {
        Self {
            future,
            guard: Some(guard),
            _body: std::marker::PhantomData,
        }
    }
}

impl<F, E, B> Future for RequestLifetimeFuture<F, B>
where
    F: Future<Output = Result<Response<B>, E>>,
    B: Body<Data = Bytes>,
{
    type Output = Result<Response<RequestLifetimeBody<B>>, E>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.project();
        match this.future.poll(context) {
            Poll::Pending => Poll::Pending,
            Poll::Ready(Ok(response)) => {
                let guard = this.guard.take();
                Poll::Ready(Ok(
                    response.map(|body| RequestLifetimeBody::new(body, guard))
                ))
            }
            Poll::Ready(Err(error)) => {
                let _ = this.guard.take().map(|mut guard| {
                    guard.finish(RequestEndReason::ServiceFailed);
                });
                Poll::Ready(Err(error))
            }
        }
    }
}

pin_project! {
    struct RequestLifetimeBody<B> {
        #[pin]
        body: B,
        guard: Option<RequestLifetimeGuard>,
    }
}

impl<B> RequestLifetimeBody<B>
where
    B: Body<Data = Bytes>,
{
    fn new(body: B, mut guard: Option<RequestLifetimeGuard>) -> Self {
        if body.is_end_stream() {
            let _ = guard
                .as_mut()
                .map(|guard| guard.finish(RequestEndReason::ResponseBodyConsumed));
        } else {
            let _ = guard
                .as_mut()
                .map(|guard| guard.set_drop_reason(RequestEndReason::ResponseBodyDropped));
        }
        Self { body, guard }
    }
}

impl<B> Body for RequestLifetimeBody<B>
where
    B: Body<Data = Bytes>,
{
    type Data = Bytes;
    type Error = B::Error;

    fn poll_frame(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Option<Result<http_body::Frame<Self::Data>, Self::Error>>> {
        let mut this = self.project();
        let frame = this.body.as_mut().poll_frame(context);
        let reason = match &frame {
            Poll::Ready(None) => Some(RequestEndReason::ResponseBodyConsumed),
            Poll::Ready(Some(Err(_))) => Some(RequestEndReason::ResponseBodyFailed),
            Poll::Ready(Some(Ok(_))) if this.body.as_ref().get_ref().is_end_stream() => {
                Some(RequestEndReason::ResponseBodyConsumed)
            }
            Poll::Ready(Some(Ok(_))) | Poll::Pending => None,
        };
        if let (Some(guard), Some(reason)) = (this.guard.as_mut(), reason) {
            guard.finish(reason);
        }
        frame
    }

    fn is_end_stream(&self) -> bool {
        self.body.is_end_stream()
    }

    fn size_hint(&self) -> http_body::SizeHint {
        self.body.size_hint()
    }
}

/// TLS metadata available for a TCP or QUIC connection.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TlsInfo {
    alpn_protocol: Option<Arc<[u8]>>,
}

impl TlsInfo {
    /// Returns the negotiated application protocol bytes, if the client
    /// negotiated ALPN.
    #[must_use]
    pub fn alpn_protocol(&self) -> Option<&[u8]> {
        self.alpn_protocol.as_deref()
    }
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            max_connections: 1_024,
            graceful_shutdown_timeout: Duration::from_secs(30),
            application_startup_timeout: Duration::from_secs(30),
            application_shutdown_timeout: Duration::from_secs(30),
            application_lifecycle: None,
            error_observer: None,
        }
    }
}

fn observe_error(
    observer: Option<&ServerErrorObserver>,
    phase: ServerErrorPhase,
    peer_addr: Option<SocketAddr>,
    error: &(dyn Error + Send + Sync + 'static),
) {
    if let Some(observer) = observer {
        let event = ServerErrorEvent {
            phase,
            peer_addr,
            error,
        };
        if catch_unwind(AssertUnwindSafe(|| observer(event))).is_err() {
            tracing::error!(?phase, ?peer_addr, "HTTP server error observer panicked");
        }
    }
}

/// Errors returned while accepting connections or shutting down the server.
#[derive(Debug)]
pub enum ServeError {
    /// The configured connection limit was zero.
    InvalidConnectionLimit,
    /// The graceful-shutdown deadline could not be represented by the runtime clock.
    InvalidGracefulShutdownTimeout,
    /// A lifecycle timeout could not be represented by the runtime clock.
    InvalidApplicationLifecycleTimeout,
    /// An application lifecycle hook returned its typed error.
    ApplicationLifecycleFailed {
        /// The lifecycle phase that failed.
        stage: ApplicationLifecycleStage,
        /// The original application error and its source chain.
        error: ApplicationLifecycleError,
    },
    /// An application lifecycle hook panicked while being created or polled.
    ApplicationLifecyclePanicked {
        /// The lifecycle phase that panicked.
        stage: ApplicationLifecycleStage,
    },
    /// An application lifecycle hook exceeded its configured deadline.
    ApplicationLifecycleTimedOut {
        /// The lifecycle phase whose deadline expired.
        stage: ApplicationLifecycleStage,
    },
    /// Serving and the subsequent application shutdown hook both failed.
    ServerAndApplicationShutdown {
        /// The server failure that caused serving to stop.
        server: Box<ServeError>,
        /// The shutdown-hook failure observed after the server stopped.
        application: Box<ServeError>,
    },
    /// Accepting a new TCP connection failed.
    Accept(io::Error),
    /// One or more active connections did not finish before the shutdown deadline.
    GracefulShutdownTimedOut,
}

impl fmt::Display for ServeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidConnectionLimit => {
                formatter.write_str("max_connections must be greater than zero")
            }
            Self::InvalidGracefulShutdownTimeout => {
                formatter.write_str("graceful shutdown timeout exceeds the runtime clock range")
            }
            Self::InvalidApplicationLifecycleTimeout => {
                formatter.write_str("application lifecycle timeout exceeds the runtime clock range")
            }
            Self::ApplicationLifecycleFailed { stage, error } => {
                let stage_name = match stage {
                    ApplicationLifecycleStage::Startup => "startup",
                    ApplicationLifecycleStage::Shutdown => "shutdown",
                };
                write!(formatter, "application {stage_name} hook failed: {error}")
            }
            Self::ApplicationLifecyclePanicked { stage } => {
                let stage_name = match stage {
                    ApplicationLifecycleStage::Startup => "startup",
                    ApplicationLifecycleStage::Shutdown => "shutdown",
                };
                write!(formatter, "application {stage_name} hook panicked")
            }
            Self::ApplicationLifecycleTimedOut { stage } => {
                let stage_name = match stage {
                    ApplicationLifecycleStage::Startup => "startup",
                    ApplicationLifecycleStage::Shutdown => "shutdown",
                };
                write!(
                    formatter,
                    "application {stage_name} hook exceeded its deadline"
                )
            }
            Self::ServerAndApplicationShutdown {
                server,
                application,
            } => write!(
                formatter,
                "server stopped with {server}; {application} also failed",
            ),
            Self::Accept(error) => write!(formatter, "could not accept a TCP connection: {error}"),
            Self::GracefulShutdownTimedOut => {
                formatter.write_str("active connections exceeded the graceful-shutdown deadline")
            }
        }
    }
}

impl Error for ServeError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Accept(error) => Some(error),
            Self::ApplicationLifecycleFailed { error, .. } => Some(error.as_ref()),
            Self::ServerAndApplicationShutdown { server, .. } => Some(server.as_ref()),
            Self::InvalidConnectionLimit
            | Self::InvalidGracefulShutdownTimeout
            | Self::InvalidApplicationLifecycleTimeout
            | Self::ApplicationLifecyclePanicked { .. }
            | Self::ApplicationLifecycleTimedOut { .. }
            | Self::GracefulShutdownTimedOut => None,
        }
    }
}

impl ServeError {
    /// Returns both failures when serving and the subsequent application
    /// shutdown hook fail. The pair keeps both causes accessible because
    /// [`Error::source`] can expose only one source at a time.
    #[must_use]
    pub fn shutdown_failures(&self) -> Option<(&ServeError, &ServeError)> {
        match self {
            Self::ServerAndApplicationShutdown {
                server,
                application,
            } => Some((server, application)),
            _ => None,
        }
    }
}

fn validate_server_config(config: &ServerConfig) -> Result<(), ServeError> {
    if config.max_connections == 0 {
        return Err(ServeError::InvalidConnectionLimit);
    }
    let now = Instant::now();
    if now.checked_add(config.graceful_shutdown_timeout).is_none() {
        return Err(ServeError::InvalidGracefulShutdownTimeout);
    }
    if config.application_lifecycle.is_some()
        && (now
            .checked_add(config.application_startup_timeout)
            .is_none()
            || now
                .checked_add(config.application_shutdown_timeout)
                .is_none())
    {
        return Err(ServeError::InvalidApplicationLifecycleTimeout);
    }
    Ok(())
}

pub(crate) async fn run_with_application_lifecycle<F>(
    config: ServerConfig,
    serving: F,
) -> Result<(), ServeError>
where
    F: Future<Output = Result<(), ServeError>>,
{
    validate_server_config(&config)?;
    let Some(lifecycle) = config.application_lifecycle.as_ref() else {
        return serving.await;
    };

    run_lifecycle_hook(
        lifecycle.as_ref(),
        ApplicationLifecycleStage::Startup,
        config.application_startup_timeout,
        config.error_observer.as_ref(),
    )
    .await?;

    let server_result = serving.await;
    let shutdown_result = run_lifecycle_hook(
        lifecycle.as_ref(),
        ApplicationLifecycleStage::Shutdown,
        config.application_shutdown_timeout,
        config.error_observer.as_ref(),
    )
    .await;

    match (server_result, shutdown_result) {
        (Ok(()), Ok(())) => Ok(()),
        (Err(server), Ok(())) => Err(server),
        (Ok(()), Err(application)) => Err(application),
        (Err(server), Err(application)) => Err(ServeError::ServerAndApplicationShutdown {
            server: Box::new(server),
            application: Box::new(application),
        }),
    }
}

async fn run_lifecycle_hook(
    lifecycle: &dyn ApplicationLifecycle,
    stage: ApplicationLifecycleStage,
    timeout: Duration,
    error_observer: Option<&ServerErrorObserver>,
) -> Result<(), ServeError> {
    let hook = AssertUnwindSafe(async {
        match stage {
            ApplicationLifecycleStage::Startup => lifecycle.startup().await,
            ApplicationLifecycleStage::Shutdown => lifecycle.shutdown().await,
        }
    })
    .catch_unwind();
    let result = tokio::time::timeout(timeout, hook).await;
    let error_phase = match stage {
        ApplicationLifecycleStage::Startup => ServerErrorPhase::ApplicationStartup,
        ApplicationLifecycleStage::Shutdown => ServerErrorPhase::ApplicationShutdown,
    };

    match result {
        Ok(Ok(Ok(()))) => Ok(()),
        Ok(Ok(Err(error))) => {
            observe_error(error_observer, error_phase, None, error.as_ref());
            Err(ServeError::ApplicationLifecycleFailed { stage, error })
        }
        Ok(Err(_)) => {
            let error = ServeError::ApplicationLifecyclePanicked { stage };
            observe_error(error_observer, error_phase, None, &error);
            Err(error)
        }
        Err(_) => {
            let error = ServeError::ApplicationLifecycleTimedOut { stage };
            observe_error(error_observer, error_phase, None, &error);
            Err(error)
        }
    }
}

/// Serves an HTTP application over cleartext TCP on an already-bound listener.
///
/// The caller owns the Tokio runtime and listener. The server accepts HTTP/1.1
/// and cleartext HTTP/2 prior-knowledge connections, clones the service for
/// each connection, and honors Tower readiness for each request. The
/// application service is expected to be cloneable and safe for concurrent
/// use; shared application state should be held behind its own synchronization
/// primitive.
///
/// Request and response body payloads use `Bytes`. Request bodies are passed
/// into the service as Hyper's body type but remain generic at the application
/// implementation boundary. Response bodies are polled incrementally. A
/// service error before response commitment is logged and becomes an empty 500
/// response; a response-body error after commitment terminates that response
/// stream. Each request receives [`ConnectionInfo`] in its extensions with
/// the accepted TCP peer address. HTTP/1.1 requests also receive
/// [`ConnectionUpgrade`] so the application can register upgraded protocol
/// sessions with the connection's graceful-shutdown lifecycle. The crate
/// leaves handshake validation and protocol framing to the application. TLS
/// metadata is `None` on this entry point.
///
/// The `shutdown` future should resolve when the process wants to stop
/// accepting requests. Active connections then receive protocol graceful
/// shutdown and are drained until `config.graceful_shutdown_timeout` expires.
/// When `application_lifecycle` is configured, startup runs before acceptance
/// and shutdown runs after the serving loop drains or cancels active work. The
/// shutdown hook has its own timeout; the total stop interval can therefore
/// include both the connection-drain timeout and the application-hook timeout.
///
/// # Errors
///
/// Returns [`ServeError::InvalidConnectionLimit`] for a zero connection limit,
/// [`ServeError::InvalidGracefulShutdownTimeout`] if the deadline cannot be
/// represented, [`ServeError::Accept`] when the listener fails, or
/// [`ServeError::GracefulShutdownTimedOut`] when active connections exceed the
/// configured drain deadline. When lifecycle hooks are configured, their
/// failures and deadlines are returned as the corresponding
/// [`ServeError::ApplicationLifecycleFailed`],
/// [`ServeError::ApplicationLifecyclePanicked`], or
/// [`ServeError::ApplicationLifecycleTimedOut`] variant.
pub async fn serve_tcp<S, B, Shutdown>(
    listener: TcpListener,
    service: S,
    shutdown: Shutdown,
    config: ServerConfig,
) -> Result<(), ServeError>
where
    S: Service<Request<Incoming>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
    Shutdown: Future<Output = ()>,
{
    run_with_application_lifecycle(
        config.clone(),
        serve_listener(listener, service, shutdown, config, None),
    )
    .await
}

/// Serves an HTTP application over TLS on an already-bound TCP listener.
///
/// The supplied acceptor controls certificate and client-authentication
/// policy. Configure its ALPN list with `h2` and `http/1.1` to enable negotiated
/// HTTP/2 and HTTP/1.1. Each request receives [`ConnectionInfo`] with its peer
/// address and negotiated ALPN bytes when present. The same bounded connection
/// admission, graceful-drain, and optional application-lifecycle behavior as
/// [`serve_tcp`] applies.
///
/// # Errors
///
/// Returns the same server-level errors as [`serve_tcp`]. Individual TLS
/// handshake failures are reported through the optional error observer and
/// close only their connection.
pub async fn serve_tls<S, B, Shutdown>(
    listener: TcpListener,
    acceptor: TlsAcceptor,
    service: S,
    shutdown: Shutdown,
    config: ServerConfig,
) -> Result<(), ServeError>
where
    S: Service<Request<Incoming>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
    Shutdown: Future<Output = ()>,
{
    run_with_application_lifecycle(
        config.clone(),
        serve_listener(listener, service, shutdown, config, Some(acceptor)),
    )
    .await
}

async fn serve_listener<S, B, Shutdown>(
    listener: TcpListener,
    service: S,
    shutdown: Shutdown,
    config: ServerConfig,
    tls_acceptor: Option<TlsAcceptor>,
) -> Result<(), ServeError>
where
    S: Service<Request<Incoming>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
    Shutdown: Future<Output = ()>,
{
    let connection_slots = Arc::new(Semaphore::new(config.max_connections));
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let mut shutdown = Box::pin(shutdown);
    let mut connections = JoinSet::new();
    let mut next_slot: Option<OwnedSemaphorePermit> = None;

    loop {
        tokio::select! {
            _ = &mut shutdown => break,
            joined = connections.join_next(), if !connections.is_empty() => {
                if let Some(joined) = joined {
                    observe_connection(joined);
                }
            }
            slot = Arc::clone(&connection_slots).acquire_owned(), if next_slot.is_none() => {
                next_slot = Some(slot.map_err(|_| ServeError::InvalidConnectionLimit)?);
            }
            accepted = listener.accept(), if next_slot.is_some() => {
                let (stream, peer) = accepted.map_err(ServeError::Accept)?;
                let Some(slot) = next_slot.take() else {
                    continue;
                };
                let service = service.clone();
                let shutdown = shutdown_receiver.clone();
                let error_observer = config.error_observer.clone();
                let tls_acceptor = tls_acceptor.clone();
                connections.spawn(async move {
                    let _slot = slot;
                    let result = match tls_acceptor {
                        Some(acceptor) => match acceptor.accept(stream).await {
                            Ok(stream) => {
                                let alpn_protocol = stream
                                    .get_ref()
                                    .1
                                    .alpn_protocol()
                                    .map(Arc::<[u8]>::from);
                                serve_connection(
                                    stream,
                                    service,
                                    ConnectionInfo {
                                        peer_addr: peer,
                                        tls: Some(TlsInfo { alpn_protocol }),
                                        transport: TransportKind::Tcp,
                                    },
                                    shutdown,
                                    error_observer.as_ref(),
                                )
                                .await
                            }
                            Err(error) => Err(ConnectionError::Tls(error)),
                        },
                        None => {
                            serve_connection(
                                stream,
                                service,
                                ConnectionInfo {
                                    peer_addr: peer,
                                    tls: None,
                                    transport: TransportKind::Tcp,
                                },
                                shutdown,
                                error_observer.as_ref(),
                            )
                            .await
                        }
                    };
                    if let Err(error) = &result {
                        observe_error(
                            error_observer.as_ref(),
                            ServerErrorPhase::Connection,
                            Some(peer),
                            error,
                        );
                        tracing::debug!(%peer, %error, "HTTP connection finished with an error");
                    }
                    result
                });
            }
        }
    }

    shutdown_sender.send_replace(true);
    let shutdown_deadline = Instant::now()
        .checked_add(config.graceful_shutdown_timeout)
        .ok_or(ServeError::InvalidGracefulShutdownTimeout)?;
    while !connections.is_empty() {
        let remaining = shutdown_deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            connections.abort_all();
            drain_aborted_connections(&mut connections).await;
            return Err(ServeError::GracefulShutdownTimedOut);
        }
        match tokio::time::timeout(remaining, connections.join_next()).await {
            Ok(Some(joined)) => observe_connection(joined),
            Ok(None) => break,
            Err(_) => {
                connections.abort_all();
                drain_aborted_connections(&mut connections).await;
                return Err(ServeError::GracefulShutdownTimedOut);
            }
        }
    }

    Ok(())
}

async fn serve_connection<I, S, B>(
    stream: I,
    service: S,
    connection_info: ConnectionInfo,
    mut shutdown: watch::Receiver<bool>,
    error_observer: Option<&ServerErrorObserver>,
) -> Result<(), ConnectionError>
where
    I: AsyncRead + AsyncWrite + Unpin + Send + 'static,
    S: Service<Request<Incoming>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    let peer_addr = connection_info.peer_addr;
    let (connection_lifetime, _connection_lifetime_guard) = ConnectionLifetimeGuard::new();
    let (upgrade_sender, mut upgrade_receiver) = mpsc::unbounded_channel();
    let (upgrade_shutdown_sender, upgrade_shutdown_receiver) = watch::channel(false);
    let connection_upgrade = ConnectionUpgrade {
        sessions: upgrade_sender,
        shutdown: upgrade_shutdown_receiver,
    };
    let mut builder = auto::Builder::new(TokioExecutor::new());
    // RFC 9112 §9.6: a client-side TCP half-close does not mean the client has
    // stopped waiting for its response. Hyper disables this behavior by default.
    builder.http1().half_close(true).max_buf_size(64 * 1024);
    let application = ServiceErrorResponse::new(
        ConnectionInfoService::<S, Incoming, B>::new(
            service,
            connection_info,
            connection_lifetime,
            Some(connection_upgrade),
        ),
        error_observer.cloned(),
        peer_addr,
    );
    let service = TowerToHyperService::new(application);
    let connection = builder.serve_connection_with_upgrades(TokioIo::new(stream), service);
    tokio::pin!(connection);

    let mut connection_result = None;
    let mut upgrade_sessions = JoinSet::new();
    let mut upgrade_receiver_open = true;
    let mut shutdown_started = false;
    let mut upgrade_error = None;

    loop {
        if connection_result.is_some() && upgrade_sessions.is_empty() && !upgrade_receiver_open {
            break;
        }

        tokio::select! {
            result = &mut connection, if connection_result.is_none() => {
                connection_result = Some(result.map_err(ConnectionError::Http));
                upgrade_receiver.close();
                while let Ok(session) = upgrade_receiver.try_recv() {
                    upgrade_sessions.spawn(session);
                }
                upgrade_receiver_open = false;
            }
            session = upgrade_receiver.recv(), if upgrade_receiver_open => match session {
                Some(session) => {
                    upgrade_sessions.spawn(session);
                }
                None => upgrade_receiver_open = false,
            },
            joined = upgrade_sessions.join_next(), if !upgrade_sessions.is_empty() => {
                match joined {
                    Some(Ok(Ok(()))) | None => {}
                    Some(Ok(Err(error))) => {
                        if upgrade_error.is_none() {
                            upgrade_error = Some(ConnectionError::Upgrade(error));
                        }
                    }
                    Some(Err(error)) => {
                        observe_connection_task_error(error, false);
                    }
                }
            }
            _ = shutdown.changed(), if !shutdown_started => {
                shutdown_started = true;
                upgrade_shutdown_sender.send_replace(true);
                if connection_result.is_none() {
                    connection.as_mut().graceful_shutdown();
                }
            }
        }
    }

    if let Some(error) = upgrade_error {
        return Err(error);
    }

    connection_result.unwrap_or(Ok(()))
}

struct ConnectionInfoService<S, RequestBody, B> {
    inner: S,
    connection_info: ConnectionInfo,
    connection_lifetime: ConnectionLifetime,
    connection_upgrade: Option<ConnectionUpgrade>,
    _types: std::marker::PhantomData<fn(RequestBody) -> B>,
}

impl<S, RequestBody, B> Clone for ConnectionInfoService<S, RequestBody, B>
where
    S: Clone,
{
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
            connection_info: self.connection_info.clone(),
            connection_lifetime: self.connection_lifetime.clone(),
            connection_upgrade: self.connection_upgrade.clone(),
            _types: std::marker::PhantomData,
        }
    }
}

impl<S, RequestBody, B> ConnectionInfoService<S, RequestBody, B> {
    fn new(
        inner: S,
        connection_info: ConnectionInfo,
        connection_lifetime: ConnectionLifetime,
        connection_upgrade: Option<ConnectionUpgrade>,
    ) -> Self {
        Self {
            inner,
            connection_info,
            connection_lifetime,
            connection_upgrade,
            _types: std::marker::PhantomData,
        }
    }
}

impl<S, RequestBody, B> Service<Request<RequestBody>> for ConnectionInfoService<S, RequestBody, B>
where
    S: Service<Request<RequestBody>, Response = Response<B>>,
    B: Body<Data = Bytes>,
{
    type Response = Response<RequestLifetimeBody<B>>;
    type Error = S::Error;
    type Future = RequestLifetimeFuture<S::Future, B>;

    fn poll_ready(&mut self, context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        self.inner.poll_ready(context)
    }

    fn call(&mut self, mut request: Request<RequestBody>) -> Self::Future {
        request
            .extensions_mut()
            .insert(self.connection_info.clone());
        request
            .extensions_mut()
            .insert(self.connection_lifetime.clone());
        if request.version() == http::Version::HTTP_11 {
            if let Some(connection_upgrade) = &self.connection_upgrade {
                request.extensions_mut().insert(connection_upgrade.clone());
            }
        }
        let (request_lifetime, guard) = RequestLifetimeGuard::new();
        request.extensions_mut().insert(request_lifetime);
        RequestLifetimeFuture::new(self.inner.call(request), guard)
    }
}

#[derive(Debug)]
enum ConnectionError {
    Http(Box<dyn Error + Send + Sync>),
    Upgrade(BoxBodyError),
    Tls(io::Error),
}

impl Error for ConnectionError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Http(error) => Some(error.as_ref()),
            Self::Upgrade(error) => Some(error.as_ref()),
            Self::Tls(error) => Some(error),
        }
    }
}

impl fmt::Display for ConnectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(error) => write!(formatter, "HTTP connection failed: {error}"),
            Self::Upgrade(error) => write!(formatter, "upgraded session failed: {error}"),
            Self::Tls(error) => write!(formatter, "TLS handshake failed: {error}"),
        }
    }
}

fn observe_connection(joined: Result<Result<(), ConnectionError>, JoinError>) {
    match joined {
        Ok(Ok(())) => {}
        Ok(Err(error)) => tracing::debug!(%error, "HTTP connection ended"),
        Err(error) => observe_connection_task_error(error, false),
    }
}

fn observe_connection_task_error(error: JoinError, during_abort: bool) {
    if error.is_cancelled() {
        return;
    }

    if during_abort {
        tracing::error!(%error, "HTTP connection task failed while aborting");
    } else {
        tracing::error!(%error, "HTTP connection task failed");
    }
}

async fn drain_aborted_connections(connections: &mut JoinSet<Result<(), ConnectionError>>) {
    while let Some(joined) = connections.join_next().await {
        if let Err(error) = joined {
            observe_connection_task_error(error, true);
        }
    }
}

struct ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>>,
{
    inner: S,
    readiness_error: Option<S::Error>,
    error_observer: Option<ServerErrorObserver>,
    peer_addr: SocketAddr,
    _response_body: std::marker::PhantomData<fn() -> B>,
    _request_body: std::marker::PhantomData<fn() -> RequestBody>,
}

impl<S, B, RequestBody> Clone for ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>> + Clone,
{
    fn clone(&self) -> Self {
        Self {
            inner: self.inner.clone(),
            readiness_error: None,
            error_observer: self.error_observer.clone(),
            peer_addr: self.peer_addr,
            _response_body: std::marker::PhantomData,
            _request_body: std::marker::PhantomData,
        }
    }
}

impl<S, B, RequestBody> ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>>,
{
    fn new(inner: S, error_observer: Option<ServerErrorObserver>, peer_addr: SocketAddr) -> Self {
        Self {
            inner,
            readiness_error: None,
            error_observer,
            peer_addr,
            _response_body: std::marker::PhantomData,
            _request_body: std::marker::PhantomData,
        }
    }
}

type ResponseOnError<B> = Response<ServerResponseBody<B>>;
type ServiceResponseFuture<S, B, RequestBody> = FutureEither<
    ObserveServiceResult<
        <S as Service<Request<RequestBody>>>::Future,
        <S as Service<Request<RequestBody>>>::Error,
        B,
    >,
    Ready<Result<ResponseOnError<B>, Infallible>>,
>;

impl<S, B, RequestBody> Service<Request<RequestBody>> for ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>, Response = Response<B>> + Clone,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    type Response = ResponseOnError<B>;
    type Error = Infallible;
    type Future = ServiceResponseFuture<S, B, RequestBody>;

    fn poll_ready(&mut self, context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        match self.inner.poll_ready(context) {
            Poll::Ready(Ok(())) => Poll::Ready(Ok(())),
            Poll::Ready(Err(error)) => {
                observe_error(
                    self.error_observer.as_ref(),
                    ServerErrorPhase::Readiness,
                    Some(self.peer_addr),
                    &error,
                );
                self.readiness_error = Some(error);
                Poll::Ready(Ok(()))
            }
            Poll::Pending => Poll::Pending,
        }
    }

    fn call(&mut self, request: Request<RequestBody>) -> Self::Future {
        if let Some(error) = self.readiness_error.take() {
            tracing::error!(%error, "HTTP application service became unavailable");
            return FutureEither::Right(ready(Ok(internal_server_error())));
        }
        FutureEither::Left(ObserveServiceResult::new(
            self.inner.call(request),
            self.error_observer.clone(),
            self.peer_addr,
        ))
    }
}

pin_project! {
    struct ObserveServiceResult<F, E, B> {
        #[pin]
        future: F,
        error_observer: Option<ServerErrorObserver>,
        peer_addr: SocketAddr,
        _types: std::marker::PhantomData<fn() -> (E, B)>,
    }
}

impl<F, E, B> ObserveServiceResult<F, E, B> {
    fn new(future: F, error_observer: Option<ServerErrorObserver>, peer_addr: SocketAddr) -> Self {
        Self {
            future,
            error_observer,
            peer_addr,
            _types: std::marker::PhantomData,
        }
    }
}

impl<F, E, B> Future for ObserveServiceResult<F, E, B>
where
    F: Future<Output = Result<Response<B>, E>>,
    E: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    type Output = Result<ResponseOnError<B>, Infallible>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.project();
        match this.future.poll(context) {
            Poll::Pending => Poll::Pending,
            Poll::Ready(Ok(response)) => {
                let response = response.map(|body| match this.error_observer.take() {
                    Some(observer) => ServerResponseBody::Observed {
                        body: ObservedBody::new(body, observer, *this.peer_addr),
                    },
                    None => ServerResponseBody::App { body },
                });
                Poll::Ready(Ok(response))
            }
            Poll::Ready(Err(error)) => {
                observe_error(
                    this.error_observer.as_ref(),
                    ServerErrorPhase::Service,
                    Some(*this.peer_addr),
                    &error,
                );
                tracing::error!(%error, "HTTP application service failed before response commitment");
                Poll::Ready(Ok(internal_server_error()))
            }
        }
    }
}

pin_project! {
    #[project = ServerResponseBodyProj]
    #[project_ref = ServerResponseBodyProjRef]
    enum ServerResponseBody<B> {
        App { #[pin] body: B },
        Observed { #[pin] body: ObservedBody<B> },
        Empty { #[pin] body: Empty<Bytes> },
    }
}

impl<B> Body for ServerResponseBody<B>
where
    B: Body<Data = Bytes>,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    type Data = Bytes;
    type Error = BoxBodyError;

    fn poll_frame(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Option<Result<http_body::Frame<Self::Data>, Self::Error>>> {
        match self.project() {
            ServerResponseBodyProj::App { body } => body
                .poll_frame(context)
                .map(|frame| frame.map(|result| result.map_err(Into::into))),
            ServerResponseBodyProj::Observed { body } => body.poll_frame(context),
            ServerResponseBodyProj::Empty { body } => body
                .poll_frame(context)
                .map(|frame| frame.map(|result| result.map_err(|never| match never {}))),
        }
    }

    fn is_end_stream(&self) -> bool {
        match self {
            Self::App { body } => body.is_end_stream(),
            Self::Observed { body } => body.is_end_stream(),
            Self::Empty { body } => body.is_end_stream(),
        }
    }

    fn size_hint(&self) -> http_body::SizeHint {
        match self {
            Self::App { body } => body.size_hint(),
            Self::Observed { body } => body.size_hint(),
            Self::Empty { body } => body.size_hint(),
        }
    }
}

pin_project! {
    #[project = ObservedBodyProj]
    #[project_ref = ObservedBodyProjRef]
    struct ObservedBody<B> {
        #[pin]
        inner: B,
        error_observer: Option<ServerErrorObserver>,
        peer_addr: SocketAddr,
    }
}

impl<B> ObservedBody<B> {
    fn new(inner: B, error_observer: ServerErrorObserver, peer_addr: SocketAddr) -> Self {
        Self {
            inner,
            error_observer: Some(error_observer),
            peer_addr,
        }
    }
}

impl<B> Body for ObservedBody<B>
where
    B: Body<Data = Bytes>,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    type Data = Bytes;
    type Error = BoxBodyError;

    fn poll_frame(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Option<Result<http_body::Frame<Self::Data>, Self::Error>>> {
        let this = self.project();
        match this.inner.poll_frame(context) {
            Poll::Ready(Some(Ok(frame))) => Poll::Ready(Some(Ok(frame))),
            Poll::Ready(Some(Err(error))) => {
                let error: BoxBodyError = error.into();
                let _ = this.error_observer.take().map(|error_observer| {
                    observe_error(
                        Some(&error_observer),
                        ServerErrorPhase::ResponseBody,
                        Some(*this.peer_addr),
                        error.as_ref(),
                    );
                });
                Poll::Ready(Some(Err(error)))
            }
            Poll::Ready(None) => Poll::Ready(None),
            Poll::Pending => Poll::Pending,
        }
    }

    fn is_end_stream(&self) -> bool {
        self.inner.is_end_stream()
    }

    fn size_hint(&self) -> http_body::SizeHint {
        self.inner.size_hint()
    }
}

fn internal_server_error<B>() -> ResponseOnError<B>
where
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    let mut response = Response::new(ServerResponseBody::Empty { body: Empty::new() });
    *response.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
    response
}
