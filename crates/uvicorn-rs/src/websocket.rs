//! HTTP/1.1 WebSocket handshake and session support.
//!
//! The server owns the upgraded session until it finishes or the configured
//! connection-drain deadline expires. This module provides an initial RFC 6455
//! handshake and framed session over HTTP/1.1. It does not implement WebSockets
//! over HTTP/2 or HTTP/3, or negotiate WebSocket extensions.

#[cfg(coverage)]
use std::sync::{
    atomic::{AtomicU8, Ordering},
    OnceLock,
};
use std::{error::Error, fmt, future::Future};

use data_encoding::BASE64;
use futures_util::{SinkExt, StreamExt};
use http::{
    header::{
        CONNECTION, SEC_WEBSOCKET_ACCEPT, SEC_WEBSOCKET_EXTENSIONS, SEC_WEBSOCKET_KEY,
        SEC_WEBSOCKET_PROTOCOL, SEC_WEBSOCKET_VERSION, UPGRADE,
    },
    Extensions, HeaderMap, HeaderName, HeaderValue, Method, Request, Response, StatusCode, Version,
};
use hyper::upgrade::{self, OnUpgrade, Upgraded};
use hyper_util::rt::TokioIo;
#[cfg(coverage)]
use tokio::sync::Notify;
use tokio_tungstenite::{
    tungstenite::{handshake::derive_accept_key, protocol::Role, Error as TungsteniteError},
    WebSocketStream,
};

use crate::{ConnectionUpgrade, ConnectionUpgradeClosed};

/// WebSocket messages, close frames, and close-code values used by a session.
pub use tokio_tungstenite::tungstenite::protocol::{
    frame::coding::CloseCode as WebSocketCloseCode, CloseFrame as WebSocketCloseFrame,
    Message as WebSocketMessage,
};

/// A validated HTTP/1.1 WebSocket upgrade request.
///
/// Create this value from a mutable request, optionally select one of the
/// client's offered subprotocols or add response headers, and call
/// [`accept`](Self::accept) to register the session before returning its
/// response. The returned response has status 101 and the correct RFC 6455
/// handshake headers.
pub struct WebSocketUpgrade {
    on_upgrade: OnUpgrade,
    connection_upgrade: ConnectionUpgrade,
    accept_key: HeaderValue,
    offered_subprotocols: Vec<Vec<u8>>,
    selected_subprotocol: Option<HeaderValue>,
    response_headers: HeaderMap,
}

struct ValidatedWebSocketHandshake {
    connection_upgrade: ConnectionUpgrade,
    accept_key: HeaderValue,
    offered_subprotocols: Vec<Vec<u8>>,
}

fn validate_websocket_handshake(
    version: Version,
    method: &Method,
    extensions: &Extensions,
    headers: &HeaderMap,
) -> Result<ValidatedWebSocketHandshake, WebSocketUpgradeError> {
    if version != Version::HTTP_11 {
        return Err(WebSocketUpgradeError::UnsupportedTransport);
    }
    if method != Method::GET {
        return Err(WebSocketUpgradeError::InvalidHandshake(
            "the request method must be GET",
        ));
    }

    let connection_upgrade = extensions
        .get::<ConnectionUpgrade>()
        .cloned()
        .ok_or(WebSocketUpgradeError::UnsupportedTransport)?;

    if !has_header_token(headers, &CONNECTION, b"upgrade")
        || !has_header_token(headers, &UPGRADE, b"websocket")
    {
        return Err(WebSocketUpgradeError::InvalidHandshake(
            "Connection and Upgrade must negotiate websocket",
        ));
    }

    let version = single_header(headers, &SEC_WEBSOCKET_VERSION, "Sec-WebSocket-Version")?;
    if version.as_bytes() != b"13" {
        return Err(WebSocketUpgradeError::InvalidHandshake(
            "Sec-WebSocket-Version must be 13",
        ));
    }

    let key = single_header(headers, &SEC_WEBSOCKET_KEY, "Sec-WebSocket-Key")?;
    let decoded_key = BASE64.decode(key.as_bytes()).map_err(|_| {
        WebSocketUpgradeError::InvalidHandshake("Sec-WebSocket-Key must be valid base64")
    })?;
    if decoded_key.len() != 16 {
        return Err(WebSocketUpgradeError::InvalidHandshake(
            "Sec-WebSocket-Key must decode to 16 bytes",
        ));
    }
    let derived_accept_key = derive_accept_key(key.as_bytes());
    #[cfg(coverage)]
    let accept_key_source: &str = if take_derived_accept_key_header_value_fault() {
        "\r\n"
    } else {
        &derived_accept_key
    };
    #[cfg(not(coverage))]
    let accept_key_source: &str = &derived_accept_key;
    let accept_key = HeaderValue::from_str(accept_key_source).map_err(|_| {
        WebSocketUpgradeError::InvalidHandshake("the derived accept key is invalid")
    })?;

    let offered_subprotocols = parse_subprotocols(headers)?;

    Ok(ValidatedWebSocketHandshake {
        connection_upgrade,
        accept_key,
        offered_subprotocols,
    })
}

