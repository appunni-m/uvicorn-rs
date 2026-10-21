#![deny(missing_docs)]

//! Rust network runtime behind the Python `uvicorn_rs` package.
//!
//! Tokio, Hyper, Quinn, and `h3` own sockets, protocol state, framing, and
//! transport backpressure. ASGI callables remain on the Python event loop that
//! starts the native `serve` entry point; PyO3 schedules calls onto that loop and returns results to
//! Rust without running application code on Tokio workers.
//!
//! # Payload ownership
//!
//! Outbound immutable Python `bytes` are retained through PyO3's `bytes`
//! conversion into Rust [`Bytes`], avoiding a payload copy while the transport
//! consumes them. Mutable `bytearray` values are snapshotted by that conversion.
//! Incoming network data must become Python `bytes` for ASGI, so that direction
//! still copies at the language boundary. Bounded channels cap queued message
//! counts, but an application controls the size of each individual message.

use std::error::Error as StdError;
use std::fmt;
use std::future::Future;
use std::net::SocketAddr;
use std::pin::Pin;
#[cfg(feature = "runtime-diagnostics")]
use std::sync::atomic::AtomicU64;
#[cfg(any(not(feature = "native-tcp"), coverage))]
use std::sync::atomic::AtomicUsize;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Arc, OnceLock};
use std::task::{Context, Poll};

#[cfg(any(not(feature = "native-tcp"), coverage))]
use bytes::Buf;
use bytes::Bytes;
#[cfg(not(feature = "native-tcp"))]
use futures_util::task::AtomicWaker;
#[cfg(not(feature = "native-tcp"))]
use futures_util::{SinkExt, StreamExt};
use http::header::{HeaderName, HeaderValue, DATE};
use http::{HeaderMap, Request, Response, StatusCode, Version};
use http_body::{Body, Frame, SizeHint};
use http_body_util::combinators::UnsyncBoxBody;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
#[cfg(not(feature = "native-tcp"))]
use hyper::service::service_fn;
#[cfg(not(feature = "native-tcp"))]
use hyper_util::rt::TokioExecutor;
#[cfg(not(feature = "native-tcp"))]
use hyper_util::rt::TokioIo;
#[cfg(not(feature = "native-tcp"))]
use hyper_util::server::conn::auto;
#[cfg(coverage)]
use pyo3::exceptions::PyMemoryError;
use pyo3::exceptions::{PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString};
use pyo3_async_runtimes::TaskLocals;
#[cfg(not(feature = "native-tcp"))]
use tokio::io::{AsyncRead, AsyncWrite};
#[cfg(not(feature = "native-tcp"))]
use tokio::net::TcpStream;
use tokio::net::{TcpListener, TcpSocket};
use tokio::sync::mpsc::{
    self,
    error::{TryRecvError, TrySendError},
};
use tokio::sync::{oneshot, watch, Mutex};
use tokio_rustls::{rustls, TlsAcceptor};
use tokio_tungstenite::tungstenite::handshake::derive_accept_key;
#[cfg(not(feature = "native-tcp"))]
use tokio_tungstenite::{
    tungstenite::{
        protocol::{Role, WebSocketConfig},
        Error as TungsteniteError,
    },
    WebSocketStream,
};
use tokio_util::sync::CancellationToken;
use tokio_util::task::TaskTracker;
use uvicorn_rs::{
    WebSocketCloseCode as CloseCode, WebSocketCloseFrame as CloseFrame,
    WebSocketMessage as Message, WebSocketSession,
};

use h3_quinn::quinn::{self, crypto::rustls::QuicServerConfig};

// Simulate a dependency task unwinding only in the instrumented fault runner.
// Production builds do not contain this function or its callers.
#[cfg(coverage)]
#[allow(
    clippy::panic,
    reason = "coverage-only task unwind and mutex poisoning probe"
)]
fn coverage_panic(message: &'static str) -> ! {
    panic!("{message}")
}

#[cfg(coverage)]
#[derive(Clone, Copy, PartialEq, Eq)]
enum CoverageFaultPoint {
    PythonTaskFutureDeferTaskTransfer,
    PythonTaskCancelGetAttr,
    PythonTaskCancelContextSetItem,
    PythonTaskCancelScheduleCall,
    HttpReceiveDisconnectedBeforeFuturePoll,
    HttpConnectionLifetimeWaitComplete,
    HttpBodyPumpFirstPollPause,
    HttpBodyPumpBatchLimitOneByte,
    HttpBodyPumpBatchThresholdSendConnectionClosed,
    HttpBodyPumpOversizedSendConnectionClosed,
    HttpBodyPumpErrorStopWait,
    HttpBodyPumpErrorBufferedSendConnectionClosed,
    HttpBodyPumpErrorBufferedSendContinues,
    HttpBodyPumpSendConnectionClosed,
    HttpBodyPumpFinalSendConnectionClosed,
    HttpBodyPumpAfterFinalConnectionClosed,
    HttpBodyPumpDrainStopWait,
    HttpBodyPumpDrainTerminalFrame,
    HttpBodyPumpErrorStop,
    HttpBodyPumpReapCancelledTask,
    HttpBodyPumpShutdownCancelJoin,
    HttpBodyPumpShutdownHang,
    HttpBodyPumpShutdownCompleteTaskBeforeAbort,
    HttpRequestBodySegmentLengthOverflow,
    HttpRequestBodySegmentOutOfBounds,
    #[cfg(not(feature = "native-tcp"))]
    ConnectionIoEofRecheckPause,
    PythonAsgiReceiveBorrowConflict,
    ServerControlShutdownBorrowConflict,
    ServerServeControlBorrowConflict,
    ServerGracefulTimeoutOverflow,
    ServerGetCurrentLocals,
    PythonTaskCompletionAllocate,
    HttpEmptyRequestChannelClosed,
    WebSocketAppTaskPanicBeforeHandshake,
    ServerQuicTlsConfigError,
    NativeModuleWrapServeFunction,
    NativeRuntimeBuildError,
    ServerWebSocketTaskShutdownPanic,
    Http3RequestTaskPanic,
    Http3RequestTaskPanicAfterResponse,
    Http3ConnectionAcceptFinished,
    Http3BodyPumpSendConnectionClosed,
    Http3BodyPumpErrorStop,
    AsgiEventTypeHttpResponseStartEq,
    AsgiEventTypeHttpResponseBodyEq,
    AsgiEventTypeWebSocketAcceptEq,
    AsgiEventTypeWebSocketCloseEq,
    AsgiEventTypeWebSocketSendEq,
    AsgiEventTypeLifespanStartupCompleteEq,
    AsgiEventTypeLifespanStartupFailedEq,
    AsgiEventTypeLifespanShutdownCompleteEq,
    AsgiEventTypeLifespanShutdownFailedEq,
    AsgiEventTypeExtract,
    HttpAsgiSendTypeGetItem,
    HttpResponseStartStatusGetItem,
    HttpResponseStartStatusExtract,
    HttpResponseStartHeadersGetItem,
    HttpResponseStartHeadersExtract,
    HttpResponseBodyBodyGetItem,
    HttpResponseBodyBodyExtract,
    HttpResponseBodyMoreBodyGetItem,
    HttpResponseBodyMoreBodyExtract,
    WebSocketAsgiSendTypeGetItem,
    WebSocketAcceptSubprotocolGetItem,
    WebSocketAcceptSubprotocolExtract,
    WebSocketAcceptHeadersGetItem,
    WebSocketAcceptHeadersExtract,
    WebSocketHandshakeMutexPoison,
    WebSocketHandshakeAlreadyCompleted,
    WebSocketAcceptKeyHeaderValueError,
    WebSocketHandshakeSendClosed,
    WebSocketOutgoingChannelClosedOnSend,
    WebSocketOutgoingQueueReceiverClosed,
    WebSocketCloseCodeGetItem,
    WebSocketCloseCodeExtract,
    WebSocketCloseReasonGetItem,
    WebSocketCloseReasonExtract,
    WebSocketSendTextGetItem,
    WebSocketSendTextExtract,
    WebSocketSendBytesGetItem,
    WebSocketSendBytesExtract,
    LifespanAsgiSendTypeGetItem,
    LifespanStartupFailedMessageGetItem,
    LifespanStartupFailedMessageExtract,
    LifespanShutdownFailedMessageGetItem,
    LifespanShutdownFailedMessageExtract,
    LifespanSendEventChannelClosed,
    NativeModuleAddAsgiIo,
    NativeModuleAddWebSocketIo,
    NativeModuleAddLifespanIo,
    NativeModuleAddServerControl,
    NativeModuleAddServeFunction,
    PythonTaskStarterImportAsyncio,
    PythonTaskStarterEnsureFuture,
    PythonTaskStarterAddDoneCallback,
    PythonTaskStarterInlineCompletion,
    PythonTaskStarterInlineCompletionRegistrationError,
    PythonTaskStarterInlineCompletionBorrowConflict,
    PythonTaskStarterRegistrationErrorBorrowConflict,
    PythonTaskStarterRegistrationSuccessBorrowConflict,
    PythonTaskStarterFailureCleanupScheduleError,
    PythonTaskStarterPreludeCloseError,
    PythonTaskStarterTaskSenderMissing,
    PythonTaskFutureTaskReceiverClosed,
    PythonTaskFutureStarterAllocation,
    PythonTaskFutureContextSetItem,
    PythonTaskFutureScheduleCall,
    PythonTaskFuturePanicAfterCompletion,
    PythonTaskCompletionResultReceiverClosed,
    HttpScopeAsgiVersionSetItem,
    HttpScopeAsgiSpecVersionSetItem,
    HttpScopeTypeSetItem,
    HttpScopeAsgiSetItem,
    HttpScopeHttpVersionSetItem,
    HttpScopeMethodSetItem,
    HttpScopeSchemeSetItem,
    HttpScopePathSetItem,
    HttpScopeRawPathSetItem,
    HttpScopeQueryStringSetItem,
    HttpScopeRootPathSetItem,
    HttpScopeHeadersAppend,
    HttpScopeHeadersSetItem,
    HttpScopeClientSetItem,
    HttpScopeServerSetItem,
    HttpScopeStateCopy,
    HttpScopeStateSetItem,
    HttpRequestTypeSetItem,
    HttpRequestBodySetItem,
    HttpRequestMoreBodySetItem,
    HttpRequestDisconnectTypeSetItem,
    HttpReceiveImmediateDisconnectMessageError,
    HttpReceiveLockContention,
    HttpConnectionPeerReadFailedWaitComplete,
    ServerConnectionTaskServiceError,
    ServerConnectionInfoMissing,
    ServerConnectionLifetimeMissing,
    ServerPeerReadHalfClosedMissing,
    ServerPeerReadFailedMissing,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskJoinError,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskServiceAwaitError,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskJoinAwaitError,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskServiceSelectResult,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskJoinSelectResult,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskServiceErrorDuringShutdown,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskJoinErrorDuringShutdown,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionTaskShutdownHang,
    #[cfg(not(feature = "native-tcp"))]
    ServerConnectionIoPollWriteError,
    HttpAsgiIoAllocate,
    HttpAppInvokeCall,
    HttpResponseTaskWinsStartSelect,
    HttpResponseStartChannelClosed,
    HttpResponseBodyChannelClosed,
    HttpResponseBodyConsumerPause,
    HttpResponseBodyPollPendingPause,
    HttpAppTaskPanicBeforeResponseStart,
    Http3NativeAppTaskPanicBeforeResponseStart,
    Http3ConnectionTaskPanic,
    Http3EndpointAcceptClosed,
    Http3ConnectionTaskPanicDuringShutdown,
    Http3ConnectionTaskShutdownHang,
    Http3ConnectionCreateError,
    Http3ConnectionAcceptError,
    Http3ConnectionInfoMissing,
    Http3ConnectionLifetimeMissing,
    Http3NativeBodyPumpStopWait,
    Http3NativeBodyPumpDisconnectSendStopWait,
    Http3NativeBodyPumpFinalMessageStopWait,
    Http3NativeBodyPumpFinalMessageSendError,
    Http3NativeBodyPumpSendStopWait,
    Http3NativeBodyPumpErrorStopWait,
    Http3NativeBodyPumpCancelBeforeFirstPoll,
    Http3NativeBodyPumpSenderClosed,
    Http3LegacyPathSelection,
    Http3PeerCloseUnexpectedError,
    Http3PeerCloseReasonUnavailable,
    Http3RequestResolveError,
    Http3ResponseBuilderError,
    Http3ResponseSendError,
    Http3ResponseBodyFrameError,
    Http3ResponseNonDataFrame,
    Http3ResponseBodySendError,
    Http3ResponseFinishError,
    Http3BodyPumpConnectionClosed,
    Http3BodyPumpConnectionClosedSelect,
    Http3BodyPumpSenderClosedSelect,
    Http3BodyPumpFinalMessageConnectionClosedSelect,
    Http3BodyPumpFinalMessageSendError,
    Http3BodyPumpEmptyData,
    Http3NativeBodyPumpEmptyData,
    Http3BodyPumpSendError,
    ServerListenerAcceptError,
    ServerListenerLocalAddrError,
    ServerHttp3EndpointBindError,
    ServerHttp3TaskShutdownHang,
    ServerWebSocketTaskShutdownHang,
    LifespanScopeAsgiVersionSetItem,
    LifespanScopeAsgiSpecVersionSetItem,
    LifespanScopeTypeSetItem,
    LifespanScopeAsgiSetItem,
    LifespanScopeStateSetItem,
    LifespanIoAllocate,
    LifespanAppInvokeCall,
    LifespanReceiveStartupTypeSetItem,
    LifespanReceiveShutdownTypeSetItem,
    LifespanReceiveChannelClosed,
    LifespanStartEventChannelClosed,
    LifespanStartupTaskJoinError,
    LifespanStartupSendClosed,
    LifespanShutdownTaskJoinError,
    LifespanShutdownTaskJoinAfterComplete,
    LifespanShutdownForceTimeout,
    WebSocketScopeAsgiVersionSetItem,
    WebSocketScopeAsgiSpecVersionSetItem,
    WebSocketScopeTypeSetItem,
    WebSocketScopeAsgiSetItem,
    WebSocketScopeHttpVersionSetItem,
    WebSocketScopeMethodSetItem,
    WebSocketScopeSchemeSetItem,
    WebSocketScopePathSetItem,
    WebSocketScopeRawPathSetItem,
    WebSocketScopeQueryStringSetItem,
    WebSocketScopeRootPathSetItem,
    WebSocketScopeHeadersAppend,
    WebSocketScopeHeadersSetItem,
    WebSocketScopeSubprotocolsSetItem,
    WebSocketScopeClientSetItem,
    WebSocketScopeServerSetItem,
    WebSocketIoAllocate,
    WebSocketAppInvokeCall,
    WebSocketNativeUpgradeMissing,
    WebSocketNativeUpgradeRegisterClosed,
    WebSocketReceiveConnectTypeSetItem,
    WebSocketReceiveTextTypeSetItem,
    WebSocketReceiveTextValueSetItem,
    WebSocketReceiveBinaryTypeSetItem,
    WebSocketReceiveBinaryValueSetItem,
    WebSocketReceiveDisconnectTypeSetItem,
    WebSocketReceiveDisconnectCodeSetItem,
    WebSocketReceiveDisconnectReasonSetItem,
    WebSocketReceiveClosedTypeSetItem,
    WebSocketReceiveClosedCodeSetItem,
    WebSocketReceiveClosedReasonSetItem,
    WebSocketReceiveChannelClosed,
    WebSocketReceiveConnectionClosed,
    WebSocketDriverConnectionClosed,
    WebSocketDriverPeerEof,
    WebSocketDriverAppTaskAborted,
    WebSocketDriverIncomingTextReceiverClosed,
    WebSocketDriverIncomingBinaryReceiverClosed,
    WebSocketDriverOutgoingChannelClosed,
    WebSocketPeerReadFailureWaitComplete,
    WebSocketPeerReadFailureUnavailable,
    WebSocketPeerReadFailureWatchFallback,
    WebSocketDriverSendError,
    WebSocketDriverDrainSendError,
}

#[cfg(coverage)]
impl CoverageFaultPoint {
    fn as_str(self) -> &'static str {
        match self {
            Self::PythonTaskFutureDeferTaskTransfer => "python.task-future.defer-task-transfer",
            Self::PythonTaskCancelGetAttr => "python.task-cancel.cancel.getattr",
            Self::PythonTaskCancelContextSetItem => "python.task-cancel.context.set-item",
            Self::PythonTaskCancelScheduleCall => "python.task-cancel.schedule-call",
            Self::HttpReceiveDisconnectedBeforeFuturePoll => {
                "http.receive.disconnected-before-future-poll"
            }
            Self::HttpConnectionLifetimeWaitComplete => "http.connection-lifetime.wait-complete",
            Self::HttpConnectionPeerReadFailedWaitComplete => {
                "http.connection.peer-read-failed.wait-complete"
            }
            Self::HttpBodyPumpFirstPollPause => "http.body-pump.first-poll-pause",
            Self::HttpBodyPumpBatchLimitOneByte => "http.body-pump.batch-limit.one-byte",
            Self::HttpBodyPumpBatchThresholdSendConnectionClosed => {
                "http.body-pump.batch-threshold.send-connection-closed"
            }
            Self::HttpBodyPumpOversizedSendConnectionClosed => {
                "http.body-pump.oversized.send-connection-closed"
            }
            Self::HttpBodyPumpErrorStopWait => "http.body-pump.error.stop-wait",
            Self::HttpBodyPumpErrorBufferedSendConnectionClosed => {
                "http.body-pump.error.buffered-send-connection-closed"
            }
            Self::HttpBodyPumpErrorBufferedSendContinues => {
                "http.body-pump.error.buffered-send-continues"
            }
            Self::HttpBodyPumpSendConnectionClosed => "http.body-pump.send.connection-closed",
            Self::HttpBodyPumpFinalSendConnectionClosed => {
                "http.body-pump.final-send.connection-closed"
            }
            Self::HttpBodyPumpAfterFinalConnectionClosed => {
                "http.body-pump.after-final.connection-closed"
            }
            Self::HttpBodyPumpDrainStopWait => "http.body-pump.drain.server-stop-wait",
            Self::HttpBodyPumpDrainTerminalFrame => "http.body-pump.drain.terminal-frame",
            Self::HttpBodyPumpErrorStop => "http.body-pump.error.request-stop",
            Self::HttpBodyPumpReapCancelledTask => "http.body-pump.reap.cancelled-task",
            Self::HttpBodyPumpShutdownCancelJoin => "http.body-pump.shutdown.cancel-join",
            Self::HttpBodyPumpShutdownHang => "http.body-pump.shutdown.hang",
            Self::HttpBodyPumpShutdownCompleteTaskBeforeAbort => {
                "http.body-pump.shutdown.complete-task-before-abort"
            }
            Self::HttpRequestBodySegmentLengthOverflow => {
                "http.request.body-segment.length-overflow"
            }
            Self::HttpRequestBodySegmentOutOfBounds => "http.request.body-segment.out-of-bounds",
            #[cfg(not(feature = "native-tcp"))]
            Self::ConnectionIoEofRecheckPause => "server.connection-io.eof-recheck.pause",
            Self::PythonAsgiReceiveBorrowConflict => "python.asgi-receive.borrow-conflict",
            Self::ServerControlShutdownBorrowConflict => "server.control.shutdown.borrow-conflict",
            Self::ServerServeControlBorrowConflict => "server.serve.control.borrow-conflict",
            Self::ServerGracefulTimeoutOverflow => "server.graceful-timeout.overflow",
            Self::ServerGetCurrentLocals => "server.python-locals.get-current",
            Self::PythonTaskCompletionAllocate => "python.task-completion.allocate",
            Self::HttpEmptyRequestChannelClosed => "http.request.empty-body.channel-closed",
            Self::WebSocketAppTaskPanicBeforeHandshake => {
                "websocket.app-task.panic-before-handshake"
            }
            Self::ServerQuicTlsConfigError => "server.quic-tls.config-error",
            Self::NativeModuleWrapServeFunction => "native.module.wrap-function.serve",
            Self::NativeRuntimeBuildError => "native.runtime.build.error",
            Self::ServerWebSocketTaskShutdownPanic => "server.websocket-task.shutdown-panic",
            Self::Http3RequestTaskPanic => "http3.request-task.panic",
            Self::Http3RequestTaskPanicAfterResponse => "http3.request-task.panic-after-response",
            Self::Http3ConnectionAcceptFinished => "http3.connection.accept-finished",
            Self::Http3BodyPumpSendConnectionClosed => "http3.body-pump.send.connection-closed",
            Self::Http3BodyPumpErrorStop => "http3.body-pump.error.request-stop",
            Self::AsgiEventTypeHttpResponseStartEq => "asgi.event-type.http-response-start.eq",
            Self::AsgiEventTypeHttpResponseBodyEq => "asgi.event-type.http-response-body.eq",
            Self::AsgiEventTypeWebSocketAcceptEq => "asgi.event-type.websocket-accept.eq",
            Self::AsgiEventTypeWebSocketCloseEq => "asgi.event-type.websocket-close.eq",
            Self::AsgiEventTypeWebSocketSendEq => "asgi.event-type.websocket-send.eq",
            Self::AsgiEventTypeLifespanStartupCompleteEq => {
                "asgi.event-type.lifespan-startup-complete.eq"
            }
            Self::AsgiEventTypeLifespanStartupFailedEq => {
                "asgi.event-type.lifespan-startup-failed.eq"
            }
            Self::AsgiEventTypeLifespanShutdownCompleteEq => {
                "asgi.event-type.lifespan-shutdown-complete.eq"
            }
            Self::AsgiEventTypeLifespanShutdownFailedEq => {
                "asgi.event-type.lifespan-shutdown-failed.eq"
            }
            Self::AsgiEventTypeExtract => "asgi.event-type.extract",
            Self::HttpAsgiSendTypeGetItem => "http.asgi.send.type.get-item",
            Self::HttpResponseStartStatusGetItem => "http.response.start.status.get-item",
            Self::HttpResponseStartStatusExtract => "http.response.start.status.extract",
            Self::HttpResponseStartHeadersGetItem => "http.response.start.headers.get-item",
            Self::HttpResponseStartHeadersExtract => "http.response.start.headers.extract",
            Self::HttpResponseBodyBodyGetItem => "http.response.body.body.get-item",
            Self::HttpResponseBodyBodyExtract => "http.response.body.body.extract",
            Self::HttpResponseBodyMoreBodyGetItem => "http.response.body.more-body.get-item",
            Self::HttpResponseBodyMoreBodyExtract => "http.response.body.more-body.extract",
            Self::WebSocketAsgiSendTypeGetItem => "websocket.asgi.send.type.get-item",
            Self::WebSocketAcceptSubprotocolGetItem => "websocket.accept.subprotocol.get-item",
            Self::WebSocketAcceptSubprotocolExtract => "websocket.accept.subprotocol.extract",
            Self::WebSocketAcceptHeadersGetItem => "websocket.accept.headers.get-item",
            Self::WebSocketAcceptHeadersExtract => "websocket.accept.headers.extract",
            Self::WebSocketHandshakeMutexPoison => "websocket.handshake.mutex.poison",
            Self::WebSocketHandshakeAlreadyCompleted => "websocket.handshake.already-completed",
            Self::WebSocketAcceptKeyHeaderValueError => "websocket.accept-key.header-value-error",
            Self::WebSocketHandshakeSendClosed => "websocket.handshake.send-closed",
            Self::WebSocketOutgoingChannelClosedOnSend => {
                "websocket.outgoing.channel-closed-on-send"
            }
            Self::WebSocketOutgoingQueueReceiverClosed => {
                "websocket.outgoing.queue-receiver-closed"
            }
            Self::WebSocketCloseCodeGetItem => "websocket.close.code.get-item",
            Self::WebSocketCloseCodeExtract => "websocket.close.code.extract",
            Self::WebSocketCloseReasonGetItem => "websocket.close.reason.get-item",
            Self::WebSocketCloseReasonExtract => "websocket.close.reason.extract",
            Self::WebSocketSendTextGetItem => "websocket.send.text.get-item",
            Self::WebSocketSendTextExtract => "websocket.send.text.extract",
            Self::WebSocketSendBytesGetItem => "websocket.send.bytes.get-item",
            Self::WebSocketSendBytesExtract => "websocket.send.bytes.extract",
            Self::LifespanAsgiSendTypeGetItem => "lifespan.asgi.send.type.get-item",
            Self::LifespanStartupFailedMessageGetItem => "lifespan.startup.failed.message.get-item",
            Self::LifespanStartupFailedMessageExtract => "lifespan.startup.failed.message.extract",
            Self::LifespanShutdownFailedMessageGetItem => {
                "lifespan.shutdown.failed.message.get-item"
            }
            Self::LifespanShutdownFailedMessageExtract => {
                "lifespan.shutdown.failed.message.extract"
            }
            Self::LifespanSendEventChannelClosed => "lifespan.send.event-channel-closed",
            Self::NativeModuleAddAsgiIo => "native.module.add-class.asgi-io",
            Self::NativeModuleAddWebSocketIo => "native.module.add-class.websocket-io",
            Self::NativeModuleAddLifespanIo => "native.module.add-class.lifespan-io",
            Self::NativeModuleAddServerControl => "native.module.add-class.server-control",
            Self::NativeModuleAddServeFunction => "native.module.add-function.serve",
            Self::PythonTaskStarterImportAsyncio => "python.task-starter.import-asyncio",
            Self::PythonTaskStarterEnsureFuture => "python.task-starter.ensure-future",
            Self::PythonTaskStarterAddDoneCallback => "python.task-starter.add-done-callback",
            Self::PythonTaskStarterInlineCompletion => "python.task-starter.inline-completion",
            Self::PythonTaskStarterInlineCompletionRegistrationError => {
                "python.task-starter.inline-completion-registration-error"
            }
            Self::PythonTaskStarterInlineCompletionBorrowConflict => {
                "python.task-starter.inline-completion.borrow-conflict"
            }
            Self::PythonTaskStarterRegistrationErrorBorrowConflict => {
                "python.task-starter.registration-error.borrow-conflict"
            }
            Self::PythonTaskStarterRegistrationSuccessBorrowConflict => {
                "python.task-starter.registration-success.borrow-conflict"
            }
            Self::PythonTaskStarterFailureCleanupScheduleError => {
                "python.task-starter.failure-cleanup.schedule-error"
            }
            Self::PythonTaskStarterPreludeCloseError => "python.task-starter.prelude-close-error",
            Self::PythonTaskStarterTaskSenderMissing => "python.task-starter.task-sender-missing",
            Self::PythonTaskFutureTaskReceiverClosed => "python.task-future.task-receiver-closed",
            Self::PythonTaskFutureStarterAllocation => "python.task-future.starter-allocation",
            Self::PythonTaskFutureContextSetItem => "python.task-future.context.set-item",
            Self::PythonTaskFutureScheduleCall => "python.task-future.schedule-call",
            Self::PythonTaskFuturePanicAfterCompletion => {
                "python.task-future.panic-after-completion"
            }
            Self::PythonTaskCompletionResultReceiverClosed => {
                "python.task-completion.result-receiver-closed"
            }
            Self::HttpScopeAsgiVersionSetItem => "scope.http.asgi.version.set-item",
            Self::HttpScopeAsgiSpecVersionSetItem => "scope.http.asgi.spec-version.set-item",
            Self::HttpScopeTypeSetItem => "scope.http.type.set-item",
            Self::HttpScopeAsgiSetItem => "scope.http.asgi.set-item",
            Self::HttpScopeHttpVersionSetItem => "scope.http.http-version.set-item",
            Self::HttpScopeMethodSetItem => "scope.http.method.set-item",
            Self::HttpScopeSchemeSetItem => "scope.http.scheme.set-item",
            Self::HttpScopePathSetItem => "scope.http.path.set-item",
            Self::HttpScopeRawPathSetItem => "scope.http.raw-path.set-item",
            Self::HttpScopeQueryStringSetItem => "scope.http.query-string.set-item",
            Self::HttpScopeRootPathSetItem => "scope.http.root-path.set-item",
            Self::HttpScopeHeadersAppend => "scope.http.headers.append",
            Self::HttpScopeHeadersSetItem => "scope.http.headers.set-item",
            Self::HttpScopeClientSetItem => "scope.http.client.set-item",
            Self::HttpScopeServerSetItem => "scope.http.server.set-item",
            Self::HttpScopeStateCopy => "scope.state.copy",
            Self::HttpScopeStateSetItem => "scope.state.set-item",
            Self::HttpRequestTypeSetItem => "request.http.type.set-item",
            Self::HttpRequestBodySetItem => "request.http.body.set-item",
            Self::HttpRequestMoreBodySetItem => "request.http.more-body.set-item",
            Self::HttpRequestDisconnectTypeSetItem => "request.http.disconnect.type.set-item",
            Self::HttpReceiveImmediateDisconnectMessageError => {
                "http.receive.immediate-disconnect-message-error"
            }
            Self::HttpReceiveLockContention => "http.receive.lock-contention",
            Self::ServerConnectionTaskServiceError => "server.connection-task.service-error",
            Self::ServerConnectionInfoMissing => "server.connection-info.missing",
            Self::ServerConnectionLifetimeMissing => "server.connection-lifetime.missing",
            Self::ServerPeerReadHalfClosedMissing => "server.peer-read-half-closed.missing",
            Self::ServerPeerReadFailedMissing => "server.peer-read-failed.missing",
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskJoinError => "server.connection-task.join-error",
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskServiceAwaitError => {
                "server.connection-task.service-await-error"
            }
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskJoinAwaitError => "server.connection-task.join-await-error",
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskServiceSelectResult => {
                "server.connection-task.service-select-result"
            }
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskJoinSelectResult => {
                "server.connection-task.join-select-result"
            }
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskServiceErrorDuringShutdown => {
                "server.connection-task.service-error-during-shutdown"
            }
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskJoinErrorDuringShutdown => {
                "server.connection-task.join-error-during-shutdown"
            }
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionTaskShutdownHang => "server.connection-task.shutdown-hang",
            #[cfg(not(feature = "native-tcp"))]
            Self::ServerConnectionIoPollWriteError => "server.connection-io.poll-write-error",
            Self::HttpAsgiIoAllocate => "http.asgi-io.allocate",
            Self::HttpAppInvokeCall => "http.asgi.app-invoke",
            Self::HttpResponseTaskWinsStartSelect => "http.response.task-wins-start-select",
            Self::HttpResponseStartChannelClosed => "http.response.start.channel-closed",
            Self::HttpResponseBodyChannelClosed => "http.response.body.channel-closed",
            Self::HttpResponseBodyConsumerPause => "http.response.body-consumer.pause",
            Self::HttpResponseBodyPollPendingPause => {
                "http.response.body-poll.receiver-pending.pause"
            }
            Self::HttpAppTaskPanicBeforeResponseStart => {
                "http.app-task.panic-before-response-start"
            }
            Self::Http3NativeAppTaskPanicBeforeResponseStart => {
                "http3.native-app-task.panic-before-response-start"
            }
            Self::Http3ConnectionTaskPanic => "http3.connection-task.panic",
            Self::Http3EndpointAcceptClosed => "http3.endpoint.accept-closed",
            Self::Http3ConnectionTaskPanicDuringShutdown => {
                "http3.connection-task.panic-during-shutdown"
            }
            Self::Http3ConnectionTaskShutdownHang => "http3.connection-task.shutdown-hang",
            Self::Http3ConnectionCreateError => "http3.connection.create-error",
            Self::Http3ConnectionAcceptError => "http3.connection.accept-error",
            Self::Http3ConnectionInfoMissing => "http3.connection-info.missing",
            Self::Http3ConnectionLifetimeMissing => "http3.connection-lifetime.missing",
            Self::Http3NativeBodyPumpStopWait => "http3.native-body-pump.stop-wait",
            Self::Http3NativeBodyPumpDisconnectSendStopWait => {
                "http3.native-body-pump.disconnect-send-stop-wait"
            }
            Self::Http3NativeBodyPumpFinalMessageStopWait => {
                "http3.native-body-pump.final-message-stop-wait"
            }
            Self::Http3NativeBodyPumpFinalMessageSendError => {
                "http3.native-body-pump.final-message-send-error"
            }
            Self::Http3NativeBodyPumpSendStopWait => "http3.native-body-pump.send-stop-wait",
            Self::Http3NativeBodyPumpErrorStopWait => "http3.native-body-pump.error-stop-wait",
            Self::Http3NativeBodyPumpCancelBeforeFirstPoll => {
                "http3.native-body-pump.cancel-before-first-poll"
            }
            Self::Http3NativeBodyPumpSenderClosed => "http3.native-body-pump.sender-closed",
            Self::Http3LegacyPathSelection => "http3.legacy-path.selection",
            Self::Http3PeerCloseUnexpectedError => "http3.peer-close.unexpected-error-kind",
            Self::Http3PeerCloseReasonUnavailable => "http3.peer-close.close-reason-unavailable",
            Self::Http3RequestResolveError => "http3.request.resolve-error",
            Self::Http3ResponseBuilderError => "http3.response.builder-error",
            Self::Http3ResponseSendError => "http3.response.send-error",
            Self::Http3ResponseBodyFrameError => "http3.response.body-frame-error",
            Self::Http3ResponseNonDataFrame => "http3.response.non-data-frame",
            Self::Http3ResponseBodySendError => "http3.response.body-send-error",
            Self::Http3ResponseFinishError => "http3.response.finish-error",
            Self::Http3BodyPumpConnectionClosed => "http3.body-pump.connection-closed",
            Self::Http3BodyPumpConnectionClosedSelect => "http3.body-pump.connection-closed-select",
            Self::Http3BodyPumpSenderClosedSelect => "http3.body-pump.sender-closed-select",
            Self::Http3BodyPumpFinalMessageConnectionClosedSelect => {
                "http3.body-pump.final-message-connection-closed-select"
            }
            Self::Http3BodyPumpFinalMessageSendError => "http3.body-pump.final-message-send-error",
            Self::Http3BodyPumpEmptyData => "http3.body-pump.empty-data-frame",
            Self::Http3NativeBodyPumpEmptyData => "http3.native-body-pump.empty-data-frame",
            Self::Http3BodyPumpSendError => "http3.body-pump.send-error",
            Self::ServerListenerAcceptError => "server.listener.accept-error",
            Self::ServerListenerLocalAddrError => "server.listener.local-addr-error",
            Self::ServerHttp3EndpointBindError => "server.http3-endpoint.bind-error",
            Self::ServerHttp3TaskShutdownHang => "server.http3-task.shutdown-hang",
            Self::ServerWebSocketTaskShutdownHang => "server.websocket-task.shutdown-hang",
            Self::LifespanScopeAsgiVersionSetItem => "lifespan.scope.asgi.version.set-item",
            Self::LifespanScopeAsgiSpecVersionSetItem => {
                "lifespan.scope.asgi.spec-version.set-item"
            }
            Self::LifespanScopeTypeSetItem => "lifespan.scope.type.set-item",
            Self::LifespanScopeAsgiSetItem => "lifespan.scope.asgi.set-item",
            Self::LifespanScopeStateSetItem => "lifespan.scope.state.set-item",
            Self::LifespanIoAllocate => "lifespan.io.allocate",
            Self::LifespanAppInvokeCall => "lifespan.app-invoke",
            Self::LifespanReceiveStartupTypeSetItem => "lifespan.receive.startup.type.set-item",
            Self::LifespanReceiveShutdownTypeSetItem => "lifespan.receive.shutdown.type.set-item",
            Self::LifespanReceiveChannelClosed => "lifespan.receive.channel-closed",
            Self::LifespanStartupSendClosed => "lifespan.startup.send-closed",
            Self::LifespanShutdownTaskJoinError => "lifespan.shutdown.task-join-error",
            Self::LifespanShutdownTaskJoinAfterComplete => {
                "lifespan.shutdown.task-join-after-complete"
            }
            Self::LifespanStartEventChannelClosed => "lifespan.startup.event-channel-closed",
            Self::LifespanStartupTaskJoinError => "lifespan.startup.task-join-error",
            Self::LifespanShutdownForceTimeout => "lifespan.shutdown.force-timeout",
            Self::WebSocketScopeAsgiVersionSetItem => "scope.websocket.asgi.version.set-item",
            Self::WebSocketScopeAsgiSpecVersionSetItem => {
                "scope.websocket.asgi.spec-version.set-item"
            }
            Self::WebSocketScopeTypeSetItem => "scope.websocket.type.set-item",
            Self::WebSocketScopeAsgiSetItem => "scope.websocket.asgi.set-item",
            Self::WebSocketScopeHttpVersionSetItem => "scope.websocket.http-version.set-item",
            Self::WebSocketScopeMethodSetItem => "scope.websocket.method.set-item",
            Self::WebSocketScopeSchemeSetItem => "scope.websocket.scheme.set-item",
            Self::WebSocketScopePathSetItem => "scope.websocket.path.set-item",
            Self::WebSocketScopeRawPathSetItem => "scope.websocket.raw-path.set-item",
            Self::WebSocketScopeQueryStringSetItem => "scope.websocket.query-string.set-item",
            Self::WebSocketScopeRootPathSetItem => "scope.websocket.root-path.set-item",
            Self::WebSocketScopeHeadersAppend => "scope.websocket.headers.append",
            Self::WebSocketScopeHeadersSetItem => "scope.websocket.headers.set-item",
            Self::WebSocketScopeSubprotocolsSetItem => "scope.websocket.subprotocols.set-item",
            Self::WebSocketScopeClientSetItem => "scope.websocket.client.set-item",
            Self::WebSocketScopeServerSetItem => "scope.websocket.server.set-item",
            Self::WebSocketIoAllocate => "websocket.io.allocate",
            Self::WebSocketAppInvokeCall => "websocket.app-invoke",
            Self::WebSocketNativeUpgradeMissing => "websocket.native-upgrade.missing",
            Self::WebSocketNativeUpgradeRegisterClosed => {
                "websocket.native-upgrade.register-closed"
            }
            Self::WebSocketReceiveConnectTypeSetItem => "websocket.receive.connect-type.set-item",
            Self::WebSocketReceiveTextTypeSetItem => "websocket.receive.text-type.set-item",
            Self::WebSocketReceiveTextValueSetItem => "websocket.receive.text-value.set-item",
            Self::WebSocketReceiveBinaryTypeSetItem => "websocket.receive.binary-type.set-item",
            Self::WebSocketReceiveBinaryValueSetItem => "websocket.receive.binary-value.set-item",
            Self::WebSocketReceiveDisconnectTypeSetItem => {
                "websocket.receive.disconnect-type.set-item"
            }
            Self::WebSocketReceiveDisconnectCodeSetItem => {
                "websocket.receive.disconnect-code.set-item"
            }
            Self::WebSocketReceiveDisconnectReasonSetItem => {
                "websocket.receive.disconnect-reason.set-item"
            }
            Self::WebSocketReceiveClosedTypeSetItem => "websocket.receive.closed-type.set-item",
            Self::WebSocketReceiveClosedCodeSetItem => "websocket.receive.closed-code.set-item",
            Self::WebSocketReceiveClosedReasonSetItem => "websocket.receive.closed-reason.set-item",
            Self::WebSocketReceiveChannelClosed => "websocket.receive.channel-closed",
            Self::WebSocketReceiveConnectionClosed => "websocket.receive.connection-closed",
            Self::WebSocketDriverConnectionClosed => "websocket.driver.connection-closed",
            Self::WebSocketDriverPeerEof => "websocket.driver.peer-eof",
            Self::WebSocketDriverAppTaskAborted => "websocket.driver.app-task-aborted",
            Self::WebSocketDriverIncomingTextReceiverClosed => {
                "websocket.driver.incoming-text-receiver-closed"
            }
            Self::WebSocketDriverIncomingBinaryReceiverClosed => {
                "websocket.driver.incoming-binary-receiver-closed"
            }
            Self::WebSocketDriverOutgoingChannelClosed => {
                "websocket.driver.outgoing-channel-closed"
            }
            Self::WebSocketPeerReadFailureWaitComplete => {
                "websocket.peer-read-failed.wait-complete"
            }
            Self::WebSocketPeerReadFailureUnavailable => "websocket.peer-read-failed.unavailable",
            Self::WebSocketPeerReadFailureWatchFallback => {
                "websocket.peer-read-failed.watch-fallback"
            }
            Self::WebSocketDriverSendError => "websocket.driver.send-error",
            Self::WebSocketDriverDrainSendError => "websocket.driver.drain-send-error",
        }
    }
}

