"""Run input-selected Python public API probes for parity comparison."""

import asyncio
import base64
import http.client
import importlib
import inspect
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time

_startup_failure_server = None
_startup_failure_task = None
_lifespan_startup_server = None
_lifespan_startup_task = None


def resolve(path: str):
    module_name, separator, attributes = path.partition(":")
    if not separator:
        module_name, separator, attributes = path.rpartition(".")
    if not module_name or not attributes:
        raise ValueError(f"invalid import path: {path!r}")
    value = importlib.import_module(module_name)
    for name in attributes.split("."):
        value = getattr(value, name)
    return value


def signature(value):
    result = []
    for parameter in inspect.signature(value).parameters.values():
        default = (
            "<required>"
            if parameter.default is inspect.Parameter.empty
            else repr(parameter.default)
        )
        result.append(
            {
                "name": parameter.name,
                "kind": parameter.kind.name,
                "default": default,
                "annotation": str(parameter.annotation),
            }
        )
    return result


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that opens its stream over a Unix-domain socket."""

    def __init__(self, socket_path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self.socket_path)
        self.sock = connection


def run_http_observation(request: dict) -> dict:
    """Exercise a public Python API or CLI server and signal shutdown."""

    child_code = r'''
import sys
import base64
import asyncio
import json
import logging
import socket
import uvicorn

lifespan_state = {"started": False}
factory_invoked = False

async def asgi3_app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                lifespan_state["started"] = True
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
        return
    if scope["type"] != "http":
        return
    if emit_level_logs:
        logger = logging.getLogger("uvicorn.error")
        logger.debug("python-api log-level debug sentinel")
        logger.info("python-api log-level info sentinel")
        logger.warning("python-api log-level warning sentinel")
        logger.error("python-api log-level error sentinel")
        logger.critical("python-api log-level critical sentinel")
    await receive()
    lifespan_status = b"lifespan-started" if lifespan_state["started"] else b"lifespan-off"
    if "state" not in scope:
        state_status = b"scope-state-missing"
    elif scope["state"] == {}:
        state_status = b"scope-state-empty"
    else:
        state_status = b"scope-state-populated"
    scope_headers = dict(scope.get("headers", []))
    expected_root_path = scope_headers.get(b"x-asgi-expected-root-path-base64")
    expected_raw_path = scope_headers.get(b"x-asgi-expected-raw-path-base64")
    if expected_root_path is not None and expected_raw_path is not None:
        root_path_matches = scope["root_path"] == base64.b64decode(
            expected_root_path, validate=True
        ).decode("utf-8")
        raw_path_matches = scope["raw_path"] == base64.b64decode(
            expected_raw_path, validate=True
        )
        body = (
            b"asgi-scope-contract-passed"
            if root_path_matches and raw_path_matches
            else b"asgi-scope-contract-failed"
        )
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
        return
    root_path_status = b"root_path=" + scope["root_path"].encode("utf-8")
    path_status = b"path=" + scope["path"].encode("utf-8")
    raw_path_status = b"raw_path=" + base64.b64encode(scope["raw_path"])
    body_parts = [
        b"python-api-run-ok",
        lifespan_status,
        state_status,
        root_path_status,
        path_status,
        raw_path_status,
    ]
    if factory_invoked:
        body_parts.append(b"factory-created")
    if observe_scope:
        body_parts.extend(
            (
                b"proxy-scheme=" + scope["scheme"].encode("latin1"),
                b"proxy-client=" + str(scope["client"][0]).encode("latin1"),
            )
        )
    if observe_loop:
        loop = asyncio.get_running_loop()
        loop_name = f"{type(loop).__module__}.{type(loop).__qualname__}"
        body_parts.append(b"python-loop=" + loop_name.encode("ascii"))
    if observe_unix_scope:
        client_is_none = scope.get("client") is None
        server = scope.get("server")
        server_has_unix_shape = (
            isinstance(server, tuple)
            and len(server) == 2
            and isinstance(server[0], str)
            and server[1] is None
        )
        body_parts.extend(
            (
                b"client-is-none=" + str(client_is_none).lower().encode("ascii"),
                b"server-has-unix-shape="
                + str(server_has_unix_shape).lower().encode("ascii"),
            )
        )
    body = b"|".join(body_parts)
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            (b"content-type", b"text/plain"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})

def asgi2_app(scope):
    async def respond(receive, send):
        await asgi3_app(scope, receive, send)
    return respond

def wsgi_app(environ, start_response):
    body = b"|".join((
        b"python-api-wsgi-ok",
        environ["REQUEST_METHOD"].encode("ascii"),
        environ["PATH_INFO"].encode("latin1"),
        environ["QUERY_STRING"].encode("ascii"),
        environ.get("HTTP_X_PYTHON_API", "missing").encode("latin1"),
    ))
    start_response("200 OK", [
        ("content-type", "text/plain"),
        ("content-length", str(len(body))),
    ])
    return [body]

def app_factory():
    global factory_invoked
    factory_invoked = True
    if application_interface == "wsgi":
        return wsgi_app
    return asgi2_app if application_interface == "asgi2" else asgi3_app

application_interface = sys.argv[5]
requested_interface = sys.argv[6]
observe_scope = sys.argv[7] == "1"
observe_loop = sys.argv[8] == "1"
observe_unix_scope = sys.argv[25] == "1"
fd = int(sys.argv[26]) if sys.argv[26] else None
proxy_headers = sys.argv[9] == "1"
forwarded_allow_ips = json.loads(sys.argv[10])
limit_concurrency = json.loads(sys.argv[11])
loop = json.loads(sys.argv[12])
invocation = sys.argv[13]
log_level = json.loads(sys.argv[14])
emit_level_logs = sys.argv[15] == "1"
access_log = sys.argv[16] == "1"
use_colors = json.loads(sys.argv[17])
factory = sys.argv[19] == "1"
backlog = json.loads(sys.argv[20])
timeout_keep_alive = json.loads(sys.argv[21])
workers = json.loads(sys.argv[22])
timeout_worker_healthcheck = json.loads(sys.argv[23])
uds_path = sys.argv[24] or None
app = app_factory if factory else (
    wsgi_app
    if application_interface == "wsgi"
    else asgi2_app if application_interface == "asgi2" else asgi3_app
)

options = {
    "host": "127.0.0.1",
    "port": int(sys.argv[1]),
    "lifespan": sys.argv[2],
    "root_path": sys.argv[3],
    "headers": json.loads(sys.argv[4]),
    "interface": requested_interface,
    "proxy_headers": proxy_headers,
    "forwarded_allow_ips": forwarded_allow_ips,
    "limit_concurrency": limit_concurrency,
    "loop": loop,
    "log_config": json.loads(sys.argv[18]),
    "log_level": log_level,
    "access_log": access_log,
    "use_colors": use_colors,
    "factory": factory,
    "backlog": backlog,
    "timeout_keep_alive": timeout_keep_alive,
    "workers": workers,
    "timeout_worker_healthcheck": timeout_worker_healthcheck,
    "fd": fd,
}
if uds_path is not None:
    options["uds"] = uds_path
if invocation in {"config-server", "server-sockets"}:
    if invocation == "server-sockets":
        options.pop("fd", None)
    config = uvicorn.Config(app, **options)
    if invocation == "server-sockets":
        listener = socket.socket(fileno=fd)
        uvicorn.Server(config).run(sockets=[listener])
    else:
        uvicorn.Server(config).run()
else:
    uvicorn.run(app, **options)
'''
    uds_directory = None
    uds_path = None
    inherited_listener = None
    if request.get("fd", False):
        if os.name == "nt":
            raise ValueError("inherited descriptor parity input requires Unix")
        inherited_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        inherited_listener.bind(("127.0.0.1", 0))
        inherited_listener.listen()
        inherited_listener.set_inheritable(True)
        port = inherited_listener.getsockname()[1]
    elif request.get("uds", False):
        uds_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-", dir="/tmp" if os.path.isdir("/tmp") else None
        )
        uds_path = os.path.join(uds_directory.name, "u.sock")
        port = 0
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

    if request["invocation"] == "module-cli":
        if request.get("uds"):
            app_target = "tests.parity.app:python_api_uds_probe_app"
        elif request.get("factory"):
            app_target = "tests.parity.app:python_api_factory_probe_app"
        elif request.get("application_interface") == "wsgi":
            app_target = "tests.parity.app:python_api_wsgi_probe_app"
        else:
            app_target = (
                "tests.parity.app:asgi2_probe_app"
                if request.get("application_interface") == "asgi2"
                else "tests.parity.app:lifespan_probe_app"
            )
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            app_target,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--root-path",
            request["root_path"],
            "--lifespan",
            request["lifespan"],
        ]
        if uds_path is not None:
            command.extend(("--uds", uds_path))
        if inherited_listener is not None:
            command.extend(("--fd", str(inherited_listener.fileno())))
        if request.get("factory"):
            command.append("--factory")
        if request.get("interface", "auto") != "auto":
            command.extend(("--interface", request["interface"]))
        for name, value in request.get("headers", []):
            command.extend(("--header", f"{name}:{value}"))
        if request.get("proxy_headers") is False:
            command.append("--no-proxy-headers")
        if request.get("forwarded_allow_ips") is not None:
            command.extend(("--forwarded-allow-ips", request["forwarded_allow_ips"]))
        if request.get("limit_concurrency") is not None:
            command.extend(("--limit-concurrency", str(request["limit_concurrency"])))
        if request.get("backlog") is not None:
            command.extend(("--backlog", str(request["backlog"])))
        if request.get("timeout_keep_alive") is not None:
            command.extend(("--timeout-keep-alive", str(request["timeout_keep_alive"])))
        if request.get("workers") is not None:
            command.extend(("--workers", str(request["workers"])))
        if request.get("timeout_worker_healthcheck") is not None:
            command.extend(("--timeout-worker-healthcheck", str(request["timeout_worker_healthcheck"])))
        if request.get("loop", "auto") != "auto":
            command.extend(("--loop", request["loop"]))
        if request.get("log_level") is not None:
            command.extend(("--log-level", str(request["log_level"])))
        if request.get("log_config") is not None:
            command.extend(("--log-config", request["log_config"]))
        if request.get("access_log") is False:
            command.append("--no-access-log")
        if request.get("use_colors") is not None:
            command.append("--use-colors" if request["use_colors"] else "--no-use-colors")
    else:
        command = [
            sys.executable,
            "-c",
            child_code,
            str(port),
            request["lifespan"],
            request["root_path"],
            json.dumps(request.get("headers", []), separators=(",", ":")),
            request.get("application_interface", "asgi3"),
            request.get("interface", "auto"),
            "1" if request.get("observe_scope", False) else "0",
            "1" if request.get("observe_loop", False) else "0",
            "0" if request.get("proxy_headers") is False else "1",
            json.dumps(request.get("forwarded_allow_ips")),
            json.dumps(request.get("limit_concurrency")),
            json.dumps(request.get("loop", "auto")),
            request["invocation"],
            json.dumps(request.get("log_level")),
            "1" if request.get("emit_level_logs", False) else "0",
            "0" if request.get("access_log") is False else "1",
            json.dumps(request.get("use_colors")),
            json.dumps(request.get("log_config")),
            "1" if request.get("factory", False) else "0",
            json.dumps(request.get("backlog", 2048)),
            json.dumps(request.get("timeout_keep_alive", 5)),
            json.dumps(request.get("workers")),
            json.dumps(request.get("timeout_worker_healthcheck", 5)),
            uds_path or "",
            "1" if request.get("observe_unix_scope", False) else "0",
            str(inherited_listener.fileno()) if inherited_listener is not None else "",
        ]

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONNOUSERSITE"] = "1"
    process_options = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        stop_signal = signal.CTRL_BREAK_EVENT
    else:
        stop_signal = signal.SIGINT
    if inherited_listener is not None:
        process_options["pass_fds"] = (inherited_listener.fileno(),)

    try:
        process = subprocess.Popen(
            command,
            cwd=os.getcwd(),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **process_options,
        )
    except BaseException:
        if inherited_listener is not None:
            inherited_listener.close()
        if uds_directory is not None:
            uds_directory.cleanup()
        raise
    response = None
    idle_connection_closed = None
    deadline = time.monotonic() + request["timeout_seconds"]
    try:
        while time.monotonic() < deadline and process.poll() is None:
            connection = (
                UnixHTTPConnection(uds_path, timeout=0.5)
                if uds_path is not None
                else http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
            )
            try:
                keep_alive_probe_delay = request.get("keep_alive_probe_delay_seconds")
                connection.request(
                    request["method"],
                    request["path"],
                    headers={
                        "Connection": "keep-alive" if keep_alive_probe_delay is not None else "close",
                        **dict(request.get("request_headers", [])),
                    },
                )
                http_response = connection.getresponse()
                response_body = http_response.read()
                response = {
                    "status": http_response.status,
                    "content_type": http_response.getheader("content-type"),
                    "body_base64": base64.b64encode(response_body).decode("ascii"),
                    "observed_headers": {
                        name.lower(): http_response.headers.get_all(name, [])
                        for name in request.get("observe_headers", [])
                    },
                }
                if keep_alive_probe_delay is not None:
                    time.sleep(keep_alive_probe_delay)
                    try:
                        connection.request(
                            request["method"],
                            request["path"],
                            headers={
                                "Connection": "keep-alive",
                                **dict(request.get("request_headers", [])),
                            },
                        )
                        second_response = connection.getresponse()
                        second_response.read()
                        idle_connection_closed = False
                    except (OSError, http.client.HTTPException, TimeoutError):
                        idle_connection_closed = True
                break
            except (OSError, http.client.HTTPException, TimeoutError):
                time.sleep(0.025)
            finally:
                connection.close()

        shutdown_signal_sent = False
        if process.poll() is None:
            try:
                process.send_signal(stop_signal)
                shutdown_signal_sent = True
            except OSError:
                pass
        server_stdout = b""
        server_stderr = b""
        try:
            server_stdout, server_stderr = process.communicate(
                timeout=request["timeout_seconds"]
            )
            process_timed_out = False
        except subprocess.TimeoutExpired:
            process_timed_out = True
            process.kill()
            server_stdout, server_stderr = process.communicate()
        observation = {
            "response_received": response is not None,
            "response_status": response["status"] if response is not None else None,
            "response_content_type": response["content_type"] if response is not None else None,
            "response_body_base64": response["body_base64"] if response is not None else "",
            "idle_connection_closed": idle_connection_closed,
            "shutdown_signal_sent": shutdown_signal_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
            "server_stdout_base64": base64.b64encode(server_stdout).decode("ascii"),
            "server_stderr_base64": base64.b64encode(server_stderr).decode("ascii"),
        }
        return observation
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        if uds_directory is not None:
            uds_directory.cleanup()
        if inherited_listener is not None:
            inherited_listener.close()


def run_websocket_observation(request: dict) -> dict:
    """Exercise WebSocket options through the public ``uvicorn.run`` API."""

    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect as websocket_connect

    child_code = r'''
import sys
import uvicorn

async def app(scope, receive, send):
    if scope["type"] != "websocket":
        return
    message = await receive()
    if message["type"] != "websocket.connect":
        return
    await send({"type": "websocket.accept"})
    while True:
        message = await receive()
        if message["type"] == "websocket.disconnect":
            return
        if message["type"] == "websocket.receive":
            response = {"type": "websocket.send"}
            if "text" in message:
                response["text"] = message["text"]
            else:
                response["bytes"] = message.get("bytes", b"")
            await send(response)

uvicorn.run(
    app,
    host="127.0.0.1",
    port=int(sys.argv[1]),
    lifespan="off",
    ws_max_size=int(sys.argv[2]),
    ws_max_queue=int(sys.argv[3]),
)
'''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONNOUSERSITE"] = "1"
    process_options = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        stop_signal = signal.CTRL_BREAK_EVENT
    else:
        stop_signal = signal.SIGINT

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(port),
            str(request["ws_max_size"]),
            str(request.get("ws_max_queue", 32)),
        ],
        cwd=os.getcwd(),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **process_options,
    )
    deadline = time.monotonic() + request["timeout_seconds"]
    connection = None
    handshake_status = None
    close_code = None
    message_received = False
    try:
        uri = f"ws://127.0.0.1:{port}{request['path']}"
        while time.monotonic() < deadline and process.poll() is None:
            try:
                connection = websocket_connect(
                    uri,
                    open_timeout=min(0.5, max(deadline - time.monotonic(), 0.01)),
                    close_timeout=0.5,
                    max_size=None,
                    legacy=True,
                )
                handshake_status = 101
                break
            except InvalidStatus as error:
                handshake_status = error.response.status_code
                break
            except (OSError, TimeoutError):
                time.sleep(0.025)

        if connection is not None:
            try:
                connection.send(request["message"])
                try:
                    connection.recv(timeout=max(deadline - time.monotonic(), 0.01))
                    message_received = True
                except ConnectionClosed as error:
                    if error.rcvd is not None:
                        close_code = error.rcvd.code
            except (OSError, TimeoutError):
                pass
            if close_code is None:
                close_code = connection.close_code
            connection.close()
            if close_code is None:
                close_code = connection.close_code

        shutdown_signal_sent = False
        if process.poll() is None:
            try:
                process.send_signal(stop_signal)
                shutdown_signal_sent = True
            except OSError:
                pass
        server_stdout = b""
        server_stderr = b""
        try:
            server_stdout, server_stderr = process.communicate(
                timeout=max(request["timeout_seconds"], 1)
            )
            process_timed_out = False
        except subprocess.TimeoutExpired:
            process_timed_out = True
            process.kill()
            server_stdout, server_stderr = process.communicate()

        observation = {
            "handshake_status": handshake_status,
            "close_code": close_code,
            "message_received": message_received,
            "shutdown_signal_sent": shutdown_signal_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
        }
        if (
            handshake_status != 101
            or close_code != 1009
            or process.returncode != 0
            or process_timed_out
        ):
            observation["server_stdout_base64"] = base64.b64encode(server_stdout).decode("ascii")
            observation["server_stderr_base64"] = base64.b64encode(server_stderr).decode("ascii")
        return observation
    finally:
        if connection is not None:
            connection.close()
        if process.poll() is None:
            process.kill()
            process.communicate()


async def server_readiness_observation() -> dict[str, bool]:
    import uvicorn

    startup_received = asyncio.Event()
    allow_startup = asyncio.Event()

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    startup_received.set()
                    await allow_startup.wait()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        loop="asyncio",
        http="httptools",
        lifespan="on",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        await asyncio.wait_for(startup_received.wait(), timeout=5)
        started_before_lifespan_complete = bool(server.started)
        allow_startup.set()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while not server.started and not task.done() and loop.time() < deadline:
            await asyncio.sleep(0)
        if task.done():
            await task
        started_after_lifespan_complete = bool(server.started)
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)
        started_after_serve_return = bool(server.started)
        return {
            "started_before_lifespan_complete": started_before_lifespan_complete,
            "started_after_lifespan_complete": started_after_lifespan_complete,
            "started_after_serve_return": started_after_serve_return,
        }
    finally:
        allow_startup.set()
        if not task.done():
            server.should_exit = True
            await asyncio.gather(task, return_exceptions=True)


async def server_startup_failure_observation() -> dict[str, bool]:
    import uvicorn

    global _startup_failure_server, _startup_failure_task

    async def app(scope, receive, send):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="does-not-exist.invalid",
            port=0,
            loop="asyncio",
            http="httptools",
            lifespan="auto",
            log_config=None,
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    _startup_failure_server = server
    _startup_failure_task = task
    raised = False
    timed_out = False
    try:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except TimeoutError:
            if task.done():
                raised = True
            else:
                timed_out = True
        except BaseException:
            raised = True
    finally:
        if not task.done():
            server.should_exit = True
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return {
        "server_started": bool(server.started),
        "serve_task_finished": task.done(),
        "serve_raised": raised,
        "serve_timed_out": timed_out,
    }


async def server_lifespan_startup_observation(request: dict) -> dict[str, object]:
    """Observe strict lifespan startup through the public Config and Server APIs."""

    import uvicorn

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            if request["app_lifespan"] == "raises-before-startup":
                raise RuntimeError("parity lifespan startup exception")
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    global _lifespan_startup_server, _lifespan_startup_task

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            loop="asyncio",
            http="httptools",
            interface="asgi3",
            lifespan=request["lifespan"],
            log_config=None,
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    _lifespan_startup_server = server
    _lifespan_startup_task = task
    raised = False
    timed_out = False
    try:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=request["timeout_seconds"])
        except TimeoutError:
            timed_out = True
        except BaseException:
            raised = True
        return {
            "server_started_before_shutdown": bool(server.started),
            "serve_task_finished_before_shutdown": task.done(),
            "serve_raised": raised,
            "serve_timed_out": timed_out,
            "server_exit_code": None,
        }
    finally:
        if not task.done():
            server.should_exit = True
            try:
                await asyncio.wait_for(
                    asyncio.gather(task, return_exceptions=True),
                    timeout=request["timeout_seconds"],
                )
            except TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


def module_cli_lifespan_startup_observation(request: dict) -> dict[str, object]:
    """Observe strict lifespan startup through ``python -m uvicorn``."""

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.parity.app:lifespan_startup_error_probe_app",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--loop",
        "asyncio",
        "--lifespan",
        request["lifespan"],
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            command,
            cwd=os.getcwd(),
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=request["timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "process_exit_code": None,
            "process_timed_out": True,
            "process_stderr_has_unhandled_task_warning": False,
        }
    return {
        "process_exit_code": completed.returncode,
        "process_timed_out": False,
        "process_stderr_has_unhandled_task_warning": (
            b"Task exception was never retrieved" in completed.stderr
        ),
    }


def main() -> None:
    request = json.loads(sys.argv[1])
    if "run_http" in request:
        observations = {"run_http": run_http_observation(request["run_http"])}
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "run_websocket" in request:
        observations = {
            "run_websocket": run_websocket_observation(request["run_websocket"]),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_readiness" in request:
        observations = {
            "server_readiness": asyncio.run(server_readiness_observation()),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_failure" in request:
        try:
            observation = asyncio.run(server_startup_failure_observation())
        except BaseException:
            # Some Uvicorn startup errors escape the task as SystemExit and
            # stop asyncio.run's loop. Capture the same public observations
            # after Runner cleanup so the input still compares started/error
            # behavior without treating the harness process exit as a test
            # oracle shortcut.
            observation = {
                "server_started": bool(
                    _startup_failure_server is not None
                    and _startup_failure_server.started
                ),
                "serve_task_finished": bool(
                    _startup_failure_task is not None
                    and _startup_failure_task.done()
                ),
                "serve_raised": True,
                "serve_timed_out": False,
            }
        observations = {"server_startup_failure": observation}
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_lifespan_startup" in request:
        try:
            observation = asyncio.run(
                server_lifespan_startup_observation(request["server_lifespan_startup"])
            )
        except SystemExit as error:
            observation = {
                "server_started_before_shutdown": bool(
                    _lifespan_startup_server is not None
                    and _lifespan_startup_server.started
                ),
                "serve_task_finished_before_shutdown": bool(
                    _lifespan_startup_task is not None
                    and _lifespan_startup_task.done()
                ),
                "serve_raised": True,
                "serve_timed_out": False,
                "server_exit_code": error.code,
            }
        observations = {"server_lifespan_startup": observation}
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "module_cli_lifespan_startup" in request:
        observations = {
            "module_cli_lifespan_startup": module_cli_lifespan_startup_observation(
                request["module_cli_lifespan_startup"]
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    observations = {"imports": {}, "signatures": {}}
    values = {}
    for path in request["imports"]:
        try:
            values[path] = resolve(path)
            observations["imports"][path] = {"available": True}
        except Exception as error:
            observations["imports"][path] = {
                "available": False,
                "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                "error": str(error),
            }
    for path in request["signatures"]:
        try:
            value = values.get(path)
            if value is None:
                value = resolve(path)
            observations["signatures"][path] = signature(value)
        except Exception as error:
            observations["signatures"][path] = {
                "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                "error": str(error),
            }
    if "calls" in request:
        observations["calls"] = []
        for call in request["calls"]:
            try:
                value = resolve(call["target"])(
                    *call["arguments"], **call["keyword_arguments"]
                )
                for method_call in call.get("method_calls", []):
                    value = getattr(value, method_call["method"])(
                        *method_call["arguments"],
                        **method_call["keyword_arguments"],
                    )
                result = {"returned": True}
            except SystemExit as error:
                result = {"returned": False, "exit_code": error.code}
            except BaseException as error:
                result = {
                    "returned": False,
                    "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                    "error": str(error),
                }
            observations["calls"].append({"target": call["target"], **result})
    print(json.dumps(observations, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
