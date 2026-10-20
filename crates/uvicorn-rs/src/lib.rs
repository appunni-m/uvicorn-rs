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
//! [`RequestLifetime`] values in its [`http::Extensions`]. TCP requests also
//! receive [`PeerReadHalfClosed`] and [`PeerReadFailed`] to distinguish clean
//! raw socket EOF from a terminal read error. The connection handle ends when
//! its protocol driver ends. The request handle
//! identifies when the service or response-body path ends, including when
//! Hyper drops an HTTP/2 service future after a stream reset. A dropped service
//! future does not identify its cause; adapters must not interpret it as a peer reset
//! unless the protocol layer provides that evidence. HTTP/3 request-reset
//! notification remains limited by the current `h3` driver and is not
//! guaranteed while neither request body nor response is being polled.

#[cfg(coverage)]
use std::sync::atomic::{AtomicU8, Ordering};
use std::{
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
use http_body_util::{Either as BodyEither, Empty};
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
#[cfg(coverage)]
use tokio::sync::Notify;
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
type BoxedShutdownFuture<'a> = Pin<Box<dyn Future<Output = ()> + Send + 'a>>;

#[cfg(coverage)]
struct CoverageFaultIo<I> {
    inner: I,
    control_file: Option<std::path::PathBuf>,
    failed: bool,
}

#[cfg(coverage)]
impl<I> CoverageFaultIo<I> {
    fn new(inner: I) -> Self {
        Self {
            inner,
            control_file: std::env::var_os("UVICORN_RS_COVERAGE_FAULT_FILE")
                .map(std::path::PathBuf::from),
            failed: false,
        }
    }

    fn take_write_error_fault(&mut self) -> bool {
        let Some(path) = &self.control_file else {
            return false;
        };
        let armed = self.write_error_fault_is_armed();
        if armed {
            let _ = std::fs::write(path, "");
        }
        armed
    }

    fn write_error_fault_is_armed(&self) -> bool {
        const POINT: &str = "server.connection-io.poll-write-error";
        self.control_file.as_ref().is_some_and(|path| {
            std::fs::read_to_string(path)
                .map(|value| value.trim() == POINT)
                .unwrap_or(false)
        })
    }
}

#[cfg(coverage)]
impl<I: AsyncRead + Unpin> AsyncRead for CoverageFaultIo<I> {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut tokio::io::ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_read(context, buffer)
    }
}

#[cfg(coverage)]
impl<I: AsyncWrite + Unpin> AsyncWrite for CoverageFaultIo<I> {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        if this.failed {
            return Poll::Ready(Err(io::Error::other(
                "coverage-injected TCP connection write error",
            )));
        }
        if this.take_write_error_fault() {
            this.failed = true;
            // Re-poll once so this public fault contract also covers the
            // persistent-failure guard after the injected error is consumed.
            context.waker().wake_by_ref();
            return Poll::Pending;
        }
        Pin::new(&mut this.inner).poll_write(context, buffer)
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffers: &[io::IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        if this.failed || this.take_write_error_fault() {
            this.failed = true;
            return Poll::Ready(Err(io::Error::other(
                "coverage-injected TCP connection write error",
            )));
        }
        Pin::new(&mut this.inner).poll_write_vectored(context, buffers)
    }

    fn is_write_vectored(&self) -> bool {
        // The fault contract uses the scalar path so it can verify both
        // AsyncWrite entry points without changing production dispatch.
        if self.failed || self.write_error_fault_is_armed() {
            return false;
        }
        self.inner.is_write_vectored()
    }

    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(context)
    }

    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(context)
    }
}

/// Test-only HTTP/3 client that exercises the server crate's QUIC adapter.
///
/// This type is compiled only in coverage builds and is not part of the normal
/// crate API.
#[cfg(coverage)]
#[doc(hidden)]
pub struct CoverageHttp3Client {
    inner: http3::CoverageClient,
}

#[cfg(coverage)]
impl CoverageHttp3Client {
    /// Connects an established QUIC connection through the HTTP/3 adapter.
    pub async fn connect(
        connection: h3_quinn::quinn::Connection,
    ) -> Result<Self, Box<dyn Error + Send + Sync + 'static>> {
        Ok(Self {
            inner: http3::CoverageClient::connect(connection).await?,
        })
    }

    /// Sends one HTTP/3 request and collects its response for an adapter probe.
    pub async fn request(
        &mut self,
        request: Request<()>,
        body: Bytes,
        trailers: Option<http::HeaderMap>,
    ) -> Result<(StatusCode, Bytes, Option<http::HeaderMap>), Box<dyn Error + Send + Sync + 'static>>
    {
        self.inner.request(request, body, trailers).await
    }

    /// Stops the probe's HTTP/3 driver task.
    pub async fn close(self) {
        self.inner.close().await;
    }
}

/// Opens a bidirectional stream through the coverage-only adapter and returns
/// the peer's HTTP/3 application close code.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn coverage_http3_open_bidi_application_close_code(
    connection: h3_quinn::quinn::Connection,
) -> Result<u64, Box<dyn Error + Send + Sync + 'static>> {
    http3::coverage_open_bidi_application_close_code(connection).await
}

/// Observes the HTTP/3 adapter's client-close result while waiting for a
/// bidirectional request stream. This entry point is absent from normal builds.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn coverage_http3_accept_bidi_error(
    connection: h3_quinn::quinn::Connection,
) -> Result<h3::quic::StreamId, h3::quic::ConnectionErrorIncoming> {
    http3::coverage_accept_bidi_error(connection).await
}

/// Exercises the coverage-only client-side HTTP/3 stream adapter contract.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn coverage_http3_client_adapter_contract(
    connection: h3_quinn::quinn::Connection,
) -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    http3::coverage_exercise_client_adapter_methods(connection).await
}

/// Exercises HTTP/3 send-sequence errors and verifies the connection recovers.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn coverage_http3_finish_after_reset(
    connection: h3_quinn::quinn::Connection,
) -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    http3::coverage_finish_after_reset(connection).await
}

/// Collects a response body through the request-lifetime wrapper without a guard.
///
/// This coverage-build-only contract verifies the defensive missing-guard path;
/// normal server construction always transfers a guard to the response body.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn coverage_request_lifetime_body_missing_guard(body: Bytes) -> Bytes {
    use http_body_util::{BodyExt, Full};

    let body = RequestLifetimeBody::new(Full::new(body), None);
    match body.collect().await {
        Ok(collected) => collected.to_bytes(),
        Err(never) => match never {},
    }
}

