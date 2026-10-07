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
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};
use std::sync::{Arc, OnceLock};
use std::task::{Context, Poll};

use bytes::{Buf, Bytes};
use futures_util::task::AtomicWaker;
use futures_util::{SinkExt, StreamExt};
use http::header::{HeaderName, HeaderValue};
use http::{HeaderMap, Request, Response, StatusCode, Version};
use http_body::{Body, Frame, SizeHint};
use http_body_util::combinators::UnsyncBoxBody;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::service::service_fn;
use hyper_util::rt::{TokioExecutor, TokioIo};
use hyper_util::server::conn::auto;
#[cfg(coverage)]
use pyo3::exceptions::PyMemoryError;
use pyo3::exceptions::{PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString};
use pyo3_async_runtimes::TaskLocals;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::mpsc::{
    self,
    error::{TryRecvError, TrySendError},
};
use tokio::sync::{oneshot, watch, Mutex};
use tokio_rustls::{rustls, TlsAcceptor};
use tokio_tungstenite::tungstenite::{
    handshake::derive_accept_key,
    protocol::{frame::coding::CloseCode, CloseFrame, Message, Role},
};
use tokio_tungstenite::WebSocketStream;
use tokio_util::sync::CancellationToken;
use tokio_util::task::TaskTracker;

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
    HttpBodyPumpFirstPollPause,
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
    ServerConnectionTaskServiceError,
    ServerConnectionTaskJoinError,
    ServerConnectionTaskServiceAwaitError,
    ServerConnectionTaskJoinAwaitError,
    ServerConnectionTaskServiceSelectResult,
    ServerConnectionTaskJoinSelectResult,
    ServerConnectionTaskServiceErrorDuringShutdown,
    ServerConnectionTaskJoinErrorDuringShutdown,
    ServerConnectionIoPollWriteError,
    HttpAsgiIoAllocate,
    HttpAppInvokeCall,
    HttpResponseTaskWinsStartSelect,
    HttpResponseStartChannelClosed,
    HttpResponseBodyChannelClosed,
    HttpResponseBodyConsumerPause,
    HttpResponseBodyPollPendingPause,
    HttpAppTaskPanicBeforeResponseStart,
    Http3ConnectionTaskPanic,
    Http3EndpointAcceptClosed,
    Http3ConnectionTaskPanicDuringShutdown,
    Http3ConnectionTaskShutdownHang,
    Http3ConnectionCreateError,
    Http3ConnectionAcceptError,
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
    Http3BodyPumpEmptyData,
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
            Self::HttpBodyPumpFirstPollPause => "http.body-pump.first-poll-pause",
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
            Self::ServerConnectionTaskJoinError => "server.connection-task.join-error",
            Self::ServerConnectionTaskServiceAwaitError => {
                "server.connection-task.service-await-error"
            }
            Self::ServerConnectionTaskJoinAwaitError => "server.connection-task.join-await-error",
            Self::ServerConnectionTaskServiceSelectResult => {
                "server.connection-task.service-select-result"
            }
            Self::ServerConnectionTaskJoinSelectResult => {
                "server.connection-task.join-select-result"
            }
            Self::ServerConnectionTaskServiceErrorDuringShutdown => {
                "server.connection-task.service-error-during-shutdown"
            }
            Self::ServerConnectionTaskJoinErrorDuringShutdown => {
                "server.connection-task.join-error-during-shutdown"
            }
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
            Self::Http3ConnectionTaskPanic => "http3.connection-task.panic",
            Self::Http3EndpointAcceptClosed => "http3.endpoint.accept-closed",
            Self::Http3ConnectionTaskPanicDuringShutdown => {
                "http3.connection-task.panic-during-shutdown"
            }
            Self::Http3ConnectionTaskShutdownHang => "http3.connection-task.shutdown-hang",
            Self::Http3ConnectionCreateError => "http3.connection.create-error",
            Self::Http3ConnectionAcceptError => "http3.connection.accept-error",
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
            Self::Http3BodyPumpEmptyData => "http3.body-pump.empty-data-frame",
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
type WebSocketTasks = Arc<Mutex<tokio::task::JoinSet<()>>>;
type RequestBodyTasks = Arc<Mutex<tokio::task::JoinSet<()>>>;
// Keep a bounded burst ahead of the HTTP body consumer. Sends fit into
// available slots synchronously; a full queue returns an awaitable so Tokio
// can apply backpressure. This is bounded by message count, not body bytes.
const RESPONSE_BODY_QUEUE_CAPACITY: usize = 16;

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
    websocket_receive_bridge_futures: AtomicU64,
    websocket_outgoing_messages: AtomicU64,
    websocket_outgoing_queue_full: AtomicU64,
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
                "websocket_receive_bridge_futures={} ",
                "websocket_outgoing_messages={} ",
                "websocket_outgoing_queue_full={}"
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
                .websocket_receive_bridge_futures
                .load(Ordering::Relaxed),
            self.counters
                .websocket_outgoing_messages
                .load(Ordering::Relaxed),
            self.counters
                .websocket_outgoing_queue_full
                .load(Ordering::Relaxed),
        ));
    }
}

