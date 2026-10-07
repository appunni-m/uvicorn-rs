# Black-box parity and Rust source coverage

## Current evidence status

The current local 491-case black-box gate passed on 2026-10-07. The manifest
declares 491 workflows across 70 input files and 71 operations: 239 live oracle
comparisons and 252 target-only contracts. Per-case attribution and all three
complete 491-case repeats passed with zero failures, infrastructure errors,
retries, or cases not run. Native coverage is **5,121/5,121 regions and
3,624/3,624 lines (100%)**. Coverage-MCP measured the attached report with
`source: matches_receipt`, `tests: passed`, zero missing regions, and zero gap
groups. A rebuilt normal non-instrumented local build passed all 239 live
oracle comparisons. The current report and its full evidence archive are
linked below.

This is source-bound local macOS ARM64 evidence from a dirty working tree at
revision `dc8cf3f58623b761d7187153d5e96636bbdd77be`, not a clean hosted release
baseline. The measured `src/lib.rs` SHA-256 is
`1a0c90dbdd08e7f6172a1a6d6f6928f021bd473d74836ee7eeb853e1fb4d55a4`; the
instrumented native SHA-256 is
`2fcd0eeb88f38d7c07801335e37416837761fd0d4a340d86aab57ba8638dc2d5`. The
region denominator changed because the coverage-only HTTP receive contention
diagnostic no longer has a second coverage-only conditional outcome. The
diagnostic remains absent from production builds. No Rust unit tests were
added; the manifest-backed live input matrix remains the behavioral evidence
system.

