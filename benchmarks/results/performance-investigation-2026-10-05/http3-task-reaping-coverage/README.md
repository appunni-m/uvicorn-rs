# Current HTTP/3 task-reaping coverage proof

Source `c7bd494d…` passed all 451 individual attribution workflows and three
complete 451-case repeats with zero failures, infrastructure errors, retries
or cases not run. The matrix contains 214 live reference comparisons and 237
target-only contracts, across 70 input files and 63 operations. No unit tests
were added or run for this gate.

The fresh instrumented native is `d2323f9a…`. Its unified report records
4,778/4,778 LLVM regions and 3,371/3,371 lines. Unfiltered Coverage MCP reports
zero gaps, `source: matches_receipt`, `tests: passed`, build
`69e1ca57e011f6ab6e9ef1e7cfa6cd9071ea6ac47320f13415a176d47fdb9474`.

The newly structured held-response contract observes the real remote H3
application close code 0x102, cancelled owned request tasks, original accept
error, Python application cleanup and a healthy follow-up response. It alone
covers the former two missing final-drain spans. The `stream_reset` field uses
the probe's existing response-read-error convention; it is not packet capture
of a RESET_STREAM frame.

`coverage-report.json.gz` decompresses to the unchanged post-MCP report.
The unchanged pre-MCP report is retained separately. `attribution-cases.tar.gz`
contains every case's original result and logs; its members were hash-checked
against the originals. All three complete repeat results/logs, frozen inputs,
sources, preparation failures and selected proof receipts are preserved.
Raw LLVM profiles and native binaries stay at their original local paths.

This is default-feature native `src/lib.rs`, with `cfg(coverage)`, on macOS
ARM64 in a dirty working tree. Python/dependency/optional-feature coverage,
other platforms, official full ASGI conformance and performance are outside
this claim. Normal release-binary validation is recorded separately in
`../current-normal-http3-task-reaping-final/` after its own gates pass.