#[cfg(coverage)]
fn coverage_fault_is_armed(point: CoverageFaultPoint) -> bool {
    let Some(path) = std::env::var_os("UVICORN_RS_COVERAGE_FAULT_FILE") else {
        return false;
    };
    std::fs::read_to_string(path)
        .map(|value| value.trim() == point.as_str())
        .unwrap_or(false)
}

#[cfg(coverage)]
fn coverage_fault_take(point: CoverageFaultPoint) -> bool {
    let Some(path) = std::env::var_os("UVICORN_RS_COVERAGE_FAULT_FILE") else {
        return false;
    };
    let armed = std::fs::read_to_string(&path)
        .map(|value| value.trim() == point.as_str())
        .unwrap_or(false);
    if armed {
        let _ = std::fs::write(path, "");
    }
    armed
}

macro_rules! coverage_try {
    ($fault_point:ident, $operation:expr) => {{
        #[cfg(coverage)]
        let result = if coverage_fault_is_armed(CoverageFaultPoint::$fault_point) {
            Err(PyMemoryError::new_err(concat!(
                "coverage-only injected MemoryError at ",
                stringify!($fault_point)
            )))
        } else {
            $operation
        };
        #[cfg(not(coverage))]
        let result = $operation;
        result?;
    }};
}

macro_rules! coverage_value {
    ($fault_point:ident, $operation:expr) => {{
        #[cfg(coverage)]
        let result = if coverage_fault_is_armed(CoverageFaultPoint::$fault_point) {
            Err(PyMemoryError::new_err(concat!(
                "coverage-only injected MemoryError at ",
                stringify!($fault_point)
            )))
        } else {
            $operation.map_err(PyErr::from)
        };
        #[cfg(not(coverage))]
        let result = $operation;
        result
    }};
}

// Exercise PyO3's real borrow error at the receive boundary, using a valid
// native object and no raw pointers. The guard is released before propagation.
macro_rules! coverage_receive_borrow_conflict {
    ($io:expr, $py:expr) => {{
        #[cfg(coverage)]
        {
            let result = if coverage_fault_take(CoverageFaultPoint::PythonAsgiReceiveBorrowConflict)
            {
                let _exclusive = $io.borrow_mut($py);
                $io.bind($py).call_method0("receive").map(drop)
            } else {
                Ok(())
            };
            result?;
        }
    }};
}

// Feed injected runtime failures through the same conversion and propagation
// as the real operation. Returning early from a probe would bypass cleanup.
macro_rules! coverage_runtime_result {
    ($fault_point:ident, $operation:expr) => {{
        #[cfg(coverage)]
        let result = if coverage_fault_take(CoverageFaultPoint::$fault_point) {
            Err(BoxError::from(std::io::Error::other(concat!(
                "coverage-injected runtime error at ",
                stringify!($fault_point)
            ))))
        } else {
            $operation.map_err(BoxError::from)
        };
        #[cfg(not(coverage))]
        let result = $operation.map_err(BoxError::from);
        result
    }};
}

type BoxError = Box<dyn StdError + Send + Sync>;

fn log_error(message: fmt::Arguments<'_>) {
    // Diagnostic I/O is secondary to the original operational Result. A full
    // or broken stderr must not turn error reporting into a server panic.
    let _ = std::io::Write::write_fmt(&mut std::io::stderr().lock(), format_args!("{message}\n"));
}
type ResponseBody = UnsyncBoxBody<Bytes, BoxError>;
#[cfg(not(feature = "native-tcp"))]
type WebSocketTasks = Arc<Mutex<tokio::task::JoinSet<()>>>;
type RequestBodyTasks = Arc<Mutex<tokio::task::JoinSet<()>>>;
// Keep a bounded burst ahead of the HTTP body consumer. Sends fit into
// available slots synchronously; a full queue returns an awaitable so Tokio
// can apply backpressure. This is bounded by message count, not body bytes.
const RESPONSE_BODY_QUEUE_CAPACITY: usize = 16;
// Coalesce already-arrived Hyper data frames into bounded ASGI body messages.
// The time limit keeps slow or streaming uploads from waiting for a full batch.
const HTTP_REQUEST_BODY_BATCH_BYTES: usize = 256 * 1024;
const HTTP_REQUEST_BODY_BATCH_MAX_WAIT: std::time::Duration = std::time::Duration::from_millis(5);

/// Optional counters for attributing Python/Rust bridge work in diagnostic builds.
///
/// The default build keeps this type zero-sized, and its inline methods compile
/// to no-ops. Enable `runtime-diagnostics` only for focused profiling runs.
#[derive(Clone, Default)]
struct RuntimeDiagnostics {
    #[cfg(feature = "runtime-diagnostics")]
    counters: Arc<RuntimeDiagnosticCounters>,
}

#[cfg(feature = "runtime-diagnostics")]
#[derive(Default)]
struct RuntimeDiagnosticCounters {
    asgi_task_schedule_calls: AtomicU64,
    http_requests: AtomicU64,
    http_receive_immediate: AtomicU64,
    http_receive_bridge_futures: AtomicU64,
    http_response_start_messages: AtomicU64,
    http_response_body_messages: AtomicU64,
    http_response_body_queue_full: AtomicU64,
    http_response_body_full_send_wait_ns: AtomicU64,
    http_python_attach_calls: AtomicU64,
    http_python_attach_wait_ns: AtomicU64,
    http_response_start_latency_calls: AtomicU64,
    http_response_start_latency_ns: AtomicU64,
    http_final_body_latency_calls: AtomicU64,
    http_final_body_latency_ns: AtomicU64,
    python_task_starter_calls: AtomicU64,
    python_task_starter_schedule_wait_ns: AtomicU64,
    websocket_receive_bridge_futures: AtomicU64,
    websocket_outgoing_messages: AtomicU64,
    websocket_outgoing_queue_full: AtomicU64,
    http_request_python_bytes_messages: AtomicU64,
    http_request_python_bytes_copied: AtomicU64,
    http_request_python_bytes_materialization_calls: AtomicU64,
    http_request_python_bytes_materialization_ns: AtomicU64,
    http_body_frame_waits: AtomicU64,
    http_body_frame_wait_ns: AtomicU64,
    http_body_data_frames: AtomicU64,
    http_body_data_bytes: AtomicU64,
    http_body_batch_timeout_flushes: AtomicU64,
    http_body_batch_threshold_flushes: AtomicU64,
    http_body_channel_send_calls: AtomicU64,
    http_body_channel_send_wait_ns: AtomicU64,
    // Detailed request-body timings distinguish completed frame polls from timer flushes.
    http_request_body_frame_poll_completions: AtomicU64,
    http_request_body_frame_ready_wait_ns: AtomicU64,
    http_request_body_batch_deadline_flushes: AtomicU64,
    // Batch age overlaps frame-ready wait because the deadline races body.frame().
    http_request_body_batch_age_at_deadline_ns: AtomicU64,
    http_request_body_batch_size_flushes: AtomicU64,
    http_request_body_eof_flushes: AtomicU64,
    http_request_body_channel_full_sends: AtomicU64,
    http_request_body_channel_full_send_wait_ns: AtomicU64,
    tcp_read_poll_calls: AtomicU64,
    tcp_read_pending_calls: AtomicU64,
    tcp_read_bytes: AtomicU64,
    tcp_read_poll_ns: AtomicU64,
    tcp_read_pending_wait_ns: AtomicU64,
    tcp_write_poll_calls: AtomicU64,
    tcp_write_pending_calls: AtomicU64,
    tcp_write_bytes: AtomicU64,
    tcp_write_poll_ns: AtomicU64,
    tcp_write_pending_wait_ns: AtomicU64,
    tcp_flush_poll_calls: AtomicU64,
    tcp_flush_poll_ns: AtomicU64,
    tcp_shutdown_poll_calls: AtomicU64,
    tcp_shutdown_poll_ns: AtomicU64,
}

impl RuntimeDiagnostics {
    #[inline]
    fn asgi_task_scheduled(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .asgi_task_schedule_calls
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_request_started(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters.http_requests.fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_python_attach_wait_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    fn http_python_attach_wait_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_python_attach_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters.http_python_attach_wait_ns.fetch_add(
                started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn http_response_latency_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    fn http_response_start_latency_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_response_start_latency_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters.http_response_start_latency_ns.fetch_add(
                started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[cfg(feature = "runtime-diagnostics")]
    #[inline]
    fn http_final_body_latency_finished(&self, started: Option<std::time::Instant>) {
        if let Some(started) = started {
            self.counters
                .http_final_body_latency_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters.http_final_body_latency_ns.fetch_add(
                started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
    }

    #[cfg(feature = "runtime-diagnostics")]
    #[inline]
    fn python_task_starter_started(&self, started: std::time::Instant) {
        {
            self.counters
                .python_task_starter_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .python_task_starter_schedule_wait_ns
                .fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
        }
    }

    #[inline]
    fn http_receive_immediate(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_receive_immediate
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_receive_bridge_future(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_receive_bridge_futures
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_request_python_bytes_copied(&self, bytes: usize) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .http_request_python_bytes_messages
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .http_request_python_bytes_copied
                .fetch_add(u64::try_from(bytes).unwrap_or(u64::MAX), Ordering::Relaxed);
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = bytes;
    }

    #[inline]
    fn http_request_python_bytes_materialization_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    fn http_request_python_bytes_materialization_finished(
        &self,
        started: Option<std::time::Instant>,
    ) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_request_python_bytes_materialization_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .http_request_python_bytes_materialization_ns
                .fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn http_body_frame_wait_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    fn http_body_frame_wait_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_body_frame_waits
                .fetch_add(1, Ordering::Relaxed);
            self.counters.http_body_frame_wait_ns.fetch_add(
                started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                Ordering::Relaxed,
            );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn http_request_body_frame_poll_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_request_body_frame_poll_completions
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .http_request_body_frame_ready_wait_ns
                .fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn http_request_body_batch_deadline_flush(&self, elapsed: std::time::Duration) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .http_request_body_batch_deadline_flushes
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .http_request_body_batch_age_at_deadline_ns
                .fetch_add(
                    elapsed.as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = elapsed;
    }

    #[inline]
    fn http_request_body_batch_size_flush(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_request_body_batch_size_flushes
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_request_body_eof_flush(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_request_body_eof_flushes
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_body_data_frame(&self, bytes: usize) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .http_body_data_frames
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .http_body_data_bytes
                .fetch_add(u64::try_from(bytes).unwrap_or(u64::MAX), Ordering::Relaxed);
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = bytes;
    }

    #[inline]
    fn http_body_batch_timeout_flush(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_body_batch_timeout_flushes
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_body_batch_threshold_flush(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_body_batch_threshold_flushes
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_body_channel_send_started(&self, channel_was_full: bool) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .http_body_channel_send_calls
                .fetch_add(1, Ordering::Relaxed);
            if channel_was_full {
                self.counters
                    .http_request_body_channel_full_sends
                    .fetch_add(1, Ordering::Relaxed);
            }
            Some(std::time::Instant::now())
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        {
            let _ = channel_was_full;
            None
        }
    }

    #[inline]
    fn http_body_channel_send_finished(
        &self,
        started: Option<std::time::Instant>,
        channel_was_full: bool,
    ) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            let elapsed = started.elapsed().as_nanos().min(u64::MAX as u128) as u64;
            self.counters
                .http_body_channel_send_wait_ns
                .fetch_add(elapsed, Ordering::Relaxed);
            if channel_was_full {
                self.counters
                    .http_request_body_channel_full_send_wait_ns
                    .fetch_add(elapsed, Ordering::Relaxed);
            }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = (started, channel_was_full);
    }

    #[inline]
    #[cfg(not(feature = "native-tcp"))]
    fn tcp_io_poll_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    #[cfg(not(feature = "native-tcp"))]
    fn tcp_read_poll_finished(
        &self,
        bytes: usize,
        pending: bool,
        started: Option<std::time::Instant>,
        pending_wait_ns: Option<u64>,
    ) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .tcp_read_poll_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .tcp_read_bytes
                .fetch_add(u64::try_from(bytes).unwrap_or(u64::MAX), Ordering::Relaxed);
            if pending {
                self.counters
                    .tcp_read_pending_calls
                    .fetch_add(1, Ordering::Relaxed);
            }
            if let Some(started) = started {
                self.counters.tcp_read_poll_ns.fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
            }
            if let Some(wait_ns) = pending_wait_ns {
                self.counters
                    .tcp_read_pending_wait_ns
                    .fetch_add(wait_ns, Ordering::Relaxed);
            }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = (bytes, pending, started, pending_wait_ns);
    }

    #[inline]
    #[cfg(not(feature = "native-tcp"))]
    fn tcp_write_poll_finished(
        &self,
        bytes: usize,
        pending: bool,
        started: Option<std::time::Instant>,
        pending_wait_ns: Option<u64>,
    ) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .tcp_write_poll_calls
                .fetch_add(1, Ordering::Relaxed);
            self.counters
                .tcp_write_bytes
                .fetch_add(u64::try_from(bytes).unwrap_or(u64::MAX), Ordering::Relaxed);
            if pending {
                self.counters
                    .tcp_write_pending_calls
                    .fetch_add(1, Ordering::Relaxed);
            }
            if let Some(started) = started {
                self.counters.tcp_write_poll_ns.fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
            }
            if let Some(wait_ns) = pending_wait_ns {
                self.counters
                    .tcp_write_pending_wait_ns
                    .fetch_add(wait_ns, Ordering::Relaxed);
            }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = (bytes, pending, started, pending_wait_ns);
    }

    #[inline]
    #[cfg(not(feature = "native-tcp"))]
    fn tcp_flush_poll_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .tcp_flush_poll_calls
                .fetch_add(1, Ordering::Relaxed);
            if let Some(started) = started {
                self.counters.tcp_flush_poll_ns.fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
            }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    #[cfg(not(feature = "native-tcp"))]
    fn tcp_shutdown_poll_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        {
            self.counters
                .tcp_shutdown_poll_calls
                .fetch_add(1, Ordering::Relaxed);
            if let Some(started) = started {
                self.counters.tcp_shutdown_poll_ns.fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
            }
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn http_response_start(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_response_start_messages
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_response_body(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_response_body_messages
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_response_body_queue_full(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .http_response_body_queue_full
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn http_response_body_wait_started(&self) -> Option<std::time::Instant> {
        #[cfg(feature = "runtime-diagnostics")]
        return Some(std::time::Instant::now());
        #[cfg(not(feature = "runtime-diagnostics"))]
        None
    }

    #[inline]
    fn http_response_body_full_send_wait_finished(&self, started: Option<std::time::Instant>) {
        #[cfg(feature = "runtime-diagnostics")]
        if let Some(started) = started {
            self.counters
                .http_response_body_full_send_wait_ns
                .fetch_add(
                    started.elapsed().as_nanos().min(u64::MAX as u128) as u64,
                    Ordering::Relaxed,
                );
        }
        #[cfg(not(feature = "runtime-diagnostics"))]
        let _ = started;
    }

    #[inline]
    fn websocket_receive_bridge_future(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .websocket_receive_bridge_futures
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn websocket_outgoing_message(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .websocket_outgoing_messages
            .fetch_add(1, Ordering::Relaxed);
    }

    #[inline]
    fn websocket_outgoing_queue_full(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.counters
            .websocket_outgoing_queue_full
            .fetch_add(1, Ordering::Relaxed);
    }

    fn report(&self) {
        #[cfg(feature = "runtime-diagnostics")]
        log_error(format_args!(
            concat!(
                "uvicorn-rs-runtime-diagnostics ",
                "asgi_task_schedule_calls={} ",
                "http_requests={} ",
                "http_receive_immediate={} ",
                "http_receive_bridge_futures={} ",
                "http_response_start_messages={} ",
                "http_response_body_messages={} ",
                "http_response_body_queue_full={} ",
                "http_response_body_full_send_wait_ns={} ",
                "http_python_attach_calls={} ",
                "http_python_attach_wait_ns={} ",
                "http_response_start_latency_calls={} ",
                "http_response_start_latency_ns={} ",
                "http_final_body_latency_calls={} ",
                "http_final_body_latency_ns={} ",
                "python_task_starter_calls={} ",
                "python_task_starter_schedule_wait_ns={} ",
                "websocket_receive_bridge_futures={} ",
                "websocket_outgoing_messages={} ",
                "websocket_outgoing_queue_full={} ",
                "http_request_python_bytes_messages={} ",
                "http_request_python_bytes_copied={} ",
                "http_request_python_bytes_materialization_calls={} ",
                "http_request_python_bytes_materialization_ns={} ",
                "http_body_frame_waits={} ",
                "http_body_frame_wait_ns={} ",
                "http_body_data_frames={} ",
                "http_body_data_bytes={} ",
                "http_body_batch_timeout_flushes={} ",
                "http_body_batch_threshold_flushes={} ",
                "http_body_channel_send_calls={} ",
                "http_body_channel_send_wait_ns={} ",
                "http_request_body_frame_poll_completions={} ",
                "http_request_body_frame_ready_wait_ns={} ",
                "http_request_body_batch_deadline_flushes={} ",
                "http_request_body_batch_age_at_deadline_ns={} ",
                "http_request_body_batch_size_flushes={} ",
                "http_request_body_eof_flushes={} ",
                "http_request_body_channel_full_sends={} ",
                "http_request_body_channel_full_send_wait_ns={} ",
                "tcp_read_poll_calls={} ",
                "tcp_read_pending_calls={} ",
                "tcp_read_bytes={} ",
                "tcp_read_poll_ns={} ",
                "tcp_read_pending_wait_ns={} ",
                "tcp_write_poll_calls={} ",
                "tcp_write_pending_calls={} ",
                "tcp_write_bytes={} ",
                "tcp_write_poll_ns={} ",
                "tcp_write_pending_wait_ns={} ",
                "tcp_flush_poll_calls={} ",
                "tcp_flush_poll_ns={} ",
                "tcp_shutdown_poll_calls={} ",
                "tcp_shutdown_poll_ns={}"
            ),
            self.counters
                .asgi_task_schedule_calls
                .load(Ordering::Relaxed),
            self.counters.http_requests.load(Ordering::Relaxed),
            self.counters.http_receive_immediate.load(Ordering::Relaxed),
            self.counters
                .http_receive_bridge_futures
                .load(Ordering::Relaxed),
            self.counters
                .http_response_start_messages
                .load(Ordering::Relaxed),
            self.counters
                .http_response_body_messages
                .load(Ordering::Relaxed),
            self.counters
                .http_response_body_queue_full
                .load(Ordering::Relaxed),
            self.counters
                .http_response_body_full_send_wait_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_python_attach_calls
                .load(Ordering::Relaxed),
            self.counters
                .http_python_attach_wait_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_response_start_latency_calls
                .load(Ordering::Relaxed),
            self.counters
                .http_response_start_latency_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_final_body_latency_calls
                .load(Ordering::Relaxed),
            self.counters
                .http_final_body_latency_ns
                .load(Ordering::Relaxed),
            self.counters
                .python_task_starter_calls
                .load(Ordering::Relaxed),
            self.counters
                .python_task_starter_schedule_wait_ns
                .load(Ordering::Relaxed),
            self.counters
                .websocket_receive_bridge_futures
                .load(Ordering::Relaxed),
            self.counters
                .websocket_outgoing_messages
                .load(Ordering::Relaxed),
            self.counters
                .websocket_outgoing_queue_full
                .load(Ordering::Relaxed),
            self.counters
                .http_request_python_bytes_messages
                .load(Ordering::Relaxed),
            self.counters
                .http_request_python_bytes_copied
                .load(Ordering::Relaxed),
            self.counters
                .http_request_python_bytes_materialization_calls
                .load(Ordering::Relaxed),
            self.counters
                .http_request_python_bytes_materialization_ns
                .load(Ordering::Relaxed),
            self.counters.http_body_frame_waits.load(Ordering::Relaxed),
            self.counters
                .http_body_frame_wait_ns
                .load(Ordering::Relaxed),
            self.counters.http_body_data_frames.load(Ordering::Relaxed),
            self.counters.http_body_data_bytes.load(Ordering::Relaxed),
            self.counters
                .http_body_batch_timeout_flushes
                .load(Ordering::Relaxed),
            self.counters
                .http_body_batch_threshold_flushes
                .load(Ordering::Relaxed),
            self.counters
                .http_body_channel_send_calls
                .load(Ordering::Relaxed),
            self.counters
                .http_body_channel_send_wait_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_frame_poll_completions
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_frame_ready_wait_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_batch_deadline_flushes
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_batch_age_at_deadline_ns
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_batch_size_flushes
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_eof_flushes
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_channel_full_sends
                .load(Ordering::Relaxed),
            self.counters
                .http_request_body_channel_full_send_wait_ns
                .load(Ordering::Relaxed),
            self.counters.tcp_read_poll_calls.load(Ordering::Relaxed),
            self.counters.tcp_read_pending_calls.load(Ordering::Relaxed),
            self.counters.tcp_read_bytes.load(Ordering::Relaxed),
            self.counters.tcp_read_poll_ns.load(Ordering::Relaxed),
            self.counters
                .tcp_read_pending_wait_ns
                .load(Ordering::Relaxed),
            self.counters.tcp_write_poll_calls.load(Ordering::Relaxed),
            self.counters
                .tcp_write_pending_calls
                .load(Ordering::Relaxed),
            self.counters.tcp_write_bytes.load(Ordering::Relaxed),
            self.counters.tcp_write_poll_ns.load(Ordering::Relaxed),
            self.counters
                .tcp_write_pending_wait_ns
                .load(Ordering::Relaxed),
            self.counters.tcp_flush_poll_calls.load(Ordering::Relaxed),
            self.counters.tcp_flush_poll_ns.load(Ordering::Relaxed),
            self.counters
                .tcp_shutdown_poll_calls
                .load(Ordering::Relaxed),
            self.counters.tcp_shutdown_poll_ns.load(Ordering::Relaxed),
        ));
    }
}

struct ServeOptions {
    host: String,
    port: u16,
    backlog: i32,
    timeout_keep_alive: std::time::Duration,
    root_path: String,
    tcp_tls: Option<TlsAcceptor>,
    quic_config: Option<quinn::ServerConfig>,
    graceful_timeout: Option<std::time::Duration>,
    lifespan_mode: LifespanMode,
    default_headers: Vec<(HeaderName, HeaderValue)>,
    date_header: bool,
    ws_max_size: usize,
    websocket_keepalive: WebSocketKeepaliveConfig,
    concurrency_limit_observer: Option<uvicorn_rs::ConcurrencyLimitObserver>,
    #[cfg(feature = "native-tcp")]
    limit_concurrency: Option<usize>,
}

struct ServerContext {
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    server_addr: SocketAddr,
    root_path: String,
    tcp_tls: Option<TlsAcceptor>,
    default_headers: Vec<(HeaderName, HeaderValue)>,
    date_header: bool,
    ws_max_size: usize,
    websocket_keepalive: WebSocketKeepaliveConfig,
    concurrency_limit_observer: Option<uvicorn_rs::ConcurrencyLimitObserver>,
    #[cfg(feature = "native-tcp")]
    limit_concurrency: Option<usize>,
    state: Option<Arc<Py<PyDict>>>,
    #[cfg(not(feature = "native-tcp"))]
    websocket_tasks: WebSocketTasks,
    request_body_tasks: RequestBodyTasks,
    #[cfg(coverage)]
    completed_request_body_pumps: Arc<AtomicUsize>,
    diagnostics: RuntimeDiagnostics,
    cancellation: CancellationToken,
    graceful_timeout: Option<std::time::Duration>,
    pending_python_tasks: TaskTracker,
    force_application_shutdown: CancellationToken,
}

#[derive(Clone, Copy)]
struct WebSocketKeepaliveConfig {
    interval: Option<std::time::Duration>,
    timeout: Option<std::time::Duration>,
}

struct WebSocketDriverContext {
    state: Arc<AtomicU8>,
    connection_closed: ConnectionClosed,
    cancellation: CancellationToken,
    keepalive: WebSocketKeepaliveConfig,
}

impl WebSocketKeepaliveConfig {
    fn from_seconds(interval: Option<f64>, timeout: Option<f64>) -> PyResult<Self> {
        let interval = match interval {
            Some(seconds) if seconds <= 0.0 => None,
            Some(seconds) => Some(Self::duration_from_seconds(seconds, "ws_ping_interval")?),
            None => None,
        };
        let timeout = match timeout {
            Some(seconds) if seconds < 0.0 => Some(std::time::Duration::ZERO),
            Some(seconds) => Some(Self::duration_from_seconds(seconds, "ws_ping_timeout")?),
            None => None,
        };
        Ok(Self { interval, timeout })
    }

    fn duration_from_seconds(seconds: f64, setting: &str) -> PyResult<std::time::Duration> {
        if !seconds.is_finite() {
            return Err(PyValueError::new_err(format!(
                "{setting} must be a finite number of seconds"
            )));
        }
        std::time::Duration::try_from_secs_f64(seconds).map_err(|_| {
            PyValueError::new_err(format!(
                "{setting} exceeds the supported monotonic deadline range"
            ))
        })
    }
}

#[derive(Debug)]
enum AsgiEventType {
    HttpResponseStart,
    HttpResponseBody,
    WebSocketAccept,
    WebSocketClose,
    WebSocketSend,
    LifespanStartupComplete,
    LifespanStartupFailed,
    LifespanShutdownComplete,
    LifespanShutdownFailed,
    Other(String),
}

impl AsgiEventType {
    fn as_str(&self) -> &str {
        match self {
            Self::HttpResponseStart => "http.response.start",
            Self::HttpResponseBody => "http.response.body",
            Self::WebSocketAccept => "websocket.accept",
            Self::WebSocketClose => "websocket.close",
            Self::WebSocketSend => "websocket.send",
            Self::LifespanStartupComplete => "lifespan.startup.complete",
            Self::LifespanStartupFailed => "lifespan.startup.failed",
            Self::LifespanShutdownComplete => "lifespan.shutdown.complete",
            Self::LifespanShutdownFailed => "lifespan.shutdown.failed",
            Self::Other(value) => value,
        }
    }
}

fn classify_asgi_event_type(py: Python<'_>, value: Bound<'_, PyAny>) -> PyResult<AsgiEventType> {
    value.cast::<PyString>()?;

    // Exact built-in strings can be compared to cached Python string objects
    // without first allocating a Rust String. Subclasses use the old extraction
    // path so their established conversion behavior is kept.
    if value.is_exact_instance_of::<PyString>() {
        if coverage_value!(
            AsgiEventTypeHttpResponseStartEq,
            value.eq(pyo3::intern!(py, "http.response.start"))
        )? {
            return Ok(AsgiEventType::HttpResponseStart);
        }
        if coverage_value!(
            AsgiEventTypeHttpResponseBodyEq,
            value.eq(pyo3::intern!(py, "http.response.body"))
        )? {
            return Ok(AsgiEventType::HttpResponseBody);
        }
        if coverage_value!(
            AsgiEventTypeWebSocketAcceptEq,
            value.eq(pyo3::intern!(py, "websocket.accept"))
        )? {
            return Ok(AsgiEventType::WebSocketAccept);
        }
        if coverage_value!(
            AsgiEventTypeWebSocketCloseEq,
            value.eq(pyo3::intern!(py, "websocket.close"))
        )? {
            return Ok(AsgiEventType::WebSocketClose);
        }
        if coverage_value!(
            AsgiEventTypeWebSocketSendEq,
            value.eq(pyo3::intern!(py, "websocket.send"))
        )? {
            return Ok(AsgiEventType::WebSocketSend);
        }
        if coverage_value!(
            AsgiEventTypeLifespanStartupCompleteEq,
            value.eq(pyo3::intern!(py, "lifespan.startup.complete"))
        )? {
            return Ok(AsgiEventType::LifespanStartupComplete);
        }
        if coverage_value!(
            AsgiEventTypeLifespanStartupFailedEq,
            value.eq(pyo3::intern!(py, "lifespan.startup.failed"))
        )? {
            return Ok(AsgiEventType::LifespanStartupFailed);
        }
        if coverage_value!(
            AsgiEventTypeLifespanShutdownCompleteEq,
            value.eq(pyo3::intern!(py, "lifespan.shutdown.complete"))
        )? {
            return Ok(AsgiEventType::LifespanShutdownComplete);
        }
        if coverage_value!(
            AsgiEventTypeLifespanShutdownFailedEq,
            value.eq(pyo3::intern!(py, "lifespan.shutdown.failed"))
        )? {
            return Ok(AsgiEventType::LifespanShutdownFailed);
        }
    }

    let event_type = coverage_value!(AsgiEventTypeExtract, value.extract::<String>())?;
    Ok(match event_type.as_str() {
        "http.response.start" => AsgiEventType::HttpResponseStart,
        "http.response.body" => AsgiEventType::HttpResponseBody,
        "websocket.accept" => AsgiEventType::WebSocketAccept,
        "websocket.close" => AsgiEventType::WebSocketClose,
        "websocket.send" => AsgiEventType::WebSocketSend,
        "lifespan.startup.complete" => AsgiEventType::LifespanStartupComplete,
        "lifespan.startup.failed" => AsgiEventType::LifespanStartupFailed,
        "lifespan.shutdown.complete" => AsgiEventType::LifespanShutdownComplete,
        "lifespan.shutdown.failed" => AsgiEventType::LifespanShutdownFailed,
        _ => AsgiEventType::Other(event_type),
    })
}

#[derive(Clone)]
enum ConnectionClosed {
    #[cfg(any(not(feature = "native-tcp"), coverage))]
    Watch(watch::Receiver<bool>),
    #[cfg(feature = "native-tcp")]
    Lifetime(uvicorn_rs::ConnectionLifetime),
    #[cfg(feature = "native-tcp")]
    Native {
        lifetime: uvicorn_rs::ConnectionLifetime,
        peer_read_half_closed: uvicorn_rs::PeerReadHalfClosed,
        peer_read_failed: uvicorn_rs::PeerReadFailed,
    },
}

impl ConnectionClosed {
    fn is_closed(&self) -> bool {
        match self {
            #[cfg(any(not(feature = "native-tcp"), coverage))]
            Self::Watch(closed) => *closed.borrow(),
            #[cfg(feature = "native-tcp")]
            Self::Lifetime(lifetime) => lifetime.is_closed(),
            #[cfg(feature = "native-tcp")]
            Self::Native {
                lifetime,
                peer_read_half_closed,
                peer_read_failed,
            } => {
                lifetime.is_closed()
                    || peer_read_half_closed.is_read_half_closed()
                    || peer_read_failed.error_kind().is_some()
            }
        }
    }

    async fn wait_until_closed_with_coverage_fault(
        &mut self,
        allow_lifetime_completion_fault: bool,
    ) {
        #[cfg(not(coverage))]
        let _ = allow_lifetime_completion_fault;
        match self {
            #[cfg(any(not(feature = "native-tcp"), coverage))]
            Self::Watch(closed) => {
                let _ = closed.wait_for(|is_closed| *is_closed).await;
            }
            #[cfg(feature = "native-tcp")]
            Self::Lifetime(lifetime) => lifetime.wait_until_closed().await,
            #[cfg(feature = "native-tcp")]
            Self::Native {
                lifetime,
                peer_read_half_closed,
                peer_read_failed,
            } => {
                tokio::select! {
                    _ = async {
                        #[cfg(coverage)]
                        if allow_lifetime_completion_fault
                            && coverage_fault_take(CoverageFaultPoint::HttpConnectionLifetimeWaitComplete)
                        {
                            return;
                        }
                        lifetime.wait_until_closed().await;
                    } => {},
                    _ = peer_read_half_closed.wait_until_read_half_closed() => {},
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(
                            CoverageFaultPoint::HttpConnectionPeerReadFailedWaitComplete,
                        ) {
                            return;
                        }
                        let _ = peer_read_failed.wait_until_failed().await;
                    } => {},
                }
            }
        }
    }

    async fn wait_for_peer_read_failure(&mut self) {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::WebSocketPeerReadFailureWatchFallback) {
            let (_closed_sender, closed_receiver) = watch::channel(false);
            *self = Self::Watch(closed_receiver);
        }
        #[cfg(feature = "native-tcp")]
        if let Self::Native {
            peer_read_failed, ..
        } = self
        {
            #[cfg(coverage)]
            let inject_failure =
                coverage_fault_take(CoverageFaultPoint::WebSocketPeerReadFailureWaitComplete);
            #[cfg(not(coverage))]
            let inject_failure = false;
            #[cfg(coverage)]
            let inject_unavailable =
                coverage_fault_take(CoverageFaultPoint::WebSocketPeerReadFailureUnavailable);
            #[cfg(not(coverage))]
            let inject_unavailable = false;
            if peer_read_failed.error_kind().is_some()
                || inject_failure
                || (!inject_unavailable && peer_read_failed.wait_until_failed().await.is_ok())
            {
                return;
            }
        }
        // A clean reader shutdown is not evidence of a reset. Keep this
        // branch pending so a TCP half-close can still receive a response.
        std::future::pending::<()>().await;
    }

    async fn wait_until_body_pump_stops(&mut self) {
        match self {
            #[cfg(any(not(feature = "native-tcp"), coverage))]
            Self::Watch(closed) => {
                let _ = closed.wait_for(|is_closed| *is_closed).await;
            }
            #[cfg(feature = "native-tcp")]
            Self::Lifetime(lifetime) => lifetime.wait_until_closed().await,
            #[cfg(feature = "native-tcp")]
            Self::Native {
                lifetime,
                peer_read_half_closed,
                ..
            } => {
                tokio::select! {
                    _ = lifetime.wait_until_closed() => {},
                    _ = peer_read_half_closed.wait_until_read_half_closed() => {},
                }
            }
        }
    }
}

#[derive(Clone)]
struct ConnectionContext {
    server: Arc<ServerContext>,
    peer_addr: SocketAddr,
    transport_scheme: &'static str,
    connection_closed: ConnectionClosed,
    #[cfg(feature = "native-tcp")]
    native_upgrade: Option<uvicorn_rs::ConnectionUpgrade>,
}

#[cfg(feature = "native-tcp")]
#[derive(Clone)]
struct NativeAsgiService {
    server: Arc<ServerContext>,
}

#[cfg(feature = "native-tcp")]
impl tower_service::Service<Request<Incoming>> for NativeAsgiService {
    type Response = Response<ResponseBody>;
    type Error = std::io::Error;
    type Future = Pin<Box<dyn Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(&mut self, _context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, request: Request<Incoming>) -> Self::Future {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerConnectionTaskServiceError) {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "coverage-injected native HTTP service error",
                ))
            });
        }
        let connection_info = request
            .extensions()
            .get::<uvicorn_rs::ConnectionInfo>()
            .cloned();
        #[cfg(coverage)]
        let connection_info =
            if coverage_fault_take(CoverageFaultPoint::ServerConnectionInfoMissing) {
                None
            } else {
                connection_info
            };
        let Some(connection_info) = connection_info else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native TCP transport omitted connection metadata",
                ))
            });
        };
        let connection_lifetime = request
            .extensions()
            .get::<uvicorn_rs::ConnectionLifetime>()
            .cloned();
        #[cfg(coverage)]
        let connection_lifetime =
            if coverage_fault_take(CoverageFaultPoint::ServerConnectionLifetimeMissing) {
                None
            } else {
                connection_lifetime
            };
        let Some(connection_lifetime) = connection_lifetime else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native TCP transport omitted connection lifetime",
                ))
            });
        };
        let peer_read_half_closed = request
            .extensions()
            .get::<uvicorn_rs::PeerReadHalfClosed>()
            .cloned();
        #[cfg(coverage)]
        let peer_read_half_closed =
            if coverage_fault_take(CoverageFaultPoint::ServerPeerReadHalfClosedMissing) {
                None
            } else {
                peer_read_half_closed
            };
        let Some(peer_read_half_closed) = peer_read_half_closed else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native TCP transport omitted the peer-read half-close observer",
                ))
            });
        };
        let peer_read_failed = request
            .extensions()
            .get::<uvicorn_rs::PeerReadFailed>()
            .cloned();
        #[cfg(coverage)]
        let peer_read_failed =
            if coverage_fault_take(CoverageFaultPoint::ServerPeerReadFailedMissing) {
                None
            } else {
                peer_read_failed
            };
        let Some(peer_read_failed) = peer_read_failed else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native TCP transport omitted the peer-read failure observer",
                ))
            });
        };
        let native_upgrade = request
            .extensions()
            .get::<uvicorn_rs::ConnectionUpgrade>()
            .cloned();
        #[cfg(coverage)]
        let native_upgrade = if is_websocket_upgrade(&request)
            && coverage_fault_take(CoverageFaultPoint::WebSocketNativeUpgradeMissing)
        {
            None
        } else {
            native_upgrade
        };
        let context = ConnectionContext {
            server: Arc::clone(&self.server),
            peer_addr: connection_info.peer_addr(),
            transport_scheme: if connection_info.tls().is_some() {
                "https"
            } else {
                "http"
            },
            connection_closed: ConnectionClosed::Native {
                lifetime: connection_lifetime,
                peer_read_half_closed,
                peer_read_failed,
            },
            native_upgrade,
        };
        let server = Arc::clone(&context.server);
        Box::pin(async move {
            let response = if is_websocket_upgrade(&request) {
                Ok(handle_websocket_request(request, context).await)
            } else {
                handle_request(request, context).await
            }?;
            apply_default_response_headers(&server, response)
        })
    }
}

