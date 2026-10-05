# Current normal release-binary validation

Source `c7bd494d…`, saved normal native `0e13bb6d…`, and normal parity client
`1c61…` passed all 214 current live public cases with zero failures,
infrastructure errors or cases not run. The separate three-case exclusion
check passed all 15 checks: 211 registered fault points, fault controls,
coverage instrumentation and authored test-only panic seams are absent.
The armed fault file was ignored by the normal binary.

`normal-gates-receipt.json` binds the successful attempt3 to the full451/three
repeat/zero-gap coverage proof and the exact portable identity captured BEFORE
public parity. Identity equality was checked after parity, exclusion audit
and documentation edits. Native binaries remain at their original local paths.
Sources and audit recipes are losslessly gzipped; executable source inventory
therefore stays unchanged during the following benchmark freeze.

`attempt-1/` preserves a behavior-passing214 run rejected for a client rebuild
after capture. `attempt-2/` preserves a behavior-passing214/three-case exclusion
run rejected because coverage archive source files appeared after capture.
The final attempt recaptured only after the archive source paths settled and
kept empty Cargo wrappers for prebuild/parity/audit. No failure was discarded
or converted to a successful portable gate.

This is a normal-build correctness and instrumentation-exclusion proof, not
a speed measurement, official full ASGI conformance or a clean release baseline.
