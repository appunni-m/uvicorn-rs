//! HTTP/3 serving over a caller-configured Quinn endpoint.

// These modules are vendored MIT-licensed sources. Keep their upstream
// implementation intact while retaining Clippy's correctness checks and the
// crate-wide unsafe-code prohibition.
#[allow(clippy::all, clippy::panic, clippy::unwrap_used, clippy::expect_used)]
#[deny(clippy::correctness)]
pub mod h3;
#[allow(clippy::all, clippy::panic, clippy::unwrap_used, clippy::expect_used)]
#[deny(clippy::correctness)]
pub mod h3_quinn;
mod transport;

#[cfg(coverage)]
pub(crate) mod coverage;

#[cfg(coverage)]
pub(crate) use coverage::{
    CoverageClient, coverage_accept_bidi_error, coverage_exercise_client_adapter_methods,
    coverage_finish_after_reset, coverage_open_bidi_application_close_code,
};

use std::{
    error::Error,
    fmt,
    future::Future,
    io,
    panic::AssertUnwindSafe,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
    time::Duration,
};

use self::{h3::error::Code, h3_quinn::quinn};
use bytes::{Buf, Bytes};
use futures_util::FutureExt;
use http::{Request, Response, StatusCode, Version};
use http_body::{Body, Frame, SizeHint};
use http_body_util::BodyExt;
use pin_project_lite::pin_project;
use tokio::{
    sync::{Semaphore, watch},
    task::JoinSet,
};
use tower_service::Service;

use crate::{
    ConcurrencyLimitObserver, ConnectionInfo, ConnectionInfoService, ServeError, ServerConfig,
    ServerErrorObserver, ServerErrorPhase, ServiceErrorPolicy, ServiceErrorResponse, TlsInfo,
    TransportKind, observe_error,
};

/// Error returned when reading an HTTP/3 request body.
pub type Http3RequestBodyError = Box<dyn Error + Send + Sync + 'static>;

pin_project! {
    /// A streaming HTTP/3 request body backed directly by its QUIC receive stream.
    ///
    /// The body does not spawn a pump task or buffer the complete request. It
    /// yields each received DATA frame when the application polls for it and
    /// yields request trailers after the DATA stream ends.
    pub struct Http3RequestBody {
        stream: h3::server::RequestStream<transport::RecvStream, Bytes>,
        finished: bool,
        peer_stopped: watch::Receiver<bool>,
    }
}

impl Http3RequestBody {
    fn new(
        stream: h3::server::RequestStream<transport::RecvStream, Bytes>,
        peer_stopped: watch::Receiver<bool>,
    ) -> Self {
        Self {
            stream,
            finished: false,
            peer_stopped,
        }
    }

    /// Returns whether the client stopped receiving this request's response.
    ///
    /// The future resolves to `true` after the peer sends QUIC `STOP_SENDING`
    /// for the response direction. It resolves to `false` if the request
    /// handler retires without observing a peer stop. Adapters can use this
    /// notification to deliver their protocol-level disconnect event while
    /// preserving the request body stream API.
    pub fn peer_stop_notification(&self) -> impl Future<Output = bool> + Send + 'static + use<> {
        let mut peer_stopped = self.peer_stopped.clone();
        async move { peer_stopped.wait_for(|stopped| *stopped).await.is_ok() }
    }
}

impl Body for Http3RequestBody {
    type Data = Bytes;
    type Error = Http3RequestBodyError;

