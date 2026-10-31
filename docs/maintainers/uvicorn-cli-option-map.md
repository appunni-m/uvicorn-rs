# Uvicorn 0.54.0 CLI and settings map

This is the reviewed parameter-to-input map for Kata `9kbx`. The declared public surface comes from `python/uvicorn/main.py`, pinned to the Uvicorn 0.54.0 contract. Input references are stimuli; only passing receipts establish behavior.

## Current evidence identity

- Denominator: 1 positional argument (`APP`) + 51 declared Click options = **52 parameters**. Click adds `--help` automatically; it is included in the CLI input matrix but is not a declaration in `main.py`.
- The CLI process input file is `tests/parity/inputs/cli.json`, schema `uvicorn-rs-parity/input@47`, with **118 cases** and SHA-256 `d569964a28c49161b60eddf2b8262c901cf0071b15cc93443b98f67048c32002`.
- Commit `6342b20402bf0cceabd8eafde3f067e1620bafba` fixes the h11 incomplete-header limit in the adapter and Rust parser. Its runtime-source SHA-256 is `c00038a3885178b4bb1146fc315a51eb70c5e149a1742a16d3bdada8c7bee50f`. Local focused receipts are diagnostic subset evidence; the clean hosted matrix must validate the committed source.
- The preceding full installed-wheel parity on macOS ARM64 / CPython 3.12.13 passed **719/719**, including all **118/118** CLI process cases. Receipt run `4f0fd48142f34ddd931639928a6daf4d`, report SHA-256 `17215002f939d255069c6fef20f0c1cd43ca1d17e981e2c29d2e6edbb6a07780`. It predates the six module-CLI WebSocket inputs, four h11 boundary inputs and runtime fix below; it is historical evidence for that earlier source and input set.
- Linux full parity passed 719/719 on the preceding input set. Windows’ three failures were worker-shutdown cases, not CLI process cases; the updated worker inputs passed the focused current-input group on Windows and Linux. The six new WebSocket cases passed their selected local comparison 6/6 on the preceding runtime. The current h11 group passed 5/5. A full hosted matrix for the committed source and complete input set remains open under `x3az`.

## Click parameter map