#[cfg(feature = "native-tcp")]
#[derive(Clone)]
struct NativeHttp3AsgiService {
    server: Arc<ServerContext>,
}

#[cfg(feature = "native-tcp")]
impl tower_service::Service<Request<uvicorn_rs::Http3RequestBody>> for NativeHttp3AsgiService {
    type Response = Response<ResponseBody>;
    type Error = std::io::Error;
    type Future = Pin<Box<dyn Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn poll_ready(&mut self, _context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, request: Request<uvicorn_rs::Http3RequestBody>) -> Self::Future {
        let connection_info = request
            .extensions()
            .get::<uvicorn_rs::ConnectionInfo>()
            .cloned();
        #[cfg(coverage)]
        let connection_info = if coverage_fault_take(CoverageFaultPoint::Http3ConnectionInfoMissing)
        {
            None
        } else {
            connection_info
        };
        let Some(connection_info) = connection_info else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native HTTP/3 transport omitted connection metadata",
                ))
            });
        };
        let connection_lifetime = request
            .extensions()
            .get::<uvicorn_rs::ConnectionLifetime>()
            .cloned();
        #[cfg(coverage)]
        let connection_lifetime =
            if coverage_fault_take(CoverageFaultPoint::Http3ConnectionLifetimeMissing) {
                None
            } else {
                connection_lifetime
            };
        let Some(connection_lifetime) = connection_lifetime else {
            return Box::pin(async {
                Err(std::io::Error::other(
                    "native HTTP/3 transport omitted connection lifetime",
                ))
            });
        };
        let context = ConnectionContext {
            server: Arc::clone(&self.server),
            peer_addr: connection_info.peer_addr(),
            // HTTP/3 uses QUIC, whose handshake is secured with TLS.
            transport_scheme: "https",
            connection_closed: ConnectionClosed::Lifetime(connection_lifetime),
            native_upgrade: None,
        };
        let server = Arc::clone(&context.server);
        Box::pin(async move {
            let response = handle_http3_asgi_request(request, context).await?;
            apply_default_response_headers(&server, response)
        })
    }
}

#[cfg(not(feature = "native-tcp"))]
struct ActiveHttpRequest {
    active_http_requests: Arc<AtomicUsize>,
    read_eof_waker: Arc<AtomicWaker>,
}

#[cfg(not(feature = "native-tcp"))]
impl ActiveHttpRequest {
    fn new(active_http_requests: Arc<AtomicUsize>, read_eof_waker: Arc<AtomicWaker>) -> Self {
        active_http_requests.fetch_add(1, Ordering::AcqRel);
        Self {
            active_http_requests,
            read_eof_waker,
        }
    }
}

#[cfg(not(feature = "native-tcp"))]
impl Drop for ActiveHttpRequest {
    fn drop(&mut self) {
        if self.active_http_requests.fetch_sub(1, Ordering::AcqRel) == 1 {
            self.read_eof_waker.wake();
        }
    }
}

struct AbortOnDrop<T> {
    handle: tokio::task::JoinHandle<T>,
    guard: TaskAbortGuard,
}

impl<T> AbortOnDrop<T> {
    fn new(handle: tokio::task::JoinHandle<T>) -> Self {
        Self {
            guard: TaskAbortGuard {
                handle: Some(handle.abort_handle()),
                keep_running_if: None,
            },
            handle,
        }
    }

    fn as_mut(&mut self) -> &mut tokio::task::JoinHandle<T> {
        &mut self.handle
    }

    fn into_handle(mut self) -> tokio::task::JoinHandle<T> {
        self.guard.handle.take();
        self.handle
    }

    fn leave_running(&mut self) {
        self.guard.handle.take();
    }

    fn leave_running_if(&mut self, condition: Arc<AtomicBool>) {
        self.guard.keep_running_if = Some(condition);
    }
}

struct TaskAbortGuard {
    handle: Option<tokio::task::AbortHandle>,
    keep_running_if: Option<Arc<AtomicBool>>,
}

impl Drop for TaskAbortGuard {
    fn drop(&mut self) {
        if let Some(handle) = self.handle.take() {
            let keep_running = self
                .keep_running_if
                .as_ref()
                .is_some_and(|condition| condition.load(Ordering::Acquire));
            if !keep_running {
                handle.abort();
            }
        }
    }
}

struct RequestCancellationGuard {
    cancellation: CancellationToken,
    armed: bool,
}

impl RequestCancellationGuard {
    fn new(cancellation: CancellationToken) -> Self {
        Self {
            cancellation,
            armed: true,
        }
    }

    fn disarm(&mut self) {
        self.armed = false;
    }
}

impl Drop for RequestCancellationGuard {
    fn drop(&mut self) {
        if self.armed {
            self.cancellation.cancel();
        }
    }
}

struct ResponseStart {
    status: StatusCode,
    headers: HeaderMap,
}

#[derive(Debug)]
struct InvalidAsgiResponseStart;

impl fmt::Display for InvalidAsgiResponseStart {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("ASGI response.start was attempted but not accepted")
    }
}

impl StdError for InvalidAsgiResponseStart {}

#[derive(Debug)]
struct WebSocketHandshakeError {
    response_body: String,
}

impl fmt::Display for WebSocketHandshakeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.response_body)
    }
}

impl StdError for WebSocketHandshakeError {}

struct BodyChunk {
    body: Bytes,
    more_body: bool,
}

enum RequestBody {
    Single(Bytes),
    Segments { segments: Vec<Bytes>, len: usize },
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum RequestBodySendMode {
    Regular,
    Final,
    #[cfg(coverage)]
    ContinueAfterStop,
}

struct RequestBodySendContext<'a> {
    diagnostics: &'a RuntimeDiagnostics,
    _mode: RequestBodySendMode,
}

impl RequestBody {
    fn from_segments(segments: Vec<Bytes>, len: usize) -> Self {
        let single_segment: Result<[Bytes; 1], Vec<Bytes>> = segments.try_into();
        match single_segment {
            Ok([body]) => Self::Single(body),
            Err(segments) => Self::Segments { segments, len },
        }
    }

    fn take_batch(segments: &mut Vec<Bytes>, len: &mut usize) -> Self {
        Self::from_segments(std::mem::take(segments), std::mem::take(len))
    }

    fn len(&self) -> usize {
        match self {
            Self::Single(body) => body.len(),
            Self::Segments { len, .. } => *len,
        }
    }

    fn into_py_bytes<'py>(self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        match self {
            Self::Single(body) => Ok(PyBytes::new(py, &body)),
            Self::Segments { segments, len } => PyBytes::new_with(py, len, |output| {
                let mut offset: usize = {
                    #[cfg(coverage)]
                    {
                        if coverage_fault_take(
                            CoverageFaultPoint::HttpRequestBodySegmentLengthOverflow,
                        ) {
                            usize::MAX
                        } else if coverage_fault_take(
                            CoverageFaultPoint::HttpRequestBodySegmentOutOfBounds,
                        ) {
                            len
                        } else {
                            0
                        }
                    }
                    #[cfg(not(coverage))]
                    {
                        0
                    }
                };
                for segment in &segments {
                    let Some(end) = offset.checked_add(segment.len()) else {
                        return Err(PyValueError::new_err(
                            "request body segment length overflowed",
                        ));
                    };
                    let Some(destination) = output.get_mut(offset..end) else {
                        return Err(PyValueError::new_err(
                            "request body segment exceeded its Python bytes allocation",
                        ));
                    };
                    destination.copy_from_slice(segment);
                    offset = end;
                }
                Ok(())
            }),
        }
    }
}

struct RequestMessage {
    body: RequestBody,
    more_body: bool,
    disconnected: bool,
}

fn make_http_request_message(
    py: Python<'_>,
    request: Option<RequestMessage>,
    request_disconnected: &AtomicBool,
    diagnostics: &RuntimeDiagnostics,
) -> PyResult<Py<PyAny>> {
    let message = PyDict::new(py);
    if let Some(request) = request.filter(|request| !request.disconnected) {
        diagnostics.http_request_python_bytes_copied(request.body.len());
        coverage_try!(
            HttpRequestTypeSetItem,
            message.set_item("type", "http.request")
        );
        let body_materialization_started =
            diagnostics.http_request_python_bytes_materialization_started();
        let body = request.body.into_py_bytes(py);
        diagnostics
            .http_request_python_bytes_materialization_finished(body_materialization_started);
        let body = body?;
        coverage_try!(HttpRequestBodySetItem, message.set_item("body", body));
        coverage_try!(
            HttpRequestMoreBodySetItem,
            message.set_item("more_body", request.more_body)
        );
    } else {
        request_disconnected.store(true, Ordering::Release);
        coverage_try!(
            HttpRequestDisconnectTypeSetItem,
            message.set_item("type", "http.disconnect")
        );
    }
    Ok(message.into_any().unbind())
}

#[pyclass]
struct PythonTaskStarter {
    awaitable: Py<PyAny>,
    task_sender: Option<oneshot::Sender<Py<PyAny>>>,
    result_sender: Option<oneshot::Sender<PyResult<Py<PyAny>>>>,
    completion_signal: watch::Sender<bool>,
    locals: TaskLocals,
    cancellation_tracker: TaskTracker,
    #[cfg(feature = "runtime-diagnostics")]
    diagnostics: RuntimeDiagnostics,
    #[cfg(feature = "runtime-diagnostics")]
    schedule_started: std::time::Instant,
}

#[pymethods]
impl PythonTaskStarter {
    fn __call__(&mut self) -> PyResult<()> {
        #[cfg(feature = "runtime-diagnostics")]
        self.diagnostics
            .python_task_starter_started(self.schedule_started);
        Python::attach(|py| {
            #[cfg(coverage)]
            let prelude_close_error =
                coverage_fault_take(CoverageFaultPoint::PythonTaskStarterPreludeCloseError);
            let task_start_result = (|| -> PyResult<()> {
                let asyncio = coverage_value!(PythonTaskStarterImportAsyncio, py.import("asyncio"));
                #[cfg(coverage)]
                let asyncio = if prelude_close_error {
                    Err(PyRuntimeError::new_err(
                        "coverage-injected task setup failure before bridge coroutine close",
                    ))
                } else {
                    asyncio
                };
                let asyncio = asyncio?;
                #[cfg(coverage)]
                let inline_registration_error = coverage_fault_take(
                    CoverageFaultPoint::PythonTaskStarterInlineCompletionRegistrationError,
                );
                #[cfg(coverage)]
                let inline_borrow_conflict = coverage_fault_take(
                    CoverageFaultPoint::PythonTaskStarterInlineCompletionBorrowConflict,
                );
                #[cfg(coverage)]
                let inline_completion =
                    coverage_fault_take(CoverageFaultPoint::PythonTaskStarterInlineCompletion);
                #[cfg(coverage)]
                let failure_cleanup_error = coverage_fault_take(
                    CoverageFaultPoint::PythonTaskStarterFailureCleanupScheduleError,
                );
                let completion = coverage_value!(
                    PythonTaskCompletionAllocate,
                    Py::new(
                        py,
                        PyTaskCompletion {
                            sender: None,
                            completion_signal: self.completion_signal.clone(),
                            registering: true,
                            buffered_result: None,
                            #[cfg(coverage)]
                            synthetic_inline_call: inline_registration_error
                                || inline_borrow_conflict
                                || inline_completion,
                        },
                    )
                )?;
                let task = coverage_value!(
                    PythonTaskStarterEnsureFuture,
                    asyncio.call_method1("ensure_future", (self.awaitable.bind(py),))
                )?;
                // Retain the result sender until registration commits. A callback
                // or completion-state borrow can fail after ensure_future starts
                // the task; this owner can still cancel it and send that exact error.
                let registration_result = (|| -> PyResult<()> {
                    #[cfg(coverage)]
                    if inline_registration_error || inline_borrow_conflict || inline_completion {
                        // Exercise the real PyO3 call rejection while the callback
                        // is borrowed, rather than substituting an early error.
                        let _borrow = inline_borrow_conflict
                            .then(|| completion.try_borrow_mut(py).ok())
                            .flatten();
                        completion.bind(py).call1((&task,))?;
                        let _ = task.call_method0("cancel");
                    }
                    let callback_result = coverage_value!(
                        PythonTaskStarterAddDoneCallback,
                        task.call_method1("add_done_callback", (completion.bind(py),))
                    );
                    #[cfg(coverage)]
                    let registration_error_borrow_conflict = coverage_fault_take(
                        CoverageFaultPoint::PythonTaskStarterRegistrationErrorBorrowConflict,
                    );
                    #[cfg(coverage)]
                    let callback_result = if inline_registration_error {
                        Err(PyRuntimeError::new_err(
                            "coverage-injected callback registration failure after inline completion",
                        ))
                    } else if registration_error_borrow_conflict {
                        Err(PyRuntimeError::new_err(
                            "coverage-injected callback registration failure before completion-state borrow",
                        ))
                    } else if failure_cleanup_error {
                        Err(PyRuntimeError::new_err(
                            "coverage-injected callback registration failure before cancellation cleanup scheduling",
                        ))
                    } else {
                        callback_result
                    };
                    if let Err(error) = callback_result {
                        #[cfg(coverage)]
                        let _borrow = registration_error_borrow_conflict
                            .then(|| completion.try_borrow_mut(py).ok())
                            .flatten();
                        // Failure to clean up callback state must not replace the
                        // original registration exception. The result sender has
                        // not transferred, so the outer owner can deliver it.
                        if let Ok(mut completion) = completion.try_borrow_mut(py) {
                            completion.registering = false;
                            completion.buffered_result.take();
                        }
                        return Err(error);
                    }
                    #[cfg(coverage)]
                    let _borrow = coverage_fault_take(
                        CoverageFaultPoint::PythonTaskStarterRegistrationSuccessBorrowConflict,
                    )
                    .then(|| completion.try_borrow_mut(py).ok())
                    .flatten();
                    let mut completion = completion.try_borrow_mut(py)?;
                    completion.sender = self.result_sender.take();
                    completion.registering = false;
                    if let Some(result) = completion.buffered_result.take() {
                        completion.complete(result);
                    }
                    #[cfg(coverage)]
                    if inline_completion {
                        // The injected callback runs before the real task finishes.
                        // Its buffered error is not a cancellation cleanup receipt.
                        track_python_task_completion(
                            &self.cancellation_tracker,
                            &self.completion_signal,
                        );
                    }
                    Ok(())
                })();
                if let Err(error) = registration_result {
                    // Run cancellation on this owning Python loop before yielding.
                    let _ = task.call_method0("cancel");
                    {
                        let tracker = &self.cancellation_tracker;
                        // Cancellation can run an asynchronous finally block,
                        // including with Python's eager task factory. Await the
                        // actual task on its captured loop and context rather than
                        // treating delivery of the registration error as cleanup.
                        #[cfg(coverage)]
                        let cleanup = if failure_cleanup_error {
                            Err(PyRuntimeError::new_err(
                                "coverage-injected cancellation cleanup scheduling failure",
                            ))
                        } else {
                            pyo3_async_runtimes::into_future_with_locals(&self.locals, task.clone())
                        };
                        #[cfg(not(coverage))]
                        let cleanup = pyo3_async_runtimes::into_future_with_locals(
                            &self.locals,
                            task.clone(),
                        );
                        match cleanup {
                            Ok(cleanup) => {
                                tracker.spawn_on(
                                    async move {
                                        if let Err(error) = cleanup.await {
                                            Python::attach(|py| error.print(py));
                                        }
                                    },
                                    pyo3_async_runtimes::tokio::get_runtime().handle(),
                                );
                            }
                            Err(cleanup_error) => {
                                cleanup_error.print(py);
                                // An admitted callback can still observe completion
                                // if scheduling the additional awaiter failed.
                                // Keep that real signal in the shutdown accounting.
                                track_python_task_completion(tracker, &self.completion_signal);
                            }
                        }
                    }
                    send_python_task_result(&mut self.result_sender, Err(error));
                }
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::PythonTaskStarterTaskSenderMissing) {
                    self.task_sender.take();
                }
                if let Some(sender) = self.task_sender.take() {
                    if let Err(task) = sender.send(task.unbind()) {
                        let _ = task.bind(py).call_method0("cancel");
                        track_python_task_completion(
                            &self.cancellation_tracker,
                            &self.completion_signal,
                        );
                    }
                } else {
                    let _ = task.call_method0("cancel");
                    track_python_task_completion(
                        &self.cancellation_tracker,
                        &self.completion_signal,
                    );
                }
                Ok(())
            })();
            if let Err(error) = task_start_result {
                // These failures precede receipt of an actual Python task.
                // Close the bridge coroutine we still own, then deliver the
                // original error through Rust rather than asyncio's callback
                // exception handler. The starter's completion sender closes
                // normally, so cancelled pending starters remain bounded.
                let close_result = self.awaitable.bind(py).call_method0("close");
                #[cfg(coverage)]
                let close_result = if prelude_close_error {
                    // Run the actual close before reporting a secondary failure:
                    // the probe must not leave an un-awaited bridge coroutine.
                    Err(PyRuntimeError::new_err(
                        "coverage-injected bridge coroutine close failure",
                    ))
                } else {
                    close_result
                };
                if let Err(close_error) = close_result {
                    close_error.print(py);
                }
                send_python_task_result(&mut self.result_sender, Err(error));
            }
            Ok(())
        })
    }
}

#[pyclass]
struct PyTaskCompletion {
    sender: Option<oneshot::Sender<PyResult<Py<PyAny>>>>,
    completion_signal: watch::Sender<bool>,
    registering: bool,
    buffered_result: Option<PyResult<Py<PyAny>>>,
    #[cfg(coverage)]
    synthetic_inline_call: bool,
}

impl PyTaskCompletion {
    fn complete(&mut self, result: PyResult<Py<PyAny>>) {
        send_python_task_result(&mut self.sender, result);
    }
}

fn send_python_task_result(
    sender: &mut Option<oneshot::Sender<PyResult<Py<PyAny>>>>,
    result: PyResult<Py<PyAny>>,
) {
    // Both registration failure and the admitted callback consume the same
    // one-shot result contract. A dropped receiver never causes a panic.
    if let Some(sender) = sender.take() {
        let _ = sender.send(result);
    }
}

fn track_python_task_completion(tracker: &TaskTracker, completed: &watch::Sender<bool>) {
    let mut completed = completed.subscribe();
    tracker.spawn_on(
        async move {
            let _ = completed.wait_for(|completed| *completed).await;
        },
        pyo3_async_runtimes::tokio::get_runtime().handle(),
    );
}

#[pymethods]
impl PyTaskCompletion {
    fn __call__(&mut self, task: &Bound<'_, PyAny>) -> PyResult<()> {
        let result = task.call_method0("result").map(Bound::unbind);
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::PythonTaskCompletionResultReceiverClosed) {
            self.sender.take();
        }
        if self.registering {
            self.buffered_result = Some(result);
        } else {
            self.complete(result);
        }
        #[cfg(coverage)]
        let synthetic_inline_call = std::mem::take(&mut self.synthetic_inline_call);
        #[cfg(not(coverage))]
        let synthetic_inline_call = false;
        if !synthetic_inline_call {
            // Error delivery from a failed registration is separate from the
            // real task's completion callback and cancellation cleanup.
            self.completion_signal.send_replace(true);
        }
        Ok(())
    }
}

struct PythonTaskFuture {
    task_receiver: Option<oneshot::Receiver<Py<PyAny>>>,
    result_receiver: oneshot::Receiver<PyResult<Py<PyAny>>>,
    task: Option<Py<PyAny>>,
    locals: TaskLocals,
    cancellation_tracker: TaskTracker,
    completion_signal: watch::Receiver<bool>,
    completed: bool,
    #[cfg(coverage)]
    defer_task_transfer: bool,
    #[cfg(coverage)]
    is_request_application: bool,
}

impl Future for PythonTaskFuture {
    type Output = PyResult<Py<PyAny>>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        #[cfg(coverage)]
        if this.task.is_none()
            && (this.defer_task_transfer
                || coverage_fault_take(CoverageFaultPoint::PythonTaskFutureDeferTaskTransfer))
        {
            // The owning Python task still runs and sends real ASGI events.
            // Hold only Rust's task-handle receipt until a peer reset drops
            // this future, then exercise cancellation before handle delivery.
            this.defer_task_transfer = true;
            return Poll::Pending;
        }
        if let Some(task_receiver) = this.task_receiver.as_mut() {
            match Pin::new(task_receiver).poll(context) {
                Poll::Ready(Ok(task)) => {
                    this.task_receiver.take();
                    this.task = Some(task);
                }
                Poll::Ready(Err(_)) => {
                    this.task_receiver.take();
                    // A failed task prelude sends its original error before
                    // closing task delivery. Do not replace that exception
                    // with the generic closed-channel diagnostic.
                    if let Ok(result) = this.result_receiver.try_recv() {
                        this.completed = true;
                        return Poll::Ready(result);
                    }
                    // A starter may still be queued on the owning Python loop.
                    // Drop must track its real completion or channel closure
                    // before the server can observe an empty cleanup tracker.
                    return Poll::Ready(Err(PyRuntimeError::new_err(
                        "Python event loop stopped before the ASGI task started",
                    )));
                }
                Poll::Pending => return Poll::Pending,
            }
        }
        match Pin::new(&mut this.result_receiver).poll(context) {
            Poll::Ready(Ok(result)) => {
                this.completed = true;
                #[cfg(coverage)]
                if this.is_request_application
                    && coverage_fault_is_armed(
                        CoverageFaultPoint::PythonTaskFuturePanicAfterCompletion,
                    )
                {
                    coverage_panic(
                        "coverage-injected ASGI app task panic after final response body",
                    );
                }
                Poll::Ready(result)
            }
            Poll::Ready(Err(_)) => {
                this.completed = true;
                Poll::Ready(Err(PyRuntimeError::new_err(
                    "Python event loop stopped before the ASGI task completed",
                )))
            }
            Poll::Pending => Poll::Pending,
        }
    }
}

impl Drop for PythonTaskFuture {
    fn drop(&mut self) {
        if self.completed {
            return;
        }
        {
            let tracker = self.cancellation_tracker.clone();
            let task = self.task.take();
            let task_receiver = self.task_receiver.take();
            let locals = self.locals.clone();
            let mut completion_signal = self.completion_signal.clone();
            tracker.spawn_on(
                async move {
                    let task = match task {
                        Some(task) => Some(task),
                        None => match task_receiver {
                            Some(task_receiver) => task_receiver.await.ok(),
                            None => None,
                        },
                    };
                    if let Some(task) = task {
                        cancel_python_task(&task, &locals);
                    }
                    let _ = completion_signal.wait_for(|completed| *completed).await;
                },
                pyo3_async_runtimes::tokio::get_runtime().handle(),
            );
        }
    }
}

async fn run_python_application(
    mut application: PythonTaskFuture,
    force_shutdown: CancellationToken,
) -> PyResult<Py<PyAny>> {
    tokio::select! {
        biased;
        // Preserve the original result if completion and forced shutdown are
        // both ready, including any exception raised by the application.
        result = &mut application => result,
        _ = force_shutdown.cancelled() => {
            // Keep the actual Python completion result before dropping the
            // bridge. Drop schedules cancellation on its owning Python loop
            // and registers completion cleanup with the server's tracker.
            // The replacement channel is allocated only during forced shutdown.
            let completion = std::mem::replace(
                &mut application.result_receiver,
                oneshot::channel().1,
            );
            drop(application);
            completion.await.map_err(|_| PyRuntimeError::new_err(
                "Python event loop stopped before the cancelled ASGI task completed",
            ))?
        }
    }
}

fn cancel_python_task(task: &Py<PyAny>, locals: &TaskLocals) {
    Python::attach(|py| {
        let result = (|| -> PyResult<()> {
            let cancel = coverage_value!(PythonTaskCancelGetAttr, task.bind(py).getattr("cancel"))?;
            let event_loop = locals.event_loop(py);
            let kwargs = PyDict::new(py);
            coverage_try!(
                PythonTaskCancelContextSetItem,
                kwargs.set_item("context", locals.context(py))
            );
            coverage_value!(
                PythonTaskCancelScheduleCall,
                event_loop.call_method("call_soon_threadsafe", (cancel,), Some(&kwargs))
            )?;
            Ok(())
        })();
        if let Err(error) = result {
            // A failed cross-loop cancellation must remain observable even
            // when the application is being torn down and cannot await it.
            error.print(py);
        }
    });
}