    fn poll_frame(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Self::Data>, Self::Error>>> {
        let this = self.project();
        if *this.finished {
            return Poll::Ready(None);
        }

        match this.stream.poll_recv_data(context) {
            Poll::Pending => return Poll::Pending,
            Poll::Ready(Err(error)) => {
                *this.finished = true;
                return Poll::Ready(Some(Err(Box::new(error))));
            }
            Poll::Ready(Ok(Some(mut data))) => {
                let len = data.remaining();
                return Poll::Ready(Some(Ok(Frame::data(data.copy_to_bytes(len)))));
            }
            Poll::Ready(Ok(None)) => {}
        }

        #[cfg(coverage)]
        let trailers = if crate::take_http3_request_body_trailers_pending_fault() {
            // The current H3 implementation has no network state that can
            // produce this transition, so coverage builds synthesize one
            // wakeable Pending result to verify that the body poll resumes.
            context.waker().wake_by_ref();
            Poll::Pending
        } else {
            this.stream.poll_recv_trailers(context)
        };
        #[cfg(not(coverage))]
        let trailers = this.stream.poll_recv_trailers(context);

        match trailers {
            Poll::Pending => {
                // `poll_recv_data` can return `None` at the end of an empty
                // DATA frame. Poll data again after returning Pending so a
                // later DATA frame is not treated as a trailer-sequence error.
                Poll::Pending
            }
            Poll::Ready(Err(error)) => {
                *this.finished = true;
                Poll::Ready(Some(Err(Box::new(error))))
            }
            Poll::Ready(Ok(Some(trailers))) => {
                *this.finished = true;
                Poll::Ready(Some(Ok(Frame::trailers(trailers))))
            }
            Poll::Ready(Ok(None)) => {
                *this.finished = true;
                Poll::Ready(None)
            }
        }
    }

    fn is_end_stream(&self) -> bool {
        self.finished
    }

    fn size_hint(&self) -> SizeHint {
        SizeHint::default()
    }
}

/// Serves an HTTP/3 application over a caller-configured Quinn endpoint.
///
/// The endpoint must have a server TLS configuration whose ALPN list includes
/// `h3`. This function owns no certificate policy: callers create and bind the
/// [`quinn::Endpoint`] and remain responsible for its TLS configuration. The
/// accepted request uses HTTP version `HTTP_3`, and its body is the streaming
/// [`Http3RequestBody`] type. Each request receives [`ConnectionInfo`] with its
/// QUIC peer address, `TransportKind::Quic`, and negotiated ALPN bytes.
///
/// Response bodies are polled one frame at a time. Sending each frame awaits
/// QUIC/H3 flow control before the next body frame is polled. Request DATA and
/// trailers are exposed incrementally to the service. On shutdown, the server
/// disables new endpoint handshakes, sends HTTP/3 GOAWAY on active
/// connections, drains active request tasks, then closes the endpoint. If the
/// configured drain deadline expires, active connection tasks are cancelled.
/// Closing another clone of the endpoint also ends acceptance and starts the
/// server cleanup path. Use `shutdown` when active connections should receive
/// GOAWAY and drain before the endpoint is closed.
///
/// # Errors
///
/// Returns [`ServeError::InvalidConnectionLimit`] for a zero connection limit,
/// [`ServeError::ConnectionLimitTooLarge`] when the limit exceeds Tokio's
/// maximum semaphore permit count, [`ServeError::ConnectionAdmissionClosed`]
/// if the internal admission semaphore closes while serving,
/// [`ServeError::InvalidGracefulShutdownTimeout`] if the deadline cannot be
/// represented, or [`ServeError::GracefulShutdownTimedOut`] when active
/// connections exceed the configured drain deadline. Individual QUIC
/// handshakes, HTTP/3 connections, and streams are reported through the
/// optional error observer and do not terminate the listener. When lifecycle
/// hooks are configured, startup must also succeed before endpoint acceptance;
/// shutdown runs after active connections are drained or cancelled.
pub async fn serve_http3<S, B, Shutdown>(
    endpoint: quinn::Endpoint,
    service: S,
    shutdown: Shutdown,
    config: ServerConfig,
) -> Result<(), ServeError>
where
    S: Service<Request<Http3RequestBody>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<super::BoxBodyError> + Send + Sync + 'static,
    Shutdown: Future<Output = ()>,
{
    let lifecycle_config = config.clone();
    super::run_with_application_lifecycle(lifecycle_config, async move {
        let connection_slots = Arc::new(Semaphore::new(config.max_connections));
        let request_concurrency = config
            .limit_concurrency
            .map(|limit| Arc::new(crate::RequestConcurrency::new(limit)));
        let default_headers = Arc::new(config.default_headers.clone());
        #[cfg(coverage)]
        if super::take_listener_admission_closed_fault() {
            connection_slots.close();
        }
        let (shutdown_sender, shutdown_receiver) = watch::channel(false);
        let mut shutdown = Box::pin(shutdown);
        let mut connections = JoinSet::new();

        'accept: loop {
            let slot = tokio::select! {
                _ = &mut shutdown => break 'accept,
                slot = Arc::clone(&connection_slots).acquire_owned() => {
                    slot.map_err(ServeError::ConnectionAdmissionClosed)?
                }
            };

            loop {
                tokio::select! {
                    _ = &mut shutdown => break 'accept,
                    joined = connections.join_next(), if !connections.is_empty() => {
                        observe_connection_task(joined);
                    }
                    incoming = endpoint.accept() => {
                        let Some(incoming) = incoming else { break 'accept; };
                        let service = service.clone();
                        let shutdown = shutdown_receiver.clone();
                        let error_observer = config.error_observer.clone();
                        let concurrency_limit_observer =
                            config.concurrency_limit_observer.clone();
                        let service_error_policy = config.service_error_policy;
                        let request_concurrency = request_concurrency.clone();
                        let default_headers = Arc::clone(&default_headers);
                        connections.spawn(async move {
                            let _slot = slot;
                            let connection_options = Http3ConnectionOptions {
                                error_observer: error_observer.as_ref(),
                                concurrency_limit_observer: concurrency_limit_observer.as_ref(),
                                service_error_policy,
                                request_concurrency,
                                default_headers,
                            };
                            if let Err(error) = serve_incoming_connection(
                                incoming,
                                service,
                                shutdown,
                                connection_options,
                            ).await {
                                tracing::debug!(%error, "HTTP/3 connection finished with an error");
                            }
                        });
                        break;
                    }
                }
            }
        }

        finish_http3_shutdown(
            endpoint,
            shutdown_sender,
            &mut connections,
            config.graceful_shutdown_timeout,
        )
        .await
    })
    .await
}

struct Http3ConnectionOptions<'a> {
    error_observer: Option<&'a ServerErrorObserver>,
    concurrency_limit_observer: Option<&'a ConcurrencyLimitObserver>,
    service_error_policy: ServiceErrorPolicy,
    request_concurrency: Option<Arc<crate::RequestConcurrency>>,
    default_headers: Arc<Vec<(http::HeaderName, http::HeaderValue)>>,
}

