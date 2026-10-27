# Uvicorn 0.54.0 compatibility contract

This page is the maintainer source map for the Uvicorn replacement work. It
records the upstream public surface, where it comes from, the current
`uvicorn-rs` PyPI distribution gap, the optional `uvicorn-rs-py` adapter role,
the Kata owner for implementation, and the parity evidence
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

The parity manifest pins the Uvicorn and Hypercorn oracle runtime to CPython
3.12. Upstream Uvicorn 0.54.0 declares `Requires-Python >=3.10`, so a candidate
wheel run on CPython 3.9 is supplemental package-floor smoke, not an oracle
parity receipt. On 2026-10-27, the dirty-source 0.2.2 wheel's `cli.console-help`
case passed on CPython 3.9.6, while `python-api.public-imports-and-signatures`
was compared against the CPython 3.12 oracle and differed only in
`typing.get_type_hints()` resolution. The 0.54.0 oracle source itself cannot
import on CPython 3.9. This cross-runtime observation establishes no candidate
API mismatch and does not change the CPython 3.12 parity result. See
`target/kata-progress/installed-parity-current-20261027/python39-parity-fixed.json`
(SHA-256 `dbec448a973e403efb7396f65f068c14fde0bf257336f846491516cda47c4daa`).

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
| App selection | `APP`, `UVICORN_APP`, `--factory`, `--app-dir`, `--reset-contextvars` | `APP` is required unless supplied by env; factory false; app-dir is empty and adds a leading import path; context reset false. Missing-module and missing-attribute import diagnostics have focused cases. `http1.cli-contextvars-inherit-by-default` and `http1.cli-reset-contextvars-clears-request-context` compare CLI context behavior; `python-api.run-reset-contextvars-clears-http-request-context` covers the `uvicorn.run()` API against Uvicorn 0.54.0. | `1s4z`, `9kbx`, `4fvf` |
| Binding | `--host`, `--port`, `--uds`, `--fd`, `--backlog` | `127.0.0.1`, `8000`, `None`, `None`, `2048`. Five live cases cover IPv4 TCP listeners through module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two sockets. Two additional module-CLI cases pass with inherited IPv6 listeners using one and two workers on macOS ARM64 / CPython 3.12.13 (run `bc282b37f69a46a38e8353a94197e2a7`, report SHA-256 `f55d9d1f8227452b0513446e2b96241fc63277c1f359ca761fb570a0ea94ca0f`). Other IPv6 API paths and Windows remain unverified. | IPv4: `python-api.module-cli-serves-request-on-inherited-fd`, `python-api.run-serves-request-on-inherited-fd`, `python-api.config-server-serves-request-on-inherited-fd`, `python-api.server-serves-request-on-prebound-socket`, `python-api.server-serves-request-on-multiple-prebound-sockets`; IPv6: `python-api.module-cli-serves-request-on-inherited-ipv6-fd`, `python-api.module-cli-two-workers-serves-inherited-ipv6-fd-request`; Kata owners: `9kbx`, `dhfq`, `4fvf` |
| Reload | `--reload`, repeatable `--reload-dir`, `--reload-include`, `--reload-exclude`, `--reload-delay` | false; no explicit dirs; includes/excludes are unset; `0.25` seconds. With no watcher package, file polling behavior is narrower. If reload and multiple workers are both set, Uvicorn warns that workers are ignored while reloading. | `dhfq`, `9kbx`, `4fvf` |
| Workers and process lifetime | `--workers`, `--timeout-worker-healthcheck`, `--limit-max-requests`, `--limit-max-requests-jitter`, `--timeout-graceful-shutdown` | workers unset, then `WEB_CONCURRENCY` or one; healthcheck `5`; request limit unset; jitter `0`; graceful timeout unset. When reload and multiple workers are both requested, reload takes precedence and Uvicorn warns that the worker count is ignored. Signal handling includes SIGINT and SIGTERM, SIGBREAK on Windows, and supervisor-specific SIGHUP/SIGTTIN/SIGTTOU behavior where available. | `dhfq`, `dv25`, `4fvf` |
| Event loop | `--loop` | `auto`; documented choices are `auto`, `asyncio`, `uvloop`, and `zuvloop`. The API also accepts `none` and import paths. Optional implementations have platform/runtime restrictions. | `dv25`, `9kbx`, `4fvf` |
| HTTP | `--http`, `--http2`, `--h11-max-incomplete-event-size` | `auto`, false, and 16 KiB effective h11 limit. Documented HTTP backends are `auto`, `h11`, `httptools`, and experimental `zttp`; HTTP/2 requires `--http zttp --http2`. The candidate maps H1 selectors to its Rust implementation and accepts the zttp selector without importing zttp. `http1.h11-selector-scope-query-header-and-body` and `http1.httptools-selector-scope-query-header-and-body` send a POST through each selected backend and compare the response and ASGI scope with Uvicorn 0.54.0. The httptools case passed 1/1 on macOS ARM64 / CPython 3.12.13 at clean candidate revision `544b44f77f03cca5e7fd4062cac924103a537bbe` (run `fa0eae62007e4e578873a8cfe0222278`). A prior local aggregate run passed the 27 earlier HTTP/2 parity inputs against Uvicorn 0.54.0 and zttp 0.0.34. The added `http2.zero-concurrency-rejects-request-with-503` case passed 1/1 in selected coverage run `8db2016852224570b63db99eea9b0a90`; it checks the oracle-matched 503 with a zero limit and reaches the HTTP/2 observer arm. This dirty local receipt is one-case evidence. The reset case encodes a zero-byte request with an empty final DATA frame because zttp does not wake ASGI `receive()` for END_STREAM on initial HEADERS; that alternate encoding remains unverified. Parser-specific malformed H1 behavior, hosted release, and benchmark evidence remain pending. | `dv25`, `9kbx`, `4fvf` |
| WebSockets | `--ws`, `--ws-max-size`, `--ws-max-queue`, `--ws-ping-interval`, `--ws-ping-timeout`, `--ws-per-message-deflate` | `auto`, 16 MiB, 32, 20 s, 20 s, true. Backends include `none`, `websockets`, `websockets-sansio`, and `wsproto`; queue and compression support depend on backend. | `dv25`, `9kbx`, `4fvf` |
| Lifespan and interface | `--lifespan`, `--interface` | both `auto`; lifespan choices are `auto`, `on`, `off`; interface choices are `auto`, `asgi3`, `asgi2`, `wsgi`. Uvicorn's native WSGI implementation is deprecated. | `dv25`, `4fvf` |
| App environment | `--env-file`, `Config(env_file=...)`, `run(env_file=...)` | unset; loads environment for the app before app import/factory invocation. `UVICORN_*` server settings are not loaded from this file. The module CLI and programmatic factory paths have focused parity cases; broader dotenv syntax and precedence remain unverified. | `9kbx`, `gjpr`, `4fvf` |
| Logging | `--log-config`, `--log-level`, `--access-log` / `--no-access-log`, `--use-colors` / `--no-use-colors` | Selected default startup, access, shutdown, and concurrency-limit warning events are compared for `uvicorn.run()`, `Config`/`Server.run()`, and module CLI requests. `python-api.run-applies-numeric-warning-log-level` verifies that API level 30 filters application DEBUG/INFO events while retaining WARNING and above; module CLI cases verify that `--log-level warning` suppresses startup/access INFO events, `UVICORN_LOG_LEVEL=debug` enables DEBUG application logs, and an explicit warning option overrides that debug environment value. `python-api.run-disables-access-log` and `python-api.module-cli-disables-access-log` verify access-log suppression while retaining other normalized lifecycle events. Custom JSON, INI, and YAML formatter cases compare through both public entry points; the YAML cases run with PyYAML from the benchmark dependency group, matching the package's `[standard]` extra. `python-api.module-cli-uses-log-config-from-environment` confirms that `UVICORN_LOG_CONFIG` overrides the built-in setting. Raw child logs remain in result artifacts; other levels, precedence combinations, color combinations, and exact traceback frames remain unverified. | `9kbx`, `gjpr`, `4fvf` |
| Proxy and response headers | `--proxy-headers` / `--no-proxy-headers`, `--forwarded-allow-ips`, `--server-header` / `--no-server-header`, `--date-header` / `--no-date-header`, repeatable `--header` | proxy/server/date headers true; trusted IPs default from `FORWARDED_ALLOW_IPS` or `127.0.0.1,::1`. Selected `uvicorn.run()` inputs cover environment-only trust and explicit API override; module-CLI inputs cover environment-only trust, explicit CLI override of a conflicting environment value, and `--no-proxy-headers`. This does not verify all proxy/header flags or precedence combinations. | `9kbx`, `dv25`, `4fvf` |
| Request/resource limits | `--root-path`, `--limit-concurrency`, `--limit-max-requests`, `--limit-max-requests-jitter`, `--timeout-keep-alive` | Empty root path; concurrency and request limit unset; jitter `0`; keep-alive `5` seconds. HTTP/1.1 target contract inputs cover ASCII `root_path` through the API and module CLI; they validate all three relevant ASGI scope values against explicit expectations and compare exit code, response receipt, shutdown signal, and timeout state with Uvicorn. Uvicorn 0.54.0 adds the configured prefix to `raw_path`, so response-body parity is not claimed for these cases. A separate case covers percent-encoded UTF-8 request-path decoding with an empty root path. A target conformance case checks Unicode `root_path` and original `raw_path` bytes; Uvicorn 0.54.0 rejects the Unicode prefix before ASGI invocation. HTTP/1.1 CLI, `uvicorn.run(limit_concurrency=1)`, and `Config`/`Server.run()` inputs verify the 503 behavior at limit 1. `cli.limit-max-requests-zero-exits-after-startup` checks the zero threshold, and `python-api.module-cli-limit-max-requests-exits-after-one-response` verifies one-request natural shutdown through `UVICORN_LIMIT_MAX_REQUESTS=1`; both match Uvicorn 0.54.0. `python-api.module-cli-limit-max-requests-jitter-stays-in-configured-range` checks that jitter 1 with a base limit of 2 exits naturally after 2 or 3 responses, preserving per-run counts but comparing the range rather than the randomized count. Negative jitter timing/message behavior remains unverified. `python-api.module-cli-timeout-keep-alive-closes-idle-connection` verifies that a one-second timeout closes an idle HTTP/1 connection after a two-second wait; the HTTP/2 zero-threshold limit and 503 response now have one selected oracle-parity case; concurrent-stream accounting, TLS, HTTP/3, other timeout values, and other request-limit values remain unverified. Backlog controls the OS accept queue. | `9kbx`, `dv25`, `4fvf` |
| TLS | `--ssl-keyfile`, `--ssl-certfile`, `--ssl-keyfile-password`, `--ssl-version`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers` | Six focused mTLS inputs exercise trusted client certificates under default negotiation and TLS 1.2, optional anonymous clients with CA-backed and empty-root configuration, rejection of an untrusted client certificate with empty roots, and trusted TLS 1.2 client authentication through the module CLI. The Config/Server batch passed 5/5 and the separate module-CLI case passed 1/1 against Uvicorn 0.54.0; selected evidence does not establish full TLS parity. Other focused inputs verify TLS 1.2 negotiation, one TLS 1.2 cipher-string restriction, and one encrypted PKCS#8 key using AES-256-CBC/PBKDF2-HMAC-SHA1. The default enables TLS 1.2/1.3; QUIC remains TLS 1.3. Two selected traditional RSA PEM cases verify AES-256-CBC loading with the correct password and the wrong-password failure; encrypted EC PEM, AES-128/AES-192 variants, and other encryption combinations remain unverified. Legacy TLS 1.0/1.1 and arbitrary `ssl_context_factory` behavior remain unsupported by the native Rustls path. | `9kbx`, `dv25`, `4fvf` |
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
| ASGI root-path scope | HTTP and WebSocket scopes expose the configured `root_path` and prefixed decoded `path`. The live WebSocket case `websocket.root-path-preserves-request-raw-path` also asserts that the target `raw_path` is the original encoded request path. Uvicorn 0.54.0's WebSocket SansIO backend prefixes `root_path` into `raw_path`; uvicorn-rs preserves the request bytes, following the ASGI HTTP/WebSocket scope definition. This is a deliberate standards-based Uvicorn compatibility exception. | `dv25`, `4fvf` |
| Streaming and disconnect | Read and write flow control apply high/low-water backpressure. After a response completes, later request-body reads yield `http.disconnect`. `Expect: 100-Continue` is acknowledged only when the application receives the body. | `dv25`, `4fvf` |
| Resource behavior | Concurrency excess is refused with HTTP 503 after request headers; backlog limits the OS accept queue and does not queue refused application work. Max requests terminates a worker and is intended for a process supervisor. | `dv25`, `dhfq`, `4fvf` |
| Shutdown and signals | SIGINT/SIGTERM start graceful shutdown; a second SIGINT can force exit. Existing responses and background tasks are drained within the graceful timeout. UDS paths created by the process are removed on exit. Worker/reloader parents have distinct signal and child-process behavior. | `dv25`, `dhfq`, `4fvf` |
| Startup and CLI failures | Click usage/argument errors, app import errors, bind/TLS failures, lifespan startup failure, and server-not-started outcomes have distinct diagnostics and exit behavior. Uvicorn's startup-failure status is 3; Click parse failures use Click's command error behavior. | `9kbx`, `gjpr`, `4fvf` |
| Operator logs | `uvicorn.error` and `uvicorn.access` are separately configurable; custom logging config accepts dict/JSON/YAML and fileConfig formats; warnings and exception traces are observable output. Selected default log events now have input-driven parity checks; custom configuration and exact traceback frame formatting remain open. | `9kbx`, `gjpr`, `4fvf` |

The ASGI protocol inputs in `tests/parity/manifest.json` cover only some rows
above. The input-only matrix now also includes CLI, Python API, and process
cases, but package-replacement checks and supported-platform evidence remain
incomplete. `4fvf` owns expanding the input-only parity system, with
implementation work split across the owners in the evidence map below.

## Current implementation and evidence map

| Surface | Current `uvicorn-rs` state | Owner | Required parity route |
| --- | --- | --- | --- |
| Distribution and `uvicorn` command/import namespace | The current source metadata is version `0.2.2` and declares the PyPI name `uvicorn-rs`, Python `>=3.9`, Uvicorn-style base dependencies, and a `[standard]` extra. The root Cargo integration package and optional extra console script remain named `uvicorn-rs-py`; `uvicorn.__version__` reports the pinned Uvicorn compatibility baseline `0.54.0`. Cargo crates at 0.2.1 are published. Local 0.2.2 inspection artifacts were built from dirty source and are not upload-eligible; the PyPI `uvicorn-rs` distribution remains unpublished. The exact-main candidate, clean downstream consumers, and full package/runtime parity gates remain open. | `1s4z` | Input cases compare installed distribution metadata/imports, entry points, module and console commands, and executable behavior with upstream 0.54.0. |
| CLI/settings/environment | The compatibility namespace uses Click option metadata adapted from Uvicorn 0.54.0. The current CLI input index has 94 unique cases (schema `uvicorn-rs-parity/input@42`; SHA-256 `eb17fe8b9b573585361b919c2832ba6aaa1c7c8d6882ad7f6b66ca6be35912aa`); the historical indexed profile had 34 cases: help/version, validation, app selection and loading, current-directory import resolution from the installed console command, worker-option normalization, selected protocol options, `--root-path`, environment-file behavior, response-header policy, `--limit-max-requests 0` startup shutdown, and `--ws-ping-interval 0` startup acceptance. The historical dirty-source profile passed 34/34 against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13 on 2026-10-22 (run ID `78f47e13dcec4e0eb0e2f6a1ac656e36`; report SHA-256 `17969ce55d3bfb4ab7ef435ed5a24c23bebc1bb0759f6134742e6766af57f951`). After the websocket-selector change on 2026-10-23, the two affected cases, `cli.ws-websockets-sansio-preserves-app-load-diagnostic` and `cli.sansio-ws-size-and-queue-preserve-app-load-diagnostic`, passed 2/2 (run ID `d652526ebcb745eca981dfd69317151b`; receipt SHA-256 `bb8a89e9df0241f59bee8b06f8fbffc69cfb80d870a9f5b3ff9e5e403ff5d22c`). The 34-case profile has not been rerun after that change. On 2026-10-24, the added `cli.invalid-limit-concurrency-env-is-rejected` case passed 1/1 against the oracle (run ID `2c2fee8ea606497f9fbad3dfc8c0005b`; receipt SHA-256 `df3c7746ab0bee5c66accf3a9f42a9a86977ada25aadd0d0879a3c33d1d1804c`; source SHA-256 `b34d2cb7e272fa3cb293b6012aaef66f4035da47df0a81cb1677e689feda2a67`; `cli.json` SHA-256 at that run `331eaa5f201437d6b3903afa2ccdf96fd94a9953720bcae0ca5a30cd9b6ed9a4`). A later one-pass full unified diagnostic (run `4d45912cb1084ed8b4e1d08a22a21b53`, report SHA-256 `6b84d61748bce0c41d2510b32cf2e9f46e5423868bb33187d6354ad15d250063`) includes all 55 CLI cases with 55/55 passing and the same CLI input hash. It binds to dirty source revision `5b1ec29201c963d8590c989b07318bb7366d7922`, has zero complete verification repeats, and predates the current input@40 inventory. It is one-pass evidence, not a release-ready full-profile receipt. Later selected receipts for invalid log-level and invalid protocol/interface selectors are recorded in [parity results](../parity.md); the focused log-level environment group also passes 2/2 for malformed `UVICORN_LOG_LEVEL` rejection and explicit `--log-level critical` precedence; selected CLI cases confirm explicit `--interface asgi3` overrides malformed `UVICORN_INTERFACE` and explicit `--timeout-graceful-shutdown 1` overrides malformed `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`; the latter passes 1/1 in the focused receipt in [parity results](../parity.md#explicit-module-cli-graceful-shutdown-value-overrides-malformed-environment-2026-10-27). Two further cases confirm explicit `--ws-max-size` and `--ws-ping-timeout` override malformed environment values; they pass 2/2 in [the focused group](../parity.md#module-cli-websocket-environment-precedence-2026-10-27). Four selected cases compare malformed `UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER` diagnostics and explicit zero-valued CLI overrides; they pass 4/4 in [the request-limit environment group](../parity.md#module-cli-request-limit-environment-validation-and-precedence-2026-10-27). Six further selected cases compare malformed backlog, keep-alive timeout, and worker-healthcheck timeout environment values with explicit CLI overrides; they pass 6/6 in [the numeric settings environment group](../parity.md#module-cli-numeric-settings-environment-validation-and-precedence-2026-10-28). Seven selected cases compare malformed WebSocket max-queue, ping-interval, and per-message-deflate environment values with explicit CLI overrides, plus explicit concurrency-limit precedence over malformed environment; they pass 7/7 in [the WebSocket and concurrency environment group](../parity.md#module-cli-websocket-and-concurrency-environment-precedence-2026-10-28). Ten selected cases compare malformed HTTP, WebSocket, lifespan, worker-count, and reload-delay environment values with explicit valid CLI overrides; they pass 10/10 in [the selector and process-setting environment group](../parity.md#module-cli-selector-and-process-setting-environment-precedence-2026-10-28). These selected cases do not constitute a full profile. The distinct `cli.explicit-port-over-invalid-env-starts-server` case also passed 1/1, verifying that `--port 0` overrides malformed `UVICORN_PORT` through startup (run `188a09864fa34689bd4d65008b9b9cff`; receipt SHA-256 `af93265d6d50c55d9a351295e7fa08127f7307f404b822f85b8db6938e909fbf`; runtime source digest `57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`; current CLI input SHA-256 `34b092559c9919b6dd3f0e0ce6702f47f372477f5e3832a39e5af1d2acb9550b`). A separate `cli.env-file-value-reaches-application-factory` case removed the process value and verified that the env-file value reaches the app factory; it passed 1/1 with identical exit status and output (run `6c2e18e456194eceb8aa897b2d354f3d`; receipt SHA-256 `94fee7a0e75237444da4f71e9e9f0c2d5a2087dbd0ef3ee9530168b3fab77035`; runtime source digest `57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`; CLI input SHA-256 `c7bc6b4db7400f0d9488b633e17536248b492041687aa2ba69b0abd5df296425`). Both newer selected cases are dirty-source macOS ARM64 / CPython 3.12.13 evidence only. The zero-interval case exits after startup and does not verify WebSocket Ping behavior on an active session. Python API inputs also drive module CLI limit settings through `UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER`. A separate HTTP/1.1 protocol input compares `--limit-concurrency 1` 503 responses. Two Python API inputs check two-worker module-CLI request and shutdown using explicit `--workers 2` and `WEB_CONCURRENCY=2`; the historical 73-case Python API profile checks one worker crash/replacement path. A selected POSIX health-check case passed 1/1 with a non-default 2-second timeout on 2026-10-23 (run ID ae4e43b0e69245a8b22cd67668cdaeba; report SHA-256 eae083b94d0d0637b0005fa9278066b48b52f787f93b06c3e58113270a602e1e; dirty target source SHA-256 2ab00648452a5ea0ca1c4ef4942e4069440d92446734ccd5513ee6046e53f57e). Repeated restart/failure policy, worker-control signals, and other option effects remain unverified. `ssl_ciphers` now maps OpenSSL-selected TLS 1.2 suites into Rustls, with one negotiated-cipher parity case passing. The PKCS#8 selected cases cover successful Config/Server and module-CLI loading plus a wrong-password failure using AES-256-CBC/PBKDF2-HMAC-SHA1. A new selected run compares successful Config/Server loading of a traditional AES-256-CBC encrypted RSA PEM and its wrong-password failure; both pass against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run `d8d3680a7144445891702d5694d2f08c`; receipt `target/kata-progress/parity-traditional-key-current.json`, SHA-256 `5ac2a8d0051609964f20a4281c3498eb505e3f42e27489ac2a9448a85600e04b`; dirty source digest `e81ab997f0b1f8405bba9400028366681d8f73c977c7823783d71c5cc7fb3af4`). Encrypted EC PEM, AES-128/AES-192 variants, and other combinations remain unverified; `ssl_context_factory` remains unsupported. | `9kbx` | Extend `tests/parity/inputs/cli.json`; invoke both module and console paths with matching argv/env/cwd/files and compare exit status, stdout, stderr, and listener/app behavior. |
| `run`, `Config`, and `Server` API | `uvicorn.Config`, `uvicorn.Server(config)`, and `uvicorn.run` expose the pinned signatures. Focused comparisons cover default ASGI3 serving, successful ASGI3 application-factory serving through both the programmatic API and module CLI, ASGI2 auto-detection and explicit selection, WSGI GETs through `uvicorn.run()` and the module CLI with `lifespan="off"` and `lifespan="auto"`, lifespan, the `root_path` ASGI scope contract, environment files, custom headers, the `Server.on_tick` signature and callback/header/request-limit behavior, readiness, startup-failure state, positive and zero concurrency-limit behavior, single-worker acceptance of a non-default healthcheck timeout, `WEB_CONCURRENCY=0` selecting one in-process server, request-limit zero/positive/jitter natural-shutdown behavior through the module CLI, warning-level filtering, `UVICORN_LOG_LEVEL=debug` and explicit CLI precedence over that environment value, custom JSON, INI, and YAML logging configuration through `uvicorn.run()` and the module CLI, two-worker module-CLI request and SIGINT shutdown with explicit `--workers 2` and `WEB_CONCURRENCY=2`, and selected SIGINT shutdown outcomes. The current input set contains 130 ordinary HTTP-run (including two active-request graceful-timeout cancellation cases), two request-limit, and five concurrency cases; it includes module-CLI --limit-concurrency 1, which returns the oracle-matched 503 and shuts down cleanly. WSGI auto-mode cases compare the unsupported-lifespan fallback with no logging, configured logging, and default module-CLI logging; all five WSGI request cases check method, path, query, and request-header mapping. The three auto-mode cases and the two `lifespan="off"` cases pass individually against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. Advanced Config settings, WSGI request-body/streaming/error behavior, other strict-mode failure classes, other log levels and precedence combinations, inherited-listener variants beyond two IPv4 TCP sockets and plain HTTP/1.1 UDS, and broader lifecycle behavior remain unverified. The two-listener case passed on macOS ARM64 / CPython 3.12.13. | `gjpr` | `tests/parity/inputs/python-api.json` compares public imports, signatures, selected run behavior, custom headers, environment-file loading, successful application-factory loading through both entry points, ASGI/WSGI interface handling, resource-limit responses, logging configuration, lifecycle observations, and normalized log events against upstream Uvicorn. |
| HTTP, WebSocket, lifespan, ASGI and errors | The current Rust server has an input-driven ASGI protocol matrix. Uvicorn is the H1/WebSocket/lifespan oracle; Hypercorn is the current H2/H3 oracle. This is not Uvicorn CLI/API compatibility. | `dv25`, `4fvf` | Extend the existing protocol cases where applicable; preserve the declared reference per protocol and compare public observations. |
| Unix/fd sockets, reload, multi-worker supervision | Eight focused HTTP/1.1 comparisons pass for POSIX UDS and inherited IPv4 TCP listeners: plain UDS through the module CLI and `Config`/`Server`, HTTPS over UDS through the module CLI, and inherited TCP through module CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one and two listeners. The UDS scope checks `client=None` and `server=(PATH, None)`. One selected `Server.serve()` case also matches replacement of an existing UDS pathname and lifespan startup/shutdown on macOS; see [the one-case receipt](#existing-uds-pathname-replacement-and-lifespan-cleanup). Two module-CLI inputs start two workers, selected by `--workers 2` and `WEB_CONCURRENCY=2`, serve a GET, and shut down on SIGINT. The historical 73-case Python API/import profile passed 73/73 on 2026-10-22 against dirty source at exact commit `86e72e181d00feca1b4db7f30377d5d9d4345b83` on macOS ARM64 / CPython 3.12.13, including `python-api.module-cli-worker-crash-restarts`; both implementations replaced one worker that exited with status 73, served the HTTP request, and shut down cleanly. Run ID `161275c5ed8c44a18d83a139622f3dad`, receipt SHA-256 `7ab890cb6988a0837621e522dce6e2447fb6d93c7b28c9084ee639af5bea8758`, source SHA-256 `92d6b4e68282fb735262d08abcc39b930bd53d6bf4347bf5dfcc659ea05fd475`, and native extension SHA-256 `969ff7c36bc36ac7f23a5837f794417b4374c1e733024112caa85a1d90b1a618`. This profile predates the 2026-10-23 Python-source change and is not current-source full-profile evidence. The local `python-api.module-cli-reload-restarts-after-watched-module-change` input also passed against Uvicorn with `--workers 2` in both dependency modes: candidate `StatReload` without watchfiles and candidate `WatchFilesReload` with `watchfiles==1.3.0`. It verifies the replacement response, the warning that reload ignores the worker count, and graceful SIGINT shutdown. The POSIX health-check expiry input passes. A focused include/exclude glob case also passes. The earlier full diagnostic pass on 2026-10-27 compared `python-api.server-handle-exit-signal-escalation` with Uvicorn 0.54.0 and it passed (report `target/kata-progress/coverage-current-source-full-diagnostic-20261027.json`; per-case result SHA-256 `b5755d5624222b0c84804982e9213570d16da19b1cdf37988c07c79936f0eba4`). It checks `handle_exit` state transitions for SIGINT and SIGTERM sequences; it does not send OS signals to supervised workers. A separate process-level input, `python-api.module-cli-second-sigint-forces-inflight-request-shutdown`, sends two actual SIGINT signals to a module-CLI process while an ASGI request remains active; both implementations serve HTTP 200, exit 0, and do not time out. Its one-case macOS receipt is documented below. This does not establish Windows or broad worker signal parity. Repeated restart/failure policy, worker-control signals, startup failures, and other listener/platform combinations remain unverified. | `dhfq` | Extend process-control parity across platforms, startup and repeated-failure recovery, supervisor signals, sockets, TLS, and reload combinations. |
| Package extras and release gates | The 0.2.2 source metadata targets the `uvicorn-rs` PyPI name and declares Uvicorn-style base dependencies plus a `[standard]` extra; the available local artifacts were built from dirty source and cannot be uploaded as a clean candidate. The PyPI distribution remains unpublished; there is no exact-main tagged candidate, and exact clean artifacts and downstream consumers have not passed release acceptance. | `1s4z`, `v5fe` | Installed-artifact cases and package-content/dependency gates on the supported OS/Python matrix. |

### Input@40 baseline CLI and Python API profile runs — 2026-10-27

The full input@40 CLI baseline passed 60/60 against Uvicorn 0.54.0 in
run `c25aac929fd74dcb9ff3d9206653596a`. Report
`target/kata-progress/9kbx-cli-current-full-20261027.json`, SHA-256
`fc58678c2f3ab8227fead7ef6f9c4e34b9d5ca823976cebcc4d72c49ba3cb3b7`.
The full Python API profile passed 209/209 oracle-parity cases in run
`c4f523f43087481f90d90fd74c46c5e8`. Report
`target/kata-progress/x3az-python-api-current-full-after-sigint-contract-fix-20261027.json`,
SHA-256 `f45a36e6f32baaaebe8d16b37f19ddf433579f9565f08cd6572e151531009b7e`.
Both use current manifest SHA-256
`ede173a29d162a002ee37d469f1ecaeeafa5d8e97c15c5bfbc67157b55c6f9be`, current
CLI input SHA-256
`b86587d0f2f6d890a9dfef3b974bd2f6b5f5cc109a09fde93c6935e892688cf0`, and
Python API input SHA-256
`3fb4cb2e7e4146060908da556d692ec8654196762261797bf92a352a4f847a96`. The
dirty target is revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`,
native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