fn python_task_future(
    py: Python<'_>,
    locals: &TaskLocals,
    awaitable: Bound<'_, PyAny>,
    diagnostics: RuntimeDiagnostics,
    cancellation_tracker: TaskTracker,
    #[cfg(coverage)] is_request_application: bool,
) -> PyResult<PythonTaskFuture> {
    let (task_sender, task_receiver) = oneshot::channel();
    #[cfg(coverage)]
    let (task_sender, task_receiver) =
        if coverage_fault_is_armed(CoverageFaultPoint::PythonTaskFutureTaskReceiverClosed) {
            drop(task_receiver);
            let (closed_sender, closed_receiver) = oneshot::channel();
            drop(closed_sender);
            (task_sender, closed_receiver)
        } else {
            (task_sender, task_receiver)
        };
    let (result_sender, result_receiver) = oneshot::channel();
    let (completion_signal, completion_receiver) = watch::channel(false);
    #[cfg(feature = "runtime-diagnostics")]
    let schedule_started = std::time::Instant::now();
    let starter = coverage_value!(
        PythonTaskFutureStarterAllocation,
        Py::new(
            py,
            PythonTaskStarter {
                awaitable: awaitable.unbind(),
                task_sender: Some(task_sender),
                result_sender: Some(result_sender),
                completion_signal,
                locals: locals.clone(),
                cancellation_tracker: cancellation_tracker.clone(),
                #[cfg(feature = "runtime-diagnostics")]
                diagnostics: diagnostics.clone(),
                #[cfg(feature = "runtime-diagnostics")]
                schedule_started,
            },
        )
    )?;
    let event_loop = locals.event_loop(py);
    let kwargs = PyDict::new(py);
    coverage_try!(
        PythonTaskFutureContextSetItem,
        kwargs.set_item("context", locals.context(py))
    );
    diagnostics.asgi_task_scheduled();
    // Own cancellation state before scheduling can fail. A failed scheduling
    // operation then uses the same Drop cleanup as a cancelled pending task.
    let future = PythonTaskFuture {
        task_receiver: Some(task_receiver),
        result_receiver,
        task: None,
        locals: locals.clone(),
        cancellation_tracker,
        completion_signal: completion_receiver,
        completed: false,
        #[cfg(coverage)]
        defer_task_transfer: false,
        #[cfg(coverage)]
        is_request_application,
    };
    coverage_value!(
        PythonTaskFutureScheduleCall,
        event_loop.call_method("call_soon_threadsafe", (starter,), Some(&kwargs))
    )?;
    Ok(future)
}

enum WebSocketIncoming {
    Text(String),
    Bytes(Bytes),
    Disconnect { code: u16, reason: String },
}

enum WebSocketOutgoing {
    Text(String),
    Bytes(Bytes),
    Close { code: u16, reason: String },
}

fn into_websocket_message(message: WebSocketOutgoing) -> Message {
    match message {
        WebSocketOutgoing::Text(text) => Message::Text(text.into()),
        WebSocketOutgoing::Bytes(bytes) => Message::Binary(bytes),
        WebSocketOutgoing::Close { code, reason } => Message::Close(Some(CloseFrame {
            code: CloseCode::from(code),
            reason: reason.into(),
        })),
    }
}

enum WebSocketHandshake {
    Accept {
        subprotocol: Option<String>,
        headers: Vec<(Bytes, Bytes)>,
    },
    Reject,
}

enum LifespanMessage {
    Startup,
    Shutdown,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum LifespanMode {
    Auto,
    On,
    Off,
}

impl LifespanMode {
    fn from_python(value: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(mode) = value.extract::<String>() {
            return match mode.as_str() {
                "auto" => Ok(Self::Auto),
                "on" => Ok(Self::On),
                "off" => Ok(Self::Off),
                _ => Err(PyValueError::new_err(
                    "lifespan must be 'auto', 'on', 'off', or a boolean",
                )),
            };
        }
        if let Ok(enabled) = value.extract::<bool>() {
            return Ok(if enabled { Self::Auto } else { Self::Off });
        }
        Err(PyValueError::new_err(
            "lifespan must be 'auto', 'on', 'off', or a boolean",
        ))
    }

    fn enabled(self) -> bool {
        self != Self::Off
    }
}

enum LifespanEvent {
    StartupComplete,
    StartupFailed(String),
    ShutdownComplete,
    ShutdownFailed(String),
}

#[pyclass]
struct AsgiIo {
    request_messages: Arc<Mutex<mpsc::Receiver<RequestMessage>>>,
    _request_sender: Option<mpsc::Sender<RequestMessage>>,
    connection_closed: ConnectionClosed,
    request_cancellation: CancellationToken,
    request_disconnected: Arc<AtomicBool>,
    preserve_application_on_disconnect: Arc<AtomicBool>,
    response_start_attempted: Arc<AtomicBool>,
    response_started: Arc<AtomicBool>,
    start: mpsc::Sender<ResponseStart>,
    body: mpsc::Sender<BodyChunk>,
    diagnostics: RuntimeDiagnostics,
    #[cfg(coverage)]
    receive_calls: AtomicUsize,
}

#[pymethods]
impl AsgiIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        if slf.request_disconnected.load(Ordering::Acquire) || slf.connection_closed.is_closed() {
            slf.preserve_application_on_disconnect
                .store(true, Ordering::Release);
            slf.diagnostics.http_receive_immediate();
            #[cfg(coverage)]
            let request_message = if coverage_fault_is_armed(
                CoverageFaultPoint::HttpReceiveImmediateDisconnectMessageError,
            ) {
                Err(PyMemoryError::new_err(
                    "coverage-injected immediate HTTP disconnect message error",
                ))
            } else {
                make_http_request_message(py, None, &slf.request_disconnected, &slf.diagnostics)
            };
            #[cfg(not(coverage))]
            let request_message =
                make_http_request_message(py, None, &slf.request_disconnected, &slf.diagnostics);
            return Ok(request_message?.into_bound(py));
        }

        #[cfg(coverage)]
        let receive_call = slf.receive_calls.fetch_add(1, Ordering::AcqRel);
        #[cfg(not(coverage))]
        let receive_call = 0;
        #[cfg(coverage)]
        let force_contention =
            coverage_fault_is_armed(CoverageFaultPoint::HttpReceiveLockContention)
                && receive_call > 0;
        #[cfg(coverage)]
        // Hold the request mutex only during the second synchronous receive
        // call so the fault-contract exercises the actual try_lock failure
        // branch without depending on Tokio/Python scheduling timing.
        let _synthetic_receive_lock = force_contention
            .then(|| slf.request_messages.try_lock().ok())
            .flatten();

        let immediate = match slf.request_messages.try_lock() {
            Ok(mut requests) => match requests.try_recv() {
                Ok(request) => Some(Some(request)),
                Err(TryRecvError::Disconnected) => Some(None),
                Err(TryRecvError::Empty) => None,
            },
            Err(_) => {
                #[cfg(coverage)]
                log_error(format_args!(
                    "uvicorn-rs: coverage observed concurrent HTTP receive lock contention"
                ));
                None
            }
        };
        if let Some(request) = immediate {
            slf.diagnostics.http_receive_immediate();
            if request.as_ref().is_none_or(|request| request.disconnected) {
                slf.preserve_application_on_disconnect
                    .store(true, Ordering::Release);
            }
            return Ok(make_http_request_message(
                py,
                request,
                &slf.request_disconnected,
                &slf.diagnostics,
            )?
            .into_bound(py));
        }
        let request_messages = Arc::clone(&slf.request_messages);
        let mut connection_closed = slf.connection_closed.clone();
        let request_cancellation = slf.request_cancellation.clone();
        let request_disconnected = Arc::clone(&slf.request_disconnected);
        let preserve_application_on_disconnect =
            Arc::clone(&slf.preserve_application_on_disconnect);
        let receive_guard = PendingReceiveGuard::new(
            Arc::clone(&preserve_application_on_disconnect),
            Arc::clone(&request_disconnected),
        );
        slf.diagnostics.http_receive_bridge_future();
        let diagnostics = slf.diagnostics.clone();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let _receive_guard = receive_guard;
            #[cfg(coverage)]
            if coverage_fault_take(CoverageFaultPoint::HttpReceiveDisconnectedBeforeFuturePoll) {
                request_disconnected.store(true, Ordering::Release);
            }
            let request = if request_disconnected.load(Ordering::Acquire) {
                None
            } else {
                tokio::select! {
                    biased;
                    message = async { request_messages.lock().await.recv().await } => message,
                    _ = wait_for_connection_close(&mut connection_closed, receive_call > 0) => {
                        request_disconnected.store(true, Ordering::Release);
                        None
                    }
                    _ = request_cancellation.cancelled() => {
                        request_disconnected.store(true, Ordering::Release);
                        None
                    }
                }
            };
            Python::attach(|py| {
                if request.as_ref().is_none_or(|request| request.disconnected) {
                    preserve_application_on_disconnect.store(true, Ordering::Release);
                }
                make_http_request_message(py, request, &request_disconnected, &diagnostics)
            })
        })
    }

    fn send<'py>(
        slf: PyRef<'py, Self>,
        py: Python<'py>,
        message: Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let event_type = classify_asgi_event_type(
            py,
            coverage_value!(HttpAsgiSendTypeGetItem, message.get_item("type"))?
                .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?,
        )?;
        match event_type {
            AsgiEventType::HttpResponseStart => {
                slf.response_start_attempted.store(true, Ordering::Release);
                if slf.connection_closed.is_closed()
                    || slf.request_disconnected.load(Ordering::Acquire)
                {
                    return Err(PyOSError::new_err(
                        "client disconnected before response start",
                    ));
                }
                let status_value =
                    coverage_value!(HttpResponseStartStatusGetItem, message.get_item("status"))?;
                let status_value = status_value
                    .ok_or_else(|| PyValueError::new_err("response.start is missing 'status'"))?;
                let status: u16 =
                    coverage_value!(HttpResponseStartStatusExtract, status_value.extract())?;
                let status = StatusCode::from_u16(status)
                    .map_err(|_| PyRuntimeError::new_err("Invalid HTTP response status code."))?;
                let headers_value =
                    coverage_value!(HttpResponseStartHeadersGetItem, message.get_item("headers"))?;
                let header_values = coverage_value!(
                    HttpResponseStartHeadersExtract,
                    extract_headers(headers_value)
                )?;
                let mut headers = HeaderMap::new();
                for (name, value) in header_values {
                    let name = HeaderName::from_bytes(&name)
                        .map_err(|_| PyRuntimeError::new_err("Invalid HTTP header name."))?;
                    let value = HeaderValue::from_bytes(&value)
                        .map_err(|_| PyRuntimeError::new_err("Invalid HTTP header value."))?;
                    headers.try_append(name, value).map_err(|error| {
                        PyRuntimeError::new_err(format!("HTTP response headers: {error}"))
                    })?;
                }
                // Commit the state only after the event is fully validated.
                // Invalid status/header data must not look like an accepted
                // response start to the request driver.
                if slf
                    .response_started
                    .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
                    .is_err()
                {
                    return Err(PyRuntimeError::new_err(
                        "ASGI app sent response.start more than once",
                    ));
                }
                slf.diagnostics.http_response_start();
                #[cfg(coverage)]
                let start_send_result = if coverage_fault_is_armed(
                    CoverageFaultPoint::HttpResponseStartChannelClosed,
                ) {
                    Err(TrySendError::Closed(ResponseStart { status, headers }))
                } else {
                    slf.start.try_send(ResponseStart { status, headers })
                };
                #[cfg(not(coverage))]
                let start_send_result = slf.start.try_send(ResponseStart { status, headers });
                if let Err(error) = start_send_result {
                    slf.response_started.store(false, Ordering::Release);
                    return Err(PyOSError::new_err(format!(
                        "server response channel closed: {error}"
                    )));
                }
                Ok(py.None().into_bound(py))
            }
            AsgiEventType::HttpResponseBody => {
                if slf.connection_closed.is_closed()
                    || slf.request_disconnected.load(Ordering::Acquire)
                {
                    return Err(PyOSError::new_err(
                        "client disconnected before response body",
                    ));
                }
                if !slf.response_started.load(Ordering::Acquire) {
                    return Err(PyValueError::new_err(
                        "ASGI app sent response.body before response.start",
                    ));
                }
                let body =
                    match coverage_value!(HttpResponseBodyBodyGetItem, message.get_item("body"))? {
                        Some(value) => {
                            coverage_value!(HttpResponseBodyBodyExtract, value.extract::<Bytes>())?
                        }
                        None => Bytes::new(),
                    };
                let more_body = match coverage_value!(
                    HttpResponseBodyMoreBodyGetItem,
                    message.get_item("more_body")
                )? {
                    Some(value) => {
                        coverage_value!(HttpResponseBodyMoreBodyExtract, value.extract::<bool>())?
                    }
                    None => false,
                };
                let chunk = BodyChunk { body, more_body };
                slf.diagnostics.http_response_body();
                #[cfg(coverage)]
                let body_send_result =
                    if coverage_fault_is_armed(CoverageFaultPoint::HttpResponseBodyChannelClosed) {
                        Err(TrySendError::Closed(chunk))
                    } else {
                        slf.body.try_send(chunk)
                    };
                #[cfg(not(coverage))]
                let body_send_result = slf.body.try_send(chunk);
                match body_send_result {
                    Ok(()) => Ok(py.None().into_bound(py)),
                    Err(TrySendError::Closed(_)) => {
                        Err(PyOSError::new_err("server response body channel closed"))
                    }
                    Err(TrySendError::Full(chunk)) => {
                        slf.diagnostics.http_response_body_queue_full();
                        let wait_started = slf.diagnostics.http_response_body_wait_started();
                        let diagnostics = slf.diagnostics.clone();
                        let sender = slf.body.clone();
                        pyo3_async_runtimes::tokio::future_into_py(py, async move {
                            sender.send(chunk).await.map_err(|_| {
                                PyOSError::new_err("server response body channel closed")
                            })?;
                            diagnostics.http_response_body_full_send_wait_finished(wait_started);
                            Python::attach(|py| Ok(py.None()))
                        })
                    }
                }
            }
            other => Err(PyValueError::new_err(format!(
                "unsupported ASGI HTTP event: {}",
                other.as_str()
            ))),
        }
    }
}

struct PendingReceiveGuard {
    preserve_application_on_disconnect: Arc<AtomicBool>,
    request_disconnected: Arc<AtomicBool>,
}

impl PendingReceiveGuard {
    fn new(
        preserve_application_on_disconnect: Arc<AtomicBool>,
        request_disconnected: Arc<AtomicBool>,
    ) -> Self {
        preserve_application_on_disconnect.store(true, Ordering::Release);
        Self {
            preserve_application_on_disconnect,
            request_disconnected,
        }
    }
}

impl Drop for PendingReceiveGuard {
    fn drop(&mut self) {
        if !self.request_disconnected.load(Ordering::Acquire) {
            self.preserve_application_on_disconnect
                .store(false, Ordering::Release);
        }
    }
}

#[pyclass]
struct WebSocketIo {
    incoming: Arc<Mutex<mpsc::Receiver<WebSocketIncoming>>>,
    connect_delivered: AtomicBool,
    state: Arc<AtomicU8>,
    handshake: std::sync::Mutex<Option<oneshot::Sender<WebSocketHandshake>>>,
    outgoing: mpsc::Sender<WebSocketOutgoing>,
    diagnostics: RuntimeDiagnostics,
}

#[pymethods]
impl WebSocketIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let connect = !slf.connect_delivered.swap(true, Ordering::AcqRel);
        if connect {
            // The internal bridge adapts this immediately available value to
            // the awaitable `receive` callable presented at the ASGI boundary.
            let message = PyDict::new(py);
            coverage_try!(
                WebSocketReceiveConnectTypeSetItem,
                message.set_item("type", "websocket.connect")
            );
            return Ok(message.into_any());
        }

        let incoming = Arc::clone(&slf.incoming);
        let state = Arc::clone(&slf.state);
        slf.diagnostics.websocket_receive_bridge_future();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let queued_message = incoming.lock().await.try_recv();
            #[cfg(coverage)]
            let force_closed =
                coverage_fault_take(CoverageFaultPoint::WebSocketReceiveConnectionClosed);
            #[cfg(not(coverage))]
            let force_closed = false;
            let state_closed = state.load(Ordering::Acquire) == 3 || force_closed;
            if state_closed {
                state.store(3, Ordering::Release);
            }
            let incoming_message =
                match queued_message {
                    Ok(message) => Some(message),
                    Err(_) if state_closed => Some(WebSocketIncoming::Disconnect {
                        code: 1005,
                        reason: String::new(),
                    }),
                    Err(_) => {
                        async {
                            #[cfg(coverage)]
                            if coverage_fault_take(
                                CoverageFaultPoint::WebSocketReceiveChannelClosed,
                            ) || coverage_fault_is_armed(
                                CoverageFaultPoint::WebSocketReceiveClosedTypeSetItem,
                            ) || coverage_fault_is_armed(
                                CoverageFaultPoint::WebSocketReceiveClosedCodeSetItem,
                            ) || coverage_fault_is_armed(
                                CoverageFaultPoint::WebSocketReceiveClosedReasonSetItem,
                            ) {
                                return None;
                            }
                            incoming.lock().await.recv().await
                        }
                        .await
                    }
                };
            Python::attach(|py| -> PyResult<Py<PyAny>> {
                let message = PyDict::new(py);
                match incoming_message {
                    Some(WebSocketIncoming::Text(text)) => {
                        coverage_try!(
                            WebSocketReceiveTextTypeSetItem,
                            message.set_item("type", "websocket.receive")
                        );
                        coverage_try!(
                            WebSocketReceiveTextValueSetItem,
                            message.set_item("text", text)
                        );
                    }
                    Some(WebSocketIncoming::Bytes(data)) => {
                        coverage_try!(
                            WebSocketReceiveBinaryTypeSetItem,
                            message.set_item("type", "websocket.receive")
                        );
                        coverage_try!(
                            WebSocketReceiveBinaryValueSetItem,
                            message.set_item("bytes", PyBytes::new(py, &data))
                        );
                    }
                    Some(WebSocketIncoming::Disconnect { code, reason }) => {
                        coverage_try!(
                            WebSocketReceiveDisconnectTypeSetItem,
                            message.set_item("type", "websocket.disconnect")
                        );
                        coverage_try!(
                            WebSocketReceiveDisconnectCodeSetItem,
                            message.set_item("code", code)
                        );
                        coverage_try!(
                            WebSocketReceiveDisconnectReasonSetItem,
                            message.set_item("reason", reason)
                        );
                    }
                    None => {
                        state.store(3, Ordering::Release);
                        coverage_try!(
                            WebSocketReceiveClosedTypeSetItem,
                            message.set_item("type", "websocket.disconnect")
                        );
                        coverage_try!(
                            WebSocketReceiveClosedCodeSetItem,
                            message.set_item("code", 1005)
                        );
                        coverage_try!(
                            WebSocketReceiveClosedReasonSetItem,
                            message.set_item("reason", "")
                        );
                    }
                }
                Ok(message.into_any().unbind())
            })
        })
    }

    fn send<'py>(
        slf: PyRef<'py, Self>,
        py: Python<'py>,
        message: Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let event_type = classify_asgi_event_type(
            py,
            coverage_value!(WebSocketAsgiSendTypeGetItem, message.get_item("type"))?
                .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?,
        )?;
        match event_type {
            AsgiEventType::WebSocketAccept => {
                if slf
                    .state
                    .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
                    .is_err()
                {
                    return Err(PyValueError::new_err(
                        "websocket.accept must be the first WebSocket response",
                    ));
                }
                let subprotocol_value = coverage_value!(
                    WebSocketAcceptSubprotocolGetItem,
                    message.get_item("subprotocol")
                )?;
                let subprotocol = match subprotocol_value {
                    Some(value) => coverage_value!(
                        WebSocketAcceptSubprotocolExtract,
                        value.extract::<Option<String>>()
                    )?,
                    None => None,
                };
                let headers_value =
                    coverage_value!(WebSocketAcceptHeadersGetItem, message.get_item("headers"))?;
                let headers = coverage_value!(
                    WebSocketAcceptHeadersExtract,
                    extract_headers(headers_value)
                )?;
                #[cfg(coverage)]
                poison_websocket_handshake_mutex(&slf.handshake);
                #[cfg(coverage)]
                discard_websocket_handshake_sender(&slf.handshake);
                let handshake = slf
                    .handshake
                    .lock()
                    .map_err(|_| PyOSError::new_err("WebSocket handshake state poisoned"))?
                    .take()
                    .ok_or_else(|| PyOSError::new_err("WebSocket handshake already completed"))?;
                #[cfg(coverage)]
                let send_result =
                    if coverage_fault_is_armed(CoverageFaultPoint::WebSocketHandshakeSendClosed) {
                        Err(WebSocketHandshake::Accept {
                            subprotocol,
                            headers,
                        })
                    } else {
                        handshake.send(WebSocketHandshake::Accept {
                            subprotocol,
                            headers,
                        })
                    };
                #[cfg(not(coverage))]
                let send_result = handshake.send(WebSocketHandshake::Accept {
                    subprotocol,
                    headers,
                });
                send_result
                    .map_err(|_| PyOSError::new_err("WebSocket handshake channel closed"))?;
                Ok(py.None().into_bound(py))
            }
            AsgiEventType::WebSocketClose => {
                let code_value =
                    coverage_value!(WebSocketCloseCodeGetItem, message.get_item("code"))?;
                let code = match code_value {
                    Some(value) => {
                        coverage_value!(WebSocketCloseCodeExtract, value.extract::<u16>())?
                    }
                    None => 1000,
                };
                let reason_value =
                    coverage_value!(WebSocketCloseReasonGetItem, message.get_item("reason"))?;
                let reason = match reason_value {
                    Some(value) => {
                        coverage_value!(WebSocketCloseReasonExtract, value.extract::<String>())?
                    }
                    None => String::new(),
                };
                match slf
                    .state
                    .compare_exchange(0, 3, Ordering::AcqRel, Ordering::Acquire)
                {
                    Ok(_) => {
                        #[cfg(coverage)]
                        poison_websocket_handshake_mutex(&slf.handshake);
                        #[cfg(coverage)]
                        discard_websocket_handshake_sender(&slf.handshake);
                        let handshake = slf
                            .handshake
                            .lock()
                            .map_err(|_| PyOSError::new_err("WebSocket handshake state poisoned"))?
                            .take()
                            .ok_or_else(|| {
                                PyOSError::new_err("WebSocket handshake already completed")
                            })?;
                        #[cfg(coverage)]
                        let send_result = if coverage_fault_is_armed(
                            CoverageFaultPoint::WebSocketHandshakeSendClosed,
                        ) {
                            Err(WebSocketHandshake::Reject)
                        } else {
                            handshake.send(WebSocketHandshake::Reject)
                        };
                        #[cfg(not(coverage))]
                        let send_result = handshake.send(WebSocketHandshake::Reject);
                        send_result.map_err(|_| {
                            PyOSError::new_err("WebSocket handshake channel closed")
                        })?;
                        Ok(py.None().into_bound(py))
                    }
                    Err(1) => {
                        slf.state.store(2, Ordering::Release);
                        queue_websocket_message(
                            py,
                            slf.outgoing.clone(),
                            WebSocketOutgoing::Close { code, reason },
                            slf.diagnostics.clone(),
                        )
                    }
                    _ => Err(PyOSError::new_err("WebSocket connection is closed")),
                }
            }
            AsgiEventType::WebSocketSend => {
                match slf.state.load(Ordering::Acquire) {
                    1 => {}
                    0 => {
                        return Err(PyValueError::new_err(
                            "websocket.send requires an accepted WebSocket",
                        ));
                    }
                    _ => return Err(PyOSError::new_err("WebSocket connection is closed")),
                }
                let text_value =
                    coverage_value!(WebSocketSendTextGetItem, message.get_item("text"))?;
                let text = match text_value {
                    Some(value) => coverage_value!(
                        WebSocketSendTextExtract,
                        value.extract::<Option<String>>()
                    )?,
                    None => None,
                };
                let bytes_value =
                    coverage_value!(WebSocketSendBytesGetItem, message.get_item("bytes"))?;
                let data = match bytes_value {
                    Some(value) => coverage_value!(
                        WebSocketSendBytesExtract,
                        value.extract::<Option<Bytes>>()
                    )?,
                    None => None,
                };
                let outgoing = match (text, data) {
                    (Some(text), None) => WebSocketOutgoing::Text(text),
                    (None, Some(data)) => WebSocketOutgoing::Bytes(data),
                    _ => {
                        return Err(PyValueError::new_err(
                            "websocket.send must contain exactly one of 'text' or 'bytes'",
                        ));
                    }
                };
                queue_websocket_message(py, slf.outgoing.clone(), outgoing, slf.diagnostics.clone())
            }
            other => Err(PyValueError::new_err(format!(
                "unsupported ASGI WebSocket event: {}",
                other.as_str()
            ))),
        }
    }
}

#[cfg(coverage)]
fn poison_websocket_handshake_mutex<T>(mutex: &std::sync::Mutex<T>) {
    if coverage_fault_is_armed(CoverageFaultPoint::WebSocketHandshakeMutexPoison) {
        let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _guard = mutex
                .lock()
                .unwrap_or_else(std::sync::PoisonError::into_inner);
            coverage_panic("coverage-injected WebSocket handshake mutex poison");
        }));
    }
}

#[cfg(coverage)]
fn discard_websocket_handshake_sender<T>(mutex: &std::sync::Mutex<Option<T>>) {
    if coverage_fault_is_armed(CoverageFaultPoint::WebSocketHandshakeAlreadyCompleted) {
        mutex
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .take();
    }
}

fn queue_websocket_message<'py>(
    py: Python<'py>,
    sender: mpsc::Sender<WebSocketOutgoing>,
    message: WebSocketOutgoing,
    diagnostics: RuntimeDiagnostics,
) -> PyResult<Bound<'py, PyAny>> {
    diagnostics.websocket_outgoing_message();
    #[cfg(coverage)]
    let send_result =
        if coverage_fault_is_armed(CoverageFaultPoint::WebSocketOutgoingChannelClosedOnSend) {
            Err(TrySendError::Closed(message))
        } else if coverage_fault_is_armed(CoverageFaultPoint::WebSocketOutgoingQueueReceiverClosed)
        {
            Err(TrySendError::Full(message))
        } else {
            sender.try_send(message)
        };
    #[cfg(not(coverage))]
    let send_result = sender.try_send(message);
    match send_result {
        Ok(()) => Ok(py.None().into_bound(py)),
        Err(TrySendError::Closed(_)) => Err(PyOSError::new_err("WebSocket connection is closed")),
        Err(TrySendError::Full(message)) => {
            diagnostics.websocket_outgoing_queue_full();
            pyo3_async_runtimes::tokio::future_into_py(py, async move {
                #[cfg(coverage)]
                let send_result = if coverage_fault_is_armed(
                    CoverageFaultPoint::WebSocketOutgoingQueueReceiverClosed,
                ) {
                    Err(tokio::sync::mpsc::error::SendError(message))
                } else {
                    sender.send(message).await
                };
                #[cfg(not(coverage))]
                let send_result = sender.send(message).await;
                send_result.map_err(|_| PyOSError::new_err("WebSocket connection is closed"))?;
                Python::attach(|py| Ok(py.None()))
            })
        }
    }
}

#[pyclass]
struct LifespanIo {
    requests: Arc<Mutex<mpsc::Receiver<LifespanMessage>>>,
    events: mpsc::Sender<LifespanEvent>,
}

#[pymethods]
impl LifespanIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let requests = Arc::clone(&slf.requests);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let mut requests = requests.lock().await;
            #[cfg(coverage)]
            if coverage_fault_take(CoverageFaultPoint::LifespanReceiveChannelClosed) {
                requests.close();
                while requests.try_recv().is_ok() {}
            }
            let request = requests
                .recv()
                .await
                .ok_or_else(|| PyOSError::new_err("ASGI lifespan channel closed"))?;
            drop(requests);
            Python::attach(|py| -> PyResult<Py<PyAny>> {
                let message = PyDict::new(py);
                match request {
                    LifespanMessage::Startup => {
                        coverage_try!(
                            LifespanReceiveStartupTypeSetItem,
                            message.set_item("type", "lifespan.startup")
                        );
                    }
                    LifespanMessage::Shutdown => {
                        coverage_try!(
                            LifespanReceiveShutdownTypeSetItem,
                            message.set_item("type", "lifespan.shutdown")
                        );
                    }
                }
                Ok(message.into_any().unbind())
            })
        })
    }

    fn send<'py>(
        slf: PyRef<'py, Self>,
        py: Python<'py>,
        message: Bound<'py, PyDict>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let event_type = classify_asgi_event_type(
            py,
            coverage_value!(LifespanAsgiSendTypeGetItem, message.get_item("type"))?
                .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?,
        )?;
        let event = match event_type {
            AsgiEventType::LifespanStartupComplete => LifespanEvent::StartupComplete,
            AsgiEventType::LifespanStartupFailed => {
                let message_value = coverage_value!(
                    LifespanStartupFailedMessageGetItem,
                    message.get_item("message")
                )?;
                let message = match message_value {
                    Some(value) => coverage_value!(
                        LifespanStartupFailedMessageExtract,
                        value.extract::<String>()
                    )?,
                    None => String::new(),
                };
                LifespanEvent::StartupFailed(message)
            }
            AsgiEventType::LifespanShutdownComplete => LifespanEvent::ShutdownComplete,
            AsgiEventType::LifespanShutdownFailed => {
                let message_value = coverage_value!(
                    LifespanShutdownFailedMessageGetItem,
                    message.get_item("message")
                )?;
                let message = match message_value {
                    Some(value) => coverage_value!(
                        LifespanShutdownFailedMessageExtract,
                        value.extract::<String>()
                    )?,
                    None => String::new(),
                };
                LifespanEvent::ShutdownFailed(message)
            }
            other => {
                return Err(PyValueError::new_err(format!(
                    "unsupported ASGI lifespan event: {}",
                    other.as_str()
                )));
            }
        };
        #[cfg(coverage)]
        let send_result =
            if coverage_fault_is_armed(CoverageFaultPoint::LifespanSendEventChannelClosed) {
                Err(TrySendError::Closed(event))
            } else {
                slf.events.try_send(event)
            };
        #[cfg(not(coverage))]
        let send_result = slf.events.try_send(event);
        send_result.map_err(|error| {
            PyOSError::new_err(format!("ASGI lifespan channel closed: {error}"))
        })?;
        Ok(py.None().into_bound(py))
    }
}

struct LifespanRuntime {
    // Abort before channel fields drop during emergency teardown. Normal
    // shutdown consumes the guarded handle after observing its result once.
    app_task: Option<AbortOnDrop<PyResult<Py<PyAny>>>>,
    state: Option<Arc<Py<PyDict>>>,
    requests: Option<mpsc::Sender<LifespanMessage>>,
    events: Option<mpsc::Receiver<LifespanEvent>>,
}

impl LifespanRuntime {
    async fn start(
        app: Arc<Py<PyAny>>,
        invoke: Arc<Py<PyAny>>,
        locals: TaskLocals,
        diagnostics: RuntimeDiagnostics,
        cancellation_tracker: TaskTracker,
        mode: LifespanMode,
    ) -> PyResult<Option<Self>> {
        let (request_tx, request_rx) = mpsc::channel(1);
        let (event_tx, mut event_rx) = mpsc::channel(1);
        let state = Python::attach(|py| PyDict::new(py).unbind());
        let scope_state = Python::attach(|py| state.clone_ref(py));
        let app_future = Python::attach(move |py| {
            let io = coverage_value!(
                LifespanIoAllocate,
                Py::new(
                    py,
                    LifespanIo {
                        requests: Arc::new(Mutex::new(request_rx)),
                        events: event_tx,
                    },
                )
            )?;
            coverage_receive_borrow_conflict!(io, py);
            let scope = PyDict::new(py);
            let asgi = PyDict::new(py);
            coverage_try!(
                LifespanScopeAsgiVersionSetItem,
                asgi.set_item("version", "3.0")
            );
            coverage_try!(
                LifespanScopeAsgiSpecVersionSetItem,
                asgi.set_item("spec_version", "2.0")
            );
            coverage_try!(LifespanScopeTypeSetItem, scope.set_item("type", "lifespan"));
            coverage_try!(LifespanScopeAsgiSetItem, scope.set_item("asgi", asgi));
            coverage_try!(
                LifespanScopeStateSetItem,
                scope.set_item("state", scope_state.bind(py))
            );
            let awaitable = coverage_value!(
                LifespanAppInvokeCall,
                invoke.bind(py).call1((app.bind(py), scope, io))
            )?;
            python_task_future(
                py,
                &locals,
                awaitable,
                diagnostics,
                cancellation_tracker,
                #[cfg(coverage)]
                false,
            )
        })?;
        let mut app_task = AbortOnDrop::new(tokio::spawn(app_future));
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::LifespanStartupTaskJoinError) {
            app_task.as_mut().abort();
        }
        #[cfg(coverage)]
        let send_result = if coverage_fault_take(CoverageFaultPoint::LifespanStartupSendClosed) {
            Err(mpsc::error::SendError(LifespanMessage::Startup))
        } else {
            request_tx.send(LifespanMessage::Startup).await
        };
        #[cfg(not(coverage))]
        let send_result = request_tx.send(LifespanMessage::Startup).await;
        if send_result.is_err() {
            app_task.as_mut().abort();
            let _ = app_task.into_handle().await;
            return Err(PyOSError::new_err("could not send ASGI lifespan startup"));
        }

