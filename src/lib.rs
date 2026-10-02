use std::error::Error as StdError;
use std::future::Future;
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;
use std::task::{Context, Poll};

use bytes::{Buf, Bytes};
use futures_util::{SinkExt, StreamExt};
use http::header::{HeaderName, HeaderValue};
use http::{Request, Response, StatusCode, Version};
use http_body::{Body, Frame, SizeHint};
use http_body_util::combinators::UnsyncBoxBody;
use http_body_util::{BodyExt, Full};
use hyper::body::Incoming;
use hyper::service::service_fn;
use hyper_util::rt::{TokioExecutor, TokioIo};
use hyper_util::server::conn::auto;
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

use h3_quinn::quinn::{self, crypto::rustls::QuicServerConfig};

type BoxError = Box<dyn StdError + Send + Sync>;
type ResponseBody = UnsyncBoxBody<Bytes, BoxError>;
type WebSocketTasks = Arc<Mutex<tokio::task::JoinSet<()>>>;

struct AbortOnDrop<T> {
    handle: Option<tokio::task::JoinHandle<T>>,
}

impl<T> AbortOnDrop<T> {
    fn new(handle: tokio::task::JoinHandle<T>) -> Self {
        Self {
            handle: Some(handle),
        }
    }

    fn as_mut(&mut self) -> &mut tokio::task::JoinHandle<T> {
        self.handle.as_mut().expect("task handle already taken")
    }

    fn take(&mut self) -> tokio::task::JoinHandle<T> {
        self.handle.take().expect("task handle already taken")
    }
}

impl<T> Drop for AbortOnDrop<T> {
    fn drop(&mut self) {
        if let Some(handle) = self.handle.take() {
            handle.abort();
        }
    }
}

struct ResponseStart {
    status: u16,
    headers: Vec<(Bytes, Bytes)>,
}

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
        message.set_item("type", "http.request")?;
        message.set_item("body", PyBytes::new(py, &request.body))?;
        message.set_item("more_body", request.more_body)?;
    } else {
        request_disconnected.store(true, Ordering::Release);
        message.set_item("type", "http.disconnect")?;
    }
    Ok(message.into_any().unbind())
}

#[pyclass]
struct PythonTaskStarter {
    awaitable: Py<PyAny>,
    task_sender: Option<oneshot::Sender<Py<PyAny>>>,
    result_sender: Option<oneshot::Sender<PyResult<Py<PyAny>>>>,
}

#[pymethods]
impl PythonTaskStarter {
    fn __call__(&mut self) -> PyResult<()> {
        Python::attach(|py| {
            let asyncio = py.import("asyncio")?;
            let task = asyncio.call_method1("ensure_future", (self.awaitable.bind(py),))?;
            let completion = PyTaskCompletion {
                sender: self.result_sender.take(),
            };
            task.call_method1("add_done_callback", (completion,))?;
            if let Some(sender) = self.task_sender.take() {
                if let Err(task) = sender.send(task.unbind()) {
                    let _ = task.bind(py).call_method0("cancel");
                }
            } else {
                let _ = task.call_method0("cancel");
            }
            Ok(())
        })
    }
}

#[pyclass]
struct PyTaskCompletion {
    sender: Option<oneshot::Sender<PyResult<Py<PyAny>>>>,
}

#[pymethods]
impl PyTaskCompletion {
    fn __call__(&mut self, task: &Bound<'_, PyAny>) -> PyResult<()> {
        let result = task.call_method0("result").map(Bound::unbind);
        if let Some(sender) = self.sender.take() {
            let _ = sender.send(result);
        }
        Ok(())
    }
}

struct PythonTaskFuture {
    task_receiver: oneshot::Receiver<Py<PyAny>>,
    result_receiver: oneshot::Receiver<PyResult<Py<PyAny>>>,
    task: Option<Py<PyAny>>,
    locals: TaskLocals,
    completed: bool,
}