The earlier Python API attempt exposed an over-specific fixed exit-code
requirement in
`python-api.config-server-uses-traditional-encrypted-rsa-des-ede3-key`. Both
upstream and target return `-SIGINT` because `Config`/`Server.run()` re-raises
the captured signal after shutdown. The input now compares the observed
process exit code between implementations while retaining the HTTP 200, signal
delivery, and no-timeout requirements. The corrected full profile passed
209/209. These are local one-pass CLI/API profiles only; installed clean
candidate, Windows/Linux, full protocol/native matrix, and three-repeat release
acceptance remain open. Benchmarks remain paused until parity is complete.

### Prior-source one-pass parity diagnostic — 2026-10-27

The local unified run executed all 926 ASGI inputs and 258 native contract
inputs once; all 1,184 passed with zero case failures or infrastructure
failures. It ran on macOS 15.7.7 ARM64, CPython 3.12.13, and Rust 1.98.1
against dirty working source at revision `5b1ec29201c963d8590c989b07318bb7366d7922`.
The report is
`target/kata-progress/coverage-current-source-full-diagnostic-20261027.json`
(SHA-256
`a67a79a380c9ea1446ba5a8ad079256300e8efe0d42a27cfe02dfd2690d8d0ac`). Its
`python-api.server-handle-exit-signal-escalation` oracle comparison passed;
the per-case result SHA-256 is
`b5755d5624222b0c84804982e9213570d16da19b1cdf37988c07c79936f0eba4`.