        tokio::select! {
            biased;
            event = async {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::LifespanStartEventChannelClosed) {
                    return None;
                }
                event_rx.recv().await
            } => match event {
                Some(LifespanEvent::StartupComplete) => Ok(Some(Self {
                    state: Some(Arc::new(state)),
                    requests: Some(request_tx),
                    events: Some(event_rx),
                    app_task: Some(app_task),
                })),
                Some(LifespanEvent::StartupFailed(message)) => {
                    app_task.as_mut().abort();
                    let _ = app_task.into_handle().await;
                    if !message.is_empty() {
                        log_error(format_args!("{message}"));
                    }
                    log_error(format_args!("Application startup failed. Exiting."));
                    Ok(None)
                }
                Some(_) => {
                    app_task.as_mut().abort();
                    let _ = app_task.into_handle().await;
                    if mode == LifespanMode::On {
                        log_error(format_args!("Application startup failed. Exiting."));
                        return Ok(None);
                    }
                    log_error(format_args!("uvicorn-rs: ASGI app does not support lifespan"));
                    Ok(Some(Self {
                        state: Some(Arc::new(state)),
                        requests: None,
                        events: None,
                        app_task: None,
                    }))
                }
                None => {
                    // Retain cancellation ownership until the result has been
                    // observed, including if startup is cancelled mid-await.
                    let result = app_task.as_mut().await;
                    app_task.into_handle();
                    Self::without_lifespan(result, state, mode)
                },
            },
            result = app_task.as_mut() => {
                app_task.into_handle();
                Self::without_lifespan(result, state, mode)
            }
        }
    }

    fn without_lifespan(
        result: Result<PyResult<Py<PyAny>>, tokio::task::JoinError>,
        state: Py<PyDict>,
        mode: LifespanMode,
    ) -> PyResult<Option<Self>> {
        match result {
            Ok(Ok(_)) => {}
            Ok(Err(error)) => {
                Python::attach(|py| error.print(py));
                if mode == LifespanMode::On {
                    log_error(format_args!("Application startup failed. Exiting."));
                    return Ok(None);
                }
            }
            Err(error) => {
                return Err(PyRuntimeError::new_err(format!(
                    "ASGI lifespan task failed: {error}"
                )));
            }
        }
        if mode == LifespanMode::Auto {
            log_error(format_args!(
                "uvicorn-rs: ASGI app does not support lifespan"
            ));
        }
        Ok(Some(Self {
            state: Some(Arc::new(state)),
            requests: None,
            events: None,
            app_task: None,
        }))
    }

    async fn cancel_and_wait(&mut self) {
        if let Some(mut app_task) = self.app_task.take() {
            // Await native task destruction before waiting for Python cleanup:
            // dropping the bridge registers cancellation on its owning loop.
            app_task.as_mut().abort();
            let _ = app_task.into_handle().await;
        }
    }

    async fn shutdown(&mut self) -> PyResult<()> {
        let (Some(requests), Some(events), Some(app_task)) = (
            self.requests.as_ref(),
            self.events.as_mut(),
            self.app_task.as_mut(),
        ) else {
            return Ok(());
        };
        let app_task = app_task.as_mut();
        requests
            .send(LifespanMessage::Shutdown)
            .await
            .map_err(|_| PyRuntimeError::new_err("could not send ASGI lifespan shutdown"))?;
        #[cfg(coverage)]
        let task_join_error =
            coverage_fault_take(CoverageFaultPoint::LifespanShutdownTaskJoinError);
        #[cfg(not(coverage))]
        let task_join_error = false;
        #[cfg(coverage)]
        if task_join_error {
            app_task.abort();
        }
        tokio::select! {
            biased;
            event = events.recv(), if !task_join_error => match event {
                Some(LifespanEvent::ShutdownComplete) => {
                    #[cfg(coverage)]
                    if coverage_fault_take(CoverageFaultPoint::LifespanShutdownTaskJoinAfterComplete) {
                        app_task.abort();
                    }
                }
                Some(LifespanEvent::ShutdownFailed(message)) => {
                    return Err(PyRuntimeError::new_err(if message.is_empty() {
                        "ASGI lifespan shutdown failed".to_string()
                    } else {
                        message
                    }));
                }
                Some(_) => return Err(PyRuntimeError::new_err("unexpected ASGI lifespan event during shutdown")),
                None => return Err(PyRuntimeError::new_err("ASGI lifespan channel closed during shutdown")),
            },
            result = &mut *app_task => {
                self.app_task.take();
                return match result {
                    Ok(Ok(_)) => Err(PyRuntimeError::new_err(
                        "ASGI app returned before lifespan.shutdown.complete",
                    )),
                    Ok(Err(error)) => Err(error),
                    Err(error) => Err(PyRuntimeError::new_err(format!("ASGI lifespan task failed: {error}"))),
                };
            }
        }
        let result = app_task.await;
        self.app_task.take();
        match result {
            Ok(Ok(_)) => Ok(()),
            Ok(Err(error)) => Err(error),
            Err(error) => Err(PyRuntimeError::new_err(format!(
                "ASGI lifespan task failed: {error}"
            ))),
        }
    }
}

struct CancelOnDrop(CancellationToken);

impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        self.0.cancel();
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum ServerStartupState {
    Starting,
    Started,
    Failed,
    Stopped,
}

struct ServerStartupSignal {
    sender: watch::Sender<ServerStartupState>,
    started: bool,
    failed: bool,
}

impl ServerStartupSignal {
    fn new(sender: watch::Sender<ServerStartupState>) -> Self {
        Self {
            sender,
            started: false,
            failed: false,
        }
    }

    fn mark_started(&mut self) {
        self.started = true;
        self.sender.send_replace(ServerStartupState::Started);
    }

    fn mark_failed(&mut self) {
        self.failed = true;
        self.sender.send_replace(ServerStartupState::Failed);
    }
}

impl Drop for ServerStartupSignal {
    fn drop(&mut self) {
        if !self.started && !self.failed {
            self.sender.send_replace(ServerStartupState::Stopped);
        }
    }
}

#[pyclass]
struct ServerControl {
    cancellation: CancellationToken,
    startup: watch::Sender<ServerStartupState>,
}

#[pymethods]
impl ServerControl {
    #[new]
    fn new() -> Self {
        let (startup, _) = watch::channel(ServerStartupState::Starting);
        Self {
            cancellation: CancellationToken::new(),
            startup,
        }
    }

    fn shutdown(&self) {
        self.cancellation.cancel();
    }

    fn wait_started<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut startup = self.startup.subscribe();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            loop {
                match *startup.borrow_and_update() {
                    ServerStartupState::Started => return Ok(true),
                    ServerStartupState::Failed | ServerStartupState::Stopped => return Ok(false),
                    ServerStartupState::Starting => {}
                }
                if startup.changed().await.is_err() {
                    return Ok(false);
                }
            }
        })
    }

    fn wait_startup_failed<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let mut startup = self.startup.subscribe();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            loop {
                match *startup.borrow_and_update() {
                    ServerStartupState::Failed => return Ok(true),
                    ServerStartupState::Started | ServerStartupState::Stopped => return Ok(false),
                    ServerStartupState::Starting => {}
                }
                if startup.changed().await.is_err() {
                    return Ok(false);
                }
            }
        })
    }
}

fn extract_headers(value: Option<Bound<'_, PyAny>>) -> PyResult<Vec<(Bytes, Bytes)>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    value.extract::<Vec<(Bytes, Bytes)>>()
}

enum ResponseApplication {
    Running(tokio::task::JoinHandle<PyResult<Py<PyAny>>>),
    Completed(Result<PyResult<Py<PyAny>>, tokio::task::JoinError>),
}

struct AsgiBody {
    receiver: mpsc::Receiver<BodyChunk>,
    application: Option<ResponseApplication>,
    app_task_tracker: TaskTracker,
    defer_completed_app_result_once: bool,
    incomplete_body_result_deferred: bool,
    #[cfg(feature = "runtime-diagnostics")]
    response_timing_diagnostics: RuntimeDiagnostics,
    #[cfg(feature = "runtime-diagnostics")]
    response_latency_started: Option<std::time::Instant>,
    #[cfg(coverage)]
    body_consumer_pause: Option<Pin<Box<tokio::time::Sleep>>>,
    #[cfg(coverage)]
    body_consumer_pause_started: bool,
    #[cfg(coverage)]
    receiver_pending_pause: Pin<Box<tokio::time::Sleep>>,
    #[cfg(coverage)]
    receiver_pending_pause_active: bool,
}

impl Drop for AsgiBody {
    fn drop(&mut self) {
        if let Some(ResponseApplication::Running(task)) = &self.application {
            task.abort();
        }
    }
}

#[cfg(not(feature = "native-tcp"))]
struct ConnectionIo<I> {
    io: I,
    diagnostics: RuntimeDiagnostics,
    closed: watch::Sender<bool>,
    active_http_requests: Arc<AtomicUsize>,
    read_eof_waker: Arc<AtomicWaker>,
    read_eof: bool,
    #[cfg(feature = "runtime-diagnostics")]
    read_pending_since: Option<std::time::Instant>,
    #[cfg(feature = "runtime-diagnostics")]
    write_pending_since: Option<std::time::Instant>,
    #[cfg(coverage)]
    eof_recheck_paused: bool,
}

async fn pump_http_request_body(
    mut body: Incoming,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: ConnectionClosed,
    cancellation: CancellationToken,
    request_cancellation: CancellationToken,
    diagnostics: RuntimeDiagnostics,
) {
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpFirstPollPause) {
        // Hold admission before the first read until the peer or server closes,
        // then resume at the known-stop guard.
        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
    }
    #[cfg(coverage)]
    let body_batch_limit = if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpBatchLimitOneByte)
        || coverage_fault_is_armed(CoverageFaultPoint::HttpBodyPumpOversizedSendConnectionClosed)
    {
        1
    } else {
        HTTP_REQUEST_BODY_BATCH_BYTES
    };
    #[cfg(not(coverage))]
    let body_batch_limit = HTTP_REQUEST_BODY_BATCH_BYTES;
    #[cfg(coverage)]
    let body_batch_max_wait = if coverage_fault_is_armed(
        CoverageFaultPoint::HttpBodyPumpBatchThresholdSendConnectionClosed,
    ) || coverage_fault_is_armed(
        CoverageFaultPoint::HttpBodyPumpErrorBufferedSendConnectionClosed,
    ) {
        std::time::Duration::from_secs(1)
    } else {
        HTTP_REQUEST_BODY_BATCH_MAX_WAIT
    };
    #[cfg(not(coverage))]
    let body_batch_max_wait = HTTP_REQUEST_BODY_BATCH_MAX_WAIT;
    let mut body_segments = Vec::new();
    let mut body_len = 0usize;
    let mut body_started: Option<tokio::time::Instant> = None;
    let mut body_batch_timer =
        std::pin::pin!(tokio::time::sleep_until(tokio::time::Instant::now()));
    loop {
        if connection_closed.is_closed()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
        {
            return;
        }
        let frame_wait_started = diagnostics.http_body_frame_wait_started();
        let frame = tokio::select! {
            biased;
            _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
            _ = sender.closed() => {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpDrainStopWait) {
                    wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    return;
                }
                #[cfg(coverage)]
                if coverage_fault_is_armed(
                    CoverageFaultPoint::HttpBodyPumpShutdownCompleteTaskBeforeAbort,
                ) {
                    log_error(format_args!(
                        "uvicorn-rs: request-body pump entered shutdown-hold fault"
                    ));
                    wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    std::future::pending::<()>().await;
                }
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpShutdownHang) {
                    wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    std::future::pending::<()>().await;
                }
                drain_http_request_body(&mut body, &mut connection_closed, &cancellation, &request_cancellation).await;
                return;
            }
            _ = &mut body_batch_timer, if body_started.is_some() => {
                diagnostics.http_body_frame_wait_finished(frame_wait_started);
                diagnostics.http_body_batch_timeout_flush();
                if let Some(started) = body_started {
                    diagnostics.http_request_body_batch_deadline_flush(started.elapsed());
                }
                None
            },
            frame = body.frame() => {
                diagnostics.http_body_frame_wait_finished(frame_wait_started);
                Some(frame)
            },
        };
        if frame.is_some() {
            diagnostics.http_request_body_frame_poll_finished(frame_wait_started);
        }
        let Some(frame) = frame else {
            let message = RequestMessage {
                body: RequestBody::take_batch(&mut body_segments, &mut body_len),
                more_body: true,
                disconnected: false,
            };
            body_started = None;
            if !send_http_request_message(
                &mut body,
                &sender,
                &mut connection_closed,
                &cancellation,
                &request_cancellation,
                message,
                RequestBodySendContext {
                    diagnostics: &diagnostics,
                    _mode: RequestBodySendMode::Regular,
                },
            )
            .await
            {
                return;
            }
            continue;
        };

        match frame {
            Some(Ok(frame)) => {
                if let Ok(data) = frame.into_data() {
                    if !data.is_empty() {
                        diagnostics.http_body_data_frame(data.len());
                        if !body_segments.is_empty()
                            && body_len.saturating_add(data.len()) > body_batch_limit
                        {
                            diagnostics.http_body_batch_threshold_flush();
                            diagnostics.http_request_body_batch_size_flush();
                            let message = RequestMessage {
                                body: RequestBody::take_batch(&mut body_segments, &mut body_len),
                                more_body: true,
                                disconnected: false,
                            };
                            body_started = None;
                            if !send_http_request_message(
                                &mut body,
                                &sender,
                                &mut connection_closed,
                                &cancellation,
                                &request_cancellation,
                                message,
                                RequestBodySendContext {
                                    diagnostics: &diagnostics,
                                    _mode: RequestBodySendMode::Regular,
                                },
                            )
                            .await
                            {
                                return;
                            }
                        }
                        if data.len() > body_batch_limit {
                            let message = RequestMessage {
                                body: RequestBody::Single(data),
                                more_body: true,
                                disconnected: false,
                            };
                            if !send_http_request_message(
                                &mut body,
                                &sender,
                                &mut connection_closed,
                                &cancellation,
                                &request_cancellation,
                                message,
                                RequestBodySendContext {
                                    diagnostics: &diagnostics,
                                    _mode: RequestBodySendMode::Regular,
                                },
                            )
                            .await
                            {
                                return;
                            }
                            continue;
                        }
                        if body_segments.is_empty() {
                            let started = tokio::time::Instant::now();
                            body_batch_timer
                                .as_mut()
                                .reset(started + body_batch_max_wait);
                            body_started = Some(started);
                        }
                        body_len = body_len.saturating_add(data.len());
                        body_segments.push(data);
                    }
                }
            }
            Some(Err(_)) => {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpErrorStop)
                    || coverage_fault_take(CoverageFaultPoint::HttpBodyPumpErrorStopWait)
                {
                    request_cancellation.cancel();
                }
                if !body_segments.is_empty() {
                    let message = RequestMessage {
                        body: RequestBody::take_batch(&mut body_segments, &mut body_len),
                        more_body: true,
                        disconnected: false,
                    };
                    let send_mode = {
                        #[cfg(coverage)]
                        {
                            if coverage_fault_take(
                                CoverageFaultPoint::HttpBodyPumpErrorBufferedSendContinues,
                            ) {
                                RequestBodySendMode::ContinueAfterStop
                            } else {
                                RequestBodySendMode::Regular
                            }
                        }
                        #[cfg(not(coverage))]
                        {
                            RequestBodySendMode::Regular
                        }
                    };
                    if !send_http_request_message(
                        &mut body,
                        &sender,
                        &mut connection_closed,
                        &cancellation,
                        &request_cancellation,
                        message,
                        RequestBodySendContext {
                            diagnostics: &diagnostics,
                            _mode: send_mode,
                        },
                    )
                    .await
                    {
                        return;
                    }
                }
                tokio::select! {
                    biased;
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.send(RequestMessage {
                        body: RequestBody::Single(Bytes::new()),
                        more_body: false,
                        disconnected: true,
                    }) => {}
                }
                return;
            }
            None => {
                if !body_segments.is_empty() {
                    diagnostics.http_request_body_eof_flush();
                    let message = RequestMessage {
                        body: RequestBody::take_batch(&mut body_segments, &mut body_len),
                        more_body: true,
                        disconnected: false,
                    };
                    if !send_http_request_message(
                        &mut body,
                        &sender,
                        &mut connection_closed,
                        &cancellation,
                        &request_cancellation,
                        message,
                        RequestBodySendContext {
                            diagnostics: &diagnostics,
                            _mode: RequestBodySendMode::Regular,
                        },
                    )
                    .await
                    {
                        return;
                    }
                }
                let final_message = RequestMessage {
                    body: RequestBody::Single(Bytes::new()),
                    more_body: false,
                    disconnected: false,
                };
                if !send_http_request_message(
                    &mut body,
                    &sender,
                    &mut connection_closed,
                    &cancellation,
                    &request_cancellation,
                    final_message,
                    RequestBodySendContext {
                        diagnostics: &diagnostics,
                        _mode: RequestBodySendMode::Final,
                    },
                )
                .await
                {
                    return;
                }
                tokio::select! {
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpAfterFinalConnectionClosed) {
                            return;
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    _ = sender.closed() => return,
                }
            }
        }
    }
}

async fn send_http_request_message(
    body: &mut Incoming,
    sender: &mpsc::Sender<RequestMessage>,
    connection_closed: &mut ConnectionClosed,
    cancellation: &CancellationToken,
    request_cancellation: &CancellationToken,
    message: RequestMessage,
    send_context: RequestBodySendContext<'_>,
) -> bool {
    let diagnostics = send_context.diagnostics;
    let _send_mode = send_context._mode;
    #[cfg(feature = "runtime-diagnostics")]
    let channel_was_full = sender.capacity() == 0;
    #[cfg(not(feature = "runtime-diagnostics"))]
    let channel_was_full = false;
    let send_wait_started = diagnostics.http_body_channel_send_started(channel_was_full);
    let result = tokio::select! {
        biased;
        _ = async {
            #[cfg(coverage)]
            if _send_mode == RequestBodySendMode::ContinueAfterStop {
                std::future::pending::<()>().await;
            }
            #[cfg(coverage)]
            if _send_mode == RequestBodySendMode::Final {
                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpFinalSendConnectionClosed) {
                    return;
                }
            } else if coverage_fault_take(
                CoverageFaultPoint::HttpBodyPumpBatchThresholdSendConnectionClosed,
            ) {
                return;
            } else if coverage_fault_take(
                CoverageFaultPoint::HttpBodyPumpOversizedSendConnectionClosed,
            ) {
                return;
            } else if coverage_fault_take(
                CoverageFaultPoint::HttpBodyPumpErrorBufferedSendConnectionClosed,
            ) {
                return;
            } else if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpSendConnectionClosed) {
                return;
            }
            wait_for_body_pump_stop(connection_closed, cancellation, request_cancellation).await;
        } => {
            diagnostics.http_body_channel_send_finished(send_wait_started, channel_was_full);
            return false;
        },
        result = sender.send(message) => {
            diagnostics.http_body_channel_send_finished(send_wait_started, channel_was_full);
            result
        },
    };
    if result.is_err() {
        drain_http_request_body(body, connection_closed, cancellation, request_cancellation).await;
        return false;
    }
    true
}

async fn drain_http_request_body(
    body: &mut Incoming,
    connection_closed: &mut ConnectionClosed,
    cancellation: &CancellationToken,
    request_cancellation: &CancellationToken,
) {
    loop {
        let frame = tokio::select! {
            biased;
            _ = wait_for_body_pump_stop(connection_closed, cancellation, request_cancellation) => return,
            frame = body.frame() => frame,
        };
        #[cfg(coverage)]
        let frame = if frame.is_none()
            && coverage_fault_take(CoverageFaultPoint::HttpBodyPumpDrainTerminalFrame)
        {
            None
        } else {
            frame
        };
        match frame {
            Some(Ok(_)) => {}
            Some(Err(_)) | None => return,
        }
    }
}

async fn wait_for_body_pump_stop(
    connection_closed: &mut ConnectionClosed,
    cancellation: &CancellationToken,
    request_cancellation: &CancellationToken,
) {
    tokio::select! {
        biased;
        _ = connection_closed.wait_until_body_pump_stops() => {},
        _ = cancellation.cancelled() => {},
        _ = request_cancellation.cancelled() => {},
    }
}

async fn spawn_request_body_task<F>(tasks: &RequestBodyTasks, task: F)
where
    F: Future<Output = ()> + Send + 'static,
{
    let mut tasks = tasks.lock().await;
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpReapCancelledTask) {
        let completed_handle = tasks.spawn(async {});
        while !completed_handle.is_finished() {
            tokio::task::yield_now().await;
        }
        let abort_handle = tasks.spawn(std::future::pending::<()>());
        abort_handle.abort();
        while !abort_handle.is_finished() {
            tokio::task::yield_now().await;
        }
    }
    while let Some(result) = tasks.try_join_next() {
        if let Err(error) = result {
            log_error(format_args!(
                "uvicorn-rs: request-body pump failed or was cancelled before reaping: {error}"
            ));
        }
    }
    tasks.spawn(task);
}

async fn wait_for_connection_close(
    connection_closed: &mut ConnectionClosed,
    allow_lifetime_completion_fault: bool,
) {
    connection_closed
        .wait_until_closed_with_coverage_fault(allow_lifetime_completion_fault)
        .await;
}

#[cfg(not(feature = "native-tcp"))]
impl<I: AsyncRead + Unpin> AsyncRead for ConnectionIo<I> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &mut tokio::io::ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        if this.read_eof {
            return this.poll_read_after_eof(cx);
        }
        let poll_started = this.diagnostics.tcp_io_poll_started();
        #[cfg(feature = "runtime-diagnostics")]
        let pending_wait_ns = this
            .read_pending_since
            .take()
            .map(|started| started.elapsed().as_nanos().min(u64::MAX as u128) as u64);
        #[cfg(not(feature = "runtime-diagnostics"))]
        let pending_wait_ns = None;
        let filled_before = buffer.filled().len();
        let result = Pin::new(&mut this.io).poll_read(cx, buffer);
        let pending = matches!(&result, Poll::Pending);
        #[cfg(feature = "runtime-diagnostics")]
        if pending {
            this.read_pending_since = Some(std::time::Instant::now());
        }
        let bytes_read = buffer.filled().len().saturating_sub(filled_before);
        this.diagnostics
            .tcp_read_poll_finished(bytes_read, pending, poll_started, pending_wait_ns);
        match result {
            Poll::Ready(Ok(())) if buffer.filled().is_empty() => {
                this.closed.send_replace(true);
                this.read_eof = true;
                this.poll_read_after_eof(cx)
            }
            Poll::Ready(Err(error)) => {
                this.closed.send_replace(true);
                this.read_eof = true;
                if this.active_http_requests.load(Ordering::Acquire) == 0 {
                    Poll::Ready(Err(error))
                } else {
                    this.poll_read_after_eof(cx)
                }
            }
            result => result,
        }
    }
}

#[cfg(not(feature = "native-tcp"))]
impl<I> ConnectionIo<I> {
    fn poll_read_after_eof(&mut self, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        #[cfg(coverage)]
        let recheck_paused = self.eof_recheck_paused;
        #[cfg(not(coverage))]
        let recheck_paused = false;
        if !recheck_paused && self.active_http_requests.load(Ordering::Acquire) == 0 {
            return Poll::Ready(Ok(()));
        }

        self.read_eof_waker.register(cx.waker());
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ConnectionIoEofRecheckPause) {
            // Yield after registering, allowing the real HTTP/2 request guard
            // to drop and wake this task. Resume at the counter recheck rather
            // than blocking a runtime worker or relying on a scheduling delay.
            self.eof_recheck_paused = true;
            return Poll::Pending;
        }
        if self.active_http_requests.load(Ordering::Acquire) == 0 {
            #[cfg(coverage)]
            {
                self.eof_recheck_paused = false;
            }
            Poll::Ready(Ok(()))
        } else {
            Poll::Pending
        }
    }
}

#[cfg(not(feature = "native-tcp"))]
enum WriteBuffers<'a> {
    Scalar(&'a [u8]),
    Vectored(&'a [std::io::IoSlice<'a>]),
}

#[cfg(not(feature = "native-tcp"))]
impl<I: AsyncWrite + Unpin> ConnectionIo<I> {
    #[inline]
    fn poll_write_buffers(
        &mut self,
        cx: &mut Context<'_>,
        buffers: WriteBuffers<'_>,
    ) -> Poll<std::io::Result<usize>> {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerConnectionIoPollWriteError)
            || coverage_fault_take(CoverageFaultPoint::ServerConnectionTaskServiceAwaitError)
            || coverage_fault_take(CoverageFaultPoint::ServerConnectionTaskJoinAwaitError)
            || coverage_fault_take(CoverageFaultPoint::ServerConnectionTaskServiceSelectResult)
            || coverage_fault_take(CoverageFaultPoint::ServerConnectionTaskJoinSelectResult)
        {
            self.closed.send_replace(true);
            return Poll::Ready(Err(std::io::Error::new(
                std::io::ErrorKind::BrokenPipe,
                "coverage-injected connection write error",
            )));
        }
        let poll_started = self.diagnostics.tcp_io_poll_started();
        #[cfg(feature = "runtime-diagnostics")]
        let pending_wait_ns = self
            .write_pending_since
            .take()
            .map(|started| started.elapsed().as_nanos().min(u64::MAX as u128) as u64);
        #[cfg(not(feature = "runtime-diagnostics"))]
        let pending_wait_ns = None;
        let result = match buffers {
            WriteBuffers::Scalar(buffer) => Pin::new(&mut self.io).poll_write(cx, buffer),
            WriteBuffers::Vectored(buffers) => {
                Pin::new(&mut self.io).poll_write_vectored(cx, buffers)
            }
        };
        let pending = matches!(&result, Poll::Pending);
        #[cfg(feature = "runtime-diagnostics")]
        if pending {
            self.write_pending_since = Some(std::time::Instant::now());
        }
        let bytes_written = match &result {
            Poll::Ready(Ok(bytes)) => *bytes,
            Poll::Ready(Err(_)) | Poll::Pending => 0,
        };
        self.diagnostics.tcp_write_poll_finished(
            bytes_written,
            pending,
            poll_started,
            pending_wait_ns,
        );
        match result {
            Poll::Ready(Err(error)) => {
                self.closed.send_replace(true);
                Poll::Ready(Err(error))
            }
            result => result,
        }
    }
}

#[cfg(not(feature = "native-tcp"))]
impl<I: AsyncWrite + Unpin> AsyncWrite for ConnectionIo<I> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<std::io::Result<usize>> {
        self.get_mut()
            .poll_write_buffers(cx, WriteBuffers::Scalar(buffer))
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffers: &[std::io::IoSlice<'_>],
    ) -> Poll<std::io::Result<usize>> {
        self.get_mut()
            .poll_write_buffers(cx, WriteBuffers::Vectored(buffers))
    }

    fn is_write_vectored(&self) -> bool {
        // Hyper retains the original Bytes buffers only when the transport
        // advertises this capability; hiding it makes Hyper copy each payload.
        self.io.is_write_vectored()
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        let poll_started = this.diagnostics.tcp_io_poll_started();
        let result = Pin::new(&mut this.io).poll_flush(cx);
        this.diagnostics.tcp_flush_poll_finished(poll_started);
        result
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        let poll_started = this.diagnostics.tcp_io_poll_started();
        let result = Pin::new(&mut this.io).poll_shutdown(cx);
        this.diagnostics.tcp_shutdown_poll_finished(poll_started);
        result
    }
}

impl AsgiBody {
    fn record_final_body_available(&mut self) {
        #[cfg(feature = "runtime-diagnostics")]
        self.response_timing_diagnostics
            .http_final_body_latency_finished(self.response_latency_started.take());
    }

    fn finish_response(&mut self, application: ResponseApplication) {
        // A final ASGI body completes the transport, while the application may
        // still run background work. Transfer that work to the server now so
        // neither another body poll nor transport teardown delays completion.
        match application {
            ResponseApplication::Running(task) => {
                self.app_task_tracker.spawn(async move {
                    observe_app_after_response(task.await);
                });
            }
            ResponseApplication::Completed(result) => observe_app_after_response(result),
        }
        self.defer_completed_app_result_once = false;
    }

    fn poll_app_task(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Bytes>, BoxError>>> {
        if self.defer_completed_app_result_once {
            self.defer_completed_app_result_once = false;
            cx.waker().wake_by_ref();
            return Poll::Pending;
        }

        let task_result = match self.application.take() {
            Some(ResponseApplication::Completed(result)) => result,
            Some(ResponseApplication::Running(mut task)) => match Pin::new(&mut task).poll(cx) {
                Poll::Ready(result) => result,
                Poll::Pending => {
                    self.application = Some(ResponseApplication::Running(task));
                    return Poll::Pending;
                }
            },
            None => return Poll::Ready(None),
        };

        // The Python completion callback and the body channel are separate
        // wakeup paths. A final app poll can finish after `poll_recv` returned
        // Pending while its already-sent body frame is queued, so drain that
        // frame before reporting the app's completion result.
        if let Ok(chunk) = self.receiver.try_recv() {
            if !chunk.more_body {
                self.record_final_body_available();
                self.finish_response(ResponseApplication::Completed(task_result));
            } else {
                self.application = Some(ResponseApplication::Completed(task_result));
            }
            return Poll::Ready(Some(Ok(Frame::data(chunk.body))));
        }

        // An incomplete ASGI body can make Hyper discard the response start or
        // an earlier body frame that it has not written yet. Yield once before
        // surfacing the app result so the transport can advance the response.
        if !self.incomplete_body_result_deferred {
            self.application = Some(ResponseApplication::Completed(task_result));
            self.defer_completed_app_result_once = true;
            self.incomplete_body_result_deferred = true;
            cx.waker().wake_by_ref();
            return Poll::Pending;
        }

        match task_result {
            Ok(Ok(_)) => Poll::Ready(Some(Err(std::io::Error::other(
                "ASGI app returned before completing the response body",
            )
            .into()))),
            Ok(Err(error)) => {
                Python::attach(|py| error.print(py));
                Poll::Ready(Some(Err(Box::new(error))))
            }
            Err(error) => Poll::Ready(Some(Err(Box::new(error)))),
        }
    }
}

impl Body for AsgiBody {
    type Data = Bytes;
    type Error = BoxError;

    fn poll_frame(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Self::Data>, Self::Error>>> {
        let this = self.get_mut();
        #[cfg(coverage)]
        if !this.body_consumer_pause_started
            && coverage_fault_is_armed(CoverageFaultPoint::HttpResponseBodyConsumerPause)
        {
            // Test-only transport pressure: stop consuming the real body
            // channel briefly so the ASGI producer reaches its bounded-send path.
            this.body_consumer_pause_started = true;
            this.body_consumer_pause = Some(Box::pin(tokio::time::sleep(
                std::time::Duration::from_millis(100),
            )));
        }
        #[cfg(coverage)]
        if let Some(pause) = this.body_consumer_pause.as_mut() {
            if pause.as_mut().poll(cx).is_pending() {
                return Poll::Pending;
            }
            this.body_consumer_pause = None;
        }
        #[cfg(coverage)]
        if this.receiver_pending_pause_active {
            if this.receiver_pending_pause.as_mut().poll(cx).is_pending() {
                return Poll::Pending;
            }
            this.receiver_pending_pause_active = false;
            return this.poll_app_task(cx);
        }
        let Some(application) = this.application.take() else {
            return this.poll_app_task(cx);
        };

        match this.receiver.poll_recv(cx) {
            Poll::Ready(Some(chunk)) => {
                if !chunk.more_body {
                    this.record_final_body_available();
                    this.finish_response(application);
                } else {
                    this.application = Some(application);
                }
                Poll::Ready(Some(Ok(Frame::data(chunk.body))))
            }
            Poll::Ready(None) => {
                this.application = Some(application);
                this.poll_app_task(cx)
            }
            Poll::Pending => {
                this.application = Some(application);
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::HttpResponseBodyPollPendingPause) {
                    // Yield to the runtime after the receiver reports Pending,
                    // then poll app completion before polling the receiver again.
                    // This exercises queued-body recovery without blocking Tokio.
                    this.receiver_pending_pause
                        .as_mut()
                        .reset(tokio::time::Instant::now() + std::time::Duration::from_millis(100));
                    this.receiver_pending_pause_active = true;
                    return Poll::Pending;
                }
                this.poll_app_task(cx)
            }
        }
    }

    fn is_end_stream(&self) -> bool {
        self.application.is_none()
    }

    fn size_hint(&self) -> SizeHint {
        SizeHint::new()
    }
}

#[pyfunction]
#[pyo3(signature = (app, invoke, host, port, backlog, timeout_keep_alive, certfile, keyfile, graceful_timeout, lifespan, root_path, default_headers, date_header, ws_max_size, ws_ping_interval, ws_ping_timeout, limit_concurrency, control, concurrency_limit_callback))]
#[expect(
    clippy::too_many_arguments,
    reason = "the native callable keeps its established Python argument signature"
)]
fn serve<'py>(
    py: Python<'py>,
    app: Py<PyAny>,
    invoke: Py<PyAny>,
    host: String,
    port: u16,
    backlog: i32,
    timeout_keep_alive: i64,
    certfile: Option<String>,
    keyfile: Option<String>,
    graceful_timeout: Option<u64>,
    lifespan: Bound<'py, PyAny>,
    root_path: String,
    default_headers: Vec<(Bytes, Bytes)>,
    date_header: bool,
    ws_max_size: usize,
    ws_ping_interval: Option<f64>,
    ws_ping_timeout: Option<f64>,
    limit_concurrency: Option<usize>,
    control: Py<ServerControl>,
    concurrency_limit_callback: Py<PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let lifespan_mode = LifespanMode::from_python(&lifespan)?;
    let websocket_keepalive =
        WebSocketKeepaliveConfig::from_seconds(ws_ping_interval, ws_ping_timeout)?;
    #[cfg(not(feature = "native-tcp"))]
    if limit_concurrency.is_some() {
        return Err(PyValueError::new_err(
            "limit_concurrency requires the native-tcp feature",
        ));
    }

    let default_headers = default_headers
        .into_iter()
        .map(|(name, value)| {
            let name = HeaderName::from_bytes(&name).map_err(|error| {
                PyValueError::new_err(format!("invalid default HTTP header name: {error}"))
            })?;
            let value = HeaderValue::from_bytes(&value).map_err(|error| {
                PyValueError::new_err(format!("invalid default HTTP header value: {error}"))
            })?;
            Ok((name, value))
        })
        .collect::<PyResult<Vec<_>>>()?;
    let graceful_timeout = graceful_timeout.map(std::time::Duration::from_secs);
    let timeout_keep_alive = std::time::Duration::from_secs(timeout_keep_alive.max(0) as u64);
    #[cfg(coverage)]
    let graceful_timeout = if coverage_fault_take(CoverageFaultPoint::ServerGracefulTimeoutOverflow)
    {
        Some(std::time::Duration::from_secs(u64::MAX))
    } else {
        graceful_timeout
    };
    // Reject an unrepresentable duration before allocating application tasks
    // or opening listeners. The shutdown budget still starts at shutdown.
    if graceful_timeout
        .is_some_and(|timeout| tokio::time::Instant::now().checked_add(timeout).is_none())
    {
        return Err(PyValueError::new_err(
            "graceful_timeout exceeds the supported monotonic deadline range",
        ));
    }
    #[cfg(coverage)]
    {
        let result = if coverage_fault_take(CoverageFaultPoint::ServerControlShutdownBorrowConflict)
        {
            let _exclusive = control.borrow_mut(py);
            control.bind(py).call_method0("shutdown").map(drop)
        } else {
            Ok(())
        };
        result?;
    }
    let (tcp_tls, quic_config) = match (certfile, keyfile) {
        (None, None) => (None, None),
        (Some(certfile), Some(keyfile)) => {
            let (tcp_tls, quic_config) = load_tls_configs(&certfile, &keyfile)?;
            (Some(tcp_tls), Some(quic_config))
        }
        _ => {
            return Err(PyValueError::new_err(
                "--certfile and --keyfile must be provided together",
            ));
        }
    };
    let locals = coverage_value!(
        ServerGetCurrentLocals,
        pyo3_async_runtimes::tokio::get_current_locals(py)
    )?;
    #[cfg(coverage)]
    let serve_control_borrow =
        coverage_fault_take(CoverageFaultPoint::ServerServeControlBorrowConflict)
            .then(|| control.borrow_mut(py));
    let cancellation = control.try_borrow(py)?.cancellation.clone();
    let startup_signal = ServerStartupSignal::new(control.try_borrow(py)?.startup.clone());
    #[cfg(coverage)]
    drop(serve_control_borrow);
    let cancel_on_drop = CancelOnDrop(cancellation.clone());
    let concurrency_limit_callback = Arc::new(concurrency_limit_callback);
    let concurrency_limit_observer: uvicorn_rs::ConcurrencyLimitObserver = Arc::new(move |event| {
        Python::attach(|py| {
            let version = match event.version() {
                http::Version::HTTP_09 => "0.9",
                http::Version::HTTP_10 => "1.0",
                http::Version::HTTP_11 => "1.1",
                http::Version::HTTP_2 => "2",
                http::Version::HTTP_3 => "3",
                _ => "",
            };
            let path = if event.uri().path().is_empty() {
                "/"
            } else {
                event.uri().path()
            };
            let query = event.uri().query().unwrap_or_default();
            if let Err(error) = concurrency_limit_callback.call1(
                py,
                (
                    event.peer_addr().ip().to_string(),
                    event.peer_addr().port(),
                    event.method().as_str(),
                    path,
                    query,
                    version,
                ),
            ) {
                error.print(py);
            }
        });
    });
    let diagnostics = RuntimeDiagnostics::default();
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        let _cancel_on_drop = cancel_on_drop;
        let options = ServeOptions {
            host,
            port,
            backlog,
            timeout_keep_alive,
            root_path,
            tcp_tls,
            quic_config,
            graceful_timeout,
            lifespan_mode,
            default_headers,
            date_header,
            ws_max_size,
            websocket_keepalive,
            concurrency_limit_observer: Some(concurrency_limit_observer),
            #[cfg(feature = "native-tcp")]
            limit_concurrency,
        };
        let result = serve_forever(
            app,
            invoke,
            locals,
            cancellation,
            startup_signal,
            options,
            diagnostics.clone(),
        )
        .await;
        diagnostics.report();
        result
    })
}

