# ASGI and protocol support

This page is a quick check of what the current source can do. It describes
tested behavior, not a complete ASGI conformance claim or a Uvicorn replacement
guarantee. The project is experimental and its Cargo and PyPI distributions
have not been published.

## Can I replace Uvicorn?

Not yet. `uvicorn-rs-py` is not a drop-in replacement today. The `uvicorn`
namespace now exposes the pinned `run`, `Config`, and `Server` signatures, but
most CLI settings, API behavior, workers, reload, and deployment behavior are
not implemented or qualified. Two focused module-CLI comparisons pass on
macOS ARM64 / CPython 3.12.13: explicit `--workers 2` and
`WEB_CONCURRENCY=2` each start two workers, serve one request, and shut down
on SIGINT. This does not qualify the broader worker or process-control
contract. If your app depends on unverified behavior, continue to use upstream
Uvicorn. See
[replacement status](uvicorn-compatibility.md) for the current package status
and migration guidance.

## Supported behaviors

| If you need… | Current status | What to keep in mind |
| --- | --- | --- |
| Run a Python ASGI 3 application | Implemented in the source checkout and covered by live protocol cases. | This is an experimental adapter; Python application code still runs in Python. |
| Serve an application factory | `uvicorn.run(factory, factory=True)` and `python -m uvicorn module:factory --factory` each load a no-argument factory returning an ASGI 3 app, serve an HTTP response, and shut down on SIGINT in focused comparisons with Uvicorn 0.54.0. | Each entry point has one successful HTTP lifecycle case. Other factory return types, CLI options, and failure paths remain unverified. |
| HTTP/1.1 | Implemented and exercised with request/response, streaming, disconnect, TLS, and idle keep-alive timeout cases. | A focused Uvicorn CLI comparison confirms `--timeout-keep-alive 1` closes an idle persistent HTTP/1 connection after the configured interval. The cases cover a declared subset; they do not prove complete ASGI or Uvicorn compatibility. |
| HTTP/2 | Implemented and exercised over TLS and cleartext prior knowledge. | The support claim is limited to the tested HTTP/2 behaviors listed in this matrix. |
| HTTP/3 | Experimental; selected requests, streaming, cancellation, and shutdown behaviors have live cases. | There is no Uvicorn HTTP/3 baseline. Check the current benchmark status before relying on performance results. |
| WebSockets | HTTP/1.1 upgrade and selected handshake, message, disconnect, shutdown, and server keepalive cases are implemented. Live Uvicorn comparisons verify `--ws-max-size` closes an oversized message with code 1009 before the ASGI app receives it, and verify server Ping, matching Pong, second Ping, and timeout close using `--ws-ping-interval 0.1 --ws-ping-timeout 0.3`. `ws_max_queue` is accepted on the default auto/SansIO path; Uvicorn 0.54.0's SansIO backend does not consume it, and the Rust adapter leaves it unset. Proxy cases verify forwarded `http` and `https` produce ASGI `ws` and `wss` schemes, and explicit forwarded `wss` is preserved. | Other WebSocket settings and timer values remain unverified. Legacy `websockets` queue behavior and WebSockets over HTTP/2 or HTTP/3 are not supported. |
| Request and response streaming | Tested cases cover incremental uploads, streamed response chunks, backpressure, and selected cancellation paths. | The tests do not cover every timing race or every ASGI extension. |
| Mount an app under an ASGI root path | HTTP/1.1 contract inputs through `uvicorn.run()` and `python -m uvicorn --root-path ...` verify `root_path`, prefixed `path`, and `raw_path` without the configured prefix. A separate parity input verifies percent-encoded UTF-8 request-path decoding with an empty `root_path`. | The root-path contract checks uvicorn-rs against ASGI scope expectations and compares exit code, response receipt, shutdown signal, and timeout state with Uvicorn; it does not compare the scope response body because Uvicorn 0.54.0 adds `root_path` to `raw_path`. Uvicorn also rejects a Unicode `root_path` with HTTP 400 before invoking the app. The ASGI spec defines `raw_path` as the original HTTP path component bytes, excluding the query string ([ASGI HTTP scope](https://asgi.readthedocs.io/en/stable/specs/www.html#http-connection-scope)). Other protocols are untested. |
| Set default response headers | The CLI `--header` policy and `uvicorn.run(headers=[(name, value)])` pass focused comparisons against Uvicorn 0.54.0. | Programmatic HTTP/1.1 cases cover custom-header delivery and duplicate value order; every validation and cross-name ordering behavior is not established. |
| Limit concurrent connections and requests | `--limit-concurrency 1`, `uvicorn.run(limit_concurrency=1)`, and `Config(limit_concurrency=1)` with `Server.run()` pass focused HTTP/1.1 comparisons against Uvicorn 0.54.0. The Python API cases compare the 503 response and SIGINT shutdown outcome. | Other limit values and HTTP/2/HTTP/3 behavior remain unverified. |
| Stop after a completed-request limit | A module CLI case with `UVICORN_LIMIT_MAX_REQUESTS=1` returns one HTTP/1.1 response and exits naturally, matching Uvicorn 0.54.0. A separate `--limit-max-requests 0` case verifies shutdown after startup without serving a request. With base limit 2 and jitter 1, a live case verifies natural exit after 2–3 HTTP/1.1 responses; the randomized count is retained in the receipt and checked against that range. | These cases cover one HTTP/1.1 connection pattern. Concurrent completion, TLS, HTTP/2/HTTP/3, WebSocket interactions, and negative jitter behavior remain unverified. |
| Honor trusted proxy headers | Focused HTTP/1.1 CLI and `uvicorn.run()` cases pass against Uvicorn 0.54.0 with an explicit loopback trust list; the app observes the forwarded client address and HTTPS scheme. Separate cases verify disabled handling, an excluded peer, wildcard and CIDR trust, opaque malformed tokens, empty `X-Forwarded-For` preserving the direct peer, the all-trusted-chain fallback, duplicate forwarding-field behavior, and uppercase unsupported proto being ignored. | Other address/network combinations and malformed `X-Forwarded-For` forms, other environment precedence/settings, and some WebSocket forwarded-protocol values remain unverified. |
| Load app environment files | The module CLI and `uvicorn.run(env_file=...)` load an app-specific value before the factory runs in focused comparisons against Uvicorn 0.54.0. A separate CLI case confirms a pre-existing process environment value takes precedence over the same key in the env file. | Requires `python-dotenv`, available in the `[standard]` extra. Broader dotenv syntax and other precedence combinations remain unverified. |
| Run ASGI2 applications | `uvicorn.run()` and `python -m uvicorn` pass focused HTTP comparisons for auto-detection and explicit `interface="asgi2"` against Uvicorn 0.54.0. The Python adapter converts ASGI2 callables to the ASGI3 shape used by Rust. | Other callable forms remain unverified. |
| Run WSGI applications | Focused `uvicorn.run()` and `python -m uvicorn` comparisons pass against Uvicorn 0.54.0 with both `lifespan="off"` and `lifespan="auto"`. Auto-mode cases cover default logging, an explicit logging configuration, and the module CLI; they verify the unsupported-lifespan fallback, a GET response, and WSGI method, path, query, and request-header values. | WSGI request-body, response-streaming, error, factory, and platform behavior remain unverified. The compatibility adapter executes the WSGI callable in Python; Uvicorn marks its native WSGI adapter as deprecated. |
| Bind to a Unix-domain socket | `python -m uvicorn --uds PATH` and the `Config(..., uds=PATH)` / `Server.run()` path each pass a live HTTP/1.1 GET comparison against Uvicorn 0.54.0. The ASGI scope matches Uvicorn for `client=None` and `server=(PATH, None)`. | These cases cover plain HTTP on POSIX. Unix-domain sockets are unavailable on Windows. TLS, HTTP/2, WebSockets, and other UDS-specific behaviors are not established. |
| Use pre-bound TCP listeners | Five live HTTP/1.1 GET comparisons pass against Uvicorn 0.54.0: module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two listeners. The two-listener case requires a successful response from each socket and graceful SIGINT exit. | These cases verify IPv4 listeners on macOS with Python 3.12. IPv6, Windows, TLS, and HTTP/2 or HTTP/3 over inherited sockets remain unverified. |
| Run multiple Python workers | Two focused module-CLI comparisons verify two workers serve an HTTP/1.1 request and stop on SIGINT: one sets `--workers 2`, the other sets `WEB_CONCURRENCY=2`. Both match Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. | This proves the two-worker TCP startup/request/SIGINT path only. Worker crash recovery, health-check expiry, worker-count signals, other sockets/platforms, and reload remain unverified. |
| Lifespan and graceful shutdown | Startup, shutdown, application failures, and selected cancellation paths have live cases. `lifespan="off"` passes focused public API and module CLI comparisons against Uvicorn 0.54.0. Focused `Config`/`Server.serve()` and module CLI cases verify that an app exception before startup under `lifespan="on"` leaves the server unstarted and exits with code 3. | Other strict-mode failure classes remain unverified. The two multi-worker cases above cover only successful startup/request/SIGINT; reload and broader process control remain unqualified. |
| Use the native Rust library | The source contains a Python-free `uvicorn-rs` Cargo library for Rust services. | It is experimental and unpublished. See [native Rust integration](native-fastapi-composition.md). |
| Match Uvicorn's CLI and Python API | Incomplete. Focused inputs cover default serving and shutdown, console-script current-directory import resolution, `--http h11` selector acceptance and one POST request, non-default `--backlog` with a live HTTP request, `--timeout-keep-alive` closing an idle HTTP/1 connection, `--limit-max-requests 0` startup shutdown and one-request natural shutdown using `UVICORN_LIMIT_MAX_REQUESTS=1`, plain HTTP/1.1 over `--uds` through the module CLI and `Config`/`Server`, inherited TCP listeners through `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)`, and `Server.run(sockets=[...])` with one or two listeners, `--use-colors` and `--no-use-colors` through the module CLI, `use_colors=True` through `uvicorn.run()`, selected lifespan behavior, `root_path`, environment-file loading, response headers, trusted proxy behavior and `FORWARDED_ALLOW_IPS` default/argument precedence, ASGI2 and WSGI selection, WebSocket message-size and server-keepalive CLI settings, a non-default worker healthcheck timeout through `Config`/`Server` with one worker, `WEB_CONCURRENCY=0` through `Config`/`Server` as a single-process setting, the selected asyncio loop through `Config`/`Server.run()`, default server/access log events, INI, JSON, and YAML logging configuration through `uvicorn.run()` and the module CLI, including `UVICORN_LOG_CONFIG`, `UVICORN_LOG_LEVEL=debug` through the module CLI, explicit `--log-level warning` precedence over that environment value, access-log suppression through `uvicorn.run(access_log=False)` and `--no-access-log`, and warning-level filtering through `uvicorn.run()` and the module CLI. | These are narrow cases, not full CLI or API parity. The Rust engine has one HTTP implementation, so selectors route to it; parser-specific malformed-request behavior is not established. Raw logs are retained and normalized log events compare color presence as well. Other levels and environment combinations, traceback frame formatting, and most runtime options remain unverified. Detailed case results and current evidence identity are in the [maintainer evidence record](maintainers/uvicorn-0.54.0-contract.md). |

## Known behavior limits

- HTTP/2 response comparisons use Hypercorn because Uvicorn has no HTTP/2
  server. They compare repeated values in order for each field name, while
  ignoring global order across different names and the implementation-specific
  `Server` value. RFC 9110 [Section 5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3)
  says order across different field names is insignificant. Raw observations
  remain available in each parity receipt.
- The complete official ASGI conformance suite has not been run.
- The latest matched Python FastAPI results do not establish a general speed
  advantage over Uvicorn. See [benchmark results](benchmark-results.md) and
  [current benchmark status](benchmark-status.md).
- Detailed case IDs, source identities, historical receipts, and coverage
  accounting are kept in the [maintainer evidence record](maintainers/asgi-support-evidence.md).

## Try the current prototype

Follow the [quickstart](quickstart.md) to run the checked-out example. The
[configuration guide](configuration.md) lists the prototype's current options.
