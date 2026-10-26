//! HTTP/1.1 WebSocket handshake and session support.
//!
//! The server owns the upgraded session until it finishes or the configured
//! connection-drain deadline expires. This module provides an initial RFC 6455
//! handshake and framed session over HTTP/1.1, including optional
//! `permessage-deflate` negotiation. It does not implement WebSockets over
//! HTTP/2 or HTTP/3.

#[cfg(coverage)]
use std::sync::{
    OnceLock,
    atomic::{AtomicU8, Ordering},
};
use std::{error::Error, fmt, future::Future};

use bytes::Bytes;
use data_encoding::BASE64;
use futures_util::{SinkExt, StreamExt};
use http::{
    Extensions, HeaderMap, HeaderName, HeaderValue, Method, Request, Response, StatusCode, Version,
    header::{
        CONNECTION, SEC_WEBSOCKET_ACCEPT, SEC_WEBSOCKET_EXTENSIONS, SEC_WEBSOCKET_KEY,
        SEC_WEBSOCKET_PROTOCOL, SEC_WEBSOCKET_VERSION, UPGRADE,
    },
};
use hyper::upgrade::{self, OnUpgrade, Upgraded};
use hyper_util::rt::TokioIo;
#[cfg(coverage)]
use tokio::sync::Notify;
use tokio_tungstenite::{
    WebSocketStream,
    tungstenite::{
        Error as TungsteniteError,
        handshake::derive_accept_key,
        protocol::{Role, WebSocketConfig},
    },
};
use yawc::{
    CompressionLevel as YawcCompressionLevel, HttpStream as YawcHttpStream,
    HttpWebSocket as YawcWebSocket, Options as YawcOptions, Role as YawcRole,
    WebSocket as YawcHandshake,
    close::CloseCode as YawcCloseCode,
    frame::{Frame as YawcFrame, OpCode as YawcOpCode},
};

use crate::{ConnectionUpgrade, ConnectionUpgradeClosed};

/// WebSocket messages, close frames, and close-code values used by a session.
pub use tokio_tungstenite::tungstenite::protocol::{
    CloseFrame as WebSocketCloseFrame, Message as WebSocketMessage,
    frame::coding::CloseCode as WebSocketCloseCode,
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
    accept_key: String,
    negotiated_extensions: Option<HeaderValue>,
    offered_subprotocols: Vec<Vec<u8>>,
    selected_subprotocol: Option<HeaderValue>,
    response_headers: HeaderMap,
    max_message_size: Option<usize>,
}

struct ValidatedWebSocketHandshake {
    connection_upgrade: ConnectionUpgrade,
    accept_key: String,
    offered_subprotocols: Vec<Vec<u8>>,
}

fn has_invalid_deflate_window_offer(headers: &HeaderMap) -> bool {
    headers
        .get_all(&SEC_WEBSOCKET_EXTENSIONS)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(','))
        .any(|extension| {
            let mut parameters = extension.split(';');
            if !parameters
                .next()
                .is_some_and(|name| name.trim().eq_ignore_ascii_case("permessage-deflate"))
            {
                return false;
            }

            parameters.any(|parameter| {
                let parameter = parameter.trim();
                let (name, value) = parameter
                    .split_once('=')
                    .map_or((parameter, None), |(name, value)| {
                        (name.trim(), Some(value.trim()))
                    });
                let is_client_window = name.eq_ignore_ascii_case("client_max_window_bits");
                let is_server_window = name.eq_ignore_ascii_case("server_max_window_bits");
                if !is_client_window && !is_server_window {
                    return false;
                }

                match value {
                    Some(value) => !matches!(value.parse::<u8>(), Ok(8..=15)),
                    None => is_server_window,
                }
            })
        })
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
    let accept_key = derive_accept_key(key.as_bytes());

    let offered_subprotocols = parse_subprotocols(headers)?;

    Ok(ValidatedWebSocketHandshake {
        connection_upgrade,
        accept_key,
        offered_subprotocols,
    })
}

fn yawc_options(max_message_size: usize) -> YawcOptions {
    // Yawc treats these limits as exclusive; Uvicorn accepts a message whose
    // size is exactly the configured value.
    let exclusive_limit = max_message_size.saturating_add(1);
    YawcOptions::default()
        .with_max_payload_read(exclusive_limit)
        .with_max_read_buffer(exclusive_limit)
        .with_utf8()
        .with_compression_level(YawcCompressionLevel::default())
}

