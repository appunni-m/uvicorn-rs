# Can I replace Uvicorn?

**Not yet from PyPI.** Immutable tag `v0.3.3` failed candidate qualification
when performance acceptance compared machine-specific dependency receipt
paths and compiled-file hashes across systems. Version 0.3.4 is being prepared
with normalized cross-system version comparison; its own exact-source gates
must pass before publication.
The distribution name is `uvicorn-rs`; it provides the `uvicorn` command, the
`uvicorn` import namespace, and `python -m uvicorn`. The optional internal
Cargo/PyO3 adapter remains `uvicorn-rs-py`. Keep upstream `uvicorn` and
`uvicorn-rs` in separate environments because they install overlapping files.
The [quickstart](quickstart.md) and [rollback guide](fastapi-evaluation.md#restore-upstream-uvicorn)
describe the install path after publication.

<a id="current-status-2026-11-02"></a>
<a id="current-status-2026-11-04"></a>
<a id="current-status-2026-11-05"></a>
<a id="current-status-2026-11-06"></a>
<a id="current-status-2026-11-07"></a>
<a id="current-status-2026-11-09"></a>
<a id="current-status-2026-11-10"></a>

## Current status (2026-11-10)

Main commit `a8cef4cc` passed CI [#774](https://github.com/appunni-m/uvicorn-rs/actions/runs/42776625577)
with 100% unified coverage (15,120/15,120 regions and 11,120/11,120 lines),
and benchmark [#381](https://github.com/appunni-m/uvicorn-rs/actions/runs/42796770165)
completed on Linux x86-64, Linux ARM64, and macOS ARM64. Candidate
[#4](https://github.com/appunni-m/uvicorn-rs/actions/runs/42813769106) passed
package checks and its exact-source coverage recheck, then failed performance
acceptance because it compared full dependency receipts across platforms.
Version 0.3.4 fixes that false cross-platform comparison and requires fresh
exact-source CI, coverage, benchmark, docs, and candidate checks.

The immutable `v0.3.1`, `v0.3.2`, and `v0.3.3` tags remain unpublished. No
Cargo or PyPI artifact was published. See the [release guide](releases.md) for the current stage and the
[versioned compatibility contract](maintainers/uvicorn-0.54.0-contract.md)
for reference-only failures and their candidate acceptance rules.

### Historical PR #23 follow-up

CI [#689](https://github.com/appunni-m/uvicorn-rs/actions/runs/42061360886)
tested head 0572a48 at merge source 3cc692ac. Linux installed-wheel parity
passed 786/786 and Windows passed 759/759 (27 POSIX-only inputs are declared
inapplicable). The Linux and Windows candidate consumers passed. macOS ARM64
passed 785/786; the remaining TLS-over-Unix-domain-socket case returned the
expected HTTP 200 and exited cleanly, but logged Hyper's NotConnected error
during TLS shutdown. The macOS candidate archive was not produced.

The focused follow-up treats NotConnected from this completed-connection
shutdown as a peer disconnect. Its selected macOS parity case passed locally
after rebuilding the extension; hosted confirmation is still required. The
full coverage job in #689 was running against the earlier head when this status
was recorded, so its report cannot qualify the follow-up source.

The prior [CI #688 coverage artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/42045047273/artifacts/13429813667)
had three passing repeats across all 1,453 cases, with zero failures or
infrastructure retries, 15,056/15,057 regions and 11,078/11,078 lines. Its
single uncovered region was the unreachable None arm of the request-body timer
state. The PR head encodes the timer invariant directly, removing that arm.
That historical source did not meet the raw coverage gate. The current main
source's raw 100% result is recorded in the [current status](#current-status-2026-11-09);
a separate Coverage-MCP receipt is optional.

[CI #640](https://github.com/appunni-m/uvicorn-rs/actions/runs/41641278412)
tests PR #21 head `8e0f792a7dc00597c580fb7ddc6d5222e0310ec2` at clean
merge producer `f42a99b1555133be4ba5095a6f48fe4fb9ffa22f`, after removal of
peer-read recycling. Runtime-source digest is
`c3b34f3eec9888f42984aac28421183d947a80700e634312afac9579e0c5a88c`.
Linux and macOS each pass all 786 public inputs and their package consumers.
The exact Linux wheel also passes the CPython 3.9.25 consumer. Normal native
contracts pass 215/215; the additional 44 fault contracts remain in coverage.

Windows raw parity is 757/759, with one failed stock SIGINT/TCP-wakeup
comparison and one stock SIGBREAK shutdown timeout recorded as infrastructure
failure. The candidate serves and exits cleanly on both inputs. The SIGINT
row passes the existing exception on offline review. SIGBREAK lacked recovery
evidence, so the gate correctly rejected the full job and packaging did not run.
The diagnostic-only follow-up
[CI #641](https://github.com/appunni-m/uvicorn-rs/actions/runs/41647390647)
captures the known startup replacement and TCP-wakeup hang together after
SIGBREAK; its raw report remains failed. The composed acceptance requires both
complete defect signatures and a clean candidate. See the
[versioned acceptance contract](maintainers/uvicorn-0.54.0-contract.md#acceptance-of-known-differences).

The following PR #21 results are historical and do not qualify PR #23 or the
release candidate.

### Earlier qualification: CI #637 and #638

[CI #637](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084)
tests [PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21) head
`b9ed5c693889a54c5ba1d3f8796702da735981cc` at clean merge source
`00f38c82dd869ba0dcc7068cbc5cc769cd0f6294`. The reports share runtime-source
digest `7646e41b9dd9ca6b43b2f93d60f83e7ed712c69c1758d97053974bb2c5a09795`.
All three public matrices used CPython 3.12.13 and the pinned Uvicorn 0.54.0
oracle.

| Platform | Raw passed/selected | Failed | Infrastructure failed | Not run | Retained report |
| --- | ---: | ---: | ---: | ---: | --- |
| Linux x86-64 | 786/786 | 0 | 0 | 0 | [13221198169](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13221198169) |
| macOS ARM64 | 786/786 | 0 | 0 | 0 | [13222316858](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13222316858) |
| Windows x86-64 | 758/759 | 1 | 0 | 0 | [13222662150](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13222662150) |

Windows excludes the 27 explicitly declared inputs requiring Unix-domain
sockets, inherited POSIX descriptors, a Unix-only listener-transfer race, or
POSIX-only signals and worker health checks. The exact exclusions are in the
[recorded workflow](https://github.com/appunni-m/uvicorn-rs/blob/b9ed5c693889a54c5ba1d3f8796702da735981cc/.github/workflows/ci.yml).

All 16 indexed custom HTTP/WebSocket protocol, `ssl_context_factory`, HTTP/2
ALPN and response header/trailer capacity cases passed on all three systems.
The [versioned contract](maintainers/uvicorn-0.54.0-contract.md) identifies the
mandatory surface and case inventory. The matrix proves those inputs; it does
not claim every possible hook, application or configuration combination.

<a id="windows-reference-hang-acceptance"></a>

### Windows reference-defect acceptance

In historical CI #636 the raw failed comparison was
`python-api.module-cli-web-concurrency-two-workers-serve-request`.
The stock reference serves requests but hangs after one Ctrl+C; a diagnostic
TCP connection releases it. This is the narrow symptom accepted by
[policy uvicorn-0.54.0-windows-two-worker-sigint-tcp-wakeup@1](https://github.com/appunni-m/uvicorn-rs/blob/2d3633d8b79e6f0b8ab0bf72466418d1d8b1662f/scripts/windows_reference_hang.py).

That retained `compatibility-acceptance.json` records
`accepted_with_reference_exception`, separately from failed raw parity.
All three eligible candidate lifecycle contracts pass: correct responses,
both workers stopping within the original deadline, and no forced kill,
replacement, extra signal or diagnostic wakeup. A candidate crash/hang or a
different reference failure is rejected. This is not a claim that 759 raw
parity comparisons passed, and the upstream hang's precise cause remains
unverified.

The current policy version `uvicorn-0.54.0-windows-two-worker-sigint-tcp-wakeup@2`
adds one exact indexed input: `python-api.module-cli-two-workers-from-uvicorn-workers-environment`
with `UVICORN_WORKERS=2`. It retains the raw failed comparison, requires the
stock process to be released by exactly one post-timeout TCP connection, and
requires the candidate to serve the same request and stop both workers within
the original deadline. The [current acceptance code](https://github.com/appunni-m/uvicorn-rs/blob/main/scripts/windows_reference_hang.py)
rejects every other reference or candidate failure.

CI #637 instead captures a stock startup failure in
`python-api.module-cli-two-workers-serve-request`: one worker raises
`WinError 10022` in `sock.listen()` and the supervisor replaces it. The
candidate returns the same response, retains both original workers and stops
cleanly after one SIGINT. The shutdown-hang policy correctly rejects this
different failure. A separate startup policy requires the exact captured
traceback, one reference replacement before shutdown, complete surviving
worker cleanup, and the unchanged candidate correctness contract. Every
response, signal and deadline comparison remains required.

Local replay against the clean CI #637 source passes that separate decision
and all three candidate lifecycle checks. Raw parity remains 758/759 with one
failure; this does not make the already-failed hosted job successful. The
updated gate was subsequently exercised in
[focused CI #638](https://github.com/appunni-m/uvicorn-rs/actions/runs/41624376500/job/125877907532)
on clean source `68c063f623852bcfd0dfe937fe2a6eca189aeb65`.
That run retains one passing raw comparison and two failed comparisons:
the exact startup defect and the SIGINT/TCP-wakeup shutdown defect. The
separate receipt accepts each through its own policy and passes all three
candidate lifecycle contracts. The installed normal wheel's native SHA-256 is
`51ce6ec3f2d344afffd0f7fd49c4f0dab00d2cad45d70f170d56d2c547dc03e2`.
The [retained artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/41624376500/artifacts/13224704148)
includes the raw report, separate decision, logs and wheel. Offline replay
reproduces the hosted decision, and wheel RECORD and native identities match.
This focused run does not replace complete Windows package qualification.
See the
[versioned policies](maintainers/uvicorn-0.54.0-contract.md#acceptance-of-known-differences)
and [original capture](https://github.com/appunni-m/uvicorn-rs/blob/develop/tools/upstream/uvicorn-windows/evidence/ci637-startup-worker-failure.json).

### Artifacts, Python profiles and remaining gates

The [CI #637 Linux candidate](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13220888591)
contains both intended Cargo archives, an abi3 wheel and an sdist. Its
default/`http3` Cargo, wheel and rebuilt-sdist consumers pass. The
[macOS candidate](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13221564463)
wheel and clean consumer pass. Their manifests, payload hashes, packaged
source and wheel RECORD/native identities were checked against the clean
producer source.

The separate [Python-floor consumer](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642084/artifacts/13222178838)
passes on CPython 3.9.25 using the exact Linux abi3 wheel. It verifies install,
CLI/imports, live ASGI lifecycle, cancellation and caller-loop behavior; it is
not the complete parity matrix on Python 3.9.

CI #637 proves the macOS Bash 3.2 wrapper and TLS fixture-directory identity
repairs. Windows package/consumer qualification remains incomplete after the
reference mismatch. Unified coverage measures 14,809/14,809 regions and
10,894/10,894 physical source lines, but strict validation fails because raw
LLVM function-line totals are incorrectly equated with unique source lines.
The validator repair independently replays LCOV line/hit sets while retaining
raw JSON checks. Actual Coverage-MCP review of the captured producer returns
zero gaps with matching source and passing tests across all 46 pages; attachment
passes. These are historical receipts for that producer, not the final source.
The maintainer reconfirmed on 2026-11-05 that a separate Coverage-MCP review is
not required. Exact-source raw coverage at 100%, matched three-system FastAPI
measurements, complete final-source artifacts and publication remain open.
Later wrapper, upload-diagnostic and documentation changes are not qualified
by these older receipts.

[Documentation #263](https://github.com/appunni-m/uvicorn-rs/actions/runs/41614642063)
built successfully for its recorded source; PR deployment was skipped. This
documentation refresh needs its own build. See the [release guide](releases.md)
and [coverage record](coverage.md) for the remaining acceptance sequence.

## Historical diagnostic records

### Input@40 CLI and Python API baseline profiles — 2026-10-27

The input@40 CLI baseline passed 60/60 and the Python API oracle-parity
profile passed 209/209 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.
The runs bind to dirty source revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
manifest SHA-256 `ede173a29d162a002ee37d469f1ecaeeafa5d8e97c15c5bfbc67157b55c6f9be`,
CLI input SHA-256 `b86587d0f2f6d890a9dfef3b974bd2f6b5f5cc109a09fde93c6935e892688cf0`,
and Python API input SHA-256 `3fb4cb2e7e4146060908da556d692ec8654196762261797bf92a352a4f847a96`.
Run IDs, report hashes, and the corrected SIGINT exit-code contract are in the
[parity evidence record](parity.md#input40-baseline-cli-and-python-api-profile-runs-2026-10-27).
These are local one-pass source-profile receipts. The earlier hosted run,
[CI #435](https://github.com/appunni-m/uvicorn-rs/actions/runs/40591281095),
passed 660 declared public oracle cases from input@42 on a clean-source installed
wheel under Linux x86-64. CI #455 later passed 702/702 at head
`4a429684d5fd92c1068c7776093452cca1ccfc90`, and CI #456 passed 707/707 at
`1c5a9a7fca45e6e4e985cf775ef844bc1fd37e83`; both are prior-head evidence.
Neither
single-platform result establishes full Uvicorn compatibility; cross-platform
parity, native/fault contracts, clean-main release evidence, and release
repeats remain open.

### Full installed-wheel parity — 2026-10-27

A local abi3 wheel built from the current dirty checkout passed the complete
580-case public parity inventory against a separate Uvicorn 0.54.0 environment
on macOS 15.7.7 ARM64 / CPython 3.12.13. The result includes CLI, Python API,
protocol, TLS, WebSocket, and lifecycle cases. The shutdown-timeout regression
found during this run was fixed and the full matrix passed after rebuilding the
wheel. See the [source-bound parity receipt](parity.md#full-installed-wheel-public-parity-after-lifespan-shutdown-fix-2026-10-27).

This is local evidence from a dirty source revision. Linux and Windows, other
supported Python versions, target-only fault contracts, native-core contracts,
and clean exact-main release acceptance remain open, so it does not establish
a cross-platform drop-in guarantee.

### Focused Python import and signature refresh — 2026-10-27

After changes to the Python wrapper imports and constructor return annotations,
`python-api.public-imports-and-signatures` passed 1/1 against Uvicorn 0.54.0
on macOS ARM64 / CPython 3.12.13. See the [source-bound receipt](maintainers/uvicorn-0.54.0-contract.md#focused-python-import-and-signature-refresh-2026-10-27).
This selected case does not establish full Python API or installed-package
compatibility.

### Focused TLS verifier error parity (2026-10-26)

The Config/Server input with `ssl_cert_reqs=3` passed 1/1 against Uvicorn
0.54.0. Both sides raise `ValueError` with the message `3 is not a valid
VerifyMode`. This checks that invalid value only; it does not establish full
TLS or client-certificate parity. A second Config/Server input uses an empty
`ssl_ca_certs` file with `ssl_cert_reqs=2`; both servers reject startup and
emit matching `ssl.SSLError` observations. It passed 1/1 against Uvicorn
0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. These two cases check only
these TLS configuration errors; they do not establish full TLS or
client-certificate parity. See the selected evidence in
[coverage status](coverage.md).

The Config/Server input `python-api.config-server-ignores-empty-client-ca-path`
passed 1/1 on 2026-10-26 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
3.12.13. Both sides served HTTP 200 and shut down on SIGINT when
`ssl_ca_certs=""` and `ssl_cert_reqs=0` were supplied (run
`bae7d82e92ca496e9d5eb9b2aa4c843b`, report SHA-256
`01f634b8d79dcf1ebab7cee0e74fa5adad421a74e94e870d4615faba2ac4aad9`, dirty
source revision `35e548f08d1a4248488fc1351ed8850e7c80f23c`, native extension
SHA-256 `9879a7e67d83799c1f360ae67732ee27aa902dbb626fa85702bb3ee1a9e146d1`).
This confirms that one empty CA path is ignored at the Python compatibility
boundary; it does not establish full TLS or client-certificate parity.

### Focused legacy PKCS#12 private-key parity — 2026-10-27

`python-api.config-server-uses-pkcs12-pbe-sha1-3des-key` passed 1/1 against
Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. Both servers loaded a
PKCS#8 key encrypted with PKCS#12 PBE-SHA1-3DES, served HTTP 200, and shut
down on SIGINT. This verifies that key format through Config/Server only; it
does not establish other legacy PBE algorithms or full TLS parity. See the
[source-bound receipt](maintainers/uvicorn-0.54.0-contract.md#focused-pkcs12-pbe-sha1-3des-key-parity-2026-10-27).

The two focused `Server.serve()` cancellation inputs cover cancellation after
readiness and while lifespan startup is held. The startup input first exposed
that the adapter accepted TCP connections before startup completed, while
Uvicorn 0.54.0 had not bound its listener. Listener binding now follows
lifespan startup, and the startup cancellation gate leaves the listener closed
while retaining the lifecycle task for explicit shutdown. Both selected
inputs passed 1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13. The retained
post-startup report is `target/kata-progress/gjpr-server-serve-cancellation-after-startup-20261026.json`
(run `e3f72e0ea2b44841b6f4d645cafffd80`, SHA-256
`de8c153cde3be8ab0ff2ec1d173b4705da4d5c0044d91d97c565464b9f79ba9b`). The
startup-cancellation case now has a current selected receipt
`target/kata-progress/gjpr-server-cancel-during-startup-20261027.json` (run
`e530db81248644218613ff4a19fe824f`, SHA-256
`b8bbf7ffe2f17232144c4b018c145335b72d462eb13cccba3846b4345232e4eb`). Both
observations show startup entered before cancellation, no accepting listener
after cancellation, a finished cancelled serve task, and `started=false`.
See the [source-bound maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#focused-serverserve-startup-cancellation-2026-10-27).
These two cases do not establish the full Uvicorn lifecycle or platform
matrix.

On 2026-10-26, a focused batch of five Python API encrypted-key cases and five
startup-rejection cases passed 10/10 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 (run `97f7acf0ca444a7ca6ecde00dc75063f`, report SHA-256
`803cd7b9eaf937c0023418f4e5cfd5fac7ff089efb5f6bd39c5da227680d0a0b`, source
SHA-256 `21d1747383dcb68827f6f2b318d09055f6603da89f488a2cb86df73d52c74a19`,
native extension SHA-256
`9879a7e67d83799c1f360ae67732ee27aa902dbb626fa85702bb3ee1a9e146d1`). This
local dirty-source receipt covers AES-128/192 key loading, malformed AES-256
IVs, and traditional-key startup rejection. It does not refresh the full
compatibility matrix or release coverage gate.

The source draft now exports the top-level `uvicorn.main` command and includes
`uvicorn.importer`. The selected `python-api.public-imports-and-signatures`
case passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13
on 2026-10-23 (run ID `02fea3c94d1e46eebaf17cf402941f73`; dirty-source SHA-256
`2ab00648452a5ea0ca1c4ef4942e4069440d92446734ccd5513ee6046e53f57e`). This
selected receipt verifies those imports and signatures for the source
checkout; it does not qualify an installed wheel or the broader Python API
profile.

The target distribution is `uvicorn-rs`. After release, it is intended to
provide the `uvicorn` import namespace, `uvicorn` command, and
`python -m uvicorn`, while remaining a separately named PyPI distribution. It
must not be installed alongside upstream `uvicorn`: both distributions own
files under the same import name. The project currently targets Uvicorn
0.54.0; compatibility with another Uvicorn release will require a separate
review. See the [versioned upstream settings reference](https://github.com/Kludex/uvicorn/blob/0.54.0/docs/settings.md)
for the starting contract. Maintainers keep exact case results and package
receipts in the [compatibility contract](maintainers/uvicorn-0.54.0-contract.md).

## Replacing Uvicorn after a compatible release

These are future migration steps. Use them only after a compatible release is
published and this page and the support matrix mark the features your app needs
as supported. The two distributions install files under the same `uvicorn`
import name, so do not install them together in one environment.

To replace upstream Uvicorn:

```sh
python -m pip uninstall uvicorn
python -m pip install "uvicorn-rs[standard]==0.3.4"
uvicorn --help
python -m uvicorn --help
```

To roll back, install the upstream version your application requires:

```sh
python -m pip uninstall uvicorn-rs
python -m pip install "uvicorn==<version-required-by-your-app>"
```

The project's pinned reference is `0.54.0`; choose the version required by
your application when rolling back.

## Compatibility scope

The compatibility work covers the command and settings, Python imports and
programmatic API, application loading, ASGI behavior, HTTP and WebSocket
protocols, lifespan, TLS and proxy settings, sockets, workers, reload,
signals, shutdown, and package extras. Matching a command name or passing a
few HTTP requests is not enough to claim a drop-in replacement. The
[maintainer contract](maintainers/uvicorn-0.54.0-contract.md) tracks the full
inventory and evidence; the [support matrix](support-matrix.md) is the shorter
user-facing summary.