`UVICORN_*` bindings use the Click destination with `auto_envvar_prefix="UVICORN"`. The table records the effective value when an option is omitted. For parameters whose decorator omits `default`, Click stores `Sentinel.UNSET`; `multiple=True` options resolve to `()`, and a flag resolves to `False`. The last column assigns every parameter to the case group below; the [input index](#cli-process-input-index) lists each argv flag and environment key for all 118 CLI process cases.

| Parameter and aliases | Destination | Type / choice | Value when omitted | Environment binding | Case group |
| --- | --- | --- | --- | --- | --- |
| `<APP>` | `app` | `required positional import string` | `required unless supplied through environment` | `UVICORN_APP` | [app-loading](#app-loading) |
| `--host` | `host` | `str` | `'127.0.0.1'` | `UVICORN_HOST` | [listeners](#listeners) |
| `--port` | `port` | `int` | `8000` | `UVICORN_PORT` | [listeners](#listeners) |
| `--uds` | `uds` | `str` | `None` | `UVICORN_UDS` | [listeners](#listeners) |
| `--fd` | `fd` | `int` | `None` | `UVICORN_FD` | [listeners](#listeners) |
| `--reload` | `reload` | `bool` | `False` | `UVICORN_RELOAD` | [supervision](#supervision) |
| `--reload-dir` | `reload_dirs` | `click.Path(exists=True)` | `Sentinel.UNSET` → `()` | `UVICORN_RELOAD_DIRS` | [supervision](#supervision) |
| `--reload-include` | `reload_includes` | `str` | `Sentinel.UNSET` → `()` | `UVICORN_RELOAD_INCLUDES` | [supervision](#supervision) |
| `--reload-exclude` | `reload_excludes` | `str` | `Sentinel.UNSET` → `()` | `UVICORN_RELOAD_EXCLUDES` | [supervision](#supervision) |
| `--reload-delay` | `reload_delay` | `float` | `0.25` | `UVICORN_RELOAD_DELAY` | [supervision](#supervision) |
| `--workers` | `workers` | `int` | `None` | `UVICORN_WORKERS` | [supervision](#supervision) |
| `--loop` | `loop` | `str` | `'auto'` | `UVICORN_LOOP` | [protocol-selection](#protocol-selection) |
| `--http` | `http` | `str` | `'auto'` | `UVICORN_HTTP` | [protocol-selection](#protocol-selection) |
| `--http2` | `http2` | `bool` | `False` | `UVICORN_HTTP2` | [protocol-selection](#protocol-selection) |
| `--ws` | `ws` | `str` | `'auto'` | `UVICORN_WS` | [protocol-selection](#protocol-selection) |
| `--ws-max-size` | `ws_max_size` | `int` | `16777216` | `UVICORN_WS_MAX_SIZE` | [websocket](#websocket) |
| `--ws-max-queue` | `ws_max_queue` | `int` | `32` | `UVICORN_WS_MAX_QUEUE` | [websocket](#websocket) |
| `--ws-ping-interval` | `ws_ping_interval` | `float` | `20.0` | `UVICORN_WS_PING_INTERVAL` | [websocket](#websocket) |
| `--ws-ping-timeout` | `ws_ping_timeout` | `float` | `20.0` | `UVICORN_WS_PING_TIMEOUT` | [websocket](#websocket) |
| `--ws-per-message-deflate` | `ws_per_message_deflate` | `bool` | `True` | `UVICORN_WS_PER_MESSAGE_DEFLATE` | [websocket](#websocket) |
| `--lifespan` | `lifespan` | `auto \| on \| off` | `'auto'` | `UVICORN_LIFESPAN` | [protocol-selection](#protocol-selection) |
| `--interface` | `interface` | `auto \| asgi3 \| asgi2 \| wsgi` | `'auto'` | `UVICORN_INTERFACE` | [protocol-selection](#protocol-selection) |
| `--env-file` | `env_file` | `click.Path(exists=True)` | `None` | `UVICORN_ENV_FILE` | [app-loading](#app-loading) |
| `--log-config` | `log_config` | `click.Path(exists=True)` | `None` | `UVICORN_LOG_CONFIG` | [logging](#logging) |
| `--log-level` | `log_level` | `critical \| error \| warning \| info \| debug \| trace` | `None` | `UVICORN_LOG_LEVEL` | [logging](#logging) |
| `--access-log/--no-access-log` | `access_log` | `bool` | `True` | `UVICORN_ACCESS_LOG` | [logging](#logging) |
| `--use-colors/--no-use-colors` | `use_colors` | `bool` | `None` | `UVICORN_USE_COLORS` | [logging](#logging) |
| `--proxy-headers/--no-proxy-headers` | `proxy_headers` | `bool` | `True` | `UVICORN_PROXY_HEADERS` | [request-response](#request-response) |
| `--server-header/--no-server-header` | `server_header` | `bool` | `True` | `UVICORN_SERVER_HEADER` | [request-response](#request-response) |
| `--date-header/--no-date-header` | `date_header` | `bool` | `True` | `UVICORN_DATE_HEADER` | [request-response](#request-response) |
| `--forwarded-allow-ips` | `forwarded_allow_ips` | `str` | `None` | `UVICORN_FORWARDED_ALLOW_IPS` | [request-response](#request-response) |
| `--root-path` | `root_path` | `str` | `''` | `UVICORN_ROOT_PATH` | [request-response](#request-response) |
| `--limit-concurrency` | `limit_concurrency` | `int` | `None` | `UVICORN_LIMIT_CONCURRENCY` | [limits](#limits) |
| `--backlog` | `backlog` | `int` | `2048` | `UVICORN_BACKLOG` | [listeners](#listeners) |
| `--limit-max-requests` | `limit_max_requests` | `int` | `None` | `UVICORN_LIMIT_MAX_REQUESTS` | [supervision](#supervision) |
| `--limit-max-requests-jitter` | `limit_max_requests_jitter` | `int` | `0` | `UVICORN_LIMIT_MAX_REQUESTS_JITTER` | [supervision](#supervision) |
| `--timeout-keep-alive` | `timeout_keep_alive` | `int` | `5` | `UVICORN_TIMEOUT_KEEP_ALIVE` | [limits](#limits) |
| `--timeout-graceful-shutdown` | `timeout_graceful_shutdown` | `int` | `None` | `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` | [supervision](#supervision) |
| `--timeout-worker-healthcheck` | `timeout_worker_healthcheck` | `int` | `5` | `UVICORN_TIMEOUT_WORKER_HEALTHCHECK` | [supervision](#supervision) |
| `--ssl-keyfile` | `ssl_keyfile` | `str` | `None` | `UVICORN_SSL_KEYFILE` | [tls](#tls) |
| `--ssl-certfile` | `ssl_certfile` | `str` | `None` | `UVICORN_SSL_CERTFILE` | [tls](#tls) |
| `--ssl-keyfile-password` | `ssl_keyfile_password` | `str` | `None` | `UVICORN_SSL_KEYFILE_PASSWORD` | [tls](#tls) |
| `--ssl-version` | `ssl_version` | `int` | `int(SSL_PROTOCOL_VERSION)` | `UVICORN_SSL_VERSION` | [tls](#tls) |
| `--ssl-cert-reqs` | `ssl_cert_reqs` | `int` | `int(ssl.CERT_NONE)` | `UVICORN_SSL_CERT_REQS` | [tls](#tls) |
| `--ssl-ca-certs` | `ssl_ca_certs` | `str` | `None` | `UVICORN_SSL_CA_CERTS` | [tls](#tls) |
| `--ssl-ciphers` | `ssl_ciphers` | `str` | `None` | `UVICORN_SSL_CIPHERS` | [tls](#tls) |
| `--header` | `headers` | `str` | `() (Click multiple default)` | `UVICORN_HEADERS` | [request-response](#request-response) |
| `--version` | `version` | `bool` | `Sentinel.UNSET` → `False` | `UVICORN_VERSION` | [ASGI context and diagnostics](#asgi-context-and-diagnostics) |
| `--app-dir` | `app_dir` | `str` | `''` | `UVICORN_APP_DIR` | [app-loading](#app-loading) |
| `--h11-max-incomplete-event-size` | `h11_max_incomplete_event_size` | `int` | `None` | `UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE` | [http1](#http1) |
| `--reset-contextvars` | `reset_contextvars` | `bool` | `False` | `UVICORN_RESET_CONTEXTVARS` | [ASGI context and diagnostics](#asgi-context-and-diagnostics) |
| `--factory` | `factory` | `bool` | `False` | `UVICORN_FACTORY` | [app-loading](#app-loading) |

## Case groups and assertions

CLI process cases invoke the pinned oracle and installed candidate through either `python -m uvicorn` or the `uvicorn` console script. The `cli.process` operation compares exit code and stdout exactly and applies the declared normalization to Python traceback paths in stderr. These cases retain argv, environment, stdout, stderr and exit status in the parity report.

Cases in `python-api.json` with `invocation: "module-cli"` launch the real CLI, send HTTP requests, and observe responses, scope, logs, startup, lifecycle, and process exit. The `python_api_probe.py` command builder makes the Click flags explicit from each typed input. A successful parse/startup-only process case is not counted as proof of a serving effect.

### `app-loading`

Parameters: `APP`, `--factory`, `--app-dir`, `--env-file`, `--interface`.

- Inputs: `cli.no-arguments-requires-app`, `cli.explicit-app-over-environment`, `cli.uvicorn-app-env-resolves-app-dir-target`, `cli.app-dir-resolves-import-before-reporting-missing-attribute`, `cli.explicit-app-dir-overrides-environment`, `cli.factory-type-error-is-startup-failure`, `cli.factory-from-environment-starts-server`, `cli.explicit-factory-overrides-false-environment`, and the `cli.env-file-*` group.
- Live module-CLI behavior: `python-api.module-cli-serves-successful-application-factory`, `python-api.module-cli-serves-asgi2-application-factory`, `python-api.module-cli-auto-detects-asgi3-application-factory`, and `python-api.module-cli-serves-successful-wsgi-application-factory`.
- `APP` uses positional precedence over `UVICORN_APP`; env-file values load before the factory, while server options are not read from the application env file.

### `listeners`

Parameters: `--host`, `--port`, `--uds`, `--fd`, `--backlog`.

- Process validation/precedence: `cli.invalid-port-value`, `cli.invalid-port-env-is-rejected`, `cli.explicit-port-over-invalid-env-starts-server`, `cli.explicit-host-over-invalid-env-starts-server`, `cli.invalid-file-descriptor-is-rejected`, `cli.invalid-fd-environment-is-rejected`, `cli.uds-startup-and-clean-exit`, `cli.uds-from-environment-starts-and-cleans`, and `cli.invalid-backlog-environment-is-rejected` / `cli.explicit-backlog-over-invalid-environment`.
- Live module-CLI behavior: `python-api.module-cli-listener-host-port-from-environment`, `python-api.module-cli-serves-unix-domain-socket-request`, `python-api.module-cli-serves-request-on-inherited-fd`, `python-api.module-cli-serves-request-on-inherited-ipv6-fd`, `python-api.module-cli-inherited-fd-from-uvicorn-environment`, `python-api.module-cli-two-workers-serves-inherited-fd-request`, and `python-api.module-cli-custom-backlog-serves-request`.

### `protocol-selection`

Parameters: `--loop`, `--http`, `--http2`, `--ws`, `--lifespan`, `--interface`.

- Process validation: `cli.invalid-loop-environment-is-rejected`, `cli.explicit-loop-over-invalid-environment`, `cli.invalid-http-selector-is-rejected`, `cli.invalid-http-selector-environment-is-rejected`, `cli.explicit-http-over-invalid-environment`, `cli.invalid-websocket-selector-is-rejected`, `cli.explicit-websocket-selector-over-invalid-environment`, `cli.invalid-lifespan-selector-is-rejected`, `cli.invalid-interface-selector-is-rejected`, and `cli.explicit-interface-over-invalid-environment`.
- Live module-CLI behavior: `python-api.module-cli-h11-backend-serves-request`, `python-api.module-cli-explicit-asgi2-interface`, `python-api.module-cli-uses-wsgi-interface-from-environment`, `python-api.module-cli-http-with-lifespan-disabled`, and `cli.custom-loop-factory-is-invoked`.
- Uvicorn 0.54.0 declares `--http2` (default `false`) and requires its experimental `zttp` backend. The pinned live HTTP/2 oracle selects `--http zttp --http2`; uvicorn-rs handles the transport in Rust. Backend validation and the maintained HTTP/2 cases establish only their declared observations.

### `websocket`

Parameters: `--ws`, `--ws-max-size`, `--ws-max-queue`, `--ws-ping-interval`, `--ws-ping-timeout`, `--ws-per-message-deflate`.

- Current CLI process cases cover invalid selector and environment values, explicit overrides, and startup acceptance: `cli.invalid-websocket-selector-is-rejected`, `cli.ws-websockets-sansio-preserves-app-load-diagnostic`, `cli.wsproto-preserves-app-load-diagnostic`, `cli.sansio-ws-size-and-queue-preserve-app-load-diagnostic`, `cli.websocket-ping-interval-zero-disables-keepalive-and-exits`, and `cli.websocket-zero-ping-timeout-is-accepted`.
- Six added live module-CLI cases now exercise message-size close code 1009, explicit `wsproto` exchange, a bounded legacy-backend queue with a delayed reader, observed server Ping and timeout close code 1011, and enabled/disabled per-message-deflate negotiation: `python-api.module-cli-websocket-message-size-limit`, `python-api.module-cli-websocket-wsproto-exchange`, `python-api.module-cli-websocket-bounded-queue-drains-burst`, `python-api.module-cli-websocket-server-ping-interval`, `python-api.module-cli-websocket-default-per-message-deflate`, and `python-api.module-cli-websocket-disabled-per-message-deflate`. The selected macOS ARM64 / CPython 3.12.13 comparison passed 6/6 with zero failed, infrastructure-failed or not-run cases; report `target/kata-progress/9kbx-module-cli-websocket-final.json`, SHA-256 `27bbcc0be8e93da26638b0cb550f7208dd4ce15e5a3ff23d738aca6e8a748f0f`. This receipt predates the h11 runtime fix. Disabling deflate uses `UVICORN_WS_PER_MESSAGE_DEFLATE=false`; upstream Click does not provide a negative flag.

### `supervision`

Parameters: `--reload`, `--reload-dir`, `--reload-include`, `--reload-exclude`, `--reload-delay`, `--workers`, `--limit-max-requests`, `--limit-max-requests-jitter`, `--timeout-graceful-shutdown`, `--timeout-worker-healthcheck`.

- Process validation/precedence: `cli.explicit-workers-over-invalid-environment`, `cli.zero-workers-normalizes-to-single-worker`, `cli.explicit-reload-delay-over-invalid-environment`, `cli.invalid-reload-dir-environment-is-rejected`, `cli.explicit-reload-dir-over-invalid-environment`, `cli.timeout-graceful-shutdown-valid-value-exits-after-startup`, and the malformed/explicit override cases for request limits and timeout values.
- Live module-CLI behavior: `python-api.module-cli-reload-restarts-after-watched-module-change`, `python-api.module-cli-reload-respects-include-exclude-globs`, `python-api.module-cli-explicit-reload-filters-override-environment`, `python-api.module-cli-limit-max-requests-exits-after-one-response`, `python-api.module-cli-limit-max-requests-jitter-stays-in-configured-range`, `python-api.module-cli-timeout-keep-alive-closes-idle-connection`, `python-api.module-cli-graceful-timeout-flag-cancels-inflight-request`, `python-api.module-cli-posix-unresponsive-worker-healthcheck-restarts`, and the worker restart/shutdown cases owned by `dhfq`.

### `request-response`

Parameters: `--proxy-headers`, `--forwarded-allow-ips`, `--server-header`, `--date-header`, `--header`, `--root-path`.

- Live module-CLI behavior: `python-api.module-cli-applies-trusted-proxy-headers`, `python-api.module-cli-disables-proxy-headers`, `python-api.module-cli-forwarded-allow-ips-from-uvicorn-environment`, `python-api.module-cli-explicit-forwarded-allow-ips-overrides-uvicorn-environment`, `python-api.module-cli-disables-server-and-date-headers`, `python-api.module-cli-explicit-server-date-headers-overrides-environment`, `python-api.module-cli-appends-custom-response-header`, `python-api.module-cli-explicit-header-overrides-uvicorn-environment`, `python-api.module-cli-applies-root-path`, and `python-api.module-cli-explicit-root-path-over-envvar`.
- `FORWARDED_ALLOW_IPS` is the runtime default for trusted proxies; `UVICORN_FORWARDED_ALLOW_IPS` is the Click-derived override.

### `limits`

Parameters: `--limit-concurrency`, `--timeout-keep-alive` (see also the supervision cases for request limits and shutdown).

- Live module-CLI behavior: `python-api.module-cli-applies-concurrency-limit`, `python-api.module-cli-explicit-concurrency-limit-overrides-valid-environment`, `python-api.module-cli-timeout-keep-alive-closes-idle-connection`.

### `tls`

Parameters: `--ssl-keyfile`, `--ssl-certfile`, `--ssl-keyfile-password`, `--ssl-version`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers`.

- Process inputs: `cli.console-h11-and-tls-settings-start-server`, `cli.explicit-ssl-options-over-invalid-environment`, `cli.invalid-ssl-version-environment-is-rejected`, and `cli.invalid-ssl-cert-reqs-environment-is-rejected`.
- Live module-CLI behavior: `python-api.module-cli-tls-from-uvicorn-environment`, `python-api.module-cli-uses-pkcs8-keyfile-password`, `python-api.module-cli-requires-trusted-client-certificate-tls12`, and `python-api.module-cli-serves-tls-over-unix-domain-socket`.

### `logging`

Parameters: `--log-config`, `--log-level`, `--access-log`, `--use-colors`.

- Process validation/output: `cli.invalid-log-level-is-rejected`, `cli.invalid-log-level-environment-is-rejected`, `cli.explicit-log-level-over-invalid-environment`, `cli.custom-json-log-config-formats-app-load-diagnostic`, `cli.use-colors-forces-colored-import-diagnostic`, and `cli.factory-type-error-forced-color-diagnostic`.
- Live module-CLI behavior: `python-api.module-cli-applies-custom-json-log-config`, `python-api.module-cli-applies-custom-ini-log-config`, `python-api.module-cli-applies-custom-yaml-log-config`, `python-api.module-cli-uses-log-level-from-environment`, `python-api.module-cli-disables-access-log`, `python-api.module-cli-explicit-access-log-overrides-environment`, and `python-api.module-cli-forces-colored-server-logs`.

### `http1`

Parameter: `--h11-max-incomplete-event-size`.

- Process validation/precedence: `cli.invalid-h11-size-environment-is-rejected`, `cli.explicit-h11-size-over-invalid-environment`, `cli.explicit-default-runtime-options-are-accepted`, and `cli.console-h11-and-tls-settings-start-server`.
- Live module-CLI cases cover an incomplete header at exactly the configured maximum and one byte over, at both 1,024 and 8,192 bytes. The exact size remains connected without a response; one byte over receives HTTP 400 and closes, matching Uvicorn 0.54.0. The adapter permits the final byte, selects the upstream 16 KiB default when unset, and accepts smaller positive limits. The native configuration still rejects a zero physical buffer.
- The four boundary cases and existing expanded-header case pass 5/5 locally on macOS ARM64 / CPython 3.12.13, zero failed/infra/not-run. Report `target/kata-progress/9kbx-h11-final.json`, run `4e60b47b7f194528b326a9619456db01`, SHA-256 `3850085052d81114891c617ea7fdf101b4cd2734dc8de49412c8bf6c46de6f06`. This is dirty-draft subset evidence, pending the full clean hosted matrix.

### `asgi-context` and `diagnostics`

`--reset-contextvars` has live HTTP behavior cases `python-api.module-cli-reset-contextvars-clears-http-request-context` and `python-api.module-cli-reset-contextvars-explicit-flag-overrides-environment`. `--version` and `--help` have module and console output cases `cli.help`, `cli.console-help`, `cli.version`, `cli.console-version`, and `cli.version-from-environment`.

## CLI process input index

Every row below is read from the 118 input-only process cases. The exact argument values remain in `cli.json`; this table indexes option flags and environment names without duplicating values.

| Case ID | Invocation | argv options | Environment names |
| --- | --- | --- | --- |
| `cli.help` | `module` | `--help` | — |
| `cli.no-arguments-requires-app` | `module` | — | — |
| `cli.console-help` | `console` | `--help` | — |
| `cli.console-cwd-import-resolution-before-missing-attribute` | `console` | `<APP>` | — |
| `cli.version` | `module` | `--version` | — |
| `cli.console-version` | `console` | `--version` | — |
| `cli.invalid-port-value` | `module` | `<APP>`, `--port` | — |
| `cli.invalid-file-descriptor-is-rejected` | `module` | `<APP>`, `--fd`, `--log-level` | — |
| `cli.uds-startup-and-clean-exit` | `module` | `<APP>`, `--uds`, `--lifespan`, `--limit-max-requests`, `--log-level` | — |
| `cli.invalid-log-level-is-rejected` | `module` | `<APP>`, `--log-level` | — |
| `cli.invalid-log-level-environment-is-rejected` | `module` | `<APP>` | `UVICORN_LOG_LEVEL` |
| `cli.explicit-log-level-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_LOG_LEVEL` |
| `cli.invalid-interface-selector-is-rejected` | `module` | `<APP>`, `--interface` | — |
| `cli.invalid-interface-environment-is-rejected` | `module` | `<APP>`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_INTERFACE` |
| `cli.explicit-interface-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_INTERFACE` |
| `cli.invalid-lifespan-selector-is-rejected` | `module` | `<APP>`, `--lifespan` | — |
| `cli.invalid-http-selector-is-rejected` | `module` | `<APP>`, `--http` | — |
| `cli.invalid-websocket-selector-is-rejected` | `module` | `<APP>`, `--ws` | — |
| `cli.explicit-port-over-invalid-env` | `module` | `<APP>`, `--port`, `--version` | `UVICORN_PORT` |
| `cli.explicit-port-over-invalid-env-starts-server` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_PORT` |
| `cli.explicit-host-over-invalid-env-starts-server` | `module` | `<APP>`, `--interface`, `--lifespan`, `--host`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_HOST` |
| `cli.invalid-host-env-is-rejected` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_HOST` |
| `cli.app-dir-resolves-import-before-reporting-missing-attribute` | `module` | `<APP>`, `--app-dir` | — |
| `cli.app-dir-environment-resolves-import-before-reporting-missing-attribute` | `module` | `<APP>` | `UVICORN_APP_DIR` |
| `cli.explicit-app-dir-overrides-environment` | `module` | `<APP>`, `--app-dir` | `UVICORN_APP_DIR` |
| `cli.factory-type-error-is-startup-failure` | `module` | `<APP>`, `--app-dir`, `--factory` | — |
| `cli.factory-type-error-forced-color-diagnostic` | `module` | `<APP>`, `--app-dir`, `--factory`, `--use-colors` | — |
| `cli.implicit-factory-warning-forced-colors` | `module` | `<APP>`, `--use-colors`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | — |
| `cli.env-file-loads-before-factory` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | — |
| `cli.env-file-environment-loads-before-factory` | `module` | `<APP>`, `--app-dir`, `--factory` | `UVICORN_ENV_FILE` |
| `cli.explicit-env-file-overrides-environment` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | `UVICORN_ENV_FILE` |
| `cli.env-file-forced-color-diagnostics` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file`, `--use-colors` | — |
| `cli.env-file-preserves-process-environment` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | `UVICORN_RS_PARITY_FACTORY_SENTINEL` |
| `cli.env-file-value-reaches-application-factory` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | `UVICORN_RS_PARITY_FACTORY_SENTINEL` |
| `cli.env-file-parses-export-quotes-and-interpolation` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | — |
| `cli.env-file-does-not-set-uvicorn-server-options` | `module` | `<APP>`, `--app-dir`, `--factory`, `--env-file` | `UVICORN_PORT`, `UVICORN_RS_PARITY_FACTORY_SENTINEL` |
| `cli.uvicorn-app-env-resolves-app-dir-target` | `module` | `<APP>`, `--app-dir` | `UVICORN_APP` |
| `cli.invalid-port-env-with-version` | `module` | `<APP>`, `--version` | `UVICORN_PORT` |
| `cli.invalid-port-env-is-rejected` | `module` | `<APP>` | `UVICORN_PORT` |
| `cli.invalid-limit-concurrency-env-is-rejected` | `module` | `<APP>` | `UVICORN_LIMIT_CONCURRENCY` |
| `cli.limit-max-requests-jitter-is-accepted-before-app-load` | `module` | `<APP>`, `--limit-max-requests-jitter` | — |
| `cli.invalid-limit-max-requests-environment-is-rejected` | `module` | `<APP>` | `UVICORN_LIMIT_MAX_REQUESTS` |
| `cli.explicit-limit-max-requests-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_LIMIT_MAX_REQUESTS` |
| `cli.invalid-limit-max-requests-jitter-environment-is-rejected` | `module` | `<APP>` | `UVICORN_LIMIT_MAX_REQUESTS_JITTER` |
| `cli.explicit-limit-max-requests-jitter-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--limit-max-requests-jitter` | `UVICORN_LIMIT_MAX_REQUESTS_JITTER` |
| `cli.invalid-backlog-environment-is-rejected` | `module` | `<APP>` | `UVICORN_BACKLOG` |
| `cli.explicit-backlog-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--backlog`, `--limit-max-requests` | `UVICORN_BACKLOG` |
| `cli.invalid-timeout-keep-alive-environment-is-rejected` | `module` | `<APP>` | `UVICORN_TIMEOUT_KEEP_ALIVE` |
| `cli.explicit-timeout-keep-alive-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--timeout-keep-alive`, `--limit-max-requests` | `UVICORN_TIMEOUT_KEEP_ALIVE` |
| `cli.invalid-timeout-worker-healthcheck-environment-is-rejected` | `module` | `<APP>` | `UVICORN_TIMEOUT_WORKER_HEALTHCHECK` |
| `cli.explicit-timeout-worker-healthcheck-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--timeout-worker-healthcheck`, `--limit-max-requests` | `UVICORN_TIMEOUT_WORKER_HEALTHCHECK` |
| `cli.invalid-timeout-graceful-shutdown-env-is-rejected` | `module` | `<APP>` | `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` |
| `cli.invalid-timeout-graceful-shutdown-argument-is-rejected` | `module` | `<APP>`, `--timeout-graceful-shutdown` | — |
| `cli.timeout-graceful-shutdown-valid-value-exits-after-startup` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--timeout-graceful-shutdown`, `--limit-max-requests` | — |
| `cli.explicit-graceful-shutdown-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--timeout-graceful-shutdown`, `--limit-max-requests` | `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` |
| `cli.timeout-graceful-shutdown-valid-environment-value-exits-after-startup` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN` |
| `cli.invalid-ws-max-size-env-is-rejected` | `module` | `<APP>` | `UVICORN_WS_MAX_SIZE` |
| `cli.explicit-ws-max-size-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws-max-size`, `--limit-max-requests` | `UVICORN_WS_MAX_SIZE` |
| `cli.invalid-ws-ping-timeout-env-is-rejected` | `module` | `<APP>` | `UVICORN_WS_PING_TIMEOUT` |
| `cli.explicit-ws-ping-timeout-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws-ping-interval`, `--ws-ping-timeout`, `--limit-max-requests` | `UVICORN_WS_PING_TIMEOUT` |
| `cli.import-missing-module-diagnostic` | `module` | `<APP>` | — |
| `cli.use-colors-forces-colored-import-diagnostic` | `module` | `<APP>`, `--use-colors` | — |
| `cli.explicit-app-over-environment` | `module` | `<APP>` | `UVICORN_APP` |
| `cli.http-auto-preserves-app-load-diagnostic` | `module` | `<APP>`, `--http` | — |
| `cli.http-httptools-preserves-app-load-diagnostic` | `module` | `<APP>`, `--http` | — |
| `cli.http-h11-preserves-app-load-diagnostic` | `module` | `<APP>`, `--http` | — |
| `cli.websocket-auto-preserves-app-load-diagnostic` | `module` | `<APP>`, `--ws` | — |
| `cli.ws-websockets-sansio-preserves-app-load-diagnostic` | `module` | `<APP>`, `--ws` | — |
| `cli.wsproto-preserves-app-load-diagnostic` | `module` | `<APP>`, `--ws` | — |
| `cli.sansio-ws-size-and-queue-preserve-app-load-diagnostic` | `module` | `<APP>`, `--ws`, `--ws-max-size`, `--ws-max-queue` | — |
| `cli.zero-workers-normalizes-to-single-worker` | `module` | `<APP>`, `--workers` | — |
| `cli.single-worker-flag-preserves-app-load-diagnostic` | `module` | `<APP>`, `--workers` | — |
| `cli.worker-healthcheck-timeout-is-inert-with-single-process` | `module` | `<APP>`, `--timeout-worker-healthcheck` | — |
| `cli.limit-max-requests-zero-exits-after-startup` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | — |
| `cli.explicit-default-runtime-options-are-accepted` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--http`, `--h11-max-incomplete-event-size`, `--ws-per-message-deflate`, `--ssl-version`, `--ssl-cert-reqs`, `--limit-max-requests` | — |
| `cli.console-h11-and-tls-settings-start-server` | `console` | `<APP>`, `--interface`, `--lifespan`, `--host`, `--port`, `--log-level`, `--http`, `--h11-max-incomplete-event-size`, `--ssl-certfile`, `--ssl-keyfile`, `--ssl-keyfile-password`, `--ssl-cert-reqs`, `--ssl-ca-certs`, `--ssl-ciphers`, `--limit-max-requests` | — |
| `cli.loop-none-uses-default-event-loop` | `module` | `<APP>`, `--loop`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | — |
| `cli.loop-custom-import-path-starts-server` | `module` | `<APP>`, `--loop`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | — |
| `cli.websocket-ping-interval-zero-disables-keepalive-and-exits` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--ws-ping-interval` | — |
| `cli.websocket-zero-ping-timeout-is-accepted` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--ws-ping-interval`, `--ws-ping-timeout` | — |
| `cli.unknown-option-is-rejected` | `module` | `<APP>`, `--uvicorn-rs-unsupported-option` | — |
| `cli.http2-requires-explicit-zttp-backend` | `module` | `<APP>`, `--http2` | — |
| `cli.custom-json-log-config-formats-app-load-diagnostic` | `module` | `<APP>`, `--log-config` | — |
| `cli.invalid-ws-max-queue-environment-is-rejected` | `module` | `<APP>` | `UVICORN_WS_MAX_QUEUE` |
| `cli.explicit-ws-max-queue-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws-max-queue`, `--limit-max-requests` | `UVICORN_WS_MAX_QUEUE` |
| `cli.invalid-ws-ping-interval-environment-is-rejected` | `module` | `<APP>` | `UVICORN_WS_PING_INTERVAL` |
| `cli.explicit-ws-ping-interval-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws-ping-interval`, `--limit-max-requests` | `UVICORN_WS_PING_INTERVAL` |
| `cli.invalid-ws-per-message-deflate-environment-is-rejected` | `module` | `<APP>` | `UVICORN_WS_PER_MESSAGE_DEFLATE` |
| `cli.explicit-ws-per-message-deflate-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws-per-message-deflate`, `--limit-max-requests` | `UVICORN_WS_PER_MESSAGE_DEFLATE` |
| `cli.explicit-limit-concurrency-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-concurrency`, `--limit-max-requests` | `UVICORN_LIMIT_CONCURRENCY` |
| `cli.invalid-http-selector-environment-is-rejected` | `module` | `<APP>` | `UVICORN_HTTP` |
| `cli.explicit-http-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--http`, `--limit-max-requests` | `UVICORN_HTTP` |
| `cli.invalid-websocket-selector-environment-is-rejected` | `module` | `<APP>` | `UVICORN_WS` |
| `cli.explicit-websocket-selector-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--ws`, `--limit-max-requests` | `UVICORN_WS` |
| `cli.invalid-lifespan-environment-is-rejected` | `module` | `<APP>` | `UVICORN_LIFESPAN` |
| `cli.explicit-lifespan-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_LIFESPAN` |
| `cli.invalid-workers-environment-is-rejected` | `module` | `<APP>` | `UVICORN_WORKERS` |
| `cli.explicit-workers-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--workers`, `--limit-max-requests` | `UVICORN_WORKERS` |
| `cli.invalid-reload-delay-environment-is-rejected` | `module` | `<APP>` | `UVICORN_RELOAD_DELAY` |
| `cli.explicit-reload-delay-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--reload-delay`, `--limit-max-requests` | `UVICORN_RELOAD_DELAY` |
| `cli.missing-reload-dir-path-is-rejected` | `module` | `<APP>`, `--reload-dir` | — |
| `cli.reload-dir-environment-accepts-existing-path` | `module` | `<APP>` | `UVICORN_RELOAD_DIRS` |
| `cli.invalid-reload-dir-environment-is-rejected` | `module` | `<APP>` | `UVICORN_RELOAD_DIRS` |
| `cli.explicit-reload-dir-over-invalid-environment` | `module` | `<APP>`, `--reload-dir` | `UVICORN_RELOAD_DIRS` |
| `cli.version-from-environment` | `module` | — | `UVICORN_VERSION` |
| `cli.factory-from-environment-starts-server` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_FACTORY` |
| `cli.explicit-factory-overrides-false-environment` | `module` | `<APP>`, `--factory`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_FACTORY` |
| `cli.invalid-fd-environment-is-rejected` | `module` | `<APP>` | `UVICORN_FD` |
| `cli.invalid-h11-size-environment-is-rejected` | `module` | `<APP>` | `UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE` |
| `cli.explicit-h11-size-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--h11-max-incomplete-event-size` | `UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE` |
| `cli.invalid-ssl-version-environment-is-rejected` | `module` | `<APP>` | `UVICORN_SSL_VERSION` |
| `cli.invalid-ssl-cert-reqs-environment-is-rejected` | `module` | `<APP>` | `UVICORN_SSL_CERT_REQS` |
| `cli.explicit-ssl-options-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--ssl-certfile`, `--ssl-keyfile`, `--ssl-keyfile-password`, `--ssl-ca-certs`, `--ssl-cert-reqs`, `--ssl-version`, `--ssl-ciphers` | `UVICORN_SSL_CA_CERTS`, `UVICORN_SSL_CERTFILE`, `UVICORN_SSL_CERT_REQS`, `UVICORN_SSL_CIPHERS`, `UVICORN_SSL_KEYFILE`, `UVICORN_SSL_KEYFILE_PASSWORD`, `UVICORN_SSL_VERSION` |
| `cli.http2-from-environment-with-zttp-backend` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--http` | `UVICORN_HTTP2` |
| `cli.invalid-loop-environment-is-rejected` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_LOOP` |
| `cli.explicit-loop-over-invalid-environment` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests`, `--loop` | `UVICORN_LOOP` |
| `cli.uds-from-environment-starts-and-cleans` | `module` | `<APP>`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | `UVICORN_UDS` |
| `cli.custom-loop-factory-is-invoked` | `module` | `<APP>`, `--loop`, `--interface`, `--lifespan`, `--port`, `--log-level`, `--limit-max-requests` | — |

## Remaining acceptance for `9kbx`

1. The six live CLI WebSocket cases and four h11 boundary cases are implemented; their focused local groups pass. Preserve those receipts and the h11 runtime regression fix.
2. Consume one exact-current-input hosted full matrix for the committed batch to close platform evidence. Do not repeat unaffected local groups.
3. Recheck the Click declaration count, aliases, default/env binding, precedence, and behavior assertions. Close `9kbx` after every in-scope parameter has passing applicable evidence or is justified as validation-only.