/// Result of installing the proactive peer-read adapter for a coverage
/// contract. This type is absent from normal builds.
#[cfg(coverage)]
#[doc(hidden)]
pub struct CoveragePeerReadAdapter<I> {
    /// The peer-observed asynchronous socket I/O.
    pub io: I,
    /// Reports whether the peer closed its write half.
    pub observer: PeerReadHalfClosed,
    /// Reports a terminal raw socket read error, such as a peer reset.
    pub failed_observer: PeerReadFailed,
    /// Drives observation independently from application reads.
    pub pump: Option<Pin<Box<dyn Future<Output = ()> + Send>>>,
}

/// Observes a TCP stream with the proactive peer-read adapter for coverage
/// contracts. This function is absent from normal builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn coverage_proactive_peer_read(
    stream: tokio::net::TcpStream,
) -> CoveragePeerReadAdapter<impl AsyncRead + AsyncWrite + Unpin + Send> {
    let (io, observer, failed_observer, pump, _, _) =
        peer_read::observe_peer_read(stream, PeerReadHalfCloseMode::Proactive);
    let pump = pump.map(|pump| {
        Box::pin(async move {
            let _ = pump.await;
        }) as Pin<Box<dyn Future<Output = ()> + Send>>
    });
    CoveragePeerReadAdapter {
        io,
        observer,
        failed_observer,
        pump,
    }
}

/// Arms a coverage-only HTTP/3 peer stream-credit gate.
///
/// The instrumented server test configures the next connection with zero
/// initial bidirectional stream credit. The test then explicitly grants one
/// stream after observing backpressure. This hook is coverage-build-only.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_peer_bidi_stream_credit_gate() -> bool {
    HTTP3_PEER_BIDI_STREAM_CREDIT_GATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Returns whether the coverage-only peer stream-credit gate was installed.
#[cfg(coverage)]
#[doc(hidden)]
pub fn http3_peer_bidi_stream_credit_gate_installed() -> bool {
    HTTP3_PEER_BIDI_STREAM_CREDIT_GATE.load(Ordering::Acquire) >= 3
}

/// Releases the coverage-only HTTP/3 peer stream-credit gate.
#[cfg(coverage)]
#[doc(hidden)]
pub fn release_http3_peer_bidi_stream_credit_gate() -> bool {
    if HTTP3_PEER_BIDI_STREAM_CREDIT_GATE
        .compare_exchange(3, 4, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
    {
        HTTP3_PEER_BIDI_STREAM_CREDIT_RELEASE.notify_one();
        true
    } else {
        false
    }
}

/// Finishes the coverage-only peer stream-credit gate and reports whether it
/// granted credit to the peer.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn finish_http3_peer_bidi_stream_credit_gate() -> bool {
    let deadline = Instant::now() + Duration::from_secs(1);
    while HTTP3_PEER_BIDI_STREAM_CREDIT_GATE.load(Ordering::Acquire) == 4
        && Instant::now() < deadline
    {
        tokio::task::yield_now().await;
    }
    HTTP3_PEER_BIDI_STREAM_CREDIT_GATE.swap(0, Ordering::AcqRel) == 5
}

