# HTTP/3 GREASE interoperability replay

The unchanged 128-request POST sequence and the public peer-close case ran
against stock Hypercorn and the current instrumented Rust server. Both arms
used the same server/native/client identities. The declared `h3_grease` value
was the only input difference; no request, deadline or reference source changed.

| Arm | Passed | Infrastructure failures | Not run |
| --- | ---: | ---: | ---: |
| GREASE enabled | 0 | 1: first Hypercorn response headers deadline | 1 |
| GREASE disabled | 2 | 0 | 0 |

The disabled arm returned 128 identical successful responses on each server,
then passed the peer-close case with clean exits and no server errors. The
maintained public sequence keeps that declared disabled setting. The enabled
failure and the earlier sandbox bind failure remain preserved.

`ab-receipt.json` links the exact inputs, normal Rust client build, server/native
identities, raw results and logs. `parser-evidence.json` records source inspection
of the pinned libraries. This supports a GREASE-dependent receive-end failure;
it is not packet capture or direct reference parser instrumentation. The
native server remained instrumented throughout: this is selected correctness
and interoperability evidence, not normal-binary parity or a speed benchmark.