fn load_tls_configs(certfile: &str, keyfile: &str) -> PyResult<(TlsAcceptor, quinn::ServerConfig)> {
    let cert_file = std::fs::File::open(certfile).map_err(|error| {
        PyOSError::new_err(format!("could not read certificate {certfile}: {error}"))
    })?;
    let cert_chain = rustls_pemfile::certs(&mut std::io::BufReader::new(cert_file))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| PyValueError::new_err(format!("invalid certificate PEM: {error}")))?;
    if cert_chain.is_empty() {
        return Err(PyValueError::new_err(
            "certificate file contains no certificates",
        ));
    }

    let key_file = std::fs::File::open(keyfile).map_err(|error| {
        PyOSError::new_err(format!("could not read private key {keyfile}: {error}"))
    })?;
    let key = rustls_pemfile::private_key(&mut std::io::BufReader::new(key_file))
        .map_err(|error| PyValueError::new_err(format!("invalid private-key PEM: {error}")))?
        .ok_or_else(|| PyValueError::new_err("private-key file contains no supported key"))?;

    let mut tcp_tls = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(cert_chain, key)
        .map_err(|error| PyValueError::new_err(format!("invalid TLS identity: {error}")))?;
    tcp_tls.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];

    let mut quic_tls = tcp_tls.clone();
    quic_tls.alpn_protocols = vec![b"h3".to_vec()];
    quic_tls.max_early_data_size = 0;
    let quic_config = quinn::ServerConfig::with_crypto(Arc::new(
        coverage_runtime_result!(
            ServerQuicTlsConfigError,
            QuicServerConfig::try_from(quic_tls)
        )
        .map_err(|error| PyValueError::new_err(format!("invalid HTTP/3 TLS identity: {error}")))?,
    ));

    Ok((TlsAcceptor::from(Arc::new(tcp_tls)), quic_config))
}

async fn bind_tcp_listener(host: &str, port: u16, backlog: i32) -> std::io::Result<TcpListener> {
    let addresses = tokio::net::lookup_host((host, port)).await?;
    let mut last_error = None;

    for address in addresses {
        let socket = if address.is_ipv4() {
            TcpSocket::new_v4()
        } else {
            TcpSocket::new_v6()
        };
        let socket = match socket {
            Ok(socket) => socket,
            Err(error) => {
                last_error = Some(error);
                continue;
            }
        };

        #[cfg(not(windows))]
        if let Err(error) = socket.set_reuseaddr(true) {
            last_error = Some(error);
            continue;
        }

        if let Err(error) = socket.bind(address) {
            last_error = Some(error);
            continue;
        }

        match socket.listen(backlog.max(0) as u32) {
            Ok(listener) => return Ok(listener),
            Err(error) => last_error = Some(error),
        }
    }

    Err(last_error.unwrap_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "could not resolve to any address",
        )
    }))
}

async fn serve_forever(
    app: Py<PyAny>,
    invoke: Py<PyAny>,
    locals: TaskLocals,
    cancellation: CancellationToken,
    mut startup_signal: ServerStartupSignal,
    options: ServeOptions,
    diagnostics: RuntimeDiagnostics,
) -> PyResult<()> {
    let listener = bind_tcp_listener(&options.host, options.port, options.backlog)
        .await
        .map_err(|error| {
            PyOSError::new_err(format!(
                "could not bind {}:{}: {error}",
                options.host, options.port
            ))
        })?;
    let local_addr = {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerListenerLocalAddrError) {
            Err(std::io::Error::other(
                "coverage-injected listener address inspection error",
            ))
        } else {
            listener.local_addr()
        }
        #[cfg(not(coverage))]
        {
            listener.local_addr()
        }
    };
    let server_addr = local_addr.map_err(|error| {
        PyOSError::new_err(format!("could not inspect bound listener: {error}"))
    })?;
    let app = Arc::new(app);
    let invoke = Arc::new(invoke);
    let endpoint = if let Some(quic_config) = options.quic_config {
        let endpoint = {
            #[cfg(coverage)]
            if coverage_fault_take(CoverageFaultPoint::ServerHttp3EndpointBindError) {
                Err(std::io::Error::other(
                    "coverage-injected HTTP/3 endpoint bind error",
                ))
            } else {
                quinn::Endpoint::server(quic_config, server_addr)
            }
            #[cfg(not(coverage))]
            {
                quinn::Endpoint::server(quic_config, server_addr)
            }
        };
        Some(endpoint.map_err(|error| {
            PyOSError::new_err(format!("could not bind HTTP/3 endpoint: {error}"))
        })?)
    } else {
        None
    };

    // Lifespan cancellation cleanup has its own tracker: the main lifespan
    // application remains active while request cleanup is drained.
    let lifespan_cleanup_tasks = TaskTracker::new();
    let mut lifespan = if options.lifespan_mode.enabled() {
        let lifespan_start = LifespanRuntime::start(
            Arc::clone(&app),
            Arc::clone(&invoke),
            locals.clone(),
            diagnostics.clone(),
            lifespan_cleanup_tasks.clone(),
            options.lifespan_mode,
        )
        .await;
        match lifespan_start {
            Ok(Some(lifespan)) => Some(lifespan),
            Ok(None) => {
                startup_signal.mark_failed();
                wait_for_lifespan_cleanup(&lifespan_cleanup_tasks, options.graceful_timeout).await;
                return Ok(());
            }
            Err(error) => {
                wait_for_lifespan_cleanup(&lifespan_cleanup_tasks, options.graceful_timeout).await;
                return Err(error);
            }
        }
    } else {
        None
    };
    let state = if options.lifespan_mode.enabled() {
        lifespan.as_ref().and_then(|runtime| runtime.state.clone())
    } else {
        Some(Arc::new(Python::attach(|py| PyDict::new(py).unbind())))
    };
    #[cfg(not(feature = "native-tcp"))]
    let websocket_tasks: WebSocketTasks = Arc::new(Mutex::new(tokio::task::JoinSet::new()));
    let request_body_tasks: RequestBodyTasks = Arc::new(Mutex::new(tokio::task::JoinSet::new()));
    // Track each network-side ASGI task together with its Python cancellation
    // cleanup. An aborted Tokio task can register that cleanup only when its
    // future is dropped, so shutdown must wait for both levels.
    let pending_python_tasks = TaskTracker::new();
    let server = Arc::new(ServerContext {
        app,
        invoke,
        locals,
        server_addr,
        root_path: options.root_path,
        tcp_tls: options.tcp_tls,
        default_headers: options.default_headers,
        date_header: options.date_header,
        ws_max_size: options.ws_max_size,
        websocket_keepalive: options.websocket_keepalive,
        concurrency_limit_observer: options.concurrency_limit_observer,
        #[cfg(feature = "native-tcp")]
        limit_concurrency: options.limit_concurrency,
        state,
        #[cfg(not(feature = "native-tcp"))]
        websocket_tasks,
        request_body_tasks,
        #[cfg(coverage)]
        completed_request_body_pumps: Arc::new(AtomicUsize::new(0)),
        diagnostics,
        cancellation: cancellation.clone(),
        graceful_timeout: options.graceful_timeout,
        pending_python_tasks,
        force_application_shutdown: CancellationToken::new(),
    });
    #[cfg(feature = "native-tcp")]
    let http3_task = endpoint.map(|endpoint| spawn_native_http3(endpoint, Arc::clone(&server)));
    #[cfg(not(feature = "native-tcp"))]
    let http3_task = endpoint.map(|endpoint| {
        let server = Arc::clone(&server);
        tokio::spawn(async move {
            if let Err(error) = serve_legacy_http3(endpoint, server).await {
                log_error(format_args!("uvicorn-rs: HTTP/3 server failed: {error}"));
            }
        })
    });

    // `started` means lifespan startup completed and the bound listeners are
    // ready to accept application traffic. Notify the Python compatibility
    // facade only after all fallible startup work has completed.
    startup_signal.mark_started();

    #[cfg(not(feature = "native-tcp"))]
    let mut connection_tasks: tokio::task::JoinSet<Result<(), BoxError>> =
        tokio::task::JoinSet::new();
    let mut accept_error = None;
    #[cfg(feature = "native-tcp")]
    {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerListenerAcceptError) {
            let _ = uvicorn_rs::arm_listener_accept_fault();
        }
        #[cfg(feature = "runtime-diagnostics")]
        let peer_read_half_close = if std::env::var("UVICORN_RS_DIAGNOSTIC_PEER_READ_MODE")
            .is_ok_and(|mode| mode == "on-read")
        {
            uvicorn_rs::PeerReadHalfCloseMode::OnRead
        } else {
            uvicorn_rs::PeerReadHalfCloseMode::Proactive
        };
        #[cfg(not(feature = "runtime-diagnostics"))]
        let peer_read_half_close = uvicorn_rs::PeerReadHalfCloseMode::Proactive;
        let config = uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: options.graceful_timeout,
            http1_keep_alive_timeout: Some(options.timeout_keep_alive),
            limit_concurrency: server.limit_concurrency,
            default_headers: server.default_headers.clone(),
            // Let an invalid HTTP/1 ASGI response start reach the transport,
            // which closes the connection as Uvicorn does. Ordinary ASGI app
            // exceptions are converted to 500 responses in `handle_request`.
            service_error_policy: uvicorn_rs::ServiceErrorPolicy::Propagate,
            peer_read_half_close,
            error_observer: Some(Arc::new(|event| {
                if event.phase() == uvicorn_rs::ServerErrorPhase::Connection {
                    log_error(format_args!(
                        "uvicorn-rs: HTTP connection from {:?} failed: {} ({:?})",
                        event.peer_addr(),
                        event.error(),
                        event.error()
                    ));
                }
            })),
            concurrency_limit_observer: server.concurrency_limit_observer.clone(),
            ..uvicorn_rs::ServerConfig::default()
        };
        let service = NativeAsgiService {
            server: Arc::clone(&server),
        };
        let result = if let Some(acceptor) = server.tcp_tls.clone() {
            let shutdown = cancellation.clone();
            uvicorn_rs::serve_tls_with_date_header(
                listener,
                acceptor,
                service,
                async move { shutdown.cancelled().await },
                config,
                server.date_header,
            )
            .await
        } else {
            let shutdown = cancellation.clone();
            uvicorn_rs::serve_tcp_with_date_header(
                listener,
                service,
                async move { shutdown.cancelled().await },
                config,
                server.date_header,
            )
            .await
        };
        if let Err(error) = result {
            match error {
                uvicorn_rs::ServeError::GracefulShutdownTimedOut => log_error(format_args!(
                    "uvicorn-rs: TCP shutdown exceeded the graceful timeout"
                )),
                error => {
                    accept_error = Some(PyOSError::new_err(format!(
                        "native TCP server failed: {error}"
                    )));
                }
            }
        }
    }
    #[cfg(not(feature = "native-tcp"))]
    loop {
        tokio::select! {
            biased;
            _ = cancellation.cancelled() => break,
            Some(result) = connection_tasks.join_next(), if !connection_tasks.is_empty() => {
                match result {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => log_error(format_args!("uvicorn-rs: connection task failed: {error:?}")),
                    Err(error) => log_error(format_args!("uvicorn-rs: connection task failed: {error:?}")),
                }
            }
            accepted = async {
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::ServerListenerAcceptError) {
                    return Err(std::io::Error::other("coverage-injected listener accept error"));
                }
                listener.accept().await
            } => match accepted {
                Ok((stream, peer_addr)) => {
                    #[cfg(coverage)]
                    let inject_service_error = coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskServiceError,
                    ) || coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskServiceAwaitError,
                    );
                    #[cfg(coverage)]
                    let inject_service_error_during_shutdown = coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskServiceErrorDuringShutdown,
                    ) || coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskServiceSelectResult,
                    );
                    #[cfg(coverage)]
                    let inject_join_error = coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskJoinError,
                    ) || coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskJoinAwaitError,
                    );
                    #[cfg(coverage)]
                    let inject_join_error_during_shutdown = coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskJoinErrorDuringShutdown,
                    ) || coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskJoinSelectResult,
                    );
                    #[cfg(coverage)]
                    let inject_shutdown_hang = coverage_fault_is_armed(
                        CoverageFaultPoint::ServerConnectionTaskShutdownHang,
                    );
                    let server_for_task = Arc::clone(&server);
                    #[cfg(coverage)]
                    let cancellation_for_task = server_for_task.cancellation.clone();
                    #[cfg(coverage)]
                    let (completed_sender, completed_receiver) =
                        tokio::sync::oneshot::channel::<()>();
                    let connection_task = async move {
                        #[cfg(coverage)]
                        if inject_service_error {
                            serve_connection(stream, peer_addr, server_for_task).await?;
                            return Err(Box::new(std::io::Error::other(
                                "coverage-injected connection service error",
                            )) as BoxError);
                        }
                        #[cfg(coverage)]
                        if inject_join_error {
                            serve_connection(stream, peer_addr, server_for_task).await?;
                            let _ = completed_sender.send(());
                            return std::future::pending::<Result<(), BoxError>>().await;
                        }
                        #[cfg(coverage)]
                        if inject_service_error_during_shutdown {
                            return tokio::select! {
                                biased;
                                _ = cancellation_for_task.cancelled() => Err(Box::new(
                                    std::io::Error::other(
                                        "coverage-injected connection service error during shutdown",
                                    ),
                                ) as BoxError),
                                result = serve_connection(stream, peer_addr, server_for_task) => result,
                            };
                        }
                        #[cfg(coverage)]
                        if inject_join_error_during_shutdown {
                            return tokio::select! {
                                biased;
                                _ = cancellation_for_task.cancelled() => {
                                    let _ = completed_sender.send(());
                                    std::future::pending::<Result<(), BoxError>>().await
                                },
                                result = serve_connection(stream, peer_addr, server_for_task) => result,
                            };
                        }
                        #[cfg(coverage)]
                        if inject_shutdown_hang {
                            return tokio::select! {
                                biased;
                                _ = cancellation_for_task.cancelled() => {
                                    std::future::pending::<Result<(), BoxError>>().await
                                },
                                result = serve_connection(stream, peer_addr, server_for_task) => result,
                            };
                        }
                        serve_connection(stream, peer_addr, server_for_task).await
                    };
                    #[cfg(coverage)]
                    let abort_handle = connection_tasks.spawn(connection_task);
                    #[cfg(not(coverage))]
                    connection_tasks.spawn(connection_task);
                    #[cfg(coverage)]
                    if inject_join_error || inject_join_error_during_shutdown {
                        tokio::spawn(async move {
                            if completed_receiver.await.is_ok() {
                                abort_handle.abort();
                            }
                        });
                    }
                }
                Err(error) => {
                    accept_error = Some(PyOSError::new_err(format!("accept failed: {error}")));
                    break;
                }
            }
        }
    }

    // Stop transport admission before waiting for active responses to drain.
    #[cfg(not(feature = "native-tcp"))]
    drop(listener);
    cancellation.cancel();
    let shutdown_started = tokio::time::Instant::now();
    if let Some(mut http3_task) = http3_task {
        if timeout_optional(
            remaining_graceful_timeout(options.graceful_timeout, shutdown_started),
            &mut http3_task,
        )
        .await
        .is_err()
        {
            log_error(format_args!(
                "uvicorn-rs: HTTP/3 shutdown exceeded grace period"
            ));
            http3_task.abort();
            let _ = http3_task.await;
        }
    }
    #[cfg(not(feature = "native-tcp"))]
    if timeout_optional(
        remaining_graceful_timeout(options.graceful_timeout, shutdown_started),
        async {
            while let Some(result) = connection_tasks.join_next().await {
                match result {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => log_error(format_args!(
                        "uvicorn-rs: connection task failed during shutdown: {error:?}"
                    )),
                    Err(error) => log_error(format_args!(
                        "uvicorn-rs: connection task failed during shutdown: {error:?}"
                    )),
                }
            }
        },
    )
    .await
    .is_err()
    {
        connection_tasks.abort_all();
        while connection_tasks.join_next().await.is_some() {}
    }
    let mut request_body_tasks = server.request_body_tasks.lock().await;
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpShutdownCancelJoin) {
        let abort_handle = request_body_tasks.spawn(std::future::pending::<()>());
        abort_handle.abort();
        tokio::task::yield_now().await;
    }
    if timeout_optional(
        remaining_graceful_timeout(options.graceful_timeout, shutdown_started),
        async {
            while let Some(result) = request_body_tasks.join_next().await {
                if let Err(error) = result {
                    log_error(format_args!(
                        "uvicorn-rs: request-body pump failed or was cancelled during shutdown: {error}"
                    ));
                }
            }
        },
    )
    .await
    .is_err()
    {
        log_error(format_args!(
            "uvicorn-rs: request-body pumps exceeded the graceful timeout"
        ));
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpShutdownCompleteTaskBeforeAbort) {
            let completed_handle = request_body_tasks.spawn(async {});
            while !completed_handle.is_finished() {
                tokio::task::yield_now().await;
            }
        }
        request_body_tasks.abort_all();
        while let Some(result) = request_body_tasks.join_next().await {
            if let Err(error) = result {
                log_error(format_args!(
                    "uvicorn-rs: request-body pump joined after forced abort: {error}"
                ));
            } else {
                log_error(format_args!(
                    "uvicorn-rs: request-body pump completed during forced-abort join"
                ));
            }
        }
    }
    drop(request_body_tasks);
    #[cfg(coverage)]
    {
        let completed = server.completed_request_body_pumps.load(Ordering::Acquire);
        if completed > 0 {
            log_error(format_args!(
                "uvicorn-rs: request-body pumps joined: {completed}"
            ));
        }
    }
    #[cfg(not(feature = "native-tcp"))]
    {
        let mut websocket_tasks = server.websocket_tasks.lock().await;
        if timeout_optional(
            remaining_graceful_timeout(options.graceful_timeout, shutdown_started),
            async {
                while let Some(result) = websocket_tasks.join_next().await {
                    if let Err(error) = result {
                        log_error(format_args!(
                            "uvicorn-rs: WebSocket task failed during shutdown: {error}"
                        ));
                    }
                }
            },
        )
        .await
        .is_err()
        {
            websocket_tasks.abort_all();
            while websocket_tasks.join_next().await.is_some() {}
        }
        drop(websocket_tasks);
    }
    server.pending_python_tasks.close();
    if timeout_optional(options.graceful_timeout, server.pending_python_tasks.wait())
        .await
        .is_err()
    {
        log_error(format_args!(
            "uvicorn-rs: cancelled Python ASGI tasks exceeded the graceful timeout"
        ));
        // Final-response applications retain their normal grace period. Only
        // after it expires do we force their bridges to schedule Python task
        // cancellation and wait for the tracked completion callbacks.
        server.force_application_shutdown.cancel();
        let cleanup_timeout = options
            .graceful_timeout
            .map(|timeout| timeout.max(std::time::Duration::from_millis(100)));
        if timeout_optional(cleanup_timeout, server.pending_python_tasks.wait())
            .await
            .is_err()
        {
            // Cancellation can fail or be suppressed by Python code. Report
            // that cleanup did not finish while keeping server shutdown bounded.
            log_error(format_args!(
                "uvicorn-rs: Python ASGI cancellation cleanup exceeded the graceful timeout"
            ));
        }
    }
    // Uvicorn's graceful timeout bounds connection/application draining only.
    // It does not impose a deadline on the ASGI lifespan shutdown handshake.
    #[cfg(coverage)]
    let lifespan_shutdown_timeout =
        if coverage_fault_is_armed(CoverageFaultPoint::LifespanShutdownForceTimeout) {
            // Give the Python app time to receive shutdown and enter its held
            // state before the timeout cancels the lifespan task.
            Some(std::time::Duration::from_secs(1))
        } else {
            None
        };
    #[cfg(not(coverage))]
    let lifespan_shutdown_timeout = None;
    let shutdown_result = if let Some(lifespan) = lifespan.as_mut() {
        match timeout_optional(lifespan_shutdown_timeout, lifespan.shutdown()).await {
            Ok(result) => result,
            Err(_) => Err(PyRuntimeError::new_err(
                "ASGI lifespan shutdown exceeded the graceful timeout",
            )),
        }
    } else {
        Ok(())
    };
    if let Some(lifespan) = lifespan.as_mut() {
        lifespan.cancel_and_wait().await;
    }
    wait_for_lifespan_cleanup(&lifespan_cleanup_tasks, options.graceful_timeout).await;
    if let Some(error) = accept_error {
        return Err(error);
    }
    shutdown_result
}

async fn wait_for_lifespan_cleanup(
    tracker: &TaskTracker,
    graceful_timeout: Option<std::time::Duration>,
) {
    tracker.close();
    let cleanup_timeout =
        graceful_timeout.map(|timeout| timeout.max(std::time::Duration::from_millis(100)));
    if timeout_optional(cleanup_timeout, tracker.wait())
        .await
        .is_err()
    {
        // Python cancellation may be suppressed or its finally block may take
        // longer than the configured window. Keep the original server error.
        log_error(format_args!(
            "uvicorn-rs: Python ASGI lifespan cancellation cleanup exceeded the graceful timeout"
        ));
    }
}

async fn timeout_optional<T>(
    timeout: Option<std::time::Duration>,
    future: impl Future<Output = T>,
) -> Result<T, ()> {
    match timeout {
        Some(timeout) => tokio::time::timeout(timeout, future).await.map_err(|_| ()),
        None => Ok(future.await),
    }
}

fn remaining_graceful_timeout(
    timeout: Option<std::time::Duration>,
    started: tokio::time::Instant,
) -> Option<std::time::Duration> {
    timeout.map(|timeout| timeout.saturating_sub(started.elapsed()))
}

#[cfg(not(feature = "native-tcp"))]
async fn serve_connection(
    stream: TcpStream,
    peer_addr: SocketAddr,
    server: Arc<ServerContext>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let transport_scheme = if server.tcp_tls.is_some() {
        "https"
    } else {
        "http"
    };
    let (closed_tx, closed_rx) = watch::channel(false);
    let active_http_requests = Arc::new(AtomicUsize::new(0));
    let read_eof_waker = Arc::new(AtomicWaker::new());
    let stream = ConnectionIo {
        io: stream,
        diagnostics: server.diagnostics.clone(),
        closed: closed_tx.clone(),
        active_http_requests: Arc::clone(&active_http_requests),
        read_eof_waker: Arc::clone(&read_eof_waker),
        read_eof: false,
        #[cfg(feature = "runtime-diagnostics")]
        read_pending_since: None,
        #[cfg(feature = "runtime-diagnostics")]
        write_pending_since: None,
        #[cfg(coverage)]
        eof_recheck_paused: false,
    };
    let context = ConnectionContext {
        server: Arc::clone(&server),
        peer_addr,
        transport_scheme,
        connection_closed: ConnectionClosed::Watch(closed_rx),
        #[cfg(feature = "native-tcp")]
        native_upgrade: None,
    };
    let result = if let Some(tls) = server.tcp_tls.as_ref() {
        let stream = tokio::select! {
            biased;
            _ = server.cancellation.cancelled() => return Ok(()),
            result = tls.accept(stream) => result?,
        };
        serve_hyper_connection(
            stream,
            context,
            Arc::clone(&active_http_requests),
            Arc::clone(&read_eof_waker),
        )
        .await
    } else {
        serve_hyper_connection(
            stream,
            context,
            Arc::clone(&active_http_requests),
            Arc::clone(&read_eof_waker),
        )
        .await
    };
    result
}

#[cfg(not(feature = "native-tcp"))]
async fn serve_hyper_connection<I>(
    io: I,
    context: ConnectionContext,
    active_http_requests: Arc<AtomicUsize>,
    read_eof_waker: Arc<AtomicWaker>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    I: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
    let cancellation = context.server.cancellation.clone();
    let graceful_timeout = context.server.graceful_timeout;
    let date_header = context.server.date_header;
    let service_active_http_requests = Arc::clone(&active_http_requests);
    let service_read_eof_waker = Arc::clone(&read_eof_waker);
    let response_header_server = Arc::clone(&context.server);
    let service = service_fn(move |request: Request<Incoming>| {
        let context = context.clone();
        let response_header_server = Arc::clone(&response_header_server);
        let active_http_requests = Arc::clone(&service_active_http_requests);
        let read_eof_waker = Arc::clone(&service_read_eof_waker);
        async move {
            let _active_request = ActiveHttpRequest::new(active_http_requests, read_eof_waker);
            let response = if is_websocket_upgrade(&request) {
                Ok::<_, std::io::Error>(handle_websocket_request(request, context).await)
            } else {
                handle_request(request, context).await
            }?;
            apply_default_response_headers(&response_header_server, response)
        }
    });
    let mut builder = auto::Builder::new(TokioExecutor::new());
    builder
        .http1()
        .auto_date_header(date_header)
        .max_buf_size(64 * 1024);
    builder.http2().auto_date_header(date_header);
    let connection = builder.serve_connection_with_upgrades(TokioIo::new(io), service);
    tokio::pin!(connection);
    tokio::select! {
        result = &mut connection => result?,
        _ = cancellation.cancelled() => {
            connection.as_mut().graceful_shutdown();
            if let Ok(Err(error)) = timeout_optional(graceful_timeout, &mut connection).await {
                // Hyper's auto detector reports its explicit graceful cancellation
                // as a direct Interrupted I/O error before choosing HTTP/1 or HTTP/2.
                // Established connections return hyper::Error instead.
                let detection_cancelled = error
                    .downcast_ref::<std::io::Error>()
                    .is_some_and(|error| error.kind() == std::io::ErrorKind::Interrupted);
                if !detection_cancelled {
                    return Err(error);
                }
            }
        }
    }
    Ok(())
}

#[cfg(feature = "native-tcp")]
fn spawn_native_http3(
    endpoint: quinn::Endpoint,
    server: Arc<ServerContext>,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        #[cfg(coverage)]
        if coverage_legacy_http3_fault_is_armed() {
            serve_legacy_http3(endpoint, server).await;
            return;
        }

        let shutdown = server.cancellation.clone();
        let config = uvicorn_rs::ServerConfig {
            graceful_shutdown_timeout: server.graceful_timeout,
            service_error_policy: uvicorn_rs::ServiceErrorPolicy::Propagate,
            concurrency_limit_observer: server.concurrency_limit_observer.clone(),
            ..uvicorn_rs::ServerConfig::default()
        };
        let service = NativeHttp3AsgiService {
            server: Arc::clone(&server),
        };
        if let Err(error) = uvicorn_rs::serve_http3(
            endpoint,
            service,
            async move { shutdown.cancelled().await },
            config,
        )
        .await
        {
            log_error(format_args!("uvicorn-rs: HTTP/3 server failed: {error}"));
        }
    })
}