Hosted Linux failures are separate from this local result. The attached run
[#23](https://github.com/appunni-m/uvicorn-rs/actions/runs/37603449348), commit
`6b28666`, used a 490-case snapshot. Its attribution log identifies
`http3.asgi-event-type-string-subclass` as an infrastructure failure; each of
the three complete repeats ended with one infrastructure failure and one case
not run. The report has 237/238 oracle parity cases passing, no behavioral
failures, and 5,106/5,108 regions covered (all 3,612 lines covered). The
independent installed-wheel parity job passed 238/238. The two missing region
locations are not present in the pasted output.

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
attempts were denied with HTTP 403. The current source therefore has full local coverage and full hosted
region/line measurement, but no passing hosted parity/coverage gate.

A separate earlier 238-case server-log excerpt reports one infrastructure
failure and one case not run but does not name the failed case.

## Current full verification (491 cases)

The archive is
[`asgi-coverage-region-fix-491`](../benchmarks/results/2026-10-07/asgi-coverage-region-fix-491/).
It contains the compressed unified LLVM report and matching context receipt,
the exact Coverage-MCP page, three full-matrix repeat results, a normal-build
oracle result, and an evidence index. The report SHA-256 before compression is
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
[`asgi-empty-subprotocol-491`](../benchmarks/results/2026-10-07/asgi-empty-subprotocol-491/).
It remains the evidence for adding the empty WebSocket subprotocol parity case;
its report passed 491-case attribution and three repeats with 5,123/5,123
regions and 3,628/3,628 lines before the coverage-only HTTP receive diagnostic
adjustment. The current archive above is the source/build receipt for the
latest region denominator.

## Superseded full verification (490 cases)

The superseded acceptance archive is
[`famh-concurrent-load-acceptance`](../benchmarks/results/2026-10-07/famh-concurrent-load-acceptance/).
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
[`asgi-inventory-485`](../benchmarks/results/2026-10-07/asgi-inventory-485/).
It contains the compressed full LLVM report and matching context receipt, the
full Coverage-MCP response and structured receipt, all three raw matrix runs
inside a compressed artifact bundle, the normal-wheel parity result, the wheel
consumer result, and the normal-build exclusion audit. The exact report SHA-256
before compression is
`457ae9d02ae1bee0f5f6d7a75315fb162b0b9c14c02bb50e721f2ca9fd64067b`; the
compressed report is
[`coverage-report-isolated.json.gz`](../benchmarks/results/2026-10-07/asgi-inventory-485/coverage-report-isolated.json.gz).
The Coverage-MCP receipt reports matching source/build identity and `tests:
passed`. The case-to-region attribution is verified against the profile union.

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
[`tls-websocket-isolation-diagnostics.json`](../benchmarks/results/2026-10-07/asgi-inventory-485/tls-websocket-isolation-diagnostics.json).

The case inventory is a focused black-box map, not full ASGI conformance. The
known cross-name response-header ordering deviation and unsupported extensions
are listed in the [support matrix](support-matrix.md) and [ASGI case
inventory](asgi-case-inventory.md).

## Historical full verification (473 cases; October 6 source inventory)

The fixed archive at
[`request-body-pump-ownership-coverage-473`](../benchmarks/results/2026-10-06/request-body-pump-ownership-coverage-473/)
retains the lossless compressed unified report, matching context sidecar,
exact Coverage-MCP response, normal-wheel parity result and normal exclusion
audit, with an evidence index and file hashes. The uncompressed report
SHA-256 is `6bc08ebf1be237392e46094d665517179866abb6a40345f7f9530123424697c8`;
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
[`http3-peer-close-coverage-460`](../benchmarks/results/2026-10-06/http3-peer-close-coverage-460/)
retains the lossless compressed unified report, its matching context sidecar,
the exact Coverage MCP response, the normal-wheel parity result, the normal
exclusion receipt and audit bundle, and an evidence index with file hashes.
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
[lossless report](../benchmarks/results/performance-investigation-2026-10-05/http3-task-reaping-coverage/coverage-report.json.gz),
[unfiltered MCP pages](../benchmarks/results/performance-investigation-2026-10-05/http3-task-reaping-coverage/coverage-mcp-pages.json)
and [full proof receipt](../benchmarks/results/performance-investigation-2026-10-05/http3-task-reaping-coverage/full-proof-receipt.json),
alongside attribution/repeat results, logs and source snapshots. Its source/input fingerprint is
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
[normal-gate receipt](../benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/normal-gates-receipt.json),
[public parity result](../benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/public-parity-result.json),
[exclusion audit](../benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/receipt.json)
and [identity captured before public parity](../benchmarks/results/performance-investigation-2026-10-05/current-normal-http3-task-reaping-final/benchmark-identity-before-public-parity.json).
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
[evidence archive](../benchmarks/results/performance-investigation-2026-10-05/current-coverage/archive-manifest.json)
preserves a lossless [full report](../benchmarks/results/performance-investigation-2026-10-05/current-coverage/coverage-report.json.gz),
the [unfiltered MCP receipt](../benchmarks/results/performance-investigation-2026-10-05/current-coverage/coverage-mcp-pages.json),
source/input snapshots, and all three full-repeat receipts and logs. Native
binaries and raw profiles remain at the original local paths recorded there.

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
Its [public parity receipt](../benchmarks/results/performance-investigation-2026-10-05/current-normal/public-parity.json)
records 213/213 passes with zero failures, infrastructure errors or cases not
run. Formatting, Clippy and build logs are preserved beside that receipt.
The independent [normal exclusion audit](../benchmarks/results/performance-investigation-2026-10-05/current-coverage/normal-exclusion/receipt.json)
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
as [incomplete zero-gap evidence](../benchmarks/results/performance-investigation-2026-10-05/current-coverage/previous-generic-helper/evidence-status.json).
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

For Coverage-MCP, query `coverage_gaps` against the exact report with
`metric: "regions"` and `limit: 15`, following `next_offset` until all groups
are returned. Preserve each structured page object in one JSON array. Current
reports omit the redundant inverse attribution arrays and can be queried
directly. Run `scripts/attach_coverage_mcp.py` against that exact report and
saved page array. Require matching region totals,
`source: matches_receipt`, `tests: passed`, and complete pagination before
updating the documented result.

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
evidence of successful hosted CI on a release commit. The [release preparation
archive](../benchmarks/results/release-preparation-2026-10-05/README.md) retains
reports, context, Coverage-MCP receipt, per-case results/logs/profiles and
source snapshots.
