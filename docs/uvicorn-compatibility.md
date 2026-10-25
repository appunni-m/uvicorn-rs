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
| Run `uvicorn` from this checkout | Help, version, and selected input checks match the pinned Uvicorn release; console-process inputs verify current-directory app import resolution and startup with selected h11/TLS settings. The current CLI input index has 54 cases. A historical 38-case snapshot had 36 grouped passes plus two same-digest receipts; focused inputs for invalid `UVICORN_LIMIT_CONCURRENCY`, invalid `--log-level`, and invalid protocol/interface selectors passed against the oracle. Selected startup cases confirm explicit `--host 127.0.0.1` and `--port 0` override malformed `UVICORN_HOST` and `UVICORN_PORT` and an env-file value reaches the app factory when the process variable is absent. See [parity results](parity.md) for source and input digests. The CLI accepts `--http h11` and `--http httptools` by routing to the Rust-native HTTP engine, plus `--ws websockets-sansio`, `--no-access-log`, and both color switches. Focused Python API parity verifies default per-message-deflate negotiation and compressed text echo, plus explicit disablement; this does not cover TLS or all extension parameters and fragmentation behavior. Color behavior is compared through startup, an HTTP request, and shutdown. Two HTTP/1.1 cases compare inherited and reset `contextvars` behavior with Uvicorn 0.54.0. The `h11` and `httptools` inputs each send an ordinary POST through the selected backend. Parser-specific malformed-request behavior is not established. These finite cases do not establish every runtime option, full CLI parity, or complete environment behavior. |
| Import `uvicorn` from this checkout | `run`, `Config`, `Server`, `Server.run()`, and `Server.serve()` expose Uvicorn 0.54.0 signatures. The focused import/signature case includes the documented logging formatters and `ServerState` paths; it compares the deprecated `uvicorn.main.ServerState` warning. Focused cases cover single-process HTTP serving, selected lifecycle behavior, the `root_path` ASGI scope contract, `lifespan="off"`, `uvicorn.run(ws_max_size=...)`, acceptance of `uvicorn.run(ws_max_queue=...)` on the auto/SansIO path, `uvicorn.run(reset_contextvars=True)` for HTTP requests, concurrency-limit responses, the selected asyncio loop through `Config`/`Server.run()`, warning-level logging through `uvicorn.run()`, custom INI/JSON/YAML logging through `uvicorn.run(log_config=...)`, and access-log suppression through `uvicorn.run(access_log=False)`. Direct `Config.load()` comparisons now cover invalid HTTP and WebSocket import selectors and the HTTP/2 auto-backend error; these three cases passed against Uvicorn 0.54.0. The module CLI also passes warning-level logging, `UVICORN_LOG_LEVEL=debug`, explicit `--log-level warning` precedence over that environment value, custom INI/JSON/YAML logging with `--log-config` and `UVICORN_LOG_CONFIG`, `--no-access-log`, and a SansIO `--ws-max-queue` app-load diagnostic comparison. The API matrix also includes password-protected PKCS#8 key loading through Config/Server and the module CLI, using one AES-256-CBC/PBKDF2-HMAC-SHA1 fixture. Runtime state-field updates, other levels, other precedence combinations, and most settings/lifecycle behavior remain unqualified. |
| Serve a Python ASGI app | An ASGI 3 prototype is available. See the [support matrix](support-matrix.md) for tested behavior and limits. |
| Use Uvicorn workers, reload, or process controls | Two focused module-CLI cases start two workers through `--workers 2` and `WEB_CONCURRENCY=2`, serve a request, and shut down on SIGINT against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. A third case sets `--workers 2` with `WEB_CONCURRENCY=3`; both implementations log exactly two worker starts, confirming the explicit CLI value takes precedence (selected run `1b050929c5ab433cbe647683c100f5b1`; details in the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#explicit-worker-count-precedence)). A selected POSIX case also compares replacement after one worker stops answering health checks; it passed 1/1 with a non-default 2-second timeout (run `ae4e43b0e69245a8b22cd67668cdaeba`, report SHA-256 `eae083b94d0d0637b0005fa9278066b48b52f787f93b06c3e58113270a602e1e`). The new two-worker SIGTERM shutdown case also passed 1/1 on the local dirty draft on macOS 15.7.7 ARM64 / CPython 3.12.13; both sides served HTTP 200, logged SIGTERM, and exited 0 (run `51cd568a8d5848e2ab90157c9abad3fe`; see [receipt details](maintainers/uvicorn-0.54.0-contract.md#two-worker-sigterm-shutdown)). A local reload input with `--workers 2` passes both without `watchfiles` (candidate `StatReload`) and with `watchfiles==1.3.0`; each detects a changed Python module, returns the new response, compares Uvicorn's warning that the worker count is ignored, and shuts down on SIGINT. A selected filter input passed 1/1: `--reload-exclude ignored.txt` suppresses that file's reload, while `--reload-include '*.txt'` reloads when `included.txt` changes. Repeated restart/failure policy, other worker-control signals, other filter combinations, Windows and other socket/platform combinations are not qualified. |
| Claim a general speed advantage | Not supported by current measurements. See [benchmark results](benchmark-results.md). |

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