This is one local pass of the declared inputs on its recorded dirty source snapshot, before the focused repeated-SIGINT change. It does not establish the
three-repeat CI gate, the full supported-OS matrix (including Windows), or a
clean release candidate. Coverage remains incomplete at 13,503/13,586 regions
and 9,980/10,022 lines, so this report is not release acceptance evidence.

The hosted CI run for PR #19 also passed 508/508 public parity cases against
an installed normal wheel on Ubuntu 24.04.5 / CPython 3.12.13 at merge commit
`d6f2400f7ebfd27adbc21e1ca44f01eceff6204c` (the tested PR head was
`5b1ec29201c963d8590c989b07318bb7366d7922`). The uploaded parity artifact is
`uvicorn-rs-public-parity`, SHA-256
`88aeb3b5f4e4f9786713b834d5ec17e815db482027a9135578c78c67d0f5ec02`, from CI
run `40317129093`. This clean hosted receipt covers the public parity subset
on Linux; its coverage job failed, and it does not establish the three-system
benchmark gate.

A fresh local abi3 wheel from the current dirty source passed the installed
consumer check and four installed-candidate comparisons: console help, public
imports/signatures, and successful and wrong-password PKCS#12 PBE startup.
Wheel SHA-256 is
`83cbac6aacc8739911b482dee0a457975275dd436ed19e9d942aec8977f4878f`; the
selected parity report SHA-256 is
`b719cdc454c678150995fe44af201898841aa16db96f120553a952e2929b2ab2`, and the
installed-consumer receipt SHA-256 is
`4d2313607feb714ff8f5a5b963ab2a06a18c4a25dbf3ad32f148fd00cb91d3b4`. A
separate replacement/rollback check could not install the pinned upstream
`uvicorn==0.54.0` because the configured package index only exposed versions
through 0.39.0; it stopped before checking rollback. These local artifacts
remain dirty-source diagnostics, not release candidates.

### Actual repeated-SIGINT shutdown with an active request

`python-api.module-cli-second-sigint-forces-inflight-request-shutdown` passed
1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust
1.98.1. Both module-CLI processes served HTTP 200, received two OS SIGINT
signals while an ASGI request task was held, exited 0, and did not time out.
Run `5250fc7d6d4145e2a1d206de3621fd91`; report
`target/kata-progress/parity-second-sigint-current-20261027.json`, SHA-256
`3d1d1487fc206a067c1cb58d5a175ac21b0cc88c3b673cd64e982f179521f601`. The
receipt binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256
`7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`, native
extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@39 SHA-256
`9cd73e4493708deebe55227a1face7bf3be76ecba8f81c6fc8ebca3b46498feb`.
Server log events are retained but excluded from comparison because platform
traceback details differ during forced cancellation. This selected macOS case
does not close wider worker, restart, or cross-platform process-control
parity.

### Actual graceful-timeout cancellation with an active request

