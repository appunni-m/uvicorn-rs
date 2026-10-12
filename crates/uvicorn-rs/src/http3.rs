//! HTTP/3 serving over a caller-configured Quinn endpoint.

use std::{
    error::Error,
    fmt,
    future::Future,
    io,
    panic::AssertUnwindSafe,
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
};

use bytes::{Buf, Bytes};
use futures_util::FutureExt;
use h3::error::Code;
use h3_quinn::quinn;
use http::{Request, Response, Version};
use http_body::{Body, Frame, SizeHint};
use http_body_util::BodyExt;
use pin_project_lite::pin_project;
use tokio::{
    sync::{watch, OwnedSemaphorePermit, Semaphore},
    task::JoinSet,
    time::Instant,
};
use tower_service::Service;

use crate::{
    observe_error, ConnectionInfo, ConnectionInfoService, ServeError, ServerConfig,
    ServerErrorObserver, ServerErrorPhase, ServiceErrorResponse, TlsInfo, TransportKind,
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
        stream: h3::server::RequestStream<h3_quinn::RecvStream, Bytes>,
        data_finished: bool,
        finished: bool,
    }
}

impl Http3RequestBody {
    fn new(stream: h3::server::RequestStream<h3_quinn::RecvStream, Bytes>) -> Self {
        Self {
            stream,
            data_finished: false,
            finished: false,
        }
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

        if !*this.data_finished {
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
                Poll::Ready(Ok(None)) => *this.data_finished = true,
            }
        }

        match this.stream.poll_recv_trailers(context) {
            Poll::Pending => {
                // `poll_recv_data` can return `None` at the end of an empty
                // DATA frame. While trailers are still pending, keep polling
                // the request body so a later DATA frame is not treated as a
                // trailer-sequence error.
                *this.data_finished = false;
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
        let (shutdown_sender, shutdown_receiver) = watch::channel(false);
        let mut shutdown = Box::pin(shutdown);
        let mut connections = JoinSet::new();
        let mut next_slot: Option<OwnedSemaphorePermit> = None;

        loop {
            tokio::select! {
                _ = &mut shutdown => break,
                joined = connections.join_next(), if !connections.is_empty() => {
                    observe_connection_task(joined);
                }
                slot = Arc::clone(&connection_slots).acquire_owned(), if next_slot.is_none() => {
                    next_slot = Some(slot.map_err(|_| ServeError::InvalidConnectionLimit)?);
                }
                incoming = endpoint.accept(), if next_slot.is_some() => {
                    let Some(incoming) = incoming else { break; };
                    let Some(slot) = next_slot.take() else { continue; };
                    let service = service.clone();
                    let shutdown = shutdown_receiver.clone();
                    let error_observer = config.error_observer.clone();
                    connections.spawn(async move {
                        let _slot = slot;
                        if let Err(error) = serve_incoming_connection(
                            incoming,
                            service,
                            shutdown,
                            error_observer.as_ref(),
                        ).await {
                            tracing::debug!(%error, "HTTP/3 connection finished with an error");
                        }
                    });
                }
            }
        }

        endpoint.set_server_config(None);
        shutdown_sender.send_replace(true);
        let shutdown_deadline = Instant::now()
            .checked_add(config.graceful_shutdown_timeout)
            .ok_or(ServeError::InvalidGracefulShutdownTimeout)?;
        while !connections.is_empty() {
            let remaining = shutdown_deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                connections.abort_all();
                drain_connection_tasks(&mut connections).await;
                endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown deadline");
                return Err(ServeError::GracefulShutdownTimedOut);
            }
            match tokio::time::timeout(remaining, connections.join_next()).await {
                Ok(Some(joined)) => observe_connection_task(Some(joined)),
                Ok(None) => break,
                Err(_) => {
                    connections.abort_all();
                    drain_connection_tasks(&mut connections).await;
                    endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown deadline");
                    return Err(ServeError::GracefulShutdownTimedOut);
                }
            }
        }

        endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown");
        if tokio::time::timeout(config.graceful_shutdown_timeout, endpoint.wait_idle())
            .await
            .is_err()
        {
            return Err(ServeError::GracefulShutdownTimedOut);
        }
        Ok(())
    })
    .await
}

