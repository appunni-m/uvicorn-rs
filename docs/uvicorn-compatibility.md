# Can I replace Uvicorn?

**Not yet.** `uvicorn-rs-py` is not published, and the current prototype does
not match Uvicorn's full command, Python API, or deployment behavior. If an
application relies on those features, keep using upstream Uvicorn. You can
[try the current prototype from a checkout](quickstart.md) without changing
your application environment.

## Current status

| What you need | Current state |
| --- | --- |
| Install from PyPI | Not available. `uvicorn-rs-py` has not been published. |
| Run `uvicorn` from this checkout | Help, version, and selected input checks match the pinned Uvicorn release; a console-process input verifies current-directory app import resolution. The CLI accepts `--http h11` and `--http httptools` by routing to the Rust-native HTTP engine, plus `--ws websockets-sansio`, `--no-access-log`, and both color switches. Color behavior is compared through startup, an HTTP request, and shutdown. Two HTTP/1.1 cases compare inherited and reset `contextvars` behavior with Uvicorn 0.54.0. One ordinary POST is compared with Uvicorn's h11 backend; parser-specific malformed-request behavior is not established. Most runtime options and environment behavior remain incomplete. |
| Import `uvicorn` from this checkout | `run`, `Config`, and `Server` expose Uvicorn 0.54.0 signatures. Focused cases cover single-process HTTP serving, selected lifecycle behavior, the `root_path` ASGI scope contract, `lifespan="off"`, `uvicorn.run(ws_max_size=...)`, acceptance of `uvicorn.run(ws_max_queue=...)` on the auto/SansIO path, `uvicorn.run(reset_contextvars=True)` for HTTP requests, concurrency-limit responses, the selected asyncio loop through `Config`/`Server.run()`, warning-level logging through `uvicorn.run()`, custom INI/JSON/YAML logging through `uvicorn.run(log_config=...)`, and access-log suppression through `uvicorn.run(access_log=False)`. The module CLI also passes warning-level logging, `UVICORN_LOG_LEVEL=debug`, explicit `--log-level warning` precedence over that environment value, custom INI/JSON/YAML logging with `--log-config` and `UVICORN_LOG_CONFIG`, `--no-access-log`, and a SansIO `--ws-max-queue` app-load diagnostic comparison. Other levels, other precedence combinations, and most settings/lifecycle behavior remain unqualified. |
| Serve a Python ASGI app | An ASGI 3 prototype is available. See the [support matrix](support-matrix.md) for tested behavior and limits. |
| Use Uvicorn workers, reload, or process controls | Two focused module-CLI cases start two workers through `--workers 2` and `WEB_CONCURRENCY=2`, serve a request, and shut down on SIGINT against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. A local reload input with `--workers 2` passes both without `watchfiles` (candidate `StatReload`) and with `watchfiles==1.3.0`; each detects a changed Python module, returns the new response, compares Uvicorn's warning that the worker count is ignored, and shuts down on SIGINT. Worker crash recovery, health-check expiry, worker-count signals, reload filters, other reload/worker combinations, and other socket/platform combinations are not qualified. |
| Claim a general speed advantage | Not supported by current measurements. See [benchmark results](benchmark-results.md). |

The target distribution is `uvicorn-rs-py`. After release, it is intended to
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
python -m pip install "uvicorn-rs-py[standard]"
uvicorn --help
python -m uvicorn --help
```

To roll back, install the upstream version your application requires:

```sh
python -m pip uninstall uvicorn-rs-py
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