impl WebSocketUpgrade {
    /// Validates an RFC 6455 HTTP/1.1 request and obtains its upgrade handle.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::UnsupportedTransport`] for requests
    /// outside HTTP/1.1 or without the native HTTP/1 upgrade capability. It
    /// returns [`WebSocketUpgradeError::InvalidHandshake`] for malformed or
    /// incomplete handshake headers.
    pub fn from_request<B>(request: &mut Request<B>) -> Result<Self, WebSocketUpgradeError> {
        let handshake = validate_websocket_handshake(
            request.version(),
            request.method(),
            request.extensions(),
            request.headers(),
        )?;
        let on_upgrade = upgrade::on(request);

        Ok(Self {
            on_upgrade,
            connection_upgrade: handshake.connection_upgrade,
            accept_key: handshake.accept_key,
            offered_subprotocols: handshake.offered_subprotocols,
            selected_subprotocol: None,
            response_headers: HeaderMap::new(),
        })
    }

    /// Selects a protocol offered by the client.
    ///
    /// Subprotocol matching is case-sensitive. Calling this method with a
    /// value the client did not offer is rejected before the handshake is
    /// committed.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::InvalidSubprotocol`] for a value that
    /// is not an HTTP token or was not offered by the client. Returns
    /// [`WebSocketUpgradeError::SubprotocolAlreadySelected`] if one was
    /// selected earlier.
    pub fn with_subprotocol(mut self, protocol: &str) -> Result<Self, WebSocketUpgradeError> {
        if self.selected_subprotocol.is_some() {
            return Err(WebSocketUpgradeError::SubprotocolAlreadySelected);
        }
        let header_value = HeaderValue::from_str(protocol)
            .map_err(|_| WebSocketUpgradeError::InvalidSubprotocol)?;
        if !is_http_token(protocol.as_bytes())
            || !self
                .offered_subprotocols
                .iter()
                .any(|offered| offered.as_slice() == protocol.as_bytes())
        {
            return Err(WebSocketUpgradeError::InvalidSubprotocol);
        }
        self.selected_subprotocol = Some(header_value);
        Ok(self)
    }

    /// Adds an application response header to the accepted handshake.
    ///
    /// The connection, upgrade, accept, extension, and subprotocol headers
    /// are managed by this type and cannot be overridden. Header capacity
    /// errors are returned instead of panicking.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::ReservedResponseHeader`] for a
    /// protocol-managed header and [`WebSocketUpgradeError::HeaderCapacity`]
    /// if the finite HTTP header map cannot accept another value.
    pub fn with_header(
        mut self,
        name: HeaderName,
        value: HeaderValue,
    ) -> Result<Self, WebSocketUpgradeError> {
        if is_reserved_handshake_header(&name) {
            return Err(WebSocketUpgradeError::ReservedResponseHeader);
        }
        self.response_headers
            .try_append(name, value)
            .map_err(|_| WebSocketUpgradeError::HeaderCapacity)?;
        Ok(self)
    }

