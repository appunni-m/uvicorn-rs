# Uvicorn 0.54.0 compatibility contract

This page is the maintainer source map for the Uvicorn replacement work. It
records the upstream public surface, where it comes from, the current
uvicorn-rs-py gap, the Kata owner for implementation, and the parity evidence
route. It is version scoped; it does not claim that uvicorn-rs-py is currently
a drop-in replacement.

## Pinned authority

The baseline is the upstream Uvicorn `0.54.0` tag at commit
[`3eb9a9ab9af69005c687728097461c1fd2a95db9`](https://github.com/Kludex/uvicorn/tree/3eb9a9ab9af69005c687728097461c1fd2a95db9).
The repository's `uvicorn-oracle` dependency group and
`tests/parity/manifest.json` both pin Uvicorn 0.54.0.
`scripts/run_parity.py` checks the installed distribution and components
against the manifest versions. A baseline update must change the
dependency lock, oracle version, source revision here, and the relevant parity
inputs together; an upstream release does not silently change this contract.

Authority files:

| Surface | Uvicorn 0.54.0 authority |
| --- | --- |
| CLI, environment defaults, and option text | [`uvicorn/main.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/main.py), [`docs/settings.md`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/docs/settings.md) |
| `run`, `Config`, app loading, TLS, logging, and protocol choices | [`uvicorn/config.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/config.py), [`uvicorn/main.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/main.py) |
| Server lifecycle, signals, and graceful shutdown | [`uvicorn/server.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/server.py), [`docs/server-behavior.md`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/docs/server-behavior.md) |
| Public imports, programmatic use, workers, and deployment | [`uvicorn/__init__.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/__init__.py), [`docs/index.md`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/docs/index.md), [`docs/deployment/index.md`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/docs/deployment/index.md) |
| Package, Python floor, entry point, and extras | [`pyproject.toml`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/pyproject.toml) |

## Public command and settings

The upstream console script is `uvicorn = uvicorn.main:main`. `python -m
uvicorn` invokes the same command. Click supplies `--help`, `--version`, input
validation, environment-variable binding, and exit behavior. There are 52
declared Click parameters, including the required `APP` argument; `--help` is
provided by Click rather than declared as an application parameter.

| Area | Uvicorn 0.54.0 public inputs | Defaults and behavior to preserve | Implementation / evidence owner |
| --- | --- | --- | --- |
| App selection | `APP`, `UVICORN_APP`, `--factory`, `--app-dir`, `--reset-contextvars` | `APP` is required unless supplied by env; factory false; app-dir is empty and adds a leading import path; context reset false. Missing-module and missing-attribute import diagnostics have focused cases. | `1s4z`, `9kbx`, `4fvf` |
| Binding | `--host`, `--port`, `--uds`, `--fd`, `--backlog` | `127.0.0.1`, `8000`, `None`, `None`, `2048`. Five live cases cover module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two IPv4 TCP listeners. | `python-api.module-cli-serves-request-on-inherited-fd`, `python-api.run-serves-request-on-inherited-fd`, `python-api.config-server-serves-request-on-inherited-fd`, `python-api.server-serves-request-on-prebound-socket`, `python-api.server-serves-request-on-multiple-prebound-sockets`; Kata owners: `9kbx`, `dhfq`, `4fvf` |
| Reload | `--reload`, repeatable `--reload-dir`, `--reload-include`, `--reload-exclude`, `--reload-delay` | false; no explicit dirs; includes/excludes are unset; `0.25` seconds. With no watcher package, file polling behavior is narrower. If reload and multiple workers are both set, Uvicorn warns that workers are ignored while reloading. | `dhfq`, `9kbx`, `4fvf` |
| Workers and process lifetime | `--workers`, `--timeout-worker-healthcheck`, `--limit-max-requests`, `--limit-max-requests-jitter`, `--timeout-graceful-shutdown` | workers unset, then `WEB_CONCURRENCY` or one; healthcheck `5`; request limit unset; jitter `0`; graceful timeout unset. Reload and workers are mutually exclusive. Signal handling includes SIGINT and SIGTERM, SIGBREAK on Windows, and supervisor-specific SIGHUP/SIGTTIN/SIGTTOU behavior where available. | `dhfq`, `dv25`, `4fvf` |
| Event loop | `--loop` | `auto`; documented choices are `auto`, `asyncio`, `uvloop`, and `zuvloop`. The API also accepts `none` and import paths. Optional implementations have platform/runtime restrictions. | `dv25`, `9kbx`, `4fvf` |
| HTTP | `--http`, `--http2`, `--h11-max-incomplete-event-size` | `auto`, false, and 16 KiB effective h11 limit. Documented HTTP backends are `auto`, `h11`, `httptools`, and experimental `zttp`; HTTP/2 requires `zttp`. | `dv25`, `9kbx`, `4fvf` |
| WebSockets | `--ws`, `--ws-max-size`, `--ws-max-queue`, `--ws-ping-interval`, `--ws-ping-timeout`, `--ws-per-message-deflate` | `auto`, 16 MiB, 32, 20 s, 20 s, true. Backends include `none`, `websockets`, `websockets-sansio`, and `wsproto`; queue and compression support depend on backend. | `dv25`, `9kbx`, `4fvf` |
| Lifespan and interface | `--lifespan`, `--interface` | both `auto`; lifespan choices are `auto`, `on`, `off`; interface choices are `auto`, `asgi3`, `asgi2`, `wsgi`. Uvicorn's native WSGI implementation is deprecated. | `dv25`, `4fvf` |
| App environment | `--env-file`, `Config(env_file=...)`, `run(env_file=...)` | unset; loads environment for the app before app import/factory invocation. `UVICORN_*` server settings are not loaded from this file. The module CLI and programmatic factory paths have focused parity cases; broader dotenv syntax and precedence remain unverified. | `9kbx`, `gjpr`, `4fvf` |
| Logging | `--log-config`, `--log-level`, `--access-log` / `--no-access-log`, `--use-colors` / `--no-use-colors` | Selected default startup, access, shutdown, and concurrency-limit warning events are compared for `uvicorn.run()`, `Config`/`Server.run()`, and module CLI requests. `python-api.run-applies-numeric-warning-log-level` verifies that API level 30 filters application DEBUG/INFO events while retaining WARNING and above; module CLI cases verify that `--log-level warning` suppresses startup/access INFO events, `UVICORN_LOG_LEVEL=debug` enables DEBUG application logs, and an explicit warning option overrides that debug environment value. `python-api.run-disables-access-log` and `python-api.module-cli-disables-access-log` verify access-log suppression while retaining other normalized lifecycle events. Custom JSON, INI, and YAML formatter cases compare through both public entry points; the YAML cases run with PyYAML from the benchmark dependency group, matching the package's `[standard]` extra. `python-api.module-cli-uses-log-config-from-environment` confirms that `UVICORN_LOG_CONFIG` overrides the built-in setting. Raw child logs remain in result artifacts; other levels, precedence combinations, color combinations, and exact traceback frames remain unverified. | `9kbx`, `gjpr`, `4fvf` |
| Proxy and response headers | `--proxy-headers` / `--no-proxy-headers`, `--forwarded-allow-ips`, `--server-header` / `--no-server-header`, `--date-header` / `--no-date-header`, repeatable `--header` | proxy/server/date headers true; trusted IPs default from `FORWARDED_ALLOW_IPS` or `127.0.0.1,::1`; the selected `uvicorn.run()` case verifies that an explicit API argument overrides the environment value | `9kbx`, `dv25`, `4fvf` |
| Request/resource limits | `--root-path`, `--limit-concurrency`, `--limit-max-requests`, `--limit-max-requests-jitter`, `--timeout-keep-alive` | Empty root path; concurrency and request limit unset; jitter `0`; keep-alive `5` seconds. HTTP/1.1 target contract inputs cover ASCII `root_path` through the API and module CLI; they validate all three relevant ASGI scope values against explicit expectations and compare exit code, response receipt, shutdown signal, and timeout state with Uvicorn. Uvicorn 0.54.0 adds the configured prefix to `raw_path`, so response-body parity is not claimed for these cases. A separate case covers percent-encoded UTF-8 request-path decoding with an empty root path. A target conformance case checks Unicode `root_path` and original `raw_path` bytes; Uvicorn 0.54.0 rejects the Unicode prefix before ASGI invocation. HTTP/1.1 CLI, `uvicorn.run(limit_concurrency=1)`, and `Config`/`Server.run()` inputs verify the 503 behavior at limit 1. `cli.limit-max-requests-zero-exits-after-startup` checks the zero threshold, and `python-api.module-cli-limit-max-requests-exits-after-one-response` verifies one-request natural shutdown through `UVICORN_LIMIT_MAX_REQUESTS=1`; both match Uvicorn 0.54.0. `python-api.module-cli-limit-max-requests-jitter-stays-in-configured-range` checks that jitter 1 with a base limit of 2 exits naturally after 2 or 3 responses, preserving per-run counts but comparing the range rather than the randomized count. Negative jitter timing/message behavior remains unverified. `python-api.module-cli-timeout-keep-alive-closes-idle-connection` verifies that a one-second timeout closes an idle HTTP/1 connection after a two-second wait; concurrent request-limit behavior, TLS, HTTP/2/HTTP/3, other timeout values, and other request-limit values remain unverified. Backlog controls the OS accept queue. | `9kbx`, `dv25`, `4fvf` |
| TLS | `--ssl-keyfile`, `--ssl-certfile`, `--ssl-keyfile-password`, `--ssl-version`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers` | no files/password; `ssl.PROTOCOL_TLS_SERVER`; `ssl.CERT_NONE`; no CA file or explicit cipher list. Programmatic API also accepts `ssl_context_factory`. | `9kbx`, `dv25`, `4fvf` |
| Command output | `--help`, `--version`, Click parse errors, missing/invalid app errors | version output includes Uvicorn version, Python implementation/version, and OS; startup failure uses exit status 3. Exact help/error text and stream placement are parity obligations. | `9kbx`, `4fvf` |

Click's `auto_envvar_prefix="UVICORN"` binds command parameters such as
`--host` to `UVICORN_HOST`; the app argument explicitly uses `UVICORN_APP`.
Explicit CLI values override environment values. Other independently consumed
environment variables are `WEB_CONCURRENCY`, `FORWARDED_ALLOW_IPS`, and, for
watchfiles reload, `WATCHFILES_FORCE_POLLING`. These are separate from the
`UVICORN_*` prefix rule.

The eleven focused HTTP/1.1 cases `http1.proxy-headers-trusted-client-and-scheme`,
`http1.proxy-headers-disabled-ignores-forwarded-values`,
`http1.proxy-headers-untrusted-peer-ignores-forwarded-values`,
`http1.proxy-headers-wildcard-trust-uses-first-forwarded-client`,
`http1.proxy-headers-cidr-trust-selects-first-untrusted-forwarded-client`,
`http1.proxy-headers-malformed-forwarded-host-remains-opaque`, and
`http1.proxy-headers-empty-forwarded-for-preserves-peer`, and
`http1.proxy-headers-all-trusted-chain-selects-first-forwarded-client`, and
`http1.proxy-headers-duplicate-forwarded-for-fields-join-in-order`, and
`http1.proxy-headers-duplicate-forwarded-proto-last-value-wins`, and
`http1.proxy-headers-uppercase-proto-is-ignored` each pass 1/1 against Uvicorn
0.54.0. The WebSocket proxy cases
`websocket.proxy-https-forwarded-scheme-becomes-wss`,
`websocket.proxy-http-forwarded-scheme-becomes-ws`, and
`websocket.proxy-wss-forwarded-scheme-remains-wss` also pass 1/1. The three
Python API cases
`python-api.run-applies-trusted-proxy-headers`,
`python-api.run-uses-forwarded-allow-ips-environment`, and
`python-api.run-argument-overrides-forwarded-allow-ips-environment` also pass
1/1. The exact-trust HTTP/1.1 case and the trusted Python API case send
`X-Forwarded-For: 198.51.100.25, 127.0.0.1` and
`X-Forwarded-Proto: https` from the loopback peer with an explicit
`127.0.0.1,::1` trust list; both expose client `198.51.100.25` and scheme
`https` to the ASGI app. The disabled case uses the same forwarded values with
proxy handling disabled; the ASGI app observes the direct peer and `http`
scheme. The excluded-peer case keeps proxy handling enabled but uses an
allowlist that excludes the loopback peer, producing the same direct-peer
observation. The wildcard case selects the first forwarded client, and the
`127.0.0.0/8` case trusts the final proxy and selects the first untrusted
forwarded client; both expose `198.51.100.25` and scheme `https`. The
malformed-host case places `not-an-ip` between the untrusted client and trusted
loopback proxy; both retain it as the reported client host with scheme `https`.
The empty forwarded-client case sends an empty `X-Forwarded-For` value from a
trusted peer; both keep the direct peer as the client and set scheme `https`.
The all-trusted chain uses a trust list containing both forwarded addresses;
both select the first address as the client and report scheme `https`.
The duplicate-field case sends client and proxy addresses in separate
`X-Forwarded-For` fields; both join them in field order and select the client
address.
The duplicate-protocol case sends `http` then `https`; both apply the last
`X-Forwarded-Proto` field and expose scheme `https`.
The uppercase-protocol case sends `HTTPS`; both ignore the unsupported token
and retain the default HTTP scope scheme.
The WebSocket proxy cases verify that forwarded `https` becomes `wss`,
forwarded `http` becomes `ws`, and explicit forwarded `wss` remains `wss` in
the ASGI scope.
The environment-default API case sets `FORWARDED_ALLOW_IPS=192.0.2.1` and omits
the API argument, so both retain the direct peer and `http` scheme. The
override case uses the same environment value but passes
`forwarded_allow_ips="127.0.0.1,::1"`; both expose the forwarded client and
`https` scheme. Other address/network combinations, other malformed
`X-Forwarded-For` forms, broader environment precedence, and other WebSocket
forwarded-protocol values remain unverified.

## Python import and callable surface

The upstream package declares `__all__ = ["main", "run", "Config", "Server"]`.
The documented primary APIs are `uvicorn.run(app, **config)`,
`uvicorn.Config(app, ...)`, `uvicorn.Server(config).run()`, and
`await uvicorn.Server(config).serve()` inside an existing event loop. The
exact source signatures are authoritative and intentionally long:

- `uvicorn.run`: 52 parameters. `app` is positional-or-keyword; all remaining
  parameters are keyword-only. It covers the settings in the table plus the
  `ssl_context_factory` callable.
- `uvicorn.Config.__init__`: 53 parameters, with positional-or-keyword
  configuration. It covers the same settings, plus `timeout_notify=30` and
  `callback_notify=None` used by server integrations.
- `uvicorn.Server.__init__(config: Config)`: one required argument.
- `uvicorn.Server.run(sockets: list[socket.socket] | None = None) -> None` and
  `uvicorn.Server.serve(sockets: list[socket.socket] | None = None) -> None`.

The `run` parameter names, in declaration order, are `app`, `host`, `port`,
`uds`, `fd`, `loop`, `http`, `http2`, `ws`, `ws_max_size`, `ws_max_queue`,
`ws_ping_interval`, `ws_ping_timeout`, `ws_per_message_deflate`, `lifespan`,
`interface`, `reload`, `reload_dirs`, `reload_includes`, `reload_excludes`,
`reload_delay`, `workers`, `env_file`, `log_config`, `log_level`, `access_log`,
`proxy_headers`, `server_header`, `date_header`, `forwarded_allow_ips`,
`root_path`, `limit_concurrency`, `backlog`, `limit_max_requests`,
`limit_max_requests_jitter`, `timeout_keep_alive`,
`timeout_graceful_shutdown`, `timeout_worker_healthcheck`, `ssl_keyfile`,
`ssl_certfile`, `ssl_keyfile_password`, `ssl_version`, `ssl_cert_reqs`,
`ssl_ca_certs`, `ssl_ciphers`, `ssl_context_factory`, `headers`, `use_colors`,
`app_dir`, `factory`, `h11_max_incomplete_event_size`, and
`reset_contextvars`. `Config.__init__` has the same names plus
`timeout_notify` and `callback_notify`; its declared order is in the pinned
[`config.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/config.py).

The documented compatibility surface also includes `uvicorn.workers` worker
classes (deprecated upstream), the `uvicorn.logging` formatters referenced by
default/custom logging configuration, and deprecated `uvicorn.main.ServerState`.
These paths must be intentionally supported or explicitly reported as
unsupported; internal protocol implementation modules are not automatically a
public compatibility promise.

Uvicorn 0.54.0 declares Python `>=3.10`, the `uvicorn` console script, required
dependencies `click`, `h11`, and (before Python 3.11) `typing_extensions`, plus
the `standard` extra: `httptools`, `python-dotenv`, `PyYAML`, `uvloop`,
`watchfiles`, and `websockets`. Upstream classifiers include CPython and PyPy;
uvicorn-rs-py's compiled-extension support is a separate target constraint and
must be reported per supported Python/OS combination.

## Lifecycle, failures, and network behavior

These are user-visible contracts that the command/API cases must cover in
addition to parsing the same settings. The pinned sources are
[`server.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/server.py),
[`config.py`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/config.py),
and [`docs/server-behavior.md`](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/docs/server-behavior.md).

| Contract | Uvicorn behavior to observe | Owner / parity route |
| --- | --- | --- |
| App target and factory | `module:attribute` import; optional no-argument factory; import/load failures and invalid factory results are visible during startup. Reload/workers require an import string; passing an object emits a warning and exits with startup-failure status 3. | `9kbx`, `gjpr`, `4fvf` |
| ASGI interface and lifespan | Auto-detect, explicit ASGI3, ASGI2 adapter, or deprecated WSGI; lifespan can be auto/on/off. Startup/shutdown events, state propagation, failures, and supported ASGI extensions are externally visible. | `dv25`, `gjpr`, `4fvf` |
| HTTP request/response | HTTP/1.1 protocol choice; header normalization/defaults; keep-alive; `Connection: close`; Content-Length validation; chunking; HEAD body suppression; response-start commitment; invalid ASGI message order; application exception before/after response commitment. | `dv25`, `4fvf` |
| Streaming and disconnect | Read and write flow control apply high/low-water backpressure. After a response completes, later request-body reads yield `http.disconnect`. `Expect: 100-Continue` is acknowledged only when the application receives the body. | `dv25`, `4fvf` |
| Resource behavior | Concurrency excess is refused with HTTP 503 after request headers; backlog limits the OS accept queue and does not queue refused application work. Max requests terminates a worker and is intended for a process supervisor. | `dv25`, `dhfq`, `4fvf` |
| Shutdown and signals | SIGINT/SIGTERM start graceful shutdown; a second SIGINT can force exit. Existing responses and background tasks are drained within the graceful timeout. UDS paths created by the process are removed on exit. Worker/reloader parents have distinct signal and child-process behavior. | `dv25`, `dhfq`, `4fvf` |
| Startup and CLI failures | Click usage/argument errors, app import errors, bind/TLS failures, lifespan startup failure, and server-not-started outcomes have distinct diagnostics and exit behavior. Uvicorn's startup-failure status is 3; Click parse failures use Click's command error behavior. | `9kbx`, `gjpr`, `4fvf` |
| Operator logs | `uvicorn.error` and `uvicorn.access` are separately configurable; custom logging config accepts dict/JSON/YAML and fileConfig formats; warnings and exception traces are observable output. Selected default log events now have input-driven parity checks; custom configuration and exact traceback frame formatting remain open. | `9kbx`, `gjpr`, `4fvf` |

The ASGI protocol inputs in `tests/parity/manifest.json` cover only some rows
above. The manifest now also has a narrow CLI process slice; Python API and
import/signature, most settings and environment combinations, process/socket,
and package-replacement cases remain incomplete. `4fvf` owns expanding the
input-only parity system, with implementation work split across the owners in
the evidence map below.

## Current implementation and evidence map

| Surface | Current uvicorn-rs-py state | Owner | Required parity route |
| --- | --- | --- | --- |
| Distribution and `uvicorn` command/import namespace | The source package keeps distribution metadata `uvicorn-rs-py` version `0.1.0`, Python `>=3.9`, Uvicorn-style base dependencies, and a `[standard]` extra. `uvicorn.__version__` reports the pinned Uvicorn compatibility baseline `0.54.0`. The wheel includes both Python namespaces and the `uvicorn-rs-py` and `uvicorn` entry points. A local macOS ARM64 wheel passed the CPython 3.9.6 consumer smoke and CPython 3.12 install/replace/rollback check; this is one-host evidence. The distribution is unpublished, and full package and runtime parity remain incomplete. | `1s4z` | Input cases compare installed distribution metadata/imports, entry points, module and console commands, and executable behavior with upstream 0.54.0. |
| CLI/settings/environment | The compatibility namespace uses Click option metadata adapted from Uvicorn 0.54.0. The indexed CLI process set has 28 cases: help/version, validation, app selection and loading, current-directory import resolution from the installed console command, worker-option normalization, selected protocol options, `--root-path`, environment-file behavior, response-header policy, and `--limit-max-requests 0` startup shutdown. Python API inputs also drive module CLI limit settings through `UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER`. A separate HTTP/1.1 protocol input compares `--limit-concurrency 1` 503 responses. Two Python API inputs now check two-worker module-CLI request and shutdown using explicit `--workers 2` and `WEB_CONCURRENCY=2`; other worker supervision and option effects remain unverified. Unsupported selected settings fail instead of being silently ignored. | `9kbx` | Extend `tests/parity/inputs/cli.json`; invoke both module and console paths with matching argv/env/cwd/files and compare exit status, stdout, stderr, and listener/app behavior. |
| `run`, `Config`, and `Server` API | `uvicorn.Config`, `uvicorn.Server(config)`, and `uvicorn.run` expose the pinned signatures. Focused comparisons cover default ASGI3 serving, successful ASGI3 application-factory serving through both the programmatic API and module CLI, ASGI2 auto-detection and explicit selection, WSGI GETs through `uvicorn.run()` and the module CLI with `lifespan="off"` and `lifespan="auto"`, lifespan, the `root_path` ASGI scope contract, environment files, custom headers, readiness, startup-failure state, concurrency-limit responses, single-worker acceptance of a non-default healthcheck timeout, `WEB_CONCURRENCY=0` selecting one in-process server, request-limit zero/positive/jitter natural-shutdown behavior through the module CLI, warning-level filtering, `UVICORN_LOG_LEVEL=debug` and explicit CLI precedence over that environment value, custom JSON, INI, and YAML logging configuration through `uvicorn.run()` and the module CLI, two-worker module-CLI request and SIGINT shutdown with explicit `--workers 2` and `WEB_CONCURRENCY=2`, and selected SIGINT shutdown outcomes. The input set contains 51 ordinary HTTP-run, two request-limit, and two concurrency cases. WSGI auto-mode cases compare the unsupported-lifespan fallback with no logging, configured logging, and default module-CLI logging; all five WSGI request cases check method, path, query, and request-header mapping. The three auto-mode cases and the two `lifespan="off"` cases pass individually against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. Advanced Config settings, WSGI request-body/streaming/error behavior, other strict-mode failure classes, other log levels and precedence combinations, inherited-listener variants beyond two IPv4 TCP sockets and plain HTTP/1.1 UDS, and broader lifecycle behavior remain unverified. The two-listener case passed on macOS ARM64 / CPython 3.12.13. | `gjpr` | `tests/parity/inputs/python-api.json` compares public imports, signatures, selected run behavior, custom headers, environment-file loading, successful application-factory loading through both entry points, ASGI/WSGI interface handling, resource-limit responses, logging configuration, lifecycle observations, and normalized log events against upstream Uvicorn. |
| HTTP, WebSocket, lifespan, ASGI and errors | The current Rust server has an input-driven ASGI protocol matrix. Uvicorn is the H1/WebSocket/lifespan oracle; Hypercorn is the current H2/H3 oracle. This is not Uvicorn CLI/API compatibility. | `dv25`, `4fvf` | Extend the existing protocol cases where applicable; preserve the declared reference per protocol and compare public observations. |
| Unix/fd sockets, reload, multi-worker supervision | Seven focused HTTP/1.1 comparisons pass for plain POSIX UDS and inherited IPv4 TCP listeners: UDS through the module CLI and `Config`/`Server`; inherited TCP through module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two listeners. The UDS scope checks `client=None` and `server=(PATH, None)`. Two module-CLI inputs start two workers, selected by `--workers 2` and `WEB_CONCURRENCY=2`, serve a GET, and shut down on SIGINT. Reload and broader worker supervision remain unverified, including worker failure/restart, dynamic worker-count signals, and non-TCP listener combinations. | `dhfq` | Add process-level reload and multi-worker cases, then extend the socket inputs to additional address families, platforms, TLS, and protocols. |
| Package extras and release gates | No published package; current distribution requirements/extras do not mirror the upstream installation contract. | `1s4z`, `v5fe` | Installed-artifact cases and package-content/dependency gates on the supported OS/Python matrix. |

Local CLI verification for code commit
[`6d157fd`](https://github.com/appunni-m/uvicorn-rs/commit/6d157fdc6)
ran the 28 indexed CLI inputs individually against isolated Uvicorn 0.54.0 on
macOS ARM64 / CPython 3.12.13; all 28 passed. A wheel from that source passed
the clean installed-wheel consumer check, including parity of `uvicorn-rs-py`
and `uvicorn` help options and version output. Its SHA-256 was
`84a98faaa78c0d342d13154c82be8ed0138d3617d95ec1d0c595d34e80904f31`. This is
local evidence for the listed cases and consumer checks, not full CLI parity
or cross-platform validation.

`tests/parity/manifest.json` describes the ASGI protocol slice, a focused CLI
process slice, and the public Python import/signature probe. Twenty-eight CLI
inputs cover module/console help and version; argument validation and selected
environment precedence; current-directory and `--app-dir` import resolution;
factory and env-file startup behavior; `UVICORN_APP` selection; HTTP and
WebSocket selector acceptance; SansIO WebSocket size/queue settings; worker
normalization; and the single-process worker-healthcheck behavior. The selector
cases check diagnostic ordering rather than parser-specific protocol behavior.
They do not establish all settings, reload, the full worker-control contract,
or the full command contract. The Python API
inputs also include `python-api.run-loads-env-file-before-factory`, which
compares `uvicorn.run(..., env_file=..., factory=True)` with the same app-dir
and environment file as the module CLI case, and
`python-api.run-applies-custom-default-response-header` plus
`python-api.run-preserves-custom-default-header-value-order`, which check
delivery and duplicate value order for `uvicorn.run(headers=[(name, value)])`,
and `python-api.run-auto-detects-asgi2-callable` plus
`python-api.run-explicit-asgi2-interface`, which compare API startup through
Uvicorn's auto-detection and explicit interface selection. The two
`python-api.module-cli-*asgi2*` cases exercise the same modes through
`python -m uvicorn`.
The matrix covers successful factory serving through both the programmatic
API and module CLI. The two-worker module-CLI cases verify a successful HTTP
request and SIGINT shutdown only; worker recovery, health-check expiry, dynamic
worker-count controls, reload, and package replacement behavior remain
unverified.
Python API inputs introduced `uvicorn-rs-parity/input@11` to include
`root_path`, optional default-header stimuli and observations, and selected
Uvicorn/application interfaces in the declared run request. Schema `@14`
allows HTTP proxy settings and Python API request-header/scope stimuli; later
schemas add environment overrides, WebSocket proxy settings, HTTP
`limit_concurrency` options, and a Python API HTTP-run concurrency stimulus.
They compare public imports/signatures, the
`uvicorn.run()` missing-module diagnostic, a successful default request, an
API request with lifespan disabled, a module CLI request with lifespan
disabled, startup readiness, startup-failure state, and API/module-CLI requests
with an ASCII root path.

The API and CLI root-path inputs use a target contract that checks `root_path`,
decoded `path`, and original request `raw_path` against explicit ASGI
expectations. They compare only exit code, response receipt, shutdown signal,
and timeout state with Uvicorn 0.54.0. For ASCII prefixes, Uvicorn returns HTTP
200 but produces the contract failure body because its `raw_path` includes the
configured prefix. ASGI defines `raw_path` as the original HTTP path component
bytes, excluding the query string ([ASGI HTTP
scope](https://asgi.readthedocs.io/en/stable/specs/www.html#http-connection-scope)).
The separate `python-api.run-http-decodes-non-ascii-request-path` input checks
percent-encoded UTF-8 decoding with an empty `root_path` and compares the
complete response against Uvicorn.

The `python-api.run-http-asgi-raw-path-preserves-unicode-root-path` input adds
a Unicode prefix. Uvicorn 0.54.0 returns HTTP 400 before ASGI invocation
because its HTTP/1.1 implementation encodes `root_path` as ASCII ([pinned
source](https://github.com/Kludex/uvicorn/blob/3eb9a9ab9af69005c687728097461c1fd2a95db9/uvicorn/protocols/http/httptools_impl.py#L261-L262)).
The target accepts `/mounted/应用`, prefixes the decoded `path`, and preserves
the original percent-encoded request path in `raw_path`. This case checks the
target scope and response against explicit ASGI expectations and compares only
the lifecycle fields with Uvicorn; it does not claim response parity.

The four focused receipts below passed individually on clean commit
`352e6700dae4956478e8cb3037bc87d67265670b`, macOS 15.7.7 ARM64, CPython
3.12.13, Rust 1.98.1, and Uvicorn 0.54.0. The target source SHA-256 was
`12b27b055f70fd1ac243e73be0cfb145e16dc1dbdce834bcc8ae4a86544db325`, the
native extension SHA-256 was
`7d75162e3f8e16127452b503ac645b1be8985d922643a6978f4cacc026dae21b`, the
fixture SHA-256 was
`de23457d5d294b2c0127affc587b21209e236e03ac3bf5d26d9a4cf84bfef94a`, and
the Python API input SHA-256 was
`a246103c003e81a554b9c62a34b60ec0e48367fb0902157f2ccf16fed0c0aa63`.

| Input | Receipt | Result |
| --- | --- | --- |
| `python-api.run-http-applies-root-path` | `9264de9848a8450da4cfdc6aaa50858b` | 1/1. Target matches all three ASGI expectations; Uvicorn returns the intentional contract-failure body. |
| `python-api.module-cli-applies-root-path` | `bc118f4d93e741579239107b648fa357` | 1/1, with the same documented `raw_path` divergence. |
| `python-api.run-http-asgi-raw-path-preserves-unicode-root-path` | `958076c562534f9c810bf520bd7e7df3` | 1/1. Target returns HTTP 200 and the expected body; Uvicorn returns HTTP 400 before ASGI invocation. |
| `python-api.run-http-decodes-non-ascii-request-path` | `208d9789ca984d67992e9e2d7fc7751e` | 1/1 with matching HTTP 200 response and scope output. |

All raw receipts are retained under ignored `target/` paths. These focused
cases do not close the remaining settings or lifecycle inventory.

Input schema `@9` was introduced on 2026-10-20 to declare `root_path` in the
`run_http` stimulus. Input schema `@10` added optional default response headers
and selected response-header observations. Schema `@11` adds the Uvicorn
`interface` and application callable shape. The `@9`-to-`@10` and
`@10`-to-`@11` migrators update markers while preserving each case. All indexed
input files carry the same schema identity. Previous full-matrix and
per-case receipts are historical under schema `@8`; regenerate the full
parity matrix against the exact release candidate before using it as a
current release gate. Focused `@9` root-path receipts were generated on
macOS 15.7.7 ARM64 / CPython 3.12.13 from base revision
`9e085cecaed811d68688239ba149854f0c07d094` with a dirty tree, source digest
`2bf372d14ff0b82aad0b8a249a53a2ebfec3c1c8e30574dec25c424f160bd7f3`, and
native extension SHA-256
`3f7e3f8346d84fc8d3be26b2a9fde39f018c6eb40079273a27bc4a3620801cf8`.
Kata `4fvf` owns extending the unified input-only parity system and release
gate for those surfaces. Until the remaining cases are represented and pass,
the support status remains incomplete and the package must not claim a
Uvicorn drop-in replacement.

## Historical focused @9 receipts (2026-10-20)

On macOS 15.7.7 ARM64 / CPython 3.12.13, the previously declared process
inputs passed when run individually against isolated genuine Uvicorn 0.54.0:
14 CLI cases and 9 Python API cases. Two additional CLI cases then passed
individually on the current dirty source: explicit `--workers 1` and
`--workers 0` both preserve the upstream missing-application diagnostic. These
two results used input schema `@9` and clean exact revision
`81ba57c3c930bffbf8e69ed7a4eaa465b6ca6dbf` with source SHA-256
`6eacdf49526598b649b97f05eb7efcd5504b67cb2e51dd42548e951c7ce76ea1` and
native extension SHA-256
`fe0cd0f5d8a4f5e0d158a67c69b8c175d3fbaf63c02dd65955065ad6c794a017`. The
run IDs are `dbf5b55507874d7795cde6eedec1f8f7` and
`51b64155a5b540fcb9e727bb8c6bc6eb`; receipts are
`target/kata-cli-workers-single-81ba.json` and
`target/kata-cli-workers-zero-81ba.json`. They prove these two values are
accepted as the single-process default, not multi-worker supervision. The
earlier receipts share target base
revision `9e085cecaed811d68688239ba149854f0c07d094`, dirty-source digest
`2bf372d14ff0b82aad0b8a249a53a2ebfec3c1c8e30574dec25c424f160bd7f3`, and
native extension SHA-256
`3f7e3f8346d84fc8d3be26b2a9fde39f018c6eb40079273a27bc4a3620801cf8`.
Per-case JSON receipts are retained locally under ignored
`target/kata-cli-*-current.json` and
`target/kata-python-api-*-current.json`.

Two more CLI cases passed individually on a source snapshot based on
`b0b73f617b87f519643aa0a516eed04a39d27b6e`; the tested change is committed
as `4c1546c5700ed0e924e682b87c4b971de833b96b`. Explicit `--http auto` and
`--ws auto` each preserve the upstream missing-application diagnostic. They
ran against isolated Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13,
with input schema `@9` and native extension SHA-256
`fe0cd0f5d8a4f5e0d158a67c69b8c175d3fbaf63c02dd65955065ad6c794a017`. Run IDs:
`87ce62e7b5db4b7c84c0738526e87245` and
`af0a8ab120c24ed88bd1f514b3332863`. The CLI input digest is
`35ad8bc5f362e729a01ba2c557195cd3f66633efc770eb3fc0a24ad333567733`; receipts
are `target/kata-cli-http-auto.json` and `target/kata-cli-ws-auto.json`. These
cases establish acceptance and error precedence for the explicit defaults;
they do not establish serving behavior for the selected protocol backends.

The `@9` case `cli.worker-healthcheck-timeout-is-inert-with-single-process`
also passes individually on macOS 15.7.7 ARM64 / CPython 3.12.13 against
isolated Uvicorn 0.54.0. It sets `--timeout-worker-healthcheck 7` and compares
the missing-application exit code and diagnostic. Uvicorn uses this setting
only in its multi-process supervisor, so the value has no effect on the
single-process server path. The receipt is retained locally at
`target/kata-cli-worker-healthcheck-after.json`; it does not qualify broader
multi-worker behavior.

The `@29` Python API case
`python-api.config-server-accepts-single-worker-healthcheck-timeout` passes
1/1 against isolated Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13.
It starts `Config`/`Server` with `workers=1` and
`timeout_worker_healthcheck=7`, serves a GET with status 200, and shuts down.
The receipt is retained locally at
`target/kata-python-api-single-worker-healthcheck-timeout.json`. This verifies
the single-process API path only; it does not qualify worker supervision.

The `@29` case
`python-api.config-server-web-concurrency-zero-uses-single-process` passes
1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13. With `WEB_CONCURRENCY=0`, both
Uvicorn and the adapter serve the request with status 200 and stop on SIGINT.
The adapter now allows this Uvicorn single-process configuration. The receipt
is retained locally at `target/kata-python-api-web-concurrency-zero.json`;
broader multi-worker supervision remains unverified; the separate two-worker
case covers only request and SIGINT shutdown.

Two individual HTTP/1.1 response-header cases also pass 1/1 against Uvicorn
0.54.0: the default response-header case preserves duplicate value order, and
the header-policy case adds `x-asgi-cli: alpha:beta` while omitting the default
Server and Date fields. These runs used macOS 15.7.7 ARM64 / CPython 3.12.13,
base revision `9e085cecaed811d68688239ba149854f0c07d094`, dirty-source digest
`19e2dea95fe4d2c45322566657a560be192902437ee23761ca97b39d985d6341`, and
native extension SHA-256
`f98bd79f57655bba3d962db87aa3efc0fea64b83488cb3cba77892d238989068`.
Receipts are retained locally under ignored
`target/parity-response-headers-current.json` and
`target/parity-http1-header-policy-current.json`.

A local abi3 wheel built from that dirty source passed the isolated
`scripts/check_replacement_install.py` smoke: clean install exposes the
`uvicorn` imports and console/module commands, and uninstalling the replacement
then reinstalling upstream restores the genuine Uvicorn import and metadata.
The wheel SHA-256 is
`be4eaaf8883f6a087a36befefaaad602eff5fdad3d348cb94573498504acdcde`; its
embedded native extension matches the parity candidate hash above. The wheel
also passed `scripts/check_installed_wheel.py` from a clean CPython 3.12.13
environment. The installed-wheel consumer verified HTTP request handling,
lifespan, caller-loop/thread/context preservation, cancellation propagation,
the installed `uvicorn` console and module commands, TLS 1.3 with HTTP/1.1
ALPN, held-request cancellation on SIGTERM, and lifespan shutdown within its
five-second bound. Its receipt is the ignored
`target/replacement-wheel-consumer.json`; the wheel and check output are local
ignored artifacts.

A separate `@9` rerun on the current dirty checkout passed
`cli.unknown-option-is-rejected` against isolated Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13. Both processes exited 2 with byte-identical stderr
and empty stdout. The run used base revision
`0bd5877529e8f8b7434b7f7ab1852c0753f5e642`, dirty-source digest
`19e2dea95fe4d2c45322566657a560be192902437ee23761ca97b39d985d6341`, and
native extension SHA-256
`f98bd79f57655bba3d962db87aa3efc0fea64b83488cb3cba77892d238989068`. Its
ignored receipt is `target/kata-cli-unknown-option-20261020.json`. This proves
the selected rejection path on this dirty source only; it does not refresh the
other `@9` results or close the CLI/settings inventory.

These results cover the declared narrow CLI/API input sets and install
replacement mechanics only. They do not cover most runtime settings, every
documented import, process supervision, protocols, or the full ASGI matrix.
Because the source was dirty, none of these artifacts is a clean release
candidate or evidence for a drop-in compatibility claim.

## Focused ASGI2 parity (2026-10-20)

The initial comparison reproduced an ASGI2 compatibility gap: upstream Uvicorn
auto-detected the one-argument application as ASGI2 and wrapped it, while the
adapter left `interface="auto"` unchanged and Rust invoked the callable with
three ASGI3 arguments. The adapter now follows Uvicorn's auto-detection and
uses a small Python ASGI2-to-ASGI3 wrapper before calling the Rust server.

All four new input cases pass individually against isolated Uvicorn 0.54.0 on
macOS 15.7.7 ARM64 / CPython 3.12.13:

- `python-api.run-auto-detects-asgi2-callable`
- `python-api.run-explicit-asgi2-interface`
- `python-api.module-cli-auto-detects-asgi2-callable`
- `python-api.module-cli-explicit-asgi2-interface`

Each compares the HTTP response and process shutdown. Receipts are retained
locally under ignored `target/parity-python-api-asgi2*.json`. This proves these
function-based ASGI2 paths only; other callable forms and remaining public API
lifecycle behaviors remain open.

## Focused WSGI parity (2026-10-21)

The five WSGI inputs in `tests/parity/inputs/python-api.json` each pass
individually against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. They issue
a GET with a request header and compare the response containing the WSGI method,
path, query string, and mapped header value. The `lifespan="off"` cases exercise
`uvicorn.run()` and `python -m uvicorn`; the three `lifespan="auto"` cases cover
the programmatic API with logging disabled, the programmatic API with an
explicit logging configuration, and default module-CLI logging. The latter
cases match Uvicorn's INFO fallback diagnostic, including the absence of raw
Rust error output.

This proves a simple request/response path and selected startup-log behavior
through both entry points. The cases do not establish WSGI request-body
handling, response streaming, exception behavior, application factories, or
cross-platform parity. The adapter uses
`a2wsgi` when installed and otherwise falls back to the Uvicorn 0.54.0 WSGI
bridge adapted in `python/uvicorn/middleware/wsgi.py`; Uvicorn itself marks
its native WSGI implementation deprecated.

## Focused WebSocket message-size parity (2026-10-20)

The input case `websocket.configured-max-message-size-closes-oversized-message`
starts both Uvicorn 0.54.0 and uvicorn-rs with `--ws-max-size 4`, sends a
five-byte text message, and requires handshake status 101 followed by close
code 1009. It passes 1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13 with
`websockets` 17.1. Receipt: ignored `target/ws-max-size-parity.json`.

This verifies the explicit CLI setting and the protocol close code for this
input. Server keepalive has a separate focused parity case below. Compression
and WebSockets over HTTP/2 or HTTP/3 remain unverified.

## Programmatic WebSocket message-size parity (2026-10-20)

The Python API input `python-api.run-applies-websocket-message-size-limit`
starts Uvicorn through public `uvicorn.run(ws_max_size=4)`, sends a five-byte
text message, and requires handshake status 101, close code 1009, and no
delivery of the oversized message to the ASGI app. It passes 1/1 against the
Uvicorn 0.54.0 oracle on macOS 15.7.7 ARM64 / CPython 3.12.13. Both child
servers exit cleanly after SIGINT. Receipt: ignored
`target/parity-python-api-ws-size-focused.json`.

This verifies one programmatic Config option path. It does not establish the
other WebSocket settings, compression, WebSockets over HTTP/2 or HTTP/3, or
the broader Python API contract.

## Default SansIO WebSocket queue option (2026-10-21)

Uvicorn 0.54.0's `ws="auto"` selects its SansIO protocol when the standard
`websockets` dependency is installed. That protocol constructs an unbounded
ASGI receive queue and does not read `ws_max_queue`; the legacy `websockets`
protocol does read it. The native adapter therefore accepts the option only
on its auto/SansIO path and does not forward it as a Rust queue limit.

`cli.sansio-ws-size-and-queue-preserve-app-load-diagnostic` passes 1/1 on
macOS ARM64 / CPython 3.12.13 with identical exit code and stderr when
`--ws websockets-sansio`, `--ws-max-size 4`, and `--ws-max-queue 1` are set.
The live Python API case
`python-api.run-applies-websocket-message-size-limit` now also supplies
`ws_max_queue=1`; it passes 1/1 with handshake 101, close 1009, no delivery of
the oversized message, and clean process exit. Receipts are ignored under
`target/ws-queue-cli-parity.json` and
`target/ws-queue-python-api-parity.json`.

This confirms option acceptance and that the independent message-size limit
still works. It does not establish a configurable queue bound or compatibility
with Uvicorn's legacy `websockets` backend.

## Focused server WebSocket keepalive parity (2026-10-21)

The input case `websocket.server-keepalive-ping-pong-timeout` starts Uvicorn
0.54.0 and uvicorn-rs through their CLI adapters with
`--ws-ping-interval 0.1 --ws-ping-timeout 0.3`. A raw RFC 6455 client
completes the handshake, reads a four-byte server Ping, returns its matching
Pong, reads the next Ping, withholds its Pong, and observes close code 1011
with reason `keepalive ping timeout`. The case passes 1/1 on macOS 15.7.7
ARM64 / CPython 3.12.13 with `websockets` 17.1. Receipt:
ignored `target/ws-keepalive-parity-focused.json`.

This verifies that one non-default CLI configuration and the Rust-owned
keepalive schedule match the pinned oracle for this exchange. Other timer
values, disabled interval/timeout behavior, direct `uvicorn.run()` and
`uvicorn_rs.Server` configuration, compression, and WebSockets over HTTP/2 or
HTTP/3 are not established by this case.

## Keep benchmark oracle files separate

The candidate distribution and upstream Uvicorn both provide files under the
`uvicorn` import name. Never install both distributions into one benchmark or
parity environment: the resulting imports can depend on installation order.
The project `.venv` contains `uvicorn-rs-py`; the oracle environment contains
stock Uvicorn 0.54.0 and is created from the locked `uvicorn-oracle` group:

~~~sh
uv sync --python 3.12 --locked --group benchmark --group fastapi-benchmark
UV_PROJECT_ENVIRONMENT=target/uvicorn-oracle uv sync --python 3.12 --locked \
  --only-group benchmark --only-group uvicorn-oracle --only-group fastapi-benchmark \
  --no-install-project
~~~

Parity passes `--oracle-python target/uvicorn-oracle/bin/python`. HTTP/1.1,
WebSocket, and lifecycle benchmark runners pass
`--uvicorn-python target/uvicorn-oracle/bin/python`. The runners verify the
oracle version, Python version, import origin, absence of `uvicorn-rs-py`, and
installed Uvicorn file hashes before starting a comparison.

## User-facing status

The install/rollback steps and current limitations are on the
[Uvicorn replacement page](../uvicorn-compatibility.md). The live ASGI
protocol results remain in the [support matrix](../support-matrix.md).
