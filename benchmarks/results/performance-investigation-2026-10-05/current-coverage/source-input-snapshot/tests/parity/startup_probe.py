"""Run one public server API startup failure for the parity matrix."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.parity.app import app


def identity_for(
    scenario: str, certificate: str, key: str, temporary: Path
) -> tuple[str | None, str | None]:
    missing = str(temporary / "missing.pem")
    if scenario == "startup-partial-tls-api":
        return missing, None
    if scenario == "startup-missing-certificate":
        return missing, str(temporary / "missing-key.pem")
    if scenario == "startup-invalid-host":
        return None, None
    if scenario == "startup-empty-certificate":
        empty = temporary / "empty-certificate.pem"
        empty.write_bytes(b"")
        return str(empty), missing
    if scenario == "startup-invalid-certificate-pem":
        invalid = temporary / "invalid-certificate.pem"
        invalid.write_text(
            "-----BEGIN CERTIFICATE-----\nnot base64!\n-----END CERTIFICATE-----\n",
            encoding="ascii",
        )
        return str(invalid), missing
    if scenario == "startup-missing-private-key":
        return certificate, str(temporary / "missing-key.pem")
    if scenario == "startup-empty-private-key":
        empty = temporary / "empty-key.pem"
        empty.write_bytes(b"")
        return certificate, str(empty)
    if scenario == "startup-invalid-private-key-pem":
        invalid = temporary / "invalid-key.pem"
        invalid.write_text(
            "-----BEGIN PRIVATE KEY-----\nnot base64!\n-----END PRIVATE KEY-----\n",
            encoding="ascii",
        )
        return certificate, str(invalid)
    if scenario == "startup-mismatched-private-key":
        mismatched = temporary / "mismatched-key.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(mismatched)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return certificate, str(mismatched)
    raise ValueError(f"unknown startup scenario: {scenario}")


def main() -> None:
    server_id, scenario, certificate, key = sys.argv[1:]
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-startup-parity-") as directory:
        certfile, keyfile = identity_for(scenario, certificate, key, Path(directory))
        host = "does-not-exist.invalid" if scenario == "startup-invalid-host" else "127.0.0.1"
        try:
            if server_id == "uvicorn-rs":
                from uvicorn_rs import Server

                server = Server(
                    app,
                    host=host,
                    port=0,
                    certfile=certfile,
                    keyfile=keyfile,
                )
                asyncio.run(server.serve())
                return

            if server_id == "uvicorn":
                import uvicorn

                config = uvicorn.Config(
                    app,
                    host=host,
                    port=0,
                    loop="uvloop",
                    ssl_certfile=certfile,
                    ssl_keyfile=keyfile,
                )
                asyncio.run(uvicorn.Server(config).serve())
                return

            raise ValueError(f"unknown startup oracle: {server_id}")
        except SystemExit:
            print("ASGI_PARITY_SERVER_STARTUP_FAILURE", file=sys.stderr, flush=True)
            raise
        except Exception:
            print("ASGI_PARITY_SERVER_STARTUP_FAILURE", file=sys.stderr, flush=True)
            raise


if __name__ == "__main__":
    main()