async fn finish_http3_shutdown(
    endpoint: quinn::Endpoint,
    shutdown_sender: watch::Sender<bool>,
    connections: &mut JoinSet<()>,
    graceful_shutdown_timeout: Option<Duration>,
) -> Result<(), ServeError> {
    endpoint.set_server_config(None);
    shutdown_sender.send_replace(true);
    let shutdown_deadline = crate::graceful_shutdown_deadline(graceful_shutdown_timeout)?;
    loop {
        let joined = match shutdown_deadline {
            Some(deadline) => tokio::select! {
                biased;
                // Keep the original deadline strict, while letting an empty
                // set finish through `join_next()` even after the deadline.
                _ = tokio::time::sleep_until(deadline), if !connections.is_empty() => {
                    connections.abort_all();
                    drain_connection_tasks(connections).await;
                    endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown deadline");
                    return Err(ServeError::GracefulShutdownTimedOut);
                }
                joined = connections.join_next() => joined,
            },
            None => connections.join_next().await,
        };
        match joined {
            Some(joined) => observe_connection_task(Some(joined)),
            None => break,
        }
    }

    endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown");
    if let Some(timeout) = graceful_shutdown_timeout {
        if tokio::time::timeout(timeout, endpoint.wait_idle())
            .await
            .is_err()
        {
            return Err(ServeError::GracefulShutdownTimedOut);
        }
    } else {
        endpoint.wait_idle().await;
    }
    Ok(())
}