`python-api.module-cli-graceful-timeout-cancels-inflight-request` passed 1/1
against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.
Both module-CLI processes served HTTP 200, received one SIGINT with
`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=1`, observed cancellation of the held ASGI
task, exited 0, and did not time out. Run
`566af64b1d144153b2e9acb369f9795c`; report
`target/kata-progress/parity-graceful-timeout-current-20261027.json`, SHA-256
`e7b00fa31814e5baf03a7667c4660c11006ba67c5ed57e45994386a81f579eda`. The
receipt binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256
`7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`, native
extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@39 SHA-256
`4e42e17e08aef42975f49bc4248ec87a9559045d320fe63a45863dd82ad50f67`. This is
one selected local platform receipt; other timeout values, signal/process
combinations, and supported platforms remain unverified.

`python-api.module-cli-graceful-timeout-flag-cancels-inflight-request` also
passed 1/1 with the timeout supplied as `--timeout-graceful-shutdown 1`.
Oracle and target both served HTTP 200, received one SIGINT while the ASGI task
was held, observed task cancellation, exited 0, and did not time out. Run
`694b96675dca41d593b315f07d0470e7`; report
`target/kata-progress/parity-graceful-timeout-flag-current-20261027.json`,
SHA-256 `d021e11ceb9d5eb27eb089f1006f5329cf4d6aa4a5a5b005ec97ff4c60ee5c87`.
The receipt binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256
`7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`, native
extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@40 SHA-256
`f8d6b7873a5c83f173f63866df6f7b3d7503159522db1929b20659dd7332ed72`. Full
current-source repeats and cross-platform acceptance remain open.

### Current-source reload parity refresh — 2026-10-27

The current-source diagnostic also passed both module-CLI reload inputs against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1 at dirty
revision `5b1ec29201c963d8590c989b07318bb7366d7922` (source SHA-256
`e9e0ccc0b6f16b803cb99984ebdded01830b89ea80056db101f55d5d2573cd6a`; Python
API input SHA-256
`452c332fcaa22a624ea85c875ae2abf6560654ac486142a72e131f1a5fe80f92`).

- `python-api.module-cli-reload-restarts-after-watched-module-change` passed
  1/1: both sides returned `before` and then `after`, observed the reload and
  ignored-worker warning, and exited 0 after SIGINT without timing out. Run
  `b2b71e5449744697ad266af99f8c5f90`; per-case report SHA-256
  `80d05baf0897d68787cdb883c3b5cbcaf1c5085b3695a2748c76619e34775a42`.
- `python-api.module-cli-reload-respects-include-exclude-globs` passed 1/1:
  an excluded-file change did not reload, an included-file change did, and
  both sides exited 0 after SIGINT without timing out. Run
  `f4416b62f9844075b2d596598d3a6b31`; per-case report SHA-256
  `c836b8e35cf64db0974ea3f514ee3dfebac34f606d7f13130f99079ec69018c0`.

These are current-source single-platform receipts. They do not establish other
glob combinations, fallback-watcher filtering, reload startup failures, or
cross-platform behavior.

### Focused module-CLI WebSocket timeout setting — 2026-10-27

`cli.websocket-zero-ping-timeout-is-accepted` starts `python -m uvicorn`
with `--ws-ping-interval 0` and `--ws-ping-timeout 0`. The selected comparison
passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13
(run `98338893fcab4a2fbc3113859ea3c311`; report
`target/kata-progress/cli-ws-ping-timeout-zero-20261027.json`, SHA-256
`c0cc541d55b801745c5ad4fe543fd619a45ad5eaa1c4195fffaf34e9e1705eec`). It
binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `3c6654dd24f30e6b838232518a5c8967c73952a1e722a6ec4d6725568f28fe0d`,
and native extension SHA-256
`d1cdd7955095a0d61c85412d1e3c41aaebd93904a0558136c5f26bc916f94657`. This
only checks CLI startup acceptance; it does not exercise live WebSocket
Ping/Pong behavior or complete CLI parity.


### Focused module-CLI graceful-shutdown settings — 2026-10-27

`cli.timeout-graceful-shutdown-valid-value-exits-after-startup` starts
`python -m uvicorn` with `--timeout-graceful-shutdown 1` and exits after startup
using `--limit-max-requests 0`. The selected comparison passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run
`7b7752d239b249e3943f50400775c437`; receipt
`target/kata-progress/9kbx-graceful-timeout-valid-20261027.json`, SHA-256
`ab9df8e484f24acc20c43edbe83d3839c2f5fa37b0a7823a4295a8efeb14963f`). It binds dirty revision
`5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`, native
extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and CLI
input SHA-256
`b376a82fdcd7ad0b2969b345be718022aaf17fc1cf546e6bab595bcd921c703b`. Both
processes exited 0 with empty stdout and stderr. This verifies valid-option
startup acceptance only; it does not verify cancellation of an in-flight
request after the graceful timeout.

`cli.timeout-graceful-shutdown-valid-environment-value-exits-after-startup`
starts the module CLI with `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=1`, without a
CLI override, and exits after startup using `--limit-max-requests 0`. The
selected comparison passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 /
CPython 3.12.13 / Rust 1.98.1 (run
`24c550a6a3464489a859b501faf2f6a2`; receipt
`target/kata-progress/9kbx-graceful-timeout-valid-env-20261027.json`, SHA-256
`701091163ad0db64e0b62c3536c5663fb526de961d1249bc4c2a481b930ade26`). It
binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
the then-current 58-case CLI input SHA-256
`bc99598c6cb980a26f58b05746fd47b32e5367f8092ad9efe12e50cf5a32af3f`. Both
processes exited 0 with empty stdout and stderr. This checks valid environment
value startup acceptance only; it does not verify the timeout effect on an
in-flight request.

### Focused module-CLI host environment error — 2026-10-27

`cli.invalid-host-env-is-rejected` starts the module CLI without `--host` and
sets `UVICORN_HOST=invalid host`. Uvicorn 0.54.0 and the target both exit 3
with empty stdout/stderr in the selected run on macOS 15.7.7 ARM64 / CPython
3.12.13 / Rust 1.98.1 (run `d8b06f9cb7c44a1d8c9a7c7147c3773a`; receipt
`target/kata-progress/9kbx-invalid-host-env-20261027.json`, SHA-256
`1e0646131004fcaefecf1bf2456620522c7284b090530fb5d12b5af4cc5812a2`). It
binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
the 59-case CLI input SHA-256
`e8e0781e94793b79e8a86a9515e3fa9212763247f0148ed3db044b1f72c13ec7`. This
checks the public startup failure from an invalid environment value; it does
not establish full environment or CLI parity.

### Focused module CLI missing APP argument — 2026-10-27

Added `cli.no-arguments-requires-app` to represent a true empty argv for the
module invocation. The parity runner now accepts an empty argument list while
continuing to reject non-string and NUL-containing arguments; the earlier
validator rejected this valid process shape before either implementation ran.
The selected comparison passed 1/1 against Uvicorn 0.54.0: both commands exit 2,
emit the identical missing-`APP` usage diagnostic on stderr, and leave stdout
empty.

Run `c17273bcc43745c684d6acf60da4b566`; receipt
`target/kata-progress/9kbx-no-arguments-requires-app-20261027.json`, SHA-256
`2ec969fede17569d3c30a009e7d88967173f034490c5d6546826a00107ec19ca2`.
The receipt binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256
`3d902bf0ff0c32c2bf4e7baed1d9074feab558cead42c05e8fa0300b4f9740f5`,
native extension SHA-256
`ab60493a10f9674a016034805f6cbdec5cee8c9724fbb0c309d43fc3e0bd373d`,
CLI input SHA-256
`058e6d836f2e87d9c7aff2e39557b0642574246bbaea429a8d384ed57848db53`,
runner SHA-256
`5a684586ab66df8b930bb182ce5fd7b55c32f86208ac16dbafd84d902a1864ac`,
and manifest SHA-256
`38501024e8a41fe41c905f04890a9131ea8da098dc84deb70f280d1751a3384f`.
Environment: macOS 15.7.7 ARM64, CPython 3.12.13, Rust 1.98.1, Uvicorn
0.54.0. This verifies only the no-argument missing-app diagnostic; full
CLI/settings and platform parity remain open.

### Focused Python import and signature refresh (2026-10-27)