struct ServeOptions {
    host: String,
    port: u16,
    tcp_tls: Option<TlsAcceptor>,
    quic_config: Option<quinn::ServerConfig>,
    graceful_timeout: std::time::Duration,
}

struct ServerContext {
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    server_addr: SocketAddr,
    tcp_tls: Option<TlsAcceptor>,
    state: Option<Arc<Py<PyDict>>>,
    websocket_tasks: WebSocketTasks,
    request_body_tasks: RequestBodyTasks,
    #[cfg(coverage)]
    completed_request_body_pumps: Arc<AtomicUsize>,
    diagnostics: RuntimeDiagnostics,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
    pending_python_tasks: TaskTracker,
    force_application_shutdown: CancellationToken,
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
struct ConnectionContext {
    server: Arc<ServerContext>,
    peer_addr: SocketAddr,
    transport_scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
}

struct ActiveHttpRequest {
    active_http_requests: Arc<AtomicUsize>,
    read_eof_waker: Arc<AtomicWaker>,
}

impl ActiveHttpRequest {
    fn new(active_http_requests: Arc<AtomicUsize>, read_eof_waker: Arc<AtomicWaker>) -> Self {
        active_http_requests.fetch_add(1, Ordering::AcqRel);
        Self {
            active_http_requests,
            read_eof_waker,
        }
    }
}

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
            guard: TaskAbortGuard(Some(handle.abort_handle())),
            handle,
        }
    }

    fn as_mut(&mut self) -> &mut tokio::task::JoinHandle<T> {
        &mut self.handle
    }

    fn into_handle(mut self) -> tokio::task::JoinHandle<T> {
        self.guard.0.take();
        self.handle
    }

    fn leave_running(&mut self) {
        self.guard.0.take();
    }
}

struct TaskAbortGuard(Option<tokio::task::AbortHandle>);

