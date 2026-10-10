"""Create short-lived CA and server certificates for TLS benchmarks."""

from __future__ import annotations

import subprocess
from pathlib import Path


def generate_server_certificate(directory: Path) -> tuple[Path, Path, Path]:
    """Return a CA certificate, a server leaf certificate, and its private key.

    The CA is trusted by benchmark clients. The server presents the separately
    issued leaf certificate, whose CA constraint is explicitly false. Keeping
    the trust anchor and end-entity certificate distinct matches normal TLS
    validation and avoids treating a CA certificate as a server identity.
    """
    ca_certificate = directory / "benchmark-ca.pem"
    ca_key = directory / "benchmark-ca-key.pem"
    request = directory / "server.csr"
    server_certificate = directory / "server.pem"
    server_key = directory / "server-key.pem"
    extensions = directory / "server.ext"
    ca_config = directory / "ca.cnf"
    ca_config.write_text(
        "[req]\n"
        "prompt=no\n"
        "distinguished_name=dn\n"
        "x509_extensions=v3_ca\n"
        "[dn]\n"
        "CN=uvicorn-rs benchmark CA\n"
        "[v3_ca]\n"
        "basicConstraints=critical,CA:TRUE,pathlen:0\n"
        "keyUsage=critical,keyCertSign,cRLSign\n"
        "subjectKeyIdentifier=hash\n"
    )

    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
            "-keyout", str(ca_key), "-out", str(ca_certificate),
            "-config", str(ca_config),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(server_key), "-out", str(request), "-subj", "/CN=localhost",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
    )
    subprocess.run(
        [
            "openssl", "x509", "-req", "-in", str(request), "-CA", str(ca_certificate),
            "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(server_certificate),
            "-days", "2", "-extfile", str(extensions),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["openssl", "verify", "-CAfile", str(ca_certificate), str(server_certificate)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ca_certificate, server_certificate, server_key
