# ASGI and protocol support

This page is a quick check of what the current source can do. It describes
tested behavior, not a complete ASGI conformance claim or a Uvicorn replacement
guarantee. The project is experimental and its Cargo and PyPI distributions
have not been published.

## Can I replace Uvicorn?

Not yet. `uvicorn-rs-py` is not a drop-in replacement today. The `uvicorn`
namespace now exposes the pinned `run`, `Config`, and `Server` signatures, but
most CLI settings, API behavior, workers, reload, and deployment behavior are
not implemented or qualified. If your app depends on those features, continue
to use upstream Uvicorn. See [replacement status](uvicorn-compatibility.md)
for the current package status and migration guidance.

## Supported behaviors

| If you need… | Current status | What to keep in mind |
| --- | --- | --- |
| Run a Python ASGI 3 application | Implemented in the source checkout and covered by live protocol cases. | This is an experimental adapter; Python application code still runs in Python. |
| HTTP/1.1 | Implemented and exercised with request/response, streaming, disconnect, TLS, and keep-alive cases. | These cases cover a declared subset. They do not prove complete ASGI or Uvicorn compatibility. |
| HTTP/2 | Implemented and exercised over TLS and cleartext prior knowledge. | The support claim is limited to the tested HTTP/2 behaviors listed in this matrix. |
| HTTP/3 | Experimental; selected requests, streaming, cancellation, and shutdown behaviors have live cases. | There is no Uvicorn HTTP/3 baseline. Check the current benchmark status before relying on performance results. |
| WebSockets | HTTP/1.1 upgrade and selected handshake, message, disconnect, and shutdown cases are implemented. | WebSockets over HTTP/2 and HTTP/3 are not supported. |
| Request and response streaming | Tested cases cover incremental uploads, streamed response chunks, backpressure, and selected cancellation paths. | The tests do not cover every timing race or every ASGI extension. |
| Mount an app under an ASGI root path | `uvicorn.run(root_path=...)` and `python -m uvicorn --root-path ...` pass focused HTTP/1.1 comparisons against Uvicorn 0.54.0. | Verified with an ASCII mount prefix. The case checks `root_path`, `path`, and `raw_path`; other protocols and non-ASCII prefixes remain unverified. |
| Lifespan and graceful shutdown | Startup, shutdown, application failures, and selected cancellation paths have live cases. `lifespan="off"` passes focused public API and module CLI comparisons against Uvicorn 0.54.0. | Strict `lifespan="on"` failure behavior for apps without lifespan support is not yet verified. Process supervision, reload, and Uvicorn worker behavior are separate compatibility work. |
| Use the native Rust library | The source contains a Python-free `uvicorn-rs` Cargo library for Rust services. | It is experimental and unpublished. See [native Rust integration](native-fastapi-composition.md). |
| Match Uvicorn's CLI and Python API | Incomplete. The current focused inputs pass for a default `uvicorn.run()` request and shutdown, selected lifespan behavior, and `root_path` through both the API and module CLI. Selected help, version, environment, and import-diagnostic cases also have individual parity results. | These are narrow cases, not full CLI or API parity. Most runtime options and programmatic behavior remain unimplemented or unverified. Detailed case results and current evidence identity are in the [maintainer evidence record](maintainers/uvicorn-0.54.0-contract.md). |

## Known behavior limits

- The current Python adapter does not preserve response-header order across
  different header names on HTTP/1.1 and HTTP/2. Repeated values for the same
  name retain their order. This is a known ASGI response-start conformance
  gap.
- The complete official ASGI conformance suite has not been run.
- The latest matched Python FastAPI results do not establish a general speed
  advantage over Uvicorn. See [benchmark results](benchmark-results.md) and
  [current benchmark status](benchmark-status.md).
- Detailed case IDs, source identities, historical receipts, and coverage
  accounting are kept in the [maintainer evidence record](maintainers/asgi-support-evidence.md).

## Try the current prototype

Follow the [quickstart](quickstart.md) to run the checked-out example. The
[configuration guide](configuration.md) lists the prototype's current options.
