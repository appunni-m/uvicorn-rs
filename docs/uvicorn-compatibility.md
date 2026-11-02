# Can I replace Uvicorn?

The maintained Uvicorn 0.54.0 public input matrix passed on Linux x86-64,
macOS ARM64, and Windows x86-64. The 0.3.0 PyPI release is not published
yet; coverage review and matched FastAPI benchmarks remain release gates.
Plan an isolated application trial after publication and keep an upstream
environment available for rollback.

Both distributions install files under the `uvicorn` import namespace. Do not
install `uvicorn-rs` and upstream `uvicorn` in the same environment.

## Current status (2026-11-02)

Open [PR #21](https://github.com/appunni-m/uvicorn-rs/pull/21) promotes
`develop` head `c28474a164cce437cf41ec12d7ebd789027f8637` to `main` at
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. CI [#615](https://github.com/appunni-m/uvicorn-rs/actions/runs/41402063098)
passed the maintained installed-wheel public matrix against Uvicorn 0.54.0.
The candidate manifests identify the clean PR merge commit as
`a276c2efa2ac66f5532910d4c56e3128dc078ceb`, with source-tree digest
`7ca7f5953a9056a368a9310f615d530d29151e5a6c18c0a95b2b051a9f85db22`.

| Platform | Result | Failed | Infrastructure failed | Not run | Artifact (archive SHA-256) |
| --- | ---: | ---: | ---: | ---: | --- |
| Linux x86-64 | 784/784 | 0 | 0 | 0 | [13122780312](https://github.com/appunni-m/uvicorn-rs/actions/runs/41402063098/artifacts/13122780312) (`bbf73c004f1f22f6286b56c954808a73ac8065b30bfa87459f600252863c3092`) |
| macOS ARM64 | 784/784 | 0 | 0 | 0 | [13123400293](https://github.com/appunni-m/uvicorn-rs/actions/runs/41402063098/artifacts/13123400293) (`e8c756fec191c1f05fda1c53e5bb91214d842a9ae4c3a6387b5543ecb20c7705`) |
| Windows x86-64 | 757/757 | 0 | 0 | 0 | [13123616750](https://github.com/appunni-m/uvicorn-rs/actions/runs/41402063098/artifacts/13123616750) (`96aacf92b71dba388c7cfaa9a59c13d233914c0b3feeae506dca45143b85f531`) |

Windows excludes 27 explicitly declared inputs that require Unix-domain
sockets, inherited POSIX descriptors, a Unix-only listener-transfer race, or
POSIX-only signals and worker health checks. The maintained matrix includes
custom HTTP and WebSocket protocol classes, `ssl_context_factory`, HTTP/2
ALPN configuration, and HTTP/1, HTTP/2, and WebSocket response header/trailer
capacity cases. The exact case inventory is in the
[maintainer contract](maintainers/uvicorn-0.54.0-contract.md), and the platform
exclusions are listed in
[`ci.yml`](https://github.com/appunni-m/uvicorn-rs/blob/develop/.github/workflows/ci.yml).

CI #615 also built Linux, macOS, and Windows candidate bundles; their clean
consumers passed. The Linux bundle contains both Cargo archives, a wheel, and
an sdist; the sdist rebuild and default/`http3` Cargo consumers passed. The
macOS and Windows wheel consumers passed. The Python 3.9 wheel-floor check
passed. Documentation deployment [#254](https://github.com/appunni-m/uvicorn-rs/actions/runs/41402063093)
passed before this page refresh; the refreshed docs still need a strict build
and deployment.

The latest three-repeat unified coverage run completed below its gate at
14,860/14,894 regions and 10,915/10,933 lines. A focused local fix passes the
six affected startup-lifespan fault cases, but a full exact-source run and
independent Coverage-MCP review remain open. Matched three-system
ordinary-FastAPI benchmarks are incomplete. The candidate is not published.

## Historical diagnostic records
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
python -m pip install "uvicorn-rs[standard]==0.3.0"
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
