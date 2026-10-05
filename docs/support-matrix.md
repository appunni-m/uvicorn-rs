# ASGI support matrix

The HTTP/3 task-reaping source passes all 451 instrumented attribution cases
and three complete repeats with zero failures, infrastructure errors, retries
or cases not run. The matrix has 214 oracle comparisons and 237 target-only
contracts across 70 input files and 63 operations. Native coverage is
4,778/4,778 regions and 3,371/3,371 lines with zero unfiltered MCP gaps.
The restored normal build passes 214/214 public comparisons and all 15
exclusion checks with three selected live cases. See
[the current source/build receipt](coverage.md#current-full-verification-451-cases).
Passing 448-case results below belong to the earlier shared-write source
identified in [the coverage record](coverage.md#current-full-verification-448-cases);
they do not attest the changed checkout.

The target is the ASGI 3 callable contract, HTTP/WebSocket sub-spec 2.5, and
lifespan 2.0. The server implements HTTP/1.1, HTTP/2, and experimental HTTP/3.
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
| HTTP/2 | **Implemented; black-box scope and benchmark cases pass.** TLS ALPN and cleartext h2c prior knowledge report `http_version == "2"`. The 84-row benchmark covers protocol scope, fixed response, 1 MiB response, many response chunks, 1 MiB upload, 64 KiB upload in 1 KiB pieces, and a rate-paced slow reader. | h2c upgrade is unverified. Extended CONNECT WebSockets are unsupported. Large-scale stream-count, packet-loss, and flow-control stress cases are not covered. Hypercorn 0.18.0 is the same-protocol performance baseline because Uvicorn does not support HTTP/2. |
| HTTP/3 | **Experimental; the October 4 66-row matrix against Hypercorn and targeted protocol/parity cases passed.** The parity suite also verifies an HTTP/3 response while a partial POST upload remains open, and exact typed H3_NO_ERROR (`0x100`) peer close followed by a fresh request and graceful owned-process exit. Other application/transport errors retain their error paths. | Hypercorn 0.18.0 upload cases remain excluded because its upload path failed earlier correctness gates. This comparison is not against Uvicorn, which has no H3 server. H3 uses experimental Rust dependencies. Loss/recovery and broad interoperability remain open. Unknown HTTP/3 application close codes are currently logged as errors instead of treated as `H3_NO_ERROR`; see the [known compatibility gap](implementation-review.md#code-and-operations). The malformed short `Content-Length` case compares status only; response-body behavior for invalid framing is outside the compatibility claim. WebSockets over HTTP/3 are unsupported. |
| HTTP/3 task ownership | **The 451-case instrumented full gate passes.** The held-response accept-error contract solely covers both final-drain spans using actual remote `0x102` connection-error termination, incomplete body, ordered cancellation/error diagnostics, application cleanup and a healthy fresh connection. The GREASE-off 128-response sequence and clean peer-close case pass full attribution, all three repeats and current normal-build public parity. | The held-response injection is instrumented and target-only; it is excluded from the restored normal build. The probe's `stream_reset` is a `recv_data` error convention and does not alone identify a QUIC `RESET_STREAM` frame. Broad cancellation/load stress remains unverified. See [current evidence](coverage.md#current-evidence-status) and [workflow contracts](parity.md#current-http3-workflows). |
| Oracle-parity cases | **214/214 pass the restored normal build, current instrumented attribution and all three complete repeats.** The synchronous callable/awaitable, caller loop, context, HTTP, WebSocket, lifespan, and protocol cases are represented by the declared matrix. H1, WebSockets, and lifecycle use Uvicorn 0.54.0; H2/H3 use Hypercorn 0.18.0 because Uvicorn has no matching server modes. See the [suite contract](parity.md) and [coverage results](coverage.md). | The 237 target-only contracts are not parity; two are public capacity support contracts without native injection. This does not provide the official full ASGI suite, a complete protocol security corpus, or Uvicorn CLI compatibility. |
| HTTP scope and multiplexing | **Targeted cases pass on H1, H2, and H3.** The negotiated protocol version is checked; H2 clients multiplex requests over four TLS connections, and H3 clients multiplex over up to four QUIC connections. Each request maps to a separate ASGI invocation. | Complete duplicate-header, pseudo-header, authority, raw-URI, and request-target case inventories have not been run. The H2/H3 clients and concurrency differ by transport; compare results within each protocol. |
| Request streaming | **Passes targeted cases.** The H1 probe confirms the app receives upload chunks incrementally and observes `http.disconnect` on an incomplete upload. An H3 parity case confirms a response completes while a partial POST remains unfinished. H1/H2/H3 performance workloads consume 1 MiB uploads; H1 and H2 also measure 64 KiB uploads in 1 KiB pieces. | The incomplete-upload disconnect race was directly probed on H1 only; the H3 case tests early response/abandoned upload behavior, not an H3 `http.disconnect` assertion. Body-size limits are not provided. Rust body chunks are copied into Python `bytes` when constructing ASGI events. |
| Response streaming and backpressure | **Passes targeted cases.** The H1 streaming probe checks ordered chunks and that response data arrives before the upload is closed. H1/H2/H3 benchmark cases include large and multi-chunk responses. Maintained H1/H2/H3 slow-reader benchmarks are cumulatively byte-paced at 4 MiB/s per connection; earlier raw timings remain historical. Immutable Python `bytes` response chunks are extracted as owner-backed Rust `Bytes`, avoiding a payload copy at that boundary. | The separate historical H1 streaming probe uses a 1 ms delay per read event; that probe is not the maintained byte-paced benchmark. Each chunk still crosses the Python ASGI boundary; streaming performance on the current normal build still requires valid repeated comparisons. |
| WebSockets | **HTTP/1.1 Upgrade implemented.** The live probe covers valid and malformed handshake keys/versions, subprotocol, text/binary echo, pre-accept denial, disconnect, and shutdown cancellation. The 36-row benchmark covers fresh handshakes, 32-byte text echo, and 64 KiB binary echo. | The handshake benchmark is a fixed 500 handshakes per sample at concurrency 1 to keep client ephemeral-port use bounded. Fragmentation, compression/extensions, malformed data frames, and extended CONNECT are untested or unsupported. |
| Lifespan and shutdown | **The historical shared-write full matrix passes.** Cases cover startup state, shallow state copies without rehashing, idle SIGTERM, held-request cancellation, idle keep-alive close, active response-stream drain, client reset during active-stream shutdown, and owning-loop snapshots of post-response and eager-task cleanup. Plaintext/TLS cases prove listener closure before held-response release and idle partial-preface connection closure while the active response drains. Both listener cases exposed the earlier retained-admission defect; the source drops the listener before task drains. | Request and lifespan cleanup use separate trackers and bounded stages; Python cleanup can remain unfinished after a window expires. Detached request-body pump completion is not separately acknowledged at shutdown. Broad startup races, high-load shutdown, and zero-timeout stage behavior remain unverified. Five repetitions per server were measured in earlier lifecycle benchmarks. |
| Disconnect and cancellation | **Targeted cases pass.** H1 disconnect receives and send-after-disconnect behavior, H2 response-stream reset cancellation, H3 client abort, and cleartext/TLS shutdown are checked. Target-only cases cover repeated receives after H2 connection EOF and failures scheduling Python cancellation, with bounded shutdown and logged errors. | Broad cancellation races under load and identical interrupted-transfer cases across every protocol remain unverified. |
| CLI and deployment | **Documented subset implemented:** `module:app`, host, port, asyncio/uvloop, TLS files, graceful timeout, SIGINT, and SIGTERM. | No reload/watch, worker/process supervision, proxy headers, Uvicorn config files, Unix sockets, or general Uvicorn CLI compatibility. No package is published. |
| TLS and listeners | **Live TLS/ALPN cases pass the historical shared-write full matrix.** TCP negotiates H2 or HTTP/1.1; QUIC negotiates H3. HTTPS/HTTP3 use the configured port. Listener admission-close and typed protocol-detection cancellation pass the strengthened plaintext/TLS pair: admission closes, the partial-preface idle connection closes, and the active response drains. | Client certificate authentication, trusted proxy handling, configurable ALPN, and QUIC tuning are not provided. |
| Response and handshake header capacity | **Finite compiled capacity; both public contracts pass the historical shared-write selected normal-build audit.** They also passed the preceding full instrumented matrix. HTTP response and WebSocket acceptance maps inherit the pinned `http` crate's capacity. Valid large ASGI header collections can exceed it; fallible `try_append` preserves response state and task ownership. Same-input public cases return the small HTTP 500 or rejected WebSocket handshake, complete cleanup, and serve healthy follow-ups. | No configurable header-capacity option or stable accepted-header count is promised. Target-only capacity contracts are not Uvicorn parity and do not activate native injection controls. |
| Packaging and platform | **A real macOS ARM64 abi3 wheel passes fresh installed-package HTTP, loop/thread/context, lifespan and cancellation checks on CPython 3.12.13 and 3.9.25. The extracted source archive rebuilds with locked dependencies and passes the same consumer check. Rust 1.85.0 default and all-feature library builds pass locally. CI configures Linux x86-64, macOS ARM64 and Windows x86-64 wheels, plus a Linux source archive and exact-wheel full public parity.** | These are dirty-checkout preparation checks. The new hosted matrix has not passed for a pushed commit. Python 3.9 has package-consumer smoke evidence, not full protocol parity. No public package or service-manager deployment validation exists. See the [release candidate workflow](releases.md). |
| `starlette-rs` | **Optional integration passes.** One route from the separately installed framework works through the standard ASGI interface and is included in the HTTP/1.1 benchmark. | The server does not depend on, import, bundle, or install `starlette-rs`. One route is not framework-wide coverage. |
| Full ASGI conformance | **Not run.** The live probes below are focused black-box cases. | Passing these cases is not a claim that every ASGI 3, HTTP/WebSocket 2.5, or lifespan 2.0 requirement is covered. |
| Rust source coverage | **The current instrumented build measured 4,778/4,778 native LLVM regions and 3,371/3,371 lines (100%).** All 451 attribution cases and three complete repeats pass, with zero unfiltered Coverage-MCP gaps and matching source/build evidence. The restored normal build passes all 15 exclusion checks and three selected live cases. See [coverage analysis](coverage.md). | macOS ARM64 dirty-working-tree evidence for default-feature `src/lib.rs` with `cfg(coverage)`. Optional diagnostics, Python code, dependencies, other features/platforms, full official ASGI conformance, and performance are outside the claim. A clean committed measurement is needed for a release baseline. |
| Performance | **The October 4 correctness-gated matrix covers H1, H2, H3, WebSockets, and lifecycle.** Raw rows include throughput, p50/p95/p99 latency, server/client CPU, and sampled RSS. | Performance is provisional because the run overlapped unrelated CPU-heavy jobs. H1 was mixed: fixed and Python-heavy workloads lagged Uvicorn, while some chunk-heavy rates were higher at greater CPU use. H2/H3 compare with Hypercorn, not Uvicorn. The [October 5 investigation](performance-investigation-2026-10-05.md) qualifies a 1.59× handshake gain over three matched, fixed 500-operation samples. Other current workloads lack valid paired comparisons; H3 baseline correctness failures prevent a speed ratio. See [the feasibility report](feasibility.md) for historical measurements. |

## Live black-box probes

```sh
uv sync --python 3.12 --group benchmark --reinstall-package uvicorn-rs
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
uv run python scripts/probe_starlette_rs.py  # requires a separate starlette-rs install
```

The historical merged category summary is in [category-summary-2026-10-02.json](../benchmarks/results/category-summary-2026-10-02.json); the October 4 historical separate per-category raw outputs are in [full-2026-10-04T113122Z](../benchmarks/results/full-2026-10-04T113122Z/). Rebuild the older merged H2 and summary artifacts with `uv run python scripts/assemble_category_results.py`. See [ADR 0001](adr/0001-runtime-and-asyncio-bridge.md) for the runtime decision, [the architecture page](architecture.md) for buffer ownership, and [the feasibility report](feasibility.md) for current performance results and their limits.

For a fresh, non-overwriting run of all five benchmark categories, including the
HTTP/2 and HTTP/3 matrices, use the [reproducible benchmark guide](benchmarks.md).
