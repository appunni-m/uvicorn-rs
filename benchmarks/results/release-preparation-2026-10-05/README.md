# Local release preparation — October 5, 2026

These are dirty-checkout preparation receipts for uvicorn-rs 0.1.0, not a
published package or successful hosted release commit. The final normal macOS
wheel has native SHA-256 `766723356793322de55931eac30cad3af2c468de4cf1e8d53b275f0a3a839f45`.
All 214 public oracle comparisons and all 16 normal-exclusion gates pass; the
three selected exclusion workflows also pass. Actual installed-wheel consumer
checks pass on CPython 3.12.13 and 3.9.25. The extracted source distribution
builds with locked dependencies and is checked in a fresh environment.

The independent instrumented binary is
`c319ee0a3d4cbdcf06be2d7fa51a291713aa41b597fd00ac9922ab9d69889390`.
Its 451 individual attribution cases and three complete 451-case repeats pass
with zero failures, infrastructure retries or cases not run. Native coverage is
4,778/4,778 regions and 3,371/3,371 lines. Coverage-MCP reports zero groups,
`matches_receipt`, and tests `passed`. This is default-feature `src/lib.rs` on
macOS ARM64; Python, dependencies, optional diagnostics, other platforms and
full official ASGI conformance are outside its denominator.

Reports, consumer receipts, validation outputs and tool logs are retained here.
Large JSON and source snapshots are compressed without changing their contents.
The coverage artifact tarball retains all per-case results, logs, raw target
profiles, merged profiles and complete-repeat results beneath `artifacts/`.
The original working paths remain recorded in receipts. Failed build/audit/
reader-validation attempts are retained with their scope; none count as passing
gates. The original development normal extension was restored byte-for-byte.

The project uses `BSD-3-Clause OR MIT`, with Copyright (c) 2026 Appunni M above
both copied license texts and the original Uvicorn/Hypercorn notices retained.
Version agreement, exact Rust 1.85.0 library feature-mode compilation, Clippy,
rustdoc and local Actionlint checks pass. Hosted Linux/macOS/Windows package
jobs, Linux shipping-wheel parity and clean exact-commit candidate assembly
remain pending. No registry publication or GitHub Release is performed.

See [release workflow](../../../docs/releases.md) for the complete candidate
contract. `archive-manifest.json` records exact archived-file digests and, for
gzip files, the original uncompressed digests.