#[cfg(all(feature = "native-tcp", coverage))]
fn coverage_legacy_http3_fault_is_armed() -> bool {
    // This coverage-only selector lets a real peer-close input exercise the
    // retained legacy HTTP/3 path without injecting a runtime failure.
    if coverage_fault_take(CoverageFaultPoint::Http3LegacyPathSelection) {
        return true;
    }
    [
        CoverageFaultPoint::Http3RequestTaskPanic,
        CoverageFaultPoint::Http3RequestTaskPanicAfterResponse,
        CoverageFaultPoint::Http3ConnectionAcceptFinished,
        CoverageFaultPoint::Http3ConnectionTaskPanic,
        CoverageFaultPoint::Http3EndpointAcceptClosed,
        CoverageFaultPoint::Http3ConnectionTaskPanicDuringShutdown,
        CoverageFaultPoint::Http3ConnectionTaskShutdownHang,
        CoverageFaultPoint::Http3ConnectionCreateError,
        CoverageFaultPoint::Http3ConnectionAcceptError,
        CoverageFaultPoint::HttpAppTaskPanicBeforeResponseStart,
        CoverageFaultPoint::Http3PeerCloseUnexpectedError,
        CoverageFaultPoint::Http3PeerCloseReasonUnavailable,
        CoverageFaultPoint::Http3RequestResolveError,
        CoverageFaultPoint::Http3ResponseBuilderError,
        CoverageFaultPoint::Http3ResponseSendError,
        CoverageFaultPoint::Http3ResponseBodyFrameError,
        CoverageFaultPoint::Http3ResponseNonDataFrame,
        CoverageFaultPoint::Http3ResponseBodySendError,
        CoverageFaultPoint::Http3ResponseFinishError,
        CoverageFaultPoint::Http3BodyPumpConnectionClosed,
        CoverageFaultPoint::Http3BodyPumpConnectionClosedSelect,
        CoverageFaultPoint::Http3BodyPumpSenderClosedSelect,
        CoverageFaultPoint::Http3BodyPumpFinalMessageConnectionClosedSelect,
        CoverageFaultPoint::Http3BodyPumpFinalMessageSendError,
        CoverageFaultPoint::Http3BodyPumpEmptyData,
        CoverageFaultPoint::Http3BodyPumpSendError,
        CoverageFaultPoint::Http3BodyPumpSendConnectionClosed,
        CoverageFaultPoint::Http3BodyPumpErrorStop,
        CoverageFaultPoint::ServerHttp3TaskShutdownHang,
    ]
    .into_iter()
    .any(coverage_fault_is_armed)
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
async fn serve_legacy_http3(
    endpoint: quinn::Endpoint,
    server: Arc<ServerContext>,
) -> Result<(), BoxError> {
    let mut connections = tokio::task::JoinSet::new();
    #[cfg(coverage)]
    let mut inject_connection_task_shutdown_hang = false;
    loop {
        tokio::select! {
            biased;
            _ = server.cancellation.cancelled() => break,
            Some(result) = connections.join_next(), if !connections.is_empty() => {
                if let Err(error) = result {
                    log_error(format_args!("uvicorn-rs: HTTP/3 connection task failed: {error}"));
                }
            }
            incoming = async {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3EndpointAcceptClosed) {
                    return None;
                }
                endpoint.accept().await
            } => {
                let Some(incoming) = incoming else { break; };
                let server = Arc::clone(&server);
                #[cfg(coverage)]
                let inject_join_error =
                    coverage_fault_take(CoverageFaultPoint::Http3ConnectionTaskPanic);
                #[cfg(coverage)]
                let inject_shutdown_panic =
                    coverage_fault_take(CoverageFaultPoint::Http3ConnectionTaskPanicDuringShutdown);
                #[cfg(coverage)]
                let inject_shutdown_hang =
                    coverage_fault_take(CoverageFaultPoint::Http3ConnectionTaskShutdownHang);
                #[cfg(coverage)]
                if inject_shutdown_hang {
                    inject_connection_task_shutdown_hang = true;
                }
                #[cfg(coverage)]
                let connection_cancellation = server.cancellation.clone();
                connections.spawn(async move {
                    #[cfg(coverage)]
                    if inject_join_error {
                        coverage_panic("coverage-injected HTTP/3 connection task panic");
                    }
                    match incoming.await {
                        Ok(connection) => {
                            let peer_addr = connection.remote_address();
                            if let Err(error) =
                                serve_http3_connection(connection, Arc::clone(&server)).await
                            {
                                log_error(format_args!("uvicorn-rs: HTTP/3 connection from {peer_addr} failed: {error}"));
                            }
                            #[cfg(coverage)]
                            if inject_shutdown_panic {
                                connection_cancellation.cancelled().await;
                                coverage_panic("coverage-injected HTTP/3 connection task panic during shutdown");
                            }
                            #[cfg(coverage)]
                            if inject_shutdown_hang {
                                connection_cancellation.cancelled().await;
                                std::future::pending::<()>().await;
                            }
                        }
                        Err(error) => log_error(format_args!("uvicorn-rs: HTTP/3 handshake failed: {error}")),
                    }
                });
            }
        }
    }

    endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown");
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::ServerHttp3TaskShutdownHang) {
        std::future::pending::<()>().await;
    }
    #[cfg(coverage)]
    let connection_drain_timeout = if inject_connection_task_shutdown_hang {
        Some(std::time::Duration::from_millis(100))
    } else {
        server.graceful_timeout
    };
    #[cfg(not(coverage))]
    let connection_drain_timeout = server.graceful_timeout;
    if timeout_optional(connection_drain_timeout, async {
        while let Some(result) = connections.join_next().await {
            if let Err(error) = result {
                log_error(format_args!(
                    "uvicorn-rs: HTTP/3 connection task failed during shutdown: {error}"
                ));
            }
        }
    })
    .await
    .is_err()
    {
        log_error(format_args!(
            "uvicorn-rs: HTTP/3 connection tasks exceeded grace period; aborting remaining tasks"
        ));
        connections.abort_all();
        while connections.join_next().await.is_some() {}
    }
    let _ = timeout_optional(server.graceful_timeout, endpoint.wait_idle()).await;
    Ok(())
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
async fn serve_http3_connection(
    connection: quinn::Connection,
    server: Arc<ServerContext>,
) -> Result<(), BoxError> {
    // HTTP/3 defines H3_INTERNAL_ERROR as 0x102; its u32 representation
    // constructs a QUIC variable integer without a fallible conversion.
    const INTERNAL_ERROR_CODE: quinn::VarInt = quinn::VarInt::from_u32(0x102);

    let peer_addr = connection.remote_address();
    let (closed_tx, closed_rx) = watch::channel(false);
    let close_monitor = connection.clone();
    tokio::spawn(async move {
        close_monitor.closed().await;
        closed_tx.send_replace(true);
    });
    let created = coverage_runtime_result!(
        Http3ConnectionCreateError,
        h3::server::Connection::new(h3_quinn::Connection::new(connection.clone())).await
    );
    let mut h3_connection = match created {
        Ok(connection) => connection,
        Err(error) => {
            connection.close(
                INTERNAL_ERROR_CODE,
                b"HTTP/3 connection initialization failed",
            );
            return Err(error);
        }
    };
    let mut requests = tokio::task::JoinSet::new();
    let mut connection_result = Ok(());
    loop {
        let accepted_result = tokio::select! {
            biased;
            _ = server.cancellation.cancelled() => {
                connection_result = h3_connection.shutdown(0).await.map_err(BoxError::from);
                break;
            }
            Some(result) = requests.join_next(), if !requests.is_empty() => {
                // Completed task allocations remain owned by JoinSet until
                // joined. Reap them while a long-lived connection accepts
                // requests, rather than accumulating them until peer close.
                observe_http3_request_task(result);
                continue;
            }
            result = async {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3ConnectionAcceptFinished) {
                    connection.close(quinn::VarInt::from_u32(0), b"coverage accept finished");
                    return Ok(None);
                }
                coverage_runtime_result!(Http3ConnectionAcceptError, h3_connection.accept().await)
            } => result,
        };
        let accepted = match accepted_result {
            Ok(accepted) => accepted,
            Err(error) if is_http3_peer_close_ignorable(error.as_ref(), &connection) => {
                // RFC 9114 requires unknown application close codes to be
                // treated as H3_NO_ERROR. A peer's normal HTTP/3 close ends
                // acceptance; drain owned request tasks below.
                break;
            }
            Err(error) => {
                let _ = h3_connection.shutdown(0).await;
                connection.close(INTERNAL_ERROR_CODE, b"HTTP/3 request acceptance failed");
                connection_result = Err(error);
                requests.abort_all();
                break;
            }
        };
        let Some(resolver) = accepted else {
            break;
        };
        let context = ConnectionContext {
            server: Arc::clone(&server),
            peer_addr,
            transport_scheme: "https",
            connection_closed: ConnectionClosed::Watch(closed_rx.clone()),
            #[cfg(feature = "native-tcp")]
            native_upgrade: None,
        };
        requests.spawn(async move {
            #[cfg(coverage)]
            if coverage_fault_take(CoverageFaultPoint::Http3RequestTaskPanic) {
                coverage_panic("coverage-injected HTTP/3 request task panic");
            }
            if let Err(error) = handle_http3_request(resolver, context).await {
                log_error(format_args!(
                    "uvicorn-rs: HTTP/3 request from {peer_addr} failed: {error}"
                ));
            }
            #[cfg(coverage)]
            if coverage_fault_take(CoverageFaultPoint::Http3RequestTaskPanicAfterResponse) {
                // Exercise join failure after real response completion without
                // dropping an unresolved request stream or changing normal IO.
                coverage_panic("coverage-injected HTTP/3 request task panic after response");
            }
        });
    }
    // The server-level HTTP/3 JoinSet owns the graceful-shutdown deadline.
    // A second equal timeout here races the outer timer: it can cancel this
    // connection task before request cleanup runs. If the server deadline
    // expires, dropping that parent task also aborts every task in this set.
    while let Some(result) = requests.join_next().await {
        observe_http3_request_task(result);
    }
    connection_result
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
fn is_http3_peer_close_ignorable(
    error: &(dyn StdError + 'static),
    connection: &quinn::Connection,
) -> bool {
    let Some(connection_error) = error.downcast_ref::<h3::error::ConnectionError>() else {
        return false;
    };
    if connection_error.is_h3_no_error() {
        return true;
    }
    // h3 0.0.8 makes fields of its Remote error variant unmatchable outside
    // the crate. Its public display text identifies the remote application
    // close; Quinn's typed close reason supplies the numeric code below.
    let is_peer_application_close = connection_error
        .to_string()
        .starts_with("Remote error: ApplicationClose: ");
    #[cfg(coverage)]
    let is_peer_application_close = is_peer_application_close
        && !coverage_fault_take(CoverageFaultPoint::Http3PeerCloseUnexpectedError);
    if !is_peer_application_close {
        return false;
    }
    let close_reason = {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::Http3PeerCloseReasonUnavailable) {
            None
        } else {
            connection.close_reason()
        }
        #[cfg(not(coverage))]
        {
            connection.close_reason()
        }
    };
    let Some(quinn::ConnectionError::ApplicationClosed(close)) = close_reason else {
        return false;
    };

    // h3 0.0.8 exposes the peer's application code through its public QUIC
    // error. Preserve errors registered by RFC 9114, QPACK, and RFC 9297;
    // future or private codes follow RFC 9114 section 8 and are non-errors.
    !matches!(close.error_code.into(), 0x33 | 0x100..=0x110 | 0x200..=0x202)
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
fn observe_http3_request_task(result: Result<(), tokio::task::JoinError>) {
    if let Err(error) = result {
        log_error(format_args!(
            "uvicorn-rs: HTTP/3 request task failed: {error}"
        ));
    }
}

#[cfg(feature = "native-tcp")]
async fn handle_http3_asgi_request(
    request: Request<uvicorn_rs::Http3RequestBody>,
    context: ConnectionContext,
) -> Result<Response<ResponseBody>, std::io::Error> {
    let (parts, body) = request.into_parts();
    let request_cancellation = CancellationToken::new();
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpCancelBeforeFirstPoll) {
        request_cancellation.cancel();
    }
    let pump_request_cancellation = request_cancellation.clone();
    let (request_tx, request_rx) = mpsc::channel(1);
    #[cfg(coverage)]
    let request_rx = {
        let mut receiver = request_rx;
        if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpSenderClosed) {
            receiver.close();
        }
        receiver
    };
    let request_body_tasks = Arc::clone(&context.server.request_body_tasks);
    let cancellation = context.server.cancellation.clone();
    let connection_closed = context.connection_closed.clone();
    #[cfg(coverage)]
    let completed_pumps = Arc::clone(&context.server.completed_request_body_pumps);
    spawn_request_body_task(&request_body_tasks, async move {
        pump_native_http3_request_body(
            body,
            request_tx,
            connection_closed,
            cancellation,
            pump_request_cancellation,
        )
        .await;
        #[cfg(coverage)]
        completed_pumps.fetch_add(1, Ordering::Release);
    })
    .await;

    match handle_request_parts(parts, request_rx, None, request_cancellation, context).await {
        Ok(response) => Ok(response),
        Err(error) => {
            log_error(format_args!(
                "uvicorn-rs: HTTP/3 ASGI request failed: {error}"
            ));
            let body = if error.downcast_ref::<InvalidAsgiResponseStart>().is_some() {
                Bytes::new()
            } else {
                Bytes::from_static(b"Internal Server Error")
            };
            Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR,
                full_body(body),
                HeaderMap::new(),
            ))
        }
    }
}

#[cfg(feature = "native-tcp")]
async fn pump_native_http3_request_body(
    mut body: uvicorn_rs::Http3RequestBody,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: ConnectionClosed,
    cancellation: CancellationToken,
    request_cancellation: CancellationToken,
) {
    let mut peer_stop_notification = Box::pin(body.peer_stop_notification());
    let mut peer_stop_notification_open = true;
    #[cfg(coverage)]
    let mut pending_coverage_data: Option<Bytes> = None;
    #[cfg(coverage)]
    let mut coverage_body_message_sent = false;
    loop {
        if connection_closed.is_closed()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
        {
            return;
        }

        let frame = tokio::select! {
            biased;
            _ = async {
                #[cfg(coverage)]
                if coverage_body_message_sent
                    && coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpStopWait)
                {
                    return;
                }
                wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
            } => return,
            _ = sender.closed() => return,
            frame = async {
                #[cfg(coverage)]
                if let Some(data) = pending_coverage_data.take() {
                    return Some(Ok(Frame::data(data)));
                }
                body.frame().await
            } => frame,
            peer_stopped = &mut peer_stop_notification, if peer_stop_notification_open => {
                if peer_stopped {
                    send_native_http3_disconnect(
                        &sender,
                        &mut connection_closed,
                        &cancellation,
                        &request_cancellation,
                    ).await;
                    return;
                }
                peer_stop_notification_open = false;
                continue;
            }
        };
        match frame {
            Some(Ok(frame)) => {
                let Ok(data) = frame.into_data() else {
                    // HTTP/3 request trailers are not part of the current ASGI
                    // adapter contract. Keep polling until the body ends.
                    continue;
                };
                #[cfg(coverage)]
                let data = if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpEmptyData)
                {
                    // The HTTP/3 decoder consumes wire-level empty DATA frames
                    // before exposing body frames. Preserve this real payload
                    // while checking the native pump's empty-frame behavior.
                    pending_coverage_data = Some(data);
                    Bytes::new()
                } else {
                    data
                };
                if data.is_empty() {
                    continue;
                }
                let message = RequestMessage {
                    body: RequestBody::Single(data),
                    more_body: true,
                    disconnected: false,
                };
                let result = tokio::select! {
                    biased;
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpSendStopWait) {
                            request_cancellation.cancel();
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    result = sender.send(message) => result,
                };
                if result.is_err() {
                    return;
                }
                #[cfg(coverage)]
                {
                    coverage_body_message_sent = true;
                }
            }
            Some(Err(_)) => {
                let disconnected = RequestMessage {
                    body: RequestBody::Single(Bytes::new()),
                    more_body: false,
                    disconnected: true,
                };
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpErrorStopWait) {
                    request_cancellation.cancel();
                }
                tokio::select! {
                    biased;
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.send(disconnected) => {}
                }
                return;
            }
            None => {
                let completed = RequestMessage {
                    body: RequestBody::Single(Bytes::new()),
                    more_body: false,
                    disconnected: false,
                };
                let result = tokio::select! {
                    biased;
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(
                            CoverageFaultPoint::Http3NativeBodyPumpFinalMessageStopWait,
                        ) {
                            request_cancellation.cancel();
                        }
                        wait_for_body_pump_stop(
                            &mut connection_closed,
                            &cancellation,
                            &request_cancellation,
                        ).await;
                    } => return,
                    result = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(
                            CoverageFaultPoint::Http3NativeBodyPumpFinalMessageSendError,
                        ) {
                            return Err(tokio::sync::mpsc::error::SendError(completed));
                        }
                        sender.send(completed).await
                    } => result,
                };
                if result.is_err() {
                    return;
                }
                tokio::select! {
                    biased;
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.closed() => return,
                    peer_stopped = &mut peer_stop_notification, if peer_stop_notification_open => {
                        if peer_stopped {
                            send_native_http3_disconnect(
                                &sender,
                                &mut connection_closed,
                                &cancellation,
                                &request_cancellation,
                            ).await;
                        }
                        return;
                    }
                }
            }
        }
    }
}

async fn send_native_http3_disconnect(
    sender: &mpsc::Sender<RequestMessage>,
    connection_closed: &mut ConnectionClosed,
    cancellation: &CancellationToken,
    request_cancellation: &CancellationToken,
) {
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::Http3NativeBodyPumpDisconnectSendStopWait) {
        request_cancellation.cancel();
    }

    let disconnected = RequestMessage {
        body: RequestBody::Single(Bytes::new()),
        more_body: false,
        disconnected: true,
    };
    tokio::select! {
        biased;
        _ = wait_for_body_pump_stop(connection_closed, cancellation, request_cancellation) => {},
        _ = sender.send(disconnected) => {},
    }
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
async fn handle_http3_request(
    resolver: h3::server::RequestResolver<h3_quinn::Connection, Bytes>,
    context: ConnectionContext,
) -> Result<(), BoxError> {
    let response_header_server = Arc::clone(&context.server);
    let resolved = resolver.resolve_request().await.map_err(BoxError::from);
    #[cfg(coverage)]
    let resolved = resolved.and_then(|(request, mut stream)| {
        if coverage_fault_take(CoverageFaultPoint::Http3RequestResolveError) {
            stream.stop_stream(h3::error::Code::H3_INTERNAL_ERROR);
            Err(BoxError::from(std::io::Error::other(
                "coverage-injected HTTP/3 request resolution error",
            )))
        } else {
            Ok((request, stream))
        }
    });
    let (request, stream) = resolved?;
    let (parts, ()) = request.into_parts();
    let (mut send_stream, receive_stream) = stream.split();
    let (request_tx, request_rx) = mpsc::channel(1);
    let request_body_tasks = Arc::clone(&context.server.request_body_tasks);
    let cancellation = context.server.cancellation.clone();
    let request_cancellation = CancellationToken::new();
    let pump_request_cancellation = request_cancellation.clone();
    let connection_closed = context.connection_closed.clone();
    #[cfg(coverage)]
    let completed_pumps = Arc::clone(&context.server.completed_request_body_pumps);
    spawn_request_body_task(&request_body_tasks, async move {
        pump_h3_request_body(
            receive_stream,
            request_tx,
            connection_closed,
            cancellation,
            pump_request_cancellation,
        )
        .await;
        #[cfg(coverage)]
        completed_pumps.fetch_add(1, Ordering::Release);
    })
    .await;

    let response =
        match handle_request_parts(parts, request_rx, None, request_cancellation, context).await {
            Ok(response) => response,
            Err(error) => {
                log_error(format_args!(
                    "uvicorn-rs: HTTP/3 ASGI request failed: {error}"
                ));
                let body = if error.downcast_ref::<InvalidAsgiResponseStart>().is_some() {
                    Bytes::new()
                } else {
                    Bytes::from_static(b"Internal Server Error")
                };
                response(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    full_body(body),
                    HeaderMap::new(),
                )
            }
        };
    let response = apply_default_response_headers(&response_header_server, response)?;

    let response_result: Result<(), BoxError> = async {
        let (response_parts, mut body) = response.into_parts();
        let response_builder = Response::builder()
            .version(Version::HTTP_3)
            .status(response_parts.status);
        #[cfg(coverage)]
        let response_builder = if coverage_fault_take(CoverageFaultPoint::Http3ResponseBuilderError)
        {
            response_builder.header("", "")
        } else {
            response_builder
        };
        let mut http3_response = response_builder.body(()).map_err(BoxError::from)?;
        *http3_response.headers_mut() = response_parts.headers;
        coverage_runtime_result!(
            Http3ResponseSendError,
            send_stream.send_response(http3_response).await
        )?;
        while let Some(frame) = body.frame().await {
            #[cfg(coverage)]
            let frame = if coverage_fault_take(CoverageFaultPoint::Http3ResponseBodyFrameError) {
                Err(Box::new(std::io::Error::other(
                    "coverage-injected HTTP/3 response body frame error",
                )) as BoxError)
            } else {
                frame
            };
            let frame = frame?;
            #[cfg(coverage)]
            let frame = if coverage_fault_take(CoverageFaultPoint::Http3ResponseNonDataFrame) {
                Frame::trailers(http::HeaderMap::new())
            } else {
                frame
            };
            // Both response body constructors (Full and AsgiBody) emit DATA
            // only. Response trailers are not in the supported ASGI surface.
            let data = frame.into_data().map_err(|_| {
                std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "ASGI response body emitted a non-DATA frame",
                )
            })?;
            if !data.is_empty() {
                coverage_runtime_result!(
                    Http3ResponseBodySendError,
                    send_stream.send_data(data).await
                )?;
            }
        }
        coverage_runtime_result!(Http3ResponseFinishError, send_stream.finish().await)?;
        Ok(())
    }
    .await;
    if response_result.is_err() {
        send_stream.stop_stream(h3::error::Code::H3_INTERNAL_ERROR);
    }
    response_result?;
    Ok(())
}

#[cfg(any(not(feature = "native-tcp"), coverage))]
async fn pump_h3_request_body(
    mut body: h3::server::RequestStream<h3_quinn::RecvStream, Bytes>,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: ConnectionClosed,
    cancellation: CancellationToken,
    request_cancellation: CancellationToken,
) {
    #[cfg(coverage)]
    let mut pending_data: Option<Bytes> = None;
    loop {
        #[cfg(coverage)]
        if connection_closed.is_closed()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
            || coverage_fault_take(CoverageFaultPoint::Http3BodyPumpConnectionClosed)
        {
            return;
        }
        #[cfg(not(coverage))]
        if connection_closed.is_closed()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
        {
            return;
        }
        let data = tokio::select! {
            biased;
            _ = async {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpConnectionClosedSelect) {
                    return;
                }
                wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
            } => return,
            _ = async {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpSenderClosedSelect) {
                    return;
                }
                sender.closed().await;
            } => return,
            result = async {
                #[cfg(coverage)]
                if let Some(data) = pending_data.take() {
                    return Ok(Some(data));
                }
                body.recv_data().await.map(|data| data.map(|mut buffer| {
                    let len = buffer.remaining();
                    buffer.copy_to_bytes(len)
                }))
            } => result,
        };
        match data {
            Ok(Some(chunk)) => {
                #[cfg(coverage)]
                let chunk = if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpEmptyData) {
                    // h3 coalesces empty DATA frames. Keep the real Bytes for
                    // the next iteration while exercising the same empty path.
                    pending_data = Some(chunk);
                    Bytes::new()
                } else {
                    chunk
                };
                if chunk.is_empty() {
                    continue;
                }
                let message = RequestMessage {
                    body: RequestBody::Single(chunk),
                    more_body: true,
                    disconnected: false,
                };
                tokio::select! {
                    biased;
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpSendConnectionClosed) {
                            return;
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    result = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpSendError) {
                            return Err(tokio::sync::mpsc::error::SendError(message));
                        }
                        sender.send(message).await
                    } => {
                        if result.is_err() {
                            let _ = sender.try_send(RequestMessage {
                                body: RequestBody::Single(Bytes::new()),
                                more_body: false,
                                disconnected: true,
                            });
                            return;
                        }
                    }
                }
            }
            Ok(None) => {
                let message = RequestMessage {
                    body: RequestBody::Single(Bytes::new()),
                    more_body: false,
                    disconnected: false,
                };
                tokio::select! {
                    biased;
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(
                            CoverageFaultPoint::Http3BodyPumpFinalMessageConnectionClosedSelect,
                        ) {
                            let _ = sender.send(RequestMessage {
                                body: RequestBody::Single(Bytes::new()),
                                more_body: false,
                                disconnected: false,
                            }).await;
                            return;
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    result = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpFinalMessageSendError) {
                            return Err(tokio::sync::mpsc::error::SendError(message));
                        }
                        sender.send(message).await
                    } => {
                        if result.is_err() {
                            return;
                        }
                    }
                }
                tokio::select! {
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.closed() => return,
                }
            }
            Err(_) => {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::Http3BodyPumpErrorStop) {
                    request_cancellation.cancel();
                }
                tokio::select! {
                    biased;
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.send(RequestMessage {
                        body: RequestBody::Single(Bytes::new()),
                        more_body: false,
                        disconnected: true,
                    }) => {}
                }
                return;
            }
        }
    }
}

async fn handle_request(
    request: Request<Incoming>,
    context: ConnectionContext,
) -> Result<Response<ResponseBody>, std::io::Error> {
    let version = request.version();
    match handle_request_inner(request, context).await {
        Ok(response) => Ok(response),
        Err(error)
            if error.downcast_ref::<InvalidAsgiResponseStart>().is_some()
                && version == Version::HTTP_2 =>
        {
            Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR,
                full_body(Bytes::new()),
                HeaderMap::new(),
            ))
        }
        Err(error) if error.downcast_ref::<InvalidAsgiResponseStart>().is_some() => {
            Err(std::io::Error::other(error))
        }
        Err(error) => {
            log_error(format_args!("uvicorn-rs: ASGI request failed: {error}"));
            let body = if version == Version::HTTP_2 {
                Bytes::new()
            } else {
                Bytes::from_static(b"Internal Server Error")
            };
            Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR,
                full_body(body),
                HeaderMap::new(),
            ))
        }
    }
}

async fn handle_request_inner(
    request: Request<Incoming>,
    context: ConnectionContext,
) -> Result<Response<ResponseBody>, BoxError> {
    let (parts, body) = request.into_parts();
    let request_cancellation = CancellationToken::new();
    let mut request_cancellation_guard = (parts.version == Version::HTTP_2)
        .then(|| RequestCancellationGuard::new(request_cancellation.clone()));
    let (request_tx, request_rx) = mpsc::channel(1);
    let request_sender = if body.is_end_stream() {
        coverage_runtime_result!(
            HttpEmptyRequestChannelClosed,
            request_tx.try_send(RequestMessage {
                body: RequestBody::Single(Bytes::new()),
                more_body: false,
                disconnected: false,
            })
        )?;
        Some(request_tx)
    } else {
        let request_body_tasks = Arc::clone(&context.server.request_body_tasks);
        let cancellation = context.server.cancellation.clone();
        let connection_closed = context.connection_closed.clone();
        let pump_request_cancellation = request_cancellation.clone();
        let pump_diagnostics = context.server.diagnostics.clone();
        #[cfg(coverage)]
        let completed_pumps = Arc::clone(&context.server.completed_request_body_pumps);
        spawn_request_body_task(&request_body_tasks, async move {
            pump_http_request_body(
                body,
                request_tx,
                connection_closed,
                cancellation,
                pump_request_cancellation,
                pump_diagnostics,
            )
            .await;
            #[cfg(coverage)]
            completed_pumps.fetch_add(1, Ordering::Release);
        })
        .await;
        None
    };
    let result = handle_request_parts(
        parts,
        request_rx,
        request_sender,
        request_cancellation,
        context,
    )
    .await;
    if let Some(guard) = &mut request_cancellation_guard {
        guard.disarm();
    }
    result
}

async fn handle_request_parts(
    parts: http::request::Parts,
    request_messages: mpsc::Receiver<RequestMessage>,
    request_sender: Option<mpsc::Sender<RequestMessage>>,
    request_cancellation: CancellationToken,
    context: ConnectionContext,
) -> Result<Response<ResponseBody>, BoxError> {
    let http_version = parts.version;
    let diagnostics = context.server.diagnostics.clone();
    diagnostics.http_request_started();
    let response_latency_started = diagnostics.http_response_latency_started();
    let response_timing_diagnostics = diagnostics.clone();
    let (start_tx, mut start_rx) = mpsc::channel(1);
    let (body_tx, body_rx) = mpsc::channel(RESPONSE_BODY_QUEUE_CAPACITY);
    let response_start_attempted = Arc::new(AtomicBool::new(false));
    let response_started = Arc::new(AtomicBool::new(false));
    let app_response_start_attempted = Arc::clone(&response_start_attempted);
    let app_response_started = Arc::clone(&response_started);
    let preserve_application_on_disconnect = Arc::new(AtomicBool::new(false));
    let app_preserve_application_on_disconnect = Arc::clone(&preserve_application_on_disconnect);
    let app_task_tracker = context.server.pending_python_tasks.clone();
    let cancellation_tracker = app_task_tracker.clone();
    let force_application_shutdown = context.server.force_application_shutdown.clone();
    let python_attach_wait_started = diagnostics.http_python_attach_wait_started();
    let python_attach_wait_diagnostics = diagnostics.clone();
    let app_future = async move {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::HttpAppTaskPanicBeforeResponseStart)
            || coverage_fault_take(CoverageFaultPoint::Http3NativeAppTaskPanicBeforeResponseStart)
        {
            coverage_panic("coverage-injected ASGI request task panic");
        }
        let app_future = Python::attach(move |py| {
            python_attach_wait_diagnostics
                .http_python_attach_wait_finished(python_attach_wait_started);
            let io = coverage_value!(
                HttpAsgiIoAllocate,
                Py::new(
                    py,
                    AsgiIo {
                        request_messages: Arc::new(Mutex::new(request_messages)),
                        _request_sender: request_sender,
                        connection_closed: context.connection_closed,
                        request_cancellation,
                        request_disconnected: Arc::new(AtomicBool::new(false)),
                        preserve_application_on_disconnect: app_preserve_application_on_disconnect,
                        response_start_attempted: app_response_start_attempted,
                        response_started: app_response_started,
                        start: start_tx,
                        body: body_tx,
                        diagnostics: diagnostics.clone(),
                        #[cfg(coverage)]
                        receive_calls: AtomicUsize::new(0),
                    },
                )
            )?;
            coverage_receive_borrow_conflict!(io, py);
            let scope = build_scope(
                py,
                &parts,
                context.peer_addr,
                context.server.server_addr,
                context.transport_scheme,
                &context.server.root_path,
                context.server.state.as_ref(),
            )?;
            let awaitable = coverage_value!(
                HttpAppInvokeCall,
                context
                    .server
                    .invoke
                    .bind(py)
                    .call1((context.server.app.bind(py), scope, io))
            )?;
            python_task_future(
                py,
                &context.server.locals,
                awaitable,
                diagnostics.clone(),
                cancellation_tracker,
                #[cfg(coverage)]
                true,
            )
        })?;
        run_python_application(app_future, force_application_shutdown).await
    };
    let mut app_task = AbortOnDrop::new(app_task_tracker.spawn(app_future));
    if http_version == Version::HTTP_2 {
        // Hyper drops a pending service future when its peer resets the
        // stream. Keep the tracked ASGI task alive long enough for the
        // request-body pump to deliver http.disconnect on that stream.
        app_task.leave_running();
    } else if http_version == Version::HTTP_3 {
        // HTTP/3 can stop only the response direction while ASGI is waiting
        // for another receive event. Keep that task alive for the disconnect
        // message; requests that are not receiving retain cancellation-on-drop.
        app_task.leave_running_if(preserve_application_on_disconnect);
    }

    #[cfg(coverage)]
    let app_task_wins_start_select =
        coverage_fault_is_armed(CoverageFaultPoint::HttpResponseTaskWinsStartSelect);
    #[cfg(not(coverage))]
    let app_task_wins_start_select = false;

    let response_without_start = |result| -> Result<Response<ResponseBody>, BoxError> {
        observe_app_before_response_start(result)?;
        if response_started.load(Ordering::Acquire)
            || response_start_attempted.load(Ordering::Acquire)
        {
            return Err(Box::new(InvalidAsgiResponseStart));
        }
        let error_body = if matches!(http_version, Version::HTTP_2 | Version::HTTP_3) {
            Bytes::new()
        } else {
            Bytes::from_static(b"Internal Server Error")
        };
        Ok(response(
            StatusCode::INTERNAL_SERVER_ERROR,
            full_body(error_body),
            HeaderMap::new(),
        ))
    };
    let (start, application) = tokio::select! {
        biased;
        start = start_rx.recv(), if !app_task_wins_start_select => {
            let Some(start) = start else {
                return response_without_start(app_task.as_mut().await);
            };
            (start, ResponseApplication::Running(app_task.into_handle()))
        },
        result = app_task.as_mut() => {
            // A coroutine may queue response.start and finish in the same
            // poll. The queued start remains authoritative when completion
            // wins this select, including an exception after response.start.
            let Ok(start) = start_rx.try_recv() else {
                return response_without_start(result);
            };
            (start, ResponseApplication::Completed(result))
        }
    };
    response_timing_diagnostics.http_response_start_latency_finished(response_latency_started);
    let defer_completed_app_result_once = matches!(application, ResponseApplication::Completed(_));

    let body = AsgiBody {
        receiver: body_rx,
        application: Some(application),
        app_task_tracker,
        defer_completed_app_result_once,
        incomplete_body_result_deferred: false,
        #[cfg(feature = "runtime-diagnostics")]
        response_timing_diagnostics,
        #[cfg(feature = "runtime-diagnostics")]
        response_latency_started,
        #[cfg(coverage)]
        body_consumer_pause: None,
        #[cfg(coverage)]
        body_consumer_pause_started: false,
        #[cfg(coverage)]
        receiver_pending_pause: Box::pin(tokio::time::sleep(std::time::Duration::ZERO)),
        #[cfg(coverage)]
        receiver_pending_pause_active: false,
    }
    .boxed_unsync();
    Ok(response(start.status, body, start.headers))
}

fn is_websocket_upgrade(request: &Request<Incoming>) -> bool {
    let upgrade = request
        .headers()
        .get(http::header::UPGRADE)
        .is_some_and(|value| value.as_bytes().eq_ignore_ascii_case(b"websocket"));
    let connection = request
        .headers()
        .get_all(http::header::CONNECTION)
        .iter()
        .any(|value| {
            value
                .as_bytes()
                .split(|byte| *byte == b',')
                .any(|token| trim_ascii(token).eq_ignore_ascii_case(b"upgrade"))
        });
    request.version() == Version::HTTP_11 && upgrade && connection
}

fn has_empty_websocket_subprotocol(headers: &HeaderMap) -> bool {
    headers
        .get_all(http::header::SEC_WEBSOCKET_PROTOCOL)
        .iter()
        .flat_map(|value| value.as_bytes().split(|byte| *byte == b','))
        .any(|protocol| trim_ascii(protocol).is_empty())
}

fn trim_ascii(mut value: &[u8]) -> &[u8] {
    while value.first().is_some_and(u8::is_ascii_whitespace) {
        value = &value[1..];
    }
    while value.last().is_some_and(u8::is_ascii_whitespace) {
        value = &value[..value.len() - 1];
    }
    value
}

async fn handle_websocket_request(
    request: Request<Incoming>,
    context: ConnectionContext,
) -> Response<ResponseBody> {
    match handle_websocket_request_inner(request, context).await {
        Ok(response) => response,
        Err(error) => match error.downcast::<WebSocketHandshakeError>() {
            Ok(handshake_error) => response(
                StatusCode::BAD_REQUEST,
                full_body(Bytes::from(handshake_error.to_string())),
                [(
                    http::header::CONTENT_TYPE,
                    HeaderValue::from_static("text/plain; charset=utf-8"),
                )]
                .into_iter()
                .collect(),
            ),
            Err(error) => {
                log_error(format_args!(
                    "uvicorn-rs: WebSocket request failed: {error}"
                ));
                response(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    full_body(Bytes::from_static(b"Internal Server Error")),
                    HeaderMap::new(),
                )
            }
        },
    }
}