After the Python wrapper imports and constructor return annotations changed,
`python-api.public-imports-and-signatures` passed 1/1 against Uvicorn 0.54.0
on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. Run
`c22b399ad08348448e7880ded0abdeb3`; receipt
`target/kata-progress/gjpr-public-imports-signatures-20261027.json`, SHA-256
`b87371a0428cc767553821fb48197555d668a4b5eb1b617cd96341bbacec8c49`. It binds
dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`, native
extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
Python API input SHA-256
`331fa538328c0a716594f144dc4b0c7e0a7c1caada920383add78a12c8afd283`. The
selected import/signature case passes for this dirty source; broader API,
lifecycle, platform, and installed-package acceptance remain open.

### Focused Config and run() parity group (2026-10-27)

Three selected current-source cases passed together against Uvicorn 0.54.0 on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1:
`python-api.config-properties-and-retired-loop-hook`,
`python-api.run-loads-env-file-before-factory`, and
`python-api.run-reports-missing-module` (3/3, run
`93f415b0d1434d298c04266d07c78e50`). Receipt
`target/kata-progress/gjpr-config-env-import-errors-20261027.json`, SHA-256
`ef02ba1591e263dbd90d0be1065a5e3416392e0eb52d0cba15f6b3dae601926e`.
It binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, runtime
source SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
Python API input SHA-256
`331fa538328c0a716594f144dc4b0c7e0a7c1caada920383add78a12c8afd283`.
The Config-properties and env-file/factory cases add current-source receipts;
the missing-module case refreshes a 2026-10-19 pass against older source. These
selected behaviors pass on this dirty source but do not complete the public
API or release acceptance.

### Focused startup and lifecycle parity group (2026-10-27)

Three selected public-API cases passed 3/3 against Uvicorn 0.54.0 on macOS
15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1: bind-failure lifespan cleanup,
UDS pathname replacement with lifespan cleanup, and concurrent startup-failure
waiter signaling. The observations match: bind failure runs startup and
shutdown, raises from `serve()`, and leaves `started` false; UDS replacement
runs startup and shutdown and returns with `started` true; the startup-failure
waiter returns true while `serve()` finishes before shutdown and `started`
remains false. Run `cf6d77c587604f50b2a00836279128d9`; receipt
`target/kata-progress/gjpr-startup-failure-cleanup-waiter-20261027.json`,
SHA-256 `e1bf2780b8aa83d9498293a56445b6111d4acb8d005df8fe8e8a52b19515dd73`.
It binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
Python API input SHA-256
`331fa538328c0a716594f144dc4b0c7e0a7c1caada920383add78a12c8afd283`.
This is selected dirty-source lifecycle evidence; full platform and installed
package acceptance remain open.

### Focused Server.serve startup cancellation — 2026-10-27

`python-api.server-serve-cancellation-during-startup` passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. Both
observations report that lifespan startup entered before cancellation, the
listener was not accepting after cancellation, the serve task was cancelled
and finished, and `server.started` remained false. Run
`e530db81248644218613ff4a19fe824f`; selected report
`target/kata-progress/gjpr-server-cancel-during-startup-20261027.json`,
SHA-256 `b8bbf7ffe2f17232144c4b018c145335b72d462eb13cccba3846b4345232e4eb`.
The receipt binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256 `2a205a2ee7e482c69fa66338b587060036ce38db5ead5d0a24bd7762cdf76e9b`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
Python API input SHA-256
`331fa538328c0a716594f144dc4b0c7e0a7c1caada920383add78a12c8afd283`. The
selected case has complete attribution (808 regions, 606 lines); the report
is a one-case subset with no complete matrix repeats and does not satisfy the
unified coverage gate. Full lifecycle and platform acceptance remain open.

Current-source CA validation — 2026-10-26: a focused unified-coverage batch passed 13/13 cases (5 Uvicorn parity cases and 8 target-only fault contracts). The cases cover empty, missing, directory, malformed, and `TRUSTED CERTIFICATE` CA inputs, plus error propagation at each step of the Python SSL compatibility helper and its successful-CPython fallback. The trusted-certificate parity case uses a PEM block without auxiliary trust bytes. Coverage-MCP found no missing spans in `python_ssl_ca_certificates_error` for this report. The selected report remains incomplete overall: 3,590/12,973 regions and 2,682/9,610 lines are covered; the full matrix and release coverage gate remain open. Source SHA-256 `83a43c50e8bd1085261e57f95125c5f319ee3c6225a25950c2d15996b9cab79f`; native extension SHA-256 `8d8d9358596ec19462012166f0146710312f9d1f6507d08174c59d9638469eaa`; report `target/coverage-ca-tls-current/report.json`, SHA-256 `f8f417148b22e9405a3fc19863a76a9bd9cb60b0d4922007bcdc554a94c2c948`.

## Current-source selected parity — 2026-10-24

- `python-api.public-imports-and-signatures` now explicitly compares the
  documented `uvicorn.logging.DefaultFormatter` and `AccessFormatter` imports
  and signatures; the focused case passed 1/1 against Uvicorn 0.54.0 on macOS
  15.7.7 ARM64 / CPython 3.12.13. Run ID
  `c6c1e9d4135e4a2dafa5d0294187f2e4`; receipt
  `target/kata-progress/uvicorn-imports-parity-log-formatters-20261024.json`,
  SHA-256 `af6778ddfc3533b6a76102c6cef8b52aa6fa9bc8129a5ccd672e8bd3a1c590e0`;
  input SHA-256
  `14af5f140a2c12549a048cdbd69a94882cbf12f58850e620c73b9a161eabeee8`;
  dirty-source SHA-256
  `57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`.
  This is one selected local case, not full Python API compatibility or
  installed-package release evidence.
- The same focused case now also resolves `uvicorn.server.ServerState` and
  deprecated `uvicorn.main.ServerState` and compares their constructor
  signatures; it passed 1/1 against Uvicorn 0.54.0 on the same host. Run ID
  `a6768d23f4374b3f836153f98322cf83`; receipt
  `target/kata-progress/uvicorn-main-server-state-parity-20261024.json`,
  SHA-256 `866bc0d8aeed019158260787a21da2eeaf75ddb7f83dcbfe04bad17eeb7047b2`;
  input SHA-256
  `bd53fd04436f9803e5688da39f4b7bc8aba4d7570eaab95fe61923739599f773`;
  dirty-source SHA-256
  `4b28bceb47a9e47db926030456c8dbc218fd302fc51147b3b0302767d68e1ab1`.
  This selection does not verify runtime updates to the state fields.
- Added the documented `uvicorn.Server.run()` and `uvicorn.Server.serve()`
  signatures to that same case; the expanded case passed 1/1. Run ID
  `9366ad00302e4497a8d579da77101f74`; receipt
  `target/kata-progress/uvicorn-public-server-method-signatures-20261024.json`,
  SHA-256 `5cc65d3b516f0a487a4534d56b83f544a5091d66695902193ecb75fc638e0d24`;
  input SHA-256
  `fec890a4b2193984524b1a6f34102e6ef4e0ee26e51f8e01b386aab28793155d`;
  dirty-source SHA-256
  `4b28bceb47a9e47db926030456c8dbc218fd302fc51147b3b0302767d68e1ab1`.
- Extended call observations to retain warning category and message, then
  exercised the deprecated `uvicorn.main.ServerState` lookup. The warning
  matched Uvicorn 0.54.0 and the one selected case passed. Run ID
  `9d40f72628a540b686b34a512bb4b171`; receipt
  `target/kata-progress/uvicorn-server-state-warning-parity-20261024.json`,
  SHA-256 `b0be689edc52ffdd103315cfc97eda791b687f77ea2202427cb1e39867dcf06e`;
  input SHA-256
  `77c7148d7b2621a589ae667f95a5d33aa1b35735e549be5ad7628b4f6cfb10d5`;
  dirty-source SHA-256
  `4b28bceb47a9e47db926030456c8dbc218fd302fc51147b3b0302767d68e1ab1`.
  Runtime updates to the state fields remain unverified.

- `python-api.module-cli-reload-respects-include-exclude-globs` passed 1/1
  against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Both sides
  used `WatchFilesReload`; changing `ignored.txt` did not reload the app,
  changing the included `included.txt` did, and SIGINT shutdown exited 0. Run
  ID `35c7bac2545c47968ee1aaa715806fef`; receipt
  `target/kata-progress/dhfq-reload-filters-20261024.json`, SHA-256
  `135b3c57f486b99815027e3ca7bbfe8b336c331e303d489e305f3fefa647f064`;
  dirty-source SHA-256
  `e7d3f0ca2c6d82c31eb675e3090d6ba8a16797a498689077c881b427b6683ecf`;
  Python API input SHA-256
  `d74f75f11e7fe7077bdb5bc9de3fe4814301cb71ebea98c4d91eef87213fe0ef`
  (input schema `uvicorn-rs-parity/input@34`).
  This is one selected local case, not full process-control or cross-platform
  evidence.

## Current-source selected parity — 2026-10-25

- Seven newly added CLI validation inputs passed together against Uvicorn
  0.54.0: invalid HTTP, interface, lifespan, WebSocket, and log-level
  selectors; invalid graceful-shutdown and WebSocket-ping timeout environment
  values. Result: 7 selected / 7 executed / 7 passed / 0 failed / 0
  infrastructure failures on macOS 15.7.7 ARM64 / CPython 3.12.13. Receipt
  `target/kata-progress/9kbx-invalid-cli-settings-20261025.json`, SHA-256
  `c15476952e5971c3dfa77bb84e1bbaecff7150c43c659a528c918497a1125395`; CLI
  input SHA-256
  `9bfd77f7f332c584df2441e9c7024cb29a44c8cc42960da29c705a7a8b1a690c`;
  dirty-source digest
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`.
  These are selected invalid-input checks, not full CLI-profile evidence.

- `cli.explicit-port-over-invalid-env-starts-server` passed 1/1 on the current
  dirty draft against Uvicorn 0.54.0. The older receipt for this same case used
  a different source digest, so this single case was rerun without rerunning
  the surrounding CLI profile. It confirms that explicit `--port 0` overrides
  malformed `UVICORN_PORT` through actual listener startup. Run ID
  `cf29c728312b4216acd148723d47ec3c`; receipt
  `target/kata-progress/9kbx-explicit-port-env-20261025.json`, SHA-256
  `7a9bc2192b31c11e88262f901173ec361aa9677c1bafd7b131153b415761c325`;
  source SHA-256
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`;
  `cli.json` SHA-256
  `9bfd77f7f332c584df2441e9c7024cb29a44c8cc42960da29c705a7a8b1a690c`.
  At the time, this selected result did not close the CLI profile. A later one-pass full unified diagnostic includes all 55 CLI inputs (see the CLI/settings evidence row) but has zero complete verification repeats.

- The added `cli.explicit-host-over-invalid-env-starts-server` input passed
  1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. It
  confirms that `--host 127.0.0.1` overrides malformed `UVICORN_HOST` through
  actual listener startup. Run ID `e65639c480814a329520c7a59a4acd81`; receipt
  `target/kata-progress/9kbx-explicit-host-env-20261025.json`, SHA-256
  `8ba7b4b25abca16131e99716fff8aaf98cf0f3d36d0d80d7d770f684136bb3fc`;
  current CLI input SHA-256
  `d3325c338f3b8153e1757bd5bb4cb22d5660207415f8495136d005e18da3423a`;
  dirty-source digest
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`.
  This is one selected case. A later one-pass full unified diagnostic includes all 55 CLI inputs (see the CLI/settings evidence row) but has zero complete verification repeats.

- `python-api.module-cli-worker-crash-restarts` passed 1/1 on the current
  dirty draft against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13.
  Both implementations logged a worker exit and replacement, served HTTP 200,
  and shut down with exit code 0. Run ID
  `1a1342f6938a4a329085587ea9acaf3b`; receipt
  `target/kata-progress/dhfq-worker-crash-current-20261025.json`, SHA-256
  `f353fd6441f5545614e5918affa24fe3777a22b88f8cf5e1873a30533e90a58d`;
  Python API input SHA-256
  `dbdce91320f25c1bc0fe3044169b49c55690e9f045d145c0382c41badcf80a95`;
  dirty-source digest
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`.
  This is a single crash/replacement path; repeated restart policy, supervisor
  signals, and cross-platform behavior remain open.

- `python-api.module-cli-two-workers-restart-on-sighup` passed 1/1 on the
  current dirty draft against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
  3.12.13. Both implementations logged the SIGHUP restart path, served HTTP
  200, exited with code 0, and did not time out. Run ID
  `38f51c8865a5457d836acee3f32820ea`; receipt
  `target/kata-progress/dhfq-sighup-restart-current-20261025.json`, SHA-256
  `64bfdd665259d95b19060b814ba825de7f24ffb133003288480d4bf8bd2095b1`;
  Python API input SHA-256
  `dbdce91320f25c1bc0fe3044169b49c55690e9f045d145c0382c41badcf80a95`;
  dirty-source digest
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`.
  This covers one POSIX SIGHUP path only; startup-failure recovery, other
  supervisor signals, Windows, and clean-source evidence remain open.

- `python-api.server-on-tick-updates-headers-callback-and-request-limit`
  passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
  3.12.13. The comparison matched `Server.on_tick(counter)`, normalized
  default headers, callback notification, and the request-limit exit result.
  Run ID `69b1ed718ea14374b3f4365613201b46`; receipt
  `target/kata-progress/gjpr-server-on-tick-20261025.json`, SHA-256
  `45d2e38cbd572a34273818fc2e328338b81d271bb7ca0b1991443e2f1c182ce0`;
  input SHA-256
  `bb53b3d6f531c0506c9c503bcc8c3218bd14726bf8d5c16c754d3c8906fff441`;
  dirty-source digest
  `fb4dcb566bfd47b6d0c4845f2de443048242703e780522f1cbced5f931ccfcec`;
  native extension SHA-256
  `a56343b27bee27fbfa6d06b6d9823345775492a820d57d8bf54b92b832181270`.
  This is one selected API case, not full lifecycle or installed-package
  parity evidence.
- `python-api.server-callback-notify-stops-server` passed 1/1 with both
  implementations starting, invoking `callback_notify` once, and exiting
  without a timeout. Run ID `aedf808dd3fc47faa8b64644ff49100f`; receipt
  `target/kata-progress/gjpr-on-tick-callback-20261025.json`, SHA-256
  `f1c5dbf1dc6807c529e1d4c5528e4755dde139747b8c45c307ae35c011906d67`;
  it uses the same Python API input hash and dirty-source digest as the
  `Server.on_tick` case above. This selected callback case does not establish
  full lifecycle or worker parity.
- After adding `Server.main_loop` and routing the live native-server wait
  through it, the two related cases above passed together: 2 selected / 2
  executed / 2 passed / 0 failed / 0 infrastructure failures. Run ID
  `49bf710d56ab444f8a4e10b634799c4d`; receipt
  `target/kata-progress/gjpr-server-main-loop-20261025.json`, SHA-256
  `786146eac9c5e217db338a29807184fbf40917f84601d83da2cd8943e7958739`;
  Python API input SHA-256
  `1cd219144124e2ebff4a98396525588f9e04215280a286c7a77ad4223a5ff216`;
  dirty-source digest
  `b6b2ae461addf64a37ba6bec78957e8276db7fae2dc7d70f21b0fe6353611b87`;
  native extension SHA-256
  `a56343b27bee27fbfa6d06b6d9823345775492a820d57d8bf54b92b832181270`.
  This is a selected source-matched batch, not full Python API acceptance.

