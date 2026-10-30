# uvicorn-rs

A Rust-first server for ASGI applications and Rust services.

## Project status (2026-10-30)

The release target is a Python-free `uvicorn-rs` server crate with HTTP/3
behind `http3`, the separate `asgi-lifespan-protocol-rs` crate, and the PyPI
distribution `uvicorn-rs`. The optional `uvicorn-rs-py` package remains the
internal Cargo/PyO3 adapter. The publisher is `.github/workflows/release.yml`;
`.github/workflows/candidate.yml` verifies candidates. As of 2026-10-30,
crates.io serves `uvicorn-rs` 0.2.1 and `asgi-lifespan-protocol-rs` 0.2.1;
PyPI has no `uvicorn-rs` release. The current 0.2.2 source has no clean,
exact-source candidate or release tag yet. See [release status](docs/releases.md).

The latest full-mode CI run,
[#497](https://github.com/appunni-m/uvicorn-rs/actions/runs/41031606350),
used branch revision `255ec35af35d44c78423d35c4cb9ee539c7a4ab5`. Linux
installed-wheel parity selected 718 cases: 715 passed, one infrastructure case
failed, and two later TLS cases were not run. The failed active-stream case
raised Broken pipe; its target log says the ASGI send saw “client disconnected
before response body.” The graceful-timeout message belongs to the preceding
TLS cancellation case, which passed. Three-repeat coverage completed at
14,032/14,203 regions and 10,343/10,428 lines, so the 100% gate failed.
Candidate parity on macOS/Windows and the Python-floor job were skipped.

Focused CI
[#500](https://github.com/appunni-m/uvicorn-rs/actions/runs/41036703998) passed
three TLS shutdown cases 3/3 on revision
`3ff0999665f8face9dbb8bf03984b734e4293d22`. Focused Linux run
[#501](https://github.com/appunni-m/uvicorn-rs/actions/runs/41040800079) then
reproduced the full-run failure in the two-case sequence: the held-request
case passed, while the active-stream case failed with an ASGI send error,
“client disconnected before response body.” Its trace shows the server
accepted the held stream and a separate readiness probe after SIGTERM, then
canceled the probe connection during shutdown. The one-second graceful-timeout
message came from the preceding cancellation case, not the active-stream case;
the failure's cause remains unconfirmed. Focused Linux run
[#502](https://github.com/appunni-m/uvicorn-rs/actions/runs/41043210309) on
`ee236c8bdfc0b2f270853a40a6ff3c4feb20db43` passed the same two cases 2/2 with
zero infrastructure failures or not-run cases. Its trace confirms the expected
one-second cancellation timeout and three-second active-stream timeout; the
active connection finished successfully and the listener drain completed. This
pass does not explain the earlier failure or replace a full-source matrix.
Focused Linux run
[#503](https://github.com/appunni-m/uvicorn-rs/actions/runs/41044156010) on
`98c90076748337ec2ef3f34a49b94bffd5ffcd22` passed the two strict HTTP/1
response-header cases and the strict HTTP/2 ordered-header case 3/3, with zero
failures, infrastructure failures, or not-run cases. Artifact 12970969486 has
SHA-256
`c615fb7d703361f36d378a4b3ce37f204b85dd09ec6917cfac5771c3e270ee99`. This
confirms these selected inputs on the exact candidate source, not the full
protocol matrix; HTTP/3 raw wire order remains unverified.
Focused Linux run
[#504](https://github.com/appunni-m/uvicorn-rs/actions/runs/41044728003) on
the same source passed the uncompressed and per-message-deflate fragmented
WebSocket text cases 2/2, with no failed, infrastructure-failed, or not-run
cases. Artifact 12972595056 has SHA-256
`c55dc16bd056f7cdc29b074828e13ea5bb74319a189c57a64383e1a4b3f35350`.
This confirms those two input contracts only.
Exact-source full coverage, independent Coverage-MCP review, complete
compatibility, candidate artifacts and consumers, and parity-first benchmarks
remain open.
See [coverage evidence](docs/coverage.md),
[parity evidence](docs/parity.md), and
[replacement status](docs/uvicorn-compatibility.md).

The Python adapter is **not yet a drop-in Uvicorn replacement**. If your
application depends on Uvicorn's full command-line, Python API, worker, or
reload behavior, keep using upstream Uvicorn for now.

The consolidated `uvicorn-rs` crate provides a Rust library, not a standalone
server executable. Cargo publication does not qualify the Python adapter or
complete the project's release gates. See
[release status](docs/releases.md).

The PyPI distribution is named `uvicorn-rs`, following the project's
`pillow-rs` naming convention, and is pending its first release. It provides
the `uvicorn` command and import namespace after the compatibility and release
gates pass. The root Cargo/PyO3 integration package remains named
`uvicorn-rs-py` internally and is not published as the PyPI distribution. The
source checkout exposes these command and import names, but only selected
paths have been compared with Uvicorn 0.54.0; broad CLI, Python API, and
process-behavior parity remains unverified. See
[replacement status](docs/uvicorn-compatibility.md) for the tested surface
and remaining gaps.

## Try the current prototype

From a development checkout with `uv`, CPython 3.12, and a Rust toolchain
installed:

```sh
uv sync --python 3.12
uv run uvicorn examples.hello_asgi:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl -i http://127.0.0.1:8000/
```

You should receive HTTP 200 and a text body beginning with `GET / 1.1`. This
checkout command is for evaluating the prototype; it does not mean the package
is published or Uvicorn-compatible. See [the quickstart](docs/quickstart.md)
and [current options](docs/configuration.md).

## What to expect

Python applications still execute on their Python event loop, and Python
application code remains subject to the GIL. Current measurements do not show
a general performance advantage over Uvicorn for Python ASGI applications;
see the [benchmark results](docs/benchmark-results.md).

Rust applications can use the Python-free `uvicorn-rs` library. The server is
independent of Starlette-RS and FastAPI-RS; those frameworks do not need it as
a runtime dependency. See [native Rust integration](docs/native-fastapi-composition.md).

## Documentation

- [Run a Python ASGI app](docs/quickstart.md)
- [Install, replace, or roll back Uvicorn](docs/uvicorn-compatibility.md)
- [ASGI and protocol support](docs/support-matrix.md)
- [Deployment guidance](docs/deployment.md)
- [Benchmark results and evidence limits](docs/benchmark-results.md)

For contributing, security reporting, support expectations, architecture, and
release information, see [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[SUPPORT.md](SUPPORT.md), and the [documentation site](https://appunni-m.github.io/uvicorn-rs/).

The project is not affiliated with the Uvicorn project. It is available under
[BSD-3-Clause or MIT](LICENSE), at your option.
