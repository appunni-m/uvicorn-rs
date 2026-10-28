# ASGI and protocol support

This page summarizes behavior verified against the checked-out source. It does
not claim complete ASGI conformance or full Uvicorn compatibility.

The Python distribution target is `uvicorn-rs`, exposing the `uvicorn` import
namespace and command. `uvicorn-rs-py` remains the optional Cargo/PyO3 adapter.
The Cargo release targets are `asgi-lifespan-protocol-rs` and one server crate,
`uvicorn-rs`; HTTP/3 is behind its optional `http3` feature. The publisher is
`.github/workflows/release.yml`. The old `native-app-contract`,
`uvicorn-rs-h3`, and `uvicorn-rs-h3-quinn` names are not release targets. Clean
candidate artifacts and downstream consumer checks remain open; see
[release status](releases.md).

## Latest completed public parity evidence (2026-10-28)

The `input@43` snapshot at commit `a4a520aeb42481cba06cbf4de597c993280d380e`
contains 695 oracle cases. Hosted CI
[#451](https://github.com/appunni-m/uvicorn-rs/actions/runs/40626804831) passed
**695/695** against the installed normal wheel on Ubuntu 24.04.5 / x86-64 /
CPython 3.12.13. The report is in artifact `uvicorn-rs-public-parity`
(artifact ID `12790545953`); it binds to PR head
`a4a520aeb42481cba06cbf4de597c993280d380e` and source SHA-256
`2b52f36acd7ecce4bec2edcf1df8a6b4cc696a44a4bfcfcfabf917af81fc95c0`.

The same 695 cases passed **695/695** in a local source-mode run on a clean
checkout of that commit, macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.
Run ID `20188eddd2394a13a966e69d9443a723`; report
`target/kata-progress/public-parity-macos-a4a520a-20261028-retry.json`,
SHA-256 `d8e2e8abfe7db162ec122f70a8f537457aeaf20a5a781e1e8de622d0cee9a176`.
The Mac run is source-mode evidence, not an installed-wheel check. These two
results cover the declared public inputs on Linux x86-64 and macOS ARM64; they
do not establish Windows or other Python-version support, or full Uvicorn
compatibility beyond the maintained cases.

These receipts bind to the earlier committed 695-case snapshot at `a4a520aeb`.
Commit `8f50720cd0e1cc12fdb8d6c60b7108c8a14cc516` adds four oracle cases: three
dotenv syntax, interpolation, process-environment, and server-setting cases,
plus `python-api.config-default-settings`. The four selected local cases pass
4/4 across focused runs. The Config probe first
exposed two mismatches (`env_file` was stored and default headers remained
`None`); the target now matches Uvicorn 0.54.0. These reports use a dirty target
and are diagnostic only, so the four cases are not counted as accepted parity
evidence here.

The current public input inventory has 699 cases. CI #451 was canceled during
its first coverage attribution pass at 785/1,217; its uploaded artifact is
incomplete. CI
[#452](https://github.com/appunni-m/uvicorn-rs/actions/runs/40633854307) is
validating the 699-case commit; its installed-wheel parity and unified coverage
jobs are still running. No current 100% coverage result or accepted
Coverage-MCP receipt is available. The benchmark matrix remains paused until
parity is complete. The earlier CI #447 and #446 counts below are historical.

Current input@43 has a focused 6/6 macOS
pass for module-CLI environment behavior: listener host/port settings, a valid
`UVICORN_LIMIT_CONCURRENCY` limit, and explicit CLI precedence over valid and
invalid concurrency environment values, WSGI selection through UVICORN_INTERFACE, and explicit ASGI3 precedence over the WSGI environment selection. It does not establish full CLI/API parity. See
the [parity receipt](parity.md#module-cli-environment-parity-2026-10-27). Two selected CLI process cases cover malformed `UVICORN_INTERFACE=invalid`
rejection and explicit `--interface asgi3` precedence over that value; a focused
two-case group also passes 2/2 for malformed `UVICORN_LOG_LEVEL` and explicit
`--log-level` precedence. A separate selected case passes 1/1 when explicit
`--timeout-graceful-shutdown 1` overrides malformed
`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`; this checks parsing/startup precedence,
while held-request cases cover actual timeout behavior. Two additional
selected cases pass 2/2 when explicit `--ws-max-size` and `--ws-ping-timeout`
override malformed environment values; they verify parse/startup precedence,
not WebSocket session behavior. See the [interface result](parity.md#invalid-module-cli-interface-environment-2026-10-27),
[log-level result](parity.md#module-cli-log-level-environment-parity-2026-10-27),
[graceful-shutdown precedence result](parity.md#explicit-module-cli-graceful-shutdown-value-overrides-malformed-environment-2026-10-27), and
[WebSocket precedence result](parity.md#module-cli-websocket-environment-precedence-2026-10-27).
Four additional focused CLI cases pass 4/4: malformed
`UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER` values
produce matching diagnostics, and explicit zero-valued CLI options override
each malformed value. See the [request-limit environment result](parity.md#module-cli-request-limit-environment-validation-and-precedence-2026-10-27).
Six more selected cases pass 6/6 for malformed backlog, keep-alive timeout,
and worker-healthcheck timeout environment values and explicit CLI overrides.
See the [numeric settings environment result](parity.md#module-cli-numeric-settings-environment-validation-and-precedence-2026-10-28).
Seven additional selected cases pass 7/7 for malformed WebSocket max-queue,
ping-interval, and per-message-deflate environment values with explicit CLI
overrides, plus explicit concurrency-limit precedence over malformed
environment. See the [WebSocket and concurrency environment result](parity.md#module-cli-websocket-and-concurrency-environment-precedence-2026-10-28).
Ten focused cases also pass 10/10 for malformed HTTP, WebSocket, lifespan,
worker-count, and reload-delay environment values with explicit valid CLI
overrides. See the [selector and process-setting environment result](parity.md#module-cli-selector-and-process-setting-environment-precedence-2026-10-28).
Four additional focused process cases pass 4/4 for environment resolution and
explicit flag precedence for `UVICORN_APP_DIR` and `UVICORN_ENV_FILE`; these
verify app import and env-file diagnostics, not the full CLI environment
contract. See the [app-dir and env-file result](parity.md#module-cli-app-dir-and-env-file-environment-precedence-2026-10-28).
Four more focused HTTP cases pass 4/4 for `UVICORN_ACCESS_LOG=false`,
`UVICORN_USE_COLORS=true`, and explicit access-log/no-color options overriding
opposing environment values. Request results and normalized log observations
match. See the [logging environment result](parity.md#module-cli-logging-boolean-environment-precedence-2026-10-28).
Two additional request cases cover environment suppression of the default
`Server` and `Date` headers, plus explicit `--server-header` precedence over
its false environment value. The environment-only case passed; after excluding
the dynamic timestamp from comparison, the explicit case passed 1/1. See the
[header environment result](parity.md#module-cli-header-environment-behavior-2026-10-28).
Three focused CLI process cases pass 3/3 for a valid `UVICORN_RELOAD_DIRS`
path, rejection of a missing environment path, and explicit `--reload-dir`
precedence over that invalid value. They verify parsing and precedence; live
directory watching remains covered separately. See the
[reload-directory environment result](parity.md#module-cli-reload-directory-environment-binding-2026-10-28). Two focused live reload cases pass 2/2 with `UVICORN_RELOAD_INCLUDES=*.txt` and `UVICORN_RELOAD_EXCLUDES=ignored.txt`: the excluded-file change does not reload, the included-file change does, and explicit `--reload-include`/`--reload-exclude` flags override conflicting environment patterns. Both exit cleanly on SIGINT. See the [reload-filter environment result](parity.md#module-cli-reload-filters-from-environment-2026-10-28).

## Can I replace Uvicorn?

Not yet. The `uvicorn-rs` PyPI distribution is not published and is not a
drop-in replacement today. The source namespace exposes the pinned `run`, `main`, `Config`, and `Server`
entry points and includes `uvicorn.importer`. Parity evidence includes a
one-pass local run of all 926 ASGI inputs and 258 native contracts (1,184
passed, zero failures) on an earlier dirty source snapshot on macOS 15.7.7
ARM64 / CPython 3.12.13, plus a later focused repeated-SIGINT case on newer
dirty source; hosted CI run
`40317129093` passed 508/508 public cases against an installed wheel on Ubuntu
24.04.5 / CPython 3.12.13; and a fresh current-source wheel passed four
selected installed-candidate comparisons plus the installed-consumer smoke.
These are one-pass and selected receipts. The three-repeat CI gate, 100%
coverage, complete supported-platform matrix, and full Uvicorn command, API,
and deployment contracts remain open. See the [maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md).
One selected POSIX
case verifies replacement after a worker stops answering health checks. A
separate two-worker SIGTERM input passed 1/1 on the local dirty draft on macOS
15.7.7 ARM64 / CPython 3.12.13: both servers returned HTTP 200, logged receipt
of SIGTERM, and exited 0 without timing out. A newer focused parity case sent
two actual SIGINT signals while a request task remained active; both module-CLI
processes returned HTTP 200 and exited 0 without timing out. It is one macOS
case, and its forced-cancellation traceback logs are retained but not compared.
A separate `SIGTTIN`/`SIGTTOU`
input also passed 1/1 on the local dirty draft on macOS ARM64 / CPython 3.12.13:
the normalized logs match Uvicorn as worker count scales from two to three and
back, followed by clean SIGINT shutdown. Another focused case verifies
replacement after two consecutive worker crashes. A SIGHUP input restarts both
workers with matching Uvicorn logs. A separate failure-path input forces a
replacement worker's lifespan startup to fail; both servers keep the old
workers serving HTTP 200 and log the failure. These selected POSIX paths do
not qualify other process-control signals, Windows or other platforms, or
broader restart/failure policy. Reload filters and other platform combinations
remain open. See the [focused SIGTERM evidence](maintainers/uvicorn-0.54.0-contract.md#two-worker-sigterm-shutdown),
[second-SIGINT evidence](maintainers/uvicorn-0.54.0-contract.md#actual-repeated-sigint-shutdown-with-an-active-request),
[two-crash evidence](maintainers/uvicorn-0.54.0-contract.md#two-consecutive-worker-crashes-and-replacement),
[worker-count signal evidence](maintainers/uvicorn-0.54.0-contract.md#live-worker-count-signals),
and [SIGHUP restart evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-worker-restart),
plus the [SIGHUP replacement-startup failure evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-replacement-startup-failure).
If your app depends on unverified
behavior, continue to use upstream Uvicorn. See
[replacement status](uvicorn-compatibility.md) for the current package status
and migration guidance.

## Supported behaviors

| If you need… | Current status | What to keep in mind |
| --- | --- | --- |
| Run a Python ASGI 3 application | Implemented in the source checkout and covered by live protocol cases. Matched async callable-instance cases pass 2/2 through `uvicorn.run()` and the module CLI with `interface="auto"`; see [the focused receipt](parity.md#asgi3-callable-instance-parity-2026-10-28). | This is an experimental adapter; Python application code still runs in Python. |
| Serve an application factory | Programmatic and module-CLI cases cover no-argument factories returning ASGI 3, ASGI 2, and WSGI callables. The implicit ASGI 3 factory pair passes 2/2 without a factory flag through `uvicorn.run()` and the module CLI; see [the focused receipt](parity.md#implicit-asgi3-application-factory-parity-2026-10-28). The ASGI 2 factory pair passes 2/2 with `interface="auto"` through both entry points; see [the focused receipt](parity.md#asgi2-application-factory-parity-2026-10-28). The WSGI factory group passes 2/2 through `uvicorn.run(factory, factory=True, interface="wsgi")` and `python -m uvicorn --factory --interface wsgi`, with HTTP 200 and clean SIGINT shutdown against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. | Other factory return types, factory combinations, and failure paths remain unverified. |
| HTTP/1.1 | Implemented and exercised with request/response, streaming, disconnect, TLS, and idle keep-alive timeout cases. | The 695-case public matrix, including the 1 MiB upload input, passed on clean source commit `a4a520aeb` on macOS 15.7.7 ARM64 / CPython 3.12.13 and on an installed wheel in hosted Linux x86-64 CI. The upload case sends sixteen 64 KiB chunks on one connection; it does not establish behavior at 64-client concurrency. |
| Invalid ASGI response starts | Twelve HTTP/1 and HTTP/2 inputs compare invalid response-header names and values, missing or malformed status, and a non-iterable headers field. Both servers close without generating a replacement HTTP 500. Those cases passed in the earlier 695/695 snapshot on macOS source and the hosted Linux wheel at `a4a520aeb`. CI #452 is revalidating the 699-case snapshot at `8f50720cd`. Malformed cases outside the declared inputs and other platforms remain separate gates. See the [seven-case H1/H2 receipt](parity.md#invalid-asgi-response-start-parity-2026-10-28) and [five-case HTTP/2 extension](parity.md#http2-invalid-response-start-parity-extension-2026-10-28). |
| HTTP/2 | Implemented and exercised over TLS and cleartext prior knowledge. | The support claim is limited to the tested HTTP/2 behaviors listed in this matrix. |
| HTTP/3 | Experimental; selected requests, streaming, cancellation, and shutdown behaviors have live cases. | There is no Uvicorn HTTP/3 baseline. Check the current benchmark status before relying on performance results. |
| Password-protected TLS keys | Focused Uvicorn comparisons cover PKCS#8 encrypted keys through `Config`/`Server` and the module CLI, plus traditional encrypted RSA keys using AES-128-CBC, AES-192-CBC, and AES-256-CBC. Selected cases cover wrong-password rejection, startup failure with an unsupported traditional cipher, missing or malformed `DEK-Info`, invalid `Proc-Type`, a missing end marker, an odd-length AES-256 IV, and non-hex characters in either IV nibble. | The additional traditional-key cases are focused local dirty-source inputs, not a complete TLS matrix or clean hosted release evidence. Encrypted EC keys and other legacy ciphers remain unverified. |
| TLS client-certificate configuration | Selected Uvicorn comparisons cover trusted and optional client certificates, TLS 1.2, untrusted clients without configured roots, `ssl_cert_reqs=3`, and startup rejection of an empty `ssl_ca_certs` file. | These are focused Config/Server inputs on macOS ARM64 / CPython 3.12.13; they do not establish complete client-authentication parity across platforms or TLS versions. |
| WebSockets | The native `WebSocketUpgrade`/`WebSocketSession` API owns HTTP/1.1 handshake and session transport; the Python ASGI adapter uses the same path and keeps Python calls on its event loop. Selected handshake, message, disconnect, shutdown, and server keepalive cases are implemented. The focused `websocket.unoffered-subprotocol-selection` parity case confirms the ASGI adapter returns a valid app-selected subprotocol even when it was not offered, matching Uvicorn 0.54.0; native Rust callers retain offer validation. Live Uvicorn comparisons verify `--ws-max-size` closes an oversized message with code 1009 before the ASGI app receives it, and verify server Ping, matching Pong, second Ping, and timeout close using `--ws-ping-interval 0.1 --ws-ping-timeout 0.3`. A CLI input accepts `--ws-ping-interval 0` during startup and exits with `--limit-max-requests 0`. An active-session Python API input sets a zero interval, idles for 0.35 seconds, then exchanges a message and closes normally against Uvicorn 0.54.0. This checks connection and application availability after the interval but does not observe Ping frames, so wire-level ping suppression is not established. A Python API case verifies `ws_ping_timeout=-0.1` closes with code 1011 before an application message. A NaN timeout case stays connected after 0.35 seconds idle and then exchanges a message, matching Uvicorn 0.54.0. On auto/SansIO and wsproto paths, `ws_max_queue` remains unset because those Uvicorn backends do not consume it. On the legacy `websockets` selector, the native ASGI receive channel is bounded by this setting; one delayed-reader case verifies three messages with `ws_max_queue=1`. Proxy cases verify forwarded `http` and `https` produce ASGI `ws` and `wss` schemes, and explicit forwarded `wss` is preserved. | The default `ws_per_message_deflate=true` negotiates per-message-deflate when offered; focused Python API cases verify one compressed text echo with normal close and verify that `false` disables negotiation against Uvicorn 0.54.0. This does not establish other extension parameters, fragmented compressed messages, or full backend parity. The selected API cases also cover a finite timeout beyond Rust's Duration range, a NaN timeout, and a positive infinite interval against Uvicorn 0.54.0; the infinite-interval and NaN-interval cases confirm connection and message survival but not wire-level ping behavior. The queue comparison covers one setting and unfragmented messages only; other thresholds, fragmented messages, and flow-control timing remain unverified. WebSockets over HTTP/2 or HTTP/3 are not supported. |
| Select the Uvicorn `wsproto` WebSocket backend | The `--ws wsproto` selector routes to the native implementation. One live comparison against Uvicorn 0.54.0's pinned `wsproto` 1.3.2 backend passes text and binary message exchange. | This does not establish full backend-specific parity for extensions, limits, timers, or failure behavior. |
| Select the legacy Uvicorn `websockets` backend | The `--ws websockets` selector routes to the native implementation. Live comparisons against Uvicorn 0.54.0 with pinned `websockets` 17.1 pass ordered text/binary exchange and a delayed-reader burst with `--ws-max-queue 1`; all three queued messages reach the ASGI app. | These are dirty-source macOS ARM64 cases, not full backend parity. The native bound counts complete ASGI messages, while upstream `websockets` applies its high-water mark to frames. Other thresholds, fragmented messages, and flow-control timing remain unverified. |
| Request and response streaming | Tested cases cover incremental uploads, streamed response chunks, backpressure, and selected cancellation paths. | The tests do not cover every timing race or every ASGI extension. |
| Mount an app under an ASGI root path | HTTP/1.1 contract inputs through `uvicorn.run()` and `python -m uvicorn --root-path ...` verify `root_path`, prefixed `path`, and the raw request path. A WebSocket parity input verifies `root_path` and prefixed decoded `path`; a separate live target requirement checks that WebSocket `raw_path` preserves the original percent-encoded request path. A separate HTTP parity input verifies percent-encoded UTF-8 request-path decoding with an empty `root_path`. | The root-path contract checks uvicorn-rs against ASGI scope expectations and compares exit code, response receipt, shutdown signal, and timeout state with Uvicorn; it does not compare the scope response body because Uvicorn 0.54.0 adds `root_path` to `raw_path`. Its default WebSocket SansIO backend does the same. Uvicorn also rejects a Unicode `root_path` with HTTP 400 before invoking the app. The ASGI spec defines `raw_path` as the original request path bytes, excluding the query string ([ASGI HTTP and WebSocket scope](https://asgi.readthedocs.io/en/stable/specs/www.html#http-connection-scope)); uvicorn-rs preserves those bytes without adding the configured root path. The `raw_path` difference is a deliberate standards-based deviation from Uvicorn 0.54.0. HTTP/2 and HTTP/3 root-path behavior is untested. |
| Set default response headers | The CLI `--header` policy passes focused comparisons against Uvicorn 0.54.0 for a colon-containing value, repeated identical values, and disabled default Server/Date headers. `uvicorn.run(headers=[(name, value)])` also passes focused comparisons. | Programmatic HTTP/1.1 cases cover custom-header delivery and duplicate value order. Other header-validation behavior remains unverified. |
| Preserve ASGI response-header order | The HTTP/1.1 encoder now accepts an explicit header-order extension. Two focused input-only cases pass strict order comparison against Uvicorn 0.54.0: custom headers with default Server/Date fields disabled, and interleaved duplicate fields with defaults enabled. | These are separate source-bound dirty-draft receipts, not the full HTTP/1.1 response-header matrix; other H1 cases still compare per-name values. HTTP/2 order remains mismatched, and HTTP/3 raw wire order is unverified because its probe observes through `HeaderMap`. ASGI 2.5 requires preserving response-start headers as provided even though RFC 9110 §5.3 does not assign semantics to order across different field names. See [the detailed evidence and known gaps](asgi-case-inventory.md#known-gaps-and-unsupported-surface), [ASGI response start](https://asgi.readthedocs.io/en/stable/specs/www.html#response-start-send-event), and [RFC 9110 §5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3). |
| Limit concurrent connections and requests | `--limit-concurrency 1`, `uvicorn.run(limit_concurrency=1)`, and `Config(limit_concurrency=1)` with `Server.run()` pass focused HTTP/1.1 comparisons against Uvicorn 0.54.0. The Python API cases compare the 503 response and SIGINT shutdown outcome. | Other limit values and HTTP/2/HTTP/3 behavior remain unverified. |
| Stop after a completed-request limit | A module CLI case with `UVICORN_LIMIT_MAX_REQUESTS=1` returns one HTTP/1.1 response and exits naturally, matching Uvicorn 0.54.0. A separate `--limit-max-requests 0` case verifies shutdown after startup without serving a request. With base limit 2 and jitter 1, a live case verifies natural exit after 2–3 HTTP/1.1 responses; the randomized count is retained in the receipt and checked against that range. | These cases cover one HTTP/1.1 connection pattern. Concurrent completion, TLS, HTTP/2/HTTP/3, WebSocket interactions, and negative jitter behavior remain unverified. |
| Honor trusted proxy headers | Focused HTTP/1.1 CLI and `uvicorn.run()` cases pass against Uvicorn 0.54.0 with an explicit loopback trust list; the app observes the forwarded client address and HTTPS scheme. Separate cases verify disabled handling, an excluded peer, wildcard and CIDR trust, opaque malformed tokens, empty `X-Forwarded-For` preserving the direct peer, the all-trusted-chain fallback, duplicate forwarding-field behavior, and uppercase unsupported proto being ignored. | Other address/network combinations and malformed `X-Forwarded-For` forms, other environment precedence/settings, and some WebSocket forwarded-protocol values remain unverified. |
| Load app environment files | The module CLI and `uvicorn.run(env_file=...)` load an app-specific value before the factory runs in focused comparisons against Uvicorn 0.54.0. A separate CLI case confirms a pre-existing process environment value takes precedence over the same key in the env file. | Requires `python-dotenv`, available in the `[standard]` extra. Broader dotenv syntax and other precedence combinations remain unverified. |
| Run ASGI2 applications | `uvicorn.run()` and `python -m uvicorn` pass focused HTTP comparisons for auto-detection and explicit `interface="asgi2"` against Uvicorn 0.54.0. The Python adapter converts ASGI2 callables to the ASGI3 shape used by Rust. | Other callable forms remain unverified. |
| Run WSGI applications | Focused `uvicorn.run()` and `python -m uvicorn` comparisons pass against Uvicorn 0.54.0 with both `lifespan="off"` and `lifespan="auto"`. Auto-mode cases cover default logging, an explicit logging configuration, and the module CLI; they verify the unsupported-lifespan fallback, a GET response, and WSGI method, path, query, and request-header values. Two local buffered POST cases and six chunked-transfer POST cases, through uvicorn.run() and python -m uvicorn, verify request bodies reach wsgi.input (each passed 1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13); see the [focused parity receipts](parity.md#focused-wsgi-post-request-body-parity-2026-10-28). Two chunked cases use one data chunk, two use two chunks, and the new pair uses 64 chunks. Two more cases verify the first response byte reaches the client before a delayed WSGI response iterator completes through both entry points (2/2 on the same host); see [response-streaming parity](parity.md#wsgi-response-streaming-parity-2026-10-28). Two WSGI application-factory cases also pass through both entry points (2/2 in a separate focused run); the two pre-response application-error cases also pass 2/2 through both entry points; see [focused error parity](parity.md#wsgi-pre-response-application-error-parity-2026-10-28). see [application-factory parity](parity.md#wsgi-application-factory-parity-2026-10-28). | The cases establish one-, two-, and 64-chunk bodies; other chunk counts, large bodies, malformed lengths, response backpressure or other response-iterator patterns, errors after response start or other failure classes, other factory shapes, or cross-platform behavior. The compatibility adapter executes the WSGI callable in Python; Uvicorn marks its native WSGI adapter as deprecated. |
| Bind to a Unix-domain socket | `python -m uvicorn --uds PATH` and the `Config(..., uds=PATH)` / `Server.run()` path each pass a live HTTP/1.1 GET comparison against Uvicorn 0.54.0. The ASGI scope matches Uvicorn for `client=None` and `server=(PATH, None)`. A selected `Server.serve()` input also matches replacement of an existing socket pathname and lifespan cleanup on macOS; see the [one-case receipt](maintainers/uvicorn-0.54.0-contract.md#existing-uds-pathname-replacement-and-lifespan-cleanup). | The UDS results are focused local evidence on POSIX, not complete UDS compatibility or release evidence. Unix-domain sockets are unavailable on Windows. TLS, HTTP/2, WebSockets, and other UDS-specific behaviors are not established. |
| Use pre-bound TCP listeners | Five live HTTP/1.1 GET comparisons pass against Uvicorn 0.54.0 for IPv4: module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two listeners. Two focused module-CLI comparisons also pass for inherited IPv6 listeners with one and two workers. The two-listener case requires a successful response from each socket and graceful SIGINT exit. A current-source refresh also verifies the startup socket log for inherited IPv4 and IPv6 module-CLI sockets (2/2); see the [focused evidence](maintainers/uvicorn-0.54.0-contract.md#inherited-fd-startup-log-parity-2026-10-28). The IPv6 cases passed on macOS ARM64 / CPython 3.12.13 (run `bc282b37f69a46a38e8353a94197e2a7`, report SHA-256 `f55d9d1f8227452b0513446e2b96241fc63277c1f359ca761fb570a0ea94ca0f`). | Other IPv6 API paths, Windows, TLS, and HTTP/2 or HTTP/3 over inherited sockets remain unverified. |
| Run multiple Python workers or reload code | Two focused module-CLI comparisons verify two workers serve an HTTP/1.1 request and stop on SIGINT: one sets `--workers 2`, the other sets `WEB_CONCURRENCY=2`. A separate input kills one worker process and verifies replacement. A new POSIX input suspends a worker, uses `--timeout-worker-healthcheck 2`, and passes 1/1 against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13 (run `ae4e43b0e69245a8b22cd67668cdaeba`; report SHA-256 `eae083b94d0d0637b0005fa9278066b48b52f787f93b06c3e58113270a602e1e`). Both implementations log an additional server process, serve the request, and shut down cleanly. A reload input passes locally on macOS ARM64 / CPython 3.12.13 with `--workers 2` in both dependency modes: without `watchfiles`, the candidate's `StatReload` fallback matches the Uvicorn watchfiles oracle; with `watchfiles==1.3.0`, both use watchfiles. Each reload run edits a watched Python module, verifies the replacement response, compares the warning that reload ignores the worker count, and shuts down on SIGINT. | See the [two-crash evidence](maintainers/uvicorn-0.54.0-contract.md#two-consecutive-worker-crashes-and-replacement), [SIGHUP restart evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-worker-restart), and [SIGHUP replacement-startup failure evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-replacement-startup-failure); the restart cases cover one forced exit, two consecutive forced worker exits, one POSIX health-check expiry, a successful SIGHUP restart, and one failed replacement startup that preserves the old workers. Restart/failure policy beyond these paths, worker-count signals beyond the tested SIGTTIN/SIGTTOU pair, Windows and other socket/platform combinations remain unverified. One WatchFilesReload include/exclude case also passes: an excluded-file change did not reload, an included-file change did, and SIGINT exited cleanly. That case ran on macOS ARM64 / CPython 3.12.13; other glob combinations, fallback-watcher filtering, platforms, and reload startup/failure modes remain unverified. See the current-source receipts in the [maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md). Use upstream Uvicorn for those paths. |
| Lifespan and graceful shutdown | Startup, shutdown, application failures, and selected cancellation paths have live cases. Two focused module-CLI comparisons set the timeout through the CLI option and environment; both confirm that a held ASGI request is cancelled after 1 second, matching Uvicorn 0.54.0 on macOS ARM64. `lifespan="off"` passes focused public API and module CLI comparisons against Uvicorn 0.54.0. Focused `Config`/`Server.serve()` and module CLI cases verify that an app exception before startup under `lifespan="on"` leaves the server unstarted and exits with code 3. | Other strict-mode failure classes remain unverified. The worker cases cover successful startup/request/SIGINT, one worker crash/replacement, one two-crash replacement case, and one POSIX health-check expiry/replacement path; worker-control signals and broader process control remain unqualified. |
| Use the native Rust library | The source contains a Python-free `uvicorn-rs` server crate and a separate `asgi-lifespan-protocol-rs` lifecycle crate; HTTP/3 is gated by `uvicorn-rs`'s optional `http3` feature. | Clean release artifacts and downstream consumer checks for the current source remain unverified. See [release status](releases.md) and [native Rust integration](native-fastapi-composition.md). |
| Match Uvicorn's CLI and Python API | Incomplete. The input@40 CLI and Python API baselines passed 60/60 and 209/209 cases on macOS 15.7.7 ARM64 / CPython 3.12.13. The pushed input@43 snapshot declares 262 Python API oracle-comparison cases, 23 target-only fault contracts, and 117 CLI process cases. A read-only inventory audit compares the pinned Uvicorn 0.54.0 Click parameters with the combined CLI/Python API inputs and finds all 52 derived `UVICORN_*` names represented; this is input coverage, not behavioral proof. A focused `Config.load()` case also compares explicit factory TypeError handling through `SystemExit(3)`. The 12 new CLI environment cases have pass evidence across an 11/12 batch and a targeted 1/1 rerun; the six Python API cases have pass evidence across a 5/6 batch and a corrected 2/2 forwarding rerun. These focused receipts span input snapshots and are scoped to the listed behaviors. See [the maintainer contract](maintainers/uvicorn-0.54.0-contract.md) and [the parity evidence](parity.md). The six selected module-CLI environment cases (listener host/port, valid concurrency limit, explicit flag precedence over valid and invalid concurrency environment values, WSGI interface selection, and explicit interface precedence over a conflicting environment value) passed 6/6, and malformed `UVICORN_INTERFACE=invalid` passed as a separate 1/1 CLI process case on that host. The new `UVICORN_WORKERS=2` module-CLI case passed 1/1 on the same host, matching two worker startup log events, a 200 response, and clean shutdown. The `UVICORN_RELOAD=true` module-CLI case also passed 1/1, matching reloader startup and shutdown, a 200 response, and clean exit. The module-CLI `--reset-contextvars` behavior and missing `--reload-dir` diagnostic each passed 1/1. A new 2-case group passes for `UVICORN_RESET_CONTEXTVARS=true` and explicit flag precedence over a false environment value (run `63a21609687947c7974c80a1d9e4a7c0`; receipt SHA-256 `e63b4fcd4319a7fd5a83c4576f1ce3b41def2fa0d633cd589c70a6f271d0a756`). The 14 worker/reload startup-log cases that failed in CI #432 now pass 14/14 after preserving Uvicorn's parent-only listener message for supervisor-supplied sockets (run `b5228c0251f0492385b1ca422da32659`; receipt SHA-256 `aebe48b2e06c899bbf0f538ce9e9826dc1b6d3c4362cdbbff5a7f64d5c72af28`). Environment-only `UVICORN_PROXY_HEADERS=false` also passed 1/1, suppressing forwarded scheme and client overrides. Three more cases pass 3/3 for valid and invalid `UVICORN_RELOAD_DIRS` parsing plus explicit `--reload-dir` precedence. Exact run and input identities are in the [maintainer evidence record](maintainers/uvicorn-0.54.0-contract.md). These focused groups are dirty-source receipts. The earlier 695-case input@43 snapshot passed 695/695 on the clean macOS source checkout and 695/695 on the installed Linux wheel in CI #451. The pushed 699-case snapshot is being revalidated in CI #452; see the evidence near the top of this page. This does not establish full cross-platform CLI/API parity. Windows and other Python/platform combinations, target-only fault contracts, complete native coverage, and release artifacts remain open. Focused inputs cover default serving and shutdown, console-script current-directory import resolution, `--http h11` and `--http httptools` selector requests, non-default `--backlog` with a live HTTP request, `--timeout-keep-alive` closing an idle HTTP/1 connection, `--limit-max-requests 0` startup shutdown and one-request natural shutdown using `UVICORN_LIMIT_MAX_REQUESTS=1`, plain HTTP/1.1 over `--uds` through the module CLI and `Config`/`Server`, inherited TCP listeners through `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)`, and `Server.run(sockets=[...])` with one or two listeners, `--use-colors` and `--no-use-colors` through the module CLI, `use_colors=True` through `uvicorn.run()`, module-CLI `--reset-contextvars` default and reset behavior plus `uvicorn.run(reset_contextvars=True)`, selected lifespan behavior, `root_path`, environment-file loading, response headers, trusted proxy behavior, module-CLI `UVICORN_PROXY_HEADERS=false`, and `FORWARDED_ALLOW_IPS` default/argument precedence, ASGI2 and WSGI selection, WebSocket message-size and server-keepalive CLI settings, a non-default worker healthcheck timeout through `Config`/`Server` with one worker, `WEB_CONCURRENCY=0` through `Config`/`Server` as a single-process setting, environment-driven two-worker module-CLI startup through `UVICORN_WORKERS=2`, live module-CLI reload selection through `UVICORN_RELOAD=true`, the selected asyncio loop through `Config`/`Server.run()`, and a module-CLI custom import-string loop factory whose invocation marker matches 1/1 against the oracle (see [focused evidence](parity.md)); module-CLI checks for valid `--timeout-graceful-shutdown 1` option and environment values, plus held-request cases that confirm cancellation after the 1-second graceful timeout through both the CLI option and environment, default server/access log events, INI, JSON, and YAML logging configuration through `uvicorn.run()` and the module CLI, including `UVICORN_LOG_CONFIG`, `UVICORN_LOG_LEVEL=debug` through the module CLI, explicit `--log-level warning` precedence over that environment value, access-log suppression through `uvicorn.run(access_log=False)` and `--no-access-log`, and warning-level filtering through `uvicorn.run()` and the module CLI. | These are narrow cases, not full CLI or API parity. The Rust engine has one HTTP implementation, so selectors route to it; the `httptools` request case passed 1/1 against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. Parser-specific malformed-request behavior is not established. Raw logs are retained and normalized log events compare color presence as well. Other levels and environment combinations, traceback frame formatting, and most runtime options remain unverified. Detailed case results and current evidence identity are in the [maintainer evidence record](maintainers/uvicorn-0.54.0-contract.md). |

## Known behavior limits

- Uvicorn 0.54.0 now provides experimental HTTP/2 through `zttp`; the parity
  oracle selects it with `--http zttp --http2`. A local aggregate run passed
  all 27 maintained HTTP/2 parity inputs against that stack on macOS ARM64 and
  CPython 3.12.13. The HTTP/2 category benchmark and hosted release evidence
  remain pending. Earlier HTTP/2 receipts used Hypercorn. Header
  comparisons preserve repeated values within each field name while ignoring
  order across different names and the implementation-specific `Server` value.
  RFC 9110 [Section 5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3)
  says order across different field names is insignificant; raw observations
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
