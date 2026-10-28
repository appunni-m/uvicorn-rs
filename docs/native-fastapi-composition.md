# Native FastAPI-RS composition evidence

## Hosted pinned composition pass (2026-10-28)

The native FastAPI-RS composition job in CI
[#464](https://github.com/appunni-m/uvicorn-rs/actions/runs/40772727247)
passed for committed PR head `a4b37c554deb99638d190ecf03e99857ecc49232`.
It used FastAPI-RS `0afccce9f35447f38ebb5e94d0e67fd338ea7ea4` and its pinned
Starlette-RS revision `4139a72449bf5751e8902fb1c7175ee7f191d338`, confirmed the
locked normal/build graph excluded PyO3, and passed all 17 declared H1/H2
real-socket inputs. This is source-bound hosted composition evidence for that
commit; it does not establish H3, TLS, WebSockets, full framework semantics,
cross-platform behavior, or performance.

## Current mainline source check (2026-10-25)

The public FastAPI-RS `main` ref resolved to
`0afccce9f35447f38ebb5e94d0e67fd338ea7ea4`. That commit's
`fastapi-rs/Cargo.toml` pins Starlette-RS at
`4139a72449bf5751e8902fb1c7175ee7f191d338`; the Starlette-RS `main` ref is
`8b15c62e8a836a622f426d52bd5a4429b45936d5`, but the composition correctly
uses FastAPI-RS's exact metadata pin. The native composition CI pin now targets
FastAPI-RS `0afccce` and Starlette-RS `4139a72`.

Using clean detached Git checkouts at those two exact revisions, the selected
real-socket input
`http1.request-stream-progress-before-upload-complete` passed once on the
Uvicorn-RS draft based on `86e72e181d00feca1b4db7f30377d5d9d4345b83`.
`cargo run --locked` accepted the existing example lockfile, and the locked
normal/build dependency graph contained no PyO3. The local receipt is
`target/kata-progress/native-composition-current-main-20261025/receipt.json`
(SHA-256
`3d565ab167a70ae81cfd0d7d52f63b0d7acfbcc5963a37297f8ec66dd2028219`).

The remaining 16 manifest inputs then passed together against the same source
snapshot and dependency pair. Before running them, all 2,280 files in the
snapshot manifest were verified to match the current Uvicorn-RS worktree. The
batch excluded the already-passed upload-progress input, so the two local runs
cover 17/17 distinct H1/H2 inputs once each for FastAPI-RS `0afccce` and its
pinned Starlette-RS `4139a72`. The outcome record is
`target/kata-progress/native-composition-current-main-20261025/remaining-16-cases-receipt.json`
(SHA-256
`514bae0bdad8a5f80063a43b1bde71ded0923916a58297f4725a3dc02620d2cf`). Its
test summary is based on the captured command output; the raw stdout log was
not retained.

This is local evidence on an uncommitted Uvicorn-RS draft. Hosted exact-source
acceptance remains required. The 17 H1/H2 inputs do not establish full
framework compatibility, HTTP/3, TLS, WebSocket, lifespan, cross-platform, or
performance behavior.

## Previous current-main check (2026-10-24; superseded by the newer pin above)

On the dirty Uvicorn-RS draft based on `86e72e181d00feca1b4db7f30377d5d9d4345b83`,
the selected real-socket input
`http1.request-stream-progress-before-upload-complete` passed once through the
native FastAPI-RS → Starlette-RS → Uvicorn-RS stack. The isolated sibling
checkouts were clean at FastAPI-RS `e5a6e91cb02b3229f9fbdfce1b00171c6913ccfe`
and Starlette-RS `4139a72449bf5751e8902fb1c7175ee7f191d338`. The locked
normal/build dependency graph contains no PyO3 package.

A second selected case, `http2.path-query-routing`, passed on the same dirty
Uvicorn-RS base revision with current FastAPI-RS `main`
`2756140f0a5fad750d11120b668e3bf5899fa102` and its pinned Starlette-RS
revision `4139a72449bf5751e8902fb1c7175ee7f191d338`. It exercises H2 prior
knowledge for `GET /items/7?tag=blue` and checks the 200 JSON route result.
The runner used isolated clean sibling checkouts; FastAPI-RS's build identity
guard confirmed the Starlette-RS pin. The locked normal/build dependency graph
for this revision pair contains no PyO3.

A third selected case, `http1.path-query-routing`, also passed once on that
same current dependency pair and Uvicorn-RS draft. It sends
`GET /items/42?tag=green` over HTTP/1.1 and checks the 200 JSON route result.
Its local receipt is
`target/kata-progress/native-composition-h2-isolated/h1-path-query-routing-receipt.json`
(evidence ID `92ee11356e4d4217bb416e26`; receipt SHA-256
`f6232b730071886d116f2a2dad7e291ae8b5968180e08e848475d9d5f2de138e`).

The example lockfile was regenerated against those pinned source revisions;
`cargo tree --locked --offline` now resolves without changing it. Its SHA-256
is `993e3418e08d559457c43e3955f48f9cdb87e686e4c42502e77dfa39d15b7c8d`, and
the input manifest SHA-256 is
`5224e4c3e5a88e3699eb71490651ffc7f2ea6a41edf302b4884d3133be392bcd`.

The worktree source manifest and local receipt are retained under
`target/kata-progress/native-composition-current-20261024/`. The receipt SHA-256
is `de5b7560f22310ce15bd22d88a3e9297a8fc00b9d2a094a8c51844c3ecb23353`;
its Uvicorn worktree content digest is
`194270638e8805107fedd57c4112da419e97134344f58b075285e909cd8d23dc`.

The H2 receipt is retained at
`target/kata-progress/native-composition-h2-isolated/receipt.json` (evidence ID
`11069fe5432772500248d62d`; receipt SHA-256
`14f0e0620074b80e805fdaa7ef0a1bca5f1de4aee429a4079f1100f96e1be7e8`; Uvicorn
source-tree SHA-256
`170649c2ae25c8080c1c8790176567eae9870bd642bb80cb555d95925d2121b5`; manifest
SHA-256 `5224e4c3e5a88e3699eb71490651ffc7f2ea6a41edf302b4884d3133be392bcd`).
The earlier H1 request-stream-progress run used FastAPI-RS `e5a6e91`; the
remaining-input batch below includes a fresh run of that case against current
`main`. Together, the two path/query cases above and the remaining 15 inputs
cover all 17 manifest cases once on the current FastAPI-RS/Starlette-RS pair.
The remaining-15 receipt is
`target/kata-progress/native-composition-h2-isolated/remaining-15-cases-receipt.json`
(evidence ID `fd9a40b9335a42e081c785de`; receipt SHA-256
`0eebcccdd1c00093916cd2f7452cd670d07cf3b9bf46086ef090321a2f43874a`; log
SHA-256 `dc61737c83fa6421a778c132b1b2f1a9d41dd15a683bfe2239d0f6452a2757e5`).
This is one local pass per input on a dirty Uvicorn-RS draft, not hosted CI,
repeated acceptance, or full Python FastAPI semantics. No H3, TLS, WebSocket,
lifespan, cross-platform, or performance claim follows from these cases.

**Hosted exact-source result (2026-10-19):** 17/17 real-socket H1/H2 inputs
passed in the dedicated composition job in exact-source CI run
[39185987997](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987997/job/117848420888).
The job used Uvicorn-RS `94c89b79c1f2a8e5f90b2171ee28ca929444a7f5`, FastAPI-RS
`f438a7cbb2308e6c1f795aef98e333de23388533`, and Starlette-RS
`b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`. The job's PyO3 check did not
execute: its `rg` command was unavailable on the hosted runner and the shell
condition treated that command error like a no-match. A local `cargo tree
--locked --edges normal,build` check over clean archives of these exact three
revisions found no PyO3 package. The corrected `grep` guard passed in hosted CI
run [39601499324](https://github.com/appunni-m/uvicorn-rs/actions/runs/39601499324)
against the prior feature-branch source pin. The refreshed current-main pin is
queued in run [39604738708](https://github.com/appunni-m/uvicorn-rs/actions/runs/39604738708).
The composition result is limited evidence, not a full FastAPI
contract, Python parity result, release candidate, repeated result, or
performance measurement.

## Earlier mainline source verification (2026-10-21; superseded)

Uvicorn-RS `main` is `40b296ecd48cda884bd5b76a020c017c76ac8189`. FastAPI-RS
`main` is `e5a6e91cb02b3229f9fbdfce1b00171c6913ccfe`; it exports
`fastapi_rs::native` from the sole `fastapi-rs` crate. Its default feature set
is empty, while the `python` feature enables optional PyO3. FastAPI-RS pins
Starlette-RS `4139a72449bf5751e8902fb1c7175ee7f191d338` in package metadata.

Using clean detached worktrees at those three exact revisions, the selected
real-socket input
`http1.request-stream-progress-before-upload-complete` passed locally. The
locked `cargo tree --edges normal,build` for the example contained no PyO3.
This proves one current-main H1 composition path and its dependency graph; it
does not refresh the 17-case hosted receipt, cover H2/H3/TLS/WebSockets or
framework lifecycle, or establish full FastAPI semantics. The native API is a
small Rust handler surface, not a Python FastAPI replacement.

The CI pins and example lockfile now target these exact mainline revisions.
Hosted confirmation of that refreshed pin is still pending. Reproduce the
selected input after checking out those exact revisions:

```sh
CARGO_TARGET_DIR=/tmp/native-composition-target \
  cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml \
  --locked -- examples/native-fastapi-contracts/manifest.json \
  --case-id http1.request-stream-progress-before-upload-complete
```

## Earlier main status (2026-10-20; superseded)

Uvicorn-RS `main` is `3c5cbb70e3bc27c07733700c1340776d8413ff23`. On that
commit, the focused real-socket input
`http2.request-stream-progress-before-upload-complete` passed with FastAPI-RS
`f438a7cbb2308e6c1f795aef98e333de23388533` and Starlette-RS
`b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`. The locked normal/build dependency
graph for this candidate composition contains no PyO3 packages. This is one
selected input, not a refreshed 17-case hosted result.

At the time of this earlier audit, FastAPI-RS `main` was `7efbf9b` and did not
export `fastapi_rs::native`. That finding was superseded when FastAPI-RS main
advanced to `e5a6e91`, which now exports the native module. The older hosted
receipt below still tests the separate `f438a7c` feature-branch snapshot and
must not be relabeled as current-main evidence.

The focused selector is committed on Uvicorn-RS `main` in
`examples/native-fastapi-contracts/src/main.rs` (SHA-256
`286ff0ba257b72ead29b8c837b779d5e8c55932446bd2ab6eb1a2c02c42636a6`). It keeps
the full manifest for shared application configuration while executing only
the requested case. The manifest SHA-256 is
`5224e4c3e5a88e3699eb71490651ffc7f2ea6a41edf302b4884d3133be392bcd`.
The following command reproduces the historical H2 input with Uvicorn-RS
`3c5cbb70`, FastAPI-RS feature branch `f438a7c`, and Starlette-RS `b4c8a65`;
it is separate from the current-main H1 check above:

```sh
CARGO_TARGET_DIR=/tmp/native-composition-target \
  cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml \
  --locked -- examples/native-fastapi-contracts/manifest.json \
  --case-id http2.request-stream-progress-before-upload-complete
```

**Previous focused HTTP/1.1 inputs (2026-10-20):** on Uvicorn-RS commit
`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`, with FastAPI-RS
`f438a7cbb2308e6c1f795aef98e333de23388533` and Starlette-RS
`b4c8a65c85e1b0d251ca05874412811eaa3ac7b8`, two individual real-socket
HTTP/1.1 inputs passed:

- `http1.slow-reader-bounds-polling-and-cancels-producer`
- `http1.request-stream-progress-before-upload-complete`

The current committed selector retains the complete manifest for shared
application configuration while executing only the requested case. Clean
detached checkouts were used for all three commits, and
`cargo tree --locked --edges normal,build` found no PyO3 package in the example
dependency graph. The build used Rust/Cargo 1.98.1 on macOS ARM64. These two
local inputs do not refresh the hosted 17-case result or establish full native
framework compatibility.

Reproduce the upload-progress input with:

```sh
CARGO_TARGET_DIR=/tmp/native-composition-target \
  cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml \
  --locked -- examples/native-fastapi-contracts/manifest.json \
  --case-id http1.request-stream-progress-before-upload-complete
```

## Hosted receipt source and input identity

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

For the exact-source revisions in the first table, check out sibling directories,
then run from the Uvicorn-RS root:

```sh
CARGO_TARGET_DIR=/tmp/native-composition-target \
  cargo run --manifest-path examples/native-fastapi-contracts/Cargo.toml \
  --locked -- examples/native-fastapi-contracts/manifest.json
```

The normal/build dependency graph for the recorded feature-branch revisions
contained no PyO3 package in the local locked check described above. The hosted Rust process
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

The [hosted composition job](https://github.com/appunni-m/uvicorn-rs/actions/runs/39185987997/job/117848420888)
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
evidence for the current single-core API. The hosted receipt uses the old
feature-branch revision. Current-main source availability and the one-case
local check are recorded above; the complete current-main hosted matrix remains
pending.