impl Drop for TaskAbortGuard {
    fn drop(&mut self) {
        if let Some(handle) = self.0.take() {
            handle.abort();
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

struct RequestMessage {
    body: Bytes,
    more_body: bool,
    disconnected: bool,
}

fn make_http_request_message(
    py: Python<'_>,
    request: Option<RequestMessage>,
    request_disconnected: &AtomicBool,
) -> PyResult<Py<PyAny>> {
    let message = PyDict::new(py);
    if let Some(request) = request.filter(|request| !request.disconnected) {
        coverage_try!(
            HttpRequestTypeSetItem,
            message.set_item("type", "http.request")
        );
        coverage_try!(
            HttpRequestBodySetItem,
            message.set_item("body", PyBytes::new(py, &request.body))
        );
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
}

#[pymethods]
impl PythonTaskStarter {
    fn __call__(&mut self) -> PyResult<()> {
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
    connection_closed: watch::Receiver<bool>,
    request_cancellation: CancellationToken,
    request_disconnected: Arc<AtomicBool>,
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
        if slf.request_disconnected.load(Ordering::Acquire) || *slf.connection_closed.borrow() {
            slf.diagnostics.http_receive_immediate();
            #[cfg(coverage)]
            let request_message = if coverage_fault_is_armed(
                CoverageFaultPoint::HttpReceiveImmediateDisconnectMessageError,
            ) {
                Err(PyMemoryError::new_err(
                    "coverage-injected immediate HTTP disconnect message error",
                ))
            } else {
                make_http_request_message(py, None, &slf.request_disconnected)
            };
            #[cfg(not(coverage))]
            let request_message = make_http_request_message(py, None, &slf.request_disconnected);
            return Ok(request_message?.into_bound(py));
        }

        #[cfg(coverage)]
        let force_contention =
            coverage_fault_is_armed(CoverageFaultPoint::HttpReceiveLockContention)
                && slf.receive_calls.fetch_add(1, Ordering::AcqRel) > 0;
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
                if coverage_fault_is_armed(CoverageFaultPoint::HttpReceiveLockContention) {
                    log_error(format_args!(
                        "uvicorn-rs: coverage observed concurrent HTTP receive lock contention"
                    ));
                }
                None
            }
        };
        if let Some(request) = immediate {
            slf.diagnostics.http_receive_immediate();
            return Ok(
                make_http_request_message(py, request, &slf.request_disconnected)?.into_bound(py),
            );
        }
        let request_messages = Arc::clone(&slf.request_messages);
        let mut connection_closed = slf.connection_closed.clone();
        let request_cancellation = slf.request_cancellation.clone();
        let request_disconnected = Arc::clone(&slf.request_disconnected);
        slf.diagnostics.http_receive_bridge_future();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
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
                    _ = wait_for_connection_close(&mut connection_closed) => {
                        request_disconnected.store(true, Ordering::Release);
                        None
                    }
                    _ = request_cancellation.cancelled() => {
                        request_disconnected.store(true, Ordering::Release);
                        None
                    }
                }
            };
            Python::attach(|py| make_http_request_message(py, request, &request_disconnected))
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
                if *slf.connection_closed.borrow()
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
                if *slf.connection_closed.borrow()
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

#[pyclass]
struct WebSocketIo {
    incoming: Arc<Mutex<mpsc::Receiver<WebSocketIncoming>>>,
    connect_delivered: AtomicBool,
    connection_closed: watch::Receiver<bool>,
    state: Arc<AtomicU8>,
    handshake: std::sync::Mutex<Option<oneshot::Sender<WebSocketHandshake>>>,
    outgoing: mpsc::Sender<WebSocketOutgoing>,
    diagnostics: RuntimeDiagnostics,
}

#[pymethods]
impl WebSocketIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let connect = !slf.connect_delivered.swap(true, Ordering::AcqRel);
        let incoming = Arc::clone(&slf.incoming);
        let mut connection_closed = slf.connection_closed.clone();
        let state = Arc::clone(&slf.state);
        slf.diagnostics.websocket_receive_bridge_future();
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let incoming_message = if connect {
                None
            } else if state.load(Ordering::Acquire) == 3 || *connection_closed.borrow() {
                state.store(3, Ordering::Release);
                Some(WebSocketIncoming::Disconnect {
                    code: 1005,
                    reason: String::new(),
                })
            } else {
                tokio::select! {
                    biased;
                    message = async {
                        #[cfg(coverage)]
                        if coverage_fault_is_armed(CoverageFaultPoint::WebSocketReceiveChannelClosed)
                            || coverage_fault_is_armed(CoverageFaultPoint::WebSocketReceiveClosedTypeSetItem)
                            || coverage_fault_is_armed(CoverageFaultPoint::WebSocketReceiveClosedCodeSetItem)
                            || coverage_fault_is_armed(CoverageFaultPoint::WebSocketReceiveClosedReasonSetItem)
                        {
                            return None;
                        }
                        incoming.lock().await.recv().await
                    } => message,
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_is_armed(CoverageFaultPoint::WebSocketReceiveConnectionClosed) {
                            return;
                        }
                        let _ = connection_closed.changed().await;
                    } => {
                        state.store(3, Ordering::Release);
                        Some(WebSocketIncoming::Disconnect {
                            code: 1005,
                            reason: String::new(),
                        })
                    }
                }
            };
            Python::attach(|py| -> PyResult<Py<PyAny>> {
                let message = PyDict::new(py);
                if connect {
                    coverage_try!(
                        WebSocketReceiveConnectTypeSetItem,
                        message.set_item("type", "websocket.connect")
                    );
                } else {
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
    ) -> PyResult<Self> {
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
                Some(LifespanEvent::StartupComplete) => Ok(Self {
                    state: Some(Arc::new(state)),
                    requests: Some(request_tx),
                    events: Some(event_rx),
                    app_task: Some(app_task),
                }),
                Some(LifespanEvent::StartupFailed(message)) => {
                    app_task.as_mut().abort();
                    let _ = app_task.into_handle().await;
                    Err(PyRuntimeError::new_err(if message.is_empty() {
                        "ASGI lifespan startup failed".to_string()
                    } else {
                        message
                    }))
                }
                Some(_) => {
                    app_task.as_mut().abort();
                    let _ = app_task.into_handle().await;
                    log_error(format_args!("uvicorn-rs: ASGI app does not support lifespan"));
                    Ok(Self {
                        state: None,
                        requests: None,
                        events: None,
                        app_task: None,
                    })
                }
                None => {
                    // Retain cancellation ownership until the result has been
                    // observed, including if startup is cancelled mid-await.
                    let result = app_task.as_mut().await;
                    app_task.into_handle();
                    Self::without_lifespan(result)
                },
            },
            result = app_task.as_mut() => {
                app_task.into_handle();
                Self::without_lifespan(result)
            }
        }
    }

