# Black-box parity and Rust source coverage

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

## Current unified coverage status (2026-10-14)

The unified v4 acceptance remains open. The current manifests contain 511 ASGI
parity/fault-contract cases and 150 Python-free native cases (661 total).
Acceptance requires three complete repeats, 100% region and line coverage,
and fully paginated Coverage-MCP results bound to the exact report bytes.

The latest exact-commit report is from hosted CI
[run 38526994848](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526994848)
on commit
[`ef9680c8e34fb2bf1c959b94d832f61cbf580213`](https://github.com/appunni-m/uvicorn-rs/commit/ef9680c8e34fb2bf1c959b94d832f61cbf580213).
All 661 indexed ASGI and native cases passed in each of three complete
verification runs, with zero retries or infrastructure failures. The unified
report measured **7,533/7,576 regions** and **5,569/5,594 lines**, leaving 43
regions and 25 lines uncovered. Its SHA-256 is
`1bef17e4fc15bbb21eb57144811dbbc9404dd44eec54ec30def086e44d57376a` and its
source SHA-256 is
`911747c042fbc1cb7c66a0fb626bfa2eb063a514e73c04d8a0adc9b021b346ee`. The
[unified coverage artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/38526994848/artifacts/11878179532)
retains the report and attribution data. Coverage-MCP did not return a
receipt for this report during three follow-up calls, which timed out, so the
required exact-report, fully paginated zero-gap check remains pending. Every
indexed case passed, but the coverage threshold and MCP receipt requirements
remain unmet.

### Historical hosted baseline: CI run #110

Hosted CI [run #110](https://github.com/appunni-m/uvicorn-rs/actions/runs/38418430762)
retained a full-scope report for commit
`796dee690ca83654cddb97131dc1dee37de96bcd` and its then-current 633-case
manifest. It passed 633/633 case attribution but measured 7,322/7,380 regions
and 5,383/5,417 lines, leaving 58 regions and 34 lines uncovered. The report
SHA-256 is
`48a33bfb11b9b0580d446612071abb0406e2a2df2f156c88342ebdf67cc621a4`;
Coverage-MCP could not produce a receipt from this retained artifact during
follow-up because both queries timed out. This run predates the current
661-case manifest and does not satisfy the exact-source coverage gate.

### Normal and instrumented native case lanes

Normal CI selects the 149 `target-contract` inputs from the 150-case native
manifest using `scripts/select_native_contracts.py` and retains a receipt with the source and selected-input hashes,
selected IDs and coverage-only IDs. The unified runner still includes all 150
native cases and all 511 ASGI cases. It requires consumed fault evidence for
the native `fault-contract` input, both during attribution and on each complete
native repeat. Repeat receipts include expected and observed fault points in
manifest order.

The normal harness now rejects a declared fault with
`native fault contracts require an instrumented coverage build`. Previously,
that input substituted an abortive client reset in normal builds and could
report a pass without consuming the declared fault. The substitution has been
removed; the input and its expected behavior remain the same across builds.

Three affected normal inputs passed, and the same fault input was rejected by
the new normal binary. The retained old binary reported a pass for that fault
without fault consumption, so it provides the defending negative control.
The local receipt is
`target/native-contracts/normal-fault-lane-focused.json`, SHA-256
`c662db78d82eca8b362e4c0c55f6661b0a8441026f95414afe8937e17a5be601`.

The fresh selected coverage run passed **1/1**, with the declared
`websocket.receive.close-reply.flush` fault consumed, zero retries and no
infrastructure failures. Report:
`target/asgi-coverage-kata-20261014/normal-lane-fault-control/repeat-marker-report.json`;
source SHA-256
`59e4315f7bc3cd30673a63f4ab1aaab22a7223f91937a4f6d1dbe69baf74d898`;
report SHA-256
`40842f1cc3fb44c9065e69d6a2e729cb9649b2b3328a9663faf39b0cd3cf6912`.
Coverage-MCP matched the source and passing selected receipt and found no
missing region groups at the close-reply fault arm. This proves the affected
lane behavior; it does not qualify all 661 cases or establish aggregate
coverage. No complete repeats were run for this focused change. The selector's
six CLI controls also passed: a valid 149-case selection and rejection of
duplicate/empty IDs, unknown modes, a normal case declaring a fault, and a fault
case without a point. Their local receipt is
`target/native-contracts/selector-controls/receipt.json`.

### Selected native TCP EOF evidence

`PeerReadHalfClosed` is a TCP request extension, including TLS over TCP. It
records a successful raw-socket EOF read with nonempty buffer capacity, below
TLS. It does not treat reader destruction, HTTP body completion, an HTTP/2
stream reset, or QUIC stream cancellation as TCP EOF. Waiting returns
`PeerReadHalfClosedUnavailable` when observation ends without confirmed EOF.

Nine new inputs reuse the request, half-close, and graceful-drain operations.
They check complete, empty, and streamed responses after client write-half
closure over TCP and TLS; the default service-error 500 after that closure;
absence of the extension on HTTP/3; and the typed unavailable result after
server shutdown without peer EOF. The existing HTTP/2 reset input also checks
that the TCP extension is present and remains false during stream reset.

These inputs and eight neighboring body, lifetime, upgrade, and transport
controls passed **18/18** once, with complete attribution, zero retries, and
zero case or infrastructure failures. Report:
`target/asgi-coverage-kata-20261014/peer-eof-focused/full-report.json`;
run ID `67168845c4a0470993f0d3d596487ce4`; source SHA-256
`4bc08270c96ef7e71d65d48dc9531e8c0fe6781b686f38f86027be63fdd3bc41`;
report SHA-256
`d5e4f365ae9ddd288d972b9a9e13c85798ba609aaf741c5ea1d30ea35ac2ab5e`.
The selected union measures 1,205/7,576 regions and 1,015/5,594 lines.
Coverage-MCP matched the source and passing-test receipts when measured. Filtered queries
have no missing groups at the wait method; the raw-read query retains one
uncovered generic region and no missing lines. The filtered receipt is stored
beside the report and is not a full aggregate zero-gap receipt.

The EOF cases observe the signal **after response completion**. Hyper's
`half_close(true)` preserves response delivery but does not promise a socket
read while an HTTP/1 service is held. Kata `1m58` tracks prompt FIN observation
at the protocol-driver level. Suppressing EOF for the entire service lifetime
would also suppress incomplete request-body errors and can stall an app
awaiting its body; that approach was rejected. No timer, second socket reader,
probe write, or fabricated disconnect was added. This selected evidence does
not qualify the 661-case gate or migrate the Python ASGI transport.
The later fault-harness correction changed the source receipt; the 18-case
report is a historical selected snapshot.

### Selected native connection-limit evidence

The native server validates `max_connections` in
`1..=tokio::sync::Semaphore::MAX_PERMITS` before lifecycle startup. Values
above that range return `ServeError::ConnectionLimitTooLarge`; zero retains
`ServeError::InvalidConnectionLimit`. This prevents the locked Tokio semaphore
constructor from panicking on an oversized public configuration.

Four new inputs reuse the existing configuration and lifecycle operations:
oversized TCP, TLS, and HTTP/3 limits return the typed error without invoking
hooks, and HTTP/3 serves a real request at the exact runtime maximum.
Ten affected inputs and controls passed once, with zero failures or retries,
in `target/asgi-coverage-kata-20261014/connection-limit-focused/full-report.json`.
The report SHA-256 is
`5e98e192f9038cc2107bdf82a6ac06f3553cf8f3b58f2c70bbb340778e4c9f08`;
the measured source SHA-256 is
`f06a947b5935e6e5dd43e676a455b9d2d40dec1d048d4859ea2ee04b995f6410`.
Coverage-MCP verified matching source receipts and no missing regions at the
new rejection branch. This historical selected snapshot does not qualify its
then-652-case coverage gate or the Python ASGI transport migration.

### Selected native service-error policy evidence

`ServerConfig::service_error_policy` now selects the default empty 500 response
or propagation of the original typed readiness/service error. Six new isolated
inputs check propagation across HTTP/1.1, HTTP/2, and HTTP/3. They require
pre-header connection termination on H1, an `INTERNAL_ERROR` stream reset on
H2, or an `H3_INTERNAL_ERROR` stream reset on H3, followed by a healthy request
on a fresh H1 connection or the same H2/H3 connection. Each checks the original
direct `io::Error`, message, observer phase, peer metadata, and bounded shutdown.
The protocol workflow has a five-second deadline. A seventh input verifies an
ordinary H3 service error still produces an empty 500 under the default policy.

These inputs and nine default-policy, panic, body-error, and public-configuration
controls passed **16/16** with complete attribution, zero retries, and zero case
or infrastructure failures. Report:
`target/asgi-coverage-kata-20261014/native-error-policy-focused/full-report.json`;
run ID `da62b0e72cdc4acfb2d89eb032ed82aa`; source SHA-256
`34103809821e490fd8f0901178b6110270bbf853c93e3459317cd4658044ffdc`;
report SHA-256
`1d53abd7ae006f5f4e737ade533875f5a0f80eb9a5c891027a6a7f4165f49241`.
It records dirty revision `796dee6` and is local diagnostic evidence.

The source-region union attributes the propagation returns and H3 reset arms
to the selected inputs. Coverage-MCP matches the source receipt and passing
test receipt. Its four filtered line queries have zero missing groups; the
region queries retain gaps in other generic instantiations. The selected union
measures 1,117/7,471 regions and 932/5,506 lines. This selected report does not
replace full attribution, three repeats, or the fully paginated zero-gap gate.
The filtered query receipt is retained beside the report, not attached as a
full aggregate Coverage-MCP receipt.

All six propagation inputs were also executed against the same instrumented
runner with only `service_error_policy` changed to the default; all six failed
at the intended abort/reset assertion. Their expectations were unchanged.
The validated negative-control receipt is Git-ignored at
`target/native-error-policy-negative-control/validated-receipt.json` and binds
runner SHA-256
`558b4dcac557595483a3c88b6df99a914ffe669fedc8276c070a0e970bdc2d90`.
Native all-target/all-feature Clippy with warnings denied, formatting, and
manifest/reference validation passed. No complete 648-case repeat was run.

### Selected native panic recovery evidence

The new native contracts cover two external application faults:

- `http1.upgrade-handler-panic-closes-session-and-listener-recovers` accepts
  the upgrade, observes session EOF without unexpected bytes, verifies a healthy
  request on a fresh connection, and requires bounded server shutdown. Its
  join diagnostic uses tracing; it does not assert a `ServerErrorObserver` event.
- `http3.readiness-panic-returns-500-and-keeps-connection` arms one application
  readiness panic, verifies an empty 500 and a typed readiness diagnostic, then
  verifies a 200 response on the same HTTP/3 connection.

Both are native target contracts. The deliberate panics live in the example
harness, which `cargo package --list` excludes from the Rust crate archive;
no production fault control or authored production panic was added.

These cases and six neighboring readiness, upgrade, and listener contracts
passed **8/8**, with complete per-case attribution and zero retries,
infrastructure failures, or case failures. The selected report is Git-ignored at
`target/asgi-coverage-kata-20261014/native-panic-contracts-focused/full-report.json`.
Run ID: `60ef10cd1c984d5d8bfca58e6a9759ea`; source SHA-256:
`3a5c6bdd1609297b5c9eb595598aee24d1255b7a4e9ff8746dad0e569753ac67`;
report SHA-256:
`78193027bf2428061e703064afd08e6bfb4c2d62a8d91a9f58c77b7cb5098016`.
It records dirty revision `796dee6` and is diagnostic evidence only.

The source-region union attributes the upgrade join-error arm and HTTP/3
readiness-panic arm to the new cases. Coverage-MCP reports matching source and
passing selected tests, but its filtered region queries retain gaps in other
generic instantiations. The filtered line queries at those arms have zero
missing groups. The selected union measures 1,031/7,434 regions and
858/5,464 lines; it cannot be combined with the older full-source report or
used to claim aggregate coverage. No complete 641-case repeat was run.

An isolated source copy with only readiness containment removed failed the
same HTTP/3 input with `H3_FRAME_UNEXPECTED` before response headers. Its local
receipt is Git-ignored at `target/native-readiness-panic-regression/receipt.json`.
This confirms the new case detects the uncontained readiness panic. Native
all-target Clippy with warnings denied, formatting, and manifest/reference
validation passed on the corrected worktree.

### Last full-manifest baseline

The last full-manifest attribution report is Git-ignored at
`target/asgi-coverage-kata-20261014/current-639-attribution/full-report.json`.
Run `01b6a2a77b06431bbfa132a91bb6de91` exercised all 639 cases once (511 ASGI
and 128 Python-free native) with complete attribution and zero case,
infrastructure, or transient failures. It records revision
`796dee690ca83654cddb97131dc1dee37de96bcd`, a dirty source tree, aggregate
source SHA-256
`8c27b2b471e00b746f17d1db95af5d06317782d87df66359bdfaf0bd9cb0fb4f`, report
SHA-256 `387aa56d0d4800165a2f6ad8975558f4b056028492119c4b383c585c32dac3b4`,
and Coverage-MCP build ID
`31cf4c67bd6305451dd6e5b6fa7d3d0fa92bb30b3f0d4099eb8e3be0f999f4b1`. The
receipt matched the worktree when this report was generated. A later refactor
in `lib.rs` changed the source hash, so this is now the last full-manifest
baseline rather than exact-current-source evidence.

Coverage measured **7,373/7,414 regions** and **5,420/5,444 lines**, leaving
41 regions and 24 lines uncovered. Coverage-MCP fully paginated both exact
report queries and returned `source=matches_receipt`: 176 region groups over
nine pages and 22 line groups over two pages. Its `tests=failed` status reflects
the remaining coverage gaps. The report's embedded `coverage_mcp` state still
says `awaiting_query`; the completed live Coverage-MCP queries are the current
evidence. The groups include repeated generic instantiations and are not a
count of distinct behavioral gaps.

This is one attribution pass only; no three-repeat matrix was run. The report
is dirty local diagnostic evidence, not release proof, and the 100% gate remains
open.

After that full run, the HTTP/1 upgrade-extension decision moved into the
non-generic `insert_http1_upgrade_extension` helper. The focused report at
`target/asgi-coverage-kata-20261014/connection-upgrade-helper-focused/full-report.json`
passed the existing native HTTP/1 WebSocket, HTTP/2 request, and HTTP/3 request
cases (3/3, with no retries or infrastructure failures). Its source SHA-256 is
`e1ff4ff9b75803fcf1456fa7b44313e7ad92fcb949e083ad98acbf5393dbf5c3`, report
SHA-256 is
`bd019e57027e46b634974458900d1853eaee1e7bc35d7e586f92b9efa10c99ef`, and run
ID is `5dcdeee69a234f63b1d5409c3946b09c`. Coverage-MCP matched the source
receipt, reported passing selected tests, and found zero missing groups for
the helper. This selected run does not refresh aggregate totals or close the
full-manifest gate; a full current-source report is still required.

The newly added native input
`http1.native-websocket-close-reply-flush-failure-preserves-source` passed a
selected instrumented run at
`target/asgi-coverage-kata-20261014/websocket-close-flush-fault-v4/full-report.json`.
Its source SHA-256 is
`8c27b2b471e00b746f17d1db95af5d06317782d87df66359bdfaf0bd9cb0fb4f` and its
Coverage-MCP build ID is
`31cf4c67bd6305451dd6e5b6fa7d3d0fa92bb30b3f0d4099eb8e3be0f999f4b1`.
Coverage-MCP matched that report to its source receipt, passed the selected
case, and reported no missing regions at `websocket.rs:267`. This selected
report covers one input from the then-639-case manifest; it is not a full-manifest result and
does not close the 100% gate. A full current-manifest report with three complete
repeats and zero missing regions and lines is still required.

The latest prior-input full-repeat baseline is Git-ignored at
`target/asgi-coverage-kata-20261014/server-shutdown-final/full-report.json`.
Run `9a19da353fef4d30aaf3fc8ea12d9d85` used revision `796dee6` with a dirty
worktree and source SHA-256
`c68c1c87078d8212beb5b283343145148027ed9e70394848d8fc15f7c1c357b1`. All
635 cases passed, including 243 oracle-parity cases and 268 fault contracts;
the 511-case ASGI matrix and 124-case native matrix each passed three complete
repeats. Attribution is complete, with zero failed cases, infrastructure
failures, transient infrastructure failures, or retries.

Coverage measured **7,329/7,371 regions** and **5,384/5,408 lines** (42 regions
and 24 lines missing). The uncovered regions are in `http3.rs` (16), `lib.rs`
(21), and `websocket.rs` (5). Coverage-MCP fully paginated this exact report:
170 region groups across nine pages and 21 line groups across two pages. Both
queries reported `source=matches_receipt` and `tests=passed`; they returned
remaining gaps, so this is not a zero-gap or 100% result. The aggregate gate is
incomplete. This 635-case three-repeat result is historical and does not
replace the last 639-case one-pass attribution report above.

The 635-case report predates four native cases. The first two HTTP/3
lifecycle cases are:
`native.lifecycle-http3-omitted-hooks-still-serves` verifies that the server
serves when application-managed lifecycle hooks are omitted, and
`native.lifecycle-http3-zero-connection-limit-rejected` verifies that invalid
server configuration returns the expected error. Both passed in the selected
instrumented report at
`target/asgi-coverage-kata-20261014/h3-lifecycle-config-selected/full-report.json`.
Its Coverage-MCP build ID is `74e65d0e587146d1f114a5bd355afbb4a6760837be0cb7ec19cde3165fdcaa12`,
report SHA-256 is
`217ae2b4857a00f1197407765f698de2fb55835a082ba3f2acb1bb45c6a50b95`, and the
recorded revision is `796dee6`. Coverage-MCP reports
`source=matches_receipt` and `tests=passed`. This selected run verifies only
the two added inputs; it does not provide current full-matrix coverage or the
required three repeats. Coverage-MCP's incremental compare against the
635-case report returned `incomparable` because the baseline detail is
incomplete for a verified union; no additive coverage claim is made. The
635-case report above predates these manifest and runner changes and cannot
serve as the current acceptance report. The listener-reaping case,
`native.http1.completed-connection-reaped-while-sibling-request-is-held`, was
run together with the existing HTTP/1 and TLS lifecycle cases in the selected
report at
`target/asgi-coverage-kata-20261014/listener-non-generic-helper-selected/full-report.json`.
All three passed. Coverage-MCP matched the source receipt and passed-test
receipt, but this selected report is not a full-matrix coverage result. The
last 639-case attribution report above supersedes it for one-pass case
results, but not for three-repeat acceptance.

A broader selected run then executed all 71 native HTTP/1, TLS, and HTTP/2
inputs together at
`target/asgi-coverage-kata-20261014/native-listener-protocols-selected/full-report.json`.
All 71 passed; Coverage-MCP matched the source and test receipts. Its focused
query still reports missing regions in `next_listener_event`: raw LLVM export
contains a zero-count copy of the generated `tokio::select!` closure alongside
an exercised copy, and the guarded `Option` fallback remains unvisited. This
selected report is not a full-matrix result. The last 639-case full run includes
those inputs, but does not clear the repeat or coverage gates and predates the
current source refactor.

Six additional HTTP/1 lifecycle error and cancellation cases also passed in
`target/asgi-coverage-kata-20261014/native-listener-lifecycle-selected/full-report.json`.
Coverage-MCP's incremental comparison against the 71-case report returned
`incomparable` because the baseline lacks the detail required for a verified
union, so no additive coverage claim is made. A `#[inline(never)]` experiment
on the listener helper did not change its missing-region result and was
removed.

The report, raw profiles, and run logs are under ignored generated directories;
none are tracked. The first exact-span audit found meaningful case candidates
for the HTTP/3 lifecycle default/invalid-config paths (`lib.rs:751,753`) and
listener completion (`lib.rs:946`). HTTP/3 shutdown failure (`http3.rs:355`)
and WebSocket close-reply flush failure (`websocket.rs:267`) depend on peer
failure timing and should count only if a black-box case proves repeatable.
The two new HTTP/3 cases cover the public omitted-hooks and invalid-connection-
limit configuration paths in a selected run. The existing
`http1.max-connections-one-releases-slot-after-peer-close`
case also passed alone under instrumentation, but did not attribute the
`serve_listener` completion observation at `lib.rs:946`; it proves slot reuse,
not that the listener reaped the finished task before shutdown.

Other remaining regions appear tied to internal ownership invariants,
uninhabited `Infallible` arms, unsupported `http_body::Frame` variants,
prevalidated timeout overflow, or panic-only task-join outcomes. Under the
current no-panic and no-private-trigger policy, those cannot be honestly
covered by ordinary input cases. The literal 100% gate therefore remains open:
first add and measure the reachable cases, then decide whether to refactor away
unreachable branches or explicitly revise the coverage scope. Do not add
synthetic cases just to inflate coverage. After source/input changes, rerun the
three complete matrices, then repeat the strict offline, installed-extension,
and exact-commit hosted checks.

### Historical audit of the gaps in the 633-case report

Three read-only reviews examined every uncovered region against the source and
case inventory recorded for that 633-case report. The current report above has
refreshed the aggregate gap counts, but a per-span audit against its exact
source has not been completed. The classifications below remain historical;
do not use them alone to add cases or change production code.

| Source | Missing regions | Missing lines | Audit result |
| --- | ---: | ---: | --- |
| `crates/uvicorn-rs/src/lib.rs` | 21 | 12 | Internal channel/semaphore invariants, OS-dependent accept failure, clock-boundary paths, uninhabited `Infallible` arms, and task-join reporting that requires a panic. |
| `crates/uvicorn-rs/src/http3.rs` | 31 | 18 | Closed-admission and impossible join states, late shutdown/clock paths, uninhabited service errors, panic-only task joins, and internal error formatting. The current `http_body::Frame` API exposes only DATA and trailers, so the unsupported-frame branch has no public stimulus. |
| `crates/uvicorn-rs/src/websocket.rs` | 6 | 4 | Generated accept-key and validated subprotocol conversions cannot fail for the supplied values; close-reply flush failure depends on peer failure and timing. |

The historical audits did not add cases whose only purpose is executing
private code. This note does not change the denominator or waive any
acceptance requirement.

The manifest includes
`native.lifecycle-http3-startup-error-prevents-serving`. It runs the real H3
listener with a failing application startup hook and checks that serving never
begins. The selected report passed 1/1 with complete attribution (205 regions)
at
`target/asgi-coverage/2026-10-13-h3-lifecycle-startup-selected/coverage-report.json`;
that input also passed in each of the then-current 124-case native verification
repeats described above.

The current native manifest also includes active TCP/TLS upgrade-registration
cases and lifecycle-enabled WebSocket handshake/message cases over TCP and
TLS. Those two WebSocket cases passed together in the selected unified report
`target/asgi-coverage/2026-10-13-lifecycle-websocket-selected/coverage-report.json`.
Focused reports support their named cases; they do not substitute for
full-source aggregate coverage.

The historical complete-scope run before the shutdown cleanup below is the
local, Git-ignored report
`target/asgi-coverage/2026-10-14-current-595-single/coverage-report.json`,
finished 2026-10-13 at 02:32 UTC. It records clean source revision
`c5a200195149af548ced5d7425ed396cdbdc704c`, binds 103 source files, and covers
the 511-case ASGI and 84-case native manifests. All 595 cases passed once with
complete attribution and no case, infrastructure, or transient infrastructure
failures. It measured **6,900/6,960 regions** and **5,061/5,093 lines**.
Coverage-MCP pagination is complete: all 111 region groups and 30 line groups
were retrieved, and both queries reported `source: matches_receipt`. Coverage
MCP reported `tests: failed` because the report has uncovered regions and
lines; the full report remains below 100%. Three complete repeats are required
and none has been run. This is not a 100% coverage pass. It covers the
then-current 511-case ASGI and 84-case native manifests and does not establish
acceptance for the then-current 612-case manifest.

After that complete-scope run, the redundant per-connection graceful-shutdown
timer was removed. The server-wide deadline already bounds connection draining
and reports `ServeError::GracefulShutdownTimedOut`; retaining a second timer
introduced a competing timeout at each connection. The focused native case
`http1.graceful-shutdown-timeout-aborts-held-response` passed 1/1 against the
updated source. Its Git-ignored selected report is
`target/asgi-coverage/2026-10-13-h1-shutdown-deadline-selected/coverage-report.json`;
it records 496/6,946 regions and 408/5,085 lines for that selected case. The
source change also reduced the executable coverage denominator. This focused
result verifies the shutdown contract only: the 595-case report above was
collected before this edit and does not establish full-matrix parity or
coverage for the updated source. The full matrix was not rerun.

Four HTTP/1 upgrade-session inputs passed 4/4 in the focused unified runner:
the successful `101` handoff/drain, session-handler error, unavailable upgrade,
and registration after connection close. The selected report is
`target/asgi-coverage/2026-10-13-native-upgrade-contracts-refactor/coverage-report.json`;
it records 673/7,072 regions and 550/5,177 lines for the selected subset, with
complete attribution and no case, infrastructure, or retry failures. Its
source SHA-256 is `2c3558737f2f4643c4848b3c0d0438a1f245dcf1b4d2835b65b0282cfbaf0a3f`.
Coverage-MCP reports a matching source receipt and passed case status. Its
The old `ConnectionUpgrade` query discrepancy was traced to the generic
service's protocol-specific instantiations: the HTTP/1 insertion executed, but
the HTTP/3 instantiation could not enter that branch. The non-generic helper
above removes that per-instantiation gap in the focused report. This selected
report is not aggregate coverage evidence and does not establish WebSocket
handshake, framing, or ASGI WebSocket support.

The initial native HTTP/1.1 WebSocket selection passed 4/4 with complete
attribution and no retries or infrastructure failures. It covers text/binary
echo, Ping/Pong, close exchange, a server shutdown close handshake, malformed
key rejection, and unoffered subprotocol rejection. Its historical, ignored
report is
`target/asgi-coverage/2026-10-13-native-websocket-h1-final/coverage-report.json`;
it records 706, 632, 631, and 688 covered regions by case, respectively, and
source SHA-256
`8eccb701012a8cd5d44ae49a227d609df13a17ea3a9c473450fe627de1c9f4fe`. That
digest was captured before the follow-up Rustdoc wording edits; executable code
was unchanged after the run. This four-case report is selected-case evidence;
it does not establish aggregate coverage, TLS/H2/H3 WebSocket support, or
Python ASGI WebSocket integration.

The historical expanded native HTTP/1.1 WebSocket selection passed 13/13 in
one unified run at
`target/asgi-coverage/2026-10-13-native-websocket-rfc-contract-final/coverage-report.json`.
The nine added cases cover a non-GET method, a WebSocket version other than
13, a decoded key of the wrong size, a missing `Connection: Upgrade` token, a
wrong `Upgrade` token, an empty offered subprotocol token, rejection of
managed response-header overrides, single-use subprotocol selection, and
preservation of an application response header. The report records complete
per-case region attribution for all 13 selected inputs; all passed on the
first attempt, with zero failed cases, retries, infrastructure failures, and
transient infrastructure failures. Its source SHA-256 is
`37901559958c25922e123eab1a080ec353b63654431416099ffc54eb82a5eeb1`. For this
selected subset, it records 868/7,384 regions and 699/5,420 lines.
The fully paginated follow-up Coverage-MCP queries for this exact report
matched the source receipt and reported `tests: passed`. In
`crates/uvicorn-rs/src/websocket.rs`, they returned 32 missing region groups
across two pages (20 and 12 groups) and 17 missing line groups on one page.
These are gaps in the selected report; they do not indicate a full-suite
regression or an attribution defect. This report predates the 629-case
manifest, so it is not aggregate coverage evidence or a 100%
coverage pass.
HTTP/2 and HTTP/3 WebSockets, TLS WebSockets, and Python ASGI WebSocket mapping
remain open.

The HTTP/3 request-body change was measured separately with
`target/asgi-coverage/current-http3-empty-body-eof-refactor/coverage-report.json`.
The native HTTP/3 empty-body EOF case passed 1/1 with complete attribution and
no retries. That selected measurement had an executable denominator of
**6,957 regions** and **5,088 lines**; the case covered 683 regions and 601
lines. This selected report does not establish aggregate coverage or
full-matrix parity.
The `data_finished` field was removed because it could not persist across
`poll_frame`: a `None` data poll immediately polls trailers; if trailers are
pending, the body returns `Pending` and polls data again next time. The new
input independently asserts the public empty-request-body state and EOF result.
The existing `http3.empty-data-frame-does-not-end-request-body` case also
passed 1/1 after the edit, preserving the empty-DATA-then-later-DATA behavior.
Both cases are included in the 595-case run above; three-repeat verification
and the full coverage gate remain outstanding.

A separate selected report is
`target/asgi-coverage/current-http1-graceful-timeout-consolidated/coverage-report.json`.
The existing native case
`http1.graceful-shutdown-timeout-aborts-held-response` passed 1/1 after the
server task-error handling was consolidated. Coverage-MCP matched the report
receipt and passed the case result; its focused region query at
`crates/uvicorn-rs/src/lib.rs:1086` returned zero gap groups. The report covers
498/6,960 regions and 410/5,093 lines in this selected run. It is not aggregate
coverage evidence. The change shares cancellation classification between
ordinary connection joins and abort draining while preserving their distinct
error log messages. The run was captured from the working tree immediately
before commit `b3abb4e3a`; the report records `dirty=true` and binds the exact
source files by receipt.

The native case `http3.response-cancel-before-finish-keeps-connection-usable`
holds an empty response body after headers, sends a real QUIC
`STOP_SENDING`, releases the app body, then checks the connection error and
same-connection recovery through both harness apps. It passed 1/1 with complete
attribution and no retries or infrastructure failures. Its selected report is
`target/asgi-coverage/current-http3-response-cancel-before-finish/coverage-report.json`
and remains Git-ignored with the other per-run artifacts. The attribution
report maps `http3.rs:489-491` to a concrete function instantiation with a
positive count. The raw LLVM export also contains a zero-count generic
`handle_http3_request::<_, _>` row for that same span. The focused
Coverage-MCP region query returned that row as one missing region group; its
line query at 491 returned zero missing groups. The raw line segment at 491 is
a boundary (`hasCount=false`), and the following `.map_err` expression at 492
has an execution count. These are different views of the generic and concrete
instantiations; the report's `hit_by` attribution does not cover every raw
instantiation. Do not add a synthetic request just to reach the generic
placeholder. This selected report measures 703/6,960 regions and 621/5,093
lines; it is not aggregate evidence.

The case reaches the response-send path through both native harness apps, but
its observer records only that some connection-phase error occurred. It does
not identify `finish().await` or its result, so it is indirect evidence for
the finish path.

The focused cases
`http3.peer-close-during-server-connection-creation-recovers` and
`native.lifecycle-http3-peer-close-during-server-connection-creation-recovers`
exercise peer closure during native HTTP/3 connection creation, check the
connection error observation, and verify listener recovery. Both passed in
the selected report
`target/asgi-coverage/current-h3-init-close-final/coverage-report.json` with
zero retries or infrastructure failures. Coverage-MCP reports
`source: matches_receipt` and `tests: passed` for that selection. At
`crates/uvicorn-rs/src/http3.rs:336`, the concrete `ContractApp` and
`LifecycleApp` instantiations have no missing regions; only the uninstantiated
generic placeholder remains. This selected report does not establish full
matrix coverage.

`http3.lifecycle-shutdown-bounds-pending-handshake` holds a real QUIC/TLS peer
inside certificate verification, requests server shutdown, and checks that
`serve_http3` returns the documented `GracefulShutdownTimedOut` result before
the peer is released. The application shutdown hook still completes. Once the
gate is released, either TLS completion or connection closure is accepted: the
peer's final handshake flight can race with the endpoint close packet. The
selected run passed 1/1 without retry in
`target/asgi-coverage/current-http3-pending-handshake-shutdown-final/coverage-report.json`.
Coverage-MCP reports `source: matches_receipt` and `tests: passed`. At
`crates/uvicorn-rs/src/http3.rs:228`, the concrete lifecycle specialization
has no missing endpoint-drain regions; remaining selected-report gaps there
belong to an uninstantiated generic placeholder. This confirms the bounded
shutdown path for this input, not aggregate coverage or full-matrix acceptance.

The historical 595- and 628-case reports are recorded above. The earlier full
629-case diagnostic retained 59 region and 34 line gaps and one infrastructure
failure; its TLS WebSocket case passed in a separate retry that is not merged
into the full receipt. Acceptance still requires three complete repeats, 100%
region and line coverage, and fully paginated zero-gap Coverage-MCP results
tied to the exact final report. Python line and branch coverage remain outside
the Rust denominator. Generated reports, profiles, Coverage-MCP payloads, and
logs stay under Git-ignored local output paths; the per-run artifacts are not
committed.

## Previous adapter-only evidence (2026-10-12)

The dirty working tree passed the complete 511-case live matrix: 243
oracle-parity cases and 268 target-only fault/support contracts. Per-case
attribution and all three complete repeats passed with zero behavior,
infrastructure, transient-infrastructure failures, or retries. Coverage was
5,561/5,561 regions and 3,997/3,997 lines for `src/lib.rs` only.

The generated JSON report, compact projection, and Coverage-MCP receipt for
this historical run are local artifacts excluded by `.gitignore`. This
maintained summary records their case totals, source/build identity, and
coverage result without committing per-run output.

The run used CPython 3.12.13, Rust 1.98.1, and macOS 15.7.7 ARM64 at dirty
working-tree revision `3dcaeaa0caf47aca96412d15451ac6a1123ebb04`. The measured
source/input digest was `cfc3aac2ed6f62e3466c3e2418dfb6498377d11045f056723fe2adc9ba688b63`;
the `src/lib.rs` SHA-256 was
`ea149b5821a398f62c5a7762a83774040ae15ae0b268c28d921e4c61f3e54f47`, and the
instrumented extension SHA-256 was
`e9e97bea9d2bec8f9d7df0aec7bc978a9c454cb2d29fa2b249db9fa69a6cf4d7`.
This is dirty local evidence for the recorded adapter source, not a clean
release checkout or hosted commit. The instrumented extension is for coverage
only and must not be used for performance timing. The report excludes the
Python-free `uvicorn-rs` crate and other feature sets or platforms; it is not
the current unified acceptance report.

The five added target-only cases exercise `UVICORN_RS_MAX_BLOCKING_THREADS`:
unset and positive values start and serve an HTTP request; non-Unicode,
malformed, and zero values fail before ASGI lifespan startup. They establish
configuration acceptance and rejection paths, not the effective blocking-pool
concurrency limit. The related public setting and limits are documented in
[configuration](configuration.md#tokio-blocking-pool-limit) and the
[support matrix](support-matrix.md#supported-behaviors).

### Previous local evidence (2026-10-11)

The dirty working tree recorded on 2026-10-11 passed the complete 506-case live matrix:
243 oracle parity cases and 263 target-only fault contracts. Per-case
attribution and all three complete 506-case repeats passed with **zero
failures, infrastructure failures, transient infrastructure failures, or
retries**. Each repeat passed 506/506 cases. Native coverage is
**5,532/5,532 regions and 3,971/3,971 lines**, and case attribution matches the
profile union.

The generated full report and compact input projection for this historical
run are local artifacts excluded by `.gitignore`. The projection retained the
LLVM coverage data and runner receipts while omitting duplicated per-case and
per-region attribution arrays from the full report. Coverage-MCP reported
`source: unverified` and `tests: unknown` for this LLVM export; source and test
identity came from the runner receipts, not Coverage-MCP.

This local macOS 15.7.7 ARM64 measurement used Python 3.12.13 and Rust
1.98.1, on dirty working tree revision
`3dcaeaa0caf47aca96412d15451ac6a1123ebb04`. The measured `src/lib.rs`
SHA-256 is
`5ecbf23cbd9cb430be9af6c9f69399bc4c835eb4441c8f8794f4e3c881beca7d`; the
instrumented extension SHA-256 is
`11bb6e665ad0d98dd9d239836b93277277d4eff9388b394685ceb6adcd87fdf4`.
After coverage collection, the normal release extension was rebuilt and
installed with `maturin develop --release --locked`; its SHA-256 is
`5c23a4e33006b6183f3a0bba89b2506c3866be2d293b9cd49ebffb037c47b028`. No
post-rebuild parity run was performed. Do not use the instrumented coverage
build for timing. This local receipt does not replace hosted exact-commit CI.
The current checkout's `src/lib.rs` hash differs from the measured hash above,
so this 506-case result is historical for the recorded source, not a full
parity or coverage pass on the present working tree. The current renamed wheel
has a separate, narrower consumer smoke result; its scope is summarized in the
support matrix.

#### Previous local evidence (same date, earlier source)

The earlier local run on this revision measured 5,532/5,532 regions and
3,974/3,974 lines, with a different dirty `src/lib.rs` hash
(`1f222c06c5ecfa4f1c3b22299259ddb69f5d39822427e50c4a9f8b4eebf8f455`) and
extension build. Coverage-MCP reported `source: matches_receipt` and
`tests: passed`, with zero missing regions or lines for that report. The raw
report, Coverage-MCP receipt, context, and evidence README are generated local
artifacts excluded by `.gitignore`; this paragraph preserves the historical
summary without linking to local files. Before that earlier coverage run, its
normal non-instrumented extension passed 243/243 public parity cases (SHA-256
`bf3cb991025074bc416ccd514b836aec31899ca1ce6f0d40bdfa819c9dd07d43`); its
coverage extension hash was
`2f8538416e5890d21a57898852eda14c2c9fcfdb405bac23f7bde4826bcc6640`. Its raw
report, receipt, context, and evidence README are generated local artifacts
excluded by `.gitignore`. These results apply only to the earlier source and
must not be carried forward to the current report.

## Latest hosted exact-commit gate (2026-10-11)

CI [run 38087300590](https://github.com/appunni-m/uvicorn-rs/actions/runs/38087300590)
passed on clean commit
[`16ed349`](https://github.com/appunni-m/uvicorn-rs/commit/16ed349f0d1528b8e6f42536b3d406ce17799915).
All eight hosted jobs passed, including installed-wheel public parity, the
unified parity/fault-contract and 100% native coverage gate, Rust quality and
MSRV, the Windows/Linux/macOS package jobs, and the declared Python-floor
wheel. This is hosted evidence for that committed source; it is separate from
the dirty local 506-case report above.

## Previous hosted exact-commit gate (2026-10-10)

CI #56 passed on clean commit
[`72dfa51`](https://github.com/appunni-m/uvicorn-rs/commit/72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f).
The installed-wheel public parity, unified coverage matrix (all 494 cases,
5,298/5,298 native regions, and 3,753/3,753 lines), macOS/Linux/Windows
package jobs, Python-floor wheel, Rust quality, and MSRV jobs completed
successfully. This remains hosted evidence for that earlier revision.

The same-commit performance matrix #13 has a macOS ARM64 parity failure before
timing on `http1.disconnect-before-first-asgi-receive`: Uvicorn returns
`http.disconnect`, while uvicorn-rs returns `http.request` before
`http.disconnect`. Both report the disconnect and serve the follow-up request.
The exact clean local build passed 60 focused repetitions, which does not
explain or erase the hosted failure. The reproduction receipt (`benchmarks/results/2026-10-10/ci13-disconnect-exact72-repro/README.md`)
preserves the hosted row, local run identities, and the unresolved cause.

## Previous local gate (2026-10-09)

The latest local black-box gate passed **494/494** cases on 2026-10-09:
240 live oracle comparisons and 254 target-only fault contracts. Per-case
attribution and all three complete 494-case repeats passed with zero failures,
infrastructure errors, retries, or cases not run. Native coverage is
**5,298/5,298 regions and 3,753/3,753 lines (100%)**. Coverage-MCP measured the
exact report with `source: matches_receipt`, `tests: passed`, and zero missing
region and line observations. The 494-case evidence archive (`benchmarks/results/2026-10-09/asgi-unified-coverage-494/`)
keeps its summary, source/build identity, repeat outcomes, and normal-wheel
parity result in Git. Its generated report, context, and Coverage-MCP payload
remain local-only. The normal non-instrumented extension passed all **240/240**
public oracle cases.

This is source-bound local macOS ARM64 evidence from a dirty working tree based
on revision `f260d78c71e9266c2b3301ab3915f74de5511fc2`, not a clean hosted
release baseline. The measured `src/lib.rs` SHA-256 is
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the
instrumented native SHA-256 is
`af499b36fd0d7f104a31bfd2620644ba06a24eb985ed841bfd2b2d58ce00e17e`, and the
normal native SHA-256 is
`94c677f0e37a52bd80d81571997443a60d69379c16bb2acdcf9831bddb0499b0`. The
aggregate source/input SHA-256 is
`3e883be563df034b41347d1694c7734b853abf272228de59068dbd6d9db57455`; the
Coverage-MCP build ID is
`78576a3a519fb09c8d8a54b03166afe77e645d745f98eb7e73bd1974c8822a8c`. The full
manifest-backed live input matrix remains the behavioral evidence system.

Hosted Linux failures are separate from this local result. The attached run
[#23](https://github.com/appunni-m/uvicorn-rs/actions/runs/37603449348), commit
`6b28666`, used a 490-case snapshot. Its attribution log identifies
`http3.asgi-event-type-string-subclass` as an infrastructure failure; each of
the three complete repeats ended with one infrastructure failure and one case
not run. The report has 237/238 oracle parity cases passing, no behavioral
failures, and 5,106/5,108 regions covered (all 3,612 lines covered). The
independent installed-wheel parity job passed 238/238. The two missing region
locations are not present in the pasted output.

The clean local 491-case run on 2026-10-08 passed this H3 subclass case during
attribution and all three repeat matrices. The attached 490-case output is
therefore historical infrastructure-failure evidence, not a reproduced H3
behavior mismatch.

Later run
[#24](https://github.com/appunni-m/uvicorn-rs/actions/runs/37607369771), commit
`d66548a`, passed its separate public-parity job but failed the unified
coverage job after 25m17s. GitHub retained the `uvicorn-rs-unified-coverage`
artifact, but this environment cannot download it without GitHub credentials;
the hosted-only failure details remain unknown.

Follow-up run
[#25](https://github.com/appunni-m/uvicorn-rs/actions/runs/37619753677), commit
`a394697`, also failed its unified coverage job after 29m52s. Its separate
installed-wheel parity job passed 239/239 with no failures, infrastructure
errors, or cases not run. GitHub retained `uvicorn-rs-unified-coverage` as
artifact `11482802502` (SHA-256
`1793948e9fad9e3872da8b61ac4d9af53ca71bb43bffd7f408d94c62fcc134a5`), but
the download endpoint returns HTTP 401 in this environment. Without the
artifact report, its exact unified-coverage failure remains unknown.

Run [#27](https://github.com/appunni-m/uvicorn-rs/actions/runs/37625295530),
commit `6cd1109`, later attributed 491/491 cases and measured 5,122/5,123
regions with all 3,628 lines covered. Its three matrix repeats encountered
Uvicorn oracle TLS-WebSocket adapter infrastructure failures: the text case
timed out waiting for its handshake, the scope case had no close frame, and a
later repeat stopped before 30 cases ran. No behavioral mismatches were
reported. Run
[#28](https://github.com/appunni-m/uvicorn-rs/actions/runs/37630629260), commit
`dc8cf3f`, attributed 490/491 cases and measured 5,122/5,123 regions. The
attribution and repeat failures were also TLS-WebSocket handshake
infrastructure errors; the installed-wheel public parity job passed 239/239.
At that point the coverage-only source change in the current local report had
not yet run on hosted Linux; run #29 below is its hosted measurement.

Run [#29](https://github.com/appunni-m/uvicorn-rs/actions/runs/37646875313),
commit `376ebdf`, exercised the coverage-only source change. Rust quality and
MSRV passed, but hosted coverage attribution was 490/491 because the Uvicorn
oracle timed out during `websocket-tls.text-round-trip-with-query-and-subprotocol`;
the only recorded app event was `lifespan.startup`, with an empty server log.
The coverage report measured all 5,121 regions and 3,624 lines, but the gate
remained incomplete. Repeat 1 also had an infrastructure timeout in
`websocket-tls.scope-headers-path-query-and-subprotocols` (490/491, zero
behavior failures); annotations do not provide the other repeat summaries.
The separate normal-wheel parity job passed 237/239, with the same class of
Uvicorn oracle timeout on the text case, one following TLS case not run, and
zero behavior mismatches. Upstream Starlette, starlette-rs, systemd, Rust, and
MSRV checks passed; platform/Python-floor jobs were skipped. The two retained
artifacts are `uvicorn-rs-unified-coverage` (ID `11496587798`) and
`uvicorn-rs-public-parity` (ID `11495180440`); unauthenticated download
attempts were denied with HTTP 403. At that point, the source had full local
coverage and full hosted region/line measurement, but no passing hosted
parity/coverage gate. Later hosted runs are recorded below.

A separate earlier 238-case server-log excerpt reports one infrastructure
failure and one case not run but does not name the failed case.

## Hosted CI follow-up (runs #30–#34)

Run [#30](https://github.com/appunni-m/uvicorn-rs/actions/runs/37651700488)
on commit `19cca6f` completed after 23m53s with failure. The installed-wheel
public parity job passed 237/239 cases: the Uvicorn oracle timed out waiting
for the TLS WebSocket handshake in
`websocket-tls.text-round-trip-with-query-and-subprotocol`; the following
scope case was `not_run`. It reported zero behavioral mismatches. Unified
coverage attributed 490/491 cases and measured all 5,121 regions and 3,624
lines, but the gate was incomplete. The same text-case infrastructure timeout
occurred during attribution and repeat 2; the scope case was not run after
those failures. The artifact annotations show only `lifespan.startup` in the
oracle events, both oracle and target processes alive, and an empty Uvicorn
server log. Platform and Python-floor jobs did not run.

Run [#31](https://github.com/appunni-m/uvicorn-rs/actions/runs/37655305687)
on commit `4c40c47` completed after 23m58s with the same class of failure.
Public parity was 237/239: the Uvicorn oracle timed out on the TLS WebSocket
text case and the following scope case was `not_run`, with zero behavioral
mismatches. Unified coverage measured all 5,121 regions and 3,624 lines, but
attribution was 490/491: the scope case hit the oracle handshake timeout.
Repeat 2 hit the text-case timeout and left the scope case `not_run`. As in
run #30, diagnostics showed only `lifespan.startup`, live oracle and target
processes, and an empty Uvicorn log. The local TLS-WebSocket isolation archive
passed its focused two-case pair five times and a 485-case attribution plus
three-repeat gate with zero infrastructure failures. That local result does
not disprove the hosted instability; neither hosted run reports a behavioral
mismatch or establishes a target-server regression. See the
local isolation diagnostics (`benchmarks/results/2026-10-07/asgi-inventory-485/tls-websocket-isolation-diagnostics.json`).

Run [#32](https://github.com/appunni-m/uvicorn-rs/actions/runs/37657779165)
on commit `500860e` completed with failure at 2026-10-07 17:46 UTC. Rust
quality, the Rust minimum, and installed-wheel public parity passed; public
parity was 239/239 with zero behavior or infrastructure failures and no cases
not run. Unified coverage per-case attribution passed 491/491 and measured
5,121/5,121 regions and 3,624/3,624 lines, but the gate was incomplete.
Repeat 3 had 489/491 passed, zero behavior failures, one infrastructure
failure, and one case not run. The Uvicorn oracle adapter timed out waiting
for the TLS WebSocket handshake in
`websocket-tls.text-round-trip-with-query-and-subprotocol`; the following
`websocket-tls.scope-headers-path-query-and-subprotocols` case was not run.
The available check annotation is truncated after Uvicorn startup/listening
logs; its visible diagnostic includes `lifespan.startup` and an oracle process
that is still alive. It does not expose the rest of the per-attempt diagnostic
or establish why the handshake stalled. Uvicorn debug logging was enabled
only for this reference profile, and the separate public parity pass did not
reproduce the timeout. The retained `uvicorn-rs-unified-coverage` artifact is ID
`11501705854` (24,945,569 bytes); its unauthenticated download returned HTTP
401, so raw per-attempt logs remain unavailable here. Platform package and
Python-floor jobs were skipped. The exact hosted failure cause remains
unknown.

The diagnostic change in commit `8c17dea` raises the bounded failure detail
from 500 to 5,000 characters and includes the target server-log tail in oracle
adapter diagnostics. Run
[#33](https://github.com/appunni-m/uvicorn-rs/actions/runs/37663278880)
exercised it and completed after 30m41s with failure. Rust quality, the Rust
minimum, and installed-wheel public parity passed; public parity was 239/239
with no failures, infrastructure errors, or cases not run. Unified coverage
measured all 5,121 regions and 3,624 lines, but the gate was incomplete at
489/491 cases.

The check annotations identify two attribution infrastructure failures:
`websocket-tls.text-round-trip-with-query-and-subprotocol` and
`websocket-tls.scope-headers-path-query-and-subprotocols`. Repeat 1 reports
490/491 passed with one infrastructure failure on the scope case and no case
not run. The visible diagnostics show only `lifespan.startup`, a successful
HTTPS readiness request, both server processes alive, no Uvicorn WebSocket
access record, and an empty target log. The Uvicorn oracle timed out waiting
for the TLS WebSocket handshake response before ASGI dispatch. No behavioral
mismatch is reported; the underlying cause remains unknown. The other repeat
details are in the protected artifact and are not asserted here.

GitHub retained `uvicorn-rs-unified-coverage` as artifact `11503562361`
(25,016,587 bytes); its anonymous download returned HTTP 401. The package and
Python-floor jobs were skipped. This is consistent with the previous hosted
TLS-WebSocket oracle timeouts and shows that the expanded diagnostic records
the empty target log, but it does not establish the cause.

Run [#34](https://github.com/appunni-m/uvicorn-rs/actions/runs/37667890595)
on `ad7d698` completed after 31m02s with failure. Rust quality, the Rust
minimum, and installed-wheel public parity passed; public parity was 239/239
with no behavior failures, infrastructure errors, or cases not run. Unified
coverage remained incomplete at 490/491 cases and measured 5,119/5,121
regions and 3,620/3,624 lines. Attribution and repeats 2 and 3 failed on
`websocket-tls.text-round-trip-with-query-and-subprotocol`; each repeat also
left `websocket-tls.scope-headers-path-query-and-subprotocols` not run. The
reported error is a Uvicorn oracle timeout while waiting for the TLS
WebSocket handshake response. The captured oracle events contain only
`lifespan.startup`; both server processes remained alive, Uvicorn logged its
HTTPS readiness request but no WebSocket request, and the target log was
empty. This still does not establish whether the stall is in the client,
TLS, or server path. Coverage annotations identify two missing native regions
at `src/lib.rs:3017-3019` and `src/lib.rs:3020`. The matching local full report
attributes those spans to `fault.http2.connection-disconnect-completes-eof-recheck`;
the hosted summary does not show whether this case reached the same path, so
the difference remains unresolved and is tracked separately from the
WebSocket timeout. GitHub retained `uvicorn-rs-unified-coverage` (23.8 MB,
SHA-256 `873d16a5eb54b832ce9488d800103bafd16a7bf2afce30ae53b6400483592a5d`).
Platform package and Python-floor jobs were skipped. A local-only diagnostic
patch now captures the WebSocket client's protocol trace on this failure path;
run #34 predates that patch.

Run [#35](https://github.com/appunni-m/uvicorn-rs/actions/runs/37672645704)
on commit `1a72c9b` completed with an overall failure on 2026-10-07. Rust
quality, the minimum-version build, installed-wheel public parity, and unified
coverage passed. Public parity was 239/239; hosted coverage was 491/491 cases,
5,121/5,121 regions, and 3,624/3,624 lines. The hosted matrix predates the
local strengthening of the H2 EOF fault contract described below. Platform
package job failures are recorded in [release status](releases.md#current-state).
The retained unified-coverage artifact is ID `11506803058`, SHA-256
`d107cfb007ae41673feb025253cdd00706168f51df411fa5fdfc6c6fdb3a910c`.

## Hosted verification (runs #36–#39)

Runs [#36](https://github.com/appunni-m/uvicorn-rs/actions/runs/37679543470)
and [#37](https://github.com/appunni-m/uvicorn-rs/actions/runs/37684421046)
passed the unified coverage job. Run #37 is on exact main commit `e617f13`;
its check annotation reports 491/491 cases, 5,121/5,121 regions and 3,624/3,624
lines. The job runs one attribution pass and three complete matrix repetitions.
The separate installed-wheel parity gate passed 239/239. Run #37 failed
afterward in the platform package jobs; see [release status](releases.md#current-state).
The retained hosted report artifact cannot be downloaded without repository
authentication from this environment. This closes the hosted coverage gate for
the current committed source; the local Coverage-MCP receipt requirement for a
public release remains separate.

Run [#38](https://github.com/appunni-m/uvicorn-rs/actions/runs/37688528361)
on commit `226ab13` also passed hosted attribution and all three complete
repeats: 491/491 cases, 5,121/5,121 regions, and 3,624/3,624 lines. Its normal
installed-wheel public parity passed 239/239. The run failed later in the
macOS package consumer because the probe certificate had a duplicate
extension OID; Linux and Windows package jobs passed, while Python-floor was
skipped. See [release status](releases.md#current-state). This updates hosted
coverage evidence for `226ab13`; the source-matched local Coverage-MCP receipt
requirement for a public release remains separate.

Run [#39](https://github.com/appunni-m/uvicorn-rs/actions/runs/37692260364)
on exact main commit `a78b4a925654ee0a5fb80814074ca2b0224bb094` passed hosted
parity (239/239), attribution and all three complete repeats (491/491 cases),
with 5,121/5,121 regions and 3,624/3,624 lines. Its package matrix and Python
3.9.25 consumer also passed. This is the current hosted commit-bound coverage
result.

Coverage-MCP also re-reviewed the local full report for the EOF recheck
archive. The generated report and MCP response are local-only and not
committed. That review reported `source: matches_receipt`, `tests: passed`,
5,121/5,121 regions, and zero gap groups. A hash check matched all 83 recorded
coverage input files against the checkout used for the report. It records
revision `1a72c9b` and a dirty working tree, so it is source-matched local
evidence; hosted run #39 is the clean commit-bound result.

<a id="previous-full-verification-492-cases"></a>
## Previous full verification (492 cases; unified matrix)

The previous 492-case report recorded revision
`490d9b40f4af46385e8f9e184c569a93004b3d74` from a dirty
working tree. The unified report SHA-256 is
`53d1f1bf0d8e7e751531ad7f0db9a1b63b3db9b9d4ee49bb1c269b518cf845e4`; the
context receipt binds source SHA-256
`96cbe266b305efd4a75192c80a832577daa664860cf0fafb9db1a6a47b856e72` and
`src/lib.rs` SHA-256
`336fb764d63c8e9cd2b24f2e1ec032c9bcf6fb4d0dc27c038e7d7d44a8229c52`.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 492/492 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 492/492 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 492/492 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 492/492 | 0 / 0 / 0 / 0 |
| Oracle parity in each repeat | 239/239 | 0 failed |
| Target-only contracts in each repeat | 253/253 | 0 failed |
| Native regions | 5,181/5,181 | 0 missing |
| Native lines | 3,671/3,671 | 0 missing |
| Coverage-MCP region gap groups | 0 | source matches; tests passed |
| Normal non-instrumented oracle parity | 239/239 | 0 / 0 / 0 / 0 |

The source-scope report has complete case-to-region attribution and its
per-case profile union matches the aggregate. Coverage-MCP build ID is
`97bbf91445ae75a120b93dab1f808b8ede3a803a4aa131bad40a5308da1a228e`.
Instrumented extension SHA-256 is
`7406560cdc52cf5f583b7f13307686753fddab1f0fb511377b666dc51e2bac21`.
This tracked document records the result and source/build identity. The
generated full report, context receipt, Coverage-MCP response, and raw repeat
outputs remain local-only. This is local source-bound coverage evidence, not a
performance result or a claim of complete official ASGI conformance.

<a id="current-full-verification-494-cases"></a>
## Historical full verification (494 cases; unified matrix)

The historical compact archive is
`asgi-unified-coverage-494` (`benchmarks/results/2026-10-09/asgi-unified-coverage-494/`).
It records revision `f260d78c71e9266c2b3301ab3915f74de5511fc2` from a dirty
working tree. `src/lib.rs` SHA-256 is
`56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the
aggregate source/input SHA-256 is
`3e883be563df034b41347d1694c7734b853abf272228de59068dbd6d9db57455`.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 494/494 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 494/494 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 494/494 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 494/494 | 0 / 0 / 0 / 0 |
| Oracle parity in each repeat | 240/240 | 0 failed |
| Target-only contracts in each repeat | 254/254 | 0 failed |
| Native regions | 5,298/5,298 | 0 missing |
| Native lines | 3,753/3,753 | 0 missing |
| Coverage-MCP region gaps | 0 | source matches; tests passed |
| Coverage-MCP line gaps | 0 | source matches; tests passed |
| Normal non-instrumented oracle parity | 240/240 | 0 / 0 / 0 / 0 |

The per-case attribution matches the aggregate profile union. Coverage-MCP build
ID is `78576a3a519fb09c8d8a54b03166afe77e645d745f98eb7e73bd1974c8822a8c`.
The instrumented native extension SHA-256 is
`af499b36fd0d7f104a31bfd2620644ba06a24eb985ed841bfd2b2d58ce00e17e`; the
normal extension SHA-256 is
`94c677f0e37a52bd80d81571997443a60d69379c16bb2acdcf9831bddb0499b0`. The
archive retains the compressed report, context receipt, combined Coverage-MCP
region and line receipts, three repeat summaries, and normal public-parity
receipt. This local dirty-worktree evidence does not establish hosted
verification on the same commit, performance, or complete official ASGI
conformance.

<a id="current-full-verification-491-cases"></a>
<a id="current-full-verification-491-cases-eof-fault-consumption-asserted"></a>
## Previous full verification (491 cases; EOF fault consumption asserted)

The previous archive is
`asgi-eof-recheck-fault-consumption-491` (`benchmarks/results/2026-10-08/asgi-eof-recheck-fault-consumption-491/`).
It records the earlier 491-case report. The working tree was
dirty at revision `1a72c9b3ab18e01389b1e19efbc76bf569e98730`; the unified report
SHA-256 is `bc49875bbdbdc0486465de314101b5124a552476a650296871171e9fe79129e1`,
and its context receipt binds the same source/build identity. The tracked change
in this measurement is the parity-runner assertion that consumes the named
fault before allowing the HTTP/2 follow-up request.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 491/491 | 0 / 0 / 0 / 0 |
| Oracle parity in each repeat | 239/239 | 0 failed |
| Target-only contracts in each repeat | 252/252 | 0 failed |
| Native regions | 5,121/5,121 | 0 missing |
| Native lines | 3,624/3,624 | 0 missing |
| Coverage-MCP region gap groups | 0 | source matches; tests passed |

The strengthened H2 case asserts that the instrumented target cleared
`UVICORN_RS_COVERAGE_FAULT_FILE` for
`server.connection-io.eof-recheck.pause` before the follow-up request, then
requires `http.disconnect` and a 200 follow-up. The focused case and all full
matrix runs passed. No temporary Rust trace instrumentation remains in the
source.

The run used CPython 3.12.13, Rust 1.98.1, cargo-llvm-cov 0.8.7, and macOS
15.7.7 ARM64. The instrumented extension SHA-256 is
`2fcd0eeb88f38d7c07801335e37416837761fd0d4a340d86aab57ba8638dc2d5`. The
generated report, context, and exact Coverage-MCP page are local-only; the
tracked archive keeps the summary, source/build identities, repeat bundle, and
normal parity result. This local result does not establish benchmark
performance. Hosted run #37 independently passed the unified gate on the exact
commit tested there. Run #38 on `226ab13` also passed hosted unified coverage;
the later `a78b4a9` package-probe fix changes no `src/lib.rs` coverage source.

## Previous full verification (491 cases; before EOF fault-consumption assertion)

The archive is
`asgi-coverage-region-fix-491` (`benchmarks/results/2026-10-07/asgi-coverage-region-fix-491/`).
The tracked archive contains a summary, three full-matrix repeat results, a
normal-build oracle result, and an evidence index. Its generated compressed
report, context receipt, and Coverage-MCP page are local-only. The report
SHA-256 before compression is
`4478d365b091dc9094462c13903c3e49d2450ff9f90f5dd8f4cf89a8f2e3bf8e`; the
Coverage-MCP build ID is
`93a183b2b3a8330d6ad74e170416c68c456b658d884be7f3a96dc637b0d337dc`.
Case-to-region attribution matches the union of per-case profiles.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 491/491 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 491/491 | 0 / 0 / 0 / 0 |
| Oracle parity in each repeat | 239/239 | 0 failed |
| Target-only contracts in each repeat | 252/252 | 0 failed |
| Native regions | 5,121/5,121 | 0 missing |
| Native lines | 3,624/3,624 | 0 missing |
| Coverage-MCP region gap groups | 0 | source matches; tests passed |
| Normal non-instrumented oracle parity | 239/239 | 0 / 0 / 0 / 0 |

The coverage change removes the conditional guard around a `cfg(coverage)`
diagnostic inside the HTTP receive lock-contention branch. The existing
forced-contention input now attributes this branch consistently. The log call
remains excluded from production builds.

The instrumented run used CPython 3.12.13, Rust 1.98.1, cargo-llvm-cov 0.8.7,
and macOS 15.7.7 ARM64. Coverage measures default-feature `src/lib.rs` with
`cfg(coverage)`; Python code, dependencies, optional diagnostics, other
platforms, the official full ASGI suite, and performance are outside this
coverage claim. One infrastructure-only attribution retry was permitted but
not used. The checkout was dirty, so this is not a clean hosted release result.

## Superseded full verification (491 cases; before receive-region fix)

The prior archive is
`asgi-empty-subprotocol-491` (`benchmarks/results/2026-10-07/asgi-empty-subprotocol-491/`).
It remains the evidence for adding the empty WebSocket subprotocol parity case;
its report passed 491-case attribution and three repeats with 5,123/5,123
regions and 3,628/3,628 lines before the coverage-only HTTP receive diagnostic
adjustment. The 494-case archive above is the source/build receipt for that
run's region denominator.

## Superseded full verification (490 cases)

The superseded acceptance archive is
`famh-concurrent-load-acceptance` (`benchmarks/results/2026-10-07/famh-concurrent-load-acceptance/`).
It contains the compressed unified LLVM report and matching context receipt,
the full Coverage-MCP structured response, three raw full-matrix repeat
results, a normal-build 238-case oracle report, and the focused five-case
load/shutdown result. The report SHA-256 before compression is
`ca2814eeb89409c84a6466ce5fd4fc2348881cf29ac35577281bae0da87241a7`;
the build ID is
`7257fa49fedfe976b1368cac2fd3656128ff23fde348228da30ce7315a326828`.
The case-to-region attribution matches the union of profiles.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 490/490 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 490/490 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 490/490 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 490/490 | 0 / 0 / 0 / 0 |
| Native regions | 5,108/5,108 | 0 missing |
| Native lines | 3,608/3,608 | 0 missing |
| Coverage-MCP region gap groups | 0 | source matches; tests passed |
| Normal non-instrumented oracle parity | 238/238 | 0 / 0 / 0 / 0 |
| Focused load and zero-timeout parity | 5/5 | 0 / 0 / 0 / 0 |

The instrumented run used CPython 3.12.13, Rust 1.98.1, and macOS 15.7.7
ARM64. Its native scope is default-feature `src/lib.rs` with `cfg(coverage)`;
Python code, dependencies, optional diagnostics, other feature combinations
and platforms, the official full ASGI suite, and performance are outside this
coverage claim. The ordinary full oracle run used the same fixture and
reference versions with the normal local extension. It is not an installed
wheel or release audit.

The new workload cases exercise 32 concurrent HTTP/1.1 connections and 32
HTTP/2 streams (four 100 ms slow-reader rounds each), 16 HTTP/3 streams (three
rounds), and 16 WebSocket sessions (four rounds). They compare response
lengths and SHA-256 fingerprints, require full concurrency and healthy
follow-up requests, verify application tasks return to zero, require no net
idle Python-task growth, and constrain the spread in late-round RSS samples to
16 MiB. These are fixed-load stability checks, not an absolute memory cap or a
throughput/latency benchmark. A separate zero-grace HTTP/1.1 shutdown case
holds 16 ASGI response streams, resets their clients, requires 16 cancellations
and zero completed responses, then checks bounded process exit and completed
lifespan shutdown. Shutdown duration is recorded for diagnosis only.

The exact inputs, results, environment, source/build receipt, and commands are
documented in the archive README and evidence index.

## Historical full verification (485 cases; earlier October 7 source)

The earlier archive is
`asgi-inventory-485` (`benchmarks/results/2026-10-07/asgi-inventory-485/`).
Its tracked README and evidence index record run identity and results. The
compressed LLVM report, context receipt, full Coverage-MCP response,
structured receipt, generated log, compressed matrix bundle, and normal-build
exclusion audit bundle are local-only; the bundles contain generated logs. The
normal-wheel parity result, wheel consumer result, and exclusion receipt
remain tracked. The report SHA-256 before compression is
`457ae9d02ae1bee0f5f6d7a75315fb162b0b9c14c02bb50e721f2ca9fd64067b`.
Coverage-MCP reported matching source/build identity and `tests: passed`.
Case-to-region attribution is verified against the profile union.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 485/485 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 485/485 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 485/485 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 485/485 | 0 / 0 / 0 / 0 |
| Native regions | 5,106/5,106 | 0 missing |
| Native lines | 3,606/3,606 | 0 missing |
| Coverage-MCP gap groups | 0 | source matches; tests passed |
| Normal-wheel public parity | 233/233 | 0 / 0 / 0 / 0 |
| Normal exclusion workflows | 3/3 | 0 / 0 / 0 / 0 |
| Normal exclusion checks | 16/16 | all pass |
| Installed-wheel consumer probe | 1/1 | all pass |

The matrix contains 233 oracle comparisons and 252 target-only contracts. The
target-only set includes public support contracts as well as deterministic
fault contracts; it is not 252 injected failures. The normal wheel is the
macOS ARM64 abi3 wheel built from the same Rust source; its SHA-256 is
`8c33d0abccef25d7f07b662d18b01703908707b933f0f705c1adc58ee52fa9e2`, and its
native extension SHA-256 is
`c26e55e15cd290fff44edf3212115577bced7fe2459da83955361fcc1fb1f98b`.

The instrumented run used CPython 3.12.13, Rust 1.98.1, and macOS 15.7.7 ARM64.
Its measured scope is default-feature `src/lib.rs` with `cfg(coverage)`; Python
code, dependencies, optional diagnostics, other feature combinations and
platforms, the official full ASGI suite, and performance are outside this
native coverage claim. The source checkout was dirty. A separate preliminary
485-case run used infrastructure retries while diagnosing a TLS WebSocket
profile-reuse timeout; it is retained under `preliminary-retry-tolerant/` and
is not the clean result summarized above. The final no-retry runs isolate the
TLS WebSocket close case at a fresh server boundary; the diagnostic record is
`tls-websocket-isolation-diagnostics.json` (`benchmarks/results/2026-10-07/asgi-inventory-485/tls-websocket-isolation-diagnostics.json`).

The case inventory is a focused black-box map, not full ASGI conformance. The
known cross-name response-header ordering deviation and unsupported extensions
are listed in the [support matrix](support-matrix.md) and [ASGI case
inventory](asgi-case-inventory.md).

## Historical full verification (473 cases; October 6 source inventory)

The fixed archive at
`request-body-pump-ownership-coverage-473` (`benchmarks/results/2026-10-06/request-body-pump-ownership-coverage-473/`)
retains a tracked summary and evidence index with artifact hashes, plus the
normal-wheel parity result and normal exclusion receipt. The generated unified
report, context sidecar, exact Coverage-MCP response, and audit bundle with
generated logs are local-only. The uncompressed report SHA-256 is `6bc08ebf1be237392e46094d665517179866abb6a40345f7f9530123424697c8`;
its context SHA-256 is
`65a35c22f82a27f78d305ab2d4e215296ac22ddba1ebb34756f1050fb3bd00e2`. Coverage
MCP build ID is
`b90d8c1eba8f88fb6257796a6ad5759ec2a25776f7dbceb2d7ada1369ae89300`.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 473/473 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 473/473 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 473/473 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 473/473 | 0 / 0 / 0 / 0 |
| Native regions | 5,106/5,106 | 0 missing |
| Native lines | 3,606/3,606 | 0 missing |
| Coverage-MCP gap groups | 0 | source matches; tests passed |
| Normal-wheel public parity | 225/225 | 0 / 0 / 0 / 0 |
| Normal exclusion workflows | 3/3 | 0 / 0 / 0 / 0 |
| Normal exclusion checks | 16/16 | all pass |

The 248 target-only contracts include public-input support contracts as well
as deterministic native fault contracts; they are not all native fault
injections. The coverage run used CPython 3.12.13, Rust 1.98.1, and macOS
15.7.7 ARM64. Its measured scope is default-feature `src/lib.rs` with
`cfg(coverage)`; Python code, dependencies, optional diagnostics, other feature
combinations and platforms, the official full ASGI suite, and performance are
outside this native coverage claim.

The installed normal wheel native SHA-256 is
`c26e55e15cd290fff44edf3212115577bced7fe2459da83955361fcc1fb1f98b`. Its
225-case public parity report SHA-256 is
`6b06574e359054d549b756a6a27cca7bd4af00580e83c01d3407697c53b007db`; the
normal exclusion receipt SHA-256 is
`59dba2e13389d7e7f6b9e4f1c973942a80cf94522e0b8a90c2ddc1cd3b471766`. The
exclusion audit covers 221 registered native fault points, confirms their
absence from the imported release wheel, and passes one public oracle case
plus two public support contracts without native injection. The audit retains
16/16 successful checks in the evidence archive.

The repeated HTTP/3 sequence sends 128 one-byte POST requests on one
connection. Each of the three complete matrix repeats records 128 target
responses matching all 128 oracle responses. Its instrumented attribution log
also records exactly `request-body pumps joined: 128`. The case-specific result,
server log, and structured three-repeat receipt are in the same archive.

## Historical full verification (460 cases; earlier October 6 source)

The fixed archive at
`http3-peer-close-coverage-460` (`benchmarks/results/2026-10-06/http3-peer-close-coverage-460/`)
retains a tracked summary and evidence index with artifact hashes, the
normal-wheel parity result, and the normal exclusion receipt. The audit bundle
with generated logs, unified report, context sidecar, and exact Coverage-MCP
response are local-only.
The uncompressed report SHA-256 is
`c45f978fc76174636ecb7d4062d23e68c4084e2fc7355d090aff99823f606d53`; its
context SHA-256 is
`4415053c90832ce2747863a1412c5827fcc0f127f795d39455082ac5a02c4498`. The
coverage build/MCP ID is
`8a4ca567f4aeef6c7b9010d36f78384187dab7366c731410b02490aa08a2e562`.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 460/460 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 460/460 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 460/460 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 460/460 | 0 / 0 / 0 / 0 |
| Native regions | 4,810/4,810 | 0 missing |
| Native lines | 3,395/3,395 | 0 missing |
| Coverage MCP gap groups | 0 | source matches; tests passed |
| Normal-wheel public parity | 221/221 | 0 / 0 / 0 / 0 |
| Normal exclusion cases | 3/3 | 0 / 0 / 0 / 0 |
| Normal exclusion checks | 16/16 | all pass |

The 239 target-only cases include the two public header-capacity support
contracts; these are not all native fault injections. The normal parity report
SHA-256 is
`eea7e61ff11934b1c0107cfd38d01cc792ff0fe260fed73dcedf6eb92e3551a7`; its
normal native identity matches the wheel member. The normal exclusion receipt
SHA-256 is
`58a940d284b84ab347322fa03b327f9ac54c250534452624487925d861aa6d00`.

## Historical full verification (451 cases; October 5 source)

The authoritative local report is
`build/asgi-coverage/unified-http3-owned-request-drain-451-2026-10-05/full-attempt-2/coverage-report.json`.
Its status is `complete` and coverage gate is `passed`. The sibling
`full-proof-receipt.json` one level above retains source/build identities,
case observations, attribution artifacts, all three complete-repeat receipts
and final-drain attribution. The fixed repository archive preserves the
full proof receipt (`benchmarks/results/performance-investigation-2026-10-05/http3-task-reaping-coverage/full-proof-receipt.json`),
attribution/repeat results, and source snapshots. The generated lossless
report, context sidecar, unfiltered MCP pages, attribution bundle, and logs are
local-only. Its source/input fingerprint is
`277319fa41871fbe77d4423c47cdee89ada7990cecc219a164c675428fab79ef`;
the report SHA-256 after MCP attachment is
`830e2565823c048d5a1c0c306e151b667c5cfd8d633794e59b538ab70b62fbe1`.
The adjacent `coverage-report.json.context.json` SHA-256 is
`921bd47217c6a0488f482568e1bf1f758d785dd970753e04455d970d6482f779`.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 451/451 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 451/451 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 451/451 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 451/451 | 0 / 0 / 0 / 0 |
| Native regions | 4,778/4,778 | 0 missing |
| Native lines | 3,371/3,371 | 0 missing |
| Unfiltered MCP gap groups | 0 | source matches; tests passed |
| Normal-build public parity | 214/214 | 0 / 0 / 0 / 0 |
| Selected normal exclusion cases | 3/3 | 0 / 0 / 0 / 0 |
| Normal exclusion checks | 15/15 | all pass |

The unfiltered `full-attempt-2/coverage-mcp-pages.json` records build ID
`69e1ca57e011f6ab6e9ef1e7cfa6cd9071ea6ac47320f13415a176d47fdb9474`,
zero missing observations and no excluded functions or locations. The new
`fault.http3.connection-accept-error-aborts-held-response` case solely covers
both formerly missing spans, `3878:20–26` and `3878:57–3880:6`, through actual
remote connection-error termination, owned-task cancellation and Python
cleanup. The original first-accept fault case remains separate. Its
`stream_reset` field follows the probe's existing `recv_data` error convention;
it does not independently prove a QUIC `RESET_STREAM` frame. The proof combines
actual remote `ApplicationClosed(0x102)`, `body_stream_error`,
`connection_closed`, diagnostics and application events.

The measured scope remains default-feature `src/lib.rs` with `cfg(coverage)`
on macOS ARM64 in a dirty checkout. Python code, dependencies, optional
diagnostics, other features/platforms, full official ASGI conformance and
performance are outside this native coverage claim. This is not a clean
committed release baseline.

## Historical normal-build verification (451-case source)

The accepted final attempt is
`build/asgi-coverage/normal-gates-held-response-451-2026-10-05-attempt-3/`.
The fixed repository archive preserves the
normal-gate receipt (`benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/normal-gates-receipt.json`),
public parity result (`benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/public-parity-result.json`),
exclusion audit (`benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/receipt.json`)
and identity captured before public parity (`benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/benchmark-identity-before-public-parity.json`).
Its restored native SHA-256 is
`0e13bb6d56cbccd53b2f34197358563d7fbaa04ad7cac69f359fd1a60d93d19d`,
on the unchanged Rust source above. The portable maintained identity was
captured before public parity in `benchmark-identity-before-public-parity.json`,
with SHA-256
`dcc0d5f7c8d210a8fa35069240aa4fa25ca4520e4f6f26a64fbfdf243bc9cde2`.
The maintained identity matched exactly after both public parity and the audit.
Explicit empty Cargo wrappers preserve the frozen client identity; archived
source snapshots were settled before capture.

`public-parity-result.json` records 214/214 live oracle comparisons with zero
failures, infrastructure errors or cases not run. Its SHA-256 is
`f71c41a07832922bccfad3cc5f09ab85f980b32ceb6f429316bc4ab4a61c8d75`.
The fresh normal exclusion `receipt.json` records 3/3 selected live cases and
all 15 checks passed, with SHA-256
`0bd7a34e08fd0894ba4db70028113d8f901b129ecd8672034120ef45c884b65f`.
It uses a disposable copy of the verified normal library and leaves the
workspace extension unchanged. The cases are one live HTTP oracle comparison
and both public header-capacity support contracts; they perform no native
fault injection.

All 211 registered native fault points, control and diagnostic literals are
absent from both raw binary and strings inspection, including
`http3.request-task.panic-after-response` with zero matches. LLVM
instrumentation, native fault-control exports and CLI fault options are absent.
The armed control file is ignored. These checks attest the named normal build;
the two public support contracts remain outside the 214 oracle denominator.

Earlier normal attempt 1 passed 214 behavioral cases but invalidated the
maintained identity when the default Cargo wrapper rebuilt the client.
Attempt 2 passed 214 public cases and the three-case audit, but newly archived
source files changed the editable-checkout fingerprint. Their raw and
identity-invalid receipts remain at the preceding attempt paths; neither is
the accepted identity proof. The final attempt recaptured the settled identity
and passed both gates without that change.

## Historical failed full verification (450 cases)

The failed report is
`build/asgi-coverage/unified-http3-task-reaping-450-2026-10-05/coverage-report.json`;
its adjacent `evidence-status.json` records 450/450 attribution passes with
zero retries, but the three full repeats have 403, 403 and 402 passes. Each
stopped with 46 cases not run; their infrastructure failure counts are 1, 1
and 2. The 128-response Hypercorn sequence timed out in each repeat; repeat
three also had a Uvicorn TLS WebSocket handshake timeout. Coverage measured
4,776/4,778 regions and 3,369/3,371 lines. Unfiltered MCP matched the source,
retained `tests: failed`, and reported the two final-drain observations at
`src/lib.rs:3878–3880`. Those profiles do not establish the enlarged matrix's
gate and were not merged into its fresh full run.

## HTTP/3 workflow evidence

The controlled public A/B receipt is
`build/asgi-coverage/http3-grease-public128-ab-2026-10-05/ab-receipt.json`.
With `h3_grease: true`, Hypercorn's first request timed out receiving headers
and the peer-close case was not run. With `false`, both selected cases passed:
each server returned 128 identical responses, and both peer-close processes
exited cleanly without connection errors. Only that sequence's GREASE input
changed; reference packages, deadlines, production source and installed native
were unchanged. The maintained sequence now sets `h3_grease: false`.
This instrumented 2/2 result supports that client interoperability choice;
it is not full regression, normal-build parity or direct parser tracing.

The new held-response accept-error contract passed its selected instrumented
case (1/1), with zero failures, infrastructure errors or cases not run. Its
receipt is
`build/asgi-coverage/unified-http3-owned-request-drain-451-2026-10-05/selected-proof-receipt.json`;
the full structured result is `selected-attempt-3/parity-result.json` beside it.
The first response remained status 200 with body `first/` and a real stream
error; the remote application close code was 258 (`0x102`). Two cancelled-task
join diagnostics preceded the original injected accept error. The application
recorded `response.reset.hold` then `response.reset.app-cancelled`, and the fresh
follow-up returned 200 without reset. The receipt binds the unchanged source
and its instrumented native
`41bf61b21be0443b5d1e02329e7ae2e6e893fe17a4b42e636e4367a5aca91cfe`,
client, manifest and runner identities.
This target-only proof is not an oracle comparison or the full 451-case gate;
its selected profiles remain separate from the fresh full attribution union.

The historical shared-write source/build named below passed all 448 attribution
cases and three full 448-case repeats with zero
failures, infrastructure errors, retries or cases not run. It measured
**4,763/4,763 LLVM regions and 3,360/3,360 lines (100%)** with zero unfiltered
Coverage-MCP gap groups, `source: matches_receipt` and `tests: passed`.
Its normal build separately passed 213/213 public comparisons and every
exclusion check with three selected live cases. Those results attest that
named prior source/build, not the changed checkout. Profiles from different
sources are not merged.

The native coverage scope is `src/lib.rs`, default features, and
`cfg(coverage)` instrumentation on macOS ARM64. It excludes Python code,
dependencies, optional diagnostics, other feature combinations and platforms,
full official ASGI conformance, and performance. Dirty-working-tree evidence
is not a clean committed release baseline.

<a id="current-full-verification-448-cases"></a>

## Historical full verification (448 cases; shared-write source)

The authoritative local report is
`build/asgi-coverage/unified-shared-write-clean-close-448-2026-10-05/coverage-report.json`.
Its status is `complete` and coverage gate is `passed`. The repository
evidence archive (`benchmarks/results/performance-investigation-2026-10-05/current-coverage/archive-manifest.json`)
preserves source/input snapshots and all three full-repeat receipts. The
lossless report, unfiltered MCP receipt, repeat logs, native binaries, and raw
profiles remain at their original local paths and are not committed.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 448/448 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 448/448 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 448/448 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 448/448 | 0 / 0 / 0 / 0 |
| Normal-build public parity | 213/213 | 0 / 0 / 0 / 0 |
| Selected normal exclusion cases | 3/3 | 0 / 0 / 0 / 0 |
| Native regions | 4,763/4,763 | 0 missing |
| Native lines | 3,360/3,360 | 0 missing |
| Unfiltered MCP gap groups | 0 | source matches; tests passed |

The measured Rust source SHA-256 is
`81c239b5f596cf4be18cc71bc3b537c02224c0f1e1ab35174e6386f5203510cd`;
the instrumented native SHA-256 is
`2aac17afa64ebc070555fdb03913747a051b4b3a00512633f7c54c4ac15c3378`.
The complete source/input fingerprint is
`146226d83e3f73ce285982eb1702723742972e7c6c592435d60e7286455882b7`.
The uncompressed report SHA-256 is
`c8ef9a6039c72a8ad0433366b837699910f22a7592cebc71e1f04f0bef58297c`;
MCP build ID is
`70b5d44d925d0b6a4885890607320c600d4086a50b9d66a74c27f0ed7a7a6716`.
Raw attribution and repeat artifacts are under
`artifacts/1f04acb17846461695d774b0c680f069/` in the local report directory.

That verification restored the workspace extension to its normal native with SHA-256
`8f69afda0be9d121d304c674d5638f470da6939fbed58ce809457284df6585b6`.
Its public parity receipt (`benchmarks/results/performance-investigation-2026-10-05/current-normal/public-parity.json`)
records 213/213 passes with zero failures, infrastructure errors or cases not
run. Formatting, Clippy and build logs are preserved beside that receipt.
The independent normal exclusion audit (`benchmarks/results/performance-investigation-2026-10-05/current-coverage/normal-exclusion/receipt.json`)
passes every check and its exact three selected cases: one ordinary HTTP
oracle comparison and both public header-capacity contracts. Registered fault
points, control/diagnostic literals and LLVM instrumentation are absent; an
armed fault file is ignored. Its receipt SHA-256 is
`1994c244577def60255e5ecc4ee3de232e32a5fbe46c2b614dc03323931e8fd5`.
This is local dirty-checkout evidence, not a clean committed release baseline
or a performance, security or full ASGI-conformance claim.

## Historical 448-case snapshot with MCP function gaps

The previous generic-write-helper report at
`build/asgi-coverage/unified-vectored-clean-close-448-2026-10-05/coverage-report.json`
records 448 passing attribution cases and three complete passing repeats.
Its aggregate summary is 4,758/4,758 regions and 3,358/3,358 lines, but MCP
reports one function group with **seven missing observations**. It is retained
as incomplete zero-gap evidence (`benchmarks/results/performance-investigation-2026-10-05/current-coverage/previous-generic-helper/evidence-status.json`).
The report's generated aggregate gate says `passed`; that does not waive the
unfiltered MCP function gap.

That source is
`b6421bc45a55e194b4924661f4492b06c2860b47d1bf97d17991145b9094d028`;
its instrumented native is
`1738b05415f22f312990282e17fa294382d79cd5e0f486d6a4f95e4c64cb6e97`.
The scalar `FnOnce` write-helper instantiation lacked the injected-error and
real-write-error observations, while the vectored instantiation covered the
same source spans. The subsequent shared-write source uses a borrowed scalar/vectored buffer
enum and one fallible handler instead of separate closure instantiations.
No observations or functions were excluded. The unchanged 448 inputs were
remeasured on the new source/build; older profiles were not merged.

<a id="current-full-verification-447-cases"></a>

## Historical full verification (447 cases; after normal-build exclusion correction)

This snapshot's inventory had 70 input files and 60 operations: 212 live oracle
comparisons and 235 target-only contracts. Its source/build passed all 447
attribution cases and three complete repeats independently.

The authoritative report is
`build/asgi-coverage/unified-production-exclusion-447-2026-10-05/coverage-report.json`.
Its status is `complete` and coverage gate is `passed`. All 447 attribution
cases and each complete repeat pass in one attempt without infrastructure
failures. Unfiltered `coverage-mcp-regions.json` records zero gap groups,
`source: matches_receipt`, and `tests: passed`. The report attaches its
normal-build audit and the listener, protocol-detection, and header-capacity
defending evidence with their hashes.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 447/447 | 0 / 0 / 0 / 0 |
| Native regions | 4,734/4,734 | 0 missing |
| Native lines | 3,333/3,333 | 0 missing |

The measured source SHA-256 is
`187ebfb2311bc793b2f1d3d98c5dc9f3f9cdc5e50805e3f4210e1179769984f8`;
the instrumented native SHA-256 is
`00f69535e61feb7cb127f7dbc912166fcded45e6f6c67071fb387460ac30fef2`.
The complete source/input fingerprint is
`7bbd83dc56c9417c1830b686e951e99f3de2f5012654289679f8139cb2346d57`.
The exact source, instrumented native, and normal native are preserved under
`artifacts/4723e6bea0da4e5f9a7e0d08e1af148d/` in the report directory.
The workspace extension was restored to the audited normal build, whose
SHA-256 is
`ba5a6f65508a0d2271a52df9893d9f27f94985144c8a5868e0c10ccdaec9ad89`.
This completed that source/build's local evidence gate; it does not establish a
performance gain, full ASGI conformance, or a clean committed release baseline.

<a id="normal-build-exclusion-correction"></a>

## Historical normal-build exclusion correction

The first normal-build audit is preserved under
`build/asgi-coverage/normal-build-result-state-audit-2026-10-05/failed-compiled-test-error-branches/`.
Its three selected live cases passed: one ordinary HTTP oracle comparison and
the two public header-capacity support contracts. Its sole failed check was
`fault_markers_absent`: two `coverage-injected ` service-error literals remained
in the async state machine despite inactive test branches. The normal library
had no registered native fault points, control-file marker, deliberate panic
helper marker, LLVM coverage instrumentation, or fault CLI option; an armed
fault file was ignored. Passing behavior did not waive the failed exclusion
check.

The corrected source puts all four connection-fault branches and their flags,
cancellation clone, one-shot channel, and abort observer behind
`cfg(coverage)`. It constructs the connection future separately; the normal
future only awaits the real connection driver. No audit markers or checks were
relaxed.

The fresh normal-build audit at
`build/asgi-coverage/normal-build-result-state-audit-2026-10-05/receipt.json`
passed every check. All three selected live cases pass with zero failures,
infrastructure errors, or cases not run. All registered fault-point, common
fault-diagnostic, control, and LLVM instrumentation markers are absent;
the deliberate panic helper is excluded. The armed startup fault is ignored
and its file remains unchanged. This is a selected normal-build proof, not a
full normal-build matrix.

That corrected source SHA-256 is
`187ebfb2311bc793b2f1d3d98c5dc9f3f9cdc5e50805e3f4210e1179769984f8`;
the normal native SHA-256 is
`ba5a6f65508a0d2271a52df9893d9f27f94985144c8a5868e0c10ccdaec9ad89`.
The completed instrumented gate is recorded under
`build/asgi-coverage/unified-production-exclusion-447-2026-10-05/`.
That full report and unfiltered MCP receipt pass. Profiles from the
preceding source/build were not merged into the new report.

## Historical full verification (447 cases; before normal-build exclusion correction)

The preceding source/build report is
`build/asgi-coverage/unified-fallible-headers-447-2026-10-05/coverage-report.json`.
Its status is `complete`, coverage gate is `passed`, and every attribution and
repeat receipt passes without a retry. Unfiltered
`coverage-mcp-regions.json` records `source: matches_receipt`, `tests: passed`,
and zero gap groups.

| Verification | Passed | Failures / infrastructure / retries / not run |
|---|---:|---|
| Per-case attribution | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 1 | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 2 | 447/447 | 0 / 0 / 0 / 0 |
| Full repeat 3 | 447/447 | 0 / 0 / 0 / 0 |
| Native regions | 4,732/4,732 | 0 missing |
| Native lines | 3,332/3,332 | 0 missing |

The measured Rust source SHA-256 is
`954a8b652727db78863b5b5a275a0e15ac3a6c9853c14859866291369b9f6290`;
the instrumented native SHA-256 is
`51495a5a3f540eca1e1085551e2e8968a3ae5fa0fb81610ce966d453965983bc`.
The complete source/input fingerprint is
`6ab42bbc364fd8d238e2995414689cee1008ebd21a9a7745ea47fef9ef6b7d87`.
The exact source and native are preserved under
`artifacts/5d82bd2cfaec435cb37d7ce39f01bcd1/` in the report directory.
The listener-admission, protocol-detection cancellation, and header-capacity
before/after audits retain their original receipts and identities. Profiles
from the interrupted older source were not merged into this measurement.

The runner validates every panic-hook event's source, message, and exact count
independently of process exit status. A deliberate coverage-only unwind cannot
excuse another unexpected panic. There is no production panic allow list.

## Historical targeted verification (9 cases; fallible header assembly)

The report at
`build/asgi-coverage/fallible-header-capacity-targeted-447-2026-10-05/coverage-report.json`
records 9/9 passing attribution cases: three ordinary oracle comparisons and
six target-only contracts, with zero failures, infrastructure failures, or
transient retries. Both public header-capacity contracts pass. The HTTP
fixture receives the capacity error, returns its small 500 response, and a
healthy follow-up returns 200. WebSocket acceptance returns a 500 handshake,
application cleanup completes, and a healthy follow-up returns 200.

The before/after artifact audit at
`build/asgi-coverage/header-capacity-before-after-audit-2026-10-05.json`
verifies matching runner, fixture, manifest, all 70 indexed input digests,
environment, and Cargo lock. Before the correction, the two same-input
contracts failed their public outcomes and produced two independently rejected
panic hooks from `http-1.5.0/src/header/map.rs:1433`. Both target processes
exited zero; the strict panic validator still failed the run. The preserved
`cli-selection-rejected.log` is a separate rejected invocation with no case
execution; the actual before-fix receipt records the valid `--fault-contracts`
command.

This subset covered 2,909/4,732 regions and 1,970/3,332 lines. Its focused
Coverage-MCP receipt matches the source and reports tests passed: the HTTP
header function has zero gap groups, while WebSocket construction retains one
gap at the inner header-value parsing `?`. The outer capacity error is covered;
the same-source full matrix subsequently exercised the remaining validation
path. This targeted receipt alone does not report zero gaps for the complete
source.

The measured Rust source SHA-256 is
`954a8b652727db78863b5b5a275a0e15ac3a6c9853c14859866291369b9f6290`;
the instrumented native SHA-256 is
`51495a5a3f540eca1e1085551e2e8968a3ae5fa0fb81610ce966d453965983bc`.
The completed fresh full verification is recorded under
`build/asgi-coverage/unified-fallible-headers-447-2026-10-05/`.
The targeted report has no three complete matrix repeats and its coverage gate
is incomplete. The separate historical full report above passes its
instrumented gate, but its normal-build exclusion audit failed. The corrected
source passed its normal audit and the separate historical 447-case full gate.

## Historical targeted verification (7 cases; before header-capacity correction)

The report at
`build/asgi-coverage/typed-detection-cancellation-targeted-445-2026-10-05/coverage-report.json`
records 7/7 passing attribution cases with zero mismatches, infrastructure
failures, or transient retries. The strengthened plaintext/TLS drain pair now
matches live Uvicorn: admission closes before response release, the idle
connection carrying a partial preface closes, the complete active response arrives, and the
application/lifespan events and established-connection close match.

The before/after artifact audit at
`build/asgi-coverage/protocol-detection-before-after-audit-2026-10-05.json`
verified the same runner, fixture, manifest, indexed input digests, environment,
and Cargo lock for both pairs. The old native produced two strict diagnostic
adapter failures; the changed native passed both ordinary live comparisons.
The old failures have no projected oracle/target observations and must not be
reported as behavioral mismatches.

This subset covered 2,874/4,726 regions and 1,958/3,335 lines. The focused
`focused-coverage-mcp.json` receipt matches its source and reports tests passed.
The new graceful-cancellation error handling has no uncovered regions; the
filtered connection functions still have two gap groups in the plaintext
WebSocket branch and TLS ordinary result-select branch. Other full-matrix
inputs must cover those paths. This is not zero gaps for the whole source.

The measured Rust source SHA-256 is
`ee392d7b75b19b00022cde6c69c638cade4e75d78f6225d7c772133207e8da3f`;
the instrumented native SHA-256 is
`7a3267cb17f7eb7af9775ab4430ee8926af020c29b44f9fe4a7e8f03c69dff32`.
The follow-up full run under
`build/asgi-coverage/unified-typed-result-policy-445-2026-10-05/`
was interrupted after 219 passing attribution cases, before case 220.
`interrupted.json` records the SIGINT and incomplete gate; the completed
per-case receipts, profiles, and exact source/native identities are preserved.
There is no complete unified report or three passing full repeats for that
run. Its profiles must not be combined with a changed source/build. Header-map
capacity handling changed the required source scope, so this targeted snapshot
is historical. The later 447-case report above passes its instrumented gate;
the historical normal-build exclusion correction passed its own full gate.

## Public header capacity contracts

The pinned `http` crate gives `HeaderMap` finite compiled capacity. Its
infallible `append` calls `expect` internally when capacity is exceeded. A valid
ASGI application can supply enough distinct response or WebSocket acceptance
headers to reach that path even though project code contains no panic macro.
The implemented correction uses `try_append` and preserves its `MaxSizeReached`
error through `Result` before response commitment or handshake task transfer.

The two declared target-only cases supply 32,769 distinct valid headers through the
ordinary ASGI boundary. They declare the server's capacity/error contract in
the existing target-only result envelope; they do not activate native fault
controls and are not Uvicorn parity. The internal bucket ceiling is not a
stable public maximum accepted-header count: distinct names, duplicate values,
reserved handshake headers, and map growth affect capacity differently. The
support matrix documents finite capacity without promising a universal numeric
threshold. No regions may be excluded to hide this reachable failure.

The cases are `support.http1.response-header-capacity-error-recovers` and
`support.websocket.accept-header-capacity-error-recovers`. Their harness-only
selectors are `public.http-response-header-capacity` and
`public.websocket-accept-header-capacity`; neither is written to a native
injection control. The HTTP contract requires the original capacity error to
be handled with a small HTTP 500 and a healthy follow-up. The WebSocket contract
requires the native capacity error, rejected handshake, application cleanup,
and healthy follow-up. Both passed the preceding 447-case full attribution and
all three complete repeats. Both also pass current attribution, all three
complete repeats, and the selected normal-build audit.

<a id="latest-incomplete-snapshot-445-cases-before-protocol-detection-cancellation-correction"></a>

## Historical incomplete snapshot (445 cases; before protocol-detection cancellation correction)

The report at
`build/asgi-coverage/unified-listener-result-policy-445-2026-10-05/coverage-report.json`
records **4,719/4,719 LLVM regions and 3,329/3,329 lines (100%)**. All 445
attribution cases passed. The first two full repeats passed 445/445 with zero
mismatches or infrastructure failures. The third repeat recorded 436 passes,
one infrastructure failure, and eight cases not run; it had zero reported
behavioral mismatches. The unified gate is **incomplete**. Coverage-MCP reports
zero gap groups and `source: matches_receipt`, but **`tests: failed`**.

The failing plaintext graceful-drain adapter had already checked the complete
response body, application completion, and clean established-connection close.
It then rejected the global diagnostic
`uvicorn-rs: connection task failed during shutdown: Cancelled`.
The pinned Hyper auto-protocol detector returns a direct interrupted I/O error
when graceful shutdown cancels its pending version read. The log did not
identify which connection produced that error. The implementation now
classifies only that cancellation path, preserves errors from established HTTP
connections, and retains the global stream-error check.

The measured Rust source SHA-256 is
`b59346e69a3067e01117a6e70a73639a617242604a59752ad38fe478e51d3fff`;
the native SHA-256 is
`5bcc56eeb1cd416dead30fbeb95109aae9d03abc645c872f61301014b85cf085`.
Copies are preserved at `artifacts/6d1a182f398e418e86445281724a872b/src/lib.rs`
and `artifacts/6d1a182f398e418e86445281724a872b/instrumented-native.abi3.so`
under that report's directory, beside the matching MCP receipt.

The existing plaintext/TLS graceful-drain cases now open an idle transport
before the active stream and send the real partial HTTP/2 preface `PRI `.
They retain it until shutdown and require `idle_connection_closed: true`,
alongside admission closure and complete active-response drain. This changes
the input and observation contract without adding cases, files, operations,
fixtures, or a test kind.

The unchanged old native deterministically reproduced the strict diagnostic
rejection for both strengthened cases. The defending receipt is
`build/asgi-coverage/protocol-detection-before-fix-2026-10-05/parity-result.json`;
it records two adapter infrastructure failures, zero reported behavioral
mismatches, and no cases not run. Its adjacent `before-identity.json` retains
the old source/native and new stimulus/harness identities. The implemented
native correction handles only the direct interrupted I/O result after explicit
graceful cancellation; other error results still propagate. The global
stream-error check is retained. Its historical targeted verification is
recorded above; the later historical 447-case full regression gate also passes.

## Preceding incomplete snapshot (444 cases; before listener ownership fix)

The report at
`build/asgi-coverage/unified-result-state-444-2026-10-05/coverage-report.json`
records **4,717/4,717 LLVM regions and 3,328/3,328 lines (100%)**, with no
source-region or line gaps. Its attached Coverage-MCP receipt reports zero gap
groups and `source: matches_receipt`, but **`tests: failed`**. The unified gate
is **incomplete**, not passed.

Per-case attribution recorded 443 passes and one infrastructure failure:
`websocket-tls.text-round-trip-with-query-and-subprotocol` timed out waiting
for the live Uvicorn TLS WebSocket handshake. This was not a Rust behavioral
mismatch, but it prevents complete passing case attribution. Each of three
full repeats separately passed all 444 cases with zero mismatches,
infrastructure failures, or transient retries. Those repetitions do not erase
the failed attribution receipt.

The measured Rust source SHA-256 is
`83cb79f57cbe864c579c0b5350d9a5f640f445e9e539aa550eadf38b52c2a636`;
the native SHA-256 is
`944ddb456ca497e54ffde1c03b053fadc8245fc6c0212361b631e5430cc7f46a`.
The report references preserved copies through `artifacts.measured_rust_source`
and `artifacts.instrumented_native_extension`; its adjacent
`coverage-mcp-regions.json` retains the matching failed-test receipt.

The strengthened plaintext and TLS graceful-drain workflows subsequently
exposed a real listener ownership defect on that same native binary. Both
live comparisons failed only `listener_closed_before_release`: Uvicorn closed
admission while Rust kept its listener open until shutdown finished. The
response bytes, application events, established-connection close, and process
termination matched. The two-case defending receipt, with zero infrastructure
failures, is
`build/asgi-coverage/listener-admission-before-fix-2026-10-05/parity-result.json`.
The current source explicitly drops the listener before task drains. The
strengthened cases passed the preceding 447-case full gate.

## Historical targeted listener verification (7 cases; before protocol-detection correction)

The selected-subset report at
`build/asgi-coverage/listener-ownership-targeted-445-rst-aware-2026-10-05/coverage-report.json`
records 7/7 passing attribution cases with zero mismatches, infrastructure
failures, or transient retries. These include the strengthened plaintext/TLS
graceful-drain pair, both transport write-error shutdown cases, the TLS
WebSocket case, peer reset before the body worker's first poll, and eager
lifespan cancellation-suppressed cleanup. The listener probe retries connect
timeouts and resets; only connection refusal proves admission closure.

This subset covered 2,866/4,719 regions and 1,951/3,329 lines. It has no full
matrix repeats and cannot close the coverage gate. The later full 445-case
snapshot is recorded above; it was incomplete and does not certify the new
idle-connection stimulus or cancellation correction.

## Preceding measured snapshot (442 cases; before lifespan guard consolidation)

All 442 cases passed per-case attribution and each of three complete matrix
repeats, with zero behavioral mismatches, infrastructure failures, or transient
retries. That snapshot contained 211 oracle-parity cases and 231 target-only
fault contracts. It recorded **4,707/4,713 LLVM regions (99.87%; six missing)**
and **3,326/3,330 lines (99.88%; four missing)**. The 100% coverage goal was
unmet.

The report is
`build/asgi-coverage/unified-result-policy-442-2026-10-05/coverage-report.json`.
Its source context is `coverage-report.json.context.json`; the adjacent
`coverage-mcp-regions.json` records six gap groups with
`source: matches_receipt` and `tests: passed`. The report retains the measured source
and instrumented native binary under its artifact directory, referenced by
`artifacts.measured_rust_source` and `artifacts.instrumented_native_extension`.
The source SHA-256 is
`fac53c219c6176cd7bf7fc1895bf6beee1dccc0a3642c8fa87d953429560f512`;
the native SHA-256 is
`c9632eeaf028e083101d02b9c8c8a92ff28fa580ddd4ab8815e50dc1a97c3162`.

Subsequent lifespan guard consolidation and new fault cases changed the source
and inputs. The later 444-case result is recorded above. The matching MCP
receipt for the 442-case snapshot does not certify those later changes or a
release build.

## Historical targeted attribution (58 cases; timed body-worker pause)

The selected-subset report at
`build/asgi-coverage/result-state-targeted-444-2026-10-05/coverage-report.json`
recorded 58/58 passing attribution cases: 10 oracle-parity cases and 48 fault
contracts, with zero behavioral or infrastructure failures. Its LLVM export
recorded 3,742/4,717 regions and 2,590/3,328 lines for that selected subset.
`PythonTaskStarter::__call__` and its emitted closures had no zero-count
regions in the export. The body pump's initial known-close return remained
uncovered: the timed coverage-only pause did not resume before the process
exited. Passing the behavioral case did not prove that region was reached.

The snapshot source SHA-256 is
`d5bc22a97dc190706ca69b2e49d018d99a08fd439c6bcddb1b0c5d239797e885`;
the native SHA-256 is
`201e62824256b618a00dc6d80451913ade6224a688fd96d1ff9c485eb8b169f2`.
The source and binary are preserved in
`artifacts/3924fe25c69e4728b389315008c2bf93/src/lib.rs` and
`artifacts/3924fe25c69e4728b389315008c2bf93/instrumented-native.abi3.so`
under that report's directory.

The current instrumented pause awaits the real connection-close watch before
resuming the normal body-worker path. This selects a causal scheduling boundary
for the existing peer-reset workflow. The later 444-case snapshot measured the
full source union but failed its complete attribution gate. This targeted
snapshot is neither a full matrix gate nor evidence for the later 445-case
source/build.

## Preceding incomplete evidence (426 cases)

The report at
`build/asgi-coverage/unified-panic-policy-426-2026-10-05/coverage-report.json`
recorded 4,378/4,383 LLVM regions (99.89%; five missing) and 3,071/3,072 lines
(99.97%; one missing). Its index contained 208 oracle-parity cases and 218
target-only fault contracts. Per-case attribution recorded 425 passes and one
infrastructure failure. Each of three full repeats recorded 426 behavioral
passes, zero mismatches, and one infrastructure failure.

That run did not pass the complete gate. The infrastructure failure came from
shutdown cancellation of an unused reference process; the current runner
repairs that path. The later 442-case snapshot passed the live matrix but still
missed its coverage goal. This predecessor report does not establish current
100% coverage.

## Historical full evidence (423 cases; before panic policy refactor)

The measured default native Rust build reached **100% LLVM region and line
coverage** on 2026-10-05. Its indexed matrix contained 423 workflows across
67 input files:
208 live oracle-parity cases and 215 target-only fault contracts. All 423 passed
per-case attribution and each of three complete matrix repeats, with zero
mismatches, infrastructure failures, or transient retries.

| Measure | Result |
|---|---:|
| Rust LLVM regions in `src/lib.rs` | **4,356/4,356 (100%); 0 missing** |
| Rust LLVM lines in `src/lib.rs` | **3,060/3,060 (100%); 0 missing** |
| Live oracle parity | 208/208 passed in each repeat |
| Target-only fault contracts | 215/215 passed in each repeat |
| Complete matrix repeats | 3 × 423/423 passed |
| Case-to-region attribution | Complete; matches the aggregate profile union |
| Coverage-MCP | 0 gap groups; source matches receipt; tests passed |
| Normal-build fault controls | Absent; armed file ignored in a live HTTP parity case |
| LLVM branch detail | Unavailable in this export |

The authoritative report for that snapshot is
`build/asgi-coverage/unified-423-final-2026-10-05/coverage-report.json`.
It contains the complete `hit_by` relation, case observations, raw-profile
references, three full-run receipts, attached Coverage-MCP verification, and
a reference to the normal-build audit. The MCP page array and source receipt
are beside that report. Earlier reports retain their own source/build identity
and must not be merged into another source/build's coverage denominator.

The exact instrumented binary is retained under the report's artifact
directory and referenced by `artifacts.instrumented_native_extension`. The
workspace extension was restored to the audited normal release build after
that measurement. Its audit does not establish normal-build exclusion after
subsequent source changes. Rebuild with `scripts/build_coverage_extension.py`
before another coverage run; use the normal build for deployment and
performance measurements.

That run measured the default native configuration with coverage-only fault seams.
Optional `runtime-diagnostics` code, dependencies, and Python integration code
are outside this Rust denominator. No project Rust source files or regions
were excluded to raise the percentage. This is macOS ARM64, CPython 3.12.13,
Rust 1.98.1, and cargo-llvm-cov 0.8.7 working-tree evidence; other platforms and
configurations need their own measurements. That snapshot passed Clippy for all
features in both normal and coverage-only configurations, and for the HTTP/3
probe; the current stricter error policy requires new checks.

The instrumented native SHA-256 is `b8578e09f0e93771187a6c3d51b26d3177bfcdeb841515d08a0672419267880e`.
The Rust source SHA-256 is `127d2535873062d40b9d6e075c83841f51e84a03623ace72330fd43d2e27cc8a`;
the source/input digest is `a29c09f5fe368169924d4e967441ed47b1c612b426fe04067491a3c6074c2f35`. Build ID:
`27e6029f9a5a173d2670fa40f39b8ae82f2887c83c064b08eb36214b94eda275`. The checkout was dirty at
revision `cf9bf062133721b094e914f49ed8f54c613eb30f`; this is not a clean release baseline.

## Previous full evidence (346 cases; superseded)

The recorded input index contained 346 workflows across 62 input files: 195
oracle-parity cases and 151 target-only fault contracts. That complete
run attributed every case and passed all 346 cases in each of three full-matrix
repetitions, with zero mismatches, infrastructure failures, or transient
retries. The report is
`build/asgi-coverage/unified-current-2026-10-05/coverage-report.json`.

The unified LLVM report records 3,826/3,943 regions (117 missing; 97.03%) and
2,665/2,726 lines (61 missing; 97.76%) in `src/lib.rs`. Attribution matches the
aggregate profile union. Coverage-MCP inspected all 48 uncovered-region
function groups across four pages; its source receipt matches and test status
is passing. The compact parsed-equal report, paginated MCP receipt, origin
record, and attached source receipt are under
`build/asgi-coverage/unified-current-2026-10-05/mcp-ingest/`. The 100% region
and line goals were unmet in that snapshot. The historical 423-case measurement
above supersedes it; coverage does not establish that untested behavior is
unreachable.

The run used CPython 3.12.13, Rust 1.98.1, cargo-llvm-cov 0.8.7, and macOS
15.7.7 on ARM64. The instrumented extension SHA-256 is
7adf876e31b5cae650941a4f59e5fc0ffccc50aa032a0001d1dfefeb43aef47c; the
`src/lib.rs` SHA-256 is
d2f17eae846d4dbb99f4d6202b9b11caad1c20a2ce031ef57110e27fcddca140 (build ID
c168a96efb4d78ca380161ca57b31bcf01e9a8eb42a9bb162ca4b7ac2f71296d). The
checkout was dirty at revision cf9bf062133721b094e914f49ed8f54c613eb30f;
this is a working-tree measurement, not a clean committed release baseline.

## Previous full evidence (336 cases; superseded)

The 2026-10-04 report at
`build/asgi-coverage/unified-336-empty-h2-2026-10-04/coverage-report.json`
passed 336 cases in each of three matrix repeats and measured 3,801/3,937
regions and 2,642/2,712 lines. The later 346-case report above supersedes its
matrix and coverage totals. The earlier report and its Coverage-MCP receipts
remain available under
`build/asgi-coverage/unified-336-empty-h2-2026-10-04/mcp-ingest/`.

## Previous full unified baseline (329 cases; superseded)

The unified runner executes manifest-backed inputs against the live reference
server and `uvicorn-rs`. Target-only injected fault-contract cases are labeled
separately. Both passing case classes contribute to one LLVM source-region
union and one case-to-region attribution map.

The historical complete measurement finished at 2026-10-04T13:03:46Z. All 329
cases passed in each of three complete matrix runs, with zero oracle mismatches,
infrastructure failures, or transient infrastructure retries. Case
attribution is complete for all 329 inputs, and the per-case profile union
matches the aggregate. The runner output is
`build/asgi-coverage/unified-lifespan-retained-callables-2026-10-04/coverage-report.json`.

| Measure | Result | Evidence |
|---|---:|---|
| Complete matrix | 329/329 passed in each of three runs | Unified runner report |
| Oracle-backed parity | 183/183 passed in each run | Pinned Uvicorn and Hypercorn configurations |
| Fault contracts | 146/146 passed in each run | Target-only injected-failure checks; not oracle parity |
| LLVM regions in `src/lib.rs` | 3,697 / 3,853 (95.95%); 156 missing | Unified report |
| LLVM lines in `src/lib.rs` | 2,574 / 2,651 (97.10%); 77 missing | Unified report |
| Case-to-region attribution | Complete; per-case profile union matches attribution | Unified report |
| Coverage-MCP | 49 groups; 3,697/3,853 regions; source matches receipt; tests passed | Compact derived report and four-page receipt |
| LLVM branch detail | Unavailable | Exported report contains region and line detail only |

The measured case distribution is:

| Area | Cases |
|---|---:|
| HTTP/1.1, including TLS | 146 |
| HTTP/2 | 18 |
| HTTP/3 | 24 |
| WebSocket, including TLS | 82 |
| Lifespan and server API | 43 |
| Server startup and configuration | 16 |
| **Total** | **329** |

The Coverage-MCP input is the compact derived report at
`build/asgi-coverage/unified-lifespan-retained-callables-2026-10-04/mcp-ingest/coverage-report.compact.json`.
Its parsed JSON matched the runner report before Coverage-MCP pages were
attached. The receipt records the original report SHA-256
`0f2781fd39eebeb4ce6be8aa1a6dc6f184dae796167d0b83c5c252eeb1763e89` and the
derived report SHA-256
`5e4629da8311d47a67e9b86e1f892c766be69a12bbb4a54470d5f00d167e6f78`.
All page objects are retained in
`build/asgi-coverage/unified-lifespan-retained-callables-2026-10-04/mcp-ingest/coverage-mcp-pages.json`.

The run used CPython 3.12.13, Rust 1.98.1, `cargo-llvm-cov` 0.8.7, and macOS
15.7.7 on ARM64. The instrumented extension SHA-256 is
`cc451a45c12bf98da7b4ffcccd7a64182fb1bf9fb6335e5a6a4854a4d8a0139b`; the
`src/lib.rs` SHA-256 is
`9f2fc5513e93ce9acba8bc504c3f61a68b7acab5da613d22d6a7d954c9b984a3`. The run
source/input digest is
`4eac10ffaf879ed17f33043dbca96e35dc9ffb89c841be8414c2ad478281c73c`; build ID
is `4f30e39076a8204529ae60cbe773540bd2fbbd91f7d94e2aafa5b6e8110f66c0`. The
checkout was dirty at revision `cf9bf062133721b094e914f49ed8f54c613eb30f`, so
this is a reproducible working-tree measurement, not a clean committed release
baseline.

## What the historical result proves

The 423-case report covers all cases in its index and reaches every compiled
source region and line in its declared default native configuration. Its
Coverage-MCP receipt has zero gap groups, and all three full repeats pass.
All these reports remain historical evidence; their source/build receipts do
not support current regression claims. The [coverage completion plan](coverage-plan.md)
records the case families, attribution contract, and historical gap inventories.
Future changes must repeat the complete gate on their own source/build.

The matrix is a declared compatibility slice, not full Uvicorn or ASGI
conformance. Its support boundary is documented in [the support matrix](support-matrix.md).
Oracle-parity and target-only fault-contract results remain distinct even
though both passing modes contribute to the single source-coverage union.
Synthetic failures verify the named error path; they do not prove that the
corresponding operating-system or CPython failure occurs naturally.

No separate Rust or Python unit-test suite was run for this measurement. It is
not a performance benchmark and does not establish a throughput or latency
advantage over Uvicorn.

## Reproduce the complete measurement

Run the unified workflow:

```sh
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --output build/asgi-coverage/unified/coverage-report.json \
  --artifacts-dir build/asgi-coverage/unified/artifacts
```

The runner builds the LLVM-instrumented extension, runs every manifest case in
an isolated target process for case-to-region attribution, then runs the
complete matrix three times. It verifies source/build identity and that the
per-case profile union matches the aggregate coverage profile. Raw profiles,
case results, logs, and matrix receipts are retained under the artifacts
directory.

The measured configuration is the default native build with `cfg(coverage)`
enabled for this crate. Optional `runtime-diagnostics` code is not compiled
into this measurement. Dependencies and the Python integration layer are not
part of the Rust region denominator. No Rust source files or source regions
are excluded to increase coverage. Clippy separately checks all Cargo features.

Coverage-only scheduling controls yield through the real task and channel
paths. The EOF recheck case suspends after waker registration and resumes when
the real HTTP/2 request finishes. It does not block a Tokio worker. The runner
clears event logs when restarting a profile, so startup and held-request
checkpoints cannot be satisfied by an earlier process.

The report is LLVM JSON with one `uvicorn_rs_unified` extension. In that
extension, `matrix.case_results` contains the result, verification mode,
requirement mapping, observations, and profile receipt for each selected case.
`coverage.regions` contains every measured source region and its complete
`hit_by` list of case IDs. To find what a case triggered, filter those region
rows for its ID. To find what triggered a region, read its `hit_by` list. An
empty list identifies an uncovered region. Both queries use the same report.

The runner verifies the inverse case-to-region mapping against the aggregate
profile union in memory. It stores that relation once, in the region rows,
instead of duplicating every region hash in every case row. The report retains
all observations and attribution while fitting Coverage-MCP's ingestion size
limit. `coverage.attribution.case_region_lookup` records this lookup path.

For Coverage-MCP, query `coverage_gaps` against the exact report for both
`metric: "regions"` and `metric: "lines"`, with `limit: 15`, following
`next_offset` until each metric is complete. Save each page together with the
exact request used to obtain it. The receipt array uses this shape:

```json
{
  "request": {
    "measurement": "build/asgi-coverage/unified/coverage-report.json",
    "metric": "regions",
    "offset": 0,
    "limit": 15,
    "query": null,
    "line": null
  },
  "response": {"context": {}, "data": {}, "page": null}
}
```

For the next page, set `request.offset` to the prior response's
`data.next_offset`. Preserve every wrapped page in one JSON array. The
attachment script and strict checker verify that each chain starts at offset
zero, continues at exactly the returned offset with a stable limit and no
filters, has no duplicate groups or repeated terminal pages, and ends at
`next_offset: null`. Current reports omit redundant inverse attribution arrays
and can be queried directly. Run `scripts/attach_coverage_mcp.py` against the
report and saved page array. Require matching totals for both metrics, zero
groups, `source: matches_receipt`, `tests: passed`, and complete pagination
before strict validation:

```sh
uv run --python 3.12 --locked --group benchmark python scripts/check_ci_evidence.py coverage \
  build/asgi-coverage/unified/coverage-report.json
```

CI uses `--allow-pending-mcp` only to validate the raw report while the MCP
query is pending; it does not satisfy the strict acceptance gate.

## Measure an incremental case

Add an input-only case to the indexed manifest, validate it with the parity
contract loader, and run only that case against the existing instrumented
source/build:

```sh
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --output build/asgi-coverage/incremental/coverage-report.json \
  --artifacts-dir build/asgi-coverage/incremental/artifacts \
  --case-id CASE_ID --matrix-repeats 0
```

Then call Coverage-MCP `coverage_compare` with the fixed full report as
`baseline`, the selected report as `measurement`, and `scope: "incremental"`.
Keep the source and instrumented build receipts identical. This reports the
case's marginal region gain and union against the baseline; it does not certify
the whole matrix or establish regression status. If line detail is
incomparable, record that result instead of deriving a combined line total.

## Release preparation verification

The October 5 release preparation reran the complete 451-case attribution and
three complete matrix repeats using result schema `@4`, the updated portable
coverage builder and Rust 1.85 package metadata. All passed with zero failures,
infrastructure retries or cases not run. Native totals remain 4,778/4,778
regions and 3,371/3,371 lines. Coverage-MCP reports zero groups, source
`matches_receipt` and tests `passed`.

The native source is unchanged (`c7bd494d…`). This run has its own source/input
fingerprint and instrumented binary (`c319ee0a…`); profiles were not combined
with prior measurements. The actual installed macOS wheel (`76672335…`)
separately passes 214 public comparisons and all 16 normal-exclusion gates with
three selected live cases. These are dirty-checkout preparation receipts, not
evidence of successful hosted CI on a release commit. The release preparation
archive (`benchmarks/results/release-preparation-2026-10-05/README.md`) retains
tracked release receipts and source snapshots. Generated coverage reports,
per-case logs and profiles remain local-only.