async fn serve_incoming_connection<S, B>(
    incoming: quinn::Incoming,
    service: S,
    mut shutdown: watch::Receiver<bool>,
    connection_options: Http3ConnectionOptions<'_>,
) -> Result<(), Http3ConnectionError>
where
    S: Service<Request<Http3RequestBody>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<super::BoxBodyError> + Send + Sync + 'static,
{
    let peer_addr = incoming.remote_address();
    let connecting = tokio::select! {
        result = incoming => result,
        _ = shutdown.changed() => return Ok(()),
    };
    let connection = match connecting {
        Ok(connection) => connection,
        Err(error) => {
            let error = Http3ConnectionError::Quic(error);
            observe_error(
                connection_options.error_observer,
                ServerErrorPhase::Connection,
                Some(peer_addr),
                &error,
            );
            return Err(error);
        }
    };

    let alpn_protocol = connection
        .handshake_data()
        .and_then(|data| data.downcast::<quinn::crypto::rustls::HandshakeData>().ok())
        .and_then(|data| data.protocol);
    if alpn_protocol.as_deref() != Some(b"h3") {
        connection.close(
            quinn::VarInt::from_u32(0x102),
            b"HTTP/3 requires the h3 ALPN",
        );
        let error = Http3ConnectionError::AlpnNotH3;
        observe_error(
            connection_options.error_observer,
            ServerErrorPhase::Connection,
            Some(peer_addr),
            &error,
        );
        return Err(error);
    }

    #[cfg(coverage)]
    if crate::take_http3_peer_bidi_stream_credit_gate() {
        // Exercise the real QUIC stream-credit wait in the client adapter.
        // The test endpoint advertises zero initial credit. This accepted
        // connection grants one stream only after the client observes Pending.
        crate::observe_http3_peer_bidi_stream_credit_gate_installed();
        let connection = connection.clone();
        tokio::spawn(async move {
            crate::wait_for_http3_peer_bidi_stream_credit_release().await;
            connection.set_max_concurrent_bi_streams(quinn::VarInt::from_u32(1));
            crate::observe_http3_peer_bidi_stream_credit_granted();
        });
    }

    let connection_info = ConnectionInfo {
        peer_addr,
        tls: Some(TlsInfo {
            alpn_protocol: alpn_protocol.map(Arc::<[u8]>::from),
        }),
        transport: TransportKind::Quic,
    };
    let _connection_guard = connection_options
        .request_concurrency
        .as_ref()
        .map(crate::RequestConcurrency::connection_started);
    let result = serve_http3_connection(
        connection,
        service,
        connection_info,
        &mut shutdown,
        &connection_options,
    )
    .await;
    if let Err(error) = &result {
        observe_error(
            connection_options.error_observer,
            ServerErrorPhase::Connection,
            Some(peer_addr),
            error,
        );
    }
    result
}