    fn without_lifespan(
        result: Result<PyResult<Py<PyAny>>, tokio::task::JoinError>,
    ) -> PyResult<Self> {
        match result {
            Ok(Ok(_)) => {}
            Ok(Err(error)) => Python::attach(|py| error.print(py)),
            Err(error) => {
                return Err(PyRuntimeError::new_err(format!(
                    "ASGI lifespan task failed: {error}"
                )));
            }
        }
        log_error(format_args!(
            "uvicorn-rs: ASGI app does not support lifespan"
        ));
        Ok(Self {
            state: None,
            requests: None,
            events: None,
            app_task: None,
        })
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

#[pyclass]
struct ServerControl {
    cancellation: CancellationToken,
}

#[pymethods]
impl ServerControl {
    #[new]
    fn new() -> Self {
        Self {
            cancellation: CancellationToken::new(),
        }
    }

    fn shutdown(&self) {
        self.cancellation.cancel();
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
    #[cfg(coverage)]
    body_consumer_pause: Option<Pin<Box<tokio::time::Sleep>>>,
    #[cfg(coverage)]
    body_consumer_pause_started: bool,
}

impl Drop for AsgiBody {
    fn drop(&mut self) {
        if let Some(ResponseApplication::Running(task)) = &self.application {
            task.abort();
        }
    }
}

struct ConnectionIo<I> {
    io: I,
    closed: watch::Sender<bool>,
    active_http_requests: Arc<AtomicUsize>,
    read_eof_waker: Arc<AtomicWaker>,
    read_eof: bool,
    #[cfg(coverage)]
    eof_recheck_paused: bool,
}

async fn pump_http_request_body(
    mut body: Incoming,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: watch::Receiver<bool>,
    cancellation: CancellationToken,
    request_cancellation: CancellationToken,
) {
    #[cfg(coverage)]
    if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpFirstPollPause) {
        // Hold admission before the first read until the peer or server closes,
        // then resume at the known-stop guard.
        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
    }
    loop {
        if *connection_closed.borrow()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
        {
            return;
        }
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
            frame = body.frame() => frame,
        };

        match frame {
            Some(Ok(frame)) => {
                if let Ok(data) = frame.into_data() {
                    if !data.is_empty() {
                        let message = RequestMessage {
                            body: data,
                            more_body: true,
                            disconnected: false,
                        };
                        tokio::select! {
                            biased;
                            _ = async {
                                #[cfg(coverage)]
                                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpSendConnectionClosed) {
                                    return;
                                }
                                wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                            } => return,
                            result = sender.send(message) => {
                                if result.is_err() {
                                    drain_http_request_body(&mut body, &mut connection_closed, &cancellation, &request_cancellation).await;
                                    return;
                                }
                            }
                        }
                    }
                }
            }
            Some(Err(_)) => {
                #[cfg(coverage)]
                if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpErrorStop) {
                    request_cancellation.cancel();
                }
                tokio::select! {
                    biased;
                    _ = wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation) => return,
                    _ = sender.send(RequestMessage {
                        body: Bytes::new(),
                        more_body: false,
                        disconnected: true,
                    }) => {}
                }
                return;
            }
            None => {
                let message = RequestMessage {
                    body: Bytes::new(),
                    more_body: false,
                    disconnected: false,
                };
                tokio::select! {
                    biased;
                    _ = async {
                        #[cfg(coverage)]
                        if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpFinalSendConnectionClosed) {
                            return;
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    result = sender.send(message) => {
                        if result.is_err() {
                            return;
                        }
                    }
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

async fn drain_http_request_body(
    body: &mut Incoming,
    connection_closed: &mut watch::Receiver<bool>,
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
        let frame = if coverage_fault_take(CoverageFaultPoint::HttpBodyPumpDrainTerminalFrame) {
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
    connection_closed: &mut watch::Receiver<bool>,
    cancellation: &CancellationToken,
    request_cancellation: &CancellationToken,
) {
    tokio::select! {
        biased;
        _ = wait_for_connection_close(connection_closed) => {},
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

async fn wait_for_connection_close(connection_closed: &mut watch::Receiver<bool>) {
    let _ = connection_closed.wait_for(|closed| *closed).await;
}

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
        match Pin::new(&mut this.io).poll_read(cx, buffer) {
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

enum WriteBuffers<'a> {
    Scalar(&'a [u8]),
    Vectored(&'a [std::io::IoSlice<'a>]),
}

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
        let result = match buffers {
            WriteBuffers::Scalar(buffer) => Pin::new(&mut self.io).poll_write(cx, buffer),
            WriteBuffers::Vectored(buffers) => {
                Pin::new(&mut self.io).poll_write_vectored(cx, buffers)
            }
        };
        match result {
            Poll::Ready(Err(error)) => {
                self.closed.send_replace(true);
                Poll::Ready(Err(error))
            }
            result => result,
        }
    }
}

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
        Pin::new(&mut self.get_mut().io).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().io).poll_shutdown(cx)
    }
}

impl AsgiBody {
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
        let Some(application) = this.application.take() else {
            return this.poll_app_task(cx);
        };

        match this.receiver.poll_recv(cx) {
            Poll::Ready(Some(chunk)) => {
                if !chunk.more_body {
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
                    // Force the app task to queue its final body after this
                    // receive poll returned Pending, exercising the recovery
                    // path without relying on scheduler luck.
                    std::thread::sleep(std::time::Duration::from_millis(100));
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
#[pyo3(signature = (app, invoke, host, port, certfile, keyfile, graceful_timeout, control))]
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
    certfile: Option<String>,
    keyfile: Option<String>,
    graceful_timeout: u64,
    control: Py<ServerControl>,
) -> PyResult<Bound<'py, PyAny>> {
    let graceful_timeout = std::time::Duration::from_secs(graceful_timeout);
    #[cfg(coverage)]
    let graceful_timeout = if coverage_fault_take(CoverageFaultPoint::ServerGracefulTimeoutOverflow)
    {
        std::time::Duration::from_secs(u64::MAX)
    } else {
        graceful_timeout
    };
    // Reject an unrepresentable duration before allocating application tasks
    // or opening listeners. The shutdown budget still starts at shutdown.
    tokio::time::Instant::now()
        .checked_add(graceful_timeout)
        .ok_or_else(|| {
            PyValueError::new_err("graceful_timeout exceeds the supported monotonic deadline range")
        })?;
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
    #[cfg(coverage)]
    drop(serve_control_borrow);
    let cancel_on_drop = CancelOnDrop(cancellation.clone());
    let diagnostics = RuntimeDiagnostics::default();
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        let _cancel_on_drop = cancel_on_drop;
        let options = ServeOptions {
            host,
            port,
            tcp_tls,
            quic_config,
            graceful_timeout,
        };
        let result = serve_forever(
            app,
            invoke,
            locals,
            cancellation,
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

async fn serve_forever(
    app: Py<PyAny>,
    invoke: Py<PyAny>,
    locals: TaskLocals,
    cancellation: CancellationToken,
    options: ServeOptions,
    diagnostics: RuntimeDiagnostics,
) -> PyResult<()> {
    let listener = TcpListener::bind((options.host.as_str(), options.port))
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
    let lifespan_start = LifespanRuntime::start(
        Arc::clone(&app),
        Arc::clone(&invoke),
        locals.clone(),
        diagnostics.clone(),
        lifespan_cleanup_tasks.clone(),
    )
    .await;
    let mut lifespan = match lifespan_start {
        Ok(lifespan) => lifespan,
        Err(error) => {
            wait_for_lifespan_cleanup(&lifespan_cleanup_tasks, options.graceful_timeout).await;
            return Err(error);
        }
    };
    let state = lifespan.state.clone();
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
        tcp_tls: options.tcp_tls,
        state,
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
    let http3_task =
        endpoint.map(|endpoint| tokio::spawn(serve_http3(endpoint, Arc::clone(&server))));

    let mut connection_tasks = tokio::task::JoinSet::new();
    let mut accept_error = None;
    loop {
        tokio::select! {
            biased;
            _ = cancellation.cancelled() => break,
            Some(result) = connection_tasks.join_next(), if !connection_tasks.is_empty() => {
                match result {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => log_error(format_args!("uvicorn-rs: connection task failed: {error}")),
                    Err(error) => log_error(format_args!("uvicorn-rs: connection task failed: {error}")),
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
    drop(listener);
    cancellation.cancel();
    let shutdown_started = tokio::time::Instant::now();
    if let Some(mut http3_task) = http3_task {
        if let Err(error) = tokio::time::timeout(
            options
                .graceful_timeout
                .saturating_sub(shutdown_started.elapsed()),
            &mut http3_task,
        )
        .await
        {
            log_error(format_args!(
                "uvicorn-rs: HTTP/3 shutdown exceeded grace period: {error}"
            ));
            http3_task.abort();
            let _ = http3_task.await;
        }
    }
    if tokio::time::timeout(
        options
            .graceful_timeout
            .saturating_sub(shutdown_started.elapsed()),
        async {
            while let Some(result) = connection_tasks.join_next().await {
                match result {
                    Ok(Ok(())) => {}
                    Ok(Err(error)) => log_error(format_args!(
                        "uvicorn-rs: connection task failed during shutdown: {error}"
                    )),
                    Err(error) => log_error(format_args!(
                        "uvicorn-rs: connection task failed during shutdown: {error}"
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
    if tokio::time::timeout(
        options
            .graceful_timeout
            .saturating_sub(shutdown_started.elapsed()),
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
    let mut websocket_tasks = server.websocket_tasks.lock().await;
    if tokio::time::timeout(
        options
            .graceful_timeout
            .saturating_sub(shutdown_started.elapsed()),
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
    server.pending_python_tasks.close();
    if tokio::time::timeout(options.graceful_timeout, server.pending_python_tasks.wait())
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
            .max(std::time::Duration::from_millis(100));
        if tokio::time::timeout(cleanup_timeout, server.pending_python_tasks.wait())
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
    // Lifespan shutdown is a separate ASGI phase. The connection drain may
    // consume its full grace period while cancelling outstanding applications;
    // still give the lifespan task its own bounded window to finish.
    #[cfg(coverage)]
    let lifespan_shutdown_timeout =
        if coverage_fault_is_armed(CoverageFaultPoint::LifespanShutdownForceTimeout) {
            // Give the Python app time to receive shutdown and enter its held
            // state before the timeout cancels the lifespan task.
            std::time::Duration::from_secs(1)
        } else {
            // Zero grace disables active request draining, but still needs a
            // bounded event-loop window to deliver and answer ASGI shutdown.
            options
                .graceful_timeout
                .max(std::time::Duration::from_millis(100))
        };
    #[cfg(not(coverage))]
    let lifespan_shutdown_timeout = options
        .graceful_timeout
        .max(std::time::Duration::from_millis(100));
    let shutdown_result =
        match tokio::time::timeout(lifespan_shutdown_timeout, lifespan.shutdown()).await {
            Ok(result) => result,
            Err(_) => Err(PyRuntimeError::new_err(
                "ASGI lifespan shutdown exceeded the graceful timeout",
            )),
        };
    lifespan.cancel_and_wait().await;
    wait_for_lifespan_cleanup(&lifespan_cleanup_tasks, options.graceful_timeout).await;
    if let Some(error) = accept_error {
        return Err(error);
    }
    shutdown_result
}

async fn wait_for_lifespan_cleanup(tracker: &TaskTracker, graceful_timeout: std::time::Duration) {
    tracker.close();
    let cleanup_timeout = graceful_timeout.max(std::time::Duration::from_millis(100));
    if tokio::time::timeout(cleanup_timeout, tracker.wait())
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
        closed: closed_tx.clone(),
        active_http_requests: Arc::clone(&active_http_requests),
        read_eof_waker: Arc::clone(&read_eof_waker),
        read_eof: false,
        #[cfg(coverage)]
        eof_recheck_paused: false,
    };
    let context = ConnectionContext {
        server: Arc::clone(&server),
        peer_addr,
        transport_scheme,
        connection_closed: closed_rx,
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
    let service_active_http_requests = Arc::clone(&active_http_requests);
    let service_read_eof_waker = Arc::clone(&read_eof_waker);
    let service = service_fn(move |request: Request<Incoming>| {
        let context = context.clone();
        let active_http_requests = Arc::clone(&service_active_http_requests);
        let read_eof_waker = Arc::clone(&service_read_eof_waker);
        async move {
            let _active_request = ActiveHttpRequest::new(active_http_requests, read_eof_waker);
            if is_websocket_upgrade(&request) {
                Ok::<_, std::io::Error>(handle_websocket_request(request, context).await)
            } else {
                handle_request(request, context).await
            }
        }
    });
    let mut builder = auto::Builder::new(TokioExecutor::new());
    builder.http1().max_buf_size(64 * 1024);
    let connection = builder.serve_connection_with_upgrades(TokioIo::new(io), service);
    tokio::pin!(connection);
    tokio::select! {
        result = &mut connection => result?,
        _ = cancellation.cancelled() => {
            connection.as_mut().graceful_shutdown();
            if let Ok(Err(error)) = tokio::time::timeout(graceful_timeout, &mut connection).await {
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

async fn serve_http3(
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
    if coverage_fault_is_armed(CoverageFaultPoint::ServerHttp3TaskShutdownHang) {
        std::future::pending::<()>().await;
    }
    #[cfg(coverage)]
    let connection_drain_timeout = if inject_connection_task_shutdown_hang {
        std::time::Duration::from_millis(100)
    } else {
        server.graceful_timeout
    };
    #[cfg(not(coverage))]
    let connection_drain_timeout = server.graceful_timeout;
    if tokio::time::timeout(connection_drain_timeout, async {
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
    let _ = tokio::time::timeout(server.graceful_timeout, endpoint.wait_idle()).await;
    Ok(())
}

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
            connection_closed: closed_rx.clone(),
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

fn observe_http3_request_task(result: Result<(), tokio::task::JoinError>) {
    if let Err(error) = result {
        log_error(format_args!(
            "uvicorn-rs: HTTP/3 request task failed: {error}"
        ));
    }
}

async fn handle_http3_request(
    resolver: h3::server::RequestResolver<h3_quinn::Connection, Bytes>,
    context: ConnectionContext,
) -> Result<(), BoxError> {
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

async fn pump_h3_request_body(
    mut body: h3::server::RequestStream<h3_quinn::RecvStream, Bytes>,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: watch::Receiver<bool>,
    cancellation: CancellationToken,
    request_cancellation: CancellationToken,
) {
    #[cfg(coverage)]
    let mut pending_data: Option<Bytes> = None;
    loop {
        #[cfg(coverage)]
        if *connection_closed.borrow()
            || cancellation.is_cancelled()
            || request_cancellation.is_cancelled()
            || coverage_fault_take(CoverageFaultPoint::Http3BodyPumpConnectionClosed)
        {
            return;
        }
        #[cfg(not(coverage))]
        if *connection_closed.borrow()
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
                    body: chunk,
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
                                body: Bytes::new(),
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
                    body: Bytes::new(),
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
                                body: Bytes::new(),
                                more_body: false,
                                disconnected: false,
                            }).await;
                            return;
                        }
                        wait_for_body_pump_stop(&mut connection_closed, &cancellation, &request_cancellation).await;
                    } => return,
                    result = sender.send(message) => {
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
                        body: Bytes::new(),
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
                body: Bytes::new(),
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
        #[cfg(coverage)]
        let completed_pumps = Arc::clone(&context.server.completed_request_body_pumps);
        spawn_request_body_task(&request_body_tasks, async move {
            pump_http_request_body(
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
    let (start_tx, mut start_rx) = mpsc::channel(1);
    let (body_tx, body_rx) = mpsc::channel(RESPONSE_BODY_QUEUE_CAPACITY);
    let response_start_attempted = Arc::new(AtomicBool::new(false));
    let response_started = Arc::new(AtomicBool::new(false));
    let app_response_start_attempted = Arc::clone(&response_start_attempted);
    let app_response_started = Arc::clone(&response_started);
    let app_task_tracker = context.server.pending_python_tasks.clone();
    let cancellation_tracker = app_task_tracker.clone();
    let force_application_shutdown = context.server.force_application_shutdown.clone();
    let app_future = async move {
        #[cfg(coverage)]
        if coverage_fault_take(CoverageFaultPoint::HttpAppTaskPanicBeforeResponseStart) {
            coverage_panic("coverage-injected ASGI request task panic");
        }
        let app_future = Python::attach(move |py| {
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
    let defer_completed_app_result_once = matches!(application, ResponseApplication::Completed(_));

    let body = AsgiBody {
        receiver: body_rx,
        application: Some(application),
        app_task_tracker,
        defer_completed_app_result_once,
        incomplete_body_result_deferred: false,
        #[cfg(coverage)]
        body_consumer_pause: None,
        #[cfg(coverage)]
        body_consumer_pause_started: false,
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
                    HeaderValue::from_static("text/plain"),
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
    let request_key = request
        .headers()
        .get(http::header::SEC_WEBSOCKET_KEY)
        .ok_or_else(|| {
            Box::new(WebSocketHandshakeError {
                response_body: "Failed to open a WebSocket connection: missing Sec-WebSocket-Key header; 'sec-websocket-key'.\n".to_owned(),
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
                response_body: "Failed to open a WebSocket connection: missing Sec-WebSocket-Version header; 'sec-websocket-version'.\n".to_owned(),
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
        connection_closed: context.connection_closed.clone(),
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

    let handshake = tokio::select! {
        biased;
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

    let app_task = app_task.into_handle();
    let server = Arc::clone(&context.server);
    let session_cancellation = server.cancellation.clone();
    let upgrade_cancellation = session_cancellation.clone();
    let connection_closed = context.connection_closed;
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
        if coverage_fault_is_armed(CoverageFaultPoint::ServerWebSocketTaskShutdownHang) {
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
                    let socket = WebSocketStream::from_raw_socket(
                        TokioIo::new(upgraded),
                        Role::Server,
                        None,
                    ).await;
                    if let Err(error) = drive_websocket(
                        socket,
                        incoming_tx,
                        outgoing_rx,
                        app_task,
                        state,
                        connection_closed,
                        session_cancellation,
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

async fn send_websocket_message<I>(
    socket: &mut WebSocketStream<I>,
    message: Message,
) -> Result<(), BoxError>
where
    I: AsyncRead + AsyncWrite + Unpin,
{
    #[cfg(coverage)]
    let result = if coverage_fault_take(CoverageFaultPoint::WebSocketDriverSendError)
        || coverage_fault_take(CoverageFaultPoint::WebSocketDriverDrainSendError)
    {
        Err(tokio_tungstenite::tungstenite::Error::ConnectionClosed)
    } else {
        socket.send(message).await
    };
    #[cfg(not(coverage))]
    let result = socket.send(message).await;
    result.map_err(|error| Box::new(error) as BoxError)
}

async fn drive_websocket<I>(
    mut socket: WebSocketStream<I>,
    incoming: mpsc::Sender<WebSocketIncoming>,
    mut outgoing: mpsc::Receiver<WebSocketOutgoing>,
    mut app_task: tokio::task::JoinHandle<PyResult<Py<PyAny>>>,
    state: Arc<AtomicU8>,
    mut connection_closed: watch::Receiver<bool>,
    cancellation: CancellationToken,
) -> Result<(), BoxError>
where
    I: AsyncRead + AsyncWrite + Unpin,
{
    let mut app_task_completed = false;
    let mut driver_error = None;
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
        tokio::select! {
            biased;
            _ = async {
                #[cfg(coverage)]
                if coverage_fault_is_armed(CoverageFaultPoint::WebSocketDriverConnectionClosed) {
                    return;
                }
                wait_for_connection_close(&mut connection_closed).await;
            } => {
                state.store(3, Ordering::Release);
                let _ = incoming.try_send(WebSocketIncoming::Disconnect {
                    code: 1006,
                    reason: String::new(),
                });
                app_task_completed = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await.is_ok();
                break;
            }
            _ = cancellation.cancelled() => {
                let _ = tokio::time::timeout(
                    std::time::Duration::from_millis(100),
                    socket.send(Message::Close(Some(CloseFrame {
                        code: CloseCode::from(1012),
                        reason: "".into(),
                    }))),
                ).await;
                state.store(3, Ordering::Release);
                let _ = incoming.try_send(WebSocketIncoming::Disconnect {
                    code: 1012,
                    reason: String::new(),
                });
                app_task_completed = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await.is_ok();
                break;
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
                    return None;
                }
                socket.next().await
            } => {
                match message {
                    Some(Ok(Message::Text(text))) => {
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
                    Some(Ok(Message::Binary(data))) => {
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
                    Some(Ok(Message::Close(frame))) => {
                        let (code, reason) = frame
                            .map(|frame| (u16::from(frame.code), frame.reason.to_string()))
                            .unwrap_or((1005, String::new()));
                        state.store(3, Ordering::Release);
                        let _ = incoming.send(WebSocketIncoming::Disconnect { code, reason }).await;
                        app_task_completed = tokio::time::timeout(
                            std::time::Duration::from_secs(1),
                            &mut app_task,
                        )
                        .await
                        .is_ok();
                        break;
                    }
                    Some(Ok(Message::Ping(_) | Message::Pong(_) | Message::Frame(_))) => {}
                    Some(Err(error)) => {
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
                    None => {
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
    coverage_try!(
        WebSocketScopePathSetItem,
        scope.set_item(
            "path",
            percent_encoding::percent_decode_str(request.uri.path())
                .decode_utf8_lossy()
                .as_ref()
        )
    );
    coverage_try!(
        WebSocketScopeRawPathSetItem,
        scope.set_item("raw_path", PyBytes::new(py, request.uri.path().as_bytes()))
    );
    coverage_try!(
        WebSocketScopeQueryStringSetItem,
        scope.set_item(
            "query_string",
            PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes())
        )
    );
    coverage_try!(
        WebSocketScopeRootPathSetItem,
        scope.set_item("root_path", "")
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
                    if !protocol.is_empty() {
                        subprotocols.push(protocol);
                    }
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
    let path = percent_encoding::percent_decode_str(request.uri.path()).decode_utf8_lossy();
    coverage_try!(
        HttpScopePathSetItem,
        scope.set_item("path", PyString::new(py, path.as_ref()))
    );
    coverage_try!(
        HttpScopeRawPathSetItem,
        scope.set_item("raw_path", PyBytes::new(py, raw_path))
    );
    coverage_try!(
        HttpScopeQueryStringSetItem,
        scope.set_item(
            "query_string",
            PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes())
        )
    );
    coverage_try!(HttpScopeRootPathSetItem, scope.set_item("root_path", ""));

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

fn response(status: StatusCode, body: ResponseBody, headers: HeaderMap) -> Response<ResponseBody> {
    let mut response = Response::new(body);
    *response.headers_mut() = headers;
    *response.status_mut() = status;
    response
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    // Both success and startup resource failure are process-wide decisions.
    // Retain the runtime without leaking a fresh allocation on reinitialization;
    // a failed build is returned again rather than silently retrying on import.
    static NATIVE_RUNTIME: OnceLock<Result<tokio::runtime::Runtime, std::io::Error>> =
        OnceLock::new();
    let runtime = NATIVE_RUNTIME.get_or_init(|| {
        let mut runtime_builder = tokio::runtime::Builder::new_multi_thread();
        runtime_builder.worker_threads(2).enable_all();
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