fn yawc_error(error: yawc::WebSocketError) -> WebSocketError {
    WebSocketError(TungsteniteError::Io(std::io::Error::other(error)))
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
        Self::from_request_with_per_message_deflate(request, true)
    }

    /// Validates an RFC 6455 HTTP/1.1 request and optionally negotiates
    /// `permessage-deflate` before obtaining its upgrade handle.
    ///
    /// The default matches Uvicorn 0.54.0, which enables per-message deflate.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::UnsupportedTransport`] for requests
    /// outside HTTP/1.1 or without the native HTTP/1 upgrade capability. It
    /// returns [`WebSocketUpgradeError::InvalidHandshake`] for malformed or
    /// incomplete handshake headers or an invalid compression offer.
    pub fn from_request_with_per_message_deflate<B>(
        request: &mut Request<B>,
        enabled: bool,
    ) -> Result<Self, WebSocketUpgradeError> {
        let handshake = validate_websocket_handshake(
            request.version(),
            request.method(),
            request.extensions(),
            request.headers(),
        )?;

        let negotiated_extensions =
            if enabled && !has_invalid_deflate_window_offer(request.headers()) {
                let mut negotiation_request = Request::new(());
                *negotiation_request.method_mut() = request.method().clone();
                *negotiation_request.uri_mut() = request.uri().clone();
                *negotiation_request.version_mut() = request.version();
                *negotiation_request.headers_mut() = request.headers().clone();
                let (response, unused_upgrade) = YawcHandshake::upgrade_with_options(
                    &mut negotiation_request,
                    yawc_options(
                        WebSocketConfig::default()
                            .max_message_size
                            .unwrap_or(usize::MAX),
                    ),
                )
                .map_err(|_| {
                    WebSocketUpgradeError::InvalidHandshake(
                        "the Sec-WebSocket-Extensions offer could not be negotiated",
                    )
                })?;
                drop(unused_upgrade);
                response.headers().get(&SEC_WEBSOCKET_EXTENSIONS).cloned()
            } else {
                None
            };
        let on_upgrade = upgrade::on(request);

        Ok(Self {
            on_upgrade,
            connection_upgrade: handshake.connection_upgrade,
            accept_key: handshake.accept_key,
            negotiated_extensions,
            offered_subprotocols: handshake.offered_subprotocols,
            selected_subprotocol: None,
            response_headers: HeaderMap::new(),
            max_message_size: WebSocketConfig::default().max_message_size,
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
    pub fn with_subprotocol(self, protocol: &str) -> Result<Self, WebSocketUpgradeError> {
        self.with_selected_subprotocol(protocol, true)
    }

    /// Selects the subprotocol supplied by an ASGI application.
    ///
    /// This keeps Uvicorn's ASGI behavior: a valid application-selected token
    /// is returned even when the client did not offer it. Native callers that
    /// require offer validation should use [`Self::with_subprotocol`].
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketUpgradeError::InvalidSubprotocol`] for a value that
    /// is not an HTTP token. Returns
    /// [`WebSocketUpgradeError::SubprotocolAlreadySelected`] if one was
    /// selected earlier.
    pub fn with_application_subprotocol(
        self,
        protocol: &str,
    ) -> Result<Self, WebSocketUpgradeError> {
        self.with_selected_subprotocol(protocol, false)
    }

    fn with_selected_subprotocol(
        mut self,
        protocol: &str,
        require_client_offer: bool,
    ) -> Result<Self, WebSocketUpgradeError> {
        if self.selected_subprotocol.is_some() {
            return Err(WebSocketUpgradeError::SubprotocolAlreadySelected);
        }
        let header_value = HeaderValue::from_str(protocol)
            .map_err(|_| WebSocketUpgradeError::InvalidSubprotocol)?;
        if !is_http_token(protocol.as_bytes())
            || (require_client_offer
                && !self
                    .offered_subprotocols
                    .iter()
                    .any(|offered| offered.as_slice() == protocol.as_bytes()))
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

    /// Sets the maximum size, in bytes, of an incoming message.
    ///
    /// The same limit is applied to an individual frame. The default matches
    /// the underlying WebSocket implementation's default configuration.
    pub fn with_max_message_size(mut self, max_message_size: usize) -> Self {
        self.max_message_size = Some(max_message_size);
        self
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
            negotiated_extensions,
            selected_subprotocol,
            response_headers,
            offered_subprotocols: _,
            max_message_size,
        } = self;

        #[cfg(coverage)]
        let accept_key_source = if take_derived_accept_key_header_value_fault() {
            "\r\n"
        } else {
            accept_key.as_str()
        };
        #[cfg(not(coverage))]
        let accept_key_source = accept_key.as_str();
        let accept_key = HeaderValue::from_str(accept_key_source)
            .map_err(|_| WebSocketUpgradeError::InvalidAcceptKeyHeaderValue)?;

        let mut response = Response::new(body);
        *response.status_mut() = StatusCode::SWITCHING_PROTOCOLS;
        let headers = response.headers_mut();
        headers.insert(CONNECTION, HeaderValue::from_static("upgrade"));
        headers.insert(UPGRADE, HeaderValue::from_static("websocket"));
        headers.insert(SEC_WEBSOCKET_ACCEPT, accept_key);
        if let Some(extensions) = negotiated_extensions.as_ref() {
            headers.insert(SEC_WEBSOCKET_EXTENSIONS, extensions.clone());
        }
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
                let session = WebSocketSession::from_accepted_upgrade_with_options(
                    stream,
                    session_shutdown,
                    max_message_size.unwrap_or(usize::MAX),
                    negotiated_extensions,
                )
                .await
                .map_err(std::io::Error::other)?;
                handler(session).await.map_err(std::io::Error::other)
            })
            .map_err(|ConnectionUpgradeClosed| WebSocketUpgradeError::ConnectionClosed)?;
        Ok(response)
    }
}

#[expect(
    clippy::large_enum_variant,
    reason = "Boxing Tungstenite would allocate for every WebSocket session."
)]
enum WebSocketStreamKind {
    Tungstenite(WebSocketStream<TokioIo<Upgraded>>),
    // Extensions use Yawc; keep the common Tungstenite-only session compact.
    Yawc(Box<YawcWebSocket>),
}

/// A framed WebSocket session owned by the native HTTP/1.1 connection.
pub struct WebSocketSession {
    stream: WebSocketStreamKind,
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
            stream: WebSocketStreamKind::Tungstenite(
                WebSocketStream::from_raw_socket(stream, Role::Server, None).await,
            ),
            connection_upgrade,
            pending_close: None,
        }
    }

    /// Creates a framed session with a configured limit for complete messages.
    ///
    /// The limit applies to complete text and binary messages. A message that
    /// exceeds it is rejected with WebSocket close code 1009.
    pub async fn from_accepted_upgrade_with_max_message_size(
        stream: TokioIo<Upgraded>,
        connection_upgrade: ConnectionUpgrade,
        max_message_size: usize,
    ) -> Self {
        let mut config = WebSocketConfig::default();
        config.max_message_size = Some(max_message_size);
        config.max_frame_size = Some(max_message_size);
        Self {
            stream: WebSocketStreamKind::Tungstenite(
                WebSocketStream::from_raw_socket(stream, Role::Server, Some(config)).await,
            ),
            connection_upgrade,
            pending_close: None,
        }
    }

    async fn from_accepted_upgrade_with_options(
        stream: TokioIo<Upgraded>,
        connection_upgrade: ConnectionUpgrade,
        max_message_size: usize,
        negotiated_extensions: Option<HeaderValue>,
    ) -> Result<Self, WebSocketError> {
        let stream = match negotiated_extensions {
            Some(extensions) => {
                let extensions = extensions.to_str().map_err(|error| {
                    WebSocketError(TungsteniteError::Io(std::io::Error::new(
                        std::io::ErrorKind::InvalidData,
                        error,
                    )))
                })?;
                WebSocketStreamKind::Yawc(Box::new(
                    YawcWebSocket::from_stream_with_extensions(
                        YawcHttpStream::from(stream),
                        YawcRole::Server,
                        Some(extensions),
                        yawc_options(max_message_size),
                    )
                    .map_err(yawc_error)?,
                ))
            }
            None => {
                let mut config = WebSocketConfig::default();
                config.max_message_size = Some(max_message_size);
                config.max_frame_size = Some(max_message_size);
                WebSocketStreamKind::Tungstenite(
                    WebSocketStream::from_raw_socket(stream, Role::Server, Some(config)).await,
                )
            }
        };
        Ok(Self {
            stream,
            connection_upgrade,
            pending_close: None,
        })
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
            let message = self.receive_from_stream().await?;
            match message {
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
            Err(WebSocketError(TungsteniteError::Io(std::io::Error::new(
                std::io::ErrorKind::BrokenPipe,
                "coverage-injected WebSocket close-reply flush failure",
            ))))
        } else {
            self.flush_stream().await
        };
        #[cfg(not(coverage))]
        let flush_result = self.flush_stream().await;
        let frame = self.pending_close.take();
        flush_result?;
        Ok(frame.map(WebSocketMessage::Close))
    }

    async fn receive_from_stream(&mut self) -> Result<Option<WebSocketMessage>, WebSocketError> {
        match &mut self.stream {
            WebSocketStreamKind::Tungstenite(stream) => match stream.next().await.transpose() {
                Ok(message) => Ok(message),
                Err(TungsteniteError::Capacity(_)) => {
                    let close = WebSocketCloseFrame {
                        code: WebSocketCloseCode::Size,
                        reason: "message too big".into(),
                    };
                    let _ = stream.close(Some(close.clone())).await;
                    Ok(Some(WebSocketMessage::Close(Some(close))))
                }
                Err(error) => Err(WebSocketError(error)),
            },
            WebSocketStreamKind::Yawc(stream) => {
                #[cfg(coverage)]
                let next_frame = if take_yawc_unexpected_continuation_frame_fault() {
                    Ok(YawcFrame::continuation(Bytes::new()))
                } else if take_yawc_invalid_text_frame_fault() {
                    Ok(YawcFrame::text(Bytes::from_static(&[0xff])))
                } else if take_yawc_invalid_close_reason_fault() {
                    Ok(YawcFrame::close(YawcCloseCode::Normal, [0xff]))
                } else {
                    stream.next_frame().await
                };
                #[cfg(not(coverage))]
                let next_frame = stream.next_frame().await;
                match next_frame {
                    Ok(frame) => yawc_frame_to_message(frame).map(Some),
                    Err(yawc::WebSocketError::FrameTooLarge) => {
                        // Yawc queues a 1009 close and closes its read half;
                        // one poll flushes the queued close before returning
                        // ConnectionClosed. Preserve 1009 at the ASGI boundary.
                        let _ = stream.next_frame().await;
                        Ok(Some(WebSocketMessage::Close(Some(WebSocketCloseFrame {
                            code: WebSocketCloseCode::Size,
                            reason: "message too big".into(),
                        }))))
                    }
                    Err(error) => Err(yawc_error(error)),
                }
            }
        }
    }

    async fn flush_stream(&mut self) -> Result<(), WebSocketError> {
        match &mut self.stream {
            WebSocketStreamKind::Tungstenite(stream) => {
                stream.flush().await.map_err(WebSocketError)
            }
            WebSocketStreamKind::Yawc(stream) => match stream.next_frame().await {
                // Yawc queues the close reply when it reads the peer's close
                // frame, then flushes that reply while observing the closed
                // read state on the next read.
                Err(yawc::WebSocketError::ConnectionClosed) => Ok(()),
                Err(error) => Err(yawc_error(error)),
                Ok(_) => Err(WebSocketError(TungsteniteError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "received a WebSocket frame after the close frame",
                )))),
            },
        }
    }

    /// Sends a WebSocket data or control message with transport backpressure.
    ///
    /// # Errors
    ///
    /// Returns [`WebSocketError`] if the peer has closed or the transport
    /// fails while writing the frame.
    pub async fn send(&mut self, message: WebSocketMessage) -> Result<(), WebSocketError> {
        match &mut self.stream {
            WebSocketStreamKind::Tungstenite(stream) => {
                stream.send(message).await.map_err(WebSocketError)
            }
            WebSocketStreamKind::Yawc(stream) => stream
                .send(yawc_message_to_frame(message)?)
                .await
                .map_err(yawc_error),
        }
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
        match &mut self.stream {
            WebSocketStreamKind::Tungstenite(stream) => {
                stream.close(frame).await.map_err(WebSocketError)
            }
            WebSocketStreamKind::Yawc(stream) => stream
                .send(yawc_message_to_frame(WebSocketMessage::Close(frame))?)
                .await
                .map_err(yawc_error),
        }
    }

    /// Waits until the server starts graceful shutdown for this connection.
    pub async fn wait_for_shutdown(&mut self) {
        self.connection_upgrade.wait_for_shutdown().await;
    }
}

fn yawc_frame_to_message(frame: YawcFrame) -> Result<WebSocketMessage, WebSocketError> {
    let payload = frame.payload().clone();
    match frame.opcode() {
        YawcOpCode::Text => String::from_utf8(payload.to_vec())
            .map(|text| WebSocketMessage::Text(text.into()))
            .map_err(|error| {
                WebSocketError(TungsteniteError::Io(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    error,
                )))
            }),
        YawcOpCode::Binary => Ok(WebSocketMessage::Binary(payload)),
        YawcOpCode::Ping => Ok(WebSocketMessage::Ping(payload)),
        YawcOpCode::Pong => Ok(WebSocketMessage::Pong(payload)),
        YawcOpCode::Close => {
            let Some(code) = frame.close_code() else {
                return Ok(WebSocketMessage::Close(None));
            };
            let reason = frame
                .close_reason()
                .map_err(yawc_error)?
                .unwrap_or_default();
            Ok(WebSocketMessage::Close(Some(WebSocketCloseFrame {
                code: WebSocketCloseCode::from(u16::from(code)),
                reason: reason.into(),
            })))
        }
        YawcOpCode::Continuation => Err(WebSocketError(TungsteniteError::Io(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "WebSocket engine returned an incomplete continuation frame",
        )))),
    }
}

fn yawc_message_to_frame(message: WebSocketMessage) -> Result<YawcFrame, WebSocketError> {
    match message {
        WebSocketMessage::Text(text) => {
            Ok(YawcFrame::text(Bytes::copy_from_slice(text.as_bytes())))
        }
        WebSocketMessage::Binary(payload) => Ok(YawcFrame::binary(payload)),
        WebSocketMessage::Ping(payload) => Ok(YawcFrame::ping(payload)),
        WebSocketMessage::Pong(payload) => Ok(YawcFrame::pong(payload)),
        WebSocketMessage::Close(Some(frame)) => Ok(YawcFrame::close(
            YawcCloseCode::from(u16::from(frame.code)),
            frame.reason.as_bytes(),
        )),
        WebSocketMessage::Close(None) => {
            let mut frame = YawcFrame::close(YawcCloseCode::Status, b"");
            *frame.payload_mut() = Bytes::new();
            Ok(frame)
        }
        WebSocketMessage::Frame(_) => {
            Err(WebSocketError(TungsteniteError::Io(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "raw WebSocket frames cannot be sent on a compressed session",
            ))))
        }
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
#[cfg(coverage)]
static YAWC_UNEXPECTED_CONTINUATION_FRAME_FAULT_STATE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static YAWC_INVALID_TEXT_FRAME_FAULT_STATE: AtomicU8 = AtomicU8::new(0);
#[cfg(coverage)]
static YAWC_INVALID_CLOSE_REASON_FAULT_STATE: AtomicU8 = AtomicU8::new(0);

/// Arms the coverage-only Yawc continuation-frame adapter fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_yawc_unexpected_continuation_frame_fault() -> bool {
    YAWC_UNEXPECTED_CONTINUATION_FRAME_FAULT_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only Yawc continuation-frame adapter fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_yawc_unexpected_continuation_frame_fault() -> bool {
    YAWC_UNEXPECTED_CONTINUATION_FRAME_FAULT_STATE.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_yawc_unexpected_continuation_frame_fault() -> bool {
    YAWC_UNEXPECTED_CONTINUATION_FRAME_FAULT_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms the coverage-only invalid-text-frame conversion fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_yawc_invalid_text_frame_fault() -> bool {
    YAWC_INVALID_TEXT_FRAME_FAULT_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only invalid-text-frame conversion fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_yawc_invalid_text_frame_fault() -> bool {
    YAWC_INVALID_TEXT_FRAME_FAULT_STATE.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_yawc_invalid_text_frame_fault() -> bool {
    YAWC_INVALID_TEXT_FRAME_FAULT_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Arms the coverage-only invalid-close-reason conversion fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn arm_yawc_invalid_close_reason_fault() -> bool {
    YAWC_INVALID_CLOSE_REASON_FAULT_STATE
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only invalid-close-reason conversion fault.
#[cfg(coverage)]
#[doc(hidden)]
pub fn finish_yawc_invalid_close_reason_fault() -> bool {
    YAWC_INVALID_CLOSE_REASON_FAULT_STATE.swap(0, Ordering::AcqRel) == 2
}

#[cfg(coverage)]
fn take_yawc_invalid_close_reason_fault() -> bool {
    YAWC_INVALID_CLOSE_REASON_FAULT_STATE
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

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
    /// The derived `Sec-WebSocket-Accept` value could not become a header.
    InvalidAcceptKeyHeaderValue,
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
            Self::InvalidAcceptKeyHeaderValue => {
                formatter.write_str("failed to parse header value")
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

impl WebSocketError {
    /// Creates a deterministic transport error for coverage contracts.
    ///
    /// This helper is compiled only in coverage builds.
    #[cfg(coverage)]
    #[doc(hidden)]
    pub fn coverage_send_failure() -> Self {
        Self(TungsteniteError::Io(std::io::Error::other(
            "coverage-injected WebSocket session send failure",
        )))
    }
}

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
