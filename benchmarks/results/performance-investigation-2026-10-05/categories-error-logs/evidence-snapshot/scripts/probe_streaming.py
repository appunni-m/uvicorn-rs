"""Black-box checks for bounded request and response body streaming."""

import contextlib
import socket
import subprocess
import sys
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


def read_chunk(stream):
    line = stream.readline()
    if not line:
        raise EOFError("server closed before completing the response")
    size = int(line.split(b";", maxsplit=1)[0].strip(), 16)
    if size == 0:
        while stream.readline() != b"\r\n":
            pass
        return None
    data = stream.read(size)
    if stream.read(2) != b"\r\n":
        raise AssertionError("invalid HTTP chunk terminator")
    return data


def main():
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn_rs",
            "examples.streaming_asgi:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_listening(port, process)
        with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
            sock.settimeout(3)
            reader = sock.makefile("rb")
            sock.sendall(
                b"POST /upload HTTP/1.1\r\n"
                b"Host: localhost\r\n"
                b"Transfer-Encoding: chunked\r\n"
                b"Connection: close\r\n\r\n"
                b"3\r\nabc\r\n"
            )
            status = reader.readline()
            headers = []
            while True:
                line = reader.readline()
                if line == b"\r\n":
                    break
                headers.append(line.lower())
            if b" 200 " not in status:
                raise AssertionError(f"unexpected streaming response: {status!r}")
            if not any(line.startswith(b"transfer-encoding: chunked") for line in headers):
                raise AssertionError(f"expected chunked streaming response, got {headers!r}")
            first = read_chunk(reader)
            if first != b"abc":
                raise AssertionError(f"expected first live request chunk, got {first!r}")

            sock.sendall(b"3\r\ndef\r\n0\r\n\r\n")
            second = read_chunk(reader)
            end = read_chunk(reader)
            if second != b"def" or end is not None:
                raise AssertionError(f"unexpected final body chunks: {second!r}, {end!r}")
        print("PASS: request and response streamed while the upload was still open")

        result = subprocess.run(
            ["curl", "--silent", "--show-error", f"http://127.0.0.1:{port}/response"],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout != "firstsecond":
            raise AssertionError(f"response stream lost or reordered chunks: {result.stdout!r}")
        print("PASS: response chunks streamed in order")
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=3)
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stderr.close()


if __name__ == "__main__":
    main()