- After extracting public `Server.startup()` and `Server.shutdown()` and
  routing `_serve()` through those lifecycle methods, five related cases
  passed together: `python-api.server-startup-main-loop-shutdown`,
  `python-api.server-started-follows-lifespan-readiness`,
  `python-api.server-callback-notify-stops-server`,
  `python-api.server-startup-failure-leaves-not-started`, and
  `lifespan.public-server-api-requests-shutdown-and-shuts-down`. The new direct
  lifecycle case matched the startup/shutdown/main-loop signatures, observed
  the pre-bound listener open after startup and closed after shutdown, and
  observed `started` on both sides. The batch passed 5/5 on macOS 15.7.7 ARM64
  / CPython 3.12.13. Run ID `2e9b07b9a9be494ca1952be9d18cc36a`; receipt
  `target/kata-progress/gjpr-server-lifecycle-final-20261025.json`, SHA-256
  `e6e8afc67ebc82c08b6534078414a8cd0977dc24c9a9194d292b7cd26ff2535a`;
  Python API input SHA-256
  `e7bceb6bbbfd85e4e8fcde450271cac13efe5a491e094b972a6c20d1c03b6072`;
  dirty-source digest
  `6f1ae9a3eed5d7f3f0e206b5acc7ef3ed6884fa24c7f462303f3f2a3c8493656`;
  native extension SHA-256
  `a56343b27bee27fbfa6d06b6d9823345775492a820d57d8bf54b92b832181270`.
  This is selected dirty-checkout evidence; direct failure variants, complete
  lifecycle, signals, workers, and installed-package parity remain open.

- The next lifecycle/signal batch corrected shutdown ordering: `should_exit`
  no longer logs before Uvicorn's `shutdown()` phase, and a pre-set exit request
  still allows startup readiness before the main loop exits. The five selected
  cases `python-api.server-startup-main-loop-shutdown`,
  `python-api.server-startup-honors-preexisting-exit-request`,
  `python-api.server-handle-exit-signal-escalation`,
  `python-api.server-callback-notify-stops-server`, and
  `python-api.run-serves-request-and-shuts-down-on-signal` passed 5/5 on macOS
  15.7.7 ARM64 / CPython 3.12.13. They compare direct startup/close behavior,
  first and repeated SIGINT/SIGTERM handler state, callback-driven exit, and
  process-level API SIGINT shutdown. Run ID `489787bb6b7f4336bffea10552b4dcf9`;
  receipt `target/kata-progress/gjpr-signal-lifecycle-20261025.json`, SHA-256
  `73e26960808988ee1c51fa3202786e4229dda140a1ca54cfc1a409ce7e3cc39f`;
  Python API input SHA-256
  `dbdce91320f25c1bc0fe3044169b49c55690e9f045d145c0382c41badcf80a95`;
  dirty-source digest
  `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`;
  native extension SHA-256
  `a56343b27bee27fbfa6d06b6d9823345775492a820d57d8bf54b92b832181270`.
  This remains selected dirty-checkout evidence; full signal capture, Windows
  signal behavior, and the complete programmatic API are unverified.

- `http1-tls.ssl-ciphers-restricts-negotiated-suite` passed 1/1 against
  Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Both servers
  negotiated `ECDHE-RSA-AES256-GCM-SHA384` with the matching TLS 1.2 cipher
  expression. Run ID `8507182448554fce8571e5bd18ea874c`; receipt
  `target/kata-progress/ssl-ciphers-negotiated-suite-verified-20261025.json`,
  SHA-256 `b3f481298b7214662c27250490bbd0f005c0d1e21179efe20fac45dc186b26b2`;
  input schema `uvicorn-rs-parity/input@35`, TLS input SHA-256
  `caaf7b25cd81c45b54a1f4b90bde153c0df7f1bbb47732e063091895404cc145`;
  dirty-source SHA-256
  `2d8ba10bd17fdc1cf48b35fa9ee26b42355c78b136662612873ff70c7fd97434`.
  This is one selected TLS behavior, not full TLS or CLI/settings evidence.

## Current-source selected reruns — 2026-10-23

- `cli.help` passed 1/1 against Uvicorn 0.54.0 after the local Click metavar
  aliases changed. Run ID `8060b49f5762437b95ab71175edbe6c0`; receipt
  SHA-256 `89bb9a124bdbb2aa0277a586ad74095baca3f32c522f8396ae6ef2028bf4ecb3`.
- `python-api.public-imports-and-signatures` passed 1/1 after exporting
  `uvicorn.main` and adding `uvicorn.importer`. Run ID
  `02fea3c94d1e46eebaf17cf402941f73`; receipt SHA-256
  `693d06a9eec064d790ae07323abfd1b9146161dc4fb95e02ddbb3d60a5844a8a`;
  dirty-source SHA-256
  `2ab00648452a5ea0ca1c4ef4942e4069440d92446734ccd5513ee6046e53f57e`.

Both selections used Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13.
They verify only their named behaviors; the complete CLI and Python API
profiles remain unqualified for the current source, and these dirty-source
receipts do not qualify installed package artifacts.