#[cfg(coverage)]
pub(crate) fn take_http3_peer_bidi_stream_credit_gate() -> bool {
    HTTP3_PEER_BIDI_STREAM_CREDIT_GATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
pub(crate) fn observe_http3_peer_bidi_stream_credit_gate_installed() {
    let _ = HTTP3_PEER_BIDI_STREAM_CREDIT_GATE.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

#[cfg(coverage)]
pub(crate) async fn wait_for_http3_peer_bidi_stream_credit_release() {
    HTTP3_PEER_BIDI_STREAM_CREDIT_RELEASE.notified().await;
}

#[cfg(coverage)]
pub(crate) fn observe_http3_peer_bidi_stream_credit_granted() {
    let _ = HTTP3_PEER_BIDI_STREAM_CREDIT_GATE.compare_exchange(
        4,
        5,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

#[cfg(coverage)]
mod coverage;
mod http3;
mod peer_read;
mod websocket;

#[cfg(coverage)]
#[doc(hidden)]
pub use coverage::{
    connection_error_source_variants as coverage_connection_error_source_variants,
    http1_on_read_peer_read as coverage_http1_on_read_peer_read,
    http1_response_activity_watch_outcomes as coverage_http1_response_activity_watch_outcomes,
};

#[cfg(coverage)]
static GRACEFUL_SHUTDOWN_DEADLINE_OVERFLOW_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static LISTENER_ACCEPT_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static LISTENER_ADMISSION_CLOSED_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP1_PEER_READ_RECEIVER_CLOSED_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP1_PEER_READ_FAILURE_AFTER_DATA_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_PEER_STOP_OBSERVER_UNAVAILABLE_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_INVALID_STREAM_ID_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_READ_CLOSED_STREAM_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_WRITE_CLOSED_STREAM_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_RESPONSE_SEND_DATA_FAULT_STAGE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_RESPONSE_SEND_DATA_FAULT_CALLS: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_SEND_DATA_PENDING_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_REQUEST_BODY_TRAILERS_PENDING_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_RESPONSE_FINISH_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_RESPONSE_FALLBACK_FINISH_FAULT: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_PEER_BIDI_STREAM_CREDIT_GATE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static HTTP3_PEER_BIDI_STREAM_CREDIT_RELEASE: Notify = Notify::const_new();

#[cfg(coverage)]
#[derive(Clone, Copy)]
pub(crate) enum Http3PeerStopObserverOutcomeFault {
    Error,
    LocalRetirement,
}

/// Arms the coverage-only HTTP/1 upgrade-receiver close fault.
///
/// The hook closes the per-connection upgrade receiver before its next poll,
/// allowing the connection supervisor's closed-channel path to be checked.
/// It is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http1_upgrade_receiver_closed_fault() -> bool {
    HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Returns whether the closed-channel branch was observed by the supervisor.
#[cfg(coverage)]
#[doc(hidden)]
pub fn http1_upgrade_receiver_closed_fault_consumed() -> bool {
    HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT.load(Ordering::Acquire) == 3
}

/// Finishes the coverage-only HTTP/1 upgrade-receiver close fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http1_upgrade_receiver_closed_fault() -> bool {
    HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT.swap(0, Ordering::AcqRel) == 3
}

#[cfg(coverage)]
fn take_http1_upgrade_receiver_closed_fault() -> bool {
    HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
fn observe_http1_upgrade_receiver_closed_fault() {
    let _ = HTTP1_UPGRADE_RECEIVER_CLOSED_FAULT.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

/// Arms the coverage-only HTTP/1 peer-read receiver-close fault.
///
/// The hook closes the private Proactive peer-read channel for the next
/// accepted connection. It is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http1_peer_read_receiver_closed_fault() -> bool {
    HTTP1_PEER_READ_RECEIVER_CLOSED_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/1 peer-read receiver-close fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http1_peer_read_receiver_closed_fault() -> bool {
    HTTP1_PEER_READ_RECEIVER_CLOSED_FAULT.swap(0, Ordering::AcqRel) == 3
}

#[cfg(coverage)]
fn take_http1_peer_read_receiver_closed_fault() -> bool {
    HTTP1_PEER_READ_RECEIVER_CLOSED_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
fn observe_http1_peer_read_receiver_closed_fault() {
    let _ = HTTP1_PEER_READ_RECEIVER_CLOSED_FAULT.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

/// Arms a coverage-only HTTP/1 peer-read failure after the pump has delivered
/// request bytes. The write half remains usable so a service can observe the
/// input error and start a response before the test releases its body.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http1_peer_read_failure_after_data_fault() -> bool {
    HTTP1_PEER_READ_FAILURE_AFTER_DATA_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only peer-read failure contract.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http1_peer_read_failure_after_data_fault() -> bool {
    HTTP1_PEER_READ_FAILURE_AFTER_DATA_FAULT.swap(0, Ordering::AcqRel) == 3
}

#[cfg(coverage)]
pub(crate) fn take_http1_peer_read_failure_after_data_fault() -> bool {
    HTTP1_PEER_READ_FAILURE_AFTER_DATA_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
pub(crate) fn observe_http1_peer_read_failure_after_data_fault() {
    let _ = HTTP1_PEER_READ_FAILURE_AFTER_DATA_FAULT.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

/// Arms a coverage-only HTTP/3 peer-stop observer fault.
///
/// The next accepted request stream omits its internal peer-stop observer.
/// This is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_peer_stop_observer_unavailable_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_UNAVAILABLE_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 peer-stop observer fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_peer_stop_observer_unavailable_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_UNAVAILABLE_FAULT.swap(0, Ordering::AcqRel) == 3
}

#[cfg(coverage)]
pub(crate) fn take_http3_peer_stop_observer_unavailable_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_UNAVAILABLE_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
pub(crate) fn observe_http3_peer_stop_observer_unavailable_fault() {
    let _ = HTTP3_PEER_STOP_OBSERVER_UNAVAILABLE_FAULT.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

/// Arms a coverage-only HTTP/3 peer-stop observer error.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_peer_stop_observer_error_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 peer-stop observer error.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_peer_stop_observer_error_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT.swap(0, Ordering::AcqRel) == 2
}

/// Arms a coverage-only HTTP/3 local send-retirement observer result.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_peer_stop_local_retirement_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT
        .compare_exchange(0, 4, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 local send-retirement observer result.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_peer_stop_local_retirement_fault() -> bool {
    HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT.swap(0, Ordering::AcqRel) == 5
}

#[cfg(coverage)]
pub(crate) fn take_http3_peer_stop_observer_outcome_fault(
) -> Option<Http3PeerStopObserverOutcomeFault> {
    if HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
    {
        Some(Http3PeerStopObserverOutcomeFault::Error)
    } else if HTTP3_PEER_STOP_OBSERVER_OUTCOME_FAULT
        .compare_exchange(4, 5, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
    {
        Some(Http3PeerStopObserverOutcomeFault::LocalRetirement)
    } else {
        None
    }
}

/// Arms a coverage-only fault for the next HTTP/3 client-adapter read.
///
/// The adapter receives Quinn's `ClosedStream` result at its normal read
/// boundary. This result cannot be selected by a valid peer request, so the
/// hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_read_closed_stream_fault() -> bool {
    HTTP3_READ_CLOSED_STREAM_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 client-adapter read fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_read_closed_stream_fault() -> bool {
    HTTP3_READ_CLOSED_STREAM_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_read_closed_stream_fault() -> bool {
    HTTP3_READ_CLOSED_STREAM_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms a coverage-only fault for the next HTTP/3 client-adapter write.
///
/// The adapter receives Quinn's `ClosedStream` result at its normal write
/// boundary. This result cannot be selected by a valid peer request, so the
/// hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_write_closed_stream_fault() -> bool {
    HTTP3_WRITE_CLOSED_STREAM_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 client-adapter write fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_write_closed_stream_fault() -> bool {
    HTTP3_WRITE_CLOSED_STREAM_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_write_closed_stream_fault() -> bool {
    HTTP3_WRITE_CLOSED_STREAM_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms a coverage-only error at a selected HTTP/3 response frame boundary.
///
/// Stage 1 is response headers, stage 2 is DATA, and stage 3 is trailers. The
/// fault returns a Quinn `ClosedStream` result from the server adapter's
/// normal send-data method. This hook is absent from normal builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_response_send_data_fault(stage: u8) -> bool {
    HTTP3_RESPONSE_SEND_DATA_FAULT_CALLS.store(0, Ordering::Release);
    HTTP3_RESPONSE_SEND_DATA_FAULT_STAGE
        .compare_exchange(0, stage, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Returns the consumed response-frame fault stage and clears the hook.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_response_send_data_fault() -> u8 {
    HTTP3_RESPONSE_SEND_DATA_FAULT_STAGE.swap(0, Ordering::AcqRel)
}

#[cfg(coverage)]
pub(crate) fn take_http3_response_send_data_fault() -> bool {
    let stage = HTTP3_RESPONSE_SEND_DATA_FAULT_STAGE.load(Ordering::Acquire);
    if stage == 0 {
        return false;
    }
    let call = HTTP3_RESPONSE_SEND_DATA_FAULT_CALLS
        .fetch_add(1, Ordering::AcqRel)
        .saturating_add(1);
    if call != stage {
        return false;
    }
    HTTP3_RESPONSE_SEND_DATA_FAULT_STAGE
        .compare_exchange(
            stage,
            stage.saturating_add(10),
            Ordering::AcqRel,
            Ordering::Acquire,
        )
        .is_ok()
}

/// Arms a coverage-only pending-write state before the next HTTP/3 DATA write.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_send_data_pending_fault() -> bool {
    HTTP3_SEND_DATA_PENDING_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only pending-write state fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_send_data_pending_fault() -> bool {
    HTTP3_SEND_DATA_PENDING_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_send_data_pending_fault() -> bool {
    HTTP3_SEND_DATA_PENDING_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms one synthetic pending result while polling HTTP/3 request trailers.
///
/// The current H3 stream API does not expose a state where request data has
/// ended but trailers are not ready. This coverage-only scheduling seam checks
/// that the body adapter remains pending and resumes without changing the
/// externally observed request body or response.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_request_body_trailers_pending_fault() -> bool {
    HTTP3_REQUEST_BODY_TRAILERS_PENDING_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the one-shot HTTP/3 request-trailer pending-state contract.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_request_body_trailers_pending_fault() -> bool {
    HTTP3_REQUEST_BODY_TRAILERS_PENDING_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_request_body_trailers_pending_fault() -> bool {
    HTTP3_REQUEST_BODY_TRAILERS_PENDING_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms an out-of-range stream ID at the next accepted HTTP/3 server stream.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_invalid_stream_id_fault() -> bool {
    HTTP3_INVALID_STREAM_ID_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only invalid stream ID fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_invalid_stream_id_fault() -> bool {
    HTTP3_INVALID_STREAM_ID_FAULT.swap(0, Ordering::AcqRel) == 3
}

#[cfg(coverage)]
pub(crate) fn take_http3_invalid_stream_id_fault() -> bool {
    HTTP3_INVALID_STREAM_ID_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
pub(crate) fn observe_http3_invalid_stream_id_fault() {
    let _ =
        HTTP3_INVALID_STREAM_ID_FAULT.compare_exchange(2, 3, Ordering::AcqRel, Ordering::Acquire);
}

/// Arms a coverage-only error when finishing the next HTTP/3 response.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_response_finish_fault() -> bool {
    HTTP3_RESPONSE_FINISH_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only HTTP/3 response finish fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_response_finish_fault() -> bool {
    HTTP3_RESPONSE_FINISH_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_response_finish_fault() -> bool {
    HTTP3_RESPONSE_FINISH_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms a coverage-only reset immediately before finishing the observer fallback response.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_http3_response_fallback_finish_fault() -> bool {
    HTTP3_RESPONSE_FALLBACK_FINISH_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only observer fallback response fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_http3_response_fallback_finish_fault() -> bool {
    HTTP3_RESPONSE_FALLBACK_FINISH_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
pub(crate) fn take_http3_response_fallback_finish_fault() -> bool {
    HTTP3_RESPONSE_FALLBACK_FINISH_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms the coverage-only TCP listener accept fault.
///
/// This hook is compiled only for instrumented coverage builds and is absent
/// from normal library builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_listener_accept_fault() -> bool {
    LISTENER_ACCEPT_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only TCP listener accept fault.
///
/// Returns whether the armed fault reached the public server error path. This
/// hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_listener_accept_fault() -> bool {
    LISTENER_ACCEPT_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_listener_accept_fault() -> bool {
    LISTENER_ACCEPT_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
fn take_tcp_nodelay_set_error_fault() -> bool {
    // Release evidence scans this registry and rejects the hook in normal wheels.
    const POINT: &str = "server.tcp-nodelay.set-error";

    let Some(path) = std::env::var_os("UVICORN_RS_COVERAGE_FAULT_FILE") else {
        return false;
    };
    let armed = std::fs::read_to_string(&path)
        .map(|value| value.trim() == POINT)
        .unwrap_or(false);
    if armed {
        let _ = std::fs::write(path, "");
    }
    armed
}

/// Arms the coverage-only connection-admission close fault.
///
/// This hook is compiled only for instrumented coverage builds and is absent
/// from normal library builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_listener_admission_closed_fault() -> bool {
    LISTENER_ADMISSION_CLOSED_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only connection-admission close fault.
///
/// Returns whether the armed fault reached the public server error path. This
/// hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_listener_admission_closed_fault() -> bool {
    LISTENER_ADMISSION_CLOSED_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_listener_admission_closed_fault() -> bool {
    LISTENER_ADMISSION_CLOSED_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms the coverage-only graceful-shutdown deadline overflow fault.
///
/// This hook is compiled only for instrumented coverage builds and is absent
/// from normal library builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_graceful_shutdown_deadline_overflow_fault() -> bool {
    GRACEFUL_SHUTDOWN_DEADLINE_OVERFLOW_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only graceful-shutdown deadline overflow fault.
///
/// Returns whether the armed fault reached the public server error path. This
/// hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_graceful_shutdown_deadline_overflow_fault() -> bool {
    GRACEFUL_SHUTDOWN_DEADLINE_OVERFLOW_FAULT.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_graceful_shutdown_deadline_overflow_fault() -> bool {
    GRACEFUL_SHUTDOWN_DEADLINE_OVERFLOW_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

pub use http3::{serve_http3, Http3RequestBody};
#[cfg(coverage)]
#[doc(hidden)]
pub use websocket::{
    arm_close_reply_flush_cancellation_fault, arm_close_reply_flush_fault,
    arm_derived_accept_key_header_value_fault, finish_close_reply_flush_cancellation_fault,
    finish_close_reply_flush_fault, finish_derived_accept_key_header_value_fault,
    wait_for_close_reply_flush_cancellation_fault,
};
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

/// How the server handles errors returned by an application service before
/// response commitment.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum ServiceErrorPolicy {
    /// Return an empty HTTP 500 response. This is the default policy.
    #[default]
    RespondInternalServerError,
    /// Forward the original typed service or readiness error to the transport.
    /// HTTP/1 ends the connection; HTTP/2 resets the affected stream.
    /// HTTP/3 resets only the affected stream with `H3_INTERNAL_ERROR` before
    /// sending response headers.
    Propagate,
}

/// How TCP connections observe the peer closing its write side.
///
/// All modes report only a real raw socket EOF. They preserve input bytes,
/// request-body errors, and the server's ability to finish its response.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum PeerReadHalfCloseMode {
    /// Observe EOF when the HTTP or TLS driver reads the socket.
    ///
    /// This default adds no read-ahead queue. An HTTP/1 service or response
    /// that is waiting can delay observation until the driver reads again.
    #[default]
    OnRead,
    /// Keep direct HTTP/TLS reads while observing peer EOF with a non-consuming
    /// peek on a duplicated socket handle.
    ///
    /// The monitor waits for the HTTP/TLS reader to consume any available
    /// bytes before peeking again, so it does not copy or queue request data.
    /// It can observe EOF while an HTTP/1 service or response is waiting once
    /// no unread bytes remain in the socket. Duplicating the socket handle and
    /// driving the monitor adds per-connection setup and scheduling cost.
    ConcurrentPeek,
    /// Read ahead within the connection task to observe EOF while an HTTP/1
    /// service or response is waiting.
    ///
    /// A sole raw socket reader feeds HTTP or TLS through a bounded queue.
    /// It adds one input copy and holds at most two queued 16 KiB chunks plus
    /// one chunk being consumed. No separate task is spawned. A full queue
    /// pauses socket reads, so unread input can still delay EOF observation.
    /// This mode is opt-in because of its buffering and scheduling cost.
    Proactive,
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
    ///
    /// Must be in the inclusive range `1..=tokio::sync::Semaphore::MAX_PERMITS`.
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
    /// Controls whether pre-response service errors become empty HTTP 500
    /// responses or propagate to the transport. Defaults to
    /// [`ServiceErrorPolicy::RespondInternalServerError`].
    pub service_error_policy: ServiceErrorPolicy,
    /// Controls how TCP connections observe peer read-half closure. Defaults
    /// to [`PeerReadHalfCloseMode::OnRead`]. Ignored for QUIC connections.
    pub peer_read_half_close: PeerReadHalfCloseMode,
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
            .field("service_error_policy", &self.service_error_policy)
            .field("peer_read_half_close", &self.peer_read_half_close)
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

/// A connection-scoped signal for peer TCP read-half closure.
///
/// The signal is inserted into requests served over TCP, including TLS over
/// TCP. It becomes true only when TCP reports that the peer's write side has
/// reached EOF. A TLS `close_notify` alone does not set it.
///
/// [`PeerReadHalfCloseMode::OnRead`], the default, observes EOF only when the
/// HTTP or TLS driver reads, which can wait until an HTTP/1 service or response
/// completes. [`PeerReadHalfCloseMode::ConcurrentPeek`] keeps that direct data
/// path and peeks through a duplicated socket handle, waiting for the driver to
/// consume unread bytes before checking again. [`PeerReadHalfCloseMode::Proactive`]
/// uses a sole raw reader in the connection task and a bounded input queue, so
/// it can observe EOF while that service or response is waiting. A full queue
/// still delays observation until the driver consumes input. No mode discards
/// unread bytes or turns an incomplete request body into a complete body.
///
/// This connection fact does not cancel a request, close the response writer,
/// or represent an ASGI disconnect event.
#[derive(Clone, Debug)]
pub struct PeerReadHalfClosed {
    closed: watch::Receiver<bool>,
    mode: PeerReadHalfCloseMode,
}

impl PeerReadHalfClosed {
    /// Returns how this connection observes raw socket EOF.
    #[must_use]
    pub const fn mode(&self) -> PeerReadHalfCloseMode {
        self.mode
    }

    /// Returns whether raw TCP EOF has been observed for this connection.
    #[must_use]
    pub fn is_read_half_closed(&self) -> bool {
        *self.closed.borrow()
    }

    /// Waits until raw TCP EOF is observed for this connection.
    ///
    /// # Errors
    ///
    /// Returns [`PeerReadHalfClosedUnavailable`] if the connection's reader
    /// ends before the server observes EOF. Reader termination alone does not
    /// confirm peer EOF.
    pub async fn wait_until_read_half_closed(
        &mut self,
    ) -> Result<(), PeerReadHalfClosedUnavailable> {
        loop {
            if *self.closed.borrow_and_update() {
                return Ok(());
            }
            self.closed
                .changed()
                .await
                .map_err(|_| PeerReadHalfClosedUnavailable)?;
        }
    }
}

/// The server stopped observing a peer read-half closure before it observed EOF.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PeerReadHalfClosedUnavailable;

impl fmt::Display for PeerReadHalfClosedUnavailable {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("peer read-half closure observation ended without EOF")
    }
}

impl Error for PeerReadHalfClosedUnavailable {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        None
    }
}

/// A TCP connection-scoped signal that the raw socket reader encountered an
/// I/O error, such as a peer reset. Requests served over TCP, including TLS
/// over TCP, receive this signal. It remains distinct from clean TCP EOF.
#[derive(Clone, Debug)]
pub struct PeerReadFailed {
    failed: watch::Receiver<Option<io::ErrorKind>>,
}

impl PeerReadFailed {
    /// Returns the raw socket read error kind when one has been observed.
    #[must_use]
    pub fn error_kind(&self) -> Option<io::ErrorKind> {
        *self.failed.borrow()
    }

    /// Waits until the raw socket reader observes an I/O error.
    ///
    /// # Errors
    ///
    /// Returns [`PeerReadFailedUnavailable`] if the reader ends without
    /// observing a read error.
    pub async fn wait_until_failed(&mut self) -> Result<io::ErrorKind, PeerReadFailedUnavailable> {
        loop {
            if let Some(kind) = *self.failed.borrow_and_update() {
                return Ok(kind);
            }
            self.failed
                .changed()
                .await
                .map_err(|_| PeerReadFailedUnavailable)?;
        }
    }
}

/// The server stopped observing a peer read error before one was observed.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PeerReadFailedUnavailable;

impl fmt::Display for PeerReadFailedUnavailable {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("peer read-error observation ended without a read error")
    }
}

impl Error for PeerReadFailedUnavailable {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        None
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
        let _ = self.closed.wait_for(|closed| *closed).await;
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
        self.ended
            .wait_for(Option::is_some)
            .await
            .ok()
            .and_then(|reason| *reason)
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
    response_body_activity: Option<watch::Sender<usize>>,
    drop_reason: RequestEndReason,
    response_body_active: bool,
    finished: bool,
}

impl RequestLifetimeGuard {
    fn new(response_body_activity: Option<watch::Sender<usize>>) -> (RequestLifetime, Self) {
        let (ended, receiver) = watch::channel(None);
        (
            RequestLifetime { ended: receiver },
            Self {
                ended,
                response_body_activity,
                drop_reason: RequestEndReason::ServiceFutureDropped,
                response_body_active: false,
                finished: false,
            },
        )
    }

    fn response_body_started(&mut self) {
        if !self.finished && !self.response_body_active {
            self.response_body_active = true;
            if let Some(response_body_activity) = &self.response_body_activity {
                response_body_activity.send_modify(|active| *active = active.saturating_add(1));
            }
        }
    }

    fn finish(&mut self, reason: RequestEndReason) {
        if !self.finished {
            self.finished = true;
            if self.response_body_active {
                self.response_body_active = false;
                if let Some(response_body_activity) = &self.response_body_activity {
                    response_body_activity.send_modify(|active| *active = active.saturating_sub(1));
                }
            }
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
        if matches!(
            &frame,
            Poll::Ready(Some(Ok(frame)))
                if frame.data_ref().is_some_and(|data| !data.is_empty())
                    || frame.trailers_ref().is_some()
        ) {
            if let Some(guard) = this.guard.as_mut() {
                guard.response_body_started();
            }
        }
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
            service_error_policy: ServiceErrorPolicy::default(),
            peer_read_half_close: PeerReadHalfCloseMode::default(),
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
    /// The configured connection limit exceeded Tokio's maximum permit count.
    ConnectionLimitTooLarge,
    /// The internal connection-admission semaphore closed while serving.
    ConnectionAdmissionClosed(tokio::sync::AcquireError),
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
            Self::ConnectionLimitTooLarge => {
                formatter.write_str("max_connections exceeds the runtime's maximum permit count")
            }
            Self::ConnectionAdmissionClosed(error) => {
                write!(formatter, "connection admission closed: {error}")
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
            Self::ConnectionAdmissionClosed(error) => Some(error),
            Self::ApplicationLifecycleFailed { error, .. } => Some(error.as_ref()),
            Self::ServerAndApplicationShutdown { server, .. } => Some(server.as_ref()),
            Self::InvalidConnectionLimit
            | Self::ConnectionLimitTooLarge
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
    if config.max_connections > Semaphore::MAX_PERMITS {
        return Err(ServeError::ConnectionLimitTooLarge);
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

fn graceful_shutdown_deadline(timeout: Duration) -> Result<Instant, ServeError> {
    let deadline = Instant::now().checked_add(timeout);
    #[cfg(coverage)]
    let deadline = if take_graceful_shutdown_deadline_overflow_fault() {
        None
    } else {
        deadline
    };
    deadline.ok_or(ServeError::InvalidGracefulShutdownTimeout)
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
/// [`ServeError::ConnectionLimitTooLarge`] when the limit exceeds Tokio's
/// maximum semaphore permit count,
/// [`ServeError::ConnectionAdmissionClosed`] if the internal admission
/// semaphore closes while the server is running,
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
    Shutdown: Future<Output = ()> + Send,
{
    let shutdown: BoxedShutdownFuture<'_> = Box::pin(shutdown);
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
    Shutdown: Future<Output = ()> + Send,
{
    let shutdown: BoxedShutdownFuture<'_> = Box::pin(shutdown);
    run_with_application_lifecycle(
        config.clone(),
        serve_listener(listener, service, shutdown, config, Some(acceptor)),
    )
    .await
}

async fn serve_listener<S, B>(
    listener: TcpListener,
    service: S,
    shutdown: BoxedShutdownFuture<'_>,
    config: ServerConfig,
    tls_acceptor: Option<TlsAcceptor>,
) -> Result<(), ServeError>
where
    S: Service<Request<Incoming>, Response = Response<B>> + Clone + Send + 'static,
    S::Future: Send + 'static,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    let connection_slots = Arc::new(Semaphore::new(config.max_connections));
    #[cfg(coverage)]
    if take_listener_admission_closed_fault() {
        connection_slots.close();
    }
    let (shutdown_sender, shutdown_receiver) = watch::channel(false);
    let mut shutdown = shutdown;
    let mut connections = JoinSet::new();

    loop {
        let ListenerEvent::Accepted { stream, peer, slot } = next_listener_event(
            &listener,
            &connection_slots,
            &mut connections,
            &mut shutdown,
        )
        .await?
        else {
            break;
        };

        // Match asyncio's accepted-socket default. Small HTTP/2 writes can
        // otherwise wait on Nagle and delayed acknowledgements.
        #[cfg(coverage)]
        let nodelay_result = if take_tcp_nodelay_set_error_fault() {
            Err(io::Error::other(
                "coverage-injected TCP_NODELAY configuration failure",
            ))
        } else {
            stream.set_nodelay(true)
        };
        #[cfg(not(coverage))]
        let nodelay_result = stream.set_nodelay(true);

        if let Err(error) = nodelay_result {
            observe_error(
                config.error_observer.as_ref(),
                ServerErrorPhase::Connection,
                Some(peer),
                &error,
            );
            tracing::debug!(%peer, %error, "failed to enable TCP_NODELAY on accepted connection");
            continue;
        }

        let (
            stream,
            peer_read_half_closed,
            peer_read_failed,
            read_pump,
            prioritize_receiver_close_fault,
            peer_read_diagnostics,
        ) = peer_read::observe_peer_read(stream, config.peer_read_half_close);
        let (response_body_activity, mut response_body_activity_receiver) = watch::channel(0usize);

        let service = service.clone();
        let shutdown = shutdown_receiver.clone();
        let error_observer = config.error_observer.clone();
        let service_error_policy = config.service_error_policy;
        let tls_acceptor = tls_acceptor.clone();
        connections.spawn(async move {
            let _slot = slot;
            let connection = async {
                match tls_acceptor {
                    Some(acceptor) => match acceptor.accept(stream).await {
                        Ok(stream) => {
                            let alpn_protocol =
                                stream.get_ref().1.alpn_protocol().map(Arc::<[u8]>::from);
                            serve_connection(
                                stream,
                                service,
                                ConnectionInfo {
                                    peer_addr: peer,
                                    tls: Some(TlsInfo { alpn_protocol }),
                                    transport: TransportKind::Tcp,
                                },
                                ConnectionSignals {
                                    peer_read_half_closed: peer_read_half_closed.clone(),
                                    peer_read_failed: peer_read_failed.clone(),
                                    response_body_activity: response_body_activity.clone(),
                                },
                                shutdown,
                                error_observer.as_ref(),
                                service_error_policy,
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
                            ConnectionSignals {
                                peer_read_half_closed,
                                peer_read_failed,
                                response_body_activity: response_body_activity.clone(),
                            },
                            shutdown,
                            error_observer.as_ref(),
                            service_error_policy,
                        )
                        .await
                    }
                }
            };
            let result = if let Some(read_pump) = read_pump {
                // The pump owns the only raw socket reader. Keeping both
                // futures in this task covers TLS and registered upgrades,
                // and makes cancellation drop the reader synchronously.
                tokio::pin!(connection);
                tokio::pin!(read_pump);
                if prioritize_receiver_close_fault {
                    // In the coverage-only receiver-close contract, poll the
                    // pump first so its real `Sender::reserve` error is
                    // observed before Hyper sees the closed input channel.
                    read_pump.await;
                    connection.await
                } else {
                    tokio::select! {
                        result = &mut connection => result,
                        outcome = &mut read_pump => match outcome {
                            peer_read::PeerReadPumpOutcome::ReceiverClosed
                            | peer_read::PeerReadPumpOutcome::ReadHalfClosed => connection.await,
                            peer_read::PeerReadPumpOutcome::ReadFailed(kind) => {
                                wait_for_connection_or_response_after_peer_read_error(
                                    connection.as_mut(),
                                    &mut response_body_activity_receiver,
                                    kind,
                                )
                                .await
                            }
                        },
                    }
                }
            } else {
                connection.await
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
            drop(peer_read_diagnostics);
            result
        });
    }

    // Stop admitting connections before the graceful drain starts. Keeping
    // the bound socket alive here would let new clients enter while existing
    // connections are being drained.
    drop(listener);
    shutdown_sender.send_replace(true);
    let shutdown_deadline = graceful_shutdown_deadline(config.graceful_shutdown_timeout)?;
    let shutdown_deadline = tokio::time::sleep_until(shutdown_deadline);
    tokio::pin!(shutdown_deadline);
    loop {
        tokio::select! {
            biased;
            // Keep the original deadline strict, while letting an empty
            // set finish through `join_next()` even after the deadline.
            _ = &mut shutdown_deadline, if !connections.is_empty() => {
                connections.abort_all();
                drain_aborted_connections(&mut connections).await;
                return Err(ServeError::GracefulShutdownTimedOut);
            }
            joined = connections.join_next() => match joined {
                Some(joined) => observe_connection(joined),
                None => break,
            },
        }
    }

    Ok(())
}

enum ListenerEvent {
    Shutdown,
    Accepted {
        stream: tokio::net::TcpStream,
        peer: SocketAddr,
        slot: OwnedSemaphorePermit,
    },
}

async fn next_listener_event(
    listener: &TcpListener,
    connection_slots: &Arc<Semaphore>,
    connections: &mut JoinSet<Result<(), ConnectionError>>,
    shutdown: &mut BoxedShutdownFuture<'_>,
) -> Result<ListenerEvent, ServeError> {
    loop {
        let slot = tokio::select! {
            _ = shutdown.as_mut() => return Ok(ListenerEvent::Shutdown),
            joined = connections.join_next(), if !connections.is_empty() => {
                joined.into_iter().for_each(observe_connection);
                continue;
            }
            slot = Arc::clone(connection_slots).acquire_owned() => {
                slot.map_err(ServeError::ConnectionAdmissionClosed)?
            }
        };

        loop {
            tokio::select! {
                _ = shutdown.as_mut() => return Ok(ListenerEvent::Shutdown),
                joined = connections.join_next(), if !connections.is_empty() => {
                    joined.into_iter().for_each(observe_connection);
                }
                accepted = async {
                    #[cfg(coverage)]
                    if take_listener_accept_fault() {
                        return Err(io::Error::other("injected TCP listener accept failure"));
                    }
                    listener.accept().await
                } => {
                    let (stream, peer) = accepted.map_err(ServeError::Accept)?;
                    return Ok(ListenerEvent::Accepted { stream, peer, slot });
                }
            }
        }
    }
}

async fn wait_for_connection_or_response_after_peer_read_error<F>(
    mut connection: Pin<&mut F>,
    response_body_activity: &mut watch::Receiver<usize>,
    error_kind: io::ErrorKind,
) -> Result<(), ConnectionError>
where
    F: Future<Output = Result<(), ConnectionError>>,
{
    loop {
        if *response_body_activity.borrow_and_update() > 0 {
            // Let Hyper consume a reset while the service is still reading
            // the request body. Once it has returned a response, drop Hyper
            // so a pending response body also drops and cancels its app task.
            return Err(ConnectionError::PeerRead(error_kind));
        }
        tokio::select! {
            biased;
            result = connection.as_mut() => return result,
            changed = response_body_activity.changed() => {
                if changed.is_err() {
                    return connection.await;
                }
            }
        }
    }
}

#[derive(Clone)]
struct ConnectionSignals {
    peer_read_half_closed: PeerReadHalfClosed,
    peer_read_failed: PeerReadFailed,
    response_body_activity: watch::Sender<usize>,
}

async fn serve_connection<I, S, B>(
    stream: I,
    service: S,
    connection_info: ConnectionInfo,
    signals: ConnectionSignals,
    mut shutdown: watch::Receiver<bool>,
    error_observer: Option<&ServerErrorObserver>,
    service_error_policy: ServiceErrorPolicy,
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
    let ConnectionSignals {
        peer_read_half_closed,
        peer_read_failed,
        response_body_activity,
    } = signals;
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
            Some(peer_read_half_closed),
            Some(peer_read_failed),
            Some(response_body_activity),
        ),
        error_observer.cloned(),
        peer_addr,
        service_error_policy,
    );
    let service = TowerToHyperService::new(application);
    #[cfg(coverage)]
    let stream = CoverageFaultIo::new(stream);
    let connection = builder.serve_connection_with_upgrades(TokioIo::new(stream), service);
    tokio::pin!(connection);

    let mut connection_result = None;
    let mut upgrade_sessions = JoinSet::new();
    let mut upgrade_receiver_open = true;
    let mut shutdown_started = false;
    let mut upgrade_error = None;

    #[cfg(coverage)]
    if take_http1_upgrade_receiver_closed_fault() {
        upgrade_receiver.close();
    }

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
                None => {
                    #[cfg(coverage)]
                    observe_http1_upgrade_receiver_closed_fault();
                    upgrade_receiver_open = false;
                }
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
    peer_read_half_closed: Option<PeerReadHalfClosed>,
    peer_read_failed: Option<PeerReadFailed>,
    response_body_activity: Option<watch::Sender<usize>>,
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
            peer_read_half_closed: self.peer_read_half_closed.clone(),
            peer_read_failed: self.peer_read_failed.clone(),
            response_body_activity: self.response_body_activity.clone(),
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
        peer_read_half_closed: Option<PeerReadHalfClosed>,
        peer_read_failed: Option<PeerReadFailed>,
        response_body_activity: Option<watch::Sender<usize>>,
    ) -> Self {
        Self {
            inner,
            connection_info,
            connection_lifetime,
            connection_upgrade,
            peer_read_half_closed,
            peer_read_failed,
            response_body_activity,
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
        if let Some(peer_read_half_closed) = &self.peer_read_half_closed {
            request
                .extensions_mut()
                .insert(peer_read_half_closed.clone());
        }
        if let Some(peer_read_failed) = &self.peer_read_failed {
            request.extensions_mut().insert(peer_read_failed.clone());
        }
        let request_version = request.version();
        insert_http1_upgrade_extension(
            request.extensions_mut(),
            request_version,
            self.connection_upgrade.as_ref(),
        );
        let (request_lifetime, guard) =
            RequestLifetimeGuard::new(self.response_body_activity.clone());
        request.extensions_mut().insert(request_lifetime);
        RequestLifetimeFuture::new(self.inner.call(request), guard)
    }
}

fn insert_http1_upgrade_extension(
    extensions: &mut http::Extensions,
    request_version: http::Version,
    connection_upgrade: Option<&ConnectionUpgrade>,
) {
    if let (http::Version::HTTP_11, Some(connection_upgrade)) =
        (request_version, connection_upgrade)
    {
        extensions.insert(connection_upgrade.clone());
    }
}

#[derive(Debug)]
enum ConnectionError {
    Http(Box<dyn Error + Send + Sync>),
    Upgrade(BoxBodyError),
    Tls(io::Error),
    PeerRead(io::ErrorKind),
}

impl Error for ConnectionError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Http(error) => Some(error.as_ref()),
            Self::Upgrade(error) => Some(error.as_ref()),
            Self::Tls(error) => Some(error),
            Self::PeerRead(_) => None,
        }
    }
}

impl fmt::Display for ConnectionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Http(error) => write!(formatter, "HTTP connection failed: {error}"),
            Self::Upgrade(error) => write!(formatter, "upgraded session failed: {error}"),
            Self::Tls(error) => write!(formatter, "TLS handshake failed: {error}"),
            Self::PeerRead(kind) => write!(formatter, "TCP peer read failed: {kind}"),
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
    service_error_policy: ServiceErrorPolicy,
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
            service_error_policy: self.service_error_policy,
            _response_body: std::marker::PhantomData,
            _request_body: std::marker::PhantomData,
        }
    }
}

impl<S, B, RequestBody> ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>>,
{
    fn new(
        inner: S,
        error_observer: Option<ServerErrorObserver>,
        peer_addr: SocketAddr,
        service_error_policy: ServiceErrorPolicy,
    ) -> Self {
        Self {
            inner,
            readiness_error: None,
            error_observer,
            peer_addr,
            service_error_policy,
            _response_body: std::marker::PhantomData,
            _request_body: std::marker::PhantomData,
        }
    }
}

// Nested sum types keep these body paths statically dispatched without a
// heap allocation for observed application bodies or internal empty replies.
type ServerResponseBody<B> = BodyEither<BodyEither<B, ObservedBody<B>>, Empty<Bytes>>;
type ResponseOnError<B> = Response<ServerResponseBody<B>>;
type ServiceResponseFuture<S, B, RequestBody> = FutureEither<
    ObserveServiceResult<
        <S as Service<Request<RequestBody>>>::Future,
        <S as Service<Request<RequestBody>>>::Error,
        B,
    >,
    Ready<Result<ResponseOnError<B>, <S as Service<Request<RequestBody>>>::Error>>,
>;

impl<S, B, RequestBody> Service<Request<RequestBody>> for ServiceErrorResponse<S, B, RequestBody>
where
    S: Service<Request<RequestBody>, Response = Response<B>> + Clone,
    S::Error: Error + fmt::Display + Send + Sync + 'static,
    B: Body<Data = Bytes> + Send + 'static,
    B::Error: Into<BoxBodyError> + Send + Sync + 'static,
{
    type Response = ResponseOnError<B>;
    type Error = S::Error;
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
                if self.service_error_policy == ServiceErrorPolicy::Propagate {
                    Poll::Ready(Err(error))
                } else {
                    self.readiness_error = Some(error);
                    Poll::Ready(Ok(()))
                }
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
            self.service_error_policy,
        ))
    }
}

pin_project! {
    struct ObserveServiceResult<F, E, B> {
        #[pin]
        future: F,
        error_observer: Option<ServerErrorObserver>,
        peer_addr: SocketAddr,
        service_error_policy: ServiceErrorPolicy,
        _types: std::marker::PhantomData<fn() -> (E, B)>,
    }
}

impl<F, E, B> ObserveServiceResult<F, E, B> {
    fn new(
        future: F,
        error_observer: Option<ServerErrorObserver>,
        peer_addr: SocketAddr,
        service_error_policy: ServiceErrorPolicy,
    ) -> Self {
        Self {
            future,
            error_observer,
            peer_addr,
            service_error_policy,
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
    type Output = Result<ResponseOnError<B>, E>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.project();
        match this.future.poll(context) {
            Poll::Pending => Poll::Pending,
            Poll::Ready(Ok(response)) => {
                let response = response.map(|body| match this.error_observer.take() {
                    Some(observer) => BodyEither::Left(BodyEither::Right(ObservedBody::new(
                        body,
                        observer,
                        *this.peer_addr,
                    ))),
                    None => BodyEither::Left(BodyEither::Left(body)),
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
                if *this.service_error_policy == ServiceErrorPolicy::Propagate {
                    tracing::error!(%error, "HTTP application service failed before response commitment; propagating error");
                    Poll::Ready(Err(error))
                } else {
                    tracing::error!(%error, "HTTP application service failed before response commitment");
                    Poll::Ready(Ok(internal_server_error()))
                }
            }
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
    let mut response = Response::new(BodyEither::Right(Empty::new()));
    *response.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
    response
}