async fn handle_websocket_request_inner(
    mut request: Request<Incoming>,
    context: ConnectionContext,
) -> Result<Response<ResponseBody>, BoxError> {
    if has_empty_websocket_subprotocol(request.headers()) {
        return Err(Box::new(WebSocketHandshakeError {
            response_body:
                "Failed to open a WebSocket connection: invalid Sec-WebSocket-Protocol header.\n"
                    .to_owned(),
        }));
    }
    let request_key = request
        .headers()
        .get(http::header::SEC_WEBSOCKET_KEY)
        .ok_or_else(|| {
            Box::new(WebSocketHandshakeError {
                response_body:
                    "Failed to open a WebSocket connection: missing Sec-WebSocket-Key header.\n"
                        .to_owned(),
            }) as BoxError
        })?
        .as_bytes();
    if let Some(reason) = websocket_key_error(request_key) {
        let key = String::from_utf8_lossy(request_key);
        let response_body = match reason {
            _ if key.is_empty() => {
                "Failed to open a WebSocket connection: empty Sec-WebSocket-Key header.\n"
                    .to_owned()
            }
            Some(reason) => format!(
                "Failed to open a WebSocket connection: invalid Sec-WebSocket-Key header: {key}; {reason}.\n"
            ),
            None => format!(
                "Failed to open a WebSocket connection: invalid Sec-WebSocket-Key header: {key}.\n"
            ),
        };
        return Err(Box::new(WebSocketHandshakeError { response_body }));
    }
    let request_version = request
        .headers()
        .get(http::header::SEC_WEBSOCKET_VERSION)
        .ok_or_else(|| {
            Box::new(WebSocketHandshakeError {
                response_body:
                    "Failed to open a WebSocket connection: missing Sec-WebSocket-Version header.\n"
                        .to_owned(),
            }) as BoxError
        })?;
    if request_version.as_bytes() != b"13" {
        let version = String::from_utf8_lossy(request_version.as_bytes());
        let response_body = if version.is_empty() {
            "Failed to open a WebSocket connection: empty Sec-WebSocket-Version header.\n"
                .to_owned()
        } else {
            format!(
                "Failed to open a WebSocket connection: invalid Sec-WebSocket-Version header: {version}.\n"
            )
        };
        return Err(Box::new(WebSocketHandshakeError { response_body }));
    }
    let request_key = request_key.to_vec();
    let on_upgrade = hyper::upgrade::on(&mut request);
    let parts = request.into_parts().0;
    let (incoming_tx, incoming_rx) = mpsc::channel(8);
    let (outgoing_tx, outgoing_rx) = mpsc::channel(8);
    let (handshake_tx, mut handshake_rx) = oneshot::channel();
    let state = Arc::new(AtomicU8::new(0));
    let app_context = context.clone();
    let app_task_tracker = app_context.server.pending_python_tasks.clone();
    let cancellation_tracker = app_task_tracker.clone();
    let force_application_shutdown = context.server.force_application_shutdown.clone();
    let diagnostics = context.server.diagnostics.clone();
    let websocket_io = WebSocketIo {
        incoming: Arc::new(Mutex::new(incoming_rx)),
        connect_delivered: AtomicBool::new(false),
        state: Arc::clone(&state),
        handshake: std::sync::Mutex::new(Some(handshake_tx)),
        outgoing: outgoing_tx,
        diagnostics: diagnostics.clone(),
    };
    #[cfg(coverage)]
    let inject_app_task_panic =
        coverage_fault_take(CoverageFaultPoint::WebSocketAppTaskPanicBeforeHandshake);
    #[cfg(not(coverage))]
    let inject_app_task_panic = false;
    let app_future = async move {
        #[cfg(coverage)]
        if inject_app_task_panic {
            coverage_panic("coverage-injected WebSocket application task panic");
        }
        let app_future = Python::attach(move |py| {
            let io = coverage_value!(WebSocketIoAllocate, Py::new(py, websocket_io))?;
            coverage_receive_borrow_conflict!(io, py);
            let scope = build_websocket_scope(
                py,
                &parts,
                app_context.peer_addr,
                app_context.server.server_addr,
                app_context.transport_scheme,
                &app_context.server.root_path,
                app_context.server.state.as_ref(),
            )?;
            let awaitable = coverage_value!(
                WebSocketAppInvokeCall,
                app_context.server.invoke.bind(py).call1((
                    app_context.server.app.bind(py),
                    scope,
                    io,
                ))
            )?;
            python_task_future(
                py,
                &app_context.server.locals,
                awaitable,
                diagnostics.clone(),
                cancellation_tracker,
                #[cfg(coverage)]
                true,
            )
        })?;
        run_python_application(app_future, force_application_shutdown).await
    };
    let mut app_task = AbortOnDrop::new(app_task_tracker.spawn(app_future));

    let mut handshake_connection_closed = context.connection_closed.clone();
    let handshake = tokio::select! {
        biased;
        _ = handshake_connection_closed.wait_for_peer_read_failure() => {
            app_task.as_mut().abort();
            let _ = app_task.as_mut().await;
            return Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR,
                full_body(Bytes::new()),
                HeaderMap::new(),
            ));
        }
        handshake = &mut handshake_rx, if !inject_app_task_panic => handshake.map_err(|_| {
            std::io::Error::other("ASGI app returned before accepting or closing the WebSocket")
        })?,
        result = app_task.as_mut() => {
            app_task.into_handle();
            observe_app_before_response_start(result)?;
            return Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR,
                full_body(Bytes::from_static(b"Internal Server Error")),
                HeaderMap::new(),
            ));
        }
    };

    let WebSocketHandshake::Accept {
        subprotocol,
        headers,
    } = handshake
    else {
        return Ok(response(
            StatusCode::FORBIDDEN,
            full_body(Bytes::new()),
            HeaderMap::new(),
        ));
    };

    let accept_key = derive_accept_key(&request_key);
    #[cfg(coverage)]
    let accept_key = if coverage_fault_take(CoverageFaultPoint::WebSocketAcceptKeyHeaderValueError)
    {
        "\n".to_string()
    } else {
        accept_key
    };
    let mut handshake_response = Response::new(full_body(Bytes::new()));
    *handshake_response.status_mut() = StatusCode::SWITCHING_PROTOCOLS;
    handshake_response.headers_mut().insert(
        http::header::CONNECTION,
        HeaderValue::from_static("upgrade"),
    );
    handshake_response
        .headers_mut()
        .insert(http::header::UPGRADE, HeaderValue::from_static("websocket"));
    handshake_response.headers_mut().insert(
        http::header::SEC_WEBSOCKET_ACCEPT,
        HeaderValue::from_str(&accept_key)?,
    );
    if let Some(subprotocol) = subprotocol {
        handshake_response.headers_mut().insert(
            http::header::SEC_WEBSOCKET_PROTOCOL,
            HeaderValue::from_str(&subprotocol)?,
        );
    }
    for (name, value) in headers {
        let name = HeaderName::from_bytes(&name)?;
        if name == http::header::CONNECTION
            || name == http::header::UPGRADE
            || name == http::header::SEC_WEBSOCKET_ACCEPT
            || name == http::header::SEC_WEBSOCKET_PROTOCOL
        {
            return Err(std::io::Error::other(
                "ASGI websocket.accept headers cannot override handshake headers",
            )
            .into());
        }
        handshake_response
            .headers_mut()
            .try_append(name, HeaderValue::from_bytes(&value)?)?;
    }

    #[cfg(feature = "native-tcp")]
    let native_upgrade = context.native_upgrade.ok_or_else(|| {
        std::io::Error::other("native TCP transport omitted the HTTP/1 WebSocket upgrade session")
    })?;
    #[cfg(not(feature = "native-tcp"))]
    let app_task = app_task.into_handle();
    let server = Arc::clone(&context.server);
    let session_cancellation = server.cancellation.clone();
    let connection_closed = context.connection_closed;
    #[cfg(feature = "native-tcp")]
    {
        let upgrade_shutdown = native_upgrade.clone();
        #[cfg(coverage)]
        let inject_shutdown_panic =
            coverage_fault_take(CoverageFaultPoint::ServerWebSocketTaskShutdownPanic);
        #[cfg(coverage)]
        let inject_shutdown_hang =
            coverage_fault_take(CoverageFaultPoint::ServerWebSocketTaskShutdownHang);
        let session_cancellation = session_cancellation.clone();
        let session_handler = move |upgraded| async move {
            // Keep cancellation ownership until registration has succeeded.
            // If the connection is already closed, dropping the rejected
            // session handler must cancel the Python ASGI task instead of
            // detaching its JoinHandle.
            let app_task = app_task.into_handle();
            #[cfg(coverage)]
            if inject_shutdown_panic {
                upgrade_shutdown.wait_for_shutdown().await;
                app_task.abort();
                let _ = app_task.await;
                coverage_panic("coverage-injected WebSocket session task panic during shutdown");
            }
            #[cfg(coverage)]
            if inject_shutdown_hang {
                upgrade_shutdown.wait_for_shutdown().await;
                app_task.abort();
                let _ = app_task.await;
                return std::future::pending::<Result<(), std::io::Error>>().await;
            }
            let socket = WebSocketSession::from_accepted_upgrade_with_max_message_size(
                upgraded,
                upgrade_shutdown,
                server.ws_max_size,
            )
            .await;
            if let Err(error) = drive_websocket(
                socket,
                incoming_tx,
                outgoing_rx,
                app_task,
                WebSocketDriverContext {
                    state,
                    connection_closed,
                    cancellation: session_cancellation,
                    keepalive: server.websocket_keepalive,
                },
            )
            .await
            {
                log_error(format_args!(
                    "uvicorn-rs: WebSocket session failed: {error}"
                ));
            }
            Ok::<(), std::io::Error>(())
        };
        #[cfg(coverage)]
        let registration =
            if coverage_fault_take(CoverageFaultPoint::WebSocketNativeUpgradeRegisterClosed) {
                Err(uvicorn_rs::ConnectionUpgradeClosed)
            } else {
                native_upgrade.register(on_upgrade, session_handler)
            };
        #[cfg(not(coverage))]
        let registration = native_upgrade.register(on_upgrade, session_handler);
        registration.map_err(|error| Box::new(error) as BoxError)?;
        Ok(handshake_response)
    }
    #[cfg(not(feature = "native-tcp"))]
    {
        let upgrade_cancellation = session_cancellation.clone();
        let websocket_tasks = Arc::clone(&server.websocket_tasks);
        websocket_tasks.lock().await.spawn(async move {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerWebSocketTaskShutdownPanic) {
            upgrade_cancellation.cancelled().await;
            app_task.abort();
            let _ = app_task.await;
            coverage_panic("coverage-injected WebSocket session task panic during shutdown");
        }
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::ServerWebSocketTaskShutdownHang) {
            upgrade_cancellation.cancelled().await;
            std::future::pending::<()>().await;
        }
        tokio::select! {
            biased;
            _ = upgrade_cancellation.cancelled() => {
                state.store(3, Ordering::Release);
                app_task.abort();
                let _ = app_task.await;
            }
            result = on_upgrade => match result {
                Ok(upgraded) => {
                    let mut websocket_config = WebSocketConfig::default();
                    websocket_config.max_message_size = Some(server.ws_max_size);
                    websocket_config.max_frame_size = Some(server.ws_max_size);
                    let socket = WebSocketStream::from_raw_socket(
                        TokioIo::new(upgraded),
                        Role::Server,
                        Some(websocket_config),
                    ).await;
                    if let Err(error) = drive_websocket(
                        socket,
                        incoming_tx,
                        outgoing_rx,
                        app_task,
                        WebSocketDriverContext {
                            state,
                            connection_closed,
                            cancellation: session_cancellation,
                            keepalive: server.websocket_keepalive,
                        },
                    ).await {
                        log_error(format_args!("uvicorn-rs: WebSocket session failed: {error}"));
                    }
                }
                Err(error) => {
                    state.store(3, Ordering::Release);
                    app_task.abort();
                    let _ = app_task.await;
                    log_error(format_args!("uvicorn-rs: WebSocket upgrade failed: {error}"));
                }
            }
        }
        });
    }
    #[cfg(not(feature = "native-tcp"))]
    Ok(handshake_response)
}

fn websocket_key_error(value: &[u8]) -> Option<Option<String>> {
    let is_base64 = |byte: &u8| byte.is_ascii_alphanumeric() || matches!(*byte, b'+' | b'/' | b'=');
    if !value.iter().all(is_base64) {
        return Some(Some("Only base64 data is allowed".to_owned()));
    }
    let padding = value.iter().rev().take_while(|byte| **byte == b'=').count();
    let data_length = value.len().saturating_sub(padding);
    if value[..data_length].contains(&b'=') {
        return Some(Some("Discontinuous padding not allowed".to_owned()));
    }
    if data_length % 4 == 1 {
        return Some(Some(format!(
            "Invalid base64-encoded string: number of data characters ({data_length}) cannot be 1 more than a multiple of 4"
        )));
    }
    let valid_padding = match padding {
        0 => data_length % 4 == 0,
        1 => data_length % 4 == 3,
        2 => data_length % 4 == 2,
        _ => false,
    };
    if !valid_padding {
        return Some(Some(if padding > 0 {
            "Excess padding not allowed".to_owned()
        } else {
            "Incorrect padding".to_owned()
        }));
    }
    if value.len() / 4 * 3 - padding != 16 {
        return Some(None);
    }
    None
}

trait WebSocketTransport {
    async fn send_message(&mut self, message: Message) -> Result<(), BoxError>;

    async fn receive_message(&mut self) -> Result<Option<Message>, BoxError>;
}

impl WebSocketTransport for WebSocketSession {
    async fn send_message(&mut self, message: Message) -> Result<(), BoxError> {
        #[cfg(coverage)]
        let result = if coverage_fault_take(CoverageFaultPoint::WebSocketDriverSendError) {
            Err(uvicorn_rs::WebSocketError::coverage_send_failure())
        } else {
            self.send(message).await
        };
        #[cfg(not(coverage))]
        let result = self.send(message).await;
        result.map_err(|error| Box::new(error) as BoxError)
    }

    async fn receive_message(&mut self) -> Result<Option<Message>, BoxError> {
        self.receive()
            .await
            .map_err(|error| Box::new(error) as BoxError)
    }
}

#[cfg(not(feature = "native-tcp"))]
impl<I> WebSocketTransport for WebSocketStream<I>
where
    I: AsyncRead + AsyncWrite + Unpin,
{
    async fn send_message(&mut self, message: Message) -> Result<(), BoxError> {
        self.send(message)
            .await
            .map_err(|error| Box::new(error) as BoxError)
    }

    async fn receive_message(&mut self) -> Result<Option<Message>, BoxError> {
        match self.next().await.transpose() {
            Ok(message) => Ok(message),
            Err(error @ TungsteniteError::Capacity(_)) => {
                let close = Message::Close(Some(CloseFrame {
                    code: CloseCode::Size,
                    reason: "message too big".into(),
                }));
                let _ = self.send(close).await;
                Err(Box::new(error))
            }
            Err(error) => Err(Box::new(error)),
        }
    }
}

async fn send_websocket_message<S>(socket: &mut S, message: Message) -> Result<(), BoxError>
where
    S: WebSocketTransport,
{
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::WebSocketDriverDrainSendError) {
        return Err(Box::new(std::io::Error::other(
            "coverage-injected WebSocket send failure",
        )));
    }
    socket.send_message(message).await
}

async fn drive_websocket<S>(
    mut socket: S,
    incoming: mpsc::Sender<WebSocketIncoming>,
    mut outgoing: mpsc::Receiver<WebSocketOutgoing>,
    mut app_task: tokio::task::JoinHandle<PyResult<Py<PyAny>>>,
    context: WebSocketDriverContext,
) -> Result<(), BoxError>
where
    S: WebSocketTransport,
{
    let WebSocketDriverContext {
        state,
        mut connection_closed,
        cancellation,
        keepalive,
    } = context;
    let mut app_task_completed = false;
    let mut driver_error = None;
    let mut ping_sequence = 0_u32;
    let mut pending_ping: Option<(Vec<u8>, tokio::time::Instant)> = None;
    let mut last_ping_rtt = std::time::Duration::ZERO;
    let mut next_ping = keepalive
        .interval
        .and_then(|interval| tokio::time::Instant::now().checked_add(interval));
    #[cfg(coverage)]
    if coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverAppTaskAborted) {
        app_task.abort();
    }
    'driver: loop {
        #[cfg(coverage)]
        let hold_outgoing_for_drain =
            coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverDrainSendError);
        #[cfg(not(coverage))]
        let hold_outgoing_for_drain = false;
        let keepalive_deadline = pending_ping
            .as_ref()
            .and_then(|(_, sent_at)| {
                keepalive
                    .timeout
                    .and_then(|timeout| sent_at.checked_add(timeout))
            })
            .or(next_ping);
        tokio::select! {
            biased;
            _ = async {
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverConnectionClosed) {
                    return;
                }
                wait_for_connection_close(&mut connection_closed, false).await;
            } => {
                state.store(2, Ordering::Release);
                let _ = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    incoming.send(WebSocketIncoming::Disconnect {
                        code: 1006,
                        reason: String::new(),
                    }),
                )
                .await;
                state.store(3, Ordering::Release);
                app_task_completed = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await.is_ok();
                break;
            }
            _ = cancellation.cancelled() => {
                let _ = tokio::time::timeout(
                    std::time::Duration::from_millis(100),
                    socket.send_message(Message::Close(Some(CloseFrame {
                        code: CloseCode::from(1012),
                        reason: "".into(),
                    }))),
                ).await;
                state.store(2, Ordering::Release);
                let _ = incoming.try_send(WebSocketIncoming::Disconnect {
                    code: 1012,
                    reason: String::new(),
                });
                state.store(3, Ordering::Release);
                app_task_completed = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await.is_ok();
                break;
            }
            _ = async {
                if let Some(deadline) = keepalive_deadline {
                    tokio::time::sleep_until(deadline).await;
                } else {
                    std::future::pending::<()>().await;
                }
            } => {
                let now = tokio::time::Instant::now();
                let ping_timed_out = pending_ping
                    .as_ref()
                    .and_then(|(_, sent_at)| {
                        keepalive
                            .timeout
                            .and_then(|timeout| sent_at.checked_add(timeout))
                    })
                    .is_some_and(|deadline| deadline <= now);
                if ping_timed_out {
                    state.store(2, Ordering::Release);
                    match tokio::time::timeout(
                        std::time::Duration::from_millis(100),
                        socket.send_message(Message::Close(Some(CloseFrame {
                            code: CloseCode::from(1011),
                            reason: "keepalive ping timeout".into(),
                        }))),
                    )
                    .await
                    {
                        Ok(Ok(())) | Err(_) => {}
                        Ok(Err(error)) => driver_error = Some(error),
                    }
                    let _ = tokio::time::timeout(
                        std::time::Duration::from_secs(1),
                        incoming.send(WebSocketIncoming::Disconnect {
                            code: 1005,
                            reason: String::new(),
                        }),
                    )
                    .await;
                    state.store(3, Ordering::Release);
                    app_task_completed = tokio::time::timeout(
                        std::time::Duration::from_secs(1),
                        &mut app_task,
                    )
                    .await
                    .is_ok();
                    break;
                }

                if next_ping.is_some_and(|deadline| deadline <= now) {
                    next_ping = None;
                    let payload = ping_sequence.to_be_bytes().to_vec();
                    ping_sequence = ping_sequence.wrapping_add(1);
                    if let Err(error) = socket
                        .send_message(Message::Ping(payload.clone().into()))
                        .await
                    {
                        driver_error = Some(error);
                        break 'driver;
                    }
                    pending_ping = Some((payload, now));
                    if keepalive.timeout.is_none() {
                        next_ping = keepalive.interval.and_then(|interval| {
                            now.checked_add(interval.saturating_sub(last_ping_rtt))
                        });
                    }
                }
            }
            result = &mut app_task => {
                app_task_completed = true;
                match result {
                    Ok(Ok(_)) => {}
                    Ok(Err(error)) => {
                        Python::attach(|py| error.print(py));
                    }
                    Err(error) => log_error(format_args!("uvicorn-rs: WebSocket app task failed: {error}")),
                }
                // An ASGI app may send its final frame and return without
                // waiting for another receive. Preserve every accepted
                // outbound event queued before its task completed.
                while let Ok(message) = outgoing.try_recv() {
                    if let Err(error) = send_websocket_message(
                        &mut socket,
                        into_websocket_message(message),
                    )
                    .await
                    {
                        driver_error = Some(error);
                        break 'driver;
                    }
                }
                break;
            }
            message = async {
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverPeerEof) {
                    return Ok(None);
                }
                socket.receive_message().await
            } => {
                match message {
                    Ok(Some(Message::Text(text))) => {
                        #[cfg(coverage)]
                        let send_failed = coverage_fault_is_armed(
                            CoverageFaultPoint::WebSocketDriverIncomingTextReceiverClosed,
                        ) || incoming.send(WebSocketIncoming::Text(text.to_string())).await.is_err();
                        #[cfg(not(coverage))]
                        let send_failed = incoming.send(WebSocketIncoming::Text(text.to_string())).await.is_err();
                        if send_failed {
                            break;
                        }
                    }
                    Ok(Some(Message::Binary(data))) => {
                        #[cfg(coverage)]
                        let send_failed = coverage_fault_is_armed(
                            CoverageFaultPoint::WebSocketDriverIncomingBinaryReceiverClosed,
                        ) || incoming.send(WebSocketIncoming::Bytes(data)).await.is_err();
                        #[cfg(not(coverage))]
                        let send_failed = incoming.send(WebSocketIncoming::Bytes(data)).await.is_err();
                        if send_failed {
                            break;
                        }
                    }
                    Ok(Some(Message::Pong(payload))) => {
                        if let Some((expected, sent_at)) = pending_ping.as_ref() {
                            if payload.as_ref() == expected.as_slice() {
                                last_ping_rtt = sent_at.elapsed();
                                pending_ping = None;
                                if keepalive.timeout.is_some() {
                                    next_ping = keepalive.interval.and_then(|interval| {
                                        tokio::time::Instant::now()
                                            .checked_add(interval.saturating_sub(last_ping_rtt))
                                    });
                                }
                            }
                        }
                    }
                    Ok(Some(Message::Close(frame))) => {
                        let (code, reason) = frame
                            .map(|frame| (u16::from(frame.code), frame.reason.to_string()))
                            .unwrap_or((1005, String::new()));
                        state.store(2, Ordering::Release);
                        let _ = incoming.send(WebSocketIncoming::Disconnect { code, reason }).await;
                        state.store(3, Ordering::Release);
                        app_task_completed = tokio::time::timeout(
                            std::time::Duration::from_secs(1),
                            &mut app_task,
                        )
                        .await
                        .is_ok();
                        break;
                    }
                    Ok(Some(Message::Ping(_) | Message::Frame(_))) => {}
                    Err(error) => {
                        let _ = incoming.send(WebSocketIncoming::Disconnect {
                            code: 1002,
                            reason: error.to_string(),
                        }).await;
                        app_task_completed = tokio::time::timeout(
                            std::time::Duration::from_secs(1),
                            &mut app_task,
                        )
                        .await
                        .is_ok();
                        break;
                    }
                    Ok(None) => {
                        let _ = incoming.send(WebSocketIncoming::Disconnect {
                            code: 1006,
                            reason: String::new(),
                        }).await;
                        app_task_completed = tokio::time::timeout(
                            std::time::Duration::from_secs(1),
                            &mut app_task,
                        )
                        .await
                        .is_ok();
                        break;
                    }
                }
            }
            message = async {
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverOutgoingChannelClosed) {
                    return None;
                }
                outgoing.recv().await
            }, if !hold_outgoing_for_drain => {
                let Some(message) = message else {
                    break;
                };
                if matches!(&message, WebSocketOutgoing::Close { .. }) {
                    state.store(2, Ordering::Release);
                }
                if let Err(error) = send_websocket_message(
                    &mut socket,
                    into_websocket_message(message),
                )
                .await
                {
                    driver_error = Some(error);
                    break 'driver;
                }
            }
        }
    }
    state.store(3, Ordering::Release);
    if !app_task_completed {
        // Aborting a task that won the completion race is harmless. Await its
        // unobserved result once, including after transport failure.
        app_task.abort();
        let _ = app_task.await;
    }
    driver_error.map_or(Ok(()), Err)
}

fn build_websocket_scope<'py>(
    py: Python<'py>,
    request: &http::request::Parts,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    transport_scheme: &str,
    root_path: &str,
    state: Option<&Arc<Py<PyDict>>>,
) -> PyResult<Bound<'py, PyDict>> {
    let scope = PyDict::new(py);
    let asgi = PyDict::new(py);
    coverage_try!(
        WebSocketScopeAsgiVersionSetItem,
        asgi.set_item("version", "3.0")
    );
    coverage_try!(
        WebSocketScopeAsgiSpecVersionSetItem,
        asgi.set_item("spec_version", "2.5")
    );
    coverage_try!(
        WebSocketScopeTypeSetItem,
        scope.set_item("type", "websocket")
    );
    coverage_try!(WebSocketScopeAsgiSetItem, scope.set_item("asgi", asgi));
    set_scope_state(py, &scope, state)?;
    coverage_try!(
        WebSocketScopeHttpVersionSetItem,
        scope.set_item(
            "http_version",
            // WebSocket Upgrade is an HTTP/1.1 mechanism in this server.
            // HTTP/1.0 requests are routed as ordinary HTTP, and HTTP/2/3 use
            // extended CONNECT rather than the Upgrade path implemented here.
            "1.1",
        )
    );
    coverage_try!(
        WebSocketScopeSchemeSetItem,
        scope.set_item(
            "scheme",
            if transport_scheme == "https" {
                "wss"
            } else {
                "ws"
            }
        )
    );
    let decoded_path = percent_encoding::percent_decode_str(request.uri.path()).decode_utf8_lossy();
    if root_path.is_empty() {
        coverage_try!(
            WebSocketScopePathSetItem,
            scope.set_item("path", decoded_path.as_ref())
        );
        coverage_try!(
            WebSocketScopeRawPathSetItem,
            scope.set_item("raw_path", PyBytes::new(py, request.uri.path().as_bytes()))
        );
    } else {
        let mut path = String::with_capacity(root_path.len() + decoded_path.len());
        path.push_str(root_path);
        path.push_str(&decoded_path);
        coverage_try!(WebSocketScopePathSetItem, scope.set_item("path", path));
        let mut raw_path = Vec::with_capacity(root_path.len() + request.uri.path().len());
        raw_path.extend_from_slice(root_path.as_bytes());
        raw_path.extend_from_slice(request.uri.path().as_bytes());
        coverage_try!(
            WebSocketScopeRawPathSetItem,
            scope.set_item("raw_path", PyBytes::new(py, &raw_path))
        );
    }
    coverage_try!(
        WebSocketScopeQueryStringSetItem,
        scope.set_item(
            "query_string",
            PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes())
        )
    );
    coverage_try!(
        WebSocketScopeRootPathSetItem,
        scope.set_item("root_path", root_path)
    );
    coverage_try!(
        WebSocketScopeMethodSetItem,
        scope.set_item("method", request.method.as_str().to_ascii_uppercase())
    );
    let headers = PyList::empty(py);
    let mut subprotocols = Vec::new();
    for name in request.headers.keys() {
        for value in request.headers.get_all(name).iter() {
            coverage_try!(
                WebSocketScopeHeadersAppend,
                headers.append((
                    PyBytes::new(py, name.as_str().as_bytes()),
                    PyBytes::new(py, value.as_bytes()),
                ))
            );
            if name == http::header::SEC_WEBSOCKET_PROTOCOL {
                for protocol in value.as_bytes().split(|byte| *byte == b',') {
                    let protocol = String::from_utf8_lossy(trim_ascii(protocol)).into_owned();
                    subprotocols.push(protocol);
                }
            }
        }
    }
    coverage_try!(
        WebSocketScopeHeadersSetItem,
        scope.set_item("headers", headers)
    );
    coverage_try!(
        WebSocketScopeSubprotocolsSetItem,
        scope.set_item("subprotocols", subprotocols)
    );
    coverage_try!(
        WebSocketScopeClientSetItem,
        scope.set_item("client", (peer_addr.ip().to_string(), peer_addr.port()))
    );
    coverage_try!(
        WebSocketScopeServerSetItem,
        scope.set_item("server", (server_addr.ip().to_string(), server_addr.port()))
    );
    Ok(scope)
}

fn observe_app_after_response(result: Result<PyResult<Py<PyAny>>, tokio::task::JoinError>) {
    match result {
        Ok(Ok(_)) => {}
        Ok(Err(error)) => Python::attach(|py| error.print(py)),
        Err(error) => {
            log_error(format_args!(
                "uvicorn-rs: ASGI app task failed after the response body completed: {error}"
            ));
        }
    }
}

fn observe_app_before_response_start(
    result: Result<PyResult<Py<PyAny>>, tokio::task::JoinError>,
) -> Result<(), BoxError> {
    match result {
        Ok(Ok(_)) => log_error(format_args!(
            "uvicorn-rs: ASGI app completed without response.start"
        )),
        Ok(Err(error)) => Python::attach(|py| error.print(py)),
        Err(error) => return Err(Box::new(error)),
    }
    Ok(())
}

fn build_scope<'py>(
    py: Python<'py>,
    request: &http::request::Parts,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    scheme: &str,
    root_path: &str,
    state: Option<&Arc<Py<PyDict>>>,
) -> PyResult<Bound<'py, PyDict>> {
    let scope = PyDict::new(py);
    let asgi = PyDict::new(py);
    coverage_try!(HttpScopeAsgiVersionSetItem, asgi.set_item("version", "3.0"));
    coverage_try!(
        HttpScopeAsgiSpecVersionSetItem,
        asgi.set_item("spec_version", "2.5")
    );
    coverage_try!(HttpScopeTypeSetItem, scope.set_item("type", "http"));
    coverage_try!(HttpScopeAsgiSetItem, scope.set_item("asgi", asgi));
    set_scope_state(py, &scope, state)?;
    coverage_try!(
        HttpScopeHttpVersionSetItem,
        scope.set_item(
            "http_version",
            if request.version == Version::HTTP_10 {
                "1.0"
            } else if request.version == Version::HTTP_2 {
                "2"
            } else if request.version == Version::HTTP_3 {
                "3"
            } else {
                "1.1"
            },
        )
    );
    coverage_try!(
        HttpScopeMethodSetItem,
        scope.set_item("method", request.method.as_str().to_ascii_uppercase())
    );
    coverage_try!(HttpScopeSchemeSetItem, scope.set_item("scheme", scheme));

    let raw_path = request.uri.path().as_bytes();
    let decoded_path = percent_encoding::percent_decode_str(request.uri.path()).decode_utf8_lossy();
    if root_path.is_empty() {
        coverage_try!(
            HttpScopePathSetItem,
            scope.set_item("path", PyString::new(py, decoded_path.as_ref()))
        );
        coverage_try!(
            HttpScopeRawPathSetItem,
            scope.set_item("raw_path", PyBytes::new(py, raw_path))
        );
    } else {
        let mut path = String::with_capacity(root_path.len() + decoded_path.len());
        path.push_str(root_path);
        path.push_str(&decoded_path);
        coverage_try!(HttpScopePathSetItem, scope.set_item("path", path));
        let mut full_raw_path = Vec::with_capacity(root_path.len() + raw_path.len());
        full_raw_path.extend_from_slice(root_path.as_bytes());
        full_raw_path.extend_from_slice(raw_path);
        coverage_try!(
            HttpScopeRawPathSetItem,
            scope.set_item("raw_path", PyBytes::new(py, &full_raw_path))
        );
    }
    coverage_try!(
        HttpScopeQueryStringSetItem,
        scope.set_item(
            "query_string",
            PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes())
        )
    );
    coverage_try!(
        HttpScopeRootPathSetItem,
        scope.set_item("root_path", root_path)
    );

    let headers = PyList::empty(py);
    let normalize_authority = matches!(request.version, Version::HTTP_2 | Version::HTTP_3);
    if normalize_authority {
        // HTTP/2 and HTTP/3 carry the host in `:authority`, not in the regular
        // header block. Hypercorn exposes that pseudo-header as a leading ASGI
        // `host` header, preferring authority over any ordinary Host value.
        // HTTP/1 must keep the original header block unchanged.
        let authority = request
            .uri
            .authority()
            .map(|authority| authority.as_str().as_bytes())
            .or_else(|| {
                request
                    .headers
                    .get_all(http::header::HOST)
                    .iter()
                    .next_back()
                    .map(http::HeaderValue::as_bytes)
            })
            .unwrap_or_default();
        coverage_try!(
            HttpScopeHeadersAppend,
            headers.append((PyBytes::new(py, b"host"), PyBytes::new(py, authority)))
        );
    }
    for name in request.headers.keys() {
        if normalize_authority && name == http::header::HOST {
            continue;
        }
        for value in request.headers.get_all(name).iter() {
            coverage_try!(
                HttpScopeHeadersAppend,
                headers.append((
                    PyBytes::new(py, name.as_str().as_bytes()),
                    PyBytes::new(py, value.as_bytes()),
                ))
            );
        }
    }
    coverage_try!(HttpScopeHeadersSetItem, scope.set_item("headers", headers));
    coverage_try!(
        HttpScopeClientSetItem,
        scope.set_item("client", (peer_addr.ip().to_string(), peer_addr.port()))
    );
    coverage_try!(
        HttpScopeServerSetItem,
        scope.set_item("server", (server_addr.ip().to_string(), server_addr.port()))
    );
    Ok(scope)
}

fn set_scope_state(
    py: Python<'_>,
    scope: &Bound<'_, PyDict>,
    state: Option<&Arc<Py<PyDict>>>,
) -> PyResult<()> {
    if let Some(state) = state {
        // Python's shallow copy preserves cached key hashes and shared values;
        // re-inserting keys can invoke user __hash__ and mutate the source.
        let request_state = coverage_value!(HttpScopeStateCopy, state.bind(py).copy())?;
        coverage_try!(
            HttpScopeStateSetItem,
            scope.set_item("state", request_state)
        );
    }
    Ok(())
}

fn full_body(body: Bytes) -> ResponseBody {
    Full::new(body)
        .map_err(|never| -> BoxError { match never {} })
        .boxed_unsync()
}

fn apply_default_response_headers(
    server: &ServerContext,
    response: Response<ResponseBody>,
) -> Result<Response<ResponseBody>, std::io::Error> {
    let (mut parts, body) = response.into_parts();
    let mut headers = HeaderMap::new();
    if server.date_header {
        let date = httpdate::fmt_http_date(std::time::SystemTime::now());
        let value = HeaderValue::from_bytes(date.as_bytes()).map_err(std::io::Error::other)?;
        headers.append(DATE, value);
    }
    for (name, value) in &server.default_headers {
        headers.append(name.clone(), value.clone());
    }
    for (name, value) in &parts.headers {
        headers.append(name.clone(), value.clone());
    }
    parts.headers = headers;
    Ok(Response::from_parts(parts, body))
}

fn response(status: StatusCode, body: ResponseBody, headers: HeaderMap) -> Response<ResponseBody> {
    let mut response = Response::new(body);
    *response.headers_mut() = headers;
    *response.status_mut() = status;
    response
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    const TOKIO_WORKER_THREADS: usize = 1;
    // Both success and startup resource failure are process-wide decisions.
    // Retain the runtime without leaking a fresh allocation on reinitialization;
    // a failed build is returned again rather than silently retrying on import.
    static NATIVE_RUNTIME: OnceLock<Result<tokio::runtime::Runtime, std::io::Error>> =
        OnceLock::new();
    let runtime = NATIVE_RUNTIME.get_or_init(|| {
        let mut runtime_builder = tokio::runtime::Builder::new_multi_thread();
        runtime_builder
            .worker_threads(TOKIO_WORKER_THREADS)
            .enable_all();
        #[cfg(coverage)]
        {
            if coverage_fault_take(CoverageFaultPoint::NativeRuntimeBuildError) {
                Err(std::io::Error::other(
                    "coverage-injected native runtime build error",
                ))
            } else {
                runtime_builder.build()
            }
        }
        #[cfg(not(coverage))]
        {
            runtime_builder.build()
        }
    });
    let runtime = runtime.as_ref().map_err(|error| {
        PyOSError::new_err(format!("could not initialize Tokio runtime: {error}"))
    })?;
    // Err(()) means another valid runtime was registered first. Preserve that
    // shared runtime; neither outcome calls the dependency's lazy builder.
    let _ = pyo3_async_runtimes::tokio::init_with_runtime(runtime);
    coverage_try!(NativeModuleAddAsgiIo, module.add_class::<AsgiIo>());
    coverage_try!(
        NativeModuleAddWebSocketIo,
        module.add_class::<WebSocketIo>()
    );
    coverage_try!(NativeModuleAddLifespanIo, module.add_class::<LifespanIo>());
    coverage_try!(
        NativeModuleAddServerControl,
        module.add_class::<ServerControl>()
    );
    let serve_function = coverage_value!(
        NativeModuleWrapServeFunction,
        wrap_pyfunction!(serve, module)
    )?;
    coverage_try!(
        NativeModuleAddServeFunction,
        module.add_function(serve_function)
    );
    Ok(())
}