The earlier local receipt for code commit
[`6d157fd`](https://github.com/appunni-m/uvicorn-rs/commit/6d157fdc6) reported
28 passing CLI inputs, but its candidate subprocess could import the installed
upstream Uvicorn package instead of the checkout adapter. Do not treat that
receipt as candidate parity evidence. With candidate source selection fixed,
the latest full local report passed all 33 CLI cases then in the input set
against isolated Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. The current
34th case, which checks startup acceptance of `--ws-ping-interval 0`, passed
separately 1/1; it exits after startup and does not verify Ping behavior on an
active WebSocket. A wheel from the earlier source passed the clean
installed-wheel consumer check, including parity of
`uvicorn-rs-py` and `uvicorn` help options and version output. Its SHA-256 was
`84a98faaa78c0d342d13154c82be8ed0138d3617d95ec1d0c595d34e80904f31`. This is
local evidence for the listed inputs and consumer checks, not full CLI parity
or cross-platform validation.

`tests/parity/manifest.json` describes the ASGI protocol slice, a focused CLI
process slice, and the public Python import/signature probe. Fifty CLI
inputs cover module/console help and version; argument validation and selected
environment precedence; app selection, loading, and import resolution; factory
and env-file startup behavior; JSON log-config diagnostics; explicit default
runtime options; HTTP and WebSocket selector acceptance; SansIO WebSocket
size/queue settings; worker normalization and single-process healthcheck
behavior; `--limit-max-requests 0` startup shutdown; and
`--ws-ping-interval 0` startup acceptance. The HTTP/WebSocket selector cases
check diagnostic ordering rather than parser-specific protocol behavior. The
zero-interval case does not open a WebSocket and does not establish
active-session Ping suppression. The CLI batch has passing evidence for dirty
source digest
`b34d2cb7e272fa3cb293b6012aaef66f4035da47df0a81cb1677e689feda2a67` and
`cli.json` SHA-256
`bf57f4d6a9ed84490237593e9d719d278ab4eb8bebd751c6d74df23f3ca41b46`: 36
inputs passed in grouped run `294c58a8ab11427995865dc68926cc18`, while two
same-digest receipts were reused. The report is
`target/kata-progress/cli-remainder-20261024.json` (SHA-256
`2f0f4f1fd90cd35f13a724025af3fe29b0d1dbf16fc3450fc169d1e912e6d86e`). These
finite inputs do not establish every setting, reload, the full worker-control
contract, or the full command contract. The CLI input set now includes one
`--ws wsproto` diagnostic case. A separate
`websocket-wsproto` profile selects Uvicorn's pinned wsproto 1.3.2 backend on
both sides; its text/binary round-trip passed as selected dirty-source run
`4ca19544cc704a35ae30419af7f62fc8` in
`target/kata-progress/wsproto-websocket-20261025/result.json`. That case does
not establish full backend-specific behavior. A separate
`websocket-websockets` profile selects the legacy Uvicorn `websockets` backend
with pinned `websockets` 17.1 on the oracle and the native implementation on
the target. Its text/binary round-trip and subprotocol case passed 1/1 as
selected dirty-source run `359572d906be43e7a823d7d1c64930fc` on macOS 15.7.7
ARM64 / CPython 3.12.13 (receipt SHA-256
`aa46efe369a53cd278e61e825330d5859544042d53a3af9e8c7477e936fc5b9a`). This
profile now passes `ws_max_queue` to a bounded native ASGI receive-message
channel. The input-only case `websocket.websockets-bounded-queue-drains-burst`
sets `--ws-max-queue 1`, delays the application reader, sends three messages,
and verifies they all arrive before a normal close. It passed 1/1 as selected
dirty-source run `a25f7f4346e64fa39fbf2469aeff1e2a` on macOS 15.7.7 ARM64 /
CPython 3.12.13 / Rust 1.98.1 (receipt SHA-256
`9b441dc55ed950b22e94a6c7bb782d21af386c8d48d1b0894a85c54ed7d1de3b`); both
observed close code 1000 with reason `queue drained`. This checks one queue
setting and delayed-reader path. The native bound counts
complete ASGI messages, while upstream `websockets` applies its high-water
mark to frames; other thresholds, fragmented messages, and flow-control timing
remain unverified. The Python API inputs also
include `python-api.run-loads-env-file-before-factory`, which
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
API and module CLI. The two-worker module-CLI cases verify a successful HTTP request and SIGINT
shutdown. A separate selected POSIX input verifies one worker stops answering
health checks, its supervisor starts a replacement, and the server serves and
shuts down cleanly; its receipt is listed in the process-supervision row
above. At this 2026-10-23 snapshot, repeated restart/failure behavior,
dynamic worker-count controls, reload, and package replacement behavior were
unverified. The current-source reload receipts are recorded in the
2026-10-27 section above; broader restart, worker-control, and package
replacement evidence remains open.
The selected `python-api.server-callback-notify-stops-server` case was added and passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. It configures `timeout_notify=0`, observes one `callback_notify`, and has that callback request server shutdown. The receipt is `target/kata-progress/python-api-server-callback-notify-20261024.json` (run ID `374c669e49c0423491e17c054a57d074`; receipt SHA-256 `4704c5569db341d35e98c932851bd9fa97cc313f5f3a04c9e4209c519ef9b0e9`; source SHA-256 `52149ee124968d443ccc0372c7c5212199b7feac628abab6cfabf7b21f135dac`; Python API input SHA-256 `cfaf2a623280f5ab7cf174333387d1124518d783622fb7780e8cacd2b211b64`). The target was dirty at base revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`, so this is selected local evidence only. It does not establish Gunicorn process supervision or Python 3.9/3.10 worker-loop cleanup.

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

### Explicit worker count precedence

The input `python-api.module-cli-explicit-workers-overrides-web-concurrency`
sets `--workers 2` while the process environment sets `WEB_CONCURRENCY=3`.
Both Uvicorn 0.54.0 and the draft served HTTP 200, exited cleanly after SIGINT,
and logged exactly two worker starts. This confirms the explicit CLI value
takes precedence over the environment value for this path. It passed 1/1 on
macOS 15.7.7 ARM64 / CPython 3.12.13. Receipt:
`target/kata-progress/dhfq-explicit-workers-overrides-web-concurrency-20261024.json`
(SHA-256
`3b1ca0b9c764d144735ac71981c3cdbad536f73362c034f1b655c699056897e3`, run
`1b050929c5ab433cbe647683c100f5b1`). The target was a dirty draft at base
revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`, runtime source digest
`9454ba8e09077f563f2ef42fc7f7056efb49d4ca2ede04dc0c3106abee188b8d`, native
extension SHA-256
`c0e18852813e9f3755466e6cc6a3bebbe2f67d74a73e9846736e617f9aef2d45`, and
Python API input SHA-256
`9e26d00c0ecbcf8923686e31ba5b3135bdc8ca03d3bad88c218619fe2904d7e4`. This is
one selected local process case, not full worker or cross-platform parity.

### Two-worker SIGTERM shutdown

The input `python-api.module-cli-two-workers-stop-on-sigterm` starts two
workers, serves one GET, then sends SIGTERM to the Uvicorn parent. It passed
1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13; both sides
returned HTTP 200, logged `Received SIGTERM, exiting.`, shut down both workers,
and exited 0 without timing out. Receipt:
`target/kata-progress/dhfq-two-workers-sigterm-20261024-after-support.json`
(SHA-256 `c7d274a05f6e0b2309bf11dd2504781f1aec489030e6b6439fc702ea1003b286`,
run `51cd568a8d5848e2ab90157c9abad3fe`). The target was a dirty draft at base
revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`, runtime source digest
`52149ee124968d443ccc0372c7c5212199b7feac628abab6cfabf7b21f135dac`, with
native extension SHA-256
`d6794ea39ffb4cfacabe6f26fbbccfb8db9aa2f63ae718b82ee43a3704bfcd16`; the
Python API input digest is
`2e7b96c38fb74dd77edc694e17e74199a7823359df8d00fb49ed0e1c8e70bdac`. This
proves only this POSIX parent-shutdown path on one local platform; other
signals, worker restart policy, Windows, and other socket combinations remain
unqualified.

### Two consecutive worker crashes and replacement

The input `python-api.module-cli-worker-restarts-after-two-crashes` starts two
workers and injects two successive worker crashes before serving one GET. It
passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13.
Both implementations recorded two child exits and worker replacement, returned
HTTP 200, shut down with exit code 0, and did not time out. Receipt:
`target/kata-progress/dhfq-two-worker-double-crash-20261024.json` (SHA-256
`e6b9bea335a59c8acf9b60b164edac1fb90c4fbef5b93cd27bd4656749f252c0`, run
`4f4e0b4a00b347b9890bd3e7287189de`). The target was a dirty draft at base
revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`; the input file used schema
`uvicorn-rs-parity/input@34` with SHA-256
`845448d64b9dc6f29f8c104607e5a9121814ccf7793b279372090d28f80f3ce6`. This
single POSIX case establishes replacement after two consecutive exits only;
other restart policies, signals, platforms, and socket combinations remain
unqualified.

### Live worker-count signals

The input `python-api.module-cli-two-workers-scale-with-ttin-ttou` starts two
workers, sends `SIGTTIN` to the parent to increase the count, then sends
`SIGTTOU` to decrease it before final `SIGINT` shutdown. It passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Both sides logged the
same signal handling, three server-process starts, three clean finishes, and
exited 0 without timing out after an HTTP 200 response. Receipt:
`target/kata-progress/dhfq-two-worker-ttin-ttou-20261024.json` (SHA-256
`4ab845bd12e92541ba100b8df7391a2b4f051838a86ec1d99c20d3560616a948`, run
`9036ee7f5d104d79bf82c5bf4cf58b82`). The target was a dirty draft at base
revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`; the input file used schema
`uvicorn-rs-parity/input@34` with SHA-256
`1b57a30b8db425b75eb9c4610c44aff8f8a11bd002617459d725cc5f8b658fd6`. This
qualifies only this POSIX two-to-three-to-two worker adjustment path; other
signals and platforms remain unqualified.

### SIGHUP worker restart

The input `python-api.module-cli-two-workers-restart-on-sighup` starts two
workers and sends `SIGHUP` to the parent. It passed 1/1 against Uvicorn 0.54.0
on macOS 15.7.7 ARM64 / CPython 3.12.13. The normalized logs matched, including `Received SIGHUP`, four server-process
starts, and four clean finishes across the two replacements. Both sides served
HTTP 200, exited 0 after SIGINT, and did not time out. Receipt:
`target/kata-progress/dhfq-two-worker-sighup-20261024.json` (SHA-256
`17b82ea9d653d9014376c4773287e66f24a87ef805829698c3607c740de7306a`, run
`b5b7bf4dee60430cbad26138435b2312`). The target was a dirty draft at base
revision `86e72e181d00feca1b4db7f30377d5d9d4345b83`; the input file used schema
`uvicorn-rs-parity/input@34` with SHA-256
`ed432b94e5ac5dd8e75d4647460b8a46eda957eb6e2ae8ef65110270085fffc3`. This
is one POSIX rolling-restart case; restart failure handling and other
platforms remain unqualified.

### SIGHUP replacement startup failure

The input
`python-api.module-cli-sighup-keeps-workers-after-replacement-startup-failure`
starts two workers, sends `SIGHUP`, makes a replacement worker report
`lifespan.startup.failed`, and then sends another GET. It passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Both servers logged
the startup failure and failed-child restart message at `ERROR`; the existing
workers continued serving HTTP 200, and both parents exited 0 after SIGINT
without timing out. Receipt:
`target/kata-progress/dhfq-two-worker-sighup-replacement-failure-20261024-final.json`
(SHA-256 `e2092bf52d6db68018996b0d0fca6eca02b6a306549dabef8de653f80c848904`,
run `084276ba5c514d46805966e6345157f5`). The dirty target was based on
`86e72e181d00feca1b4db7f30377d5d9d4345b83`, with runtime source digest
`57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`, native
extension SHA-256
`c0e18852813e9f3755466e6cc6a3bebbe2f67d74a73e9846736e617f9aef2d45`, parity
runner SHA-256
`d0b06940d3436ad04e5b37c27c3b913ca21884d22d9f4de7b5f63bbc3b4e1746`, and
Python API input SHA-256
`8b00c1074cb66d60440c10271099288d8802d5763fc4aed601793eb5cdb39001`. This
qualifies only this POSIX SIGHUP replacement-startup failure path; other
startup failures, restart policies, and platforms remain unverified.

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

The input-only header-policy case declares its `--header`, `--no-server-header`,
and `--no-date-header` settings; the parity runner no longer injects them by
profile. Its operation now compares `ordered_response_headers`. The first strict
run exposed Hyper's regrouping of distinct names. A local Hyper 1.12.0 patch
adds `hyper::ext::HeaderOrder`; the ASGI bridge carries the original field-name
sequence and prepends server defaults before handing the response to Hyper.
Focused run `9c801d3e06f24971a040c57604458141` then passed 1/1 on macOS 15.7.7
ARM64 / CPython 3.12.13. The input SHA-256 is
`a4f80d5a74835c35c8b2ffbc2eeb10a12844cb3ee572c32d38bf2f4731d92ee1`; source
digest `f61dec17bab469c808ab29bccb07f48340061ad3d73f8b540cad0b2b317a0e74`
includes the vendored Hyper encoder. The target was a dirty draft based on
`86e72e181d00feca1b4db7f30377d5d9d4345b83`; receipt:
`target/kata-progress/http1-header-order-source-bound-20261025.json`.
This proves one HTTP/1.1 case only. A later selected run of
`http1.response-headers-preserve-duplicate-value-order` changed that input's
operation to `http.response-headers-ordered` and passed 1/1 with Server and
Date defaults enabled (run `079d4c55793e4b2f92e65be7dd6d8468`, source digest
`d7b3c2db28624ae8c7a7019f1734d71a3c183ea94883c29c5f6bf12f8ff0779c`, receipt
`target/kata-progress/http1-response-headers-defaults-strict-20261025.json`).
This is a separate dirty-draft source-bound observation, not a rerun of the
full H1 matrix. Other H1 response cases still compare per-name values, and
H2/H3 order has not been verified by this patch.

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
other WebSocket settings, extension parameter combinations, fragmented
compressed messages, WebSockets over HTTP/2 or HTTP/3, or the broader Python
API contract.

## Per-message-deflate parity (2026-10-24)

The input-only cases `python-api.run-websocket-default-per-message-deflate` and
`python-api.run-websocket-disabled-per-message-deflate` compare the public
Python API with Uvicorn 0.54.0. The first selected two-case run showed that the
disabled setting passed while the default-compression case negotiated
compression but ended with close code 1006. After fixing the Yawc close-reply
flush path, the default case passed 1/1: compression negotiated, the text echo
arrived, and the close code was 1000. The disabled case was not rerun because
the fix only changes the compressed session close path.

Receipts are stored under the ignored
`target/kata-progress/ws-per-message-deflate-20261024/` directory. The final
single-case receipt is run `9e203dcc238f4126b4222c0a0a5f87c3` with SHA-256
`7773b653ebba80fdffd6c0e795c895637e72a9a47b3b69142c37edbc26b10d27`; its
dirty-source SHA-256 is
`503c0558a1f9c1df86ff9f82ce8c908b0045d74535a5198fe4d1f56da5389df9`.
This verifies one compressed text exchange and normal closure; other extension
parameters, fragmented compressed messages, and broader backend compatibility
remain open. The subsequent `rustfmt` pass changed layout only; current Rust
source SHA-256 is `b1baa699fdc0b1a385d3be0e4149bb8d45fdb3294f646c9e919db913389e6836`.
The formatted source passes `cargo check -p uvicorn-rs-py`; parity was not rerun
for this formatting-only edit.

## Default SansIO WebSocket queue option (2026-10-21)

This section records the implementation state on 2026-10-21; the 2026-10-25
legacy-backend queue support and receipt are documented above.

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

At the time, this confirmed option acceptance on the SansIO path and that the
independent message-size limit still worked. The later legacy-backend case above
adds one configurable queue-bound comparison; it does not establish general
queue or full backend parity.

## Focused server WebSocket keepalive parity (2026-10-21)

The input case `websocket.server-keepalive-ping-pong-timeout` starts Uvicorn
0.54.0 and uvicorn-rs through their CLI adapters with
`--ws-ping-interval 0.1 --ws-ping-timeout 0.3`. A raw RFC 6455 client
completes the handshake, reads a four-byte server Ping, returns its matching
Pong, reads the next Ping, withholds its Pong, and observes close code 1011
with reason `keepalive ping timeout`. The case passes 1/1 on macOS 15.7.7
ARM64 / CPython 3.12.13 with `websockets` 17.1. Receipt:
ignored `target/ws-keepalive-parity-focused.json`.

The same input was rerun after the timeout-cleanup refactor on the current
dirty source. It still passes 1/1 and records both server Pings, the Pong, and
the 1011 timeout close. The selected result is
`target/kata-progress/positive-timeout-coverage-20261023/parity-result-v1.json`,
run ID `776916a88b9f494dbd6b371f2d8287e8`, SHA-256
`4700a966a120a4b4633a948ffc8962ad66c6ad9b92f86c62fcdd8e1083ce8fe9`.

This verifies that one non-default CLI configuration and the Rust-owned
keepalive schedule match the pinned oracle for this exchange. Other timer
values, wire-level zero-interval ping suppression, direct `uvicorn.run()` and
`uvicorn_rs.Server` configuration, extension parameter combinations, fragmented
compressed messages, and WebSockets over HTTP/2 or HTTP/3 are not established
by this case.

The focused input `python-api.run-websocket-zero-ping-interval-disables-keepalive`
also exercises an active Python API WebSocket with `ws_ping_interval=0`: it
waits 0.35 seconds, exchanges an application message, and closes normally.
Oracle and target observations match 1/1 on macOS 15.7.7 ARM64 / CPython
3.12.13, with Uvicorn 0.54.0 and `websockets` 17.1. The selected result is
`target/kata-progress/zero-interval-coverage-20261023/parity-result-v2.json`,
run ID `c4df708d419142e1868739c047146440`, SHA-256
`9ceef30ed34c6ccb77c848f79efb52d0a9f8e3f1e2429a2644b3e0244c40632f`. This
checks that the connection remains usable after the configured interval; it
does not inspect Ping-frame emission or establish wire-level ping suppression.
It is selected-case evidence, not a full parity or coverage-gate result.

Two current-source CLI inputs also compare zero-valued keepalive settings:
`cli.websocket-ping-interval-zero-disables-keepalive-and-exits` sets
`--ws-ping-interval 0`, and `cli.websocket-zero-ping-timeout-is-accepted`
sets both `--ws-ping-interval 0` and `--ws-ping-timeout 0`. Each case passed
1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. The
oracle and target both exited 0 with empty stdout and stderr. Reports:
`target/kata-progress/9kbx-ws-keepalive-zero-20261027.json` (run
`5e9ad941c0cc432d988af55d3c963499`, SHA-256
`ade0a7fa56a11b1bcdb8495eed6ca964e517e9520575cc480f00da5824f3dd6d`) and
`target/kata-progress/9kbx-ws-zero-timeout-20261027.json` (run
`72d23479ab5c48a6b9c09ed3bad65c66`, SHA-256
`1af9260663bf5156f58298d06e216e06b46b5bf2b0530896b90666e7097af55b`). Both
receipts bind dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
CLI input@38 SHA-256
`058e6d836f2e87d9c7aff2e39557b0642574246bbaea429a8d384ed57848db53`, runner
SHA-256 `eac669579c55ba7ce905d4a03c387567d1fc079820c927126c419b1761998ad2`,
and native extension SHA-256
`8ebf16713c705f88f179b7dac26bedd71db606c30daf3c9392546f06548634d7`; all
155 recorded source files still match the checkout. These cases establish
CLI option acceptance and startup/exit behavior only. They do not observe
active WebSocket Ping frames or close the full CLI/API or cross-platform
compatibility gates.

The input `python-api.run-websocket-negative-ping-timeout-closes-1011` sets
`ws_ping_interval=0.1` and `ws_ping_timeout=-0.1`, waits for the server Ping,
and observes close code 1011 before the application message is delivered.
Oracle and target observations match 1/1 on macOS 15.7.7 ARM64 / CPython
3.12.13. The selected result is
`target/kata-progress/negative-timeout-coverage-20261023/parity-result-v2.json`,
run ID `2b5bf7f0715448039ca585832e8198df`, SHA-256
`c529fd308a4c9db2452b8f96de58d449fb86c99e561382ba81aed83687072ed4`. Its
instrumented profile reaches the immediate timeout handling path. This is
selected-case evidence, not a full parity or coverage-gate result.

Two further current-source Python API inputs exercise long keepalive delays:
`python-api.run-websocket-with-unbounded-ping-timeout` uses a finite timeout
of `1e300`, and `python-api.run-websocket-with-infinite-ping-interval` uses
`1e9999` (decoded by Python as positive infinity). Both match Uvicorn 0.54.0
for handshake, message exchange, normal close, and process exit. Their
combined selected unified coverage report is
`target/kata-progress/websocket-keepalive-large-delay-coverage-20261023/report.json`,
bound to source SHA-256
`8e87132998967f7e5ee53f74489f390f9ad44effa85265cb2f73f15af05e3263` and build
ID `c4201abea2113cbceba673100711a038479e23a0cddf4ec0df18ac50aee47372`. The
selection does not complete the full parity, coverage, or release gates; the
infinite-interval case does not observe wire-level Ping suppression.

## Existing UDS pathname replacement and lifespan cleanup

The selected input
`python-api.server-startup-uds-replaces-existing-socket-and-shuts-down-lifespan`
binds an active Unix-domain socket at the configured path before starting
`Server.serve()`. The implementation removes an existing pathname only when it
refers to a Unix socket, matching Uvicorn's replacement behavior while leaving
regular files for the bind error path. The input compares startup, completion,
exception/timeout state, exit status, and lifespan events; it does not send an
HTTP request through the replacement listener.

The case passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
3.12.13 / Rust 1.98.1 (run `77810df8d13f4d6fbca2bf2a6e796580`; receipt
`target/asgi-parity/uds-replacement-one-case.json`, SHA-256
`600c69da81ec30df304892ef2f8dd1059562b7f6f5dc0d57666a37737b38c5e5`). Oracle
and target both started, completed the serve task, exited 0, and observed
`lifespan.startup` followed by `lifespan.shutdown`, with no exception or
timeout. The receipt binds to dirty target revision
`5b1ec29201c963d8590c989b07318bb7366d7922` (`dirty=true`), Python API input
SHA-256 `1c9f06464bc0e69ce517eebefbe36fea27c77090255d582eb17362476d072a9c`,
manifest SHA-256
`38501024e8a41fe41c905f04890a9131ea8da098dc84deb70f280d1751a3384f`, and
native extension SHA-256
`07807ccd278f6b5cfb23d311c1751b18edfbc5705011937a822e8226956254fd`.

This is one selected local case on one platform. It is not clean-source or
hosted release evidence and does not establish other UDS lifecycle, platform,
TLS, HTTP/2, or HTTP/3 behavior.

## Keep benchmark oracle files separate

The candidate distribution and upstream Uvicorn both provide files under the
`uvicorn` import name. Never install both distributions into one benchmark or
parity environment: the resulting imports can depend on installation order.
The project `.venv` contains the `uvicorn-rs` distribution; the oracle environment contains
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
oracle version, Python version, import origin, absence of the `uvicorn-rs` distribution, and
installed Uvicorn file hashes before starting a comparison.

## Focused PKCS#12 PBE-SHA1-3DES key parity — 2026-10-27

Added the Config/Server input
`python-api.config-server-uses-pkcs12-pbe-sha1-3des-key`. It passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. Both
implementations loaded the same PKCS#8 private key encrypted with
`pbeWithSHA1And3-KeyTripleDES-CBC`, served HTTP 200, received SIGINT, and exited
cleanly. The focused Rust decrypt path supports this one PKCS#12 PBE OID; other
legacy PBE algorithms and full TLS/platform parity remain unverified.

Receipt: `target/kata-progress/x3az-pkcs12-pbe-sha1-3des-20261027.json`, SHA-256
`a1adc6563459eb7520cd2ea0e24598e3c9aed89447f09adda731adb2eaf95929`. It binds
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, Python API input
SHA-256 `a003111db711f02cda5ae40f888a6142ffbab2fe155ac8bea3f3795921ac458d`,
`src/lib.rs` SHA-256
`9f66996ee8df59fb54540cab41e813352f98f4dc6dd276ed8480871e8ceffb1b`, and
native extension SHA-256
`e7ab61a231ba2c79575f6316d9c8ff55471f1772ec266d4be1bcc45a545e28b8`. This is
one selected dirty-source behavior and does not qualify the full compatibility
matrix or release candidate.

## Complete installed-wheel public parity after lifespan timeout fix — 2026-10-27

The first complete installed-wheel run identified one lifecycle mismatch in
`lifespan.post-response-background-task-cancelled-before-server-return`:
after a one-second request-drain timeout cancelled the held request, the target
skipped the ASGI lifespan shutdown handshake that Uvicorn completed. The
failing case reproduced in isolation. `src/lib.rs` now always performs the
lifespan shutdown handshake after request cancellation. The focused case and
four related graceful-timeout inputs passed on the rebuilt wheel.

The final current-source wheel then passed the complete declared public parity
inventory: 580/580 cases, zero behavior or infrastructure failures, zero not
run. It was built and installed in a fresh environment separate from the
Uvicorn 0.54.0 oracle. Receipt:
`target/kata-progress/installed-parity-current-source-20261027/installed-full-parity-after-lifespan-fix.json`,
run `9f5d8332dbd842b08e52372571b0eee2`, report SHA-256
`b9ea5b0062a935406fcb45fc8579d3a370470776cb07d82a148bf92a743b7153`. The
abi3 wheel SHA-256 is
`8b424d96785e22df63f429104783446ecff81f9136ec15ce4ae64098df4de9fd`.

This receipt binds to dirty revision
`5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`, native
extension SHA-256
`74fd52144fbc0b168db90da59de02cffaf5e1a037995beb2a3b6b2792a523535`, and
manifest SHA-256 `ede173a29d162a002ee37d469f1ecaeeafa5d8e97c15c5bfbc67157b55c6f9be`.
Environment: macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. Offline
evidence validation passed with `scripts/check_ci_evidence.py parity --offline`.
This covers local public oracle parity only; the supported OS/Python matrix,
349 target-only fault contracts, 258 native-core contracts, and clean exact-main
release evidence remain open.

## Module-CLI environment parity — 2026-10-27

Six selected cases pass against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 /
CPython 3.12.13 / Rust 1.98.1: `python-api.module-cli-listener-host-port-from-environment`
binds with `UVICORN_HOST=0.0.0.0` and a dynamically reserved `UVICORN_PORT`
and serves HTTP 200; `python-api.module-cli-concurrency-limit-from-environment`
uses `UVICORN_LIMIT_CONCURRENCY=1` and returns HTTP 503 on both implementations;
`python-api.module-cli-explicit-concurrency-limit-overrides-invalid-environment`
uses `--limit-concurrency 2` to override a malformed environment value and
serves HTTP 200; `python-api.module-cli-explicit-concurrency-limit-overrides-valid-environment`
uses the same CLI limit over `UVICORN_LIMIT_CONCURRENCY=1`, returns HTTP 200,
and confirms the explicit argument takes precedence; `python-api.module-cli-uses-wsgi-interface-from-environment`
selects the WSGI adapter through `UVICORN_INTERFACE=wsgi` and serves HTTP 200
against the WSGI fixture on both implementations; `python-api.module-cli-explicit-interface-overrides-environment`
uses `--interface asgi3` over the conflicting valid `UVICORN_INTERFACE=wsgi`
value and serves the ASGI3 fixture with HTTP 200. All six processes exit 0
after SIGINT, and the normalized observations match.

Run `6bccbbc39531471f9d5c191bd6a77507`; receipt
`target/kata-progress/python-api-cli-environment-parity-20261027.json`, SHA-256
`eaba087fc44e031c275394917555f2398af6f03ee2e2d16c23c61d6cbc190533`.
It binds Python API input@42 SHA-256
`3e9e033ea06125c39f22c0eecdf8fdf30232894f1a5c61bc54617531a1707753`,
dirty target revision `8b1f90752b092c447ad4e22b20fe477ae8fe6951`, runner SHA-256
`f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`, and
probe SHA-256 `5dcfc30c60f59c6340a519114820d9a19d5e402a4d689883ef398d21075e9809`.
The `@probe-port` value is replaced with the reserved listener port before the
child starts; it is not a Uvicorn setting. This is selected single-platform
evidence; the complete input@42 profile, other supported platforms, and exact
release-candidate parity remain open.

## User-facing status

The install/rollback steps and current limitations are on the
[Uvicorn replacement page](../uvicorn-compatibility.md). The live ASGI
protocol results remain in the [support matrix](../support-matrix.md).