async fn serve_incoming_connection<S, B>(
    incoming: quinn::Incoming,
    service: S,
    mut shutdown: watch::Receiver<bool>,
    error_observer: Option<&ServerErrorObserver>,
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
            observe_error(
                error_observer,
                ServerErrorPhase::Connection,
                Some(peer_addr),
                &error,
            );
            return Err(Http3ConnectionError::Quic(error));
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
        let error = io::Error::new(
            io::ErrorKind::InvalidData,
            "QUIC connection did not negotiate the h3 ALPN",
        );
        observe_error(
            error_observer,
            ServerErrorPhase::Connection,
            Some(peer_addr),
            &error,
        );
        return Err(Http3ConnectionError::AlpnNotH3);
    }

    let connection_info = ConnectionInfo {
        peer_addr,
        tls: Some(TlsInfo {
            alpn_protocol: alpn_protocol.map(Arc::<[u8]>::from),
        }),
        transport: TransportKind::Quic,
    };
    let result = serve_http3_connection(
        connection,
        service,
        connection_info,
        &mut shutdown,
        error_observer,
    )
    .await;
    if let Err(error) = &result {
        observe_error(
            error_observer,
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
    error_observer: Option<&ServerErrorObserver>,
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
    let created = h3::server::Connection::new(h3_quinn::Connection::new(connection.clone()))
        .await
        .map_err(Http3ConnectionError::H3)?;
    let info_service = ConnectionInfoService::<S, Http3RequestBody, B>::new(
        service,
        connection_info,
        connection_lifetime,
    );
    let application =
        ServiceErrorResponse::<_, crate::RequestLifetimeBody<B>, Http3RequestBody>::new(
            info_service,
            error_observer.cloned(),
            peer_addr,
        );
    let mut h3_connection = created;
    let mut requests = JoinSet::new();
    let mut connection_error = None;

    loop {
        if *shutdown.borrow() {
            h3_connection
                .shutdown(0)
                .await
                .map_err(Http3ConnectionError::H3)?;
            break;
        }

        tokio::select! {
            biased;
            changed = shutdown.changed() => {
                if changed.is_err() || *shutdown.borrow() {
                    h3_connection
                        .shutdown(0)
                        .await
                        .map_err(Http3ConnectionError::H3)?;
                    break;
                }
            }
            Some(result) = requests.join_next(), if !requests.is_empty() => {
                observe_request_task(result);
            }
            accepted = h3_connection.accept() => {
                match accepted {
                    Ok(Some(resolver)) => {
                        let application = application.clone();
                        let connection = connection.clone();
                        let error_observer = error_observer.cloned();
                        requests.spawn(async move {
                            tokio::select! {
                                result = handle_http3_request(
                                    resolver,
                                    application,
                                    peer_addr,
                                    error_observer,
                                ) => {
                                    if let Err(error) = result {
                                        tracing::debug!(%error, "HTTP/3 request stream failed");
                                    }
                                }
                                _ = connection.closed() => {}
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
    resolver: h3::server::RequestResolver<h3_quinn::Connection, Bytes>,
    mut service: ServiceErrorResponse<
        ConnectionInfoService<S, Http3RequestBody, B>,
        crate::RequestLifetimeBody<B>,
        Http3RequestBody,
    >,
    peer_addr: std::net::SocketAddr,
    error_observer: Option<ServerErrorObserver>,
) -> Result<(), Http3RequestStreamError>
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
    let request = request.map(|()| Http3RequestBody::new(receive_stream));

    futures_util::future::poll_fn(|context| service.poll_ready(context))
        .await
        .map_err(|never| match never {})?;
    let response = match AssertUnwindSafe(async { service.call(request).await })
        .catch_unwind()
        .await
    {
        Ok(Ok(response)) => response,
        Ok(Err(never)) => match never {},
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
    };
    let (mut parts, body) = response.into_parts();
    let mut body = Box::pin(body);
    parts.version = Version::HTTP_3;
    let send_result = async {
        send_stream
            .send_response(Response::from_parts(parts, ()))
            .await
            .map_err(Http3RequestStreamError::H3)?;

        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(Http3RequestStreamError::Body)?;
            match frame.into_data() {
                Ok(data) => send_stream
                    .send_data(data)
                    .await
                    .map_err(Http3RequestStreamError::H3)?,
                Err(frame) => match frame.into_trailers() {
                    Ok(trailers) => send_stream
                        .send_trailers(trailers)
                        .await
                        .map_err(Http3RequestStreamError::H3)?,
                    Err(_) => return Err(Http3RequestStreamError::UnsupportedBodyFrame),
                },
            }
        }
        send_stream
            .finish()
            .await
            .map_err(Http3RequestStreamError::H3)
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
enum Http3RequestStreamError {
    H3(h3::error::StreamError),
    Body(super::BoxBodyError),
    UnsupportedBodyFrame,
}

impl fmt::Display for Http3RequestStreamError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::H3(error) => write!(formatter, "HTTP/3 stream failed: {error}"),
            Self::Body(error) => write!(formatter, "response body failed: {error}"),
            Self::UnsupportedBodyFrame => {
                formatter.write_str("response body emitted a frame other than DATA or trailers")
            }
        }
    }
}

impl Error for Http3RequestStreamError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::H3(error) => Some(error),
            Self::Body(error) => Some(error.as_ref()),
            Self::UnsupportedBodyFrame => None,
        }
    }
}

impl From<Http3RequestStreamError> for io::Error {
    fn from(error: Http3RequestStreamError) -> Self {
        io::Error::other(error)
    }
}
