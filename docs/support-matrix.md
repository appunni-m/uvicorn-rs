# ASGI and protocol support

This page summarizes the maintained Uvicorn 0.54.0 compatibility contract.
The official ASGI conformance suite has not been run, and the evidence does
not extend to other Uvicorn versions.

The Python distribution is `uvicorn-rs`, providing `uvicorn` imports and
command. `uvicorn-rs-py` is the optional internal Cargo/PyO3 adapter. The Cargo
release targets are the Python-free `uvicorn-rs` server crate with optional
`http3`, and `asgi-lifespan-protocol-rs`. The publisher is `release.yml`.

<a id="current-verification-status-2026-11-02"></a>
<a id="current-verification-status-2026-11-04"></a>
<a id="current-verification-status-2026-11-05"></a>
<a id="current-verification-status-2026-11-06"></a>
<a id="current-verification-status-2026-11-07"></a>

## Current verification status (2026-11-07)

PR [#24](https://github.com/appunni-m/uvicorn-rs/pull/24) merged to `main` as
`242f05096181ee1b84aac116bea613c1a6dad76f`. PR-head CI
[#719](https://github.com/appunni-m/uvicorn-rs/actions/runs/42348498407)
passed installed-wheel Uvicorn 0.54.0 parity on Linux x86-64 (786/786), macOS
ARM64 (786/786), and Windows x86-64 (759/759 applicable cases; 27 POSIX-only
cases are inapplicable). The 16 indexed custom HTTP/WebSocket protocol,
`ssl_context_factory`, ALPN, and response-capacity cases pass on all three.
Candidate packages and clean consumers passed on all three systems and the
CPython 3.9 floor.

The same CI run passed all 1,453 unified cases through three ASGI and three
native repeats, with complete attribution and zero failures or infrastructure
retries. Raw coverage is 15,061/15,061 regions and 11,075/11,075 lines; artifact
[13567108849](https://github.com/appunni-m/uvicorn-rs/actions/runs/42348498407/artifacts/13567108849)
has SHA-256 `4a670ab7794c50c3104ca9415fc6664f0ec7b7080dc47086864c09949aa8c856`.
Coverage-MCP reviewed the full report with 45/45 region pages (899 groups),
the full line result, zero gaps, matching source receipt, and passed test
status. The maintainer waived independent Coverage-MCP review as a release
gate; exact-source 100% raw coverage remains mandatory. Main CI #720 and the
three-system benchmark #366 were dispatched on `242f050`; docs build #314 passed.

The complete matched benchmark [#364](https://github.com/appunni-m/uvicorn-rs/actions/runs/42325915265)
has 68/69/68 qualified category pairs on Linux x86-64, Linux ARM64, and macOS
ARM64. FastAPI HTTP/1 validated-route throughput is slower than Uvicorn on all
six system/loop pairs, and WebSocket text echo is slower; H2/H3 results vary by
workload. No broad FastAPI speedup is supported. The ARM64 Hypercorn HTTP/3
slow-reader reference failure has candidate-only passing evidence and no
comparative ratio. Focused upload trace [#365](https://github.com/appunni-m/uvicorn-rs/actions/runs/42340595289)
did not reproduce the historical HTTP/1 timeout and did not establish its
cause.

Run #364 is bound to earlier source `e8b5d6b`; exact-main benchmark #366 was
dispatched for `242f050`. The package scope remains
the Python-free Cargo `uvicorn-rs` crate with optional `http3`,
`asgi-lifespan-protocol-rs`, and PyPI `uvicorn-rs` exposing the `uvicorn`
namespace and command. Exact-main CI, benchmark, candidate artifacts, and
consumers must pass before publication.

### Historical status (2026-11-05)

PR [#23](https://github.com/appunni-m/uvicorn-rs/pull/23) has newer hosted
evidence than the exact-main baseline below. CI
[#689](https://github.com/appunni-m/uvicorn-rs/actions/runs/42061360886) passed
Linux installed-wheel parity (786/786), Windows parity (759/759, with 27
declared POSIX-inapplicable cases), and their candidate consumers. macOS ARM64
parity was 785/786. In the sole failed TLS-over-Unix-domain-socket case, both
servers returned HTTP 200 and exited cleanly, but the candidate logged an extra
Hyper NotConnected error during TLS shutdown; no macOS candidate archive was
produced.

A focused follow-up treats this post-response NotConnected error as a peer
disconnect, and its selected case passed locally after rebuilding the native
extension. Hosted confirmation remains required. The full coverage job in #689
was still running against the earlier PR head when this status was recorded;
it does not qualify the follow-up source. The preceding #688 report completed
all 1,453 cases through three repeats with zero failures or infrastructure
retries, but measured 15,056/15,057 regions and 11,078/11,078 lines. The one
uncovered region was an unreachable optional request-body timer state, removed
by the invariant change on the #689 head.

That historical snapshot records an earlier review-gate discussion. The
maintainer's current decision waives a separate Coverage-MCP review; exact-source
100% raw coverage and the final-source three-system benchmark remain required.
No 0.3.0 package has been published.

## Last complete exact-main release baseline (2026-11-04)

The last complete exact-main [CI #661](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594662)
binds to clean commit `feb955d2758166ad8c4b519903fd1318b29e7d2d`. The
installed-wheel public parity matrix, Linux x86-64/macOS ARM64/Windows x86-64
candidate package consumers, Python 3.9 floor consumer, and native
FastAPI-RS → Starlette-RS → Uvicorn-RS composition passed. Unified coverage
passed all 1,453 cases with three ASGI and three native repeats: 14,965/14,965
regions and 10,984/10,984 lines.

| Profile | Result | Scope |
| --- | --- | --- |
| Linux x86-64 / CPython 3.12.13 | Passed | Exact-main installed-wheel parity and clean candidate consumer |
| macOS ARM64 / CPython 3.12.13 | Passed | Exact-main installed-wheel parity and clean candidate consumer |
| Windows x86-64 / CPython 3.12.13 | Passed | Exact-main reference-defect acceptance, candidate package and clean consumer |
| Linux x86-64 / CPython 3.9.25 | Passed | Exact abi3 wheel consumer; not the full versioned parity matrix |

Windows has 27 declared platform-inapplicable inputs. The
[reference exception](uvicorn-compatibility.md#windows-reference-hang-acceptance)
preserves raw failed parity and requires clean candidate behavior; other
failures remain failures. All 16 custom protocol, TLS-context-factory and
response-capacity inputs pass on all three tested systems.

The exact-main benchmark [#283](https://github.com/appunni-m/uvicorn-rs/actions/runs/41802594681)
completed on Linux x86-64, Linux ARM64 and macOS ARM64. HTTP/1 FastAPI
validated-route throughput is lower on all six system/loop pairs; H2/H3 gains
are workload-specific, and WebSocket text-echo is slower. No general FastAPI
performance advantage is claimed. The 0.3.0 PyPI distribution remains
unpublished, and compatibility acceptance and exact-tag candidate assembly
remain open. These receipts cover their recorded source and test inputs, not
arbitrary applications.

## Can I replace Uvicorn?

Use the [quickstart](quickstart.md) and
[application evaluation guide](fastapi-evaluation.md) after release acceptance.
Keep upstream Uvicorn in a separate environment for comparison and rollback.
The rows below describe the tested behavior and the limits of individual
inputs. Historical local receipts remain historical; the clean hosted matrix
above is the latest platform evidence for included cases.

## Supported behaviors

The installed-wheel matrices above execute every platform-applicable input in
`tests/parity/manifest.json`. The table groups that tested public surface;
[the versioned contract](maintainers/uvicorn-0.54.0-contract.md) retains the
individual case IDs, input limits and historical investigation receipts.
A passing case covers its recorded settings and requests, rather than every
possible application or configuration combination.

| Surface | Maintained behavior and evidence scope |
| --- | --- |
| CLI, settings and environment | Module and console commands; help/version; argument validation; environment and explicit-option precedence; application import and factory loading; logging and exit diagnostics. |
| Python API | `Config`, `Server`, `uvicorn.run()`, caller-owned event loops, custom loop factories, startup/shutdown, cancellation and application import paths. |
| Custom protocols and TLS factories | Custom HTTP/WebSocket protocol classes, ASGI2 scope handling, TLS context factories on custom/native HTTP and WebSockets, and HTTP/2 ALPN. All named hook/capacity inputs pass on Linux, macOS and Windows. |
| ASGI applications | ASGI3 functions and callable instances, explicit and detected factories, ASGI2 adaptation, lifespan state and application errors. Python application code executes on its Python event loop. |
| WSGI adaptation | Explicit WSGI mode, factories, buffered and chunked request bodies, response streaming, and application-error behavior. The adapter executes the WSGI callable in Python. |
| HTTP/1.1 | Request targets, headers, content lengths/chunking, uploads, response streaming, keep-alive, limits, disconnect/reset and graceful drain inputs. |
| HTTP/2 | TLS ALPN and cleartext prior knowledge, concurrent streams, request/response bodies, headers/trailers, cancellation and error inputs. The Uvicorn 0.54.0 oracle selects its `zttp` backend and HTTP/2 option. |
| HTTP/3 | Optional native `http3` feature; live requests, streaming, trailers, cancellation and shutdown inputs. Uvicorn has no HTTP/3 reference; the matrix uses its declared protocol/specification and Hypercorn contracts. Comparative timing remains a separate gate. |
| TLS | Certificate/key loading and diagnostics, encrypted key inputs, selected protocol/cipher/client-certificate settings, context factories and ALPN. TLS variants are bounded by the individual recorded inputs. |
| WebSockets | Upgrade/handshake, text/binary and fragmented messages, compression, configured message limits, ping/pong/timeouts, disconnect and application/lifespan state. Selectors include auto, SansIO, wsproto and legacy websockets. WebSockets over HTTP/2 or HTTP/3 are outside the supported transport surface. |
| WebSocket receive queue | `ws_max_queue` bounds pending complete messages for the legacy `websockets` selector. Pinned Uvicorn uses `websockets.legacy`, whose queue also contains complete messages. Auto/SansIO and wsproto follow their upstream setting behavior. The delayed-reader case verifies delivery with queue size one; it does not measure flow-control timing. |
| Response headers and trailers | Default/custom fields, repeated values, validated header order, malformed starts and large header/trailer sets. The capacity inputs include HTTP/1 and HTTP/2 values above the native map boundary plus WebSocket acceptance headers. |
| Root paths and proxies | Configured root paths, original request bytes, trusted/disabled proxy handling, forwarded schemes/client addresses and malformed forwarding inputs. The standards-based `raw_path` difference is described below. |
| Workers and reload | Multiple workers, normal shutdown, intentional worker crashes/replacement, reload backends and filters, applicable worker signals and health checks. The two stock Windows defects require separate candidate correctness acceptance. |
| Listener integration | TCP, multiple/pre-bound/inherited listeners and applicable Unix-domain sockets, including their indexed TLS, lifecycle and transfer cases. Windows excludes the 27 explicitly listed POSIX-specific inputs. |
| Lifespan and shutdown | Startup/shutdown completion and failures, disabled/automatic/strict lifespan modes, in-flight request draining, deadlines and cancellation. A process-manager or application trial remains application specific. |
| Native Rust API | Python-free `uvicorn-rs`, optional `http3`, and separate `asgi-lifespan-protocol-rs`; Linux candidate consumers exercise default and HTTP/3 features. No Python framework is a dependency of the server crate. |

The Rust transport uses one Tokio worker thread for the Python adapter.
[FastAPI evaluation](fastapi-evaluation.md) describes matched settings and
rollback for the maintainer's own application trial after release acceptance.

## Known behavior limits

- The current HTTP/2 and HTTP/3 inputs are included in the complete platform
  matrices above. Their exact-main performance measurements are complete, but
  protocol-specific gains do not establish a broad FastAPI speed advantage.
  Earlier HTTP/2 receipts using Hypercorn are historical.
- The adapter preserves the original path bytes in `raw_path`, including
  when `root_path` is configured. Uvicorn 0.54.0 adds the configured root path
  there. The candidate follows the [ASGI HTTP/WebSocket scope contract](https://asgi.readthedocs.io/en/stable/specs/www.html#http-connection-scope),
  which defines this field from the unmodified incoming path, excluding the
  query. This is a documented specification-based difference, with dedicated
  public inputs.
- Header-order cases compare the full response sequence for the indexed
  HTTP/1 and HTTP/2 inputs. Other cases use their declared comparison policy;
  HTTP/3 raw wire order is not established by a probe that observes only a
  `HeaderMap`. See the [case inventory](asgi-case-inventory.md#known-gaps-and-unsupported-surface).
- The complete official ASGI conformance suite has not been run.
- The latest matched Python FastAPI results do not establish a general speed
  advantage over Uvicorn. See [benchmark results](benchmark-results.md) and
  [current benchmark status](benchmark-status.md).
- Detailed case IDs, source identities, historical receipts, and coverage
  accounting are kept in the [maintainer evidence record](maintainers/asgi-support-evidence.md).

## Try the current prototype

Follow the [quickstart](quickstart.md) to run the checked-out example. The
[configuration guide](configuration.md) lists the prototype's current options.
