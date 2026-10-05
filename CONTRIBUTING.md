# Contributing

Thanks for taking an interest in `uvicorn-rs`. The project is an experimental
ASGI server; contributions should preserve the support matrix and avoid
promoting a targeted probe result into a general compatibility claim.

The HTTP/3 task-reaping source passes 451/451 instrumented attribution cases
and three complete 451-case repeats with zero failures, infrastructure errors,
retries or cases not run. The matrix declares 214 public oracle comparisons and
237 target-only contracts across 70 input files and 63 operations. All 4,778
native regions and 3,371 lines are covered with zero unfiltered MCP gaps.
The restored normal build passes 214/214 public comparisons and all 15
exclusion checks with three selected live cases; see
[the current evidence status](docs/coverage.md#current-evidence-status).

## Development setup

The checked local setup uses CPython 3.12.13, Rust 1.98.1, Cargo, and `uv`.
The manifest declares Rust 1.85 as the minimum. Default and all-feature library
checks passed locally on Rust 1.85.0; CI checks that exact toolchain separately.
Set up the local environment with:

```sh
uv sync --python 3.12 --group benchmark
```

The optional benchmark group installs Uvicorn, uvloop, Hypercorn, and probe
clients. The server itself does not depend on Uvicorn, Hypercorn, uvloop, or
`starlette-rs` at runtime.

Run the version-pinned, input-only source/target matrix with:

```sh
uv run --group benchmark python scripts/run_parity.py
```

It exercises H1, H2, H3, WebSockets, disconnect delivery, and graceful
lifespan shutdown. See the [parity guide](docs/parity.md) for why Uvicorn is the
oracle for H1/WebSockets/lifespan and Hypercorn for H2/H3, and for the current
case scope. The latest local evidence is linked from the [support
matrix](docs/support-matrix.md); record a new result under a fresh filename.
Live oracle comparisons and target-only contracts have separate denominators.
Every native source/build change requires fresh source-matched coverage and
normal-build exclusion evidence; earlier profiles cannot certify the new build.
The held-response accept-error workflow uses the existing native fault point,
actual body and remote-close observations, cancellation diagnostics and
application cleanup. Keep its first-chunk barrier before fault arming and
preserve the original first-accept error case. Client deadlines and local
closure must not count as semantic success. See the [workflow contract](docs/parity.md#current-http3-workflows).

## Before submitting

Run the Rust formatter, linter, and API documentation build:

```sh
cargo fmt --all -- --check
cargo clippy --all-targets --all-features --locked -- -D warnings
RUSTDOCFLAGS='-D warnings' cargo doc -p uvicorn-rs --no-deps --locked
```

The HTTP/3 probe utility is a separate Cargo manifest and has its own lockfile:

```sh
cargo fmt --manifest-path tools/http3-probe/Cargo.toml --all -- --check
cargo clippy --manifest-path tools/http3-probe/Cargo.toml \
  --all-targets --all-features --locked -- -D warnings
```

After building the extension, run the focused black-box probes for the behavior
you changed. For broad protocol or lifecycle changes, run the complete current
probe set:

```sh
uv run python scripts/probe_http.py
uv run python scripts/probe_http2.py
uv run python scripts/probe_streaming.py
uv run python scripts/probe_websocket.py
uv run python scripts/probe_cancellation.py
uv run python scripts/probe_lifespan.py
```

The optional `starlette-rs` check requires installing that framework
independently. These probes do not replace the complete ASGI conformance suite,
which has not yet been run.

## Rust error policy

Operational failures return `Result`; Python-facing failures return `PyResult`
and preserve the original exception where available. Do not use `panic!`,
`unwrap()`, or `expect()` in production code. Represent ownership and state
invariants in the types rather than asserting them with a panic. Handle task
join failures, cancellation, and transport errors through their result paths.
Review dependency methods for documented panic paths as well as authored
macros. For finite header-map capacity, use `HeaderMap::try_append` and propagate
its error; `append` can panic internally on valid large ASGI header collections.
Construct response headers before committing response state, and retain task
ownership until fallible WebSocket handshake construction succeeds.
Put coverage-only fault branches and their state-machine setup behind
`cfg(coverage)`. An inactive branch still containing diagnostic literals does
not satisfy normal-build fault exclusion; check the compiled library as well
as the live behavior.
Build the native runtime through its fallible constructor and register the
built runtime explicitly. Preserve task-setup errors in the native result
channel, including failures before Python task creation; closing an owned
awaitable must not replace the original exception with a cleanup error.

Every Python task bridge requires a cleanup tracker. Request applications and
their post-response observers share the server's request tracker; lifespan
cancellation uses a separate tracker so its active main task cannot block
request cleanup. Await native task destruction before draining tracked Python
cleanup. Keep the original application or registration error when cleanup also
fails, and report secondary failures separately. Shutdown uses bounded stages;
Python code that suppresses cancellation or takes longer than those stages can
remain unfinished. See [the ownership and shutdown contract](docs/architecture.md).

The main crate and HTTP/3 probe both deny Clippy's `panic`, `unwrap_used`,
`expect_used`, `print_stdout`, and `print_stderr` lints. Use fallible I/O writes:
required stdout observations propagate their errors; best-effort stderr
diagnostics may discard the write result. Keep these checks enabled in normal
and coverage builds.
There is no runtime panic allow list.
These lints and injected failure cases do not establish recovery from
process-wide allocation failure or unwinds inside dependencies.

The Clippy `panic` lint has one coverage-only exception, scoped to
`coverage_panic`, a `cfg(coverage)` helper. It simulates a foreign task unwinding
or a poisoned mutex so the black-box fault matrix can exercise cleanup and
error reporting. The helper and its callers are absent from production builds.
The parity runner validates each injected panic's source, message, and exact
count for that process; an additional or unexpected panic fails the case.
Hook validation is independent of exit validation. An unexpected hook fails
verification even when the process exits successfully; a matching injected
hook does not excuse a failing exit policy.
These cases remain target-only fault contracts, not oracle parity.

## Performance changes

Do not infer speed from language, SIMD availability, or a microbenchmark alone.
For performance changes, follow the [full benchmark setup and commands](docs/benchmarks.md).
Record the source revision/hash, machine, Python and dependency versions, load
parameters, correctness-gate result, throughput, latency percentiles,
server/client CPU, and sampled RSS. Use the same ASGI app and load client for
candidate and baseline. Do not overwrite an existing raw result file; give new
runs a distinct name. See [the feasibility report](docs/feasibility.md) for
current results and their limits.

## Documentation and changes

Update the support matrix when implementation status or evidence changes. Keep
performance statements scoped to the exact workload and environment. Explain
unsafe code only if the repository policy is deliberately changed; the main
crate currently forbids unsafe Rust. Keep `starlette-rs` optional and outside
the server's runtime dependencies.

The CI checks, artifact targets, and annotated-tag candidate process are
documented in [Release candidates](docs/releases.md). Do not publish or tag a
public release before the exact clean commit passes hosted CI and the public
distribution decision is made.

## Project status

The repository uses [BSD-3-Clause or MIT](LICENSE), at the recipient's option.
There is no contributor license agreement or DCO configured. See [support](SUPPORT.md)
and [security reporting](SECURITY.md) for contact and disclosure expectations.
