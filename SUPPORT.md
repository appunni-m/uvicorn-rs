# Support

This project is an experimental, locally built prototype. It has no published
binary or Python package, no service-level commitment, and no supported release
window.

The development environment that has been exercised is CPython 3.12.13 on
macOS ARM64 with Rust 1.98.1. The manifests declare Python 3.9 or newer and
Rust 1.83 or newer; those lower bounds have not been validated. Other versions
and platforms are unverified. See the [ASGI support matrix](docs/support-matrix.md)
for behavioral evidence and known limits.

For a reproducible problem, open a GitHub issue with the commit, operating
system, Rust/Python versions, exact command, protocol, and a minimal ASGI app.
Do not post secrets or exploitable vulnerability details in a public issue; use
the private route described in [SECURITY.md](SECURITY.md).

The project is not affiliated with Uvicorn. It does not promise Uvicorn CLI
parity or support every Uvicorn deployment mode.
