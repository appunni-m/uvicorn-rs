# Evaluate uvicorn-rs with your FastAPI application

Use the verified wheel and exact version supplied with the release handoff.
An evaluation build supplied before release acceptance is provisional; its
receipt must state which gates remain open. The maintainer runs the real
application trial. Repository benchmarks do not establish a gain for that app.

The distribution is `uvicorn-rs`. It provides the `uvicorn` command and imports,
so upstream `uvicorn` and this distribution should use separate environments.

## Prepare two equivalent environments

Use the same application commit, Python interpreter, FastAPI/Starlette/Pydantic
versions, dependency lock, environment variables and external-service state.
Install the application's dependencies into both environments, then install
exactly one server distribution into each. If the app lock includes upstream
Uvicorn, remove that distribution from the candidate environment before
installing the candidate wheel.

```sh
# In the upstream environment, after installing the app dependencies:
python -m pip install 'uvicorn[standard]==0.54.0'

# In the candidate environment, after installing the same app dependencies:
python -m pip uninstall -y uvicorn
python -m pip install /absolute/path/to/the-verified-uvicorn_rs.whl
python -c 'import importlib.metadata as m; import uvicorn; print(m.version("uvicorn-rs")); print(uvicorn.__file__)'
python -m pip check
```

Use the actual handed-off wheel filename. Verify its supplied SHA-256 and
platform tag before installation. Keep a dependency listing for each environment;
the server distributions differ, while shared application dependencies match.

## Compare application behavior before timing

Run the same app with matched settings in each environment, one at a time:

```sh
python -m uvicorn your_package.main:app \
  --host 127.0.0.1 --port 8000 --workers 1 --loop asyncio \
  --no-access-log --no-server-header --no-date-header
```

Replace the app target and any required settings with your normal configuration
on both servers. Start with one Python process; the candidate uses one Tokio
worker thread. Match event-loop choice, logging, TLS/proxy path, keep-alive,
worker count and resource limits before comparing results.

Replay representative successful and failing requests. Check status, body,
headers, authentication, validation, database effects, startup and shutdown.
Include streaming/uploads/WebSockets if the app relies on them. A correctness
failure stops performance interpretation for that route.

## Measure the workloads that matter to your app

Use identical request bytes and concurrency, a warmup, and at least five paired
samples. Alternate server order across pairs. Keep the load generator and
external services from becoming an unreported bottleneck; do not run unrelated
builds or tests during a sample. Compare routes separately before reporting an
aggregate, and retain errors/timeouts instead of removing slow samples.

Record requests/second, p50/p95/p99 latency, error count, CPU time per completed
request and peak RSS, together with the app commit, server version/wheel hash,
Python/dependency versions, host and load settings. Repeat the same comparison
at your normal deployment worker count after the single-process comparison.

Higher throughput or lower latency/CPU can qualify only for the measured app,
route and load. Report regressions alongside gains. The repository's current
`docs/performance-acceptance.json` withdraws a broad Python ASGI speed claim
based on earlier slower FastAPI results; it is not evidence that your app will
improve. A Python CPU or database bottleneck can also limit the benefit of a
faster transport.

## Restore upstream Uvicorn

Stop the candidate server, then restore the application lock's upstream version:

```sh
python -m pip uninstall -y uvicorn-rs
python -m pip install 'uvicorn[standard]==0.54.0'
python -m pip check
```

Use the version from your original lock if it differs. Keeping the two
environments separate lets you switch launch commands without replacing files
in a running application environment.
