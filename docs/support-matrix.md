# ASGI and protocol support

This page summarizes the maintained Uvicorn 0.54.0 compatibility contract.
The official ASGI conformance suite has not been run, and the evidence does
not extend to other Uvicorn versions.

The Python distribution is `uvicorn-rs`, providing `uvicorn` imports and
command. `uvicorn-rs-py` is the optional internal Cargo/PyO3 adapter. The Cargo
release targets are the Python-free `uvicorn-rs` server crate with optional
`http3`, and `asgi-lifespan-protocol-rs`. The publisher is `release.yml`.

<a id="current-verification-status-2026-11-02"></a>

## Current verification status (2026-11-03)

The latest [CI #637 receipts](uvicorn-compatibility.md#current-status-2026-11-03)
bind to clean merge source `00f38c82dd869ba0dcc7068cbc5cc769cd0f6294`,
testing PR head `b9ed5c693`. Focused Windows CI #638 tests
`68c063f623852bcfd0dfe937fe2a6eca189aeb65` with the same runtime-source digest.

| Profile | Result | Scope |
| --- | --- | --- |
| Linux x86-64 / CPython 3.12.13 | 786/786 raw parity passed | Installed normal wheel against Uvicorn 0.54.0 |
| macOS ARM64 / CPython 3.12.13 | 786/786 raw parity passed | Installed normal wheel and clean package consumer pass |
| Windows x86-64 / CPython 3.12.13 | 758/759 raw parity passed | Captured stock-reference startup defect; separate local acceptance. Focused CI #638 qualifies both reference-defect policies and passes all three candidate lifecycle contracts |
| Linux x86-64 / CPython 3.9.25 | Clean consumer passed | Exact abi3 wheel; not the full versioned parity matrix |

Windows has 27 declared platform-inapplicable inputs. The
[reference exception](uvicorn-compatibility.md#windows-reference-hang-acceptance)
preserves raw failed parity and requires clean candidate behavior; other
failures remain failures. All 16 custom protocol, TLS-context-factory and
response-capacity inputs pass on all three tested systems.

Linux and macOS artifact/consumer jobs and the Python 3.9 floor consumer pass.
Full Windows package qualification, strict coverage acceptance, final-main
review handoff, final-source qualification and matched FastAPI benchmarks
remain open. The 0.3.0 PyPI distribution is unpublished. Later source changes
require qualification; these receipts do not prove the current checkout or
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

- The current HTTP/2 inputs are included in the complete platform matrices
  above. HTTP/2 and HTTP/3 performance measurements and final-source release
  qualification remain pending. Earlier HTTP/2 receipts using Hypercorn are
  historical.
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
