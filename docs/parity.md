# ASGI server parity suite

The parity runner starts the reference server and `uvicorn-rs` as separate
processes, imports the same ASGI app in each, sends the same input workflows,
and compares their live public observations. It does not contain golden
responses. This is a version-pinned, scoped compatibility check; passing it
does not establish complete ASGI conformance or full Uvicorn compatibility.

## Run it

Build the local extension and sync the pinned reference-server dependencies,
run the fast contract tests, then execute the live parity input set:

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
uv run python -m unittest discover -s tests -p 'test_parity_*.py'
uv run --group benchmark python scripts/run_parity.py
```

The default generated evidence file is `build/asgi-parity/result.json`. Choose
another destination with `--output PATH`; for example, save a reviewable run in
`benchmarks/results/`. The command fails if any manifest-pinned server or
protocol component differs, an adapter cannot start, a protocol client fails,
an observation differs, or a case is malformed. Every selected case appears
exactly once in the result, including cases marked `not_run` after an
infrastructure failure. Results include the per-input and manifest digests,
reference dependency versions, target checkout revision, native extension and
Cargo lock digests, parity runner and app-fixture digests, the HTTP/3 client
binary digest, individual observations, and selected/executed/passed/failed/
not-run counts. A dirty checkout is recorded as such; it is not release
evidence.

HTTP/2 and HTTP/3 cases build a small Rust HTTP/3 client and generate a
short-lived local certificate with OpenSSL. CI exercises all declared profiles.

## Oracle selection

| Profile | Reference | Why |
|---|---|---|
| HTTP/1.1 | Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0 | Same protocol and the measured fast Uvicorn stack. |
| WebSocket | Uvicorn 0.54.0, uvloop 0.23.0, websockets 17.1 | Same HTTP/1.1 WebSocket upgrade path. |
| Lifecycle | Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0 | Same ASGI lifespan and HTTP/1.1 shutdown surface. |
| HTTP/2 | Hypercorn 0.18.0, uvloop 0.23.0, h2 4.4.1, TLS ALPN, explicit ASGI mode | Uvicorn does not provide an HTTP/2 server profile. |
| HTTP/3 | Hypercorn 0.18.0, aioquic 1.3.0, QUIC, explicit ASGI mode | Uvicorn does not provide an HTTP/3 server profile. |

The H2/H3 rows are same-protocol ASGI observations against Hypercorn. They are
not described as Uvicorn parity. Server versions and protocol components are
exact requirements in `tests/parity/manifest.json`; a version mismatch
invalidates a run rather than silently changing the oracle. The result also
records the exact Python/runtime versions and native-extension/Cargo-lock
digests for the target.

## Scope and comparison rules

The active manifest and input schema are `uvicorn-rs-parity/manifest@2` and
`uvicorn-rs-parity/input@2`; live artifacts use
`uvicorn-rs-parity/result@2`.

`tests/parity/manifest.json` indexes one input-only case file per profile under
`tests/parity/inputs/`. Inputs contain request methods, paths, headers, body
bytes, WebSocket messages, disconnect workflows, and shutdown workflows. They
do not contain expected responses or previously captured server output. The
fixture app is shared source code imported in fresh, independent oracle and
target processes. Its exported ASGI callable is synchronous and returns an
awaitable. The Uvicorn adapter forces `--interface asgi3`; the Hypercorn
adapter uses its `asgi:` selector. Both then execute the same callable under
the ASGI 3 contract. The profile split keeps protocol-specific stimulus easy
to review; the runner also checks the indexed-file set against the files on
disk.
The previous combined input is retained in `tests/parity/archive/` because an
older result artifact records its digest.

The current cases cover:

- HTTP scope observations, query/header/body transport, status and response
  content type;
- a synchronous ASGI callable returning an awaitable, exercised by the HTTP/1.1
  live parity case;
- ordered response streaming and streamed request-body echo;
- H1/H2 response delivery before the app sends its final body event, and a
  response chunk delivered before the client finishes its upload;
- an application exception and an application-generated 404;
- the ASGI `http.disconnect` event after an incomplete HTTP/1.1 upload;
- WebSocket subprotocol selection, text and binary echo, and pre-accept denial;
- lifespan startup state, shutdown, and cancellation of an in-flight request;
- HTTP version reporting and body behavior over HTTP/1.1, HTTP/2, and HTTP/3.

The runner compares status, the application `content-type` response header,
and response bytes. `date` and server-identification headers are excluded by
declared policy because they identify the implementation/runtime. WebSocket
handshake status, negotiated subprotocol, and ordered text/binary messages are
compared. Lifecycle observations include the HTTP state response, process
termination, and ordered events recorded by the test app. The raw exit code is
retained diagnostically but is not required to match: Uvicorn re-raises its
handled signal after graceful cleanup, while `uvicorn-rs` exits normally after
cleanup. Traceback formatting is not
a wire-level API; application-error parity compares its public HTTP status and
body, while the existing focused bridge probe checks that the Python exception
is logged.

The progressive streaming workflows use a fixture-app completion marker and
interleave upload and response reads. They prove that a response chunk arrived
while the application response was still open and that uploads can continue
after the first response chunk. Exact TCP read boundaries are intentionally
not compared: protocol implementations may merge or split network frames
without changing ASGI semantics. Backpressure timing,
malformed framing, broad request-security corpora, and the full ASGI test suite
remain separate work; see the [support matrix](support-matrix.md).

## Extending the inputs

Add a new case only when it maps to a declared operation and profile. Keep the
case input-only; expected values belong in neither the manifest nor inputs.
The adapter compares live outputs and stores any mismatches in the generated
result. Add a new oracle profile only for a protocol the current oracle cannot
serve, and state why that server is a valid same-protocol reference. Update the
support matrix when a new behavior is covered, and keep unsupported or
unmeasured cases explicit.

The input loader rejects unknown fields, unsupported schemas, duplicate case
IDs, unindexed files, undeclared profiles/operations, invalid body encodings,
unrepresented declared operations, and observed output fields embedded in
active cases. The contract tests cover these fail-closed properties and verify
that result accounting cannot omit a selected case. The runner selects adapters
by declared profile and workflow shape, never by case ID.

## CI evidence

The main CI workflow runs this matrix and, even on failure, retains the
structured result and runner log as an `asgi-parity-<run-id>` Actions artifact
for 30 days. It also emits a concise annotation for each failed case or
infrastructure error, so the failure can be located without interpreting a
large server log. Artifacts are scoped to their workflow run and are not a
public package release.