    /// Accepts the request, registers the session, and returns the 101 response.
    ///
    /// `handler` owns the session for its lifetime. It can receive and send
    /// framed messages, wait for server shutdown, or return to close the
    /// upgraded transport. Handler errors are reported by the configured
    /// server error observer.
    ///
    /// The body type is supplied by the application so an upgrade response
    /// fits the same body type as its ordinary HTTP responses.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::ConnectionClosed`] if the connection
    /// no longer accepts upgrade sessions, or
    /// [`WebSocketUpgradeError::HeaderCapacity`] if the final response header
    /// map cannot represent the selected handshake headers.
    pub fn accept<B, F, Fut, E>(
        self,
        body: B,
        handler: F,
    ) -> Result<Response<B>, WebSocketUpgradeError>
    where
        F: FnOnce(WebSocketSession) -> Fut + Send + 'static,
        Fut: Future<Output = Result<(), E>> + Send + 'static,
        E: Error + Send + Sync + 'static,
    {
        let Self {
            on_upgrade,
            connection_upgrade,
            accept_key,
            selected_subprotocol,
            response_headers,
            offered_subprotocols: _,
        } = self;

        let mut response = Response::new(body);
        *response.status_mut() = StatusCode::SWITCHING_PROTOCOLS;
        let headers = response.headers_mut();
        headers.insert(CONNECTION, HeaderValue::from_static("upgrade"));
        headers.insert(UPGRADE, HeaderValue::from_static("websocket"));
        headers.insert(SEC_WEBSOCKET_ACCEPT, accept_key);
        if let Some(protocol) = selected_subprotocol {
            headers.insert(SEC_WEBSOCKET_PROTOCOL, protocol);
        }
        for (name, value) in &response_headers {
            headers
                .try_append(name.clone(), value.clone())
                .map_err(|_| WebSocketUpgradeError::HeaderCapacity)?;
        }

        let session_shutdown = connection_upgrade.clone();
        connection_upgrade
            .register(on_upgrade, move |stream| async move {
                let session =
                    WebSocketSession::from_accepted_upgrade(stream, session_shutdown).await;
                handler(session).await
            })
            .map_err(|ConnectionUpgradeClosed| WebSocketUpgradeError::ConnectionClosed)?;
        Ok(response)
    }
}

/// A framed WebSocket session owned by the native HTTP/1.1 connection.
pub struct WebSocketSession {
    stream: WebSocketStream<TokioIo<hyper::upgrade::Upgraded>>,
    connection_upgrade: ConnectionUpgrade,
    // Some(None) retains a peer close frame without a code or reason.
    pending_close: Option<Option<WebSocketCloseFrame>>,
}

impl WebSocketSession {
    /// Creates a framed session for a stream accepted by an HTTP/1.1 upgrade.
    ///
    /// Use this inside the handler passed to [`ConnectionUpgrade::register`]
    /// after returning the response that completes the protocol upgrade.
    /// Prefer [`WebSocketUpgrade::accept`] for RFC 6455 handshakes; this
    /// constructor is available to adapters that already own handshake
    /// validation and response construction.
    pub async fn from_accepted_upgrade(
        stream: TokioIo<Upgraded>,
        connection_upgrade: ConnectionUpgrade,
    ) -> Self {
        Self {
            stream: WebSocketStream::from_raw_socket(stream, Role::Server, None).await,
            connection_upgrade,
            pending_close: None,
        }
    }

    /// Receives the next WebSocket message, including a peer close frame, or
    /// returns `None` when the underlying stream ends. On a peer close, it
    /// flushes the protocol close reply before returning the frame.
    ///
    /// Canceling this future preserves any received close frame. A subsequent
    /// call resumes flushing the reply before returning that frame.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketError`] for malformed frames or transport failure.
    pub async fn receive(&mut self) -> Result<Option<WebSocketMessage>, WebSocketError> {
        if self.pending_close.is_none() {
            match self
                .stream
                .next()
                .await
                .transpose()
                .map_err(WebSocketError)?
            {
                Some(WebSocketMessage::Close(frame)) => self.pending_close = Some(frame),
                message => return Ok(message),
            }
        }
        #[cfg(coverage)]
        if take_close_reply_flush_cancellation_fault() {
            close_reply_flush_cancellation_reached().notify_one();
            std::future::pending::<()>().await;
        }
        // Tungstenite queues the close reply while reading the peer's close
        // frame. Flush it before a handler can return and drop the transport,
        // retaining the frame in the session if this receive is canceled.
        #[cfg(coverage)]
        let flush_result = if take_close_reply_flush_fault() {
            Err(TungsteniteError::Io(std::io::Error::new(
                std::io::ErrorKind::BrokenPipe,
                "coverage-injected WebSocket close-reply flush failure",
            )))
        } else {
            self.stream.flush().await
        };
        #[cfg(not(coverage))]
        let flush_result = self.stream.flush().await;
        let frame = self.pending_close.take();
        flush_result.map_err(WebSocketError)?;
        Ok(frame.map(WebSocketMessage::Close))
    }