async fn serve_http3_connection<S, B>(
    connection: quinn::Connection,
    service: S,
    connection_info: ConnectionInfo,
    shutdown: &mut watch::Receiver<bool>,
    connection_options: &Http3ConnectionOptions<'_>,
) -> Result<(), Http3ConnectionError>
where
    S: Service<Request<Http3RequestBody>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<super::BoxBodyError> + Send + Sync + 'static,
{
    let peer_addr = connection_info.peer_addr();
    let (connection_lifetime, _connection_lifetime_guard) = crate::ConnectionLifetimeGuard::new();
    let (transport, peer_stops) = transport::Connection::new(connection.clone());
    let created = h3::server::Connection::new(transport)
        .await
        .map_err(Http3ConnectionError::H3)?;
    let info_service = ConnectionInfoService::<S, Http3RequestBody, B>::new(
        service,
        connection_info,
        connection_lifetime,
        None,
        crate::ConnectionRequestMetadata::default(),
    );
    let application =
        ServiceErrorResponse::<_, crate::RequestLifetimeBody<B>, Http3RequestBody>::new(
            info_service,
            connection_options.error_observer.cloned(),
            connection_options.concurrency_limit_observer.cloned(),
            peer_addr,
            connection_options.service_error_policy,
            connection_options.request_concurrency.clone(),
            Arc::clone(&connection_options.default_headers),
        );
    let mut h3_connection = created;
    let mut requests = JoinSet::new();
    let mut connection_error = None;

    loop {
        tokio::select! {
            biased;
            // The listener owns this watch sender and only changes it when
            // shutdown begins. A closed sender also means no more streams
            // should be accepted, so either result drains the H3 connection.
            _ = shutdown.changed() => {
                h3_connection
                    .shutdown(0)
                    .await
                    .map_err(Http3ConnectionError::H3)?;
                break;
            }
            Some(result) = requests.join_next(), if !requests.is_empty() => {
                observe_request_task(result);
            }
            accepted = h3_connection.accept() => {
                match accepted {
                    Ok(Some(resolver)) => {
                        let application = application.clone();
                        let error_observer = connection_options.error_observer.cloned();
                        let peer_stops = peer_stops.clone();
                        requests.spawn(async move {
                            if let Err(error) = handle_http3_request(
                                resolver,
                                application,
                                peer_addr,
                                error_observer,
                                peer_stops,
                            )
                            .await
                            {
                                tracing::debug!(%error, "HTTP/3 request stream failed");
                            }
                        });
                    }
                    Ok(None) => break,
                    Err(error) => {
                        connection_error = Some(Http3ConnectionError::H3(error));
                        break;
                    }
                }
            }
        }
    }

    if connection_error.is_some() {
        connection.close(
            quinn::VarInt::from_u32(0x102),
            b"HTTP/3 request acceptance failed",
        );
    }

    // The connection owns every request stream. Once QUIC closes, no sibling
    // request can make progress, so cancel the remaining applications before
    // draining their task results.
    while !requests.is_empty() {
        tokio::select! {
            biased;
            _ = connection.closed() => {
                requests.abort_all();
                break;
            }
            Some(result) = requests.join_next() => observe_request_task(result),
        }
    }
    while let Some(result) = requests.join_next().await {
        observe_request_task(result);
    }

    if let Some(error) = connection_error {
        return Err(error);
    }

    connection.close(quinn::VarInt::from_u32(0), b"HTTP/3 connection drained");
    Ok(())
}

async fn handle_http3_request<S, B>(
    resolver: h3::server::RequestResolver<transport::Connection, Bytes>,
    service: ServiceErrorResponse<
        ConnectionInfoService<S, Http3RequestBody, B>,
        crate::RequestLifetimeBody<B>,
        Http3RequestBody,
    >,
    peer_addr: std::net::SocketAddr,
    error_observer: Option<ServerErrorObserver>,
    peer_stops: transport::PeerStops,
) -> Result<(), Http3RequestStreamError<S::Error>>
where
    S: Service<Request<Http3RequestBody>, Response = Response<B>> + Clone,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<super::BoxBodyError> + Send + Sync + 'static,
{
    let (mut request, stream) = resolver
        .resolve_request()
        .await
        .map_err(Http3RequestStreamError::H3)?;
    *request.version_mut() = Version::HTTP_3;
    let (mut send_stream, receive_stream) = stream.split();
    let (peer_stopped_tx, peer_stopped_rx) = watch::channel(false);
    let request = request.map(|()| Http3RequestBody::new(receive_stream, peer_stopped_rx));
    let Some(mut peer_stopped) = peer_stops.take(send_stream.send_id()) else {
        #[cfg(coverage)]
        crate::observe_http3_peer_stop_observer_unavailable_fault();
        let error = Http3RequestStreamError::ObserverUnavailable(io::Error::other(
            "HTTP/3 request has no send-stream stop observer",
        ));
        observe_error(
            error_observer.as_ref(),
            ServerErrorPhase::Connection,
            Some(peer_addr),
            &error,
        );
        let mut response = Response::new(());
        *response.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
        send_http3_response_start::<S::Error>(&mut send_stream, response).await?;
        finish_http3_response::<S::Error>(&mut send_stream).await?;
        return Err(error);
    };

    let stop_code = {
        let work = run_http3_request(
            request,
            &mut send_stream,
            service,
            peer_addr,
            error_observer.clone(),
        );
        tokio::pin!(work);
        tokio::select! {
            biased;
            stopped = &mut peer_stopped => match stopped {
                Ok(Some(code)) => {
                    peer_stopped_tx.send_replace(true);
                    code
                }
                // Quinn also returns None after the local send side has been
                // fully retired. It is not evidence that the peer cancelled
                // the application, and the completed observer must not be
                // polled again.
                Ok(None) => return work.await,
                Err(error) => {
                    let error = Http3RequestStreamError::PeerStop(error);
                    observe_error(
                        error_observer.as_ref(),
                        ServerErrorPhase::Connection,
                        Some(peer_addr),
                        &error,
                    );
                    return Err(error);
                }
            },
            result = &mut work => return result,
        }
    };

    // Leaving the block drops pending readiness, application, and body
    // futures before resetting just this request. The connection's accept
    // driver continues serving sibling streams.
    send_stream.stop_stream(Code::from(stop_code.into_inner()));
    Ok(())
}

