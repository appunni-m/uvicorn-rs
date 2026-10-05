"""Black-box HTTP/1.1 and HTTP/2 scope probe (requires curl with nghttp2)."""

import contextlib
import pathlib
import socket
import subprocess
import sys
import tempfile
import time


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_listening(port, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early with status {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("server did not start listening")


def start_server(port, certfile=None, keyfile=None):
    command = [
        sys.executable,
        "-m",
        "uvicorn_rs",
        "examples.protocol_asgi:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if certfile is not None:
        command.extend(["--certfile", str(certfile), "--keyfile", str(keyfile)])
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_listening(port, process)
    return process


def stop_server(process):
    process.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=3)
    if process.poll() is None:
        process.kill()
        process.wait()
    process.stderr.close()


def probe(expected, protocol_args, url):
    result = subprocess.run(
        ["curl", "--silent", "--show-error", *protocol_args, url],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = result.stdout.strip()
    if actual != f"http_version={expected}":
        raise AssertionError(f"expected {expected}, got {actual!r}")
    print(f"PASS: HTTP/{expected} request scope reports {actual}")


def main():
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-protocol-") as temp_dir:
        certfile = pathlib.Path(temp_dir) / "cert.pem"
        keyfile = pathlib.Path(temp_dir) / "key.pem"
        cafile = pathlib.Path(temp_dir) / "ca.pem"
        cakey = pathlib.Path(temp_dir) / "ca.key"
        csrfile = pathlib.Path(temp_dir) / "server.csr"
        extensions = pathlib.Path(temp_dir) / "server.ext"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "2",
                "-keyout",
                str(cakey),
                "-out",
                str(cafile),
                "-subj",
                "/CN=uvicorn-rs test CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,keyCertSign,cRLSign",
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(keyfile),
                "-out",
                str(csrfile),
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        extensions.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=serverAuth\n"
            "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(csrfile),
                "-CA",
                str(cafile),
                "-CAkey",
                str(cakey),
                "-CAcreateserial",
                "-out",
                str(certfile),
                "-days",
                "2",
                "-extfile",
                str(extensions),
            ],
            check=True,
            capture_output=True,
        )
        process = start_server(port)
        try:
            probe("1.1", ["--http1.1"], f"http://127.0.0.1:{port}/protocol")
            probe("2", ["--http2-prior-knowledge"], f"http://127.0.0.1:{port}/protocol")
        finally:
            stop_server(process)

        process = start_server(port, certfile, keyfile)
        try:
            probe("1.1", ["--http1.1", "--insecure"], f"https://localhost:{port}/protocol")
            probe("2", ["--http2", "--insecure"], f"https://localhost:{port}/protocol")

            h3 = subprocess.run(
                [
                    "cargo",
                    "run",
                    "--quiet",
                    "--manifest-path",
                    "tools/http3-probe/Cargo.toml",
                    "--bin",
                    "uvicorn-rs-http3-probe",
                    "--",
                    f"127.0.0.1:{port}",
                    str(cafile),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if h3.returncode != 0:
                raise RuntimeError(f"HTTP/3 probe failed:\n{h3.stderr}")
            print(h3.stdout.strip())
        finally:
            stop_server(process)


if __name__ == "__main__":
    main()