impl Future for PythonTaskFuture {
    type Output = PyResult<Py<PyAny>>;

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        if this.task.is_none() {
            match Pin::new(&mut this.task_receiver).poll(context) {
                Poll::Ready(Ok(task)) => this.task = Some(task),
                Poll::Ready(Err(_)) => {
                    this.completed = true;
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
        if let Some(task) = self.task.take() {
            cancel_python_task(&task, &self.locals);
        }
    }
}

fn cancel_python_task(task: &Py<PyAny>, locals: &TaskLocals) {
    Python::attach(|py| {
        let Ok(cancel) = task.bind(py).getattr("cancel") else {
            return;
        };
        let event_loop = locals.event_loop(py);
        let kwargs = PyDict::new(py);
        if kwargs.set_item("context", locals.context(py)).is_err() {
            return;
        }
        let _ = event_loop.call_method("call_soon_threadsafe", (cancel,), Some(&kwargs));
    });
}

fn python_task_future(
    py: Python<'_>,
    locals: &TaskLocals,
    awaitable: Bound<'_, PyAny>,
) -> PyResult<PythonTaskFuture> {
    let (task_sender, task_receiver) = oneshot::channel();
    let (result_sender, result_receiver) = oneshot::channel();
    let starter = Py::new(
        py,
        PythonTaskStarter {
            awaitable: awaitable.unbind(),
            task_sender: Some(task_sender),
            result_sender: Some(result_sender),
        },
    )?;
    let event_loop = locals.event_loop(py);
    let kwargs = PyDict::new(py);
    kwargs.set_item("context", locals.context(py))?;
    event_loop.call_method("call_soon_threadsafe", (starter,), Some(&kwargs))?;
    Ok(PythonTaskFuture {
        task_receiver,
        result_receiver,
        task: None,
        locals: locals.clone(),
        completed: false,
    })
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
    request_disconnected: Arc<AtomicBool>,
    response_started: AtomicBool,
    start: mpsc::Sender<ResponseStart>,
    body: mpsc::Sender<BodyChunk>,
}

#[pymethods]
impl AsgiIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        if slf.request_disconnected.load(Ordering::Acquire) {
            return Ok(
                make_http_request_message(py, None, &slf.request_disconnected)?.into_bound(py),
            );
        }

        let immediate = match slf.request_messages.try_lock() {
            Ok(mut requests) => match requests.try_recv() {
                Ok(request) => Some(Some(request)),
                Err(TryRecvError::Disconnected) => Some(None),
                Err(TryRecvError::Empty) => None,
            },
            Err(_) => None,
        };
        if let Some(request) = immediate {
            return Ok(
                make_http_request_message(py, request, &slf.request_disconnected)?.into_bound(py),
            );
        }
        if *slf.connection_closed.borrow() {
            return Ok(
                make_http_request_message(py, None, &slf.request_disconnected)?.into_bound(py),
            );
        }

        let request_messages = Arc::clone(&slf.request_messages);
        let mut connection_closed = slf.connection_closed.clone();
        let request_disconnected = Arc::clone(&slf.request_disconnected);
        pyo3_async_runtimes::tokio::future_into_py(py, async move {
            let request = loop {
                if request_disconnected.load(Ordering::Acquire) {
                    break None;
                }
                tokio::select! {
                    biased;
                    message = async { request_messages.lock().await.recv().await } => break message,
                    changed = connection_closed.changed() => {
                        if changed.is_err() || *connection_closed.borrow() {
                            request_disconnected.store(true, Ordering::Release);
                            break None;
                        }
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
        let event_type: String = message
            .get_item("type")?
            .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?
            .extract()?;
        match event_type.as_str() {
            "http.response.start" => {
                if *slf.connection_closed.borrow()
                    || slf.request_disconnected.load(Ordering::Acquire)
                {
                    return Err(PyOSError::new_err(
                        "client disconnected before response start",
                    ));
                }
                let status: u16 = message
                    .get_item("status")?
                    .ok_or_else(|| PyValueError::new_err("response.start is missing 'status'"))?
                    .extract()?;
                let headers = extract_headers(message.get_item("headers")?)?;
                if slf.response_started.swap(true, Ordering::AcqRel) {
                    return Err(PyValueError::new_err(
                        "ASGI app sent response.start more than once",
                    ));
                }
                if let Err(error) = slf.start.try_send(ResponseStart { status, headers }) {
                    slf.response_started.store(false, Ordering::Release);
                    return Err(PyOSError::new_err(format!(
                        "server response channel closed: {error}"
                    )));
                }
                Ok(py.None().into_bound(py))
            }
            "http.response.body" => {
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
                let body = match message.get_item("body")? {
                    Some(value) => Bytes::from(value.extract::<Vec<u8>>()?),
                    None => Bytes::new(),
                };
                let more_body = message
                    .get_item("more_body")?
                    .map(|value| value.extract::<bool>())
                    .transpose()?
                    .unwrap_or(false);
                let chunk = BodyChunk { body, more_body };
                match slf.body.try_send(chunk) {
                    Ok(()) => Ok(py.None().into_bound(py)),
                    Err(TrySendError::Closed(_)) => {
                        Err(PyOSError::new_err("server response body channel closed"))
                    }
                    Err(TrySendError::Full(chunk)) => {
                        let sender = slf.body.clone();
                        pyo3_async_runtimes::tokio::future_into_py(py, async move {
                            sender.send(chunk).await.map_err(|_| {
                                PyOSError::new_err("server response body channel closed")
                            })?;
                            Python::attach(|py| Ok(py.None()))
                        })
                    }
                }
            }
            other => {
                return Err(PyValueError::new_err(format!(
                    "unsupported ASGI event in HTTP prototype: {other}"
                )));
            }
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
}

#[pymethods]
impl WebSocketIo {
    fn receive<'py>(slf: PyRef<'py, Self>, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let connect = !slf.connect_delivered.swap(true, Ordering::AcqRel);
        let incoming = Arc::clone(&slf.incoming);
        let mut connection_closed = slf.connection_closed.clone();
        let state = Arc::clone(&slf.state);
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
                    message = async { incoming.lock().await.recv().await } => message,
                    changed = connection_closed.changed() => {
                        let _ = changed;
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
                    message.set_item("type", "websocket.connect")?;
                } else {
                    match incoming_message {
                        Some(WebSocketIncoming::Text(text)) => {
                            message.set_item("type", "websocket.receive")?;
                            message.set_item("text", text)?;
                        }
                        Some(WebSocketIncoming::Bytes(data)) => {
                            message.set_item("type", "websocket.receive")?;
                            message.set_item("bytes", PyBytes::new(py, &data))?;
                        }
                        Some(WebSocketIncoming::Disconnect { code, reason }) => {
                            message.set_item("type", "websocket.disconnect")?;
                            message.set_item("code", code)?;
                            message.set_item("reason", reason)?;
                        }
                        None => {
                            state.store(3, Ordering::Release);
                            message.set_item("type", "websocket.disconnect")?;
                            message.set_item("code", 1005)?;
                            message.set_item("reason", "")?;
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
        let event_type: String = message
            .get_item("type")?
            .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?
            .extract()?;
        match event_type.as_str() {
            "websocket.accept" => {
                if slf
                    .state
                    .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
                    .is_err()
                {
                    return Err(PyValueError::new_err(
                        "websocket.accept must be the first WebSocket response",
                    ));
                }
                let subprotocol = message
                    .get_item("subprotocol")?
                    .map(|value| value.extract::<Option<String>>())
                    .transpose()?
                    .flatten();
                let headers = extract_headers(message.get_item("headers")?)?;
                let handshake = slf
                    .handshake
                    .lock()
                    .map_err(|_| PyOSError::new_err("WebSocket handshake state poisoned"))?
                    .take()
                    .ok_or_else(|| PyOSError::new_err("WebSocket handshake already completed"))?;
                handshake
                    .send(WebSocketHandshake::Accept {
                        subprotocol,
                        headers,
                    })
                    .map_err(|_| PyOSError::new_err("WebSocket handshake channel closed"))?;
                Ok(py.None().into_bound(py))
            }
            "websocket.close" => {
                let code = message
                    .get_item("code")?
                    .map(|value| value.extract::<u16>())
                    .transpose()?
                    .unwrap_or(1000);
                let reason = message
                    .get_item("reason")?
                    .map(|value| value.extract::<String>())
                    .transpose()?
                    .unwrap_or_default();
                match slf
                    .state
                    .compare_exchange(0, 3, Ordering::AcqRel, Ordering::Acquire)
                {
                    Ok(_) => {
                        let handshake = slf
                            .handshake
                            .lock()
                            .map_err(|_| PyOSError::new_err("WebSocket handshake state poisoned"))?
                            .take()
                            .ok_or_else(|| {
                                PyOSError::new_err("WebSocket handshake already completed")
                            })?;
                        handshake.send(WebSocketHandshake::Reject).map_err(|_| {
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
                        )
                    }
                    _ => Err(PyOSError::new_err("WebSocket connection is closed")),
                }
            }
            "websocket.send" => {
                match slf.state.load(Ordering::Acquire) {
                    1 => {}
                    0 => {
                        return Err(PyValueError::new_err(
                            "websocket.send requires an accepted WebSocket",
                        ));
                    }
                    _ => return Err(PyOSError::new_err("WebSocket connection is closed")),
                }
                let text = message
                    .get_item("text")?
                    .map(|value| value.extract::<Option<String>>())
                    .transpose()?
                    .flatten();
                let data = message
                    .get_item("bytes")?
                    .map(|value| value.extract::<Option<Vec<u8>>>())
                    .transpose()?
                    .flatten();
                let outgoing = match (text, data) {
                    (Some(text), None) => WebSocketOutgoing::Text(text),
                    (None, Some(data)) => WebSocketOutgoing::Bytes(Bytes::from(data)),
                    _ => {
                        return Err(PyValueError::new_err(
                            "websocket.send must contain exactly one of 'text' or 'bytes'",
                        ));
                    }
                };
                queue_websocket_message(py, slf.outgoing.clone(), outgoing)
            }
            other => Err(PyValueError::new_err(format!(
                "unsupported ASGI WebSocket event: {other}"
            ))),
        }
    }
}

fn queue_websocket_message<'py>(
    py: Python<'py>,
    sender: mpsc::Sender<WebSocketOutgoing>,
    message: WebSocketOutgoing,
) -> PyResult<Bound<'py, PyAny>> {
    match sender.try_send(message) {
        Ok(()) => Ok(py.None().into_bound(py)),
        Err(TrySendError::Closed(_)) => Err(PyOSError::new_err("WebSocket connection is closed")),
        Err(TrySendError::Full(message)) => {
            pyo3_async_runtimes::tokio::future_into_py(py, async move {
                sender
                    .send(message)
                    .await
                    .map_err(|_| PyOSError::new_err("WebSocket connection is closed"))?;
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
            let request = requests
                .lock()
                .await
                .recv()
                .await
                .ok_or_else(|| PyOSError::new_err("ASGI lifespan channel closed"))?;
            Python::attach(|py| -> PyResult<Py<PyAny>> {
                let message = PyDict::new(py);
                match request {
                    LifespanMessage::Startup => {
                        message.set_item("type", "lifespan.startup")?;
                    }
                    LifespanMessage::Shutdown => {
                        message.set_item("type", "lifespan.shutdown")?;
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
        let event_type: String = message
            .get_item("type")?
            .ok_or_else(|| PyValueError::new_err("ASGI message is missing 'type'"))?
            .extract()?;
        let event = match event_type.as_str() {
            "lifespan.startup.complete" => LifespanEvent::StartupComplete,
            "lifespan.startup.failed" => LifespanEvent::StartupFailed(
                message
                    .get_item("message")?
                    .map(|value| value.extract::<String>())
                    .transpose()?
                    .unwrap_or_default(),
            ),
            "lifespan.shutdown.complete" => LifespanEvent::ShutdownComplete,
            "lifespan.shutdown.failed" => LifespanEvent::ShutdownFailed(
                message
                    .get_item("message")?
                    .map(|value| value.extract::<String>())
                    .transpose()?
                    .unwrap_or_default(),
            ),
            other => {
                return Err(PyValueError::new_err(format!(
                    "unsupported ASGI lifespan event: {other}"
                )));
            }
        };
        slf.events.try_send(event).map_err(|error| {
            PyOSError::new_err(format!("ASGI lifespan channel closed: {error}"))
        })?;
        Ok(py.None().into_bound(py))
    }
}

struct LifespanRuntime {
    state: Option<Arc<Py<PyDict>>>,
    requests: Option<mpsc::Sender<LifespanMessage>>,
    events: Option<mpsc::Receiver<LifespanEvent>>,
    app_task: Option<tokio::task::JoinHandle<PyResult<Py<PyAny>>>>,
}

impl Drop for LifespanRuntime {
    fn drop(&mut self) {
        if let Some(app_task) = self.app_task.take() {
            app_task.abort();
        }
    }
}

impl LifespanRuntime {
    async fn start(
        app: Arc<Py<PyAny>>,
        invoke: Arc<Py<PyAny>>,
        locals: TaskLocals,
    ) -> PyResult<Self> {
        let (request_tx, request_rx) = mpsc::channel(1);
        let (event_tx, mut event_rx) = mpsc::channel(1);
        let state = Python::attach(|py| PyDict::new(py).unbind());
        let scope_state = Python::attach(|py| state.clone_ref(py));
        let app_future = Python::attach(move |py| {
            let io = Py::new(
                py,
                LifespanIo {
                    requests: Arc::new(Mutex::new(request_rx)),
                    events: event_tx,
                },
            )?;
            let scope = PyDict::new(py);
            let asgi = PyDict::new(py);
            asgi.set_item("version", "3.0")?;
            asgi.set_item("spec_version", "2.0")?;
            scope.set_item("type", "lifespan")?;
            scope.set_item("asgi", asgi)?;
            scope.set_item("state", scope_state.bind(py))?;
            let awaitable = invoke.bind(py).call1((app.bind(py), scope, io))?;
            python_task_future(py, &locals, awaitable)
        })?;
        let mut app_task = AbortOnDrop::new(tokio::spawn(app_future));
        request_tx
            .send(LifespanMessage::Startup)
            .await
            .map_err(|_| PyOSError::new_err("could not send ASGI lifespan startup"))?;

        tokio::select! {
            biased;
            event = event_rx.recv() => match event {
                Some(LifespanEvent::StartupComplete) => Ok(Self {
                    state: Some(Arc::new(state)),
                    requests: Some(request_tx),
                    events: Some(event_rx),
                    app_task: Some(app_task.take()),
                }),
                Some(LifespanEvent::StartupFailed(message)) => {
                    app_task.take().abort();
                    Err(PyRuntimeError::new_err(if message.is_empty() {
                        "ASGI lifespan startup failed".to_string()
                    } else {
                        message
                    }))
                }
                Some(_) => {
                    app_task.take().abort();
                    Err(PyRuntimeError::new_err("unexpected ASGI lifespan event during startup"))
                }
                None => {
                    let result = app_task.take().await;
                    match result {
                        Ok(Ok(_)) => {
                            eprintln!("uvicorn-rs: ASGI app does not support lifespan");
                            Ok(Self {
                                state: None,
                                requests: None,
                                events: None,
                                app_task: None,
                            })
                        }
                        Ok(Err(error)) => {
                            Python::attach(|py| error.print(py));
                            eprintln!("uvicorn-rs: ASGI app does not support lifespan");
                            Ok(Self {
                                state: None,
                                requests: None,
                                events: None,
                                app_task: None,
                            })
                        }
                        Err(error) => Err(PyRuntimeError::new_err(format!(
                            "ASGI lifespan task failed: {error}"
                        ))),
                    }
                },
            },
            result = app_task.as_mut() => {
                app_task.take();
                match result {
                    Ok(Ok(_)) => {
                        eprintln!("uvicorn-rs: ASGI app does not support lifespan");
                        Ok(Self {
                            state: None,
                            requests: None,
                            events: None,
                            app_task: None,
                        })
                    }
                    Ok(Err(error)) => {
                        Python::attach(|py| error.print(py));
                        eprintln!("uvicorn-rs: ASGI app does not support lifespan");
                        Ok(Self {
                            state: None,
                            requests: None,
                            events: None,
                            app_task: None,
                        })
                    }
                    Err(error) => Err(PyRuntimeError::new_err(format!("ASGI lifespan task failed: {error}"))),
                }
            }
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
        requests
            .send(LifespanMessage::Shutdown)
            .await
            .map_err(|_| PyRuntimeError::new_err("could not send ASGI lifespan shutdown"))?;
        loop {
            tokio::select! {
                biased;
                event = events.recv() => match event {
                    Some(LifespanEvent::ShutdownComplete) => break,
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
                result = app_task => {
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
        }
        let result = self
            .app_task
            .as_mut()
            .expect("lifespan app task exists")
            .await;
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
    let items = value.extract::<Vec<(Vec<u8>, Vec<u8>)>>()?;
    Ok(items
        .into_iter()
        .map(|(name, value)| (Bytes::from(name), Bytes::from(value)))
        .collect())
}

struct AsgiBody {
    receiver: mpsc::Receiver<BodyChunk>,
    app_task: Option<tokio::task::JoinHandle<PyResult<Py<PyAny>>>>,
    final_body_seen: bool,
    stream_ended: bool,
}

impl Drop for AsgiBody {
    fn drop(&mut self) {
        if let Some(task) = self.app_task.take() {
            task.abort();
        }
    }
}

struct ConnectionIo<I> {
    io: I,
    closed: watch::Sender<bool>,
}

async fn pump_http_request_body(
    mut body: Incoming,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: watch::Receiver<bool>,
) {
    loop {
        if *connection_closed.borrow() {
            return;
        }
        let frame = tokio::select! {
            biased;
            _ = wait_for_connection_close(&mut connection_closed) => return,
            _ = sender.closed() => {
                while body.frame().await.is_some() {}
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
                            _ = wait_for_connection_close(&mut connection_closed) => return,
                            result = sender.send(message) => {
                                if result.is_err() {
                                    while body.frame().await.is_some() {}
                                    return;
                                }
                            }
                        }
                    }
                }
            }
            Some(Err(_)) => {
                let _ = sender
                    .send(RequestMessage {
                        body: Bytes::new(),
                        more_body: false,
                        disconnected: true,
                    })
                    .await;
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
                    _ = wait_for_connection_close(&mut connection_closed) => return,
                    result = sender.send(message) => {
                        if result.is_err() {
                            return;
                        }
                    }
                }
                tokio::select! {
                    _ = wait_for_connection_close(&mut connection_closed) => return,
                    _ = sender.closed() => return,
                }
            }
        }
    }
}

async fn wait_for_connection_close(connection_closed: &mut watch::Receiver<bool>) {
    if *connection_closed.borrow() {
        return;
    }
    let _ = connection_closed.changed().await;
}

impl<I: AsyncRead + Unpin> AsyncRead for ConnectionIo<I> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buffer: &mut tokio::io::ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        match Pin::new(&mut this.io).poll_read(cx, buffer) {
            Poll::Ready(Ok(())) if buffer.filled().is_empty() => {
                this.closed.send_replace(true);
                Poll::Ready(Ok(()))
            }
            Poll::Ready(Err(error)) => {
                this.closed.send_replace(true);
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
        let this = self.get_mut();
        match Pin::new(&mut this.io).poll_write(cx, buffer) {
            Poll::Ready(Err(error)) => {
                this.closed.send_replace(true);
                Poll::Ready(Err(error))
            }
            result => result,
        }
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().io).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().io).poll_shutdown(cx)
    }
}

impl AsgiBody {
    fn poll_app_task(
        &mut self,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Bytes>, BoxError>>> {
        let task_result = match self.app_task.as_mut() {
            Some(task) => match Pin::new(task).poll(cx) {
                Poll::Ready(result) => result,
                Poll::Pending => return Poll::Pending,
            },
            None => return Poll::Ready(None),
        };
        self.app_task = None;

        match task_result {
            Ok(Ok(_)) if self.final_body_seen => Poll::Ready(None),
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
        if this.stream_ended {
            return this.poll_app_task(cx);
        }

        match this.receiver.poll_recv(cx) {
            Poll::Ready(Some(chunk)) => {
                if !chunk.more_body {
                    this.final_body_seen = true;
                    this.stream_ended = true;
                }
                Poll::Ready(Some(Ok(Frame::data(chunk.body))))
            }
            Poll::Ready(None) => {
                this.stream_ended = true;
                this.poll_app_task(cx)
            }
            Poll::Pending => Poll::Pending,
        }
    }

    fn is_end_stream(&self) -> bool {
        self.stream_ended && self.app_task.is_none()
    }

    fn size_hint(&self) -> SizeHint {
        SizeHint::new()
    }
}

#[pyfunction]
#[pyo3(signature = (app, invoke, host, port, certfile, keyfile, graceful_timeout, control))]
fn serve<'py>(
    py: Python<'py>,
    app: Py<PyAny>,
    invoke: Py<PyAny>,
    host: String,
    port: u16,
    certfile: Option<String>,
    keyfile: Option<String>,
    graceful_timeout: u64,
    control: PyRef<'py, ServerControl>,
) -> PyResult<Bound<'py, PyAny>> {
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
    let locals = pyo3_async_runtimes::tokio::get_current_locals(py)?;
    let cancellation = control.cancellation.clone();
    let cancel_on_drop = CancelOnDrop(cancellation.clone());
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        let _cancel_on_drop = cancel_on_drop;
        serve_forever(
            app,
            invoke,
            locals,
            host,
            port,
            tcp_tls,
            quic_config,
            cancellation,
            std::time::Duration::from_secs(graceful_timeout),
        )
        .await
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
    let quic_config =
        quinn::ServerConfig::with_crypto(Arc::new(QuicServerConfig::try_from(quic_tls).map_err(
            |error| PyValueError::new_err(format!("invalid HTTP/3 TLS identity: {error}")),
        )?));

    Ok((TlsAcceptor::from(Arc::new(tcp_tls)), quic_config))
}

async fn serve_forever(
    app: Py<PyAny>,
    invoke: Py<PyAny>,
    locals: TaskLocals,
    host: String,
    port: u16,
    tcp_tls: Option<TlsAcceptor>,
    quic_config: Option<quinn::ServerConfig>,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
) -> PyResult<()> {
    let listener = TcpListener::bind((host.as_str(), port))
        .await
        .map_err(|error| PyOSError::new_err(format!("could not bind {host}:{port}: {error}")))?;
    let server_addr = listener.local_addr().map_err(|error| {
        PyOSError::new_err(format!("could not inspect bound listener: {error}"))
    })?;
    let app = Arc::new(app);
    let invoke = Arc::new(invoke);
    let endpoint = if let Some(quic_config) = quic_config {
        Some(
            quinn::Endpoint::server(quic_config, server_addr).map_err(|error| {
                PyOSError::new_err(format!("could not bind HTTP/3 endpoint: {error}"))
            })?,
        )
    } else {
        None
    };

    let mut lifespan =
        LifespanRuntime::start(Arc::clone(&app), Arc::clone(&invoke), locals.clone()).await?;
    let state = lifespan.state.clone();
    let websocket_tasks: WebSocketTasks = Arc::new(Mutex::new(tokio::task::JoinSet::new()));
    let http3_task = endpoint.map(|endpoint| {
        tokio::spawn(serve_http3(
            endpoint,
            Arc::clone(&app),
            Arc::clone(&invoke),
            locals.clone(),
            server_addr,
            state.clone(),
            cancellation.clone(),
            graceful_timeout,
        ))
    });

    let mut connection_tasks = tokio::task::JoinSet::new();
    let mut accept_error = None;
    loop {
        tokio::select! {
            biased;
            _ = cancellation.cancelled() => break,
            Some(result) = connection_tasks.join_next(), if !connection_tasks.is_empty() => {
                if let Err(error) = result {
                    eprintln!("uvicorn-rs: connection task failed: {error}");
                }
            }
            accepted = listener.accept() => match accepted {
                Ok((stream, peer_addr)) => {
                    connection_tasks.spawn(serve_connection(
                        stream,
                        peer_addr,
                        server_addr,
                        Arc::clone(&app),
                        Arc::clone(&invoke),
                        locals.clone(),
                        tcp_tls.clone(),
                        state.clone(),
                        Arc::clone(&websocket_tasks),
                        cancellation.clone(),
                        graceful_timeout,
                    ));
                }
                Err(error) => {
                    accept_error = Some(PyOSError::new_err(format!("accept failed: {error}")));
                    break;
                }
            }
        }
    }

    cancellation.cancel();
    let shutdown_deadline = tokio::time::Instant::now() + graceful_timeout;
    if let Some(mut http3_task) = http3_task {
        if let Err(error) = tokio::time::timeout(
            shutdown_deadline.saturating_duration_since(tokio::time::Instant::now()),
            &mut http3_task,
        )
        .await
        {
            eprintln!("uvicorn-rs: HTTP/3 shutdown exceeded grace period: {error}");
            http3_task.abort();
            let _ = http3_task.await;
        }
    }
    if tokio::time::timeout(
        shutdown_deadline.saturating_duration_since(tokio::time::Instant::now()),
        async {
            while let Some(result) = connection_tasks.join_next().await {
                if let Err(error) = result {
                    eprintln!("uvicorn-rs: connection task failed during shutdown: {error}");
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
    let mut websocket_tasks = websocket_tasks.lock().await;
    if tokio::time::timeout(
        shutdown_deadline.saturating_duration_since(tokio::time::Instant::now()),
        async {
            while let Some(result) = websocket_tasks.join_next().await {
                if let Err(error) = result {
                    eprintln!("uvicorn-rs: WebSocket task failed during shutdown: {error}");
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
    // Lifespan shutdown is a separate ASGI phase. The connection drain may
    // consume its full grace period while cancelling outstanding applications;
    // still give the lifespan task its own bounded window to finish.
    let shutdown_result = match tokio::time::timeout(graceful_timeout, lifespan.shutdown())
    .await
    {
        Ok(result) => result,
        Err(_) => Err(PyRuntimeError::new_err(
            "ASGI lifespan shutdown exceeded the graceful timeout",
        )),
    };
    if let Some(error) = accept_error {
        return Err(error);
    }
    shutdown_result
}

async fn serve_connection(
    stream: TcpStream,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    tcp_tls: Option<TlsAcceptor>,
    state: Option<Arc<Py<PyDict>>>,
    websocket_tasks: WebSocketTasks,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let scheme = if tcp_tls.is_some() { "https" } else { "http" };
    let (closed_tx, closed_rx) = watch::channel(false);
    let stream = ConnectionIo {
        io: stream,
        closed: closed_tx.clone(),
    };
    let result = if let Some(tls) = tcp_tls {
        let stream = tokio::select! {
            biased;
            _ = cancellation.cancelled() => return Ok(()),
            result = tls.accept(stream) => result?,
        };
        serve_hyper_connection(
            stream,
            peer_addr,
            server_addr,
            app,
            invoke,
            locals,
            scheme,
            closed_rx,
            state,
            websocket_tasks,
            cancellation,
            graceful_timeout,
        )
        .await
    } else {
        serve_hyper_connection(
            stream,
            peer_addr,
            server_addr,
            app,
            invoke,
            locals,
            scheme,
            closed_rx,
            state,
            websocket_tasks,
            cancellation,
            graceful_timeout,
        )
        .await
    };
    result
}

async fn serve_hyper_connection<I>(
    io: I,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
    state: Option<Arc<Py<PyDict>>>,
    websocket_tasks: WebSocketTasks,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>>
where
    I: AsyncRead + AsyncWrite + Unpin + Send + 'static,
{
    let service_cancellation = cancellation.clone();
    let service = service_fn(move |request: Request<Incoming>| {
        let app = Arc::clone(&app);
        let invoke = Arc::clone(&invoke);
        let locals = locals.clone();
        let connection_closed = connection_closed.clone();
        let state = state.clone();
        let websocket_tasks = Arc::clone(&websocket_tasks);
        let cancellation = service_cancellation.clone();
        async move {
            let response = if is_websocket_upgrade(&request) {
                handle_websocket_request(
                    request,
                    peer_addr,
                    server_addr,
                    app,
                    invoke,
                    locals,
                    scheme,
                    connection_closed,
                    state,
                    websocket_tasks,
                    cancellation,
                )
                .await
            } else {
                handle_request(
                    request,
                    peer_addr,
                    server_addr,
                    app,
                    invoke,
                    locals,
                    scheme,
                    connection_closed,
                    state,
                )
                .await
            };
            Ok::<_, std::convert::Infallible>(response)
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
            if let Ok(result) = tokio::time::timeout(graceful_timeout, &mut connection).await {
                result?;
            }
        }
    }
    Ok(())
}

async fn serve_http3(
    endpoint: quinn::Endpoint,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    server_addr: SocketAddr,
    state: Option<Arc<Py<PyDict>>>,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
) -> Result<(), BoxError> {
    let mut connections = tokio::task::JoinSet::new();
    loop {
        tokio::select! {
            biased;
            _ = cancellation.cancelled() => break,
            Some(result) = connections.join_next(), if !connections.is_empty() => {
                if let Err(error) = result {
                    eprintln!("uvicorn-rs: HTTP/3 connection task failed: {error}");
                }
            }
            incoming = endpoint.accept() => {
                let Some(incoming) = incoming else { break; };
                let app = Arc::clone(&app);
                let invoke = Arc::clone(&invoke);
                let locals = locals.clone();
                let state = state.clone();
                let cancellation = cancellation.clone();
                connections.spawn(async move {
                    match incoming.await {
                        Ok(connection) => {
                            let peer_addr = connection.remote_address();
                            if let Err(error) = serve_http3_connection(
                                connection,
                                peer_addr,
                                server_addr,
                                app,
                                invoke,
                                locals,
                                state,
                                cancellation,
                                graceful_timeout,
                            ).await {
                                eprintln!("uvicorn-rs: HTTP/3 connection from {peer_addr} failed: {error}");
                            }
                        }
                        Err(error) => eprintln!("uvicorn-rs: HTTP/3 handshake failed: {error}"),
                    }
                });
            }
        }
    }

    endpoint.close(quinn::VarInt::from_u32(0), b"server shutdown");
    if tokio::time::timeout(graceful_timeout, async {
        while let Some(result) = connections.join_next().await {
            if let Err(error) = result {
                eprintln!("uvicorn-rs: HTTP/3 connection task failed during shutdown: {error}");
            }
        }
    })
    .await
    .is_err()
    {
        connections.abort_all();
        while connections.join_next().await.is_some() {}
    }
    let _ = tokio::time::timeout(graceful_timeout, endpoint.wait_idle()).await;
    Ok(())
}

async fn serve_http3_connection(
    connection: quinn::Connection,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    state: Option<Arc<Py<PyDict>>>,
    cancellation: CancellationToken,
    graceful_timeout: std::time::Duration,
) -> Result<(), BoxError> {
    let (closed_tx, closed_rx) = watch::channel(false);
    let close_monitor = connection.clone();
    tokio::spawn(async move {
        close_monitor.closed().await;
        closed_tx.send_replace(true);
    });
    let mut h3_connection =
        h3::server::Connection::new(h3_quinn::Connection::new(connection)).await?;
    let mut requests = tokio::task::JoinSet::new();
    loop {
        let accepted = tokio::select! {
            biased;
            _ = cancellation.cancelled() => {
                h3_connection.shutdown(0).await?;
                break;
            }
            result = h3_connection.accept() => result?,
        };
        let Some(resolver) = accepted else {
            break;
        };
        let app = Arc::clone(&app);
        let invoke = Arc::clone(&invoke);
        let locals = locals.clone();
        let state = state.clone();
        let connection_closed = closed_rx.clone();
        requests.spawn(async move {
            if let Err(error) = handle_http3_request(
                resolver,
                peer_addr,
                server_addr,
                app,
                invoke,
                locals,
                connection_closed,
                state,
            )
            .await
            {
                eprintln!("uvicorn-rs: HTTP/3 request from {peer_addr} failed: {error}");
            }
        });
    }
    if tokio::time::timeout(graceful_timeout, async {
        while let Some(result) = requests.join_next().await {
            if let Err(error) = result {
                eprintln!("uvicorn-rs: HTTP/3 request task failed: {error}");
            }
        }
    })
    .await
    .is_err()
    {
        requests.abort_all();
        while requests.join_next().await.is_some() {}
    }
    Ok(())
}

async fn handle_http3_request(
    resolver: h3::server::RequestResolver<h3_quinn::Connection, Bytes>,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    connection_closed: watch::Receiver<bool>,
    state: Option<Arc<Py<PyDict>>>,
) -> Result<(), BoxError> {
    let (request, stream) = resolver.resolve_request().await?;
    let (parts, ()) = request.into_parts();
    let (mut send_stream, receive_stream) = stream.split();
    let (request_tx, request_rx) = mpsc::channel(1);
    tokio::spawn(pump_h3_request_body(
        receive_stream,
        request_tx,
        connection_closed.clone(),
    ));

    let response = match handle_request_parts(
        parts,
        request_rx,
        None,
        connection_closed,
        peer_addr,
        server_addr,
        app,
        invoke,
        locals,
        "https",
        state,
    )
    .await
    {
        Ok(response) => response,
        Err(error) => {
            eprintln!("uvicorn-rs: HTTP/3 ASGI request failed: {error}");
            response(
                StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
                full_body(Bytes::from_static(b"Internal Server Error")),
                Vec::new(),
            )
        }
    };

    let (response_parts, mut body) = response.into_parts();
    let mut http3_response = Response::builder()
        .version(Version::HTTP_3)
        .status(response_parts.status)
        .body(())?;
    *http3_response.headers_mut() = response_parts.headers;
    send_stream.send_response(http3_response).await?;
    while let Some(frame) = body.frame().await {
        let frame = frame?;
        if let Ok(data) = frame.into_data() {
            if !data.is_empty() {
                send_stream.send_data(data).await?;
            }
        }
    }
    send_stream.finish().await?;
    Ok(())
}

async fn pump_h3_request_body(
    mut body: h3::server::RequestStream<h3_quinn::RecvStream, Bytes>,
    sender: mpsc::Sender<RequestMessage>,
    mut connection_closed: watch::Receiver<bool>,
) {
    loop {
        if *connection_closed.borrow() {
            return;
        }
        let data = tokio::select! {
            biased;
            _ = wait_for_connection_close(&mut connection_closed) => return,
            _ = sender.closed() => return,
            result = body.recv_data() => result,
        };
        match data {
            Ok(Some(mut data)) => {
                let len = data.remaining();
                let chunk = data.copy_to_bytes(len);
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
                    _ = wait_for_connection_close(&mut connection_closed) => return,
                    result = sender.send(message) => {
                        if result.is_err() {
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
                    _ = wait_for_connection_close(&mut connection_closed) => return,
                    result = sender.send(message) => {
                        if result.is_err() {
                            return;
                        }
                    }
                }
                tokio::select! {
                    _ = wait_for_connection_close(&mut connection_closed) => return,
                    _ = sender.closed() => return,
                }
            }
            Err(_) => {
                let _ = sender
                    .send(RequestMessage {
                        body: Bytes::new(),
                        more_body: false,
                        disconnected: true,
                    })
                    .await;
                return;
            }
        }
    }
}

async fn handle_request(
    request: Request<Incoming>,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
    state: Option<Arc<Py<PyDict>>>,
) -> Response<ResponseBody> {
    match handle_request_inner(
        request,
        peer_addr,
        server_addr,
        app,
        invoke,
        locals,
        scheme,
        connection_closed,
        state,
    )
    .await
    {
        Ok(response) => response,
        Err(error) => {
            eprintln!("uvicorn-rs: ASGI request failed: {error}");
            response(
                StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
                full_body(Bytes::from_static(b"Internal Server Error")),
                Vec::new(),
            )
        }
    }
}

async fn handle_request_inner(
    request: Request<Incoming>,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
    state: Option<Arc<Py<PyDict>>>,
) -> Result<Response<ResponseBody>, BoxError> {
    let (parts, body) = request.into_parts();
    let (request_tx, request_rx) = mpsc::channel(1);
    let request_sender = if body.is_end_stream() {
        request_tx
            .try_send(RequestMessage {
                body: Bytes::new(),
                more_body: false,
                disconnected: false,
            })
            .map_err(|error| Box::new(error) as BoxError)?;
        Some(request_tx)
    } else {
        tokio::spawn(pump_http_request_body(
            body,
            request_tx,
            connection_closed.clone(),
        ));
        None
    };
    handle_request_parts(
        parts,
        request_rx,
        request_sender,
        connection_closed,
        peer_addr,
        server_addr,
        app,
        invoke,
        locals,
        scheme,
        state,
    )
    .await
}

async fn handle_request_parts(
    parts: http::request::Parts,
    request_messages: mpsc::Receiver<RequestMessage>,
    request_sender: Option<mpsc::Sender<RequestMessage>>,
    connection_closed: watch::Receiver<bool>,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    scheme: &'static str,
    state: Option<Arc<Py<PyDict>>>,
) -> Result<Response<ResponseBody>, BoxError> {
    let (start_tx, mut start_rx) = mpsc::channel(1);
    let (body_tx, body_rx) = mpsc::channel(1);
    let app_future = Python::attach(move |py| {
        let io = Py::new(
            py,
            AsgiIo {
                request_messages: Arc::new(Mutex::new(request_messages)),
                _request_sender: request_sender,
                connection_closed,
                request_disconnected: Arc::new(AtomicBool::new(false)),
                response_started: AtomicBool::new(false),
                start: start_tx,
                body: body_tx,
            },
        )?;
        let scope = build_scope(py, &parts, peer_addr, server_addr, scheme, state.as_ref())?;
        let awaitable = invoke.bind(py).call1((app.bind(py), scope, io))?;
        python_task_future(py, &locals, awaitable)
    })?;
    let mut app_task = AbortOnDrop::new(tokio::spawn(app_future));

    let start = tokio::select! {
        biased;
        start = start_rx.recv() => start,
        result = app_task.as_mut() => {
            app_task.take();
            observe_app_before_response_start(result)?;
            return Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
                full_body(Bytes::from_static(b"Internal Server Error")),
                Vec::new(),
            ));
        }
    };
    let Some(start) = start else {
        let result = app_task.as_mut().await;
        app_task.take();
        observe_app_before_response_start(result)?;
        return Ok(response(
            StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
            full_body(Bytes::from_static(b"Internal Server Error")),
            Vec::new(),
        ));
    };

    let body = AsgiBody {
        receiver: body_rx,
        app_task: Some(app_task.take()),
        final_body_seen: false,
        stream_ended: false,
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
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    transport_scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
    scope_state: Option<Arc<Py<PyDict>>>,
    websocket_tasks: WebSocketTasks,
    cancellation: CancellationToken,
) -> Response<ResponseBody> {
    match handle_websocket_request_inner(
        request,
        peer_addr,
        server_addr,
        app,
        invoke,
        locals,
        transport_scheme,
        connection_closed,
        scope_state,
        websocket_tasks,
        cancellation,
    )
    .await
    {
        Ok(response) => response,
        Err(error) => {
            eprintln!("uvicorn-rs: WebSocket request failed: {error}");
            response(
                StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
                full_body(Bytes::from_static(b"Internal Server Error")),
                Vec::new(),
            )
        }
    }
}

async fn handle_websocket_request_inner(
    mut request: Request<Incoming>,
    peer_addr: SocketAddr,
    server_addr: SocketAddr,
    app: Arc<Py<PyAny>>,
    invoke: Arc<Py<PyAny>>,
    locals: TaskLocals,
    transport_scheme: &'static str,
    connection_closed: watch::Receiver<bool>,
    scope_state: Option<Arc<Py<PyDict>>>,
    websocket_tasks: WebSocketTasks,
    cancellation: CancellationToken,
) -> Result<Response<ResponseBody>, BoxError> {
    let request_key = request
        .headers()
        .get(http::header::SEC_WEBSOCKET_KEY)
        .ok_or_else(|| std::io::Error::other("WebSocket request is missing Sec-WebSocket-Key"))?
        .as_bytes()
        .to_vec();
    let on_upgrade = hyper::upgrade::on(&mut request);
    let parts = request.into_parts().0;
    let (incoming_tx, incoming_rx) = mpsc::channel(8);
    let (outgoing_tx, outgoing_rx) = mpsc::channel(8);
    let (handshake_tx, mut handshake_rx) = oneshot::channel();
    let state = Arc::new(AtomicU8::new(0));
    let websocket_io = WebSocketIo {
        incoming: Arc::new(Mutex::new(incoming_rx)),
        connect_delivered: AtomicBool::new(false),
        connection_closed: connection_closed.clone(),
        state: Arc::clone(&state),
        handshake: std::sync::Mutex::new(Some(handshake_tx)),
        outgoing: outgoing_tx,
    };
    let app_future = Python::attach(move |py| {
        let io = Py::new(py, websocket_io)?;
        let scope = build_websocket_scope(
            py,
            &parts,
            peer_addr,
            server_addr,
            transport_scheme,
            scope_state.as_ref(),
        )?;
        let awaitable = invoke.bind(py).call1((app.bind(py), scope, io))?;
        python_task_future(py, &locals, awaitable)
    })?;
    let mut app_task = AbortOnDrop::new(tokio::spawn(app_future));

    let handshake = tokio::select! {
        biased;
        handshake = &mut handshake_rx => handshake.map_err(|_| {
            std::io::Error::other("ASGI app returned before accepting or closing the WebSocket")
        })?,
        result = app_task.as_mut() => {
            app_task.take();
            observe_app_before_response_start(result)?;
            return Ok(response(
                StatusCode::INTERNAL_SERVER_ERROR.as_u16(),
                full_body(Bytes::from_static(b"Internal Server Error")),
                Vec::new(),
            ));
        }
    };

    let WebSocketHandshake::Accept {
        subprotocol,
        headers,
    } = handshake
    else {
        return Ok(response(
            StatusCode::FORBIDDEN.as_u16(),
            full_body(Bytes::new()),
            Vec::new(),
        ));
    };

    let accept_key = derive_accept_key(&request_key);
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
            .append(name, HeaderValue::from_bytes(&value)?);
    }

    let app_task = app_task.take();
    let upgrade_cancellation = cancellation.clone();
    websocket_tasks.lock().await.spawn(async move {
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
                        cancellation,
                    ).await {
                        eprintln!("uvicorn-rs: WebSocket session failed: {error}");
                    }
                }
                Err(error) => {
                    state.store(3, Ordering::Release);
                    app_task.abort();
                    let _ = app_task.await;
                    eprintln!("uvicorn-rs: WebSocket upgrade failed: {error}");
                }
            }
        }
    });
    Ok(handshake_response)
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
    loop {
        tokio::select! {
            biased;
            _ = wait_for_connection_close(&mut connection_closed) => {
                state.store(3, Ordering::Release);
                let _ = incoming.try_send(WebSocketIncoming::Disconnect {
                    code: 1006,
                    reason: String::new(),
                });
                let _ = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await;
                break;
            }
            _ = cancellation.cancelled() => {
                let _ = tokio::time::timeout(
                    std::time::Duration::from_millis(100),
                    socket.send(Message::Close(Some(CloseFrame {
                        code: CloseCode::Away,
                        reason: "server shutdown".into(),
                    }))),
                ).await;
                state.store(3, Ordering::Release);
                let _ = incoming.try_send(WebSocketIncoming::Disconnect {
                    code: 1001,
                    reason: "server shutdown".to_string(),
                });
                let _ = tokio::time::timeout(
                    std::time::Duration::from_secs(1),
                    &mut app_task,
                ).await;
                break;
            }
            result = &mut app_task => {
                match result {
                    Ok(Ok(_)) => {
                        if state.load(Ordering::Acquire) == 1 {
                            socket.send(Message::Close(Some(CloseFrame {
                                code: CloseCode::Normal,
                                reason: "".into(),
                            }))).await?;
                        }
                    }
                    Ok(Err(error)) => {
                        Python::attach(|py| error.print(py));
                        socket.send(Message::Close(Some(CloseFrame {
                            code: CloseCode::Error,
                            reason: "ASGI application error".into(),
                        }))).await?;
                    }
                    Err(error) => eprintln!("uvicorn-rs: WebSocket app task failed: {error}"),
                }
                break;
            }
            message = socket.next() => {
                match message {
                    Some(Ok(Message::Text(text))) => {
                        if incoming.send(WebSocketIncoming::Text(text.to_string())).await.is_err() {
                            break;
                        }
                    }
                    Some(Ok(Message::Binary(data))) => {
                        if incoming.send(WebSocketIncoming::Bytes(data)).await.is_err() {
                            break;
                        }
                    }
                    Some(Ok(Message::Close(frame))) => {
                        let (code, reason) = frame
                            .map(|frame| (u16::from(frame.code), frame.reason.to_string()))
                            .unwrap_or((1005, String::new()));
                        state.store(3, Ordering::Release);
                        let _ = incoming.send(WebSocketIncoming::Disconnect { code, reason }).await;
                        let _ = tokio::time::timeout(std::time::Duration::from_secs(1), &mut app_task).await;
                        break;
                    }
                    Some(Ok(Message::Ping(_) | Message::Pong(_) | Message::Frame(_))) => {}
                    Some(Err(error)) => {
                        let _ = incoming.send(WebSocketIncoming::Disconnect {
                            code: 1002,
                            reason: error.to_string(),
                        }).await;
                        break;
                    }
                    None => {
                        let _ = incoming.send(WebSocketIncoming::Disconnect {
                            code: 1006,
                            reason: String::new(),
                        }).await;
                        break;
                    }
                }
            }
            message = outgoing.recv() => {
                let Some(message) = message else {
                    if state.load(Ordering::Acquire) == 1 {
                        socket.send(Message::Close(Some(CloseFrame {
                            code: CloseCode::Normal,
                            reason: "".into(),
                        }))).await?;
                    }
                    break;
                };
                let message = match message {
                    WebSocketOutgoing::Text(text) => Message::Text(text.into()),
                    WebSocketOutgoing::Bytes(bytes) => Message::Binary(bytes),
                    WebSocketOutgoing::Close { code, reason } => {
                        state.store(2, Ordering::Release);
                        Message::Close(Some(CloseFrame {
                            code: CloseCode::from(code),
                            reason: reason.into(),
                        }))
                    }
                };
                socket.send(message).await?;
            }
        }
    }
    state.store(3, Ordering::Release);
    if !app_task.is_finished() {
        app_task.abort();
    }
    let _ = app_task.await;
    Ok(())
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
    asgi.set_item("version", "3.0")?;
    asgi.set_item("spec_version", "2.5")?;
    scope.set_item("type", "websocket")?;
    scope.set_item("asgi", asgi)?;
    set_scope_state(py, &scope, state)?;
    scope.set_item(
        "http_version",
        match request.version {
            Version::HTTP_10 => "1.0",
            Version::HTTP_11 => "1.1",
            Version::HTTP_2 => "2",
            Version::HTTP_3 => "3",
            _ => "1.1",
        },
    )?;
    scope.set_item(
        "scheme",
        if transport_scheme == "https" {
            "wss"
        } else {
            "ws"
        },
    )?;
    scope.set_item(
        "path",
        percent_encoding::percent_decode_str(request.uri.path())
            .decode_utf8_lossy()
            .as_ref(),
    )?;
    scope.set_item("raw_path", PyBytes::new(py, request.uri.path().as_bytes()))?;
    scope.set_item(
        "query_string",
        PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes()),
    )?;
    scope.set_item("root_path", "")?;
    scope.set_item("method", request.method.as_str().to_ascii_uppercase())?;
    let headers = PyList::empty(py);
    let mut subprotocols = Vec::new();
    for (name, value) in request.headers.iter() {
        headers.append((
            PyBytes::new(py, name.as_str().as_bytes()),
            PyBytes::new(py, value.as_bytes()),
        ))?;
        if name == http::header::SEC_WEBSOCKET_PROTOCOL {
            for protocol in value.as_bytes().split(|byte| *byte == b',') {
                let protocol = String::from_utf8_lossy(trim_ascii(protocol)).into_owned();
                if !protocol.is_empty() {
                    subprotocols.push(protocol);
                }
            }
        }
    }
    scope.set_item("headers", headers)?;
    scope.set_item("subprotocols", subprotocols)?;
    scope.set_item("client", (peer_addr.ip().to_string(), peer_addr.port()))?;
    scope.set_item("server", (server_addr.ip().to_string(), server_addr.port()))?;
    Ok(scope)
}

fn observe_app_before_response_start(
    result: Result<PyResult<Py<PyAny>>, tokio::task::JoinError>,
) -> Result<(), BoxError> {
    match result {
        Ok(Ok(_)) => eprintln!("uvicorn-rs: ASGI app completed without response.start"),
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
    asgi.set_item("version", "3.0")?;
    asgi.set_item("spec_version", "2.5")?;
    scope.set_item("type", "http")?;
    scope.set_item("asgi", asgi)?;
    set_scope_state(py, &scope, state)?;
    scope.set_item(
        "http_version",
        match request.version {
            Version::HTTP_10 => "1.0",
            Version::HTTP_11 => "1.1",
            Version::HTTP_2 => "2",
            Version::HTTP_3 => "3",
            _ => "1.1",
        },
    )?;
    scope.set_item("method", request.method.as_str().to_ascii_uppercase())?;
    scope.set_item("scheme", scheme)?;

    let raw_path = request.uri.path().as_bytes();
    let path = percent_encoding::percent_decode_str(request.uri.path())
        .decode_utf8_lossy()
        .into_owned();
    scope.set_item("path", PyString::new(py, &path))?;
    scope.set_item("raw_path", PyBytes::new(py, raw_path))?;
    scope.set_item(
        "query_string",
        PyBytes::new(py, request.uri.query().unwrap_or("").as_bytes()),
    )?;
    scope.set_item("root_path", "")?;

    let headers = PyList::empty(py);
    for (name, value) in request.headers.iter() {
        headers.append((
            PyBytes::new(py, name.as_str().as_bytes()),
            PyBytes::new(py, value.as_bytes()),
        ))?;
    }
    scope.set_item("headers", headers)?;
    scope.set_item("client", (peer_addr.ip().to_string(), peer_addr.port()))?;
    scope.set_item("server", (server_addr.ip().to_string(), server_addr.port()))?;
    Ok(scope)
}

fn set_scope_state(
    py: Python<'_>,
    scope: &Bound<'_, PyDict>,
    state: Option<&Arc<Py<PyDict>>>,
) -> PyResult<()> {
    if let Some(state) = state {
        let request_state = PyDict::new(py);
        for (key, value) in state.bind(py).iter() {
            request_state.set_item(key, value)?;
        }
        scope.set_item("state", request_state)?;
    }
    Ok(())
}

fn full_body(body: Bytes) -> ResponseBody {
    Full::new(body)
        .map_err(|never| -> BoxError { match never {} })
        .boxed_unsync()
}

fn response(
    status: u16,
    body: ResponseBody,
    headers: Vec<(Bytes, Bytes)>,
) -> Response<ResponseBody> {
    let mut response = Response::new(body);
    *response.status_mut() =
        StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    for (name, value) in headers {
        let Ok(name) = HeaderName::from_bytes(&name) else {
            *response.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
            *response.body_mut() = full_body(Bytes::from_static(b"Invalid response header"));
            return response;
        };
        let Ok(value) = HeaderValue::from_bytes(&value) else {
            *response.status_mut() = StatusCode::INTERNAL_SERVER_ERROR;
            *response.body_mut() = full_body(Bytes::from_static(b"Invalid response header"));
            return response;
        };
        response.headers_mut().append(name, value);
    }
    response
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let mut runtime_builder = tokio::runtime::Builder::new_multi_thread();
    runtime_builder.worker_threads(2).enable_all();
    pyo3_async_runtimes::tokio::init(runtime_builder);
    module.add_class::<AsgiIo>()?;
    module.add_class::<WebSocketIo>()?;
    module.add_class::<LifespanIo>()?;
    module.add_class::<ServerControl>()?;
    module.add_function(wrap_pyfunction!(serve, module)?)?;
    Ok(())
}
