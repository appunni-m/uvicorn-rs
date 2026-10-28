"""Run input-selected Python public API probes for parity comparison."""

from __future__ import annotations

import asyncio
import base64
import http.client
import importlib
import inspect
import json
import os
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import warnings
from pathlib import Path
from typing import get_type_hints

_startup_failure_server = None
_startup_failure_task = None
_startup_bind_failure_lifespan_state = None
_startup_uds_replacement_lifespan_state = None
_startup_failure_waiter_state = None
_lifespan_startup_server = None
_lifespan_startup_task = None


def subprocess_environment() -> dict[str, str]:
    """Keep the runner-selected package path and coverage shim for the child."""

    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONSTARTUP"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if environment.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") == "1":
        coverage_site = str(Path(__file__).parent / "coverage_site")
        environment["PYTHONPATH"] = os.pathsep.join(
            path for path in (coverage_site, environment.get("PYTHONPATH")) if path
        )
    return environment


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
    signature_target = value.__init__ if inspect.isclass(value) else value
    try:
        get_type_hints(signature_target)
        type_hints_resolve = {"resolves": True}
    except Exception as error:
        type_hints_resolve = {
            "resolves": False,
            "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
        }
    inspected_signature = inspect.signature(value)
    result = []
    for parameter in inspected_signature.parameters.values():
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
    return {
        "parameters": result,
        "return_annotation": str(inspected_signature.return_annotation),
        "type_hints": type_hints_resolve,
    }


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


class UnixHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that wraps a Unix-domain socket with TLS."""

    def __init__(self, socket_path: str, timeout: float, context: ssl.SSLContext):
        super().__init__("localhost", timeout=timeout, context=context)
        self.socket_path = socket_path
        self.tls_context = context

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(self.socket_path)
            self.sock = self.tls_context.wrap_socket(
                connection, server_hostname=self.host
            )
        except BaseException:
            connection.close()
            raise


def run_http_reload_observation(request: dict) -> dict:
    """Change watched files and observe whether the supervisor replaces its child."""

    timeout_seconds = request["timeout_seconds"]
    fixture_directory = Path(__file__).parent / "fixtures"
    reload_filters = "reload_include" in request or "reload_exclude" in request
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-reload-") as directory:
        app_directory = Path(directory)
        if reload_filters:
            (app_directory / "included.txt").write_bytes(b"before-included")
            (app_directory / "ignored.txt").write_bytes(b"before-excluded")
            (app_directory / "reload_filter_app.py").write_text(
                '''from pathlib import Path

base = Path(__file__).parent
body = base.joinpath("included.txt").read_bytes() + b":" + base.joinpath("ignored.txt").read_bytes()

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    elif scope["type"] == "http":
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})
''',
                encoding="utf-8",
            )
            app_module = "reload_filter_app:app"
        else:
            shutil.copyfile(fixture_directory / "reload_app.py", app_directory / "reload_app.py")
            shutil.copyfile(fixture_directory / "reload_state.py", app_directory / "reload_state.py")
            app_module = "reload_app:app"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

        command = [
            sys.executable,
            "-m",
            "uvicorn",
            app_module,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--workers",
            str(request["workers"]),
            "--loop",
            "asyncio",
            "--reload",
            "--reload-dir",
            str(app_directory),
            "--reload-delay",
            str(request["reload_delay"]),
            "--app-dir",
            str(app_directory),
        ]
        for pattern in request.get("reload_include", []):
            command.extend(["--reload-include", pattern])
        for pattern in request.get("reload_exclude", []):
            command.extend(["--reload-exclude", pattern])
        environment = subprocess_environment()
        for name, value in request.get("environment", {}).items():
            environment[name] = value
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == "nt"
            else 0
        )
        process = subprocess.Popen(
            command,
            cwd=os.getcwd(),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )

        def request_body() -> tuple[int | None, bytes | None]:
            connection = http.client.HTTPConnection(
                "127.0.0.1", port, timeout=0.5
            )
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                return response.status, response.read()
            except (OSError, http.client.HTTPException):
                return None, None
            finally:
                connection.close()

        first_status = None
        first_body = None
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            first_status, first_body = request_body()
            if first_status == 200:
                break
            time.sleep(0.05)

        reload_observed = False
        excluded_change_reloaded = None
        included_change_reloaded = None
        second_status = None
        second_body = None
        if first_status == 200:
            # The reloader starts serving from its child before the parent has
            # necessarily entered the watch iterator. Let the configured poll
            # interval elapse before changing the module so the case measures
            # reload behavior rather than racing watcher startup.
            time.sleep(max(0.3, request["reload_delay"] * 3))
            if reload_filters:
                initial_body = b"before-included:before-excluded"
                excluded_only_body = b"before-included:after-excluded"
                final_body = b"after-included:after-excluded"
                (app_directory / "ignored.txt").write_bytes(b"after-excluded")
                excluded_change_reloaded = False
                deadline = time.monotonic() + max(
                    2.0, request["reload_delay"] * 20
                )
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    status, body = request_body()
                    if status == 200:
                        second_status, second_body = status, body
                        if body == excluded_only_body:
                            excluded_change_reloaded = True
                    time.sleep(0.05)

                (app_directory / "included.txt").write_bytes(b"after-included")
                included_change_reloaded = False
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    second_status, second_body = request_body()
                    if second_status == 200 and second_body == final_body:
                        reload_observed = True
                        included_change_reloaded = True
                        break
                    time.sleep(0.1)
                if first_body != initial_body:
                    raise RuntimeError("reload filter probe started with an unexpected response")
            else:
                (app_directory / "reload_state.py").write_text(
                    'BODY = b"after"\n', encoding="utf-8"
                )
                deadline = time.monotonic() + timeout_seconds
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    second_status, second_body = request_body()
                    if second_status == 200 and second_body == b"after":
                        reload_observed = True
                        break
                    time.sleep(0.2)

        shutdown_signal_sent = False
        if process.poll() is None:
            try:
                process.send_signal(signal.SIGINT)
                shutdown_signal_sent = True
            except OSError:
                process.terminate()
        process_timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            process_timed_out = True
            process.kill()
            process.wait()
        stdout, stderr = process.communicate()
        if len(stdout) > 4 * 1024 * 1024 or len(stderr) > 4 * 1024 * 1024:
            raise RuntimeError("reload probe process output exceeded the 4 MiB bound")

        return {
            "first_response_body_base64": base64.b64encode(
                first_body or b""
            ).decode("ascii"),
            "second_response_body_base64": base64.b64encode(
                second_body or b""
            ).decode("ascii"),
            "reload_observed": reload_observed,
            "excluded_change_reloaded": excluded_change_reloaded,
            "included_change_reloaded": included_change_reloaded,
            "shutdown_signal_sent": shutdown_signal_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
            "workers_ignored_warning": (
                b'"workers" flag is ignored when reloading is enabled.' in stderr
            ),
            "process_stdout_base64": base64.b64encode(stdout).decode("ascii"),
            "process_stderr_base64": base64.b64encode(stderr).decode("ascii"),
        }


def run_http_observation(request: dict) -> dict:
    """Exercise a public Python API or CLI server and signal shutdown."""

    if "request_body_chunks_base64" in request:
        request_body = [
            base64.b64decode(chunk, validate=True)
            for chunk in request["request_body_chunks_base64"]
        ]
    elif "request_body_base64" in request:
        request_body = base64.b64decode(request["request_body_base64"], validate=True)
    else:
        request_body = None
    chunked_request = any(
        name.lower() == "transfer-encoding" and value.lower() == "chunked"
        for name, value in request.get("request_headers", [])
    )
    if chunked_request and isinstance(request_body, bytes):
        request_body = [request_body]
    wsgi_streaming_probe = (
        request.get("application_interface") == "wsgi"
        and request["path"].split("?", 1)[0]
        in {
            "/python-api-wsgi-stream",
            "/python-api-wsgi-after-start-error",
        }
    )

    child_code = r'''
import sys
import os
import base64
import asyncio
import contextvars
import json
import logging
import socket
import time
import uvicorn

lifespan_state = {"started": False}
factory_invoked = False
loop_factory_calls = 0
request_context = contextvars.ContextVar("python_api_request_context", default="empty")
request_context.set("inherited")

_default_loop = asyncio.new_event_loop()
_default_loop_type = type(_default_loop)
_default_loop.close()

class ParityEventLoop(_default_loop_type):
    pass

def custom_loop_factory():
    global loop_factory_calls
    loop_factory_calls += 1
    return ParityEventLoop()

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
    if scope["path"] == "/python-api-second-signal-escalation":
        marker_path = os.environ.get("ASGI_PARITY_SIGNAL_HOLD_MARKER")
        if marker_path is None:
            raise RuntimeError("signal-escalation input is missing its hold marker")
        body = b"python-api-signal-escalation-hold"
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
        with open(marker_path, "a", encoding="utf-8"):
            pass
        await asyncio.Event().wait()
        return
    if scope["path"] == "/contextvars":
        body = request_context.get().encode("ascii")
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
    lifespan_status = b"lifespan-started" if lifespan_state["started"] else b"lifespan-off"
    if "state" not in scope:
        state_status = b"scope-state-missing"
    elif scope["state"] == {}:
        state_status = b"scope-state-empty"
    else:
        state_status = b"scope-state-populated"
    scope_headers = dict(scope.get("headers", []))
    expected_root_path = scope_headers.get(b"x-asgi-expected-root-path-base64")
    expected_path = scope_headers.get(b"x-asgi-expected-path-base64")
    expected_raw_path = scope_headers.get(b"x-asgi-expected-raw-path-base64")
    if (
        expected_root_path is not None
        and expected_path is not None
        and expected_raw_path is not None
    ):
        root_path_matches = scope["root_path"] == base64.b64decode(
            expected_root_path, validate=True
        ).decode("utf-8")
        path_matches = scope["path"] == base64.b64decode(
            expected_path, validate=True
        ).decode("utf-8")
        raw_path_matches = scope["raw_path"] == base64.b64decode(
            expected_raw_path, validate=True
        )
        body = (
            b"asgi-scope-contract-passed"
            if root_path_matches and path_matches and raw_path_matches
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
    if loop_factory_calls:
        body_parts.append(f"loop-factory-calls={loop_factory_calls}".encode("ascii"))
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

class ASGI3CallableInstance:
    async def __call__(self, scope, receive, send):
        await asgi3_app(scope, receive, send)

def wsgi_app(environ, start_response):
    if environ["PATH_INFO"] == "/python-api-wsgi-error":
        raise RuntimeError("python-api-wsgi-probe-error")

    if environ["PATH_INFO"] == "/python-api-wsgi-iterator-before-start-error":
        def response_chunks():
            yield from ()
            raise RuntimeError("python-api-wsgi-iterator-before-start-probe-error")

        return response_chunks()

    if environ["PATH_INFO"] == "/python-api-wsgi-after-start-error":
        start_response("200 OK", [("content-type", "text/plain")])
        marker = os.environ["ASGI_PARITY_WSGI_STREAM_RELEASE_MARKER"]

        def response_chunks():
            yield b"python-api-wsgi-after-start|first"
            deadline = time.monotonic() + 3.0
            while not os.path.exists(marker) and time.monotonic() < deadline:
                time.sleep(0.01)
            raise RuntimeError("python-api-wsgi-after-start-probe-error")

        return response_chunks()

    if environ["PATH_INFO"] == "/python-api-wsgi-stream":
        start_response("200 OK", [("content-type", "text/plain")])
        marker = os.environ["ASGI_PARITY_WSGI_STREAM_RELEASE_MARKER"]
        def response_chunks():
            yield b"python-api-wsgi-stream|first"
            deadline = time.monotonic() + 3.0
            while not os.path.exists(marker) and time.monotonic() < deadline:
                time.sleep(0.01)
            yield b"|released" if os.path.exists(marker) else b"|timed-out"
        return response_chunks()

    body = b"|".join((
        b"python-api-wsgi-ok",
        environ["REQUEST_METHOD"].encode("ascii"),
        environ["PATH_INFO"].encode("latin1"),
        environ["QUERY_STRING"].encode("ascii"),
        environ.get("HTTP_X_PYTHON_API", "missing").encode("latin1"),
    ))
    if environ["REQUEST_METHOD"] == "POST":
        body += b"|request-body=" + environ["wsgi.input"].read()
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
listener_fds = json.loads(sys.argv[27])
reset_contextvars = sys.argv[28] == "1"
ssl_certfile = sys.argv[29] or None
ssl_keyfile = sys.argv[30] or None
host = sys.argv[31]
ssl_keyfile_password = json.loads(sys.argv[32])
ssl_ca_certs = json.loads(sys.argv[33])
ssl_cert_reqs = int(sys.argv[34])
ssl_version = json.loads(sys.argv[35])
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
if os.environ.get("ASGI_PARITY_CALLABLE_INSTANCE") == "1":
    app = ASGI3CallableInstance()
elif os.environ.get("ASGI_PARITY_IMPLICIT_FACTORY") == "1":
    app = app_factory
else:
    app = app_factory if factory else (
        wsgi_app
        if application_interface == "wsgi"
        else asgi2_app if application_interface == "asgi2" else asgi3_app
    )

options = {
    "host": host,
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
    "reset_contextvars": reset_contextvars,
}
if uds_path is not None:
    options["uds"] = uds_path
if ssl_certfile is not None:
    options["ssl_certfile"] = ssl_certfile
    options["ssl_keyfile"] = ssl_keyfile
    if ssl_keyfile_password is not None:
        options["ssl_keyfile_password"] = ssl_keyfile_password
if ssl_ca_certs is not None:
    options["ssl_ca_certs"] = ssl_ca_certs
if ssl_cert_reqs != 0:
    options["ssl_cert_reqs"] = ssl_cert_reqs
if ssl_version is not None:
    options["ssl_version"] = ssl_version
try:
    if invocation in {"config-server", "server-sockets"}:
        if invocation == "server-sockets":
            options.pop("fd", None)
        config = uvicorn.Config(app, **options)
        if invocation == "server-sockets":
            listeners = [socket.socket(fileno=listener_fd) for listener_fd in listener_fds]
            uvicorn.Server(config).run(sockets=listeners)
        else:
            uvicorn.Server(config).run()
    else:
        uvicorn.run(app, **options)
except KeyboardInterrupt:
    if os.environ.get("ASGI_PARITY_COVERAGE_CAPTURE_SHUTDOWN") != "1":
        raise
'''
    uds_directory = None
    uds_path = None
    wsgi_stream_directory = None
    wsgi_stream_release_marker = None
    bind_conflict_listener = None
    inherited_listeners = []
    tls_directory = Path(__file__).resolve().parents[1] / "native-core" / "tls"
    tls_assets = request.get("_tls_assets", {})
    certificate_filename = (
        "localhost-cert-ec.pem"
        if request.get("ssl_keyfile_format") == "traditional-ec-aes256"
        else "localhost-cert.pem"
    )
    tls_certificate = (
        Path(tls_assets["server_certificate"])
        if request.get("tls") and "server_certificate" in tls_assets
        else tls_directory / certificate_filename
        if request.get("tls")
        else None
    )
    key_filename = {
        "unencrypted-rsa-with-password": "localhost-key.pem",
        "pkcs12-pbe-sha1-3des": "localhost-key-pkcs12-pbe-sha1-3des.pem",
        "pkcs12-pbe-sha1-2des": "localhost-key-pkcs12-pbe-sha1-2des.pem",
        "pkcs12-pbe-sha1-3des-zero-iterations": "localhost-key-pkcs12-pbe-sha1-3des-zero-iterations.pem",
        "pkcs12-pbe-sha1-3des-short-ciphertext": "localhost-key-pkcs12-pbe-sha1-3des-short-ciphertext.pem",
        "pkcs12-pbe-sha1-3des-invalid-decrypted-key": "localhost-key-pkcs12-pbe-sha1-3des-invalid-decrypted-key.pem",
        "pkcs12-pbe-sha1-3des-malformed-outer-sequence": "localhost-key-pkcs12-pbe-sha1-3des-malformed-outer-sequence.pem",
        "pkcs12-pbe-sha1-3des-trailing-outer-data": "localhost-key-pkcs12-pbe-sha1-3des-trailing-outer-data.pem",
        "pkcs12-pbe-sha1-3des-missing-algorithm": "localhost-key-pkcs12-pbe-sha1-3des-missing-algorithm.pem",
        "pkcs12-pbe-sha1-3des-invalid-encrypted-data-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-encrypted-data-type.pem",
        "pkcs12-pbe-sha1-3des-trailing-encrypted-info-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-encrypted-info-field.pem",
        "pkcs12-pbe-sha1-3des-invalid-algorithm-oid-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-algorithm-oid-type.pem",
        "pkcs12-pbe-sha1-3des-missing-parameters": "localhost-key-pkcs12-pbe-sha1-3des-missing-parameters.pem",
        "pkcs12-pbe-sha1-3des-trailing-algorithm-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-algorithm-field.pem",
        "pkcs12-pbe-sha1-3des-invalid-salt-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-salt-type.pem",
        "pkcs12-pbe-sha1-3des-missing-iterations": "localhost-key-pkcs12-pbe-sha1-3des-missing-iterations.pem",
        "pkcs12-pbe-sha1-3des-trailing-parameters-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-parameters-field.pem",
        "traditional-rsa-aes128": "localhost-key-rsa-aes128-encrypted.pem",
        "traditional-rsa-aes192": "localhost-key-rsa-aes192-encrypted.pem",
        "traditional-rsa-aes256": "localhost-key-rsa-aes256-encrypted.pem",
        "traditional-rsa-des-ede3": "localhost-key-rsa-3des-encrypted.pem",
        "traditional-ec-aes256": "localhost-key-ec-aes256-encrypted.pem",
        "traditional-rsa-aes256-invalid-proc-type": "localhost-key-rsa-aes256-invalid-proc-type.pem",
        "traditional-rsa-aes256-unknown-header": "localhost-key-rsa-aes256-unknown-header.pem",
        "traditional-rsa-aes256-missing-proc-type": "localhost-key-rsa-aes256-missing-proc-type.pem",
        "traditional-rsa-aes256-missing-dek-info": "localhost-key-rsa-aes256-missing-dek-info.pem",
        "traditional-rsa-aes256-malformed-dek-info": "localhost-key-rsa-aes256-malformed-dek-info.pem",
        "traditional-rsa-aes256-short-iv": "localhost-key-rsa-aes256-short-iv.pem",
        "traditional-rsa-aes256-missing-body": "localhost-key-rsa-aes256-missing-body.pem",
        "traditional-rsa-aes256-missing-end-marker": "localhost-key-rsa-aes256-missing-end-marker.pem",
        "traditional-rsa-aes256-invalid-base64": "localhost-key-rsa-aes256-invalid-base64.pem",
        "traditional-rsa-aes256-empty-body": "localhost-key-rsa-aes256-empty-body.pem",
        "traditional-rsa-aes256-short-ciphertext": "localhost-key-rsa-aes256-short-ciphertext.pem",
        "traditional-rsa-unsupported-cipher": "localhost-key-rsa-unsupported-cipher.pem",
        "traditional-rsa-malformed-begin-line": "localhost-key-rsa-malformed-begin-line.pem",
        "traditional-rsa-empty-key": "localhost-key-rsa-empty-key.pem",
        "traditional-rsa-invalid-utf8": "localhost-key-rsa-invalid-utf8.pem",
        "traditional-dsa-encrypted": "localhost-key-dsa-encrypted.pem",
        "traditional-rsa-malformed-begin-suffix": "localhost-key-rsa-malformed-begin-suffix.pem",
        "traditional-rsa-aes256-high-nonhex-iv": "localhost-key-rsa-aes256-high-nonhex-iv.pem",
        "traditional-rsa-aes256-odd-iv": "localhost-key-rsa-aes256-odd-iv.pem",
        "traditional-rsa-aes256-nonhex-iv": "localhost-key-rsa-aes256-nonhex-iv.pem",
    }.get(
        request.get("ssl_keyfile_format"),
        "localhost-key-pkcs8-encrypted.pem"
        if request.get("ssl_keyfile_password") is not None
        else "localhost-key.pem",
    )
    tls_key = (
        Path(tls_assets["server_key"])
        if request.get("tls") and "server_key" in tls_assets
        else tls_directory / key_filename
        if request.get("tls")
        else None
    )
    ssl_ca_certs = (
        tls_assets.get("ca_certificate")
        if request.get("ssl_ca_certs") == "generated-ca"
        else tls_assets.get("trusted_ca_certificate")
        if request.get("ssl_ca_certs") == "trusted-ca"
        else tls_assets.get("empty_ca_certificate")
        if request.get("ssl_ca_certs") == "empty-ca"
        else tls_assets["missing_ca_certificate"]
        if request.get("ssl_ca_certs") == "missing-ca"
        else tls_assets.get("directory_ca")
        if request.get("ssl_ca_certs") == "directory-ca"
        else tls_assets.get("malformed_ca_certificate")
        if request.get("ssl_ca_certs") == "malformed-ca"
        else tls_assets.get("invalid_der_ca_certificate")
        if request.get("ssl_ca_certs") == "invalid-der-ca"
        else tls_assets.get("non_utf8_ca_certificate")
        if request.get("ssl_ca_certs") == "non-utf8-ca"
        else request.get("ssl_ca_certs")
    )
    ssl_cert_reqs = request.get("ssl_cert_reqs", 0)
    ssl_version = request.get("ssl_version")
    host = request.get("host", "127.0.0.1")
    # Wildcard binding is observed through a concrete loopback destination.
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    configured_environment = request.get("environment", {})
    host_from_environment = configured_environment.get("UVICORN_HOST")
    port_from_environment = configured_environment.get("UVICORN_PORT")
    fd_from_environment = configured_environment.get("UVICORN_FD") == "@probe-fd"
    if host_from_environment is not None and host_from_environment != host:
        raise RuntimeError("UVICORN_HOST must match the requested listener host")
    if port_from_environment not in (None, "@probe-port"):
        raise RuntimeError("UVICORN_PORT must use the @probe-port input marker")
    address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
    if request.get("fd", False):
        if os.name == "nt":
            raise ValueError("inherited descriptor parity input requires Unix")
        listener_count = request.get("prebound_socket_count", 1)
        for _ in range(listener_count):
            inherited_listener = socket.socket(address_family, socket.SOCK_STREAM)
            inherited_listener.bind((host, 0))
            inherited_listener.listen()
            inherited_listener.set_inheritable(True)
            inherited_listeners.append(inherited_listener)
        port = inherited_listeners[0].getsockname()[1]
    elif request.get("uds", False):
        uds_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-", dir="/tmp" if os.path.isdir("/tmp") else None
        )
        uds_path = os.path.join(uds_directory.name, "u.sock")
        if request.get("bind_conflict", False):
            Path(uds_path).touch()
        port = 0
    elif request.get("bind_conflict", False):
        bind_conflict_listener = socket.socket(address_family, socket.SOCK_STREAM)
        bind_conflict_listener.bind((host, 0))
        bind_conflict_listener.listen()
        port = bind_conflict_listener.getsockname()[1]
    else:
        with socket.socket(address_family, socket.SOCK_STREAM) as reservation:
            reservation.bind((host, 0))
            port = reservation.getsockname()[1]

    if request["invocation"] == "module-cli":
        if request.get("callable_instance"):
            app_target = "tests.parity.app:python_api_asgi3_callable_app"
        elif request.get("implicit_factory"):
            app_target = "tests.parity.app:python_api_factory_probe_app"
        elif request.get("uds"):
            app_target = "tests.parity.app:python_api_uds_probe_app"
        elif request.get("factory") and request.get("application_interface") == "wsgi":
            app_target = "tests.parity.app:python_api_wsgi_probe_app_factory"
        elif request.get("factory") and request.get("application_interface") == "asgi2":
            app_target = "tests.parity.app:python_api_asgi2_factory_probe_app"
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
        command = [sys.executable, "-m", "uvicorn", app_target]
        if host_from_environment is None:
            command.extend(("--host", host))
        if port_from_environment != "@probe-port":
            command.extend(("--port", str(port)))
        if not request.get("root_path_from_environment"):
            command.extend(("--root-path", request["root_path"]))
        command.extend(("--lifespan", request["lifespan"]))
        if uds_path is not None:
            command.extend(("--uds", uds_path))
        if tls_certificate is not None and tls_key is not None:
            if "UVICORN_SSL_CERTFILE" not in configured_environment:
                command.extend(("--ssl-certfile", str(tls_certificate)))
            if "UVICORN_SSL_KEYFILE" not in configured_environment:
                command.extend(("--ssl-keyfile", str(tls_key)))
            if (
                request.get("ssl_keyfile_password") is not None
                and "UVICORN_SSL_KEYFILE_PASSWORD" not in configured_environment
            ):
                command.extend(("--ssl-keyfile-password", request["ssl_keyfile_password"]))
        if ssl_ca_certs is not None and "UVICORN_SSL_CA_CERTS" not in configured_environment:
            command.extend(("--ssl-ca-certs", str(ssl_ca_certs)))
        if "ssl_cert_reqs" in request and "UVICORN_SSL_CERT_REQS" not in configured_environment:
            command.extend(("--ssl-cert-reqs", str(ssl_cert_reqs)))
        if "ssl_version" in request and "UVICORN_SSL_VERSION" not in configured_environment:
            command.extend(("--ssl-version", str(ssl_version)))
        if inherited_listeners and not fd_from_environment:
            command.extend(("--fd", str(inherited_listeners[0].fileno())))
        if request.get("factory"):
            command.append("--factory")
        if request.get("interface", "auto") != "auto":
            command.extend(("--interface", request["interface"]))
        for name, value in request.get("headers", []):
            command.extend(("--header", f"{name}:{value}"))
        if request.get("proxy_headers") is not None:
            command.append(
                "--proxy-headers"
                if request["proxy_headers"]
                else "--no-proxy-headers"
            )
        if request.get("forwarded_allow_ips") is not None:
            command.extend(("--forwarded-allow-ips", request["forwarded_allow_ips"]))
        if request.get("limit_concurrency") is not None:
            command.extend(("--limit-concurrency", str(request["limit_concurrency"])))
        if request.get("backlog") is not None:
            command.extend(("--backlog", str(request["backlog"])))
        if request.get("timeout_keep_alive") is not None:
            command.extend(("--timeout-keep-alive", str(request["timeout_keep_alive"])))
        if request.get("timeout_graceful_shutdown") is not None:
            command.extend(
                (
                    "--timeout-graceful-shutdown",
                    str(request["timeout_graceful_shutdown"]),
                )
            )
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
        if request.get("reset_contextvars"):
            command.append("--reset-contextvars")
        if request.get("use_colors") is not None:
            command.append("--use-colors" if request["use_colors"] else "--no-use-colors")
        if request.get("server_header") is not None:
            command.append("--server-header" if request["server_header"] else "--no-server-header")
        if request.get("date_header") is not None:
            command.append("--date-header" if request["date_header"] else "--no-date-header")
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
            str(inherited_listeners[0].fileno()) if inherited_listeners else "",
            json.dumps([listener.fileno() for listener in inherited_listeners]),
            "1" if request.get("reset_contextvars", False) else "0",
            str(tls_certificate) if tls_certificate is not None else "",
            str(tls_key) if tls_key is not None else "",
            host,
            json.dumps(request.get("ssl_keyfile_password")),
            json.dumps(ssl_ca_certs),
            str(ssl_cert_reqs),
            json.dumps(request.get("ssl_version")),
        ]

    environment = subprocess_environment()
    if request.get("callable_instance"):
        environment["ASGI_PARITY_CALLABLE_INSTANCE"] = "1"
    if request.get("implicit_factory"):
        environment["ASGI_PARITY_IMPLICIT_FACTORY"] = "1"
    if wsgi_streaming_probe:
        wsgi_stream_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-wsgi-response-stream-"
        )
        wsgi_stream_release_marker = (
            Path(wsgi_stream_directory.name) / "first-response-byte-received"
        )
        environment["ASGI_PARITY_WSGI_STREAM_RELEASE_MARKER"] = str(
            wsgi_stream_release_marker
        )
    if port_from_environment == "@probe-port":
        if os.environ.get("UVICORN_PORT") != "@probe-port":
            raise RuntimeError(
                "UVICORN_PORT=@probe-port marker was not passed to the probe"
            )
        # The probe reserves a dynamic listener port. Bind that exact port
        # through Click's environment path so the HTTP observer can verify it.
        environment["UVICORN_PORT"] = str(port)
    if fd_from_environment:
        if not inherited_listeners:
            raise RuntimeError("UVICORN_FD=@probe-fd requires an inherited listener")
        environment["UVICORN_FD"] = str(inherited_listeners[0].fileno())
    signal_hold_directory = None
    signal_hold_marker = None
    signal_cancel_marker = None
    if (
        "shutdown_signal_sequence" in request
        or request["path"] == "/python-api-graceful-timeout-hold"
    ):
        if (
            request["invocation"] not in {"api", "module-cli"}
            or request["path"] not in {
                "/python-api-second-signal-escalation",
                "/python-api-graceful-timeout-hold",
            }
        ):
            raise RuntimeError(
                "shutdown signal sequences require a supported public-API hold input"
            )
        signal_hold_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-signal-escalation-"
        )
        signal_hold_marker = Path(signal_hold_directory.name) / "asgi-held"
        environment["ASGI_PARITY_SIGNAL_HOLD_MARKER"] = str(signal_hold_marker)
        if request["path"] == "/python-api-graceful-timeout-hold":
            signal_cancel_marker = Path(signal_hold_directory.name) / "asgi-cancelled"
            environment["ASGI_PARITY_SIGNAL_CANCEL_MARKER"] = str(
                signal_cancel_marker
            )
    worker_crash_directory = None
    worker_crash_count_value = os.environ.get("ASGI_PARITY_WORKER_CRASH_COUNT")
    if worker_crash_count_value is None:
        worker_crash_count_value = (
            "1" if os.environ.get("ASGI_PARITY_WORKER_CRASH_ONCE") == "1" else "0"
        )
    try:
        worker_crash_count = int(worker_crash_count_value)
    except ValueError as error:
        raise RuntimeError("worker crash count must be an integer") from error
    if not 0 <= worker_crash_count <= 8:
        raise RuntimeError("worker crash count must be between 0 and 8")
    if worker_crash_count > 0:
        worker_crash_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-worker-restart-"
        )
        environment["ASGI_PARITY_WORKER_CRASH_ONCE_FILE"] = str(
            Path(worker_crash_directory.name) / "worker-crashed"
        )
        environment["ASGI_PARITY_WORKER_CRASH_COUNT"] = str(worker_crash_count)
    worker_control_signal_value = os.environ.get(
        "ASGI_PARITY_WORKER_CONTROL_SIGNALS", ""
    )
    worker_control_signal_names = (
        worker_control_signal_value.split(",") if worker_control_signal_value else []
    )
    if worker_control_signal_names and (
        os.name == "nt"
        or request["invocation"] != "module-cli"
        or type(request.get("workers")) is not int
        or request["workers"] < 2
        or any(
            name not in {"SIGHUP", "SIGTTIN", "SIGTTOU"}
            or not hasattr(signal, name)
            for name in worker_control_signal_names
        )
    ):
        raise RuntimeError(
            "worker-count signals require a POSIX module-CLI request with at least two workers"
        )
    fail_restart_startup = (
        os.environ.get("ASGI_PARITY_WORKER_CONTROL_FAIL_RESTART_STARTUP") == "1"
    )
    if fail_restart_startup and (
        "SIGHUP" not in worker_control_signal_names
        or request.get("uds")
        or request.get("tls")
        or request.get("fd")
        or request.get("prebound_socket_count")
    ):
        raise RuntimeError(
            "restart-startup failure requires the module-CLI SIGHUP worker-control input"
        )
    worker_control_startup_failure_directory = None
    worker_control_startup_failure_marker = None
    worker_control_startup_ready_directory = None
    if fail_restart_startup:
        worker_control_startup_failure_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-worker-restart-startup-failure-"
        )
        worker_control_startup_ready_directory = (
            Path(worker_control_startup_failure_directory.name) / "startup-ready"
        )
        worker_control_startup_ready_directory.mkdir()
        worker_control_startup_failure_marker = (
            Path(worker_control_startup_failure_directory.name) / "fail-restart-startup"
        )
        environment[
            "ASGI_PARITY_WORKER_CONTROL_FAIL_RESTART_STARTUP_FILE"
        ] = str(worker_control_startup_failure_marker)
        environment["ASGI_PARITY_WORKER_CONTROL_STARTUP_READY_DIR"] = str(
            worker_control_startup_ready_directory
        )
    worker_stall_directory = None
    worker_stall_marker = None
    worker_stall_resumer_stop = threading.Event()
    worker_stall_resumer = None
    if os.environ.get("ASGI_PARITY_WORKER_STALL_ONCE") == "1":
        if os.name == "nt" or not hasattr(signal, "SIGSTOP"):
            raise RuntimeError(
                "worker health-check expiry input requires POSIX SIGSTOP/SIGCONT"
            )
        worker_stall_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-worker-healthcheck-"
        )
        worker_stall_marker = Path(worker_stall_directory.name) / "stalled-worker-pid"
        environment["ASGI_PARITY_WORKER_STALL_ONCE_FILE"] = str(worker_stall_marker)

        def resume_stalled_worker_if_needed() -> None:
            while not worker_stall_resumer_stop.is_set():
                try:
                    worker_pid = int(worker_stall_marker.read_text(encoding="ascii"))
                except (OSError, ValueError):
                    if worker_stall_resumer_stop.wait(0.025):
                        return
                    continue
                resume_delay = max(
                    6.0,
                    float(request.get("timeout_worker_healthcheck", 5)) + 4.0,
                )
                if worker_stall_resumer_stop.wait(resume_delay):
                    return
                try:
                    os.kill(worker_pid, signal.SIGCONT)
                except OSError:
                    pass
                return

        worker_stall_resumer = threading.Thread(
            target=resume_stalled_worker_if_needed,
            name="uvicorn-rs-parity-stalled-worker-resumer",
            daemon=True,
        )
        worker_stall_resumer.start()
    process_options = {}
    shutdown_signal_name = request.get("shutdown_signal", "SIGINT")
    if shutdown_signal_name not in {"SIGINT", "SIGTERM"}:
        raise ValueError("run_http shutdown_signal must be SIGINT or SIGTERM")
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        stop_signal = (
            signal.CTRL_BREAK_EVENT
            if shutdown_signal_name == "SIGINT"
            else signal.SIGTERM
        )
    else:
        stop_signal = getattr(signal, shutdown_signal_name)
        if worker_stall_directory is not None or worker_control_signal_names:
            process_options["start_new_session"] = True
    if inherited_listeners:
        process_options["pass_fds"] = tuple(
            listener.fileno() for listener in inherited_listeners
        )

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
        for inherited_listener in inherited_listeners:
            inherited_listener.close()
        if signal_hold_directory is not None:
            signal_hold_directory.cleanup()
        if bind_conflict_listener is not None:
            bind_conflict_listener.close()
        if uds_directory is not None:
            uds_directory.cleanup()
        if wsgi_stream_directory is not None:
            wsgi_stream_directory.cleanup()
        if worker_crash_directory is not None:
            worker_crash_directory.cleanup()
        if worker_control_startup_failure_directory is not None:
            worker_control_startup_failure_directory.cleanup()
        worker_stall_resumer_stop.set()
        if worker_stall_resumer is not None:
            worker_stall_resumer.join(timeout=1.0)
        if worker_stall_directory is not None:
            worker_stall_directory.cleanup()
        raise

    def kill_server_process_group() -> None:
        if process_options.get("start_new_session"):
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except OSError:
                pass
        if process.poll() is None:
            process.kill()

    def exited_after_worker_signal(signal_name: str) -> RuntimeError:
        return_code = process.poll()
        kill_server_process_group()
        try:
            server_stdout, server_stderr = process.communicate(timeout=1.0)
        except subprocess.TimeoutExpired as error:
            server_stdout = error.output or b""
            server_stderr = error.stderr or b""

        def tail(output: bytes) -> str:
            return output.decode("utf-8", errors="replace")[-2048:]

        return RuntimeError(
            f"worker supervisor exited after receiving {signal_name}; "
            f"exit_code={return_code}; stdout_tail={tail(server_stdout)!r}; "
            f"stderr_tail={tail(server_stderr)!r}"
        )

    response = None
    wsgi_stream_response_started = False
    probe_ports = (
        [listener.getsockname()[1] for listener in inherited_listeners]
        if inherited_listeners
        else [port]
    )
    listener_responses = [None] * len(probe_ports)
    response_count = 0
    idle_connection_closed = None
    connection_timeout = request.get("client_timeout_seconds")
    if connection_timeout is None:
        connection_timeout = (
            5.0
            if worker_crash_count > 0
            or os.environ.get("ASGI_PARITY_WORKER_STALL_ONCE") == "1"
            else 0.5
        )

    def make_client_tls_context() -> ssl.SSLContext:
        # Invalid or absent CA files are inputs for server-side startup
        # rejection. Keep the probe's own TLS trust valid so those startup
        # failures cannot be misreported as client context setup errors.
        trust_anchor = (
            tls_certificate
            if request.get("ssl_ca_certs")
            in {
                "empty-ca",
                "missing-ca",
                "directory-ca",
                "malformed-ca",
                "invalid-der-ca",
                "non-utf8-ca",
            }
            else ssl_ca_certs or tls_certificate
        )
        if trust_anchor is None:
            raise RuntimeError("TLS client context is missing its trust anchor")
        context = ssl.create_default_context(cafile=str(trust_anchor))
        if request.get("ssl_version") == ssl.PROTOCOL_TLSv1_2:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        if request.get("client_tls"):
            client_certificate = tls_assets.get("client_certificate")
            client_key = tls_assets.get("client_key")
            if client_certificate is None or client_key is None:
                raise RuntimeError(
                    "TLS client certificate input has no generated identity"
                )
            context.load_cert_chain(
                certfile=client_certificate,
                keyfile=client_key,
            )
        return context

    request_limit = None
    request_limit_jitter = 0
    limit_environment = request.get("environment", {})
    try:
        if "UVICORN_LIMIT_MAX_REQUESTS" in limit_environment:
            request_limit = int(limit_environment["UVICORN_LIMIT_MAX_REQUESTS"])
        if "UVICORN_LIMIT_MAX_REQUESTS_JITTER" in limit_environment:
            request_limit_jitter = int(
                limit_environment["UVICORN_LIMIT_MAX_REQUESTS_JITTER"]
            )
    except (TypeError, ValueError):
        request_limit = None
        request_limit_jitter = 0
    deadline = time.monotonic() + request["timeout_seconds"]
    try:
        while (
            not request.get("bind_conflict", False)
            and time.monotonic() < deadline
            and process.poll() is None
        ):
            made_progress = False
            for listener_index, listener_port in enumerate(probe_ports):
                if listener_responses[listener_index] is not None:
                    continue
                if uds_path is not None and request.get("tls"):
                    tls_context = make_client_tls_context()
                    connection = UnixHTTPSConnection(
                        uds_path, timeout=connection_timeout, context=tls_context
                    )
                elif uds_path is not None:
                    connection = UnixHTTPConnection(uds_path, timeout=connection_timeout)
                elif request.get("tls"):
                    tls_context = make_client_tls_context()
                    connection = http.client.HTTPSConnection(
                        probe_host,
                        listener_port,
                        timeout=connection_timeout,
                        context=tls_context,
                    )
                else:
                    connection = http.client.HTTPConnection(
                        probe_host, listener_port, timeout=connection_timeout
                    )
                if request.get("http_version") == "1.0":
                    connection._http_vsn = 10
                    connection._http_vsn_str = "HTTP/1.0"
                try:
                    keep_alive_probe_delay = request.get("keep_alive_probe_delay_seconds")
                    connection.request(
                        request["method"],
                        request["path"],
                        body=request_body,
                        encode_chunked=chunked_request,
                        headers={
                            "Connection": "keep-alive" if keep_alive_probe_delay is not None else "close",
                            **dict(request.get("request_headers", [])),
                        },
                    )
                    http_response = connection.getresponse()
                    if wsgi_streaming_probe:
                        wsgi_stream_response_started = True
                        first_byte = http_response.read(1)
                        if first_byte:
                            assert wsgi_stream_release_marker is not None
                            wsgi_stream_release_marker.touch()
                        try:
                            response_body = first_byte + http_response.read()
                        except http.client.IncompleteRead as error:
                            response_body = first_byte + error.partial
                    else:
                        response_body = http_response.read()
                    listener_response = {
                        "status": http_response.status,
                        "content_type": http_response.getheader("content-type"),
                        "body_base64": base64.b64encode(response_body).decode("ascii"),
                        "observed_headers": {
                            name.lower(): http_response.headers.get_all(name, [])
                            for name in request.get("observe_headers", [])
                        },
                    }
                    listener_responses[listener_index] = listener_response
                    response_count += 1
                    made_progress = True
                    if listener_index == 0:
                        response = listener_response
                        if keep_alive_probe_delay is not None:
                            time.sleep(keep_alive_probe_delay)
                            try:
                                connection.request(
                                    request["method"],
                                    request["path"],
                                    body=request_body,
                                    encode_chunked=chunked_request,
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
                except (OSError, http.client.HTTPException, TimeoutError):
                    pass
                finally:
                    connection.close()
            if all(item is not None for item in listener_responses):
                break
            if not made_progress:
                if wsgi_streaming_probe and wsgi_stream_response_started:
                    break
                time.sleep(0.025)

        if request.get("bind_conflict", False) and process.poll() is None:
            try:
                process.wait(timeout=min(1.0, request["timeout_seconds"]))
            except subprocess.TimeoutExpired:
                pass

        if response is not None and request_limit is not None and request_limit > 0:
            if request_limit_jitter > 0:
                max_requests = request_limit + request_limit_jitter
                for _ in range(response_count, max_requests):
                    if process.poll() is not None:
                        break
                    connection = http.client.HTTPConnection(
                        host, port, timeout=0.5
                    )
                    try:
                        connection.request(
                            request["method"],
                            request["path"],
                            body=request_body,
                            encode_chunked=chunked_request,
                            headers={
                                "Connection": "close",
                                **dict(request.get("request_headers", [])),
                            },
                        )
                        additional_response = connection.getresponse()
                        additional_response.read()
                        response_count += 1
                    except (OSError, http.client.HTTPException, TimeoutError):
                        break
                    finally:
                        connection.close()
                    if process.poll() is None:
                        try:
                            process.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            pass
            if process.poll() is None:
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass

        for signal_name in worker_control_signal_names:
            if process.poll() is not None:
                raise RuntimeError(
                    f"worker supervisor exited before {signal_name} could be sent"
                )
            if (
                signal_name == "SIGHUP"
                and worker_control_startup_failure_marker is not None
            ):
                ready_deadline = time.monotonic() + request["timeout_seconds"]
                ready_workers = set()
                while (
                    len(ready_workers) < request["workers"]
                    and process.poll() is None
                    and time.monotonic() < ready_deadline
                ):
                    ready_workers = set(
                        worker_control_startup_ready_directory.glob("*.ready")
                    )
                    if len(ready_workers) < request["workers"]:
                        time.sleep(0.025)
                if len(ready_workers) < request["workers"]:
                    raise RuntimeError(
                        "initial workers did not complete startup before the "
                        "replacement failure was armed; "
                        f"observed={len(ready_workers)} expected={request['workers']}"
                    )
                # Let each worker's supervisor observe the ASGI startup-complete
                # message before the next replacement is deliberately failed.
                time.sleep(0.05)
                worker_control_startup_failure_marker.touch()
            process.send_signal(getattr(signal, signal_name))
            time.sleep(3.0 if signal_name == "SIGHUP" else 1.25)
            if process.poll() is not None:
                raise exited_after_worker_signal(signal_name)

        if worker_control_startup_failure_marker is not None:
            connection = http.client.HTTPConnection(
                host, port, timeout=connection_timeout
            )
            try:
                connection.request(
                    request["method"],
                    request["path"],
                    body=request_body,
                    encode_chunked=chunked_request,
                    headers={
                        "Connection": "close",
                        **dict(request.get("request_headers", [])),
                    },
                )
                followup = connection.getresponse()
                followup_body = followup.read()
                response = {
                    "status": followup.status,
                    "content_type": followup.getheader("content-type"),
                    "body_base64": base64.b64encode(followup_body).decode("ascii"),
                    "observed_headers": {
                        name.lower(): followup.headers.get_all(name, [])
                        for name in request.get("observe_headers", [])
                    },
                }
                listener_responses[0] = response
                response_count += 1
            except (OSError, http.client.HTTPException, TimeoutError):
                response = None
                listener_responses[0] = None
            finally:
                connection.close()

        shutdown_signal_names = request.get(
            "shutdown_signal_sequence", [shutdown_signal_name]
        )
        shutdown_signals_sent = []
        if signal_hold_marker is not None:
            hold_deadline = time.monotonic() + request["timeout_seconds"]
            while (
                not signal_hold_marker.exists()
                and process.poll() is None
                and time.monotonic() < hold_deadline
            ):
                time.sleep(0.01)
            if not signal_hold_marker.exists():
                raise RuntimeError(
                    "signal-escalation ASGI task did not enter its hold before shutdown"
                )
        for index, signal_name in enumerate(shutdown_signal_names):
            if process.poll() is not None:
                break
            if index:
                time.sleep(0.2)
            try:
                process.send_signal(
                    stop_signal
                    if signal_name == shutdown_signal_name
                    else (
                        signal.CTRL_BREAK_EVENT
                        if os.name == "nt" and signal_name == "SIGINT"
                        else getattr(signal, signal_name)
                    )
                )
                shutdown_signals_sent.append(signal_name)
            except OSError:
                break
        shutdown_signal_sent = bool(shutdown_signals_sent)
        server_stdout = b""
        server_stderr = b""
        try:
            server_stdout, server_stderr = process.communicate(
                timeout=request["timeout_seconds"]
            )
            process_timed_out = False
        except subprocess.TimeoutExpired:
            process_timed_out = True
            kill_server_process_group()
            server_stdout, server_stderr = process.communicate()
        request_limit_range_satisfied = None
        if request_limit is not None and request_limit > 0 and request_limit_jitter >= 0:
            request_limit_range_satisfied = (
                request_limit <= response_count <= request_limit + request_limit_jitter
                and not shutdown_signal_sent
                and not process_timed_out
                and process.returncode == 0
            )
        observation = {
            "response_received": bool(listener_responses)
            and all(item is not None for item in listener_responses),
            "response_status": response["status"] if response is not None else None,
            "response_content_type": response["content_type"] if response is not None else None,
            "response_body_base64": response["body_base64"] if response is not None else "",
            "listener_responses": listener_responses,
            "idle_connection_closed": idle_connection_closed,
            "shutdown_signal_sent": shutdown_signal_sent,
            "shutdown_signals_sent": shutdown_signals_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
            "graceful_shutdown_cancellation_observed": (
                signal_cancel_marker is not None and signal_cancel_marker.exists()
            ),
            "request_limit_response_count": response_count,
            "request_limit_range_satisfied": request_limit_range_satisfied,
            "server_stdout_base64": base64.b64encode(server_stdout).decode("ascii"),
            "server_stderr_base64": base64.b64encode(server_stderr).decode("ascii"),
        }
        return observation
    finally:
        if process.poll() is None or process_options.get("start_new_session"):
            kill_server_process_group()
            process.communicate()
        worker_stall_resumer_stop.set()
        if worker_stall_resumer is not None:
            worker_stall_resumer.join(timeout=1.0)
        if uds_directory is not None:
            uds_directory.cleanup()
        if wsgi_stream_directory is not None:
            wsgi_stream_directory.cleanup()
        if signal_hold_directory is not None:
            signal_hold_directory.cleanup()
        if worker_crash_directory is not None:
            worker_crash_directory.cleanup()
        if worker_control_startup_failure_directory is not None:
            worker_control_startup_failure_directory.cleanup()
        if worker_stall_directory is not None:
            worker_stall_directory.cleanup()
        for inherited_listener in inherited_listeners:
            inherited_listener.close()
        if bind_conflict_listener is not None:
            bind_conflict_listener.close()


def run_websocket_observation(request: dict) -> dict:
    """Exercise WebSocket options through the public ``uvicorn.run`` API."""

    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect as websocket_connect
    from websockets.sync.client import unix_connect

    child_code = r'''
import json
import sys
import uvicorn

uds_path = sys.argv[2] or None
observe_scope = sys.argv[5] == "1"

def decode_setting(raw):
    value = json.loads(raw)
    if value == {"$float": "nan"}:
        return float("nan")
    return value

async def app(scope, receive, send):
    if scope["type"] != "websocket":
        return
    message = await receive()
    if message["type"] != "websocket.connect":
        return
    await send({"type": "websocket.accept"})
    if observe_scope:
        server = scope["server"]
        await send({
            "type": "websocket.send",
            "text": json.dumps({
                "client_is_none": scope["client"] is None,
                "path": scope["path"],
                "scheme": scope["scheme"],
                "server_path_matches": (
                    server is not None and server[0] == uds_path
                ),
                "server_port_is_none": server is not None and server[1] is None,
            }, sort_keys=True),
        })
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
    uds=uds_path,
    ws_max_size=int(sys.argv[3]),
    ws_max_queue=int(sys.argv[4]),
    ws_ping_interval=decode_setting(sys.argv[6]),
    ws_ping_timeout=decode_setting(sys.argv[7]),
    ws_per_message_deflate=sys.argv[8] == "1",
)
'''
    uds_directory = None
    uds_path = None
    if request.get("uds", False):
        uds_directory = tempfile.TemporaryDirectory(
            prefix="uvrs-ws-", dir="/tmp" if os.path.isdir("/tmp") else None
        )
        uds_path = os.path.join(uds_directory.name, "u.sock")
        port = 0
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]

    environment = subprocess_environment()
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
            uds_path or "",
            str(request["ws_max_size"]),
            str(request.get("ws_max_queue", 32)),
            "1" if request.get("observe_scope", False) else "0",
            json.dumps(request.get("ws_ping_interval", 20)),
            json.dumps(request.get("ws_ping_timeout", 20)),
            "0" if request.get("ws_per_message_deflate") is False else "1",
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
    scope_observation = None
    compression_negotiated = None
    try:
        uri = f"ws://127.0.0.1:{port}{request['path']}"
        while time.monotonic() < deadline and process.poll() is None:
            try:
                connect_options = {
                    "open_timeout": min(0.5, max(deadline - time.monotonic(), 0.01)),
                    "close_timeout": 0.5,
                    "max_size": None,
                    "legacy": True,
                }
                if uds_path is not None:
                    connection = unix_connect(uds_path, uri, **connect_options)
                else:
                    connection = websocket_connect(uri, **connect_options)
                handshake_status = 101
                break
            except InvalidStatus as error:
                handshake_status = error.response.status_code
                break
            except (OSError, TimeoutError):
                time.sleep(0.025)

        if connection is not None:
            try:
                if request.get("observe_compression"):
                    compression_negotiated = any(
                        type(extension).__name__ == "PerMessageDeflate"
                        for extension in connection.protocol.extensions
                    )
                if request.get("observe_scope"):
                    scope_observation = json.loads(
                        connection.recv(
                            timeout=max(deadline - time.monotonic(), 0.01)
                        )
                    )
                if request.get("keepalive_idle_seconds"):
                    time.sleep(request["keepalive_idle_seconds"])
                try:
                    connection.send(request["message"])
                    try:
                        connection.recv(timeout=max(deadline - time.monotonic(), 0.01))
                        message_received = True
                    except ConnectionClosed as error:
                        if error.rcvd is not None:
                            close_code = error.rcvd.code
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
            "scope_observation": scope_observation,
            "shutdown_signal_sent": shutdown_signal_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
        }
        if (
            handshake_status != 101
            or close_code is None
            or process.returncode != 0
            or process_timed_out
        ):
            observation["server_stdout_base64"] = base64.b64encode(server_stdout).decode("ascii")
            observation["server_stderr_base64"] = base64.b64encode(server_stderr).decode("ascii")
        if request.get("observe_compression"):
            observation["compression_negotiated"] = compression_negotiated
        return observation
    finally:
        if connection is not None:
            connection.close()
        if process.poll() is None:
            process.kill()
            process.communicate()
        if uds_directory is not None:
            uds_directory.cleanup()


async def server_readiness_observation() -> dict[str, object]:
    import uvicorn

    startup_received = asyncio.Event()
    allow_startup = asyncio.Event()
    http_received = asyncio.Event()
    allow_http_response = asyncio.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

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
            http_received.set()
            await allow_http_response.wait()
            if scope["path"] == "/no-content":
                await send({"type": "http.response.start", "status": 204, "headers": []})
                await send({"type": "http.response.body", "body": b""})
            else:
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"ready"})

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        loop="asyncio",
        http="httptools",
        lifespan="on",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    jittered_server = uvicorn.Server(
        uvicorn.Config(
            app,
            limit_max_requests=3,
            limit_max_requests_jitter=2,
            log_config=None,
            access_log=False,
        )
    )
    selected_request_limit = jittered_server.limit_max_requests
    request_limit_observation = {
        "none_stays_none": server.limit_max_requests is None,
        "jitter_is_in_range": selected_request_limit is not None
        and 3 <= selected_request_limit <= 5,
        "jitter_is_cached": selected_request_limit
        == jittered_server.limit_max_requests,
    }
    state = server.server_state
    initial_server_state = {
        "present": isinstance(state, uvicorn.server.ServerState),
        "total_requests": state.total_requests,
        "connection_count": len(state.connections),
        "task_count": len(state.tasks),
        "default_headers": state.default_headers,
        "last_notified": server.last_notified,
    }
    response_received = threading.Event()
    release_client = threading.Event()
    request_outcome: dict[str, int] = {}
    task = asyncio.create_task(server.serve())
    request_task = None
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

        def request(
            path: str,
            response_received: threading.Event,
            release_client: threading.Event,
            outcome: dict[str, int],
        ) -> int:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                connection.request("GET", path)
                response = connection.getresponse()
                response.read()
                outcome["status"] = response.status
                response_received.set()
                release_client.wait(timeout=5)
                return outcome["status"]
            finally:
                connection.close()

        request_task = asyncio.create_task(
            asyncio.to_thread(request, "/", response_received, release_client, request_outcome)
        )
        await asyncio.wait_for(http_received.wait(), timeout=5)
        in_flight_state = {
            "total_requests": state.total_requests,
            "task_count": len(state.tasks),
        }
        allow_http_response.set()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while not response_received.is_set() and not request_task.done() and loop.time() < deadline:
            await asyncio.sleep(0.001)
        if not response_received.is_set():
            raise TimeoutError("HTTP client did not receive the response")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5
        while state.tasks and loop.time() < deadline:
            await asyncio.sleep(0)
        completed_request_state = {
            "total_requests": state.total_requests,
            "task_count": len(state.tasks),
        }
        default_header_names = [name.decode("ascii") for name, _ in state.default_headers]
        response_status = request_outcome["status"]
        release_client.set()
        await asyncio.wait_for(request_task, timeout=5)

        no_content_received = threading.Event()
        release_no_content_client = threading.Event()
        no_content_outcome: dict[str, int] = {}
        no_content_task = asyncio.create_task(
            asyncio.to_thread(
                request,
                "/no-content",
                no_content_received,
                release_no_content_client,
                no_content_outcome,
            )
        )
        deadline = loop.time() + 5
        while not no_content_received.is_set() and not no_content_task.done() and loop.time() < deadline:
            await asyncio.sleep(0.001)
        if not no_content_received.is_set():
            raise TimeoutError("HTTP client did not receive the bodyless response")
        deadline = loop.time() + 5
        while (state.total_requests < 2 or state.tasks) and loop.time() < deadline:
            await asyncio.sleep(0)
        bodyless_request_state = {
            "total_requests": state.total_requests,
            "task_count": len(state.tasks),
        }
        release_no_content_client.set()
        await asyncio.wait_for(no_content_task, timeout=5)

        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)
        started_after_serve_return = bool(server.started)
        return {
            "initial_server_state": initial_server_state,
            "request_limit": request_limit_observation,
            "in_flight_state": in_flight_state,
            "completed_request_state": completed_request_state,
            "bodyless_request_state": bodyless_request_state,
            "default_header_names_after_startup": default_header_names,
            "response_status": response_status,
            "started_before_lifespan_complete": started_before_lifespan_complete,
            "started_after_lifespan_complete": started_after_lifespan_complete,
            "started_after_serve_return": started_after_serve_return,
        }
    finally:
        allow_startup.set()
        allow_http_response.set()
        release_client.set()
        if "release_no_content_client" in locals():
            release_no_content_client.set()
        if "no_content_task" in locals() and not no_content_task.done():
            await asyncio.gather(no_content_task, return_exceptions=True)
        if request_task is not None and not request_task.done():
            await asyncio.gather(request_task, return_exceptions=True)
        if not task.done():
            server.should_exit = True
            await asyncio.gather(task, return_exceptions=True)


async def server_serve_cancellation_observation(phase: str) -> dict[str, bool]:
    """Observe public serve-task cancellation during or after lifespan startup."""
    import uvicorn

    startup_entered = asyncio.Event()
    allow_startup_completion = asyncio.Event()

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    startup_entered.set()
                    if phase == "during-startup":
                        await allow_startup_completion.wait()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        elif scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            loop="asyncio",
            lifespan="on" if phase == "during-startup" else "off",
            log_config=None,
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        if phase == "during-startup":
            await asyncio.wait_for(startup_entered.wait(), timeout=5)
        else:
            for _ in range(500):
                if server.started:
                    break
                if task.done():
                    await task
                    break
                await asyncio.sleep(0.01)
        started_before_cancel = bool(server.started)
        if phase == "after-startup" and not started_before_cancel:
            raise RuntimeError("server did not become ready before cancellation probe")

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            serve_cancelled = True
        else:
            serve_cancelled = False

        await asyncio.sleep(0)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            listener_accepting_after_cancel = probe.connect_ex(("127.0.0.1", port)) == 0
        return {
            "lifespan_startup_entered_before_cancel": startup_entered.is_set(),
            "server_started_before_cancel": started_before_cancel,
            "serve_cancelled": serve_cancelled,
            "serve_task_finished": task.done(),
            "listener_accepting_after_cancel": listener_accepting_after_cancel,
        }
    finally:
        allow_startup_completion.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def server_startup_cancel_before_listener_observation(
    lifespan_mode: str = "on",
) -> dict[str, object]:
    """Cancel startup before bind and verify lifespan shutdown still runs."""

    target = os.environ.get("ASGI_PARITY_SERVER_ID") == "uvicorn-rs"
    startup_entered = asyncio.Event()
    allow_startup_completion = asyncio.Event()
    application_events = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                application_events.append(message["type"])
                if message["type"] == "lifespan.startup":
                    startup_entered.set()
                    await allow_startup_completion.wait()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

    if target:
        from uvicorn_rs import Server

        server = Server(app, host="127.0.0.1", port=0, lifespan=lifespan_mode)
    else:
        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                loop="asyncio",
                lifespan=lifespan_mode,
                log_config=None,
                access_log=False,
            )
        )

    task = asyncio.create_task(server.serve())
    serve_cancelled = False
    serve_raised = False
    serve_timed_out = False
    try:
        if lifespan_mode == "off":
            if target:
                # The serve coroutine publishes its native control before it
                # schedules the Rust future. Cancel in that handoff window so
                # startup observes cancellation before the no-lifespan branch
                # can bind a listener.
                await asyncio.sleep(0)
                server_started_before_cancel = bool(
                    getattr(server, "started", False)
                )
                server.cancel_startup()
                server.shutdown()
            else:
                server_started_before_cancel = bool(
                    getattr(server, "started", False)
                )
                server.should_exit = True
        else:
            await asyncio.wait_for(startup_entered.wait(), timeout=5)
            server_started_before_cancel = bool(getattr(server, "started", False))
            if target:
                server.cancel_startup()
                server.shutdown()
            else:
                server.should_exit = True

        allow_startup_completion.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.CancelledError:
            serve_cancelled = True
        except asyncio.TimeoutError:
            serve_timed_out = True
        except BaseException:
            serve_raised = True
        return {
            "lifespan_startup_entered_before_cancel": startup_entered.is_set(),
            "server_started_before_cancel": server_started_before_cancel,
            "serve_cancelled": serve_cancelled,
            "serve_raised": serve_raised,
            "serve_timed_out": serve_timed_out,
            "serve_task_finished": task.done(),
            "application_events": application_events,
            "server_started_before_shutdown": bool(
                getattr(server, "started", False)
            ),
        }
    finally:
        allow_startup_completion.set()
        if not task.done():
            if target:
                server.shutdown()
            else:
                server.should_exit = True
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def server_startup_cancel_during_prebound_transfer_observation(
    lifespan_mode: str = "on",
) -> dict[str, object]:
    """Cancel while the inherited-listener transfer is held before delivery."""

    target = os.environ.get("ASGI_PARITY_SERVER_ID") == "uvicorn-rs"
    startup_entered = asyncio.Event()
    allow_startup_completion = asyncio.Event()
    shutdown_complete = asyncio.Event()
    application_events = []
    transfer_started = threading.Event()
    allow_transfer = threading.Event()
    bridge = None
    original_send_listener_fds = None

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                application_events.append(message["type"])
                if message["type"] == "lifespan.startup":
                    startup_entered.set()
                    await allow_startup_completion.wait()
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    shutdown_complete.set()
                    return

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    if target:
        from uvicorn_rs import Server, _bridge

        bridge = _bridge
        original_send_listener_fds = bridge.send_listener_fds

        def hold_listener_transfer(path, listeners, stop_event=None):
            transfer_started.set()
            if not allow_transfer.wait(timeout=5):
                raise TimeoutError("listener-transfer probe was not released")
            return original_send_listener_fds(path, listeners, stop_event)

        bridge.send_listener_fds = hold_listener_transfer
        server = Server(
            app,
            host="127.0.0.1",
            port=0,
            sockets=[listener],
            lifespan=lifespan_mode,
        )
        task = asyncio.create_task(server.serve())
    else:
        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                loop="asyncio",
                lifespan=lifespan_mode,
                log_config=None,
                access_log=False,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))

    serve_cancelled = False
    serve_raised = False
    serve_timed_out = False
    server_started_before_cancel = False
    listener_transfer_blocked = False
    try:
        if lifespan_mode == "off":
            server_started_before_cancel = bool(getattr(server, "started", False))
            if target:
                listener_transfer_blocked = await asyncio.wait_for(
                    asyncio.to_thread(transfer_started.wait, 5), timeout=5
                )
                if not listener_transfer_blocked:
                    raise RuntimeError("listener transfer did not enter its hold")
                server.shutdown()
                allow_transfer.set()
            else:
                server.should_exit = True
        else:
            await asyncio.wait_for(startup_entered.wait(), timeout=5)
            server_started_before_cancel = bool(getattr(server, "started", False))
            if target:
                allow_startup_completion.set()
                listener_transfer_blocked = await asyncio.wait_for(
                    asyncio.to_thread(transfer_started.wait, 5), timeout=5
                )
                if not listener_transfer_blocked:
                    raise RuntimeError("listener transfer did not enter its hold")
                server.shutdown()
                await asyncio.wait_for(shutdown_complete.wait(), timeout=5)
                allow_transfer.set()
            else:
                server.should_exit = True
                allow_startup_completion.set()

        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.CancelledError:
            serve_cancelled = True
        except asyncio.TimeoutError:
            serve_timed_out = True
        except BaseException:
            serve_raised = True
        return {
            "lifespan_startup_entered_before_cancel": startup_entered.is_set(),
            "server_started_before_cancel": server_started_before_cancel,
            "serve_cancelled": serve_cancelled,
            "serve_raised": serve_raised,
            "serve_timed_out": serve_timed_out,
            "serve_task_finished": task.done(),
            "application_events": application_events,
            "server_started_before_shutdown": bool(
                getattr(server, "started", False)
            ),
            "listener_transfer_blocked": listener_transfer_blocked,
        }
    finally:
        allow_startup_completion.set()
        allow_transfer.set()
        if not task.done():
            if target:
                server.shutdown()
            else:
                server.should_exit = True
            try:
                await asyncio.wait_for(task, timeout=5)
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if bridge is not None and original_send_listener_fds is not None:
            bridge.send_listener_fds = original_send_listener_fds
        listener.close()


async def server_callback_notify_observation() -> dict[str, int | bool]:
    import uvicorn

    callback_count = 0
    server = None

    async def app(scope, receive, send):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    async def callback_notify():
        nonlocal callback_count
        callback_count += 1
        server.should_exit = True

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        loop="asyncio",
        http="httptools",
        lifespan="off",
        log_config=None,
        access_log=False,
        timeout_notify=0,
        callback_notify=callback_notify,
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    serve_timed_out = False
    try:
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            serve_timed_out = True
            server.should_exit = True
            await asyncio.gather(task, return_exceptions=True)
        return {
            "callback_count": callback_count,
            "server_started": bool(server.started),
            "serve_timed_out": serve_timed_out,
        }
    finally:
        if not task.done():
            server.should_exit = True
            await asyncio.gather(task, return_exceptions=True)


async def server_on_tick_observation(request: dict) -> dict:
    import uvicorn

    callback_count = 0

    async def app(scope, receive, send):
        return None

    async def callback_notify():
        nonlocal callback_count
        callback_count += 1

    config = uvicorn.Config(app, **request["options"])
    config.load()
    if request.get("callback_notify"):
        config.callback_notify = callback_notify
        config.timeout_notify = -1

    server = uvicorn.Server(config)
    server.server_state.total_requests = request["total_requests"]
    should_exit = await server.on_tick(request["counter"])
    default_headers = []
    for name, value in server.server_state.default_headers:
        if name == b"date":
            value = b"<date>"
        default_headers.append([name.decode(), value.decode()])

    return {
        "callback_count": callback_count,
        "default_headers": default_headers,
        "limit_max_requests": server.limit_max_requests,
        "notification_sent": server.last_notified > 0,
        "server_main_loop_signature": signature(uvicorn.Server.main_loop),
        "server_on_tick_signature": signature(uvicorn.Server.on_tick),
        "should_exit": should_exit,
    }


async def server_lifecycle_observation(request: dict) -> dict:
    import uvicorn

    async def app(scope, receive, send):
        return None

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        loop="asyncio",
        lifespan="off",
        log_level="warning",
    )
    config.load()
    server = uvicorn.Server(config)
    # Uvicorn initializes its lifespan object in _serve before calling the
    # public startup method. The adapter's native lifecycle owns that setup.
    if hasattr(config, "lifespan_class") and not hasattr(server, "lifespan"):
        server.lifespan = config.lifespan_class(config)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    try:
        if request["stop_phase"] == "before_startup":
            server.should_exit = True
        await server.startup(sockets=[listener])
        started_after_startup = bool(server.started)
        listener_open_after_startup = listener.fileno() >= 0
        if request["stop_phase"] == "after_startup":
            server.should_exit = True
        await server.main_loop()
        await server.shutdown(sockets=[listener])
        return {
            "listener_closed_after_shutdown": listener.fileno() == -1,
            "listener_open_after_startup": listener_open_after_startup,
            "server_main_loop_signature": signature(uvicorn.Server.main_loop),
            "server_shutdown_signature": signature(uvicorn.Server.shutdown),
            "server_started_after_shutdown": bool(server.started),
            "server_startup_signature": signature(uvicorn.Server.startup),
            "started_after_startup": started_after_startup,
        }
    finally:
        if listener.fileno() >= 0:
            listener.close()


def server_signal_handling_observation(request: dict) -> dict:
    import signal
    import uvicorn

    async def app(scope, receive, send):
        return None

    sequences = []
    for signal_names in request["sequences"]:
        server = uvicorn.Server(uvicorn.Config(app))
        states = []
        for signal_name in signal_names:
            server.handle_exit(getattr(signal, signal_name), None)
            states.append(
                {
                    "force_exit": server.force_exit,
                    "should_exit": server.should_exit,
                }
            )
        sequences.append(states)

    return {
        "server_capture_signals_signature": signature(uvicorn.Server.capture_signals),
        "server_handle_exit_signature": signature(uvicorn.Server.handle_exit),
        "sequences": sequences,
    }


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
            host="256.256.256.256",
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


async def server_startup_bind_failure_lifespan_observation() -> dict[str, object]:
    """Verify lifespan cleanup when listener setup fails after startup."""
    import uvicorn

    global _startup_bind_failure_lifespan_state

    application_events = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                application_events.append(message["type"])
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="256.256.256.256",
            port=0,
            loop="asyncio",
            lifespan="on",
            log_config=None,
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    _startup_bind_failure_lifespan_state = {
        "server": server,
        "task": task,
        "application_events": application_events,
    }
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
        "application_events": application_events,
    }


async def server_startup_uds_replacement_lifespan_observation() -> dict[str, object]:
    """Verify Uvicorn replaces an existing UDS path and shuts down lifespan."""
    import uvicorn

    global _startup_uds_replacement_lifespan_state

    application_events = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                application_events.append(message["type"])
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

    _startup_uds_replacement_lifespan_state = None
    with tempfile.TemporaryDirectory(prefix="urs-") as directory:
        socket_path = str(Path(directory) / "server.sock")
        blocker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server = None
        task = None
        raised = False
        timed_out = False
        try:
            blocker.bind(socket_path)
            blocker.listen(1)
            server = uvicorn.Server(
                uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=0,
                    uds=socket_path,
                    loop="asyncio",
                    lifespan="on",
                    log_config=None,
                    access_log=False,
                )
            )
            task = asyncio.create_task(server.serve())
            _startup_uds_replacement_lifespan_state = {
                "server": server,
                "task": task,
                "application_events": application_events,
            }
            try:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 5
                while not server.started and not task.done() and loop.time() < deadline:
                    await asyncio.sleep(0.001)
                if not server.started:
                    if task.done():
                        raised = True
                    else:
                        timed_out = True
                else:
                    server.should_exit = True
                    await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except TimeoutError:
                if task.done():
                    raised = True
                else:
                    timed_out = True
            except BaseException:
                raised = True
        finally:
            if task is not None and not task.done():
                server.should_exit = True
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            blocker.close()
        if server is None or task is None:
            raise RuntimeError("UDS replacement probe did not create its server")
        return {
            "server_started": bool(server.started),
            "serve_task_finished": task.done(),
            "serve_raised": raised,
            "serve_timed_out": timed_out,
            "application_events": application_events,
        }


async def server_startup_failure_waiter_observation() -> dict[str, object]:
    """Compare a concurrent startup-failure waiter with Uvicorn startup status."""

    global _startup_failure_waiter_state

    target = os.environ.get("ASGI_PARITY_SERVER_ID") == "uvicorn-rs"
    lifespan_entered = asyncio.Event()
    release_failure = asyncio.Event()

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            message = await receive()
            if message["type"] == "lifespan.startup":
                lifespan_entered.set()
                await release_failure.wait()
                await send(
                    {
                        "type": "lifespan.startup.failed",
                        "message": "parity startup failure",
                    }
                )

    if target:
        from uvicorn_rs import Server, _native

        server = Server(
            app,
            host="127.0.0.1",
            port=0,
            lifespan="on",
            _defer_startup_failure=True,
        )
    else:
        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                loop="asyncio",
                lifespan="on",
                log_config=None,
                access_log=False,
            )
        )

    task = asyncio.create_task(server.serve())
    waiter = None
    _startup_failure_waiter_state = {
        "server": server,
        "task": task,
        "startup_failure_wait_result": None,
        "dropped_control_wait_result": None,
    }
    try:
        await asyncio.wait_for(lifespan_entered.wait(), timeout=5)
        if target:
            waiter = asyncio.create_task(server.wait_startup_failed())
            _startup_failure_waiter_state["waiter"] = waiter
            await asyncio.sleep(0)

            control = _native.ServerControl(False)
            dropped_waiter = control.wait_startup_failed()
            del control
            dropped_control_wait_result = await asyncio.wait_for(
                dropped_waiter, timeout=5
            )
            _startup_failure_waiter_state[
                "dropped_control_wait_result"
            ] = dropped_control_wait_result

        release_failure.set()
        if target:
            startup_failure_wait_result = await asyncio.wait_for(waiter, timeout=5)
            _startup_failure_waiter_state[
                "startup_failure_wait_result"
            ] = startup_failure_wait_result
            await asyncio.wait_for(task, timeout=5)
        else:
            try:
                await asyncio.wait_for(task, timeout=5)
            except BaseException:
                # Uvicorn reports an explicit lifespan startup failure by
                # terminating serve with SystemExit(3).
                pass
            startup_failure_wait_result = not server.started and task.done()
            _startup_failure_waiter_state[
                "startup_failure_wait_result"
            ] = startup_failure_wait_result
    finally:
        release_failure.set()
        if not task.done():
            server.should_exit = True
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return startup_failure_waiter_result_from_state(_startup_failure_waiter_state)


def startup_failure_waiter_result_from_state(state) -> dict[str, object]:
    """Collect stable startup observations even if Uvicorn SystemExit stops the loop."""

    state = state or {}
    server = state.get("server")
    task = state.get("task")
    startup_failure_wait_result = state.get("startup_failure_wait_result")
    if startup_failure_wait_result is None and server is not None and task is not None:
        startup_failure_wait_result = not bool(getattr(server, "started", False)) and task.done()
    return {
        "startup_failure_wait_result": startup_failure_wait_result,
        "dropped_control_wait_result": state.get("dropped_control_wait_result"),
        "server_started_before_shutdown": bool(
            server is not None and getattr(server, "started", False)
        ),
        "serve_task_finished_before_shutdown": bool(task and task.done()),
    }


async def server_lifespan_startup_observation(request: dict) -> dict[str, object]:
    """Observe strict lifespan startup through the public Config and Server APIs."""

    import uvicorn

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            if request["app_lifespan"] == "raises-before-startup":
                raise RuntimeError("parity lifespan startup exception")
            if request["app_lifespan"] == "unexpected-startup-event":
                startup = await receive()
                if startup["type"] == "lifespan.startup":
                    await send({"type": "lifespan.shutdown.complete"})
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


async def server_lifespan_mode_observation(request: dict) -> dict[str, object]:
    """Compare direct-server lifespan values with Uvicorn's public API."""

    server_id = os.environ.get("ASGI_PARITY_SERVER_ID")
    target = server_id == "uvicorn-rs"
    events = []

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                events.append(message["type"])
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

    mode = request["mode"]
    server_started = False
    serve_raised = False
    listener = None

    try:
        if mode == "boolean-disabled" and request.get("prebound_listener", False):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
        if target:
            from uvicorn_rs import Server

            if mode == "boolean-disabled":
                lifespan = False
            elif mode == "boolean-enabled":
                lifespan = True
            elif mode == "invalid-type":
                lifespan = 1
            else:
                lifespan = "not-a-lifespan-mode"
            server = Server(
                app,
                host="127.0.0.1",
                port=0,
                sockets=[listener] if listener is not None else None,
                limit_max_requests=request.get("limit_max_requests"),
                limit_max_requests_jitter=request.get("limit_max_requests_jitter", 0),
                lifespan=lifespan,
            )
        else:
            import uvicorn

            if mode == "boolean-disabled":
                lifespan = "off"
            elif mode == "boolean-enabled":
                lifespan = "auto"
            elif mode == "invalid-type":
                lifespan = 1
            else:
                lifespan = "not-a-lifespan-mode"
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=0,
                loop="asyncio",
                lifespan=lifespan,
                limit_max_requests=request.get("limit_max_requests"),
                limit_max_requests_jitter=request.get("limit_max_requests_jitter", 0),
                log_config=None,
                access_log=False,
            )
            server = uvicorn.Server(config)

        serve = (
            server.serve(sockets=[listener])
            if not target and listener is not None
            else server.serve()
        )
        task = asyncio.create_task(serve)
        if mode in {"boolean-disabled", "boolean-enabled"}:
            if target:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 5
                while not server_started and not task.done() and loop.time() < deadline:
                    server_started = await server.wait_started()
                    if not server_started:
                        await asyncio.sleep(0.001)
                if not server_started:
                    raise TimeoutError("direct server did not finish startup")
                server.cancel_startup()
                await asyncio.wait_for(task, timeout=5)
            else:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 5
                while not server.started and not task.done() and loop.time() < deadline:
                    await asyncio.sleep(0.001)
                server_started = bool(server.started)
                if not server_started:
                    raise TimeoutError("Uvicorn server did not finish startup")
                server.should_exit = True
                await asyncio.wait_for(task, timeout=5)
        else:
            try:
                await asyncio.wait_for(task, timeout=2)
            except (AssertionError, KeyError, ValueError):
                serve_raised = True
            except TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    except (AssertionError, KeyError, ValueError):
        serve_raised = True
    finally:
        if "task" in locals() and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if listener is not None and listener.fileno() >= 0:
            listener.close()

    return {
        "server_started_before_shutdown": server_started,
        "serve_raised": serve_raised,
        "application_events": events,
    }


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
    environment = subprocess_environment()
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
    if "run_http_reload" in request:
        observations = {
            "run_http_reload": run_http_reload_observation(
                request["run_http_reload"]
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
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
    if "server_on_tick" in request:
        observations = {
            "server_on_tick": asyncio.run(
                server_on_tick_observation(request["server_on_tick"])
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_lifecycle" in request:
        observations = {
            "server_lifecycle": asyncio.run(
                server_lifecycle_observation(request["server_lifecycle"])
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_signals" in request:
        observations = {
            "server_signals": server_signal_handling_observation(
                request["server_signals"]
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_readiness" in request:
        observations = {
            "server_readiness": asyncio.run(server_readiness_observation()),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_serve_cancellation" in request:
        observations = {
            "server_serve_cancellation": asyncio.run(
                server_serve_cancellation_observation(
                    request["server_serve_cancellation"]["phase"]
                )
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_cancel_before_listener" in request:
        observations = {
            "server_startup_cancel_before_listener": asyncio.run(
                server_startup_cancel_before_listener_observation()
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_cancel_without_lifespan" in request:
        observations = {
            "server_startup_cancel_before_listener": asyncio.run(
                server_startup_cancel_before_listener_observation("off")
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_cancel_during_prebound_transfer" in request:
        observations = {
            "server_startup_cancel_before_listener": asyncio.run(
                server_startup_cancel_during_prebound_transfer_observation()
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_cancel_during_prebound_transfer_without_lifespan" in request:
        observations = {
            "server_startup_cancel_before_listener": asyncio.run(
                server_startup_cancel_during_prebound_transfer_observation("off")
            ),
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_callback_notify" in request:
        observations = {
            "server_callback_notify": asyncio.run(
                server_callback_notify_observation()
            ),
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
    if "server_startup_bind_failure_lifespan_cleanup" in request:
        try:
            observation = asyncio.run(
                server_startup_bind_failure_lifespan_observation()
            )
        except BaseException:
            state = _startup_bind_failure_lifespan_state or {}
            server = state.get("server")
            task = state.get("task")
            observation = {
                "server_started": bool(
                    server is not None and getattr(server, "started", False)
                ),
                "serve_task_finished": bool(task and task.done()),
                "serve_raised": True,
                "serve_timed_out": False,
                "application_events": state.get("application_events", []),
            }
        observations = {"server_startup_bind_failure_lifespan_cleanup": observation}
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_uds_socket_replacement_lifespan_cleanup" in request:
        try:
            observation = asyncio.run(
                server_startup_uds_replacement_lifespan_observation()
            )
        except BaseException:
            state = _startup_uds_replacement_lifespan_state or {}
            server = state.get("server")
            task = state.get("task")
            observation = {
                "server_started": bool(
                    server is not None and getattr(server, "started", False)
                ),
                "serve_task_finished": bool(task and task.done()),
                "serve_raised": True,
                "serve_timed_out": False,
                "application_events": state.get("application_events", []),
            }
        observations = {
            "server_startup_uds_socket_replacement_lifespan_cleanup": observation
        }
        print(json.dumps(observations, sort_keys=True, separators=(",", ":")))
        return
    if "server_startup_failure_waiter" in request:
        try:
            observation = asyncio.run(server_startup_failure_waiter_observation())
        except BaseException:
            observation = startup_failure_waiter_result_from_state(
                _startup_failure_waiter_state
            )
        observations = {"server_startup_failure_waiter": observation}
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
    if "server_lifespan_mode" in request:
        observations = {
            "server_lifespan_mode": asyncio.run(
                server_lifespan_mode_observation(request["server_lifespan_mode"])
            ),
        }
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
    if "config_probes" in request:
        from uvicorn.config import Config

        observations["config_probes"] = []
        for probe in request["config_probes"]:
            config = Config(probe["app"], **probe["options"])
            properties = {}
            for name in probe["properties"]:
                try:
                    properties[name] = getattr(config, name)
                except BaseException as error:
                    properties[name] = {
                        "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                        "error": str(error),
                    }
            methods = []
            for name in probe["methods"]:
                try:
                    getattr(config, name)()
                    result = {"returned": True}
                except BaseException as error:
                    result = {
                        "returned": False,
                        "error_type": f"{type(error).__module__}.{type(error).__qualname__}",
                        "error": str(error),
                    }
                methods.append({"method": name, **result})
            observations["config_probes"].append(
                {"properties": properties, "methods": methods}
            )
    if "calls" in request:
        observations["calls"] = []
        for call in request["calls"]:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
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
            result["warnings"] = [
                {
                    "category": f"{warning.category.__module__}.{warning.category.__qualname__}",
                    "message": str(warning.message),
                }
                for warning in caught
            ]
            observations["calls"].append({"target": call["target"], **result})
    print(json.dumps(observations, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
