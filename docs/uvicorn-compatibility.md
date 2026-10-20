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
| Run `uvicorn` from this checkout | Help, version, and selected input checks match the pinned Uvicorn release; the CLI accepts `--http httptools` and `--ws websockets-sansio`. Most runtime options and environment behavior remain incomplete. |
| Import `uvicorn` from this checkout | `run`, `Config`, and `Server` expose Uvicorn 0.54.0 signatures. Focused parity covers single-process HTTP serving, selected lifecycle behavior, `root_path`, `lifespan="off"`, `uvicorn.run(ws_max_size=...)`, and concurrency-limit responses through both `uvicorn.run()` and `Config`/`Server.run()`; most settings and lifecycle behavior remain unqualified. |
| Serve a Python ASGI app | An ASGI 3 prototype is available. See the [support matrix](support-matrix.md) for tested behavior and limits. |
| Use Uvicorn workers, reload, or process controls | Not implemented or qualified as compatible. |
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
