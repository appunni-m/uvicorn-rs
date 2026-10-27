# Can I replace Uvicorn?

**Not yet.** The `uvicorn-rs` Python distribution is not published, and the current prototype does
not match Uvicorn's full command, Python API, or deployment behavior. If an
application relies on those features, keep using upstream Uvicorn. You can
[try the current prototype from a checkout](quickstart.md) without changing
your application environment.

## Current status

| What you need | Current state |
| --- | --- |
| Install from PyPI | Not available. `uvicorn-rs` has not been published. |
| Run `uvicorn` from this checkout | Help, version, and selected input checks match the pinned Uvicorn release; console-process inputs verify current-directory app import resolution and startup with selected h11/TLS settings. The current CLI input index has 114 unique cases (schema `uvicorn-rs-parity/input@43`). The selected `cli.no-arguments-requires-app` case passes 1/1: both commands exit 2 with the same missing-`APP` stderr and empty stdout; see the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md). An earlier one-pass diagnostic executed 926 ASGI inputs and 258 native contract inputs; all 1,184 passed on that dirty source snapshot on macOS 15.7.7 ARM64 / CPython 3.12.13. Hosted CI run `40317129093` passed 508/508 public parity cases. The latest completed run, [CI #435](https://github.com/appunni-m/uvicorn-rs/actions/runs/40591281095), passed 660/660 declared input@42 public parity cases using a clean-source installed wheel on Ubuntu 24.04 / CPython 3.12.13; [CI #437](https://github.com/appunni-m/uvicorn-rs/actions/runs/40598829834) is in progress on 9b4fc703b and does not include the local input@43 chunked-body cases; docs run #154 passed on that head. A fresh current-source wheel passed four selected installed-candidate cases and the installed-consumer smoke. These results do not establish full Uvicorn CLI/API compatibility or cross-platform behavior. Three-repeat coverage, complete platform support, and broad option/API parity remain separate acceptance gates. See the [maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md) for source and artifact identities. The new `cli.websocket-zero-ping-timeout-is-accepted` input passes 1/1 for module-CLI startup; it does not exercise active WebSocket Ping/Pong behavior. Two startup cases pass 1/1 for a valid `--timeout-graceful-shutdown 1` option and `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=1` environment value. Two additional focused cases hold an ASGI request open, set the timeout through the CLI option or environment, send one SIGINT, and confirm both processes cancel the task and exit after the one-second graceful timeout; see the [graceful-timeout cancellation evidence](maintainers/uvicorn-0.54.0-contract.md#actual-graceful-timeout-cancellation-with-an-active-request). The selected `cli.invalid-host-env-is-rejected` case passes 1/1: invalid `UVICORN_HOST=invalid host` without `--host` makes both processes exit 3 with empty output. This confirms this environment value reaches listener startup, not full environment parity; see the [host environment receipt](maintainers/uvicorn-0.54.0-contract.md#focused-module-cli-host-environment-error-2026-10-27). A newer selected refresh of the invalid graceful-shutdown timeout case is documented in [parity results](parity.md); it adds no unique case coverage. A historical 38-case snapshot had 36 grouped passes plus two same-digest receipts; focused inputs for invalid `UVICORN_LIMIT_CONCURRENCY`, invalid `--log-level`, and invalid protocol/interface selectors passed against the oracle. Selected startup cases confirm explicit `--host 127.0.0.1` and `--port 0` override malformed `UVICORN_HOST` and `UVICORN_PORT` and an env-file value reaches the app factory when the process variable is absent. Six selected module-CLI environment cases also pass 6/6: listener host/port settings, `UVICORN_LIMIT_CONCURRENCY=1` returning HTTP 503, and explicit `--limit-concurrency 2` overriding both a malformed environment value and the valid `UVICORN_LIMIT_CONCURRENCY=1` value, plus `UVICORN_INTERFACE=wsgi` selecting the WSGI adapter and explicit `--interface asgi3` precedence over that setting; see the [focused parity evidence](parity.md#module-cli-environment-parity-2026-10-27). The malformed `UVICORN_INTERFACE=invalid` CLI case passes 1/1 with matching diagnostics, and an explicit `--interface asgi3` override of that malformed value also passes 1/1. A two-case group passes 2/2 for malformed `UVICORN_LOG_LEVEL` rejection and explicit `--log-level critical` precedence. Another selected case passes 1/1 when explicit `--timeout-graceful-shutdown 1` overrides malformed `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`; this verifies parse/startup precedence, while separate held-request cases cover actual timeout cancellation. Two further selected cases pass 2/2 when explicit `--ws-max-size` and `--ws-ping-timeout` override malformed environment values; they verify parse/startup precedence, not WebSocket session behavior. Four additional cases pass 4/4 for malformed `UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER` diagnostics plus explicit zero-valued CLI overrides; see the [focused request-limit environment result](parity.md#module-cli-request-limit-environment-validation-and-precedence-2026-10-27). Six more cases pass 6/6 for malformed `UVICORN_BACKLOG`, `UVICORN_TIMEOUT_KEEP_ALIVE`, and `UVICORN_TIMEOUT_WORKER_HEALTHCHECK` values with explicit CLI overrides; see the [numeric settings environment result](parity.md#module-cli-numeric-settings-environment-validation-and-precedence-2026-10-28). Seven further selected cases pass 7/7 for malformed WebSocket queue, ping-interval, and compression environment values with explicit CLI overrides, plus explicit `--limit-concurrency` precedence over malformed environment; see the [WebSocket and concurrency environment result](parity.md#module-cli-websocket-and-concurrency-environment-precedence-2026-10-28). Ten selected cases pass 10/10 for malformed HTTP, WebSocket, lifespan, worker-count, and reload-delay environment values with explicit valid CLI overrides; see the [selector and process-setting environment result](parity.md#module-cli-selector-and-process-setting-environment-precedence-2026-10-28). Four additional selected cases pass 4/4 for environment and explicit-option handling of `UVICORN_APP_DIR` and `UVICORN_ENV_FILE`; see the [focused app-dir and env-file parity result](parity.md#module-cli-app-dir-and-env-file-environment-precedence-2026-10-28). Four focused HTTP cases also pass 4/4 for environment-backed access-log suppression and colorized logs, with explicit access-log/no-color precedence; see the [logging environment result](parity.md#module-cli-logging-boolean-environment-precedence-2026-10-28). Two header cases also cover environment suppression of the default `Server`/`Date` headers and explicit `--server-header` precedence; the live Date timestamp is excluded from the explicit comparison because it changes between processes. See the [header environment result](parity.md#module-cli-header-environment-behavior-2026-10-28). Three more CLI process cases pass 3/3 for valid and invalid `UVICORN_RELOAD_DIRS` paths and explicit `--reload-dir` precedence; see the [reload-directory environment result](parity.md#module-cli-reload-directory-environment-binding-2026-10-28). Two live reload cases pass 2/2 for environment-driven `UVICORN_RELOAD_INCLUDES`/`UVICORN_RELOAD_EXCLUDES` and explicit CLI precedence: excluded-file changes stay quiet, included-file changes trigger reload, and explicit flags override conflicting environment patterns; see the [reload-filter environment result](parity.md#module-cli-reload-filters-from-environment-2026-10-28). See the [interface rejection](parity.md#invalid-module-cli-interface-environment-2026-10-27), [interface override](parity.md#explicit-module-cli-interface-overrides-malformed-environment-2026-10-27), [log-level result](parity.md#module-cli-log-level-environment-parity-2026-10-27), [graceful-shutdown precedence result](parity.md#explicit-module-cli-graceful-shutdown-value-overrides-malformed-environment-2026-10-27), and [WebSocket environment precedence result](parity.md#module-cli-websocket-environment-precedence-2026-10-27). See [parity results](parity.md) for source and input digests. The CLI accepts `--http h11` and `--http httptools` by routing to the Rust-native HTTP engine, plus `--ws websockets-sansio`, `--no-access-log`, and both color switches. Focused Python API parity verifies default per-message-deflate negotiation and compressed text echo, plus explicit disablement; these WebSocket-extension cases do not establish TLS negotiation or all extension parameters and fragmentation behavior. Color behavior is compared through startup, an HTTP request, and shutdown. Two HTTP/1.1 cases compare inherited and reset `contextvars` behavior with Uvicorn 0.54.0. The `h11` and `httptools` inputs each send an ordinary POST through the selected backend. Parser-specific malformed-request behavior is not established. These finite cases do not establish every runtime option, full CLI parity, or complete environment behavior. |
| Import `uvicorn` from this checkout | `run`, `Config`, `Server`, `Server.run()`, and `Server.serve()` expose Uvicorn 0.54.0 signatures. A focused two-case local run also compares `Server.startup()`, `shutdown()`, `main_loop()`, `on_tick()`, and `capture_signals()` signatures. The focused import/signature case includes the documented logging formatters and `ServerState` paths; a current-source three-case group covers Config properties and the retired loop hook, loading an env file before factory invocation, and missing-module reporting (3/3 on the local dirty source; the missing-module case refreshes an older-source pass; see the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#focused-config-and-run-parity-group-2026-10-27)). It also compares the deprecated `uvicorn.main.ServerState` warning. Focused cases cover single-process HTTP serving and selected lifecycle behavior. Two WSGI POST cases, through uvicorn.run() and python -m uvicorn, confirm finite bodies reach wsgi.input; four more selected cases confirm chunked-transfer POST bodies, with one- and two-chunk bodies through both entry points. Higher chunk counts and other WSGI behavior remain open (see [focused parity receipts](parity.md#focused-wsgi-post-request-body-parity-2026-10-28)). A current-source three-case startup group passed 3/3 for bind-failure lifespan cleanup, UDS pathname replacement with lifespan cleanup, and concurrent startup-failure waiter signaling (local dirty source; see the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#focused-startup-and-lifecycle-parity-group-2026-10-27)). The matrix also covers the `root_path` ASGI scope contract, direct `Server(lifespan=False)` versus `Config(lifespan="off")` and `Server(lifespan=True)` versus `Config(lifespan="auto")` (selected cases; see [coverage results](coverage.md)), `uvicorn.run(ws_max_size=...)`, acceptance of `uvicorn.run(ws_max_queue=...)` on the auto/SansIO path, `uvicorn.run(reset_contextvars=True)` for HTTP requests, positive and zero concurrency-limit behavior through the programmatic API, plus a selected module-CLI --limit-concurrency 1 check, the selected asyncio loop through `Config`/`Server.run()`, and a custom import-string loop factory through `uvicorn.run()`; the two-case local run confirms the returned loop type is active but remains dirty-source evidence. The selected API matrix also checks warning-level logging through `uvicorn.run()`, custom INI/JSON/YAML logging through `uvicorn.run(log_config=...)`, and access-log suppression through `uvicorn.run(access_log=False)`. Direct `Config.load()` comparisons now cover invalid HTTP and WebSocket import selectors and the HTTP/2 auto-backend error; these three cases passed against Uvicorn 0.54.0. The module CLI also passes warning-level logging, `UVICORN_LOG_LEVEL=debug`, explicit `--log-level warning` precedence over that environment value, custom INI/JSON/YAML logging with `--log-config` and `UVICORN_LOG_CONFIG`, `--no-access-log`, and a SansIO `--ws-max-queue` app-load diagnostic comparison. The API matrix also includes successful PKCS#8 key loading through Config/Server and the module CLI plus a wrong-password error through Config/Server, using one AES-256-CBC/PBKDF2-HMAC-SHA1 fixture. Additional selected inputs pass for loading traditional encrypted RSA keys with AES-128-CBC, AES-192-CBC, and AES-256-CBC through Config/Server, rejecting a wrong password and startup with an unsupported cipher, missing/malformed `DEK-Info`, invalid `Proc-Type`, or a missing end marker, and rejecting AES-256 keys with odd-length or non-hex IV values. These additional traditional-key cases are focused local dirty-source evidence, not full TLS parity or a clean hosted release candidate. Six selected TLS client-auth inputs exercise trusted certificates with default negotiation and TLS 1.2, optional anonymous clients with and without trust roots, rejection of an untrusted certificate with no roots, and trusted TLS 1.2 client authentication through the module CLI. The Config/Server five-case batch passed 5/5 and the separate CLI case passed 1/1; these selected cases do not establish full TLS parity. These cases do not establish encrypted EC PEM or other legacy cipher combinations. Runtime state-field updates, other levels, other precedence combinations, and most settings/lifecycle behavior remain unqualified. |
| Serve a Python ASGI app | An ASGI 3 prototype is available. See the [support matrix](support-matrix.md) for tested behavior and limits. |
| Use Uvicorn workers, reload, or process controls | Two focused module-CLI cases start two workers through `--workers 2` and `WEB_CONCURRENCY=2`, serve a request, and shut down on SIGINT against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. A third case sets `--workers 2` with `WEB_CONCURRENCY=3`; both implementations log exactly two worker starts, confirming the explicit CLI value takes precedence (selected run `1b050929c5ab433cbe647683c100f5b1`; details in the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#explicit-worker-count-precedence)). A selected POSIX case also compares replacement after one worker stops answering health checks; it passed 1/1 with a non-default 2-second timeout (run `ae4e43b0e69245a8b22cd67668cdaeba`, report SHA-256 `eae083b94d0d0637b0005fa9278066b48b52f787f93b06c3e58113270a602e1e`). The new two-worker SIGTERM shutdown case also passed 1/1 on the local dirty draft on macOS 15.7.7 ARM64 / CPython 3.12.13; both sides served HTTP 200, logged SIGTERM, and exited 0 (run `51cd568a8d5848e2ab90157c9abad3fe`; see [receipt details](maintainers/uvicorn-0.54.0-contract.md#two-worker-sigterm-shutdown)). A later focused case sent two actual SIGINT signals while an ASGI request task remained active; both processes served HTTP 200 and exited 0 without timing out on macOS ARM64 / CPython 3.12.13. Its logs are retained, but platform-specific traceback details are excluded from comparison; see [the repeated-SIGINT receipt](maintainers/uvicorn-0.54.0-contract.md#actual-repeated-sigint-shutdown-with-an-active-request). A local reload input with `--workers 2` passes both without `watchfiles` (candidate `StatReload`) and with `watchfiles==1.3.0`; each detects a changed Python module, returns the new response, compares Uvicorn's warning that the worker count is ignored, and shuts down on SIGINT. A selected filter input passed 1/1: `--reload-exclude ignored.txt` suppresses that file's reload, while `--reload-include '*.txt'` reloads when `included.txt` changes. Repeated restart/failure policy, other worker-control signals, other filter combinations, Windows and other socket/platform combinations are not qualified. |
| Claim a general speed advantage | Not supported by current measurements. See [benchmark results](benchmark-results.md). |

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
