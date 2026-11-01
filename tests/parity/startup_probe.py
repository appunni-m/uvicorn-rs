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
    if scenario.startswith("startup-client-ca-"):
        return certificate, key
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
    tls_fixtures = {
        "startup-encrypted-private-key-pkcs12-invalid-encrypted-data-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-encrypted-data-type.pem",
        "startup-encrypted-private-key-pkcs12-trailing-encrypted-info-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-encrypted-info-field.pem",
        "startup-encrypted-private-key-pkcs12-invalid-algorithm-oid-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-algorithm-oid-type.pem",
        "startup-encrypted-private-key-pkcs12-missing-parameters": "localhost-key-pkcs12-pbe-sha1-3des-missing-parameters.pem",
        "startup-encrypted-private-key-pkcs12-trailing-algorithm-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-algorithm-field.pem",
        "startup-encrypted-private-key-pkcs12-invalid-salt-type": "localhost-key-pkcs12-pbe-sha1-3des-invalid-salt-type.pem",
        "startup-encrypted-private-key-pkcs12-missing-iterations": "localhost-key-pkcs12-pbe-sha1-3des-missing-iterations.pem",
        "startup-encrypted-private-key-pkcs12-trailing-parameters-field": "localhost-key-pkcs12-pbe-sha1-3des-trailing-parameters-field.pem",
        "startup-encrypted-private-key-pkcs12-zero-iterations": "localhost-key-pkcs12-pbe-sha1-3des-zero-iterations.pem",
        "startup-encrypted-private-key-pkcs12-short-ciphertext": "localhost-key-pkcs12-pbe-sha1-3des-short-ciphertext.pem",
        "startup-encrypted-private-key-pkcs12-wrong-password": "localhost-key-pkcs12-pbe-sha1-3des.pem",
        "startup-encrypted-private-key-pkcs12-invalid-decrypted-key": "localhost-key-pkcs12-pbe-sha1-3des-invalid-decrypted-key.pem",
        "startup-traditional-encrypted-private-key-unknown-header": "localhost-key-rsa-aes256-unknown-header.pem",
        "startup-traditional-encrypted-private-key-high-nonhex-iv": "localhost-key-rsa-aes256-high-nonhex-iv.pem",
        "startup-traditional-encrypted-private-key-low-nonhex-iv": "localhost-key-rsa-aes256-nonhex-iv.pem",
        "startup-traditional-encrypted-private-key-odd-iv": "localhost-key-rsa-aes256-odd-iv.pem",
        "startup-traditional-encrypted-private-key-short-iv": "localhost-key-rsa-aes256-short-iv.pem",
        "startup-traditional-encrypted-private-key-short-ciphertext": "localhost-key-rsa-aes256-short-ciphertext.pem",
        "startup-traditional-encrypted-private-key-wrong-password": "localhost-key-rsa-aes256-encrypted.pem",
    }
    if scenario == "startup-traditional-encrypted-private-key-empty-document":
        empty = temporary / "empty-encrypted-key.pem"
        empty.write_bytes(b"")
        return certificate, str(empty)
    if scenario in tls_fixtures:
        fixture_directory = ROOT / "tests" / "native-core" / "tls"
        return certificate, str(fixture_directory / tls_fixtures[scenario])
    malformed_encrypted_key_documents = {
        "startup-encrypted-private-key-invalid-utf8": b"\xff\xfe\n",
        "startup-encrypted-private-key-malformed-pem": b"not a PEM document\n",
        "startup-encrypted-private-key-wrong-label": (
            b"-----BEGIN NOT A PRIVATE KEY-----\nMAA=\n"
            b"-----END NOT A PRIVATE KEY-----\n"
        ),
        "startup-encrypted-private-key-invalid-der": (
            b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nMAA=\n"
            b"-----END ENCRYPTED PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-unsupported-cipher": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n"
            b"DEK-Info: UNKNOWN-CBC,0123456789ABCDEF\n\n"
            b"AAAA\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-missing-dek-info": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n\n"
            b"AAAA\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-invalid-dek-info": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n"
            b"DEK-Info: AES-256-CBC-0123456789ABCDEF\n\n"
            b"AAAA\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-invalid-proc-type": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 5,ENCRYPTED\n"
            b"DEK-Info: AES-256-CBC,0123456789ABCDEF0123456789ABCDEF\n\n"
            b"AAAA\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-missing-body": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n"
            b"DEK-Info: AES-256-CBC,0123456789ABCDEF0123456789ABCDEF\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-invalid-body-base64": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n"
            b"DEK-Info: AES-256-CBC,0123456789abcdef0123456789abcdef\n\n"
            b"not-base64!\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
        "startup-traditional-encrypted-private-key-missing-end-marker": (
            b"-----BEGIN RSA PRIVATE KEY-----\n"
            b"Proc-Type: 4,ENCRYPTED\n"
            b"DEK-Info: AES-256-CBC,0123456789ABCDEF0123456789ABCDEF\n\n"
            b"AAAA\n"
        ),
        "startup-traditional-unencrypted-private-key-invalid-base64": (
            b"-----BEGIN RSA PRIVATE KEY-----\n\n"
            b"not-base64!\n"
            b"-----END RSA PRIVATE KEY-----\n"
        ),
    }
    if scenario in malformed_encrypted_key_documents:
        invalid = temporary / "invalid-encrypted-key.pem"
        invalid.write_bytes(malformed_encrypted_key_documents[scenario])
        return certificate, str(invalid)
    if scenario == "startup-encrypted-private-key-wrong-password":
        fixture_directory = ROOT / "tests" / "native-core" / "tls"
        return (
            str(fixture_directory / "localhost-cert.pem"),
            str(fixture_directory / "localhost-key-pkcs8-encrypted.pem"),
        )
    raise ValueError(f"unknown startup scenario: {scenario}")


def client_ca_path_for(
    scenario: str, temporary: Path, trust_anchor: str | None
) -> str | None:
    if scenario == "startup-client-ca-missing-file":
        return str(temporary / "missing-client-ca.pem")
    if scenario == "startup-client-ca-no-certificates":
        path = temporary / "no-client-ca-certificates.pem"
        path.write_bytes(b"not a PEM certificate\n")
        return str(path)
    if scenario == "startup-client-ca-invalid-utf8-prefix-valid-pem":
        if trust_anchor is None:
            raise ValueError("client CA fallback case requires a generated trust anchor")
        path = temporary / "non-utf8-prefix-client-ca.pem"
        path.write_bytes(b"\xff\n" + Path(trust_anchor).read_bytes())
        return str(path)
    return None


def main() -> None:
    arguments = sys.argv[1:]
    if len(arguments) == 4:
        server_id, scenario, certificate, key = arguments
        trust_anchor = None
    elif len(arguments) == 5:
        server_id, scenario, certificate, key, trust_anchor = arguments
        trust_anchor = trust_anchor or None
    else:
        raise ValueError("expected server, scenario, certificate, key, and optional trust anchor")
    with tempfile.TemporaryDirectory(prefix="uvicorn-rs-startup-parity-") as directory:
        temporary = Path(directory)
        certfile, keyfile = identity_for(scenario, certificate, key, temporary)
        if scenario == "startup-encrypted-private-key-pkcs12-wrong-password":
            key_password = "incorrect-pkcs12-parity-password"
        elif scenario == "startup-encrypted-private-key-pkcs12-invalid-decrypted-key":
            key_password = "uvicorn-rs-parity-key"
        elif scenario.startswith("startup-encrypted-private-key-pkcs12-"):
            key_password = "uvicorn-rs-parity-key"
        elif scenario.startswith("startup-encrypted-private-key-"):
            key_password = "not-the-parity-key-password"
        elif scenario.startswith("startup-traditional-encrypted-private-key-"):
            key_password = (
                "incorrect-traditional-parity-password"
                if scenario.endswith("wrong-password")
                else "not-the-parity-key-password"
            )
        elif scenario == "startup-traditional-unencrypted-private-key-invalid-base64":
            key_password = "not-the-parity-key-password"
        else:
            key_password = None
        host = (
            "does-not-exist.invalid"
            if scenario in {
                "startup-invalid-host",
                "startup-client-ca-invalid-utf8-prefix-valid-pem",
            }
            else "127.0.0.1"
        )
        ca_certs = client_ca_path_for(scenario, temporary, trust_anchor)
        cert_reqs = 3 if scenario == "startup-client-ca-invalid-verify-mode" else (
            2 if scenario.startswith("startup-client-ca-") else 0
        )
        try:
            if server_id == "uvicorn-rs":
                from uvicorn_rs import Server

                options = {
                    "host": host,
                    "port": 0,
                    "certfile": certfile,
                    "keyfile": keyfile,
                }
                if key_password is not None:
                    options["ssl_keyfile_password"] = key_password
                if ca_certs is not None:
                    options["ssl_ca_certs"] = ca_certs
                if cert_reqs != 0:
                    options["ssl_cert_reqs"] = cert_reqs
                server = Server(app, **options)
                asyncio.run(server.serve())
                return

            if server_id == "uvicorn":
                import uvicorn

                options = {
                    "host": host,
                    "port": 0,
                    "loop": "uvloop",
                    "ssl_certfile": certfile,
                    "ssl_keyfile": keyfile,
                }
                if key_password is not None:
                    options["ssl_keyfile_password"] = key_password
                if ca_certs is not None:
                    options["ssl_ca_certs"] = ca_certs
                if cert_reqs != 0:
                    options["ssl_cert_reqs"] = cert_reqs
                # The native uvicorn_rs.Server API consumes ASGI3 callables
                # directly. Pin the oracle to the same interface so this
                # startup case measures listener failure rather than auto
                # detection of the shared synchronous test wrapper.
                config = uvicorn.Config(app, interface="asgi3", **options)
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
