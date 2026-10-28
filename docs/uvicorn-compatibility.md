# Can I replace Uvicorn?

**Not yet.** The PyPI distribution `uvicorn-rs` has not been published, and the
current candidate has not passed the full Uvicorn 0.54.0 replacement contract.
Use upstream Uvicorn for production workloads that depend on unverified
behavior. You can [try the prototype from a checkout](quickstart.md) without
changing an existing application environment.

Both distributions install files under the `uvicorn` import namespace. Do not
install `uvicorn-rs` and upstream `uvicorn` in the same environment. The
replacement and rollback steps below apply only after a compatible version is
published.

## Current status — 2026-10-28

The current PR head is `8f50720cd0e1cc12fdb8d6c60b7108c8a14cc516`. Its
input@43 inventory contains 699 public oracle cases: 117 CLI process cases and
262 Python API cases, alongside protocol, lifecycle, and target-only contracts.
The installed-wheel parity job in [CI #452](https://github.com/appunni-m/uvicorn-rs/actions/runs/40633854307) passed 699/699 cases on Linux x86-64. Its unified coverage job is still running.
The local input@43 working tree adds one Python API SIGTERM case, bringing its
inventory to 700 public oracle cases (263 Python API cases). That case passes
1/1 as dirty-source diagnostic evidence; CI #452 predates it, so clean-source
parity evidence for the addition is still pending.

| What you need | Current state |
| --- | --- |
| Install from PyPI | Not available. The `uvicorn-rs` distribution has not been published. |
| Run the `uvicorn` command | The candidate exposes the `uvicorn` command and `python -m uvicorn`. Selected inputs cover help, settings, environment precedence, and startup; complete CLI parity is not proved. |
| Import and configure `uvicorn` | The candidate exposes `run`, `Config`, and `Server`. Selected signature, defaults, startup, and shutdown inputs are covered; the full programmatic contract remains open. |
| Serve a Python ASGI app | The adapter supports selected ASGI3, ASGI2, and WSGI paths through the Rust server. The pushed 699-case matrix passed on Linux x86-64; the additional local case is not yet in clean-source evidence, and this does not establish full Uvicorn compatibility. |
| Use workers, reload, sockets, or process controls | Selected parity cases cover some worker, reload, socket, signal, and graceful-shutdown behavior. Other combinations, platforms, and failure paths remain unverified. |
| Claim a performance advantage | Not supported. The previous three-system benchmark is incomplete, and benchmark work remains paused until parity is accepted. See [benchmark status](benchmark-status.md). |

The previous 695-case snapshot passed on Linux x86-64 and macOS ARM64, but it
predates the current 699-case commit. Four focused additions pass 4/4 in local
runs; their dirty-target reports are diagnostic only. See the [support
matrix](support-matrix.md) and [release gates](releases.md) for the current
evidence limits and remaining checks.

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
These are local one-pass source-profile receipts. The latest hosted run,
[CI #435](https://github.com/appunni-m/uvicorn-rs/actions/runs/40591281095),
passed 660 declared public oracle cases from input@42 on a clean-source installed
wheel under Linux x86-64. That single platform pass does not establish full
Uvicorn compatibility; cross-platform parity, native/fault contracts, clean-main
release evidence, and release repeats remain open.

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
python -m pip install "uvicorn-rs[standard]"
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
