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

## Current verification status (2026-10-31)

PR #19 is draft against `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. The h11 fix is committed at
`6342b20402bf0cceabd8eafde3f067e1620bafba`; its runtime-source SHA-256 is
`c00038a3885178b4bb1146fc315a51eb70c5e149a1742a16d3bdada8c7bee50f`.
Its fresh clean hosted matrix is
[CI #536](https://github.com/appunni-m/uvicorn-rs/actions/runs/41151116481),
still running. A separate focused coverage follow-up is described on the
[coverage page](coverage.md).

Full hosted CI [#531](https://github.com/appunni-m/uvicorn-rs/actions/runs/41140694132)
ran on the previous branch head `48aba59dc12ab4fa9c6195d95d2fabd226b4a052`.
Linux installed-wheel parity passed 719/719. Windows passed 689/692; its only
three failures were two-worker shutdown cases. Those case inputs now pass 3/3
on focused current-input runs for Windows
[#534](https://github.com/appunni-m/uvicorn-rs/actions/runs/41145100547) and
Linux [#535](https://github.com/appunni-m/uvicorn-rs/actions/runs/41145558362).
A full local macOS ARM64 / CPython 3.12.13 installed-wheel run on baseline
`ed60fef` passed 719/719, zero failed/infra/not-run; report run
`4f0fd48142f34ddd931639928a6daf4d`, SHA-256
`17215002f939d255069c6fef20f0c1cd43ca1d17e981e2c29d2e6edbb6a07780`. The
focused case union is useful evidence but is not a full exact-current-input
hosted Linux and Windows matrix.

The #531 three-repeat coverage run attributed 1,341/1,341 cases but missed the
100% gate at 14,137/14,252 regions and 10,411/10,465 lines. Its report binds to
the earlier merge ref. No accepted exact-source Coverage-MCP review exists.
The Linux 0.2.2 candidate artifact and clean consumers passed on that earlier
ref; Windows candidate verification failed after parity and macOS candidate
verification was cancelled. The docs deployment run #215 passed for an earlier
revision; the current docs edits still need deployment. Details and artifact
identity are in the [maintainer completion plan](maintainers/release-completion-plan.md).

The current CLI map covers 52 declared parameters and indexes 118 CLI process
inputs. Six new live CLI WebSocket cases passed 6/6 locally on the preceding
runtime. Four new h11 boundary inputs exposed early rejection and HTTP 431
instead of 400; the fix passes those four and the existing expanded-header
case 5/5, including a 1 KiB limit. See the
[CLI/settings map](maintainers/uvicorn-cli-option-map.md).
The API and protocol children remain open for exact committed-source hosted
acceptance. Full Uvicorn 0.54.0 compatibility and 100% coverage are not
established.

Cargo `uvicorn-rs` and `asgi-lifespan-protocol-rs` are published at 0.2.1;
0.2.2 is still a candidate. The PyPI `uvicorn-rs` project remains unpublished.
The `release.yml` PyPI pending publisher is saved, and the maintainer confirms
both crates.io Trusted Publisher entries are already configured. No candidate
is accepted for publication. Benchmarks remain behind complete parity; the
older Linux ARM64 HTTP/3 benchmark is incomplete. The declared Python 3.9
consumer check is separate from the Uvicorn 0.54.0 parity baseline, which
starts at Python 3.10. See [coverage evidence](coverage.md), [parity history](parity.md),
and [release status](releases.md).

## Can I replace Uvicorn?

Not yet. The `uvicorn-rs` PyPI distribution is unpublished and the full
compatibility matrix and coverage gate have not passed. A clean candidate is
not accepted across all required platforms. The new CLI WebSocket and h11
observations still need the full hosted matrix. The real FastAPI application trial is for
the maintainer to run after repository acceptance. See the
[maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md).
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
| HTTP/1.1 | Implemented and exercised with request/response, streaming, disconnect, TLS, and idle keep-alive timeout cases. | CI #461's 714-case Linux public parity matrix includes the 1 MiB upload input (sixteen 64 KiB chunks on one connection) for PR head `0591996`; it does not establish behavior at 64-client concurrency. Later local commits are not included in that run. |
| Invalid ASGI response starts | Twelve HTTP/1 and HTTP/2 inputs compare invalid response-header names and values, missing or malformed status, and a non-iterable headers field. Both servers close without generating a replacement HTTP 500. The prior Linux and local macOS inventories exercised these cases on earlier source snapshots; they do not bind to the current head. Malformed cases outside the declared inputs and Windows behavior remain unverified. See the [seven-case H1/H2 receipt](parity.md#invalid-asgi-response-start-parity-2026-10-28) and [five-case HTTP/2 extension](parity.md#http2-invalid-response-start-parity-extension-2026-10-28). |
| HTTP/2 | Implemented and exercised over TLS and cleartext prior knowledge. | The support claim is limited to the tested HTTP/2 behaviors listed in this matrix. |
| HTTP/3 | Experimental; selected requests, streaming, cancellation, and shutdown behaviors have live cases. | There is no Uvicorn HTTP/3 baseline. Check the current benchmark status before relying on performance results. |
| Password-protected TLS keys | Focused Uvicorn comparisons cover PKCS#8 encrypted keys through `Config`/`Server` and the module CLI, plus traditional encrypted RSA keys using AES-128-CBC, AES-192-CBC, and AES-256-CBC. Selected cases cover wrong-password rejection, startup failure with an unsupported traditional cipher, missing or malformed `DEK-Info`, invalid `Proc-Type`, a missing end marker, an odd-length AES-256 IV, and non-hex characters in either IV nibble. | The additional traditional-key cases are focused local dirty-source inputs, not a complete TLS matrix or clean hosted release evidence. Encrypted EC keys and other legacy ciphers remain unverified. |
| TLS client-certificate configuration | Selected Uvicorn comparisons cover trusted and optional client certificates, TLS 1.2, untrusted clients without configured roots, `ssl_cert_reqs=3`, and startup rejection of an empty `ssl_ca_certs` file. | These are focused Config/Server inputs on macOS ARM64 / CPython 3.12.13; they do not establish complete client-authentication parity across platforms or TLS versions. |
| WebSockets | The native `WebSocketUpgrade`/`WebSocketSession` API owns HTTP/1.1 handshake and session transport; the Python ASGI adapter uses the same path and keeps Python calls on its event loop. Selected handshake, message, disconnect, shutdown, and server keepalive cases are implemented. The focused `websocket.unoffered-subprotocol-selection` parity case confirms the ASGI adapter returns a valid app-selected subprotocol even when it was not offered, matching Uvicorn 0.54.0; native Rust callers retain offer validation. Live Uvicorn comparisons verify `--ws-max-size` closes an oversized message with code 1009 before the ASGI app receives it, and verify server Ping, matching Pong, second Ping, and timeout close using `--ws-ping-interval 0.1 --ws-ping-timeout 0.3`. A CLI input accepts `--ws-ping-interval 0` during startup and exits with `--limit-max-requests 0`. An active-session Python API input sets a zero interval, idles for 0.35 seconds, then exchanges a message and closes normally against Uvicorn 0.54.0. This checks connection and application availability after the interval but does not observe Ping frames, so wire-level ping suppression is not established. A Python API case verifies `ws_ping_timeout=-0.1` closes with code 1011 before an application message. A NaN timeout case stays connected after 0.35 seconds idle and then exchanges a message, matching Uvicorn 0.54.0. On auto/SansIO and wsproto paths, `ws_max_queue` remains unset because those Uvicorn backends do not consume it. On the legacy `websockets` selector, the native ASGI receive channel is bounded by this setting; one delayed-reader case verifies three messages with `ws_max_queue=1`. Proxy cases verify forwarded `http` and `https` produce ASGI `ws` and `wss` schemes, and explicit forwarded `wss` is preserved. | The default `ws_per_message_deflate=true` negotiates per-message-deflate when offered; focused Python API cases verify one compressed text echo with normal close and verify that `false` disables negotiation against Uvicorn 0.54.0. A selected raw-frame Uvicorn comparison also verifies one uncompressed fragmented text message and one `permessage-deflate` fragmented text message are each delivered as a single ASGI event; these are local dirty-source receipts, not cross-platform acceptance. Other extension parameters and full backend parity remain unverified. The selected API cases also cover a finite timeout beyond Rust's Duration range, a NaN timeout, and a positive infinite interval against Uvicorn 0.54.0; the infinite-interval and NaN-interval cases confirm connection and message survival but not wire-level ping behavior. The queue comparison covers one setting; fragmented-message queue behavior, other thresholds, and flow-control timing remain unverified. WebSockets over HTTP/2 or HTTP/3 are not supported. |
| Select the Uvicorn `wsproto` WebSocket backend | The `--ws wsproto` selector routes to the native implementation. One live comparison against Uvicorn 0.54.0's pinned `wsproto` 1.3.2 backend passes text and binary message exchange. | This does not establish full backend-specific parity for extensions, limits, timers, or failure behavior. |
| Select the legacy Uvicorn `websockets` backend | The `--ws websockets` selector routes to the native implementation. Live comparisons against Uvicorn 0.54.0 with pinned `websockets` 17.1 pass ordered text/binary exchange and a delayed-reader burst with `--ws-max-queue 1`; all three queued messages reach the ASGI app. | These are dirty-source macOS ARM64 cases, not full backend parity. The native bound counts complete ASGI messages, while upstream `websockets` applies its high-water mark to frames. Queue behavior during fragmentation, other thresholds, and flow-control timing remain unverified. |
| Request and response streaming | Tested cases cover incremental uploads, streamed response chunks, backpressure, and selected cancellation paths. | The tests do not cover every timing race or every ASGI extension. |
| Mount an app under an ASGI root path | HTTP/1.1 contract inputs through `uvicorn.run()` and `python -m uvicorn --root-path ...` verify `root_path`, prefixed `path`, and the raw request path. A WebSocket parity input verifies `root_path` and prefixed decoded `path`; a separate live target requirement checks that WebSocket `raw_path` preserves the original percent-encoded request path. A separate HTTP parity input verifies percent-encoded UTF-8 request-path decoding with an empty `root_path`. | The root-path contract checks uvicorn-rs against ASGI scope expectations and compares exit code, response receipt, shutdown signal, and timeout state with Uvicorn; it does not compare the scope response body because Uvicorn 0.54.0 adds `root_path` to `raw_path`. Its default WebSocket SansIO backend does the same. Uvicorn also rejects a Unicode `root_path` with HTTP 400 before invoking the app. The ASGI spec defines `raw_path` as the original request path bytes, excluding the query string ([ASGI HTTP and WebSocket scope](https://asgi.readthedocs.io/en/stable/specs/www.html#http-connection-scope)); uvicorn-rs preserves those bytes without adding the configured root path. The `raw_path` difference is a deliberate standards-based deviation from Uvicorn 0.54.0. HTTP/2 and HTTP/3 root-path behavior is untested. |
| Set default response headers | The CLI `--header` policy passes focused comparisons against Uvicorn 0.54.0 for a colon-containing value, repeated identical values, and disabled default Server/Date headers. `uvicorn.run(headers=[(name, value)])` also passes focused comparisons. | Programmatic HTTP/1.1 cases cover custom-header delivery and duplicate value order. Other header-validation behavior remains unverified. |
| Preserve ASGI response-header order | Two focused HTTP/1.1 inputs and one focused HTTP/2 input pass strict full-sequence comparison against Uvicorn 0.54.0. All three pass on exact branch source `98c90076748337ec2ef3f34a49b94bffd5ffcd22` in hosted Linux run [#503](https://github.com/appunni-m/uvicorn-rs/actions/runs/41044156010); the H2 path carries the original sequence into the vendored `h2` HPACK encoder. | This is not the full response-header matrix; other H1/H2 cases still compare per-name values. HTTP/3 raw wire order is unverified because its probe observes through `HeaderMap`. ASGI 2.5 requires preserving response-start headers as provided even though RFC 9110 §5.3 does not assign semantics to order across different field names. See [the detailed evidence and known gaps](asgi-case-inventory.md#known-gaps-and-unsupported-surface), [ASGI response start](https://asgi.readthedocs.io/en/stable/specs/www.html#response-start-send-event), and [RFC 9110 §5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3). |
| Limit concurrent connections and requests | `--limit-concurrency 1`, `uvicorn.run(limit_concurrency=1)`, and `Config(limit_concurrency=1)` with `Server.run()` pass focused HTTP/1.1 comparisons against Uvicorn 0.54.0. The Python API cases compare the 503 response and SIGINT shutdown outcome. | Other limit values and HTTP/2/HTTP/3 behavior remain unverified. |
| Stop after a completed-request limit | A module CLI case with `UVICORN_LIMIT_MAX_REQUESTS=1` returns one HTTP/1.1 response and exits naturally, matching Uvicorn 0.54.0. A separate `--limit-max-requests 0` case verifies shutdown after startup without serving a request. With base limit 2 and jitter 1, a live case verifies natural exit after 2–3 HTTP/1.1 responses; the randomized count is retained in the receipt and checked against that range. | These cases cover one HTTP/1.1 connection pattern. Concurrent completion, TLS, HTTP/2/HTTP/3, WebSocket interactions, and negative jitter behavior remain unverified. |
| Honor trusted proxy headers | Focused HTTP/1.1 CLI and `uvicorn.run()` cases pass against Uvicorn 0.54.0 with an explicit loopback trust list; the app observes the forwarded client address and HTTPS scheme. Separate cases verify disabled handling, an excluded peer, wildcard and CIDR trust, opaque malformed tokens, empty `X-Forwarded-For` preserving the direct peer, the all-trusted-chain fallback, duplicate forwarding-field behavior, and uppercase unsupported proto being ignored. | Other address/network combinations and malformed `X-Forwarded-For` forms, other environment precedence/settings, and some WebSocket forwarded-protocol values remain unverified. |
| Load app environment files | The module CLI and `uvicorn.run(env_file=...)` load an app-specific value before the factory runs in focused comparisons against Uvicorn 0.54.0. A separate CLI case confirms a pre-existing process environment value takes precedence over the same key in the env file. | Requires `python-dotenv`, available in the `[standard]` extra. Broader dotenv syntax and other precedence combinations remain unverified. |
| Run ASGI2 applications | `uvicorn.run()` and `python -m uvicorn` pass focused HTTP comparisons for auto-detection and explicit `interface="asgi2"` against Uvicorn 0.54.0. The Python adapter converts ASGI2 callables to the ASGI3 shape used by Rust. | Other callable forms remain unverified. |
| Run WSGI applications | Focused `uvicorn.run()` and `python -m uvicorn` comparisons pass against Uvicorn 0.54.0 with both `lifespan="off"` and `lifespan="auto"`. Auto-mode cases cover default logging, an explicit logging configuration, and the module CLI; they verify the unsupported-lifespan fallback, a GET response, and WSGI method, path, query, and request-header values. Two local buffered POST cases and six chunked-transfer POST cases, through uvicorn.run() and python -m uvicorn, verify request bodies reach wsgi.input (each passed 1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13); see the [focused parity receipts](parity.md#focused-wsgi-post-request-body-parity-2026-10-28). Two chunked cases use one data chunk, two use two chunks, and the new pair uses 64 chunks. Two more cases verify the first response byte reaches the client before a delayed WSGI response iterator completes through both entry points (2/2 on the same host); see [response-streaming parity](parity.md#wsgi-response-streaming-parity-2026-10-28). Two WSGI application-factory cases also pass through both entry points (2/2 in a separate focused run); the two pre-response application-error cases also pass 2/2 through both entry points; see [focused error parity](parity.md#wsgi-pre-response-application-error-parity-2026-10-28). see [application-factory parity](parity.md#wsgi-application-factory-parity-2026-10-28). | The cases establish one-, two-, and 64-chunk bodies; other chunk counts, large bodies, malformed lengths, response backpressure or other response-iterator patterns, errors after response start or other failure classes, other factory shapes, or cross-platform behavior. The compatibility adapter executes the WSGI callable in Python; Uvicorn marks its native WSGI adapter as deprecated. |
| Bind to a Unix-domain socket | `python -m uvicorn --uds PATH` and the `Config(..., uds=PATH)` / `Server.run()` path each pass a live HTTP/1.1 GET comparison against Uvicorn 0.54.0. The ASGI scope matches Uvicorn for `client=None` and `server=(PATH, None)`. A selected `Server.serve()` input also matches replacement of an existing socket pathname and lifespan cleanup on macOS; see the [one-case receipt](maintainers/uvicorn-0.54.0-contract.md#existing-uds-pathname-replacement-and-lifespan-cleanup). | The UDS results are focused local evidence on POSIX, not complete UDS compatibility or release evidence. Unix-domain sockets are unavailable on Windows. TLS, HTTP/2, WebSockets, and other UDS-specific behaviors are not established. |
| Use pre-bound TCP listeners | Five live HTTP/1.1 GET comparisons pass against Uvicorn 0.54.0 for IPv4: module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two listeners. Two focused module-CLI comparisons also pass for inherited IPv6 listeners with one and two workers. The two-listener case requires a successful response from each socket and graceful SIGINT exit. A current-source refresh also verifies the startup socket log for inherited IPv4 and IPv6 module-CLI sockets (2/2); see the [focused evidence](maintainers/uvicorn-0.54.0-contract.md#inherited-fd-startup-log-parity-2026-10-28). The IPv6 cases passed on macOS ARM64 / CPython 3.12.13 (run `bc282b37f69a46a38e8353a94197e2a7`, report SHA-256 `f55d9d1f8227452b0513446e2b96241fc63277c1f359ca761fb570a0ea94ca0f`). | The direct Config/Server.run IPv6 loopback bind has one focused local comparison; other IPv6 API paths, Windows, TLS, and HTTP/2 or HTTP/3 over inherited sockets remain unverified. |
| Run multiple Python workers or reload code | Two focused module-CLI comparisons verify two workers serve an HTTP/1.1 request and stop on SIGINT: one sets `--workers 2`, the other sets `WEB_CONCURRENCY=2`. A separate input kills one worker process and verifies replacement. A new POSIX input suspends a worker, uses `--timeout-worker-healthcheck 2`, and passes 1/1 against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13 (run `ae4e43b0e69245a8b22cd67668cdaeba`; report SHA-256 `eae083b94d0d0637b0005fa9278066b48b52f787f93b06c3e58113270a602e1e`). Both implementations log an additional server process, serve the request, and shut down cleanly. A reload input passes locally on macOS ARM64 / CPython 3.12.13 with `--workers 2` in both dependency modes: without `watchfiles`, the candidate's `StatReload` fallback matches the Uvicorn watchfiles oracle; with `watchfiles==1.3.0`, both use watchfiles. Each reload run edits a watched Python module, verifies the replacement response, compares the warning that reload ignores the worker count, and shuts down on SIGINT. | See the [two-crash evidence](maintainers/uvicorn-0.54.0-contract.md#two-consecutive-worker-crashes-and-replacement), [SIGHUP restart evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-worker-restart), and [SIGHUP replacement-startup failure evidence](maintainers/uvicorn-0.54.0-contract.md#sighup-replacement-startup-failure); the restart cases cover one forced exit, two consecutive forced worker exits, one POSIX health-check expiry, a successful SIGHUP restart, and one failed replacement startup that preserves the old workers. Restart/failure policy beyond these paths, worker-count signals beyond the tested SIGTTIN/SIGTTOU pair, Windows and other socket/platform combinations remain unverified. One WatchFilesReload include/exclude case also passes: an excluded-file change did not reload, an included-file change did, and SIGINT exited cleanly. That case ran on macOS ARM64 / CPython 3.12.13; other glob combinations, fallback-watcher filtering, platforms, and reload startup/failure modes remain unverified. See the current-source receipts in the [maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md). Use upstream Uvicorn for those paths. |
| Lifespan and graceful shutdown | Startup, shutdown, application failures, and selected cancellation paths have live cases. Two focused module-CLI comparisons set the timeout through the CLI option and environment; both confirm that a held ASGI request is cancelled after 1 second, matching Uvicorn 0.54.0 on macOS ARM64. `lifespan="off"` passes focused public API and module CLI comparisons against Uvicorn 0.54.0. Focused `Config`/`Server.serve()` and module CLI cases verify that an app exception before startup under `lifespan="on"` leaves the server unstarted and exits with code 3. | Other strict-mode failure classes remain unverified. The worker cases cover successful startup/request/SIGINT, one worker crash/replacement, one two-crash replacement case, and one POSIX health-check expiry/replacement path; worker-control signals and broader process control remain unqualified. |
| Use the native Rust library | The source contains a Python-free `uvicorn-rs` server crate and a separate `asgi-lifespan-protocol-rs` lifecycle crate; HTTP/3 is gated by `uvicorn-rs`'s optional `http3` feature. | Clean release artifacts and downstream consumer checks for the current source remain unverified. See [release status](releases.md) and [native Rust integration](native-fastapi-composition.md). |
| Match Uvicorn's CLI and Python API | Incomplete. CI #486 passed Linux and macOS candidate parity 718/718 each. Windows candidate parity did not complete: 684/689 executed cases passed, with worker shutdown and infrastructure failures plus a TLS oracle error; the Windows consumer lane was skipped. Full settings/runtime, worker/process, Windows and other declared Python versions, and release acceptance remain open. Selected passes do not establish drop-in compatibility. See the [compatibility status](uvicorn-compatibility.md). |

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
