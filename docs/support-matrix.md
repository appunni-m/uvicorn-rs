# ASGI support matrix

The current support evidence is the 490-case matrix: 490/490 attribution
cases and three complete 490/490 repeats pass, with 238 live oracle comparisons
and 252 target-only contracts across 70 input files and 71 operations. Native
coverage is 5,108/5,108 regions and 3,608/3,608 lines, with zero Coverage MCP
gaps. A normal non-instrumented local build passes 238/238 public parity
cases. These are dirty-checkout results, not a release claim. See
[the current source/build receipt](coverage.md#current-full-verification-490-cases).

The project targets the ASGI 3 callable interface and implements a documented
subset of HTTP/WebSocket sub-specification 2.5 and lifespan 2.0. It implements
HTTP/1.1, HTTP/2, and experimental HTTP/3. The [ASGI behavior inventory](asgi-case-inventory.md)
maps declared behaviors to input case IDs and records known deviations and
unsupported extensions.
The historical shared-write inventory declares 448 cases across 70 input files and 61
operations: 213 live oracle-parity cases and 235 target-only contracts. Two of the target-only rows
declare public header-capacity behavior without native injection. **Historical shared-write
regression, native coverage, and normal-build exclusion verification are
complete for the named source/build.** All 448 attribution cases and three
complete 448-case repeats pass with zero failures, infrastructure errors, retries, or cases not run. The
historical report records 4,763/4,763 native LLVM regions and 3,360/3,360 lines
(100%); unfiltered Coverage-MCP has zero gap groups and a matching passing
source receipt. The scope is default-feature `src/lib.rs` with `cfg(coverage)`
on macOS ARM64. The corrected source passes every normal-build exclusion check
and three selected live cases: one HTTP oracle comparison and the two public
capacity support contracts. Its normal build independently passes all 213
public comparisons. That normal build was restored at the time of its audit.
See the [historical source/build and archive](coverage.md#current-full-verification-448-cases).

## Historical evidence

The earlier 447-case source measured 4,734/4,734 regions and 3,333/3,333
lines, passed attribution and three full repeats, and passed its corrected
normal exclusion audit. The subsequent 448-case generic-helper snapshot
measured aggregate 4,758/4,758 regions and 3,358/3,358 lines but retained seven
MCP function observations. Neither snapshot is the current denominator.

The preceding source passed all 447 attribution cases and three complete
447-case repeats with zero failures, infrastructure errors, retries, or cases
not run. Its instrumented report records 4,732/4,732 LLVM regions and 3,332/3,332 lines
(100%) with zero unfiltered Coverage-MCP gap groups, a matching source receipt,
and tests passed. This is default-feature `src/lib.rs` with `cfg(coverage)` on
macOS ARM64. Its first normal-build audit failed because two inactive fault
diagnostic literals remained; the corrected source passed a separate fresh
instrumented gate. The previous exact source/native and failed
normal audit are preserved.

The historical 445-case snapshot measured 4,719/4,719 Rust regions and 3,329/3,329
lines with zero Coverage-MCP gaps and passed all attribution cases. Two full
repeats passed 445/445; the third had 436 passes, one graceful-drain adapter
infrastructure failure, and eight cases not run. The gate remained incomplete
and MCP retained `tests: failed`. The idle-connection shutdown stimulus and
protocol-detection cancellation correction passed a targeted subset. Its
follow-up full run was interrupted after 219 attribution passes for reachable
header-map capacity panics; fallible header handling and public target-capacity
contracts required fresh source verification, supplied by the preceding report.
Fallible header handling passed a new nine-case attribution subset with zero
failures or retries, including both public capacity contracts. Its complete
447-case instrumented gate subsequently passed. The exclusion correction now
passes its normal audit and its separate full instrumented gate.
The preceding 444-case snapshot measured 4,717/4,717 Rust regions and 3,328/3,328
lines with zero Coverage-MCP gaps, but its full gate was incomplete: 443
attribution cases passed and one Uvicorn TLS WebSocket handshake timed out.
All three full repeats passed 444/444 with zero failures. Coverage-MCP retained
`tests: failed`. The listener ownership fix and strengthened plaintext/TLS
shutdown observations passed the preceding full report.
The historical 423-case matrix contained 208 oracle-parity cases and 215
separately labeled target-only fault contracts. All passed attribution and
three full repeats with no mismatches, infrastructure failures, or retries.
Its Coverage-MCP receipt verified 4,356/4,356 Rust regions and 3,060/3,060 lines
(100%) for that default native source/build. The preceding 447-case report independently
measures production panic removal, application ownership changes, and stricter
panic-hook validation; older profiles were not merged into it.
The preceding 426-case report was incomplete: 4,378/4,383 Rust regions and
3,071/3,072 lines were covered, per-case attribution had 425 passes and one
infrastructure failure, and each of three full repeats had 426 behavioral
passes and one infrastructure failure. Its unused-reference cancellation
issue was repaired before the later measurements.
The evidence below combines the declared matrix with clearly dated earlier
probes and benchmarks. Optional diagnostics, Python code, dependencies, other
feature combinations, and other platforms are outside the Rust denominator.
Dirty-working-tree evidence does not establish complete
Uvicorn compatibility or full ASGI conformance. See the [parity contract](parity.md),
[coverage analysis](coverage.md), and [feasibility report](feasibility.md).

## Supported behaviors

| Area | Status and live evidence | Limits |
|---|---|---|
| ASGI callable and Python loop | **Targeted cases pass.** Async apps, a synchronous callable returning an awaitable, execution on the loop that called `Server.serve()`, caller `ContextVar`, and standard event names carried by a `str` subclass are covered by [the HTTP probe](../scripts/probe_http.py) and HTTP/1.1 cases. Both asyncio and uvloop were measured. | Full protocol parity uses CPython 3.12.13. An installed-wheel HTTP/loop/context/lifespan/cancellation smoke also passes on CPython 3.9.25; this is not full Python-version parity. Other event loops and nested context/task combinations are unverified. |
| Context and exceptions | **Targeted cases pass.** Caller context crosses the boundary; an app exception produces HTTP 500 and retains the Python traceback. The exception benchmark checks 200 responses per sample at one in-flight request. | Exception benchmark samples are capped, short fixed-count runs. Exceptions at every ASGI message boundary and under concurrency are not covered. |
| Response completion and background work | **HTTP/1.1 and HTTP/2 live parity cases pass the historical shared-write full matrix.** The final ASGI body completes the response before application return, and the application's finite background work finishes afterward. The adapter transfers the application to a tracked observer when it emits the final frame. A target-only late native task-panic case checks response preservation and error logging. | Throughput and latency effects need a fresh benchmark. |
| HTTP/1.1 | **Implemented and exercised.** The probe checks request scope, upload, response status/body, exceptions, streaming, disconnect, and send-after-disconnect. The configured benchmark list has 12 workloads; the October 4 run measured the 11 available workloads across four configurations and three repetitions (132 rows) because the optional `starlette-rs` route was not installed. The list covers fixed and 1 MiB responses, response chunking, uploads, a slow reader, 32 headers, contextvars, a synchronous callable, and exception handling. | HTTP/1.0 scope and host synthesis have targeted parity cases; broader HTTP/1.0 behavior is unverified. Request-smuggling/security suites, malformed framing, and the complete HTTP edge-case inventory have not been run. |
| HTTP/2 | **Implemented; black-box scope and benchmark cases pass.** TLS ALPN and cleartext h2c prior knowledge report `http_version == "2"`. The 84-row benchmark covers protocol scope, fixed response, 1 MiB response, many response chunks, 1 MiB upload, 64 KiB upload in 1 KiB pieces, and a rate-paced slow reader. A 32-stream synchronized slow-reader parity case also passes four rounds. | h2c upgrade is unverified. Extended CONNECT WebSockets are unsupported. Higher stream counts, packet loss, and broad flow-control stress remain untested. Hypercorn 0.18.0 is the same-protocol performance baseline because Uvicorn does not support HTTP/2. |
| HTTP/3 | **Experimental; the October 4 66-row matrix against Hypercorn and targeted protocol/parity cases passed.** Public cases verify an HTTP/3 response while a partial POST upload remains open, typed H3_NO_ERROR (`0x100`), unknown remote application close codes (zero, reserved GREASE, an unknown code, and maximum u62), and registered HTTP/3-family application codes. Unknown application codes follow the RFC 9114 clean-close behavior; registered codes retain their error path. | Hypercorn 0.18.0 upload cases remain excluded because its upload path failed earlier correctness gates. This comparison is not against Uvicorn, which has no H3 server. H3 uses experimental Rust dependencies. QUIC transport `CONNECTION_CLOSE` behavior is unverified; loss/recovery and broad interoperability remain open. The malformed short `Content-Length` case compares status only; response-body behavior for invalid framing is outside the compatibility claim. WebSockets over HTTP/3 are unsupported. |
| HTTP/3 task ownership | **The current 490-case instrumented full gate passes.** The held-response accept-error contract covers both final-drain spans using actual remote `0x102` application-close termination, incomplete body, ordered cancellation/error diagnostics, application cleanup and a healthy fresh connection. The 128-request one-connection sequence passes all three repeats; instrumented attribution records 128 completed request-body pumps joined. A 16-stream slow-reader case passes three rounds with response fingerprints and resource checks. Clean and registered peer-close cases pass too. | The held-response injection is target-only and is excluded from the normal build. The probe's `stream_reset` is a `recv_data` error convention and does not alone identify a QUIC `RESET_STREAM` frame. Higher stream counts, loss/recovery, and broad interoperability remain unverified. See [current evidence](coverage.md#current-full-verification-490-cases) and [workflow contracts](parity.md#current-http3-workflows). |
| Oracle-parity cases | **238/238 pass the current normal non-instrumented local build and all three complete instrumented repeats.** The synchronous callable/awaitable, caller loop, context, HTTP, WebSocket, lifespan, protocol, concurrent load, and shutdown cases are represented by the declared matrix. H1, WebSockets, and lifecycle use Uvicorn 0.54.0; H2/H3 use Hypercorn 0.18.0 because Uvicorn has no matching server modes. See the [suite contract](parity.md) and [coverage results](coverage.md). | The 252 target-only contracts are not oracle parity; they include public-input support contracts as well as native fault cases. This does not provide the official full ASGI suite, a complete protocol security corpus, or Uvicorn CLI compatibility. The current normal local run is not an installed-wheel release audit. |
| HTTP response header ordering | **Known H1/H2 ASGI deviation captured by interleaved header inputs.** Those adapters record wire order and compare repeated values within each name. The H3 client exposes fields through `http::HeaderMap`, so its iteration order does not establish wire order. | ASGI HTTP 2.5 requires response header order to be preserved. The Rust `HeaderMap` groups different names and loses their cross-name order, so that field is excluded from parity comparison. H1/H2 order is known not to conform; H3 wire order remains unverified. See the [behavior inventory](asgi-case-inventory.md#known-gaps-and-unsupported-surface). |
| HTTP scope and multiplexing | **Targeted cases pass on H1, H2, and H3.** The negotiated protocol version is checked; H2 clients multiplex requests over four TLS connections, and H3 clients multiplex over up to four QUIC connections. New input cases cover ordered duplicate fields on H1, duplicate fields and cookies on H2/H3, encoded path/query bytes, and matching custom `Host`/`:authority` values. | This is a focused scope inventory, not a complete pseudo-header or request-target corpus. H2/H3 combine repeated Cookie fields as `name=value; name=value` for oracle comparison, as allowed by ASGI. The H2/H3 clients and concurrency differ by transport; compare results within each protocol. |
| WebSocket scope | **Plain and TLS HTTP/1.1 cases pass against Uvicorn.** The fixture observes type, ASGI version, scheme, path, raw path, query bytes, headers, client/server, offered subprotocols, state, and disconnect/close details. | The scope matrix does not cover every malformed handshake or optional WebSocket extension. WebSockets over HTTP/2 and HTTP/3 are unsupported. |
| Response header ordering | **Repeated values for each header name retain their input order** on the current H1/H2/H3 live cases. The result retains wire order, while the parity projection compares ordered values grouped by name. | **The server does not preserve the ASGI-required order across different header names.** For interleaved input, `http::HeaderMap` groups values by name before Hyper/H2/H3 serialize them; H1/H2 therefore differ from the live reference. The case does not claim full ASGI response-header ordering. Fixing this requires an ordered representation through each protocol serializer, not only the Python bridge. |
| Request streaming | **Passes the current black-box matrix on H1/H2/H3.** H1 cases verify incremental upload, incomplete-upload disconnect, early-response drain, and malformed final-chunk disconnect. H2 cases verify disconnect after a complete upload reset while a sibling stream remains healthy, as well as partial-upload cancellation. H3 cases verify early response with an open upload, body-stream errors, cancellation and follow-up health. H1/H2/H3 performance workloads consume 1 MiB uploads; H1 and H2 also measure 64 KiB uploads in 1 KiB pieces. | The H3 error-stop contract is target-only; this does not claim full QUIC reset-frame parity or exhaustive disconnect races under load. Request queues are bounded by item count, but no body-size or global byte limit is provided. This acceptance adds no new cap because the fixed workloads do not establish a safe general limit; any cap needs a separate compatibility decision and parity cases. Rust body chunks are copied into Python `bytes` when constructing ASGI events. |
| Response streaming and backpressure | **Passes targeted cases.** The H1 streaming probe checks ordered chunks and that response data arrives before the upload is closed. H1/H2/H3 benchmark cases include large and multi-chunk responses. Maintained H1/H2/H3 slow-reader benchmarks are cumulatively byte-paced at 4 MiB/s per connection; earlier raw timings remain historical. New synchronized H1/H2/H3 load cases compare body lengths and SHA-256 fingerprints while concurrent slow readers run, and require zero active app tasks and healthy follow-up requests. Immutable Python `bytes` response chunks are extracted as owner-backed Rust `Bytes`, avoiding a payload copy at that boundary. | The load cases are fixed concurrency and do not establish throughput or latency gains. The separate historical H1 streaming probe uses a 1 ms delay per read event; that probe is not the maintained byte-paced benchmark. Each chunk still crosses the Python ASGI boundary. |
| WebSockets | **HTTP/1.1 Upgrade implemented.** The live probe covers valid and malformed handshake keys/versions, subprotocol, text/binary echo, pre-accept denial, disconnect, and shutdown cancellation. The 36-row benchmark covers fresh handshakes, 32-byte text echo, and 64 KiB binary echo. A new 16-session echo load case compares message fingerprints across four slow-reader rounds and checks follow-up health and resource stability. | The handshake benchmark is a fixed 500 handshakes per sample at concurrency 1 to keep client ephemeral-port use bounded. The load case is not a throughput benchmark. Fragmentation, compression/extensions, malformed data frames, and extended CONNECT are untested or unsupported. |
| Lifespan and shutdown | **The current 490-case matrix covers lifecycle and bounded load behavior.** Existing cases cover startup state, shallow state copies without rehashing, idle SIGTERM, held-request cancellation, idle keep-alive close, active response-stream drain, client reset during active-stream shutdown, and owning-loop snapshots of post-response and eager-task cleanup. Synchronized contracts cover canceled pump reaping, graceful pump completion, forced abort after the grace deadline, and completed/error JoinSet outcomes. A zero-grace HTTP/1.1 case cancels 16 held ASGI responses, observes no completed responses, completes lifespan shutdown, and requires bounded process exit. | Body pumps are server-owned and joined within the remaining transport grace period; on expiry they are aborted and drained before `Server.serve()` returns. Request/lifespan cleanup use separate bounded stages, so total shutdown can exceed one configured grace interval; lifespan shutdown and cancellation cleanup retain a 100 ms minimum window even when the configured grace is zero. Python cleanup can remain unfinished after a window expires. Broad startup races and concurrent shutdown stress on H2/H3/WebSockets remain unverified. Five repetitions per server were measured in earlier lifecycle benchmarks. |
| Disconnect and cancellation | **Targeted cases pass.** H1 disconnect receives and send-after-disconnect behavior, H2 response-stream reset cancellation, H3 client abort, and cleartext/TLS shutdown are checked. The new zero-grace lifecycle case resets 16 active HTTP/1.1 response clients and observes cancellation of all 16 ASGI tasks. Target-only cases cover repeated receives after H2 connection EOF and failures scheduling Python cancellation, with bounded shutdown and logged errors. | This does not cover every cancellation race under load or identical interrupted-transfer cases across each protocol. |
| CLI and deployment | **An installed macOS ARM64 wheel passed the module:app CLI path, TLS HTTP/1.1 over TLS 1.3 with ALPN, and SIGTERM during a held request.** The request was cancelled, lifespan shutdown completed, and the process exited within the probe's 5 s bound. The [hosted Linux CI run](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036) also passed module:app startup and the transient systemd manager-stop probe on the exact installed wheel, including request cancellation, lifespan shutdown, and exit within 10 s. | The systemd result covers one transient service on Ubuntu 24.04; the persistent example unit, launchd, containers, and Windows service-manager behavior are unverified. No reload/watch, worker/process supervision, proxy headers, Uvicorn config files, Unix sockets, or general Uvicorn CLI compatibility. No package is published. See [deployment](deployment.md). |
| TLS and listeners | **Live TLS/ALPN cases pass the historical shared-write full matrix.** TCP negotiates H2 or HTTP/1.1; QUIC negotiates H3. HTTPS/HTTP3 use the configured port. Listener admission-close and typed protocol-detection cancellation pass the strengthened plaintext/TLS pair: admission closes, the partial-preface idle connection closes, and the active response drains. | Client certificate authentication, trusted proxy handling, configurable ALPN, and QUIC tuning are not provided. |
| Response and handshake header capacity | **Finite compiled capacity; both public contracts pass the historical shared-write selected normal-build audit.** They also passed the preceding full instrumented matrix. HTTP response and WebSocket acceptance maps inherit the pinned `http` crate's capacity. Valid large ASGI header collections can exceed it; fallible `try_append` preserves response state and task ownership. Same-input public cases return the small HTTP 500 or rejected WebSocket handshake, complete cleanup, and serve healthy follow-ups. | No configurable header-capacity option or stable accepted-header count is promised. Target-only capacity contracts are not Uvicorn parity and do not activate native injection controls. |
| Packaging and platform | **An installed macOS ARM64 abi3 wheel passed the package-consumer HTTP/loop/context/lifespan/cancellation checks and the CLI/TLS/held-request SIGTERM probe on CPython 3.12.13.** Earlier evidence also covers CPython 3.9.25 and a locked source-archive rebuild. The hosted [CI run](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036) on commit `9d05c72` passed the Linux x86-64 wheel, framework, systemd, full public parity, and normal fault-seam exclusion checks; the Rust 1.85.0 MSRV, lint, feature-build, and rustdoc jobs also passed. | Hosted package/deployment evidence covers the Ubuntu 24.04 runner only. The same run's unified coverage job failed and dependent package candidate jobs were skipped, so it did not produce a complete hosted release bundle. Python 3.9 has package-consumer smoke evidence, not full protocol parity. The POSIX CLI/TLS/signal probe is not run on Windows. See the [release candidate workflow](releases.md). |
| Starlette frameworks | **The same shared app passed Uvicorn 0.54.0 vs the installed uvicorn-rs wheel on upstream Starlette 1.6.0 and on starlette-rs-py 0.1.0 from commit 738c43362938896c268ca29b9a9a2a5942df510c.** The macOS receipts and hosted Linux [CI run](https://github.com/appunni-m/uvicorn-rs/actions/runs/37566368036) passed observations for lifespan state, streamed request body, three distinct response chunks, background work, HTTP 500, WebSocket handshake/subprotocol/echo, and lifespan shutdown. The server wheel has no runtime requirements and contains no framework package. See the [evidence index](../benchmarks/results/framework-integration-2026-10-07/evidence-index.json). | Selected app-level integration cases do not establish full Starlette or ASGI conformance. The pinned starlette-rs revision does not expose WebSocketRoute; its WebSocket case uses a plain ASGI branch to test the server transport, not framework-level WebSocket routing. The frameworks require separate environments because both own the starlette import namespace. On the recorded macOS run, Uvicorn completed lifespan cleanup and then re-raised SIGTERM (exit -15); uvicorn-rs exited 0. Process exit-code parity is not claimed. |
| Full ASGI conformance | **Not run.** The live probes below are focused black-box cases. | Passing these cases is not a claim that every ASGI 3, HTTP/WebSocket 2.5, or lifespan 2.0 requirement is covered. |
| Rust source coverage | **The local instrumented build measured 5,108/5,108 native LLVM regions and 3,608/3,608 lines (100%).** All 490 attribution cases and three complete repeats pass, with zero unfiltered Coverage-MCP gaps and matching source/build evidence. The normal non-instrumented local build passes all 238 public comparisons. See [coverage analysis](coverage.md). | This is macOS ARM64 dirty-working-tree evidence for default-feature `src/lib.rs` with `cfg(coverage)`. The earlier installed-wheel exclusion audit applies to an older source snapshot, not this one. Hosted Linux coverage failed in CI run 37566368036 with exit code 1; its artifact is recorded, but the failure detail is not in the public summary. Optional diagnostics, Python code, dependencies, other features/platforms, full official ASGI conformance, and performance are outside the claim. A clean committed measurement is needed for a release baseline. |
| Performance | **The October 4 correctness-gated matrix covers H1, H2, H3, WebSockets, and lifecycle.** Raw rows include throughput, p50/p95/p99 latency, server/client CPU, and sampled RSS. | Performance is provisional because the run overlapped unrelated CPU-heavy jobs. H1 was mixed: fixed and Python-heavy workloads lagged Uvicorn, while some chunk-heavy rates were higher at greater CPU use. H2/H3 compare with Hypercorn, not Uvicorn. The [October 5 investigation](performance-investigation-2026-10-05.md) reports a 1.59× handshake result over three matched, fixed 500-operation samples on its frozen build. The exact October 6 source has not been benchmarked. Other workloads lack valid paired comparisons; H3 baseline correctness failures prevent a speed ratio. See [the feasibility report](feasibility.md) for historical measurements. |

## Live black-box probes

```sh
uv sync --python 3.12 --group benchmark --reinstall-package uvicorn-rs
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
```

Run the paired upstream Starlette and starlette-rs probes in separate
environments with an installed candidate wheel, as described in
[deployment and framework integration](deployment.md#test-starlette-integrations).

The historical merged category summary is in [category-summary-2026-10-02.json](../benchmarks/results/category-summary-2026-10-02.json); the October 4 historical separate per-category raw outputs are in [full-2026-10-04T113122Z](../benchmarks/results/full-2026-10-04T113122Z/). Rebuild the older merged H2 and summary artifacts with `uv run python scripts/assemble_category_results.py`. See [ADR 0001](adr/0001-runtime-and-asyncio-bridge.md) for the runtime decision, [the architecture page](architecture.md) for buffer ownership, and [the feasibility report](feasibility.md) for current performance results and their limits.

For a fresh, non-overwriting run of all five benchmark categories, including the
HTTP/2 and HTTP/3 matrices, use the [reproducible benchmark guide](benchmarks.md).