    /// Sends a WebSocket data or control message with transport backpressure.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketError`] if the peer has closed or the transport
    /// fails while writing the frame.
    pub async fn send(&mut self, message: WebSocketMessage) -> Result<(), WebSocketError> {
        self.stream.send(message).await.map_err(WebSocketError)
    }

    /// Sends a WebSocket close frame and flushes queued frames.
    ///
    /// Pass `None` to send an empty close frame or provide a close code and
    /// reason in a [`WebSocketCloseFrame`].
    ///
    /// To complete a server-initiated close handshake, continue receiving
    /// until the peer's close frame arrives.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketError`] if the close frame cannot be written.
    pub async fn close(
        &mut self,
        frame: Option<WebSocketCloseFrame>,
    ) -> Result<(), WebSocketError> {
        self.stream.close(frame).await.map_err(WebSocketError)
    }

    /// Waits until the server starts graceful shutdown for this connection.
    pub async fn wait_for_shutdown(&mut self) {
        self.connection_upgrade.wait_for_shutdown().await;
    }
}

#[cfg(coverage)]
static CLOSE_REPLY_FLUSH_FAULT_STATE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static CLOSE_REPLY_FLUSH_CANCELLATION_STATE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static CLOSE_REPLY_FLUSH_CANCELLATION_REACHED: OnceLock<Notify> = OnceLock::new();
#[cfg(coverage)]
static DERIVED_ACCEPT_KEY_HEADER_VALUE_FAULT_STATE: AtomicU8 = AtomicU8::new(0);

/// Arms the coverage-only derived WebSocket accept-key header conversion fault.
///
/// The injected value is supplied only at the header parser boundary in
/// instrumented builds. The derived RFC 6455 accept key remains unchanged.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_derived_accept_key_header_value_fault() -> bool {
    DERIVED_ACCEPT_KEY_HEADER_VALUE_FAULT_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only derived accept-key conversion fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_derived_accept_key_header_value_fault() -> bool {
    DERIVED_ACCEPT_KEY_HEADER_VALUE_FAULT_STATE.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_derived_accept_key_header_value_fault() -> bool {
    DERIVED_ACCEPT_KEY_HEADER_VALUE_FAULT_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms the coverage-only WebSocket close-reply flush fault contract.
///
/// This hook is compiled only for instrumented coverage builds and is absent
/// from normal library builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_close_reply_flush_fault() -> bool {
    CLOSE_REPLY_FLUSH_FAULT_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only WebSocket close-reply flush fault contract.
///
/// Returns whether the armed failure reached the public session error path.
/// This hook is compiled only for instrumented coverage builds.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_close_reply_flush_fault() -> bool {
    CLOSE_REPLY_FLUSH_FAULT_STATE.swap(0, Ordering::AcqRel) == 2
}

/// Arms a coverage-only barrier after a peer close is retained and before its
/// protocol reply is flushed.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_close_reply_flush_cancellation_fault() -> bool {
    CLOSE_REPLY_FLUSH_CANCELLATION_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Waits until a `receive` future reaches the close-reply cancellation barrier.
#[cfg(coverage)]
#[doc(hidden)]
pub async fn wait_for_close_reply_flush_cancellation_fault() {
    close_reply_flush_cancellation_reached().notified().await;
}

/// Finishes the coverage-only close-reply cancellation contract.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_close_reply_flush_cancellation_fault() -> bool {
    CLOSE_REPLY_FLUSH_CANCELLATION_STATE.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_close_reply_flush_fault() -> bool {
    CLOSE_REPLY_FLUSH_FAULT_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
fn take_close_reply_flush_cancellation_fault() -> bool {
    CLOSE_REPLY_FLUSH_CANCELLATION_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

#[cfg(coverage)]
fn close_reply_flush_cancellation_reached() -> &'static Notify {
    CLOSE_REPLY_FLUSH_CANCELLATION_REACHED.get_or_init(Notify::new)
}

/// An error while validating a WebSocket handshake or registering its session.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WebSocketUpgradeError {
    /// The request is not an HTTP/1.1 request with a native upgrade capability.
    UnsupportedTransport,
    /// The request does not satisfy the RFC 6455 handshake requirements.
    InvalidHandshake(&'static str),
    /// The selected subprotocol is invalid or was not offered by the client.
    InvalidSubprotocol,
    /// A subprotocol was selected more than once.
    SubprotocolAlreadySelected,
    /// The application attempted to replace a protocol-managed response header.
    ReservedResponseHeader,
    /// The HTTP header map reached its finite capacity.
    HeaderCapacity,
    /// The HTTP connection ended before the session could be registered.
    ConnectionClosed,
}

impl fmt::Display for WebSocketUpgradeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedTransport => {
                formatter.write_str("WebSocket Upgrade is supported only on HTTP/1.1")
            }
            Self::InvalidHandshake(reason) => {
                write!(formatter, "invalid WebSocket handshake: {reason}")
            }
            Self::InvalidSubprotocol => {
                formatter.write_str("WebSocket subprotocol was invalid or not offered")
            }
            Self::SubprotocolAlreadySelected => {
                formatter.write_str("WebSocket subprotocol was already selected")
            }
            Self::ReservedResponseHeader => {
                formatter.write_str("WebSocket response header is managed by the handshake")
            }
            Self::HeaderCapacity => {
                formatter.write_str("WebSocket response header capacity exceeded")
            }
            Self::ConnectionClosed => {
                formatter.write_str("HTTP connection ended before upgrade registration")
            }
        }
    }
}

