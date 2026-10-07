"""Exercise a transient systemd service using an exact installed uvicorn-rs wheel."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import http.client
import importlib.metadata
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command, *, timeout=10, check=True):
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command!r}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _free_port():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _installed_native(wheel):
    import uvicorn_rs
    from uvicorn_rs import _native

    package = Path(uvicorn_rs.__file__).resolve()
    native = Path(_native.__file__).resolve()
    if package.is_relative_to(ROOT / "python") or native.is_relative_to(
        ROOT / "python"
    ):
        raise RuntimeError(
            "systemd probe requires an installed wheel, not an editable checkout"
        )
    with zipfile.ZipFile(wheel) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.startswith("uvicorn_rs/_native.") and name.endswith((".so", ".pyd"))
        ]
        if len(members) != 1 or native.read_bytes() != archive.read(members[0]):
            raise RuntimeError(
                "imported native extension does not match the supplied wheel"
            )
    return package, native


def _request(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", "/state")
        response = connection.getresponse()
        body = response.read()
        return response.status, body
    finally:
        connection.close()


def _journal(unit):
    result = _run(
        [
            "sudo",
            "-n",
            "journalctl",
            "--no-pager",
            "--output=cat",
            "--unit",
            unit,
            "-n",
            "80",
        ],
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"journal read failed for {unit}: {result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("this probe requires a Linux systemd host")
    if shutil.which("systemd-run") is None or shutil.which("systemctl") is None:
        raise RuntimeError("systemd-run and systemctl are required")
    if shutil.which("sudo") is None:
        raise RuntimeError("sudo is required to manage a transient system service")

    wheel = args.wheel.resolve()
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    package, native = _installed_native(wheel)
    _run(["sudo", "-n", "systemctl", "show-environment"], timeout=10)
    systemd_version = _run(["systemctl", "--version"], timeout=5).stdout.splitlines()[0]

    port = _free_port()
    unit = f"uvicorn-rs-integration-{os.getpid()}-{secrets.token_hex(4)}.service"
    python = str(Path(sys.executable).resolve())
    run_command = [
        "sudo",
        "-n",
        "systemd-run",
        "--quiet",
        "--no-block",
        f"--unit={unit}",
        f"--uid={getpass.getuser()}",
        f"--working-directory={ROOT}",
        f"--setenv=PYTHONPATH={ROOT}",
        "--property=Type=exec",
        "--property=Restart=no",
        "--property=KillSignal=SIGTERM",
        "--property=TimeoutStopSec=10s",
        python,
        "-m",
        "uvicorn_rs",
        "examples.lifespan_asgi:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--graceful-timeout",
        "2",
    ]
    started = time.monotonic()
    service_started = False
    held_connection = None
    try:
        _run(run_command, timeout=15)
        service_started = True
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            active = _run(
                [
                    "sudo",
                    "-n",
                    "systemctl",
                    "show",
                    unit,
                    "--property=ActiveState",
                    "--value",
                ],
                timeout=5,
                check=False,
            )
            state = active.stdout.strip()
            if active.returncode != 0 or state in {"failed", "inactive"}:
                try:
                    journal = _journal(unit)
                except RuntimeError as error:
                    journal = str(error)
                details = active.stderr.strip() or active.stdout.strip()
                raise RuntimeError(
                    f"systemd unit {unit} is not active (state={state!r}; "
                    f"systemctl={details!r}); journal:\n{journal}"
                )
            if state != "active":
                time.sleep(0.05)
                continue
            try:
                status, body = _request(port)
                if status == 200 and body == b"startup-token:0":
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise TimeoutError("systemd service did not serve its module:app route")

        held_connection = socket.create_connection(("127.0.0.1", port), timeout=3)
        held_connection.settimeout(3)
        held_connection.sendall(
            b"GET /hold HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"
        )
        hold_deadline = time.monotonic() + 10
        while time.monotonic() < hold_deadline:
            logs = _journal(unit)
            if "APP_HOLD_STARTED" in logs:
                break
            time.sleep(0.05)
        else:
            raise TimeoutError("systemd service did not enter the held ASGI request")

        stop_started = time.monotonic()
        _run(["sudo", "-n", "systemctl", "stop", unit], timeout=12)
        stop_elapsed = time.monotonic() - stop_started
        logs = _journal(unit)
        status_result = _run(
            [
                "sudo",
                "-n",
                "systemctl",
                "show",
                unit,
                "--property=ExecMainStatus",
                "--value",
            ],
            timeout=5,
            check=False,
        )
        if status_result.returncode != 0 or status_result.stdout.strip() != "0":
            raise RuntimeError(
                f"systemd service did not exit successfully: {status_result.stdout!r} {logs}"
            )
        if "APP_CANCELLED_BY_SHUTDOWN" not in logs:
            raise RuntimeError("systemd stop did not cancel the held ASGI request")
        if "LIFESPAN_SHUTDOWN_COMPLETE" not in logs:
            raise RuntimeError("systemd stop did not complete ASGI lifespan shutdown")
        if stop_elapsed > 10:
            raise RuntimeError("systemd service exceeded its ten-second stop bound")

        result = {
            "schema": "uvicorn-rs-systemd-deployment@1",
            "status": "passed",
            "unit": unit,
            "wheel": str(wheel),
            "wheel_sha256": wheel_sha256,
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "app_sha256": hashlib.sha256(
                (ROOT / "examples/lifespan_asgi.py").read_bytes()
            ).hexdigest(),
            "server_version": importlib.metadata.version("uvicorn-rs"),
            "server_package": str(package),
            "native_path": str(native),
            "native_sha256": hashlib.sha256(native.read_bytes()).hexdigest(),
            "app": "examples.lifespan_asgi:app",
            "service_manager": "systemd transient service",
            "systemd_version": systemd_version,
            "systemd_unit_properties": {
                "Type": "exec",
                "KillSignal": "SIGTERM",
                "TimeoutStopSec": "10s",
                "Restart": "no",
            },
            "module_app_http": {"status": status, "body": body.decode()},
            "held_request_cancelled": True,
            "lifespan_shutdown_completed": True,
            "service_exit_status": 0,
            "stop_elapsed_seconds": round(stop_elapsed, 6),
            "stop_bound_seconds": 10,
            "total_probe_elapsed_seconds": round(time.monotonic() - started, 6),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": "passed", "receipt": str(args.output)}))
    finally:
        if held_connection is not None:
            held_connection.close()
        if service_started:
            _run(["sudo", "-n", "systemctl", "stop", unit], timeout=12, check=False)


if __name__ == "__main__":
    main()