async fn run_http3_request<S, B>(
    request: Request<Http3RequestBody>,
    send_stream: &mut h3::server::RequestStream<transport::SendStream, Bytes>,
    mut service: ServiceErrorResponse<
        ConnectionInfoService<S, Http3RequestBody, B>,
        crate::RequestLifetimeBody<B>,
        Http3RequestBody,
    >,
    peer_addr: std::net::SocketAddr,
    error_observer: Option<ServerErrorObserver>,
) -> Result<(), Http3RequestStreamError<S::Error>>
where
    S: Service<Request<Http3RequestBody>, Response = Response<B>> + Clone,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<super::BoxBodyError> + Send + Sync + 'static,
{
    let response = match AssertUnwindSafe(futures_util::future::poll_fn(|context| {
        service.poll_ready(context)
    }))
    .catch_unwind()
    .await
    {
        Ok(Ok(())) => match AssertUnwindSafe(async { service.call(request).await })
            .catch_unwind()
            .await
        {
            Ok(Ok(response)) => response,
            Ok(Err(error)) => {
                send_stream.stop_stream(Code::H3_INTERNAL_ERROR);
                return Err(Http3RequestStreamError::Service(error));
            }
            Err(_) => {
                let error = io::Error::other("HTTP/3 application service panicked");
                observe_error(
                    error_observer.as_ref(),
                    ServerErrorPhase::Service,
                    Some(peer_addr),
                    &error,
                );
                tracing::error!(%error, "HTTP/3 application service panicked before response commitment");
                super::internal_server_error()
            }
        },
        Ok(Err(error)) => {
            send_stream.stop_stream(Code::H3_INTERNAL_ERROR);
            return Err(Http3RequestStreamError::Service(error));
        }
        Err(_) => {
            let error = io::Error::other("HTTP/3 application service readiness panicked");
            observe_error(
                error_observer.as_ref(),
                ServerErrorPhase::Readiness,
                Some(peer_addr),
                &error,
            );
            tracing::error!(%error, "HTTP/3 application service readiness panicked before response commitment");
            super::internal_server_error()
        }
    };
    let (mut parts, body) = response.into_parts();
    let mut body = Box::pin(body);
    parts.version = Version::HTTP_3;
    let send_result = async {
        send_http3_response_start::<S::Error>(send_stream, Response::from_parts(parts, ())).await?;

        loop {
            let frame = AssertUnwindSafe(body.frame())
                .catch_unwind()
                .await
                .map_err(|_| {
                    Http3RequestStreamError::Body(Box::new(io::Error::other(
                        "HTTP/3 application response body panicked",
                    )))
                })?;
            let Some(frame) = frame else {
                break;
            };
            let frame = frame.map_err(Http3RequestStreamError::Body)?;
            match frame.into_data() {
                Ok(data) => send_stream
                    .send_data(data)
                    .await
                    .map_err(Http3RequestStreamError::H3)?,
                Err(frame) => {
                    // `Frame` can contain only DATA or trailers. Since DATA
                    // extraction failed above, the remaining frame is trailers.
                    let trailers = frame.into_trailers().unwrap_or_default();
                    send_stream
                        .send_trailers(trailers)
                        .await
                        .map_err(Http3RequestStreamError::H3)?;
                }
            }
        }
        finish_http3_response::<S::Error>(send_stream).await
    }
    .await;

    if let Err(error) = &send_result {
        send_stream.stop_stream(Code::H3_INTERNAL_ERROR);
        observe_error(
            error_observer.as_ref(),
            ServerErrorPhase::Connection,
            Some(peer_addr),
            error,
        );
    }
    send_result
}

