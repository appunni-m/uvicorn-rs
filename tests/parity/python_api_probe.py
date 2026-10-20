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
import time

_startup_failure_server = None
_startup_failure_task = None


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


def run_http_observation(request: dict) -> dict:
    """Exercise a public Python API or CLI server and signal shutdown."""

    child_code = r'''
import sys
import base64
import json
import uvicorn

lifespan_state = {"started": False}

async def app(scope, receive, send):
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
    await receive()
    lifespan_status = b"lifespan-started" if lifespan_state["started"] else b"lifespan-off"
    if "state" not in scope:
        state_status = b"scope-state-missing"
    elif scope["state"] == {}:
        state_status = b"scope-state-empty"
    else:
        state_status = b"scope-state-populated"
    root_path_status = b"root_path=" + scope["root_path"].encode("utf-8")
    path_status = b"path=" + scope["path"].encode("utf-8")
    raw_path_status = b"raw_path=" + base64.b64encode(scope["raw_path"])
    body = b"|".join(
        (
            b"python-api-run-ok",
            lifespan_status,
            state_status,
            root_path_status,
            path_status,
            raw_path_status,
        )
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

uvicorn.run(
    app,
    host="127.0.0.1",
    port=int(sys.argv[1]),
    lifespan=sys.argv[2],
    root_path=sys.argv[3],
    headers=json.loads(sys.argv[4]),
)
'''
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]

    if request["invocation"] == "module-cli":
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.parity.app:lifespan_probe_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--root-path",
            request["root_path"],
            "--lifespan",
            request["lifespan"],
        ]
        for name, value in request.get("headers", []):
            command.extend(("--header", f"{name}:{value}"))
    else:
        command = [
            sys.executable,
            "-c",
            child_code,
            str(port),
            request["lifespan"],
            request["root_path"],
            json.dumps(request.get("headers", []), separators=(",", ":")),
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

    process = subprocess.Popen(
        command,
        cwd=os.getcwd(),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **process_options,
    )
    response = None
    deadline = time.monotonic() + request["timeout_seconds"]
    try:
        while time.monotonic() < deadline and process.poll() is None:
            connection = http.client.HTTPConnection(
                "127.0.0.1", port, timeout=0.5
            )
            try:
                connection.request(
                    request["method"],
                    request["path"],
                    headers={"Connection": "close"},
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
            "shutdown_signal_sent": shutdown_signal_sent,
            "process_exit_code": process.returncode,
            "process_timed_out": process_timed_out,
        }
        if (
            response is None
            or response["status"] >= 500
            or process.returncode != 0
            or process_timed_out
        ):
            observation["server_stdout_base64"] = base64.b64encode(server_stdout).decode("ascii")
            observation["server_stderr_base64"] = base64.b64encode(server_stderr).decode("ascii")
        return observation
    finally:
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


def main() -> None:
    request = json.loads(sys.argv[1])
    if "run_http" in request:
        observations = {"run_http": run_http_observation(request["run_http"])}
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
                resolve(call["target"])(*call["arguments"], **call["keyword_arguments"])
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