impl Error for WebSocketUpgradeError {}

/// A WebSocket framing or transport error.
#[derive(Debug)]
pub struct WebSocketError(TungsteniteError);

impl fmt::Display for WebSocketError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "WebSocket session failed: {}", self.0)
    }
}

impl Error for WebSocketError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(&self.0)
    }
}

fn single_header<'a>(
    headers: &'a HeaderMap,
    name: &HeaderName,
    display_name: &'static str,
) -> Result<&'a HeaderValue, WebSocketUpgradeError> {
    let mut values = headers.get_all(name).iter();
    let Some(value) = values.next() else {
        return Err(WebSocketUpgradeError::InvalidHandshake(display_name));
    };
    if values.next().is_some() {
        return Err(WebSocketUpgradeError::InvalidHandshake(
            "a required handshake header occurred more than once",
        ));
    }
    Ok(value)
}

fn has_header_token(headers: &HeaderMap, name: &HeaderName, expected: &[u8]) -> bool {
    headers.get_all(name).iter().any(|value| {
        value
            .as_bytes()
            .split(|byte| *byte == b',')
            .map(trim_ascii_whitespace)
            .any(|token| token.eq_ignore_ascii_case(expected))
    })
}

fn parse_subprotocols(headers: &HeaderMap) -> Result<Vec<Vec<u8>>, WebSocketUpgradeError> {
    let mut offered = Vec::new();
    for value in headers.get_all(&SEC_WEBSOCKET_PROTOCOL).iter() {
        for protocol in value
            .as_bytes()
            .split(|byte| *byte == b',')
            .map(trim_ascii_whitespace)
        {
            if !is_http_token(protocol) {
                return Err(WebSocketUpgradeError::InvalidHandshake(
                    "Sec-WebSocket-Protocol must contain non-empty tokens",
                ));
            }
            offered.push(protocol.to_vec());
        }
    }
    Ok(offered)
}

fn trim_ascii_whitespace(mut value: &[u8]) -> &[u8] {
    while value.first().is_some_and(u8::is_ascii_whitespace) {
        value = &value[1..];
    }
    while value.last().is_some_and(u8::is_ascii_whitespace) {
        value = &value[..value.len() - 1];
    }
    value
}

fn is_http_token(value: &[u8]) -> bool {
    !value.is_empty()
        && value.iter().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(
                    byte,
                    b'!' | b'#'
                        | b'$'
                        | b'%'
                        | b'&'
                        | b'\''
                        | b'*'
                        | b'+'
                        | b'-'
                        | b'.'
                        | b'^'
                        | b'_'
                        | b'`'
                        | b'|'
                        | b'~'
                )
        })
}

fn is_reserved_handshake_header(name: &HeaderName) -> bool {
    name == CONNECTION
        || name == UPGRADE
        || name == SEC_WEBSOCKET_ACCEPT
        || name == SEC_WEBSOCKET_EXTENSIONS
        || name == SEC_WEBSOCKET_PROTOCOL
}