fn observe_connection_task(result: Option<Result<(), tokio::task::JoinError>>) {
    if let Some(Err(error)) = result {
        if !error.is_cancelled() {
            tracing::error!(%error, "HTTP/3 connection task failed");
        }
    }
}

fn observe_request_task(result: Result<(), tokio::task::JoinError>) {
    if let Err(error) = result {
        if !error.is_cancelled() {
            tracing::error!(%error, "HTTP/3 request task panicked");
        }
    }
}

async fn drain_connection_tasks(connections: &mut JoinSet<()>) {
    while let Some(result) = connections.join_next().await {
        observe_connection_task(Some(result));
    }
}

#[derive(Debug)]
enum Http3ConnectionError {
    Quic(quinn::ConnectionError),
    H3(h3::error::ConnectionError),
    AlpnNotH3,
}

impl fmt::Display for Http3ConnectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Quic(error) => write!(formatter, "QUIC handshake failed: {error}"),
            Self::H3(error) => write!(formatter, "HTTP/3 connection failed: {error}"),
            Self::AlpnNotH3 => formatter.write_str("QUIC connection did not negotiate h3 ALPN"),
        }
    }
}

impl Error for Http3ConnectionError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Quic(error) => Some(error),
            Self::H3(error) => Some(error),
            Self::AlpnNotH3 => None,
        }
    }
}

#[derive(Debug)]
enum Http3RequestStreamError<E> {
    H3(h3::error::StreamError),
    Body(super::BoxBodyError),
    Service(E),
    PeerStop(quinn::StoppedError),
    ObserverUnavailable(io::Error),
}

impl<E> fmt::Display for Http3RequestStreamError<E>
where
    E: Error + fmt::Display + 'static,
{
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::H3(error) => {
                let source = <Self as Error>::source(self).unwrap_or(error);
                write!(formatter, "HTTP/3 stream failed: {source}")
            }
            Self::Body(error) => {
                let source = <Self as Error>::source(self).unwrap_or(error.as_ref());
                write!(formatter, "response body failed: {source}")
            }
            Self::Service(error) => {
                let source = <Self as Error>::source(self).unwrap_or(error);
                write!(formatter, "HTTP/3 application service failed: {source}")
            }
            Self::PeerStop(error) => {
                write!(formatter, "HTTP/3 peer-stop observation failed: {error}")
            }
            Self::ObserverUnavailable(error) => error.fmt(formatter),
        }
    }
}

impl<E> Error for Http3RequestStreamError<E>
where
    E: Error + 'static,
{
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::H3(error) => Some(error),
            Self::Body(error) => Some(error.as_ref()),
            Self::Service(error) => Some(error),
            Self::PeerStop(error) => Some(error),
            Self::ObserverUnavailable(error) => Some(error),
        }
    }
}

async fn send_http3_response_start<E>(
    send_stream: &mut h3::server::RequestStream<transport::SendStream, Bytes>,
    response: Response<()>,
) -> Result<(), Http3RequestStreamError<E>> {
    send_stream
        .send_response(response)
        .await
        .map_err(Http3RequestStreamError::H3)
}

async fn finish_http3_response<E>(
    send_stream: &mut h3::server::RequestStream<transport::SendStream, Bytes>,
) -> Result<(), Http3RequestStreamError<E>> {
    #[cfg(coverage)]
    if crate::take_http3_response_fallback_finish_fault() {
        send_stream.stop_stream(Code::H3_REQUEST_CANCELLED);
    }
    send_stream
        .finish()
        .await
        .map_err(Http3RequestStreamError::H3)
}
