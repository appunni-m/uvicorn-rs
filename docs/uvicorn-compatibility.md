# Uvicorn replacement status

This page describes the intended replacement contract and the current gap. It does not claim that the prototype already behaves like Uvicorn.

## Confirmed target

The Python distribution remains named uvicorn-rs-py. Once the compatibility work and release checks pass, installing that distribution is intended to provide the uvicorn command and uvicorn import namespace. The Rust server remains the network engine; Python compatibility code should stay thin.

The initial compatibility baseline is upstream Uvicorn 0.54.0, pinned in this repository's benchmark dependencies. Compatibility claims will name the exact tested upstream version and supported Python/OS combinations. A future Uvicorn release is not covered automatically; the project must review and adopt each new baseline explicitly.

See the [Uvicorn 0.54.0 release notes](https://github.com/Kludex/uvicorn/blob/0.54.0/docs/release-notes.md) and [settings reference](https://github.com/Kludex/uvicorn/blob/0.54.0/docs/settings.md) for the upstream contract.

## What is available today

| User-visible surface | Current state |
| --- | --- |
| PyPI distribution | uvicorn-rs-py is the intended distribution name; no package has been published. |
| Command | The checkout exposes uvicorn-rs-py with a small custom option set. It does not install the uvicorn command. |
| Python imports | The checkout exposes uvicorn_rs.Server. It does not provide the uvicorn import namespace or uvicorn.run, Config, or Server API. |
| ASGI app | The prototype serves an ASGI 3 callable through the Python-owned event loop and Rust networking. See the [live support matrix](support-matrix.md) for tested behavior. |
| Uvicorn compatibility | Full CLI, import/API, worker, reload, and process parity has not been implemented or qualified. |

Generic ASGI request parity does not prove Uvicorn CLI or Python API compatibility. Until the installed artifact passes the declared compatibility matrix, keep using upstream Uvicorn when an application depends on its public imports or options.

## Planned replacement workflow

These are the intended steps after a compatible release is available. They are not install instructions for the current prototype.

~~~sh
python -m pip uninstall uvicorn
python -m pip install uvicorn-rs-py
uvicorn --help
~~~

The distributions would install overlapping uvicorn files. Remove upstream Uvicorn before installing uvicorn-rs-py, and do not keep both installed in the same environment.

To return to the pinned upstream baseline:

~~~sh
python -m pip uninstall uvicorn-rs-py
python -m pip install "uvicorn==0.54.0"
~~~

A rollback should use the upstream version required by the application; 0.54.0 is the project's initial compatibility reference, not a promise that it is the latest upstream version forever.

## What compatibility means

The target inventory includes command help, options, defaults, environment-variable precedence, exit codes and diagnostics; documented imports and signatures; application strings, objects and factories; ASGI3, ASGI2 and WSGI interfaces; HTTP and WebSocket behavior; TLS, proxy and socket configuration; lifespan, cancellation and graceful shutdown; workers, reload and signals; and package extras.

A surface is supported only when its exact versioned input case passes against live upstream Uvicorn and the installed uvicorn-rs-py artifact. Missing cases, unsupported options, or observable differences remain visible in the [support matrix](support-matrix.md) and block a drop-in claim.
