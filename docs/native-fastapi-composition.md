# Native FastAPI-RS composition evidence

**Current result (2026-10-19):** 17/17 real-socket H1/H2 inputs passed in the
dedicated composition job in exact-source CI run
[39185987997](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987997/job/117848420888).
The job used Uvicorn-RS `94c89b79c1f2a8e5f90b2171ee28ca929444a7f5`, FastAPI-RS
`f438a7cbb2308e6c1f795aef98e333de23388533`, and Starlette-RS
`b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`. The job's PyO3 check did not
execute: its `rg` command was unavailable on the hosted runner and the shell
condition treated that command error like a no-match. A local `cargo tree
--locked --edges normal,build` check over clean archives of these exact three
revisions found no PyO3 package. The CI guard now uses `grep` and treats a
checker error as a failure; hosted confirmation of that corrected guard is
pending. The composition result is limited evidence, not a full FastAPI
contract, Python parity result, release candidate, repeated result, or
performance measurement.

## Current source and input identity

| Repository | Revision | State |
|---|---|---|
| Uvicorn-RS | `94c89b79c1f2a8e5f90b2171ee28ca929444a7f5` | exact `main` CI commit |
| FastAPI-RS | `f438a7cbb2308e6c1f795aef98e333de23388533` | pinned native feature branch |
| Starlette-RS | `b4c8a65c85e1b0d251ca05874412811eaa3ac7b8` | pinned by FastAPI-RS |

The manifest SHA-256 is
`5224e4c3e5a88e3699eb71490651ffc7f2ea6a41edf302b4884d3133be392bcd`; the
locked example dependency graph SHA-256 is
`05e867b1265386bfc21263f88de9dbaf481eda699c8b85c788b0a8799630b258`. The
Uvicorn native crate manifest SHA-256 is
`64b6be240b020c6b20bafdbce0fbc854797fe80c7b81424b90349b249ada46e9`.

The local dependency-graph check used clean `git archive` exports of all three
revisions and Cargo's locked normal/build graph. Its output was checked for
every package beginning with `pyo3`; none was present. The hosted composition
job passed all 17 inputs on Ubuntu 24.04 with Rust/Cargo 1.98.1. Its build log
records the exact source revisions but does not retain a separate dependency
graph receipt.

## Historical local prototype source identities

| Repository | Revision | State |
|---|---|---|
| Uvicorn-RS | `8e7e68046082a024a73877ee6476c5c395339839` | `main` |
| FastAPI-RS | `f438a7cbb2308e6c1f795aef98e333de23388533` | `codex/native-fastapi-core` |
| Starlette-RS | `b4c8a65c85e1b0d251ca05874412811eaa3ac7b8` | FastAPI-RS pinned source |

Each checkout was clean and detached at the listed revision. The example's
relative paths resolved in a sibling layout:

```text
workspace/
├── uvicorn-rs/
├── fastapi-rs/
└── starlette-rs/
```

FastAPI-RS's build script verified the Starlette-RS Git revision. Cargo used
an external target directory, so generated build output stayed outside these
source checkouts.

## Historical prototype build identity

The input manifest SHA-256 is
`5224e4c3e5a88e3699eb71490651ffc7f2ea6a41edf302b4884d3133be392bcd`.
The earlier Uvicorn example lockfile SHA-256 was
`b91c0f385bd07d12ce1bca54ffe38a63d59cc766872ae51f2583fcb4894f62bc`;
the FastAPI workspace lockfile SHA-256 is
`1fa63ad5cdf0d5af406ba6b615be4067c1fda2ba5f95f3bae2782473d747fa96`.

Cargo manifest SHA-256 values:

| Manifest | SHA-256 |
|---|---|
| Uvicorn example | `07608e8378e50decd648b32c020054fc546d0e0fb415d80beb66e5bb9d9dbcf0` |
| Uvicorn native crate | `f7a86081738f50eec15d8f820bee980e2cf9e00341c0fc116503559dba9e3e6c` |
| FastAPI workspace | `c090f1122e76aaf5b62fe26a56b1f994b6b739e991ee6d7372cc2697bce200bd` |
| FastAPI core crate | `dc6ec6a1ec99e707816da1ca39e56e26da09cb37ed2ac3da79bc889cdec4546c` |
| Starlette core crate | `44a31f840cefa1bad9d4348497b6ad980ac969165a51afbef9207b4ee50f96c0` |

Toolchain: `rustc 1.98.1`, `cargo 1.98.1`; platform: Darwin 24.6.0,
`arm64`.

## Reproduction

For the current revisions in the first table, check out sibling directories,
then run from the Uvicorn-RS root:

```sh
CARGO_TARGET_DIR=/tmp/native-composition-target \
  cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml \
  --locked -- examples/native-fastapi-contracts/manifest.json
```

The normal/build dependency graph for the exact current revisions contained no
PyO3 package in the local locked check described above. The hosted Rust process
passed these manifest inputs:

```text
http1.path-query-routing
http1.bodyless-get-omits-content-length
http1.json-body-consumption
http1.request-stream-progress-before-upload-complete
http1.pre-commit-application-error
http1.first-stream-frame-before-completion
http1.partial-upload-observes-disconnect-and-recovers
http1.slow-reader-bounds-polling-and-cancels-producer
http2.path-query-routing
http2.bodyless-get-omits-content-length
http2.partial-upload-reset-delivers-body-error-and-preserves-connection
http2.json-body-consumption
http2.request-stream-progress-before-upload-complete
http2.pre-commit-application-error
http2.slow-reader-bounds-polling-and-resets-producer
http1.graceful-shutdown-drains-active-response
http2.graceful-shutdown-drains-active-response
```

## Hosted composition verification

The [current hosted composition job](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987997/job/117848420888)
passed all 17 manifest inputs on Uvicorn-RS commit
`94c89b79c1f2a8e5f90b2171ee28ca929444a7f5` with FastAPI-RS
`f438a7cbb2308e6c1f795aef98e333de23388533` and Starlette-RS
`b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`. The overall exact-source CI run
also passed its unified coverage and package gates. The hosted job's attempted
PyO3 graph assertion was ineffective because `rg` was missing; the exact-source
local graph check above passed, and the workflow guard has since been corrected
but not yet rerun on a hosted commit.

The earlier dedicated composition job in run 38862681888 used Uvicorn-RS
`27de9f3ac7d259a3a9b612c3247ab2c60eb27306`; its parent coverage gate failed.
That result and run 38828501018 are historical evidence only.

The earlier build emitted one non-fatal `dead_code` warning for
`FastApiOperationRouter::find_slash_redirect_path` in this no-Python native
build.

## Limits

These single runs exercise only the example's cleartext HTTP/1.1 and HTTP/2
contracts. They do not cover composed TLS, HTTP/3, WebSockets, framework
lifespan integration, the full FastAPI validation/dependency/Pydantic/OpenAPI
surface, Python FastAPI parity, repeated composition, a fully green hosted
workflow, or performance. The older 51/51
receipt used a separate `fastapi-rs-native` crate and is historical; it is not
evidence for the current single-core API. The pinned FastAPI-RS revision is a
feature branch, not a claim that the native API is already in its default
branch.
