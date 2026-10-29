# Black-box parity and Rust source coverage

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

<a id="current-unified-coverage-status-2026-10-22"></a>
<a id="current-unified-coverage-status-2026-10-29"></a>

## Current unified coverage status (2026-10-29)

PR #19 remains a draft. CI
[#466](https://github.com/appunni-m/uvicorn-rs/actions/runs/40807137734)
checked committed PR head `51c6e4920644d1a4e6fdd9f9ae9571ec8d2d7e61`, based
on `main` at `86e72e181d00feca1b4db7f30377d5d9d4345b83`. Its three-repeat
matrix attributed all 1,071 cases, but the 100% gate failed at
**13,962/14,134 regions** and **10,290/10,377 lines** (172 regions and 87
lines uncovered). The retained artifact is ID `12870939134`, archive digest
`sha256:592368538dcbff0ba373ca9b3640676b80cc1ca7fc7abc572f8a0682f71b7a89`,
and report SHA-256
`d2f1dc778284e3736b9783fd50e3f19589c0608db04a42ee3c380e81c11597a6`. The
matrix passed its cases; only the coverage threshold failed.

The same run passed 717/717 installed-wheel public parity cases on Linux
x86-64 and macOS ARM64, plus release handoff, native composition, Rust minimum,
and Rust quality. Windows candidate parity stopped before cases because its
oracle dependency check required `uvloop`, which is unavailable there. Linux
and macOS candidate identity recording failed because pinned `maturin` was not
on PATH; Linux clean-consumer checks passed and the macOS wheel passed parity.
The local working tree contains focused fixes for Windows dependency selection
and the pinned-tool lookup; those inputs and runner changes are not covered by
CI #466. A local gap map identifies 6 uncovered regions / 4 lines in
`crates/uvicorn-rs/src/http3.rs` and 166 regions / 83 lines in `src/lib.rs`.
It is diagnostic only because CI used a synthetic merge revision and the local
manifest/runner have changed since that run.

Coverage-MCP could not return an independent review: its local daemon failed
health checks, then timed out again after a restart. No review receipt was
created, and `7t4g` remains blocked. The saved LLVM report can guide targeted
coverage work but does not satisfy independent acceptance.

### Prior completed unified coverage result (CI #464)

The retained `uvicorn-rs-unified-coverage` artifact is ID `12858010668`, with
archive SHA-256
`0dca6fccce5c498361018f34dda30e48c4f1129bc740c32c8b03e30b26ed19e6`; the
report SHA-256 is
`b0d73cc53969317c211b65b955585fc451636024a014a0f0bd386c59cc9052a9`. The
report is a gap-mapping aid, not current full-gate evidence: it was produced on
synthetic merge revision `d3bd3bcf634a0d83ab4b13748100d6848b659d2b`, while
the local branch has three changed non-Rust files. All measured Rust source
hashes match the branch. A compact Coverage-MCP projection grouped the missing
regions into 52 functions, but reported `source=unverified`; independent
acceptance remains open.

CI #466 confirms Linux and macOS public parity, including the earlier TLS
fixture change. The local platform/evidence fixes and this documentation update
are not included in that run and still need hosted confirmation.

The post-change focused receipt is local-only:
`target/coverage-diagnostic/ci461-startup-shutdown-fault-fix/coverage-report.json`,
SHA-256 `d64ac46b5d9f745557372ebad1d3be87234c1af28d7b959fd625cf3c77441b6a`.
It passes the selected fault contract 1/1 with no infrastructure failure and
binds to source SHA-256
`7d460401be3f1225964937ddd8fdeb5985a1a818b929686c013dffb42902cd2d` and
instrumented extension SHA-256
`4c6116ec76fbf353a7b7c2124cfb7a8700bb1dcdb29d6f67920b3b09033c9876`. The
selection contains one fault case and no oracle-parity cases, so its incomplete
coverage totals do not measure the full source gate.

The prior run, CI #456, was superseded when #457 started. Its coverage job was
canceled and its retained artifact is not a completed gate receipt. CI #461
also missed the 100% gate; its current-source focused follow-up covers one case
only and does not replace the full report. CI #462 is a completed historical
failure. CI #463 is historical and does not bind to the latest local commits.
CI #466 is a completed prior-source result. After the related parity/evidence
fixes and targeted coverage inputs are stable, push one coherent batch, then
request one independent Coverage-MCP review bound to the new exact source and
report. An accepted independent review is still outstanding.

### Prior CI #455 coverage result (source 4a429684)

The earlier pull-request run,
[#455](https://github.com/appunni-m/uvicorn-rs/actions/runs/40652026006),
evaluated merge commit `9c935f8ec4b075c783d9fde755c43d8b430a1ac9`, with its
recorded target-source hashes matching PR head
`4a429684d5fd92c1068c7776093452cca1ccfc90`. The unified coverage artifact is
ID `12804865394`, archive SHA-256
`16bab28580018491f7e62ac9290fb36750da79b7d109b085de25cde863622e5d`; the
extracted report SHA-256 is
`9d3a169a132a88e57298368f3c572b1a0f36217060503b865f2546a152ae654c`. Its
coverage source digest is
`bf1bea77564889116acd1fcee8c8ccc40dc2d4749d04a5496c0422c2d01d80d0`.

The matrix attributed all 1,309 indexed cases. Two of the three ASGI repeats
passed 1,051/1,051; one passed 1,050/1,051 because a coverage-only shutdown
join-error case recorded `lifespan.shutdown` after the message was sent but
before the injected task abort. The aggregate measured **13,801/13,983
regions** and **10,165/10,263 lines**. The `uvicorn-rs-public-parity` job
passed 702/702, but this older source result does not clear current coverage.

An earlier local draft corrected the fault-specific shutdown predicate and
removed the contradictory generic `application_events` requirement; that
selected case passed 1/1 on that draft. It also corrected
`fault.asgi-event-type.extract`:
the old fixture sent the recognized `http.response.trailers` event, so its
ordinary HTTP 500 could pass without exercising the injected extraction error.
The dedicated fixture route produced the injected `MemoryError`, which the
fault contract verified from the server log. It passed 1/1 and
attributed the previously missing `src/lib.rs:542` fault-point region. Local
run `65a83d09fa124b0da40f5b5c43a22b75` is dirty relative to revision
`4a429684d5fd92c1068c7776093452cca1ccfc90`; its selected report SHA-256 is
`c6e24595eff5555f1e65f8ef2a965f742666ac6437627ed2cb8aa5e0caf2588f`. The
selected report is incomplete by design and is not full-coverage evidence. No
exact-source 100% report or accepted Coverage-MCP receipt is available.
Candidate jobs were skipped after the hosted coverage failure, and release
remains blocked.

Two additional WebSocket input cases send HTTP response-extension event types
through the public WebSocket ASGI `send` callable. The selected pair passed
2/2 against Uvicorn and the target, and covered the previously missing
`AsgiEventType::as_str` regions at `src/lib.rs:2022` and `src/lib.rs:2023`.
Local run `4c10f41d5f0340ac84bbe98fbac257c8` is dirty relative to revision
`4a429684d5fd92c1068c7776093452cca1ccfc90`; its selected report SHA-256 is
`801dc40b7f87f69941d58d41e3fb80fb1a7582c44536d37e000918c92e56ad46`. This
adds focused attribution only; the full hosted 100% gate remains open.

Two HTTP/2 trailer cases now send an invalid trailer name and an invalid
trailer value after response-body completion. Both matched Uvicorn 0.54.0 and
the target; server logs confirm the expected header-name and header-value
errors. The selected report attributes the target validation paths at
`src/lib.rs:3865-3868`. Run
`1472d9e30da84705b6ab3a224e05c813` passed 2/2 with zero case or infrastructure
failures and no retries. Report SHA-256:
`bbe74f5d5ad9e635b1da533ab2aa2e585580dd085eee1a5e0337261049818be0`; source
digest `1c850fe5c4e9f45fc85975198736221190d7dd1add0d6e80ffb281e7cd7ca245`.
The report is selected-subset diagnostic evidence, not a full coverage pass.

### Previous exact-main coverage failure (2026-10-27)

The last exact-main CI run
[39689988928](https://github.com/appunni-m/uvicorn-rs/actions/runs/39689988928)
is bound to clean commit
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. Its unified matrix completed
884/884 selected cases with no case failures or infrastructure retries, but
the required 100% coverage gate failed: **10,962/11,375 source-span regions**
and **8,130/8,438 executable lines**. The remaining gaps are 413 regions and
308 lines. The retained `uvicorn-rs-unified-coverage` artifact is ID
`12390496561` (archive SHA-256
`6bab44ea1c32e91c67f7e71651902d480ff9a3fb58d373568df537eda67158e1`); its
report SHA-256 is
`9d58a1e169b6e751efbe35f4492528fc368d7c31ea02aee2bd35d06c5669a51c`.

### Previous full current-draft coverage attempt (2026-10-27)

This earlier full-inventory report describes the pre-CA-fix source snapshot
below and is not current-source coverage evidence.

One no-repeat diagnostic pass ran on dirty revision
`5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`0f6f08a042d517c083c3ec775efc159cb2d21053084769a2af6f653a640b6066`.
The full inventory selected and executed 1,137 cases (881 ASGI and 256
native); 1,135 passed, with zero behavior failures and two infrastructure
failures. Both failures were TLS WebSocket cases. In each, the oracle process
remained alive after lifespan startup while the handshake response timed out;
the target server reached readiness. Coverage attribution completed for all
selected cases, but the full release gate also requires three complete passes
with every case passing.

The coverage gate remains incomplete at **13,080/13,191 regions** and
**9,729/9,787 lines** (111 regions and 58 lines missing). The report is
`target/asgi-coverage/coverage-current-draft-fresh-20261027.json`, run
`fc7fc82bf56b4f67954e1ea601e77fc3`, report SHA-256
`c88e3cd15585eb787cd75f1957770512d1b1245221104b2f932da66af049974a`; the
instrumented extension SHA-256 is
`ab60493a10f9674a016034805f6cbdec5cee8c9724fbb0c309d43fc3e0bd373d`.
The remaining 111 uncovered regions are in `src/lib.rs` (103) and
`crates/uvicorn-rs/src/websocket.rs` (8); the other measured Rust source files
are complete in this report.

Coverage-MCP fully paginated both metrics for this exact report. It returned
`source=matches_receipt` and `tests=failed`, with 899 region groups and 54 line
groups. The two infrastructure failures prevent an accepted review receipt;
the grouped observations do not change the 111-region and 58-line full-report
totals or pass the zero-gap review.

A focused no-retry recheck of only the two failed TLS WebSocket cases passed
2/2 against Uvicorn 0.54.0 and the Rust target. Its report is
`target/asgi-coverage/coverage-websocket-tls-recheck-20261027.json`, run
`d1b1a60e9e834bbca8a8569b830f4cf9`, report SHA-256
`3f7e5963859e788e38448bc1111b168f8799f8ee90592443202d631602f1eb81`; it uses
the same dirty source and instrumented extension. The timeout did not
reproduce, but this selected subset does not rewrite the full matrix result,
remove the remaining coverage gaps, or establish the three-repeat gate.

A focused follow-up offered `permessage-deflate` on
`websocket.frame-after-close-is-rejected`, routing its raw close-plus-data
frames through the Yawc session. Uvicorn 0.54.0 and the Rust target matched
the 101 handshake, normal 1000 disconnect, and HTTP 200 follow-up. The selected
profile hits the Yawc `ConnectionClosed` handling at
`crates/uvicorn-rs/src/websocket.rs:632` and `:636`; it does not reach the
defensive `Err(error)` or `Ok(_)` arms at lines 637–641. The one-case report
`target/kata-progress/websocket-frame-after-close-yawc-20261027.json` passed
1/1 with complete attribution and no infrastructure failures (run
`00a51921e8dd4317b770fdfbd0f6b153`, report SHA-256
`d87e0c64809785198a0dd39577f44584c140ab42c3b0edec7b6e07fce209ee18`). It
binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`0ea64c2d398c46468fe62d80a9d670e85fb9901107b81753a068da56fb496162`,
WebSocket input SHA-256
`e57035e7a7982bbe1f872522a265b3c92e266a35d01b680f98c4bba9431616a4`, and
instrumented extension SHA-256
`544dfcf37b731fabb0f72c9f37e70d3307b0ed920aa2530cffa145de096e1bee`. This
selected-subset receipt is not a full coverage pass or independent review.

Two coverage-only fault contracts now exercise the remaining Yawc close-flush
outcomes that normal close frames do not reach. They send an explicit client
close, then inject either a Yawc I/O error or an unexpected frame returned
after close. Both contracts passed (2/2), with the 101 handshake, consumed
fault, and HTTP 200 follow-up; there were no case or infrastructure failures.
The selected receipt is
`target/kata-progress/websocket-yawc-close-flush-faults-20261027.json`, run
`b575189e07584284b6d1a32c2ccdcc91`, report SHA-256
`564f3e3543b418d7b204ff7064ea507109847ee6e10c3bbde1238a24b2cc7d78`, source
SHA-256 `993ef4820f55ba7f42c9e2dfab62d2ff59bb441a7c298c61cb58f166e43c7ee4`,
and instrumented extension SHA-256
`ab60493a10f9674a016034805f6cbdec5cee8c9724fbb0c309d43fc3e0bd373d`. The
fault profiles attribute the error arm to
`crates/uvicorn-rs/src/websocket.rs:651` and the unexpected-frame arm to
`:652–655`. These are target-only selected fault contracts; the report remains
an incomplete subset and does not replace a current full-source run or
Coverage-MCP review.

A route-explicit current-source rerun (2026-10-27) sets
`server_options.ws="websockets-sansio"` in both inputs so they exercise the
intended Yawc backend. Both selected fault contracts passed (2/2), with no
case or infrastructure failures. Run `66c230606c0c4310b76609f9082b080e`;
report `target/asgi-coverage/coverage-yawc-close-reply-flush-sansio-20261027.json`,
SHA-256 `47050d27c0906ce5cc5f956e670bb28785cc3f4a7de619d899d4d220811fecfa`.
It binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
digest `bae4968452b9b6fa667d921a6cb1b041c23231d58dfc72e53165ba49dda3d6c1`,
WebSocket input SHA-256
`c31ff3ec38a6eafa9d943c84a6e6f5fc72b5e26ea71ed8d772c75c80c788ced8`, and
instrumented extension SHA-256
`09879b43a4d09cbd51fe287bd6c94c5cf179e15cb49ca2a1a52eb12e010814b2`.
Per-case source-span attribution hits the error helper for the first case and
the unexpected-frame helper for the second. Coverage-MCP confirms this report
matches its source receipt and that its tests passed, but its function-level
query still lists six no-hit helper instances while the report's normalized
source-span attribution marks those helper locations hit. This selected report
does not settle that independent-review discrepancy or the full coverage gate.

### Selected invalid CA certificate follow-up (2026-10-27)

Added the live case `python-api.config-server-rejects-invalid-der-client-ca-file`
with a PEM-wrapped invalid DER certificate. Its first selected run exposed a
parity mismatch: Uvicorn raised `ssl.SSLError` with OpenSSL's `[X509] PEM lib`
message, while the Rust target surfaced a rustls `ValueError`. The target now
routes `RootCertStore::add` failures through the existing CPython SSL error
adapter, preserving the rustls error as fallback if CPython accepts the file.
The focused rerun passed 1/1, including the same public error class and message
as Uvicorn.

The report is
`target/asgi-coverage/coverage-invalid-der-client-ca-after-fix-20261027.json`,
run `ba7e1bb61af74d18888dd0eb12607e56`, report SHA-256
`0735a4ee7c99d51157148c3881f310f4f0f6069ee433239e38a093afb4e67661`; it binds
`src/lib.rs` SHA-256
`356dc7b1553b1586f924408925b8efae13481e4a77e1587122282dc8a782a2df` and
instrumented extension SHA-256
`2016f980ddd2a52a42a65ddd70a7017e43cd7185f61d5b88151f87ee6254bc17`.
Attribution records 263 covered regions for the selected case. The report is
selected-subset evidence; it does not establish full coverage. The earlier
full draft report and WebSocket recheck predate this Rust change, so their
source identities do not describe the current checkout. Refresh the full
matrix and independent Coverage-MCP review after the remaining gaps are fixed.

### Selected HTTP/1.0 concurrency callback follow-up (2026-10-27)

Added `python-api.run-zero-concurrency-rejects-http10-request` to exercise the
Python adapter with a real HTTP/1.0 request and `limit_concurrency=0`. The
case passed 1/1 against Uvicorn and the Rust target with the expected 503; its
coverage profile reaches the HTTP/1.0 formatting arm at `src/lib.rs:5540`.

The report is
`target/asgi-coverage/coverage-python-api-http10-concurrency-20261027.json`,
run `c451b8ccc6f1455e93722b684db1248b`, report SHA-256
`1d48432d5e77d04b98e35a554307aedd9065d17a81f2a3be259cc0e90a23090f`. It binds
`src/lib.rs` SHA-256
`356dc7b1553b1586f924408925b8efae13481e4a77e1587122282dc8a782a2df` and
instrumented extension SHA-256
`67eca10e3c26a5632aad6850aa7cbd896077010a0fa456111cdf3691b179a950`.
Attribution records 2,054 covered regions and 1,610 lines for this selected
case. HTTP/0.9, HTTP/2, HTTP/3, empty-path, and callback-error arms remain
uncovered in the prior full report; this selected report does not refresh the
full matrix or satisfy the independent review.

### Full one-pass current-source diagnostic before UDS fault coverage (2026-10-27)

One full inventory pass ran on dirty revision
`5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`f02bd82bff910047259af535ba700f075c4d365acfc0b60be7084cc0a388af09`. All
1,142 selected cases passed (884 ASGI and 258 native), with no case or
infrastructure failures. This was one pass; the release gate requires three
complete passes.

Coverage was **13,154/13,259 regions** and **9,783/9,836 lines** (105 regions
and 53 lines missing). The report is
`target/asgi-coverage/coverage-current-source-diagnostic-20261027.json`, run
`d003d53fbba04b4eb41ece2c72de9277`, report SHA-256
`dba2de253f6478737f172bfa343a543883d968fb1c1108b2fb1c92dae9a18bb6`, and
instrumented extension SHA-256
`6be84aa8b61337a7c2330497e5d274748d3dec6fe0602d3fb656a7ad66b4d7b2`.
Coverage-MCP matched the report receipt and reported failed tests because of
the remaining gaps. Its function query for `serve_unix_listener` showed gap
locations that were absent from the report's normalized uncovered-region
list, so the attribution discrepancy still needs review.

### Latest full pull-request coverage run (2026-10-26)

PR run [`40317129093`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40317129093)
measured branch head `5b1ec29201c963d8590c989b07318bb7366d7922`. Its full matrix
completed 1,084/1,084 indexed cases across three verification repeats (837 ASGI
and 247 native), with no parity failures, infrastructure failures, or retries.
The 100% gate still failed at **12,880/13,052 regions** and
**9,557/9,662 lines** (172 regions and 105 lines missing).

The retained [`uvicorn-rs-unified-coverage` artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/40317129093/artifacts/12651255632)
has archive SHA-256
`a291ff61325f065ee7c742442615c2dc8571c8616a948d032b1e73ae0abb71d9`. Its
report SHA-256 is
`905a2ada915de9a248200629713215879232e77e8c4871450d4e87e5d9285043`; the
artifact context records merge revision
`d6f2400f7ebfd27adbc21e1ca44f01eceff6204c` and source digest
`53f53e87a82cecb725f5acca1ceaf8d5f05ac417c80b62217ebaf2e588a62da1`. A fresh
local hash audit found mismatches for `src/lib.rs`,
`crates/uvicorn-rs/src/lib.rs`, and `crates/uvicorn-rs/src/websocket.rs`, so
the hosted report's gap map is stale for those files in the current dirty
checkout. Its measured gaps were concentrated in the Python adapter
(`src/lib.rs`, 148 regions and 85 lines), server core
(`crates/uvicorn-rs/src/lib.rs`, 5 regions and 4 lines), and WebSocket handling
(`crates/uvicorn-rs/src/websocket.rs`, 19 regions and 16 lines). HTTP/3, its
transport, and peer-read each had 100% region and line coverage in that report.
This is PR evidence, not exact-main evidence. The Python-floor and
package-artifact jobs were skipped after coverage failed.

Coverage-MCP has not returned an independent receipt for this hosted full
report. A historical local daemon invalidation and timeout prevented that
query. On 2026-10-27, Coverage-MCP responded to an exact-receipt query for the
selected Yawc report below, but that selected result does not review this full
hosted report or satisfy the independent full-source gate.

### Prior local one-pass follow-up (2026-10-26)

One fresh attribution pass completed against dirty branch head
`5b1ec29201c963d8590c989b07318bb7366d7922`, after `src/lib.rs` changed from
the source measured by the hosted PR run. All **1,118/1,118 indexed cases**
passed once with complete case attribution and no case or infrastructure
failures. The run used `--matrix-repeats 0`, so it does not satisfy the required
three-repeat gate.

The report is
`target/asgi-coverage/coverage-current-dirty-one-pass.json` (run
`0400b930d64049b7854a70676488189a`, report SHA-256
`b90b6aeb7ca1b6f8ffdf9739065e1e11ce6599eeb2f86f278402975fbcbfe50d`). It
records source digest
`a291485ff9f3770e4660cdf1cd71b944d19aadc879f41dfb194bdf2e541c05c2` and
instrumented extension SHA-256
`7d8a29b93609283394cc758789f4f62790584d612fe94e3cd6fa7b6b05658ceb`.
Coverage remains incomplete at **12,978/13,105 regions** and **9,633/9,708
lines**. The remaining 127 regions and 75 lines are in `src/lib.rs` (112
regions, 61 lines) and `crates/uvicorn-rs/src/websocket.rs` (15 regions, 14
lines); the other measured files are complete in this report.

This is local diagnostic evidence for the dirty checkout. It does not replace
the failed hosted coverage gate, complete three-repeat run, or independent
Coverage-MCP receipt. The indexed input inventory has since grown from 1,118
to 1,133 cases, including three selected CLI cases added after this report; the
server core and WebSocket sources have also changed. It predates the Yawc
handshake fault hook and native case documented next, so it is not current
coverage for the checkout.

### Focused HTTP/2 concurrency-limit case (2026-10-27)

Added `http2.zero-concurrency-rejects-request-with-503` to
`tests/parity/inputs/http2.json`. With `limit_concurrency=0`, the case confirms
the oracle-matched HTTP 503 and reaches the HTTP/2 arm of the adapter's
`ConcurrencyLimitObserver` at `src/lib.rs:5536`.

The selected run passed 1/1 with complete attribution and no infrastructure
failures: run `8db2016852224570b63db99eea9b0a90`. Its report is
`target/asgi-coverage/selected-http2-zero-concurrency-20261027.json` (SHA-256
`7aa1d6ea15bc5ce45c0c28fd9b5ee21888ff2f9ab2838b68058cb1f865f5604e`). It is
bound to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
digest `87a46890d3d54ae7668322092896bd1b8907a57b6ff929a96f8fe41c26a6a931`,
HTTP/2 input SHA-256
`c383e9b53c71ddf7adbcc584f93a694e0e054f63aba7c9607c734087c1fe0055`, and
instrumented extension SHA-256
`d1cdd7955095a0d61c85412d1e3c41aaebd93904a0558136c5f26bc916f94657`. This
selected subset attributes 2,450/13,127 regions and 1,887/9,722 lines. It
confirms one H2 observer path; it does not refresh full coverage, satisfy the
three-repeat gate, or provide an independent Coverage-MCP receipt.
The later inherited-listener fault-hook change updated `src/lib.rs`, so this
H2 report is historical for its recorded source digest and is not an
exact-source receipt for the latest checkout.

### Focused inherited-listener address failure (2026-10-27)

Extended the existing `server.listener.local-addr-error` hook to the inherited
TCP listener path, under coverage builds only. Added the target-only fault
contract `fault.http1.inherited-server-local-address-inspection-error`; the
instrumented server received the inherited listener, returned a startup
failure, and emitted lifespan startup and shutdown events.

The selected run passed 1/1 with complete attribution and no infrastructure
failures: run `53b3ce05c19043ab8b4e5752902f5622`. Its report is
`target/asgi-coverage/selected-inherited-fd-local-addr-error-20261027-attempt2.json`
(SHA-256
`92eeb3c3e89cb6baf42c393f857229e43c5880e870ddef06e5a54389b5ffa73a`). It is
bound to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
digest `ea03a1b848d3d6dd311f37ed24e8c535295bbd74b8066a4c221f6d8d2116626e`,
input SHA-256
`6c69a3316905417bda986ae297c5efcecdcb87134856e3de5e106bb31bbbd9ce`, and
instrumented extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`. The
selected subset attributes 1,124/13,132 regions and 828/9,728 lines. It adds
one target-only input; the full coverage gate and independent review remain
incomplete.

### Focused Yawc handshake-error fault contract (2026-10-27)

The target-only case
`fault.http1.native-websocket-extension-negotiation-error-recovers` passed
1/1 with the injected failure consumed, complete case attribution, and no
infrastructure retries. This is a source refresh of an existing case after the
WebSocket handshake hook and native runner changed; it adds no new case ID.
The fault hook is compiled only into coverage builds.

The current selected report is
`target/kata-progress/b8k7-yawc-handshake-error-20261027.json` (run
`504f5ca068b546ebbf03f74b151f08ea`, report SHA-256
`91d1ca19bc2be5fb529b877b644b505385b50dde86f3d4306d3776628728f024`), bound
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source digest
`2a205a2ee7e482c69fa66338b587060036ce38db5ead5d0a24bd7762cdf76e9b`, native
manifest SHA-256
`3be1278e408924497b0b61c3a21d054fbfd715f326e332f1fdfdd6a373002589`, and
instrumented extension SHA-256
`711e2d5ffdd245e465015665711dfe62bb73ecc250147d9f1292ac222446c29a`. It
attributes 1,353 regions to the selected case. Coverage-MCP queried this exact
report for regions and lines; both results returned `status=measured`,
`source=matches_receipt`, and `tests=passed`. The one-case report totals
1,353/13,132 regions and 1,150/9,728 lines. This is selected-subset evidence,
not a full coverage refresh or an accepted independent full-source review;
the three-repeat and full 100% gates remain open.

### Focused response-header coverage diagnostics (2026-10-26)

The new parity case `python-api.module-cli-appends-custom-response-header`
passed 1/1 in local selected run `be77bb7263cc490da17a49e1e35a1871` on
macOS 15.7.7 ARM64 / CPython 3.12.13. Its instrumented report attributed 66
regions in `src/lib.rs`'s `apply_default_response_headers` function group to
the case. The report is
`target/asgi-coverage/selected-custom-header-report.json` (SHA-256
`6ee3bca8d7ea9b0eb37caf498e596883a8ae72ce8e811b8db4da565a57b57bd8`), bound
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source digest
`d5005474aff3cafc2e01a89545d1e16918660622bcca67efa8d5274f2fd31e35`, and
instrumented extension SHA-256
`ac4218787d422f8f46977880bfb6935a580c12e92a39c5f33b8de63543134f92`.
The selected subset measured 3,146/13,098 regions and 2,362/9,701 lines;
its coverage gate is incomplete. This local diagnostic is not a full-matrix
refresh or an independent Coverage-MCP receipt.

A second case, `fault.http1.generated-date-header-error-recovers`, is a
target-only fault contract. It injects an invalid Date value in the coverage
build, confirms the first request connection closes without a response, and
confirms a follow-up request receives 200. It passed 1/1 with complete case
attribution and no infrastructure failures. The report is
`target/asgi-coverage/selected-date-header-fault-recovery-report.json` (run
`a9d1063ab56b427087a532360e3663e7`, report SHA-256
`df81e45f630262769f4dba6776ceb21240b60a080da548ef332c00ff10e59934`), bound
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source digest
`4b81409879899acfb442072a6f11f06c242dd339b2db0fae6f3f5a2a4ada93ae`, and
instrumented extension SHA-256
`936e9aff985ff0eb9f1899f20f573173de185d8ff307138dfc2cb51390155bff`. The
selected subset measured 3,424/13,104 regions and 2,569/9,706 lines, so it
does not refresh the full-matrix gate or independently review the report.

### Traditional encrypted-key failure attribution (2026-10-26)

Before the cipher-enum refactor below, added two input-only startup failures
using the existing AES-128 and AES-192 traditional RSA key fixtures with an
incorrect password. Each case passed once against Uvicorn 0.54.0 and the target
with complete attribution and no
infrastructure failures. Their combined post-change run is
`d16cee8e4f4c45af8cb38c23e92ec82e`; report SHA-256
`12248fedcd1f53e674194fb1acc3db690fa5daa33a46d6bef3e4d2d928445590`. Both
cases passed with complete attribution, covering 409/13,101 regions and
280/9,706 lines in this selected subset. The report binds `src/lib.rs`
SHA-256 `84022f97dd0084bf21626aa8633ddc3017160287d184ecbd8c13d3ea3f993ff0`.
After the same refactor, the existing AES-256 wrong-password case also passed
1/1 in run `07f4cea1b5c04d0ebf177e6817b86143`; report SHA-256
`5ebe66b9ffa7bb0448137c347c3ae42d60c0b086ed40c22d72f2c8e5a6ab656f`. It
binds the same `src/lib.rs` hash and attributes 399 regions in its selected
subset.

The review also removed three unreachable constructor-error mappings. The
locked `crypto-common` 0.1.7 implementation returns `InvalidLength` only when
the key or IV lengths differ from the cipher's fixed sizes; this code derives a
key of the selected cipher's exact length and validates the IV length before
construction. The constructors now state that invariant explicitly. The
selected report's region denominator dropped by three after this change. This
source review and the selected cases do not refresh the full report or satisfy
the overall 100% gate.

A later review found a second unreachable fallback: after the parser accepted
one of three AES cipher names, decryption repeated the string match with another
unsupported-name arm. The parser now converts the accepted name into an
exhaustive `TraditionalPrivateKeyCipher` enum and dispatches on that enum. This
removed three more regions and lines from the denominator. Post-refactor run
`199b764c93424a519705beb0fbd176e9` reran the four successful AES-128/192/256
RSA and AES-256 EC cases plus all three wrong-password cases: 7/7 passed with
complete attribution and zero infrastructure failures. Its report SHA-256 is
`b69c9bb419336ec60810b6b78c32cc2748a5b4ccc6e1a4f6690e08b7bc094ef6`; selected
coverage is 3,677/13,098 regions and 2,704/9,703 lines. It binds `src/lib.rs`
SHA-256 `f59da9165e78423e0b4699cef2697c6f063e2c18f47591601662976cc285723f`
and instrumented extension SHA-256
`696971351481671c4ba18b8bc92b87768e4c28ee6942177448c49753d1617c18`.

The unsupported-cipher case was also rerun against that build, because the
enum conversion changed its dispatch point. Run
`f5838fbd6d854136958fdd6d9fa53004` passed 1/1 with complete attribution; report
SHA-256
`43b5344d22dfbd225acd451a5b4eb24ab2b120c5cb8e43fe40571ca064d43bae`. This
selected case covers 327 regions and has the same source and extension hashes.

Fifteen input-only traditional-key failures passed individually against Uvicorn
0.54.0 and the target before the enum refactor, each with complete attribution
and no infrastructure failures. The cases cover invalid `Proc-Type`, absent and
malformed `DEK-Info`, short IV, missing body, missing end marker, invalid
base64, empty and short ciphertext, unsupported cipher and label, malformed
begin lines, an empty key file, and invalid UTF-8:

| Case | Run | Selected regions | Report SHA-256 |
| --- | --- | ---: | --- |
| Invalid `Proc-Type` | `983264291e4046e8bd7b8f29ca85df89` | 260 | `d4d6524a3e06207b0179640f73a0561679ccb512827feb8163e55eb81b596097` |
| Missing `DEK-Info` | `d24d7354b8644e52b4745b1df688d95e` | 285 | `3fa2bd55834df040ea750d36eea0d5dd2df56b556d12c31b846ae55e00c40b86` |
| Malformed `DEK-Info` | `8354028a7a70418c955354544f50b746` | 290 | `884b6aa7b973000700b1d7113d8f9708886c60abaa6b7f808d217e44d791b468` |
| Short IV | `9a25cf2c911d4048931fb99c36f5bda9` | 330 | `090695eb982332b50f674b457b077c9661bb6697350c75db7433fb72791b28c5` |
| Missing body | `853a0587f2b94600b9bc323ed45ad2df` | 270 | `46436a92e73a1e635ac257ffbfe6d3af769c1a31e1106326bf9543fcbde59553` |
| Missing end marker | `430a9c463b7048318544b09a58e66507` | 280 | `2ee48f3c841106a2369ae209eb917438cd3ae8cba297b2022a190ab3e1f08e04` |
| Invalid base64 | `4538f64e4bd34c0c8d020543f1f3e3a5` | 341 | `7b22f2ee23cf0e56ce6a5a922cb02f2faa86b177534d0d4bc7178f4abe8a0408` |
| Empty ciphertext | `39e118e1f39741aea1d2e35c193d1210` | 331 | `1bf1ab82127c8cbf977150953fe446b09d23a687aba521a0b96a1fd209a5783b` |
| Short ciphertext | `07fb947cbdc5461a80e3c66f04060527` | 342 | `0e1778e81285971c75e8507a3938af1d944870ac9d1dc710675e381ff64e82d5` |
| Unsupported cipher | `b9623d34eace4a1596cf5ff445b05630` | 327 | `9d1c6246e1302d7617532e79e48f139c3242e054cd0e0def041de44cd4ff6a67` |
| Malformed begin line | `98aa88fdbaa94eb8af6d166db195504d` | 241 | `3f8c11460d55d5cb00ebc01fed65a0450c4fda2f82843d937430ad333cb882e3` |
| Empty key file | `49129e6bfc8348b0be86e944efe21c8a` | 237 | `8376509d7f3884e1867aa333277aadd3e6359ac9695cdec7137c454ee42d802a` |
| Invalid UTF-8 | `5abc82df0a004be2b41bd2793913dbe3` | 227 | `2db92f5cc8f7ea11a79ba2ae3a953a61635052c19d20844991d93577fb736de6` |
| Unsupported key label | `3c12eb5e869c4ee7821c63de06895bb1` | 247 | `ceaeab893693c38e753381948678fd631aba211785a1f2f9829bfb45211694eb` |
| Malformed begin suffix | `cfd9befa22274b0d99b88f91cfeac5fd` | 244 | `986ce54e3b3031f4d0666b8efccccaf22db91f2444a7013414e3316a200fd123` |

The 15 malformed-key reports bind `src/lib.rs` SHA-256
`84022f97dd0084bf21626aa8633ddc3017160287d184ecbd8c13d3ea3f993ff0` and
instrumented extension SHA-256
`053ca6051a9008cb4da7d94b97340a8346c254374308b178f5e13e3799adcffb`. Their
selected totals are not combined because each report has a different input
manifest digest. These cases do not refresh the full matrix or the 100% gate.

### Native WebSocket negotiation coverage diagnostics (2026-10-26)

Five newly added native WebSocket negotiation cases passed once each with
complete attribution and no failures or infrastructure retries. The cases
cover valid `client_max_window_bits`, a valid non-window parameter, invalid
client-window fallback, missing server-window fallback, and ignoring an
unsupported extension. Their per-case attribution totals are 1,697, 1,679,
1,457, 1,441, and 1,456 regions.

Correction (2026-10-27): comparing source coordinates rather than region IDs
shows that the selected report leaves the same WebSocket error spans uncovered.
The five cases passed and cover other negotiation paths, but they do not reach
the remaining error branches. The selected and full reports have the same
`crates/uvicorn-rs/src/websocket.rs` source hash
`91a15df3483202e11b4837d6175f6fbcc3b3a5c93d5c3e5ae91442ce3e4bed6a`; a
per-coordinate comparison confirms that all 15 WebSocket regions still
uncovered in current one-pass report `0400b930d64049b7854a70676488189a` are
also uncovered in this selected report. Its aggregate per-case attribution
counts are not evidence that those spans were reached. The selected report is
not full-suite evidence and cannot be combined with the current full report,
whose source and extension hashes differ.

The selected report is
`target/asgi-coverage/selected-native-websocket-negotiation-current.json`
(SHA-256
`cc8d483ee31857897cc46b6045f9734c8e1ae55fb06aae8bea1d718223e1d664`). It is
bound to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256
`4b81409879899acfb442072a6f11f06c242dd339b2db0fae6f3f5a2a4ada93ae`, and
instrumented extension SHA-256
`7d47df4e31cce994409217bbbca2b3e0d9292a4170d573045c0756188e15be4d`. This
selected subset does not refresh the full 100% gate or provide the independent
Coverage-MCP receipt.

An earlier full pull-request coverage run
[`40237012947`](https://github.com/appunni-m/uvicorn-rs/actions/runs/40237012947)
used PR head `35e548f08d1a4248488fc1351ed8850e7c80f23c`. It passed its selected
parity cases but failed the 100% gate at **12,502/12,711 regions** and
**9,280/9,415 lines** (209 regions and 135 lines missing). The uploaded report
records a synthetic merge revision, so Coverage-MCP did not accept it as a
review bound to the exact local checkout; there is no accepted independent
zero-gap receipt. The focused cases added after that run are selected dirty
source evidence and do not refresh the full gate.

Independent Coverage-MCP review is **not complete**. The local consolidation
draft has a measured report, but its coverage gate failed and there is no
accepted zero-gap receipt. The exact-main CI result still describes the old
committed package graph. Candidate package and Python-floor jobs were skipped
after the coverage gate failed. See the [release guide](releases.md) and
[benchmark status](benchmark-status.md) for the other open release gates.

After the pull-request run, five focused local startup cases reached
traditional encrypted RSA key parsing. The unsupported-cipher case passed
1/1; missing and malformed `DEK-Info`, invalid `Proc-Type`, and missing end
marker cases passed 4/4 against Uvicorn 0.54.0. Target LLVM profiles record the
rejection paths at `src/lib.rs:5710`, `src/lib.rs:5732`, `src/lib.rs:5738`,
`src/lib.rs:5742`, and `src/lib.rs:5749`. These selected dirty-source cases do
not refresh the full report or satisfy the 100% gate.

A new input, `startup-traditional-encrypted-private-key-missing-body`, checks
traditional encrypted RSA PEM with `Proc-Type` and `DEK-Info` headers but no
blank body separator. It passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13. Coverage-MCP matched the report to its source receipt
and found no missing regions at the no-body error path (`src/lib.rs:5731`).
The selected report is
`target/kata-progress/coverage-traditional-missing-body-current.json` (run
`b0cf304c045243dc90f67af63a9d086b`, report SHA-256
`e3b690370ac375d6f3e5c55c43db5c842b153b144aa18262a5b1b343f40102a3`, source
SHA-256 `925d352eac310c8219d1a154cc5fae803f1a1feb68cf3b93ed0d7b9155ccaf54`,
instrumented extension SHA-256
`926dea46abde6f4eab735fd88ef5d6996bb94d903a3c2143c2dd96273f141076`). The
selected subset measured 270/12,750 regions and 218/9,438 lines; it does not
refresh the full report or satisfy the 100% gate.

A second input, `startup-traditional-encrypted-private-key-invalid-body-base64`,
reaches the base64 decoder with valid traditional RSA encryption headers and
an invalid framed body. It passed 1/1 with complete attribution against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Coverage-MCP matched
the report to its source receipt, reported `tests=passed`, and found no missing
regions in the decoder error closure at `src/lib.rs:5763`. The selected report
is `target/kata-progress/coverage-traditional-invalid-body-base64-current.json`
(run `6fc048d2d4f84167b76caaa348f5d1cd`, report SHA-256
`4f92cd3738a48d437e9f480d9f9183b3445ca437f1cb352008076a5ea1a739d2`, source
SHA-256 `013d6d57e9c3d0e344c9d1d394316f999bf18bfa8f553f2c986ccf65d142233b`,
instrumented extension SHA-256
`0dbfbafd03dd20dc8c63079f76ef4cf43488abb2732e947ccbe56be78f144ea2`). This
selected subset measured 341/12,750 regions and 252/9,438 lines; it does not
refresh the full report or satisfy the 100% gate.

### Local consolidation draft (2026-10-22)

The one-pass local report `target/asgi-coverage/draft-after-uds-tls/coverage-report.json`
(run `a8015f34fe39456580851f22c11aa284`) uses the dirty consolidation draft based on commit
`86e72e181d00feca1b4db7f30377d5d9d4345b83`. Its source SHA-256 is
`2438ea5aff732a5ea692571c41efee9349288be0945a23e1e3d5de39805c8d03`; its
instrumented extension SHA-256 is
`5bda85c3abfe3cf2d0e414c4c4e6d1b47d8a4b1d68fd0ad35acc1e93f0ae68fd`.
The 893-case inventory (671 ASGI and 222 native) recorded 891 passed, one
parity failure, and one oracle-side infrastructure failure. It measured
11,126/11,375 regions and 8,278/8,442 lines, leaving 249 regions and 164 lines
uncovered. No full verification repeats were run (0/3).

Coverage-MCP reports `source=matches_receipt` and `tests=failed` for that exact
report. The regions query returned only page 1 of 821 function groups; region
and line results have not been fully paginated, and no accepted review receipt
exists.

At that point, the input inventory had grown to 894 cases with
`cli.websocket-ping-interval-zero-disables-keepalive-and-exits`. Its isolated
oracle parity passed 1/1, and selected coverage report
`target/asgi-coverage/cli-ws-ping-zero/coverage-report.json` (source SHA-256
`324eee016deccef3c317cbb4104ccdf0509858c09ee81977e20e055ee59b01b3`)
recorded one passing case with the same instrumented extension. This selected
run is not a full-matrix refresh or a coverage-gate pass; that 894-case
inventory had no complete report or three-repeat evidence. The case checks
startup with a zero ping interval and immediate request-limit shutdown; it does
not exchange WebSocket frames or prove active-session ping suppression. These
`target/` reports are local ignored artifacts, not published documentation
attachments.

The current 2026-10-26 working-tree inventory contains 1,059 cases: 819
indexed ASGI inputs (498 oracle-parity and 321 target-only fault-contract
cases) plus 240 native-core contracts. The three new Yawc adapter fault cases
passed 1/1 each in a selected local coverage batch on macOS ARM64 / CPython
3.12.13. Two additional Python API parity inputs compare successful loading of
a traditional AES-256-CBC encrypted RSA key and the wrong-password failure;
both passed against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. The parity
receipt is `target/kata-progress/parity-traditional-key-current.json` (run
`d8d3680a7144445891702d5694d2f08c`, 2/2, report SHA-256
`5ac2a8d0051609964f20a4281c3498eb505e3f42e27489ac2a9448a85600e04b`, dirty
source digest `e81ab997f0b1f8405bba9400028366681d8f73c977c7823783d71c5cc7fb3af4`).
This selected parity receipt is not a coverage-gate result. The five selected
TLS-key inputs also passed an updated local coverage batch after the
traditional PEM end-marker fix: 3,672/12,680 regions and 2,685/9,401 lines
covered. Its report is `target/kata-progress/coverage-encrypted-key-formats-fixed.json`
(SHA-256 `7e38dadb2a0bb9eea00e86da5961a10e0bddfb64649c93c07d4324823233f1d5`,
source SHA-256
`6e611ec3893ec3ef8ef2c5f71f7e3ccf0e43d3562038b1c2f31bd865c73961e9`). This is
selected-subset evidence and does not establish the full coverage gate. The
new input `python-api.config-server-uses-traditional-encrypted-ec-key` adds a
successful encrypted SEC1 EC-key load through the Python API. It passed 1/1
against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. The parity
receipt is `target/kata-progress/traditional-encrypted-ec-key-current-20261026.json`
(run `5c776eaf4bd24718aab95a887907c8a2`, SHA-256
`a05d380a44c4b1ba327193ce27a9d7808638a5fdd79b22f2555ddd3224def48f`). It uses
dirty source at `35e548f08d1a4248488fc1351ed8850e7c80f23c` and did not collect an
LLVM coverage profile; it is parity evidence only, not a coverage-gate result.
The separate Yawc coverage report is
`target/kata-progress/coverage-yawc-adapter-faults-775489526/coverage-report.json`
(SHA-256
`6242f3b1a9e9d17e4cfb3987ac0a0cac67c21708a89ddc545528db2cfb65a0e2`; build ID
`5c5da52e017315a2d58616df9c4356882a0b2f532cf3b7cf9de41fd3be4e5c26`). The
source receipt hashes match the Rust source files recorded by that report. Case attribution
confirms the invalid-text conversion, invalid close-reason conversion, and
unexpected-continuation error regions were reached. This is selected-case
evidence only: the report is incomplete, with 8,011 uncovered regions and
5,984 uncovered lines across its full instrumented source set. There is still
no complete coverage report or three-repeat evidence for this source/input
set. Earlier reports remain bound to earlier source and input identities and
do not certify this expanded inventory.

An earlier two-case client-auth run exercised only CA-backed required and
optional authentication. It passed 2/2 and covered 44 of 75 regions in the
then-current verifier; its report and Coverage-MCP query are historical. The
statement that rootless client authentication was unexercised is superseded by
the focused adapter batch below.

The five-case batch covers a trusted client certificate with default TLS
negotiation and forced TLS 1.2, optional anonymous clients with and without
configured roots, and rejection of a presented client certificate when no
trust roots are configured. All five passed against Uvicorn 0.54.0 on macOS
15.7.7 ARM64 / CPython 3.12.13, with complete per-case attribution and zero
case or infrastructure failures. The focused report is
`target/kata-progress/coverage-mtls-verifier-adapter-20261026.json` (run
`b3823fe0aff14ae8bd3e30f7921afc14`, report SHA-256
`96251e88d25194fe527747b93d711451983208db3773f7ef767186cefe7ecb80`). Its
selected-source coverage is 3,480/12,712 regions and 2,607/9,415 normalized
lines; the coverage gate is incomplete. The instrumented export records one
hit each for `ClientCertVerifierAdapter::verify_tls12_signature` and
`ClientCertVerifierAdapter::verify_tls13_signature`. The report binds to dirty
revision `489e65674f03c3a226c49387318a99be83c32936`, source digest
`c994a889f9429f7a6b3014321cb6c8863d6c99d309ccce5f715d3da6d405b7c3`, and
extension digest
`a43a714a0af88181e8517ce530889ae92df0473430c58e8f4191d5ff8271343e`; it
binds the pre-rustfmt working-tree source and input schema @36, before the
format-only Rust change and input-schema marker migration to @37. It is selected
evidence only, not a full coverage report, three-repeat result, or full
Coverage-MCP review.

A separate selected case exercises trusted client authentication through the
module CLI with TLS 1.2 pinned. Its first attempt exposed a missing
`ssl_version` local in the parity probe's CLI argument assembly; after fixing
the probe, the case passed 1/1 with complete attribution and no infrastructure
failure. The report is
`target/kata-progress/coverage-mtls-tls12-module-cli-retry-20261026.json`
(run `9d3c0e9a9e5f4fe4a442b7c53fce7f80`, report SHA-256
`4f1b5c53ecdd71c62fcadf98209fa984388655f588d05e0007a805849a13705e`). It
measured 3,458/12,711 regions and 2,578/9,415 lines, so the full gate remains
incomplete. It binds to dirty revision
`489e65674f03c3a226c49387318a99be83c32936`, source digest
`bdc1b9ddf654172e2a226b463d165b74bb060cc56c75bd23bb4e898f49aa8c26`, and
extension digest
`c74c89acb61d6d8abd0f7803d55dc9a724d30839ecb4138a70b67d2f7e2b7b32`.
This remains one selected case, not a full coverage report, three-repeat
result, or full Coverage-MCP review.

One focused Python API input now checks invalid `ssl_cert_reqs=3`. It passed
1/1 against Uvicorn 0.54.0 after matching the upstream `ValueError` text,
`3 is not a valid VerifyMode`. The selected report is
`target/kata-progress/coverage-invalid-client-cert-reqs-20261026.json` (report
SHA-256 `c282768a5fe7b5c89f8cce76a148c6c93bdb70a2a8cf1c26a0a3d71d66248b7e`,
build ID `ceb0acb6269aa4bf148ff84d93bb86336252b70905a75439d9e6e8b2fb405bfe`,
source SHA-256
`7189a531535da3dc4215277f8bc0a087097a6840c78ffe10030a9bf376142236`). Its
selected case covers 177/12,711 regions and 159/9,415 lines. Coverage-MCP
matched the source receipt and found no missing region at the error formatting
span (`src/lib.rs:5578`); the selected report still has an uncovered valid-mode
branch at `src/lib.rs:5577`. This is one dirty-source case, not a refreshed
full report or a 100% gate pass.

A separate input uses an empty `ssl_ca_certs` file with `ssl_cert_reqs=2`.
It passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13;
both servers reject startup with matching `ssl.SSLError` observations. The
selected report is
`target/kata-progress/empty-client-ca-matched-runtime/coverage-report.json`
(run `0a2be6f26e5b438dac0db9593e049564`, report SHA-256
`19a4e7ca2cab4f5f2058c669d51bfa457f2d634a857f0505d7b17d0960c61a13`, source
SHA-256 `ce35205bbd74c6ca56eb09f6d8e06fda4748986c2e3d0084d67fdac572cb355f`,
instrumented extension SHA-256
`9879a7e67d83799c1f360ae67732ee27aa902dbb626fa85702bb3ee1a9e146d1`).
Coverage-MCP matched the source receipt and recorded the selected test as
passed; the single-case report remains incomplete at 225/12,750 regions and
189/9,438 lines and does not refresh the full gate. The case covers the empty
client-CA error path only.

A later selected case, `python-api.run-websocket-zero-ping-interval-disables-keepalive`,
opens a WebSocket through the Python API with a zero interval, waits 0.35
seconds, then exchanges an application message and closes normally. It passed
1/1 against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13 and its instrumented
profile reaches the non-positive interval branch. This does not observe
Ping-frame emission. The result and hash are recorded in the
[Uvicorn contract evidence](maintainers/uvicorn-0.54.0-contract.md); it does not
refresh the full coverage report or satisfy the 100% gate.

The selected input `python-api.run-websocket-negative-ping-timeout-closes-1011`
also passed 1/1 against Uvicorn 0.54.0. It exercises the negative timeout
conversion and immediate 1011 close path; its receipt is recorded alongside the
zero-interval result. These selected cases do not replace a fresh full-matrix
coverage run or the independent zero-gap Coverage-MCP review.

<a id="current-unified-coverage-status-2026-10-19"></a>

### Previous hosted coverage status (2026-10-19)

Hosted exact-source CI run
[39205955886](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955886)
passed on clean commit
[5b279d48ddf60bb26380914eaf32b13717a647fb](https://github.com/appunni-m/uvicorn-rs/commit/5b279d48ddf60bb26380914eaf32b13717a647fb).
The [unified coverage job](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955886/job/117908726187)
passed attribution for 761/761 cases (547 Python ASGI and 214 Python-free
Rust), with three complete repeats of each lane. It measured 9,300/9,300
source-span regions and 6,880/6,880 normalized physical executable lines.

The same CI run passed installed-wheel public parity 251/251, native
FastAPI-RS → Starlette-RS → Uvicorn-RS composition, Rust MSRV, and package
jobs. These are separate gates from coverage. The retained
[hosted coverage artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39205955886/artifacts/12166704523)
contains the run-bound report.

**Independent Coverage-MCP review remains outstanding.** The artifact records
mcp_status=awaiting_query; earlier full-report and reduced-query attempts
timed out without a receipt. Passing the CI coverage gate does not replace
independent Coverage-MCP review. See the [release guide](releases.md) and
[benchmark status](benchmark-status.md) for remaining gates.

<a id="current-unified-coverage-status-2026-10-17"></a>
<a id="current-unified-coverage-status-2026-10-18"></a>

### Previous hosted coverage report (2026-10-18)

Hosted exact-source CI run
[39107767728](https://github.com/appunni-m/uvicorn-rs/actions/runs/39107767728)
passed its unified coverage job on clean commit
[`dd6ed00f551c02196544ae9452c7b0747452a422`](https://github.com/appunni-m/uvicorn-rs/commit/dd6ed00f551c02196544ae9452c7b0747452a422).
The [coverage job](https://github.com/appunni-m/uvicorn-rs/actions/runs/39107767728/job/117617220689)
completed attribution for all **757/757 cases** (543 Python ASGI and 214
Python-free Rust). All three full ASGI repeats and all three native repeats
passed with zero failures, infrastructure failures, retries, or unrun cases.
The hosted report measured **9,166/9,166 source-span regions** and
**6,768/6,768 normalized physical executable lines**. Attribution matched the
coverage union. The report records source SHA-256
`7124365a1a219b40196cf2b358b593b6eddb70fade3ea67607a7d5cbd07265e6`, native
extension SHA-256 `651eafee745e399001178bc20f980268917c64c503ad8430f4e25727785a7d03`,
and `mcp_status=awaiting_query`. The retained
[hosted coverage artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39107767728/artifacts/12129763726)
has SHA-256
`482eae3da1709e6cfb38c6c4a7b25cf02afa06f3e6df411526ac4ac38cdc1734` and
contains the report and per-case evidence.

The same exact-head run also passed the complete installed-wheel public input
matrix **251/251** and the Python-free native FastAPI-RS → Starlette-RS →
Uvicorn-RS composition inputs. These are separate gates from source coverage.
All three platform package jobs passed, including Linux source-archive rebuild,
Rust archive packaging, and exact-wheel public parity.

**Coverage-MCP review of this hosted report remains outstanding.** The CI
report explicitly says `awaiting_query`; do not treat the hosted artifact's
100% totals as a completed Coverage-MCP receipt. The fully paginated local
Coverage-MCP evidence below is for an earlier matching source commit, not
`dd6ed00`, and does not substitute for querying this report. I extracted the
exact raw report and context from the hosted artifact, but both region and line
queries timed out after 60 seconds; a file-filtered region query also timed
out. No MCP receipt was produced.

### Previous matching-source local Coverage-MCP receipt (2026-10-18; 8d1f169)

A separate full local run on clean code commit
`8d1f16950971a56e35ce566d38b5d700d0d039e7` was independently checked by the
strict offline evidence checker and Coverage-MCP. Coverage-MCP fully paginated
that report: 26 region pages covered all 513 diagnostic groups, and one line
page returned zero gap groups. Both metrics reported `source=matches_receipt`,
`tests=passed`, and zero missing regions or lines. This receipt is bound to
the local instrumented build and the 8d1f169 source hash; it is not an MCP
receipt attached to the current hosted artifact.

| Local evidence identity | Value |
| --- | --- |
| Recorded revision | `8d1f16950971a56e35ce566d38b5d700d0d039e7` (clean) |
| Source SHA-256 | `0d42d33ef1a0b13bee09eef13772682fae709a6ade19683b0af1383a9cffa019` |
| Instrumented extension SHA-256 | `cdecca74c0d98e66e054b1caeeaabd2c94cb8d24339b0bfdb4596506926c2bd4` |
| Coverage run ID | `7ae7d556b5f941b5bdc9bd0f759fca1a` |
| Coverage report SHA-256 (after MCP receipt attachment) | `71cff208637265eb4bbb1c9194fb8ee0dfcd49dfe4b917cdfa66bd0adb333de2` |
| MCP page receipt SHA-256 | `d3d1a6357a9af11f44b4fb8af01384d072aab3ff85200a097750dbd9697ea9b3` |
| Environment | macOS 15.7.7 ARM64, CPython 3.12.13, Rust 1.98.1, cargo-llvm-cov 0.8.7 |

The ignored local artifacts are
`target/asgi-coverage/full-local-8d1f169-ci-env/coverage-report.json`, its
`.context.json`, and `coverage-mcp-pages.json`. The local artifacts are not
hosted CI artifacts. Neither report establishes package readiness, full
Uvicorn compatibility, or a performance gain. The release gates remain listed
in [release status](releases.md).

### Previous hosted report (2026-10-17)

Hosted CI run [39020268579](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579)
on clean commit `aa4c93836f5e2147462837bbd8b1bde6c0ebe84e` completed its
749-case manifest (535 ASGI, 214 native), all three repeats of each matrix,
and per-case attribution. It measured 9,004/9,004 source-span regions and
6,636/6,636 normalized physical executable lines. Its source SHA-256 was
`6005f3b617f09df31d7271ab0ef891809cef0e6148cc2a8cd02c415ec9d96f64`, and its
instrumented extension SHA-256 was
`1739528ddbccd3c131ddbb232f8411c5f98a1da3ccc67529c60f1cade3b41711`. Its
report metadata still says `awaiting_query` for Coverage-MCP. The retained
[hosted artifact](https://github.com/appunni-m/uvicorn-rs/actions/runs/39020268579/artifacts/12097831254)
is historical evidence for that commit and is superseded for current-source
coverage by the exact-source local report above.

### Previous local 748-case aggregate (2026-10-17)

This earlier local aggregate executed all **748/748** manifest cases (534 ASGI
and 214 Python-free native Rust). Three complete ASGI repeats each passed
534/534, and three native repeats each passed 214/214. Attribution passed
748/748. There were zero case failures, infrastructure failures, transient
infrastructure retries, or unrun cases.

The aggregate measured **8,997/8,997 executable source-span regions** and
**6,629/6,629 normalized physical executable lines**. Coverage-MCP fully
paginated the exact report: 26 region pages covered all 509 diagnostic groups,
and the line page reported zero groups because no line gaps remain. Source and
build identities match, and the MCP gate reports `tests=passed` with zero
missing regions or lines. The 509 region groups are per-function-instantiation
diagnostics, not uncovered source spans; the accepted denominator is the
validated source-span and physical-line union, not duplicated generic
instantiation counters in raw LLVM summaries.

The offline evidence checker independently reconstructed the retained LLVM
profiles and passed. It verified all 748 attribution cases, the three ASGI and
three native repeats, and both 100% coverage totals without rerunning the
cases.

The local-only report is bound to dirty revision
`27de9f3ac7d259a3a9b612c3247ab2c60eb27306`, source SHA-256
`f1627a340a49b8d62d74b2630e4e3e43136461e98ab018328a9294173b332ada`,
instrumented extension SHA-256
`e5d67ee18d1b5a2960f323266d6775b54346d7c1154d1982491611c2bc6812b0`, run ID
`84fa54ad4c9d4218b4ffba79d111098a`, and report SHA-256
`cc83cf9928c2f8bf924ab94463b75a4d6d9d0dfb0a0830387663ef135c50c197`. The
Coverage-MCP build ID is
`4ddfed70ecc82d6dc3d6b9d6b1e55c04c2b3330e7d765254ebfa8d37ee468c88`; the 27
page receipt SHA-256 is
`c884c4db25dee6192adb9f667b2306d8f2ca832fd0654463ea2a9a718932bc5f`. The
report, page receipt, and context receipt are ignored local artifacts under
`target/`. This local result is historical and is superseded for current-source coverage by
the 753-case exact-source report above. It is not hosted release evidence.

### Historical 717-case report (2026-10-15)

Exact-source hosted CI [run 38790016719](https://github.com/appunni-m/uvicorn-rs/actions/runs/38790016719)
on commit `5a32e3c0d84a02c95fe8a3f01712c895419ea571` completed all 717 indexed
cases. It reported 8,654/8,654 LLVM regions and 6,521/6,521 lines, with zero
uncovered regions. The evidence checker rejected the run afterward because the
report producer and checker used different wording for the pending
Coverage-MCP request. This was a receipt-contract failure, not a failed ASGI
case or uncovered source region. The producer wording now matches the checker;
this edited source needs a new exact-commit hosted run and a matching
Coverage-MCP receipt. The hosted report artifact is
[uvicorn-rs-unified-coverage](https://github.com/appunni-m/uvicorn-rs/actions/runs/38790016719/artifacts/12001561854).

The local full-source report below is a separate earlier dirty-source result.

The final local full-source report executed all **717/717** declared cases:
511 Python ASGI cases and 206 Python-free native cases. Attribution passed
with zero case failures, infrastructure failures, retries, or unrun cases.
All three full ASGI repeats passed **511/511** and all three native repeats
passed **206/206**, with zero transient infrastructure failures in each
repeat. Per-case attribution matches the aggregate union.

The measured executable-source union is **8,651/8,651 LLVM regions** and
**6,523/6,523 lines**. The unified source coverage gate and strict evidence
checker both passed.

| Executable source file | LLVM regions | Lines |
| --- | ---: | ---: |
| `src/lib.rs` | 5,563/5,563 | 3,998/3,998 |
| `crates/uvicorn-rs/src/lib.rs` | 1,447/1,447 | 1,227/1,227 |
| `crates/uvicorn-rs/src/http3.rs` | 673/673 | 536/536 |
| `crates/uvicorn-rs/src/http3/transport.rs` | 366/366 | 291/291 |
| `crates/uvicorn-rs/src/websocket.rs` | 405/405 | 320/320 |
| `crates/uvicorn-rs/src/peer_read.rs` | 197/197 | 151/151 |
| **Total executable source** | **8,651/8,651** | **6,523/6,523** |

At this historical source revision, the lifecycle crate was named
`native-app-contract`; it has since been renamed to
`asgi-lifespan-protocol-rs`. The historical source has no executable LLVM
counters. The coverage-only helper
`crates/uvicorn-rs/src/http3/coverage.rs` is reported separately from the
production executable-source denominator.

Coverage-MCP measured the same report and matched its source/build receipt:
13 region pages and one line page, `tests=passed`, `gate=passed`, and zero
missing regions or lines. Its 187 region groups are per-function-instantiation
diagnostics; they do not replace the aggregate totals. The strict CI evidence
checker also accepted the attached report and receipt.

The report is
`target/asgi-coverage/final-release-acceptance-20261015-r4/report.json`,
run `665c07b933654d4bbb5482415705df51`, at revision
`1bde9cee0bb89618a30c3fc01b04af183f709c7b`. Its source SHA-256 is
`5335d58d277dc3c844c7f602f349053214e2c8f8a2fb4f6cc1dc126c1b313ef2`;
the instrumented extension SHA-256 is
`0020079b603a1d065a8ced12fe3eecdfd4e9d71184871d8069cc31c5ee5663ce`;
the report SHA-256 is
`301be8575d59f277e169a4199d5d6c44487483e9f5968811612054f6c1ba78cf`;
and the paginated Coverage-MCP receipt SHA-256 is
`362b8c044366b503d9b6887b1d191b5a4d701e0ea3b0eab95a8e50085d0433fe`.
Environment: macOS 15.7.7 ARM64, CPython 3.12.13, Rust 1.98.1, and
`cargo-llvm-cov` 0.8.7. This is a source-hash-bound **dirty local** result;
it does not establish a clean-commit or hosted release pass. Reports,
profiles, logs, and MCP data remain under ignored `target/`.

### Earlier full-coverage snapshot: t6zz v6

This earlier schema v7 snapshot declared 511 Python ASGI cases and 164
Python-free native cases (675 total). Its full report is
`target/asgi-coverage/t6zz-final-acceptance-20261015-v6/full-report.json`.
It records run ID `53b90df8098b43c0ab702742581d37ad`, revision
`1bde9cee0bb89618a30c3fc01b04af183f709c7b`, and a dirty worktree. Its source
SHA-256 is
`edf9189996750cb42c7cbabbe7d3238556f24a40ae84fc0fad6f740f2cd8c368`; the
report SHA-256 after the MCP receipt was attached is
`87949c1c2582ec68dbf15cbec6e1d5f23cb47e1981226094741b1775d2f112db`.

All **675/675 attribution cases passed**, with zero failures, infrastructure
errors, or retries: 243 oracle-parity cases, 268 ASGI fault-contract cases,
156 native target-contract cases, and 8 native fault-contract cases. Three
complete ASGI repeats passed **511/511 each**, and three native repeats passed
**164/164 each**, with zero transient infrastructure failures in every run.
Per-case profile attribution matches the aggregate. Normalized LLVM source-span coverage is
**7,655/7,655 regions** and **5,706/5,706 lines**. The instrumented extension
SHA-256 is `da8b066b124b8fcefee33497fafb5c1b4aa7219e49cf4d13017c3c7441d9e5cb`;
the measurement used Python 3.12.13 on macOS 15.7.7 arm64 and Rust 1.98.1.

### Resolved source gaps and deterministic behavior

- The two watch-channel lifetime fallbacks (`R2` and `R3`) were removed by
  replacing the manual watch loops with `watch::Receiver::wait_for`. Existing
  public HTTP/1 upgrade-lifetime and HTTP/2 stream-reset-lifetime cases passed
  and attributed the changed paths.
- The HTTP/1 graceful-timeout drain (`R4`) is exercised by
  `http1.shutdown-timeout-drains-completed-connection-and-aborts-held-sibling`.
  It keeps one completed connection's response, aborts a held sibling at the
  public shutdown deadline, and observes the timeout result.
- HTTP/3 request cancellation (`R5`) now has one owner at the connection
  supervisor. It closes and aborts remaining request tasks after the QUIC
  connection closes, then drains task results. The malformed-control-frame
  held-sibling case and the peer-close held-response case both pass and
  attribute the cancellation behavior.

- The formerly unreachable HTTP/1 upgrade receiver closure is exercised by
  `fault.http1.upgrade-receiver-closed-keeps-service-healthy`. A coverage-only
  fault closes the receiver while the service is polling it; the case checks
  connection handling and a later healthy HTTP request.
- The derived WebSocket accept-key conversion error is exercised by
  `fault.http1.native-websocket-derived-accept-key-header-value-error-recovers`.
  A coverage-only fault reaches the fallible header-value conversion; the
  case verifies handshake rejection and a healthy follow-up request. Ordinary
  valid-key and invalid-key RFC handshake cases continue to cover protocol
  behavior. The constructor remains fallible; no panic or unsafe construction
  was introduced.
- The native HTTP/3 control-stream stop/shutdown case observes STOP_SENDING
  transmission, then requires a later ACK batch with no bytes in flight and
  no intervening packet loss or congestion. A client-only observer delegates
  to Quinn's default Cubic controller; a short client keepalive ensures a new
  ACK batch can arrive. This establishes delivery before requesting shutdown.
  The normal build passed 20 focused repetitions. The final instrumented case
  and all three native matrix repetitions also passed.

These two new paths are declared fault contracts, not Uvicorn parity claims.
Each verifies an externally observable response or recovery property. They
remain inside the same unified source denominator and per-case attribution
map.

### Coverage-MCP receipt and strict evidence validation

Coverage-MCP read this exact report with `source=matches_receipt`, matching
build identity, and `tests=passed`. The fully paginated receipt contains 9
region pages and 1 line page. Aggregate region coverage is **7,655/7,655**
with zero missing; line coverage is **5,706/5,706** with zero missing. MCP
returns 163 per-function-instantiation diagnostic groups and zero line groups.
Those grouped observations retain LLVM monomorphization detail; the aggregate
source-span totals are the coverage gate. Receipt SHA-256:
`6281f21c07a298e75e2c2f0f97b178ec1a612dc4142b0f3de33d50678a7632aa`.

Strict validation passed on this report after independently replaying the
retained aggregate and all 675 isolated case profiles. It verifies exact native
case and fault multisets, authenticates their execution order against recorded
stdout, and checks the complete MCP receipt. Both Astra review findings—the
native execution-order mismatch and imprecise HTTP/3 delivery barrier—are
resolved in this measured source. Run the same validation with:

```sh
.venv/bin/python scripts/check_ci_evidence.py coverage \
  target/asgi-coverage/t6zz-final-acceptance-20261015-v6/full-report.json
```

The passing output is retained in the same directory as `strict-check.log`.
Reports, profiles, logs, and MCP receipts remain under Git-ignored `target/`
and must not be committed. Kata `t6zz` is locally complete. The evidence is
exact for this dirty source snapshot; hosted CI and a clean committed-source
run remain release validation steps. Python and branch coverage are not
claimed. Older dated reports below are historical.

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
675-case manifest and does not satisfy the exact-source coverage gate.

### Normal and instrumented native case lanes

The t6zz v6 native manifest contained 164 cases: 156 `target-contract` cases
and 8 `fault-contract` cases. Unified schema v7 ran all 164 native cases
with all 511 Python ASGI cases. Each native fault contract must be consumed
by an instrumented run; the normal harness rejects fault-contract inputs with
`native fault contracts require an instrumented coverage build`.

The focused selector and fault-lane receipts below are historical evidence
from the earlier 150-case native manifest, which had 149 target contracts and
one fault contract. They document the normal-build rejection fix, not the
the t6zz v6 164-case lane or current aggregate coverage result.

The normal harness previously substituted an abortive client reset for a
declared fault in normal builds and could report a pass without consuming the
fault. That substitution was removed; the input and expected behavior remain
the same across builds.

Three affected normal inputs passed, and the same fault input was rejected by
the new normal binary. The retained old binary reported a pass for that fault
without fault consumption, so it provides the defending negative control. The
historical local receipt is
`target/native-contracts/normal-fault-lane-focused.json`, SHA-256
`c662db78d82eca8b362e4c0c55f6661b0a8441026f95414afe8937e17a5be601`.

The historical selected coverage run passed **1/1**, with the declared
`websocket.receive.close-reply.flush` fault consumed, zero retries and no
infrastructure failures. Report:
`target/asgi-coverage-kata-20261014/normal-lane-fault-control/repeat-marker-report.json`;
source SHA-256
`59e4315f7bc3cd30673a63f4ab1aaab22a7223f91937a4f6d1dbe69baf74d898`;
report SHA-256
`40842f1cc3fb44c9065e69d6a2e729cb9649b2b3328a9663faf39b0cd3cf6912`.
Coverage-MCP matched the source and passing selected receipt and found no
missing region groups at the close-reply fault arm. This proves the affected
historical lane behavior; it does not establish aggregate coverage for the
t6zz v6 675-case manifest. No complete repeats were run for that focused
change. The selector's six CLI controls also passed in that snapshot: a valid
149-case selection and rejection of duplicate/empty IDs, unknown modes, a
normal case declaring a fault, and a fault case without a point. Its local
receipt is `target/native-contracts/selector-controls/receipt.json`.

### Historical selected native TCP EOF evidence

The 18-case report below predates the current full matrix. Its observations
remain useful design history, but its denominator and coverage totals are not
current; use the 2026-10-17 unified result at the top of this document for
current-source status.

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

In that selected snapshot, the EOF cases observed the signal **after response completion**. Hyper's
`half_close(true)` preserves response delivery but does not promise a socket
read while an HTTP/1 service is held. Kata `1m58` tracks prompt FIN observation
at the protocol-driver level. Suppressing EOF for the entire service lifetime
would also suppress incomplete request-body errors and can stall an app
awaiting its body; that approach was rejected. No timer, second socket reader,
probe write, or fabricated disconnect was added. This selected evidence does
not qualify the 661-case gate at that time.
The later fault-harness correction changed the source receipt; the 18-case
report is a historical selected snapshot.

The current native implementation adds opt-in `PeerReadHalfCloseMode::Proactive`:
one owned raw TCP reader feeds TLS/HTTP through a bounded queue while the
protocol driver remains the sole consumer. The Python ASGI adapter selects this
mode for HTTP/1.1 and HTTP/2 over TCP/TLS. Its native `ConnectionClosed` bridge
observes the peer-read signal and supplies a repeatable `http.disconnect` when
the app calls `receive()`. On 2026-10-20, clean `origin/main` commit
`0bd5877529e8f8b7434b7f7ab1852c0753f5e642` passed ten consecutive selected-case
runs of `http1.disconnect-before-first-asgi-receive` against stock Uvicorn
0.54.0 on macOS ARM64 (Python 3.12.13, Rust 1.98.1). The source SHA-256 was
`7be314247077dad7463121dcc167d0f9562a1104df8c5bc1332973bda88f37ac` and the
built extension SHA-256 was
`08cd62c448496f035e651b2b8993304e68bd2640a35939cf2c06a1a7e88d4fe2`. Every run
observed `http.disconnect` and matching follow-up HTTP 200 responses with the
connection open. This current-commit recheck does not explain the older hosted
mismatch or prove full ASGI disconnect conformance.

The 2026-10-17 full matrix at the top includes the current ASGI and native
manifests, including the TCP/TLS peer-read and disconnect cases. Its passing
aggregate is the current local coverage evidence. The latest hosted run
[38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888)
passed 712 cases on an older manifest but left 154 regions and 106 lines
uncovered; run `38828501018` is earlier historical evidence. Single-case
reports use a selected-subset denominator and do not establish aggregate
coverage.

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

Historical reports include five target-only cases for the experimental
`UVICORN_RS_MAX_BLOCKING_THREADS` setting. The cases and setting were removed
after matched FastAPI upload measurements failed to establish a repeatable
performance benefit. Archived coverage counts still include those cases where
they were present; the current manifest does not.

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
package job failures are recorded in [release status](releases.md).
The retained unified-coverage artifact is ID `11506803058`, SHA-256
`d107cfb007ae41673feb025253cdd00706168f51df411fa5fdfc6c6fdb3a910c`.

## Historical hosted verification (runs #36–#39)

Runs [#36](https://github.com/appunni-m/uvicorn-rs/actions/runs/37679543470)
and [#37](https://github.com/appunni-m/uvicorn-rs/actions/runs/37684421046)
passed the unified coverage job. Run #37 is on exact main commit `e617f13`;
its check annotation reports 491/491 cases, 5,121/5,121 regions and 3,624/3,624
lines. The job runs one attribution pass and three complete matrix repetitions.
The separate installed-wheel parity gate passed 239/239. Run #37 failed
afterward in the platform package jobs; see [release status](releases.md).
This result closed hosted coverage for commit `e617f13` only. It does not
cover later commits or the current dirty worktree. The local Coverage-MCP
receipt requirement for a public release remains separate.

Run [#38](https://github.com/appunni-m/uvicorn-rs/actions/runs/37688528361)
on commit `226ab13` also passed hosted attribution and all three complete
repeats: 491/491 cases, 5,121/5,121 regions, and 3,624/3,624 lines. Its normal
installed-wheel public parity passed 239/239. The run failed later in the
macOS package consumer because the probe certificate had a duplicate
extension OID; Linux and Windows package jobs passed, while Python-floor was
skipped. See [release status](releases.md). This updates hosted
coverage evidence for `226ab13`; the source-matched local Coverage-MCP receipt
requirement for a public release remains separate.

Run [#39](https://github.com/appunni-m/uvicorn-rs/actions/runs/37692260364)
on exact main commit `a78b4a925654ee0a5fb80814074ca2b0224bb094` passed hosted
parity (239/239), attribution and all three complete repeats (491/491 cases),
with 5,121/5,121 regions and 3,624/3,624 lines. Its package matrix and Python
3.9.25 consumer also passed. This was the latest hosted coverage result for
its October 8 commit at the time. The newer hosted run
[38862681888](https://github.com/appunni-m/uvicorn-rs/actions/runs/38862681888)
is summarized in [current unified coverage status](#current-unified-coverage-status-2026-10-17);
its older 712-case manifest left 154 regions and 106 lines uncovered.

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
idle Python-task growth, and limit the spread between the last two sampled
server-process-tree RSS values to 16 MiB. The sampler includes worker children
so a supervisor's changing RSS cannot hide or invent server growth. Summed RSS
may count shared pages more than once; this is a fixed-load stability check,
not an absolute memory cap or a throughput/latency benchmark. A separate
zero-grace HTTP/1.1 shutdown case
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

The case inventory is a focused black-box map, not full ASGI conformance. One
strict H1 response-order case now passes on the local draft; H2/H3 order remains
unverified or mismatched, and optional extensions are unsupported. See the
[support matrix](support-matrix.md) and [ASGI case inventory](asgi-case-inventory.md).

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
UV_PROJECT_ENVIRONMENT=target/coverage-oracle uv sync --python 3.12 --locked \
  --only-group benchmark --only-group uvicorn-oracle --no-install-project
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --oracle-python target/coverage-oracle/bin/python \
  --output build/asgi-coverage/unified/coverage-report.json \
  --artifacts-dir build/asgi-coverage/unified/artifacts
```

The runner builds the LLVM-instrumented Python extension and native contract
executable, runs every case from both manifests in an isolated target process
for case-to-region attribution, then runs each complete matrix three times.
It verifies source/build identity and that the
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
extension, `matrix.case_results` records the ASGI cases and
`matrix.native_case_results` records the native cases, including their
verification modes, observations, and profile receipts.
`coverage.regions` contains every measured source region and its complete
`hit_by` list of case keys (`asgi:<id>` or `native:<id>`). To find what a case triggered, filter those region
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
report and saved page array. Require matching source-span totals for both
metrics, zero missing regions and lines, `source: matches_receipt`,
`tests: passed`, and complete pagination before strict validation. Schema v9
retains per-function-instantiation diagnostic groups even when the union of
identical source spans is fully covered; the checker independently reconstructs
that union from the retained aggregate and isolated profiles.

```sh
uv run --python 3.12 --locked --group benchmark python scripts/attach_coverage_mcp.py \
  --report build/asgi-coverage/unified/coverage-report.json \
  --receipt build/asgi-coverage/unified/coverage-mcp-receipt.json
```

Then validate the attached report:

```sh
uv run --python 3.12 --locked --group benchmark python scripts/check_ci_evidence.py coverage \
  build/asgi-coverage/unified/coverage-report.json
```

CI uses `--allow-pending-mcp` only to validate the raw report while the MCP
query is pending; it does not satisfy the strict acceptance gate.

<a id="release-coverage-mcp-handoff"></a>

## Complete the release Coverage-MCP handoff

The release candidate needs a Coverage-MCP receipt for the exact successful
main CI run. The handoff preserves the raw artifact byte for byte, creates a
deterministic compact projection containing every canonical source span and
uncovered span, and binds that projection and its receipt to the raw report,
CI run, source hashes, build, and passing full test matrix. The candidate
rebuilds and validates the projection and receipt offline.

1. Wait for the complete main CI run to succeed. Record its run ID, attempt,
   and commit. Download `uvicorn-rs-unified-coverage` into
   `target/asgi-coverage/` and confirm `ci-run.json` has the same run ID,
   attempt, and commit. Leave `coverage-report.json` and its context unchanged.
2. Create the review projection:

   ```sh
   python scripts/coverage_mcp_handoff.py project \
     --report target/asgi-coverage/coverage-report.json \
     --output target/asgi-coverage-review/coverage-mcp-projection.json
   ```

   Query `coverage_gaps` for
   `target/asgi-coverage-review/coverage-mcp-projection.json` with
   `metric: "regions"`, then `metric: "lines"`; use `limit: 15`, no filters,
   and follow each `next_offset` through its terminal page. Save every request
   with the exact structured response in one JSON array.
3. Open **Actions → Coverage MCP handoff → Run workflow**. Select `main` at
   the same commit as the CI run, provide its run ID and attempt, and provide a
   single-line gzip+base64 encoding of the compact JSON array as
   `receipt_gzip_base64`. For example, save the JSON array to a local file and
   run `gzip -c receipt.json | base64 | tr -d '\n'`. Dispatch it once for that
   CI attempt. The handoff decodes the receipt with a 32 MiB output limit and
   writes the page array into the ignored review directory.

The handoff rejects stale or mismatched CI runs and artifacts, incomplete page
chains, altered projections, source/build mismatches, failed tests, and any
missing region or line. It leaves the raw CI artifact unchanged and uploads
the projection, derived reviewed report, page receipt, and digest manifest.
The release candidate selects exactly one successful handoff for its commit
and CI attempt, checks the raw file hashes against the original CI artifact,
rebuilds the projection from that report, and validates both metric page
chains offline. If `main` moves before the handoff is dispatched, use a
successful CI run for the new commit and query its projection; do not reuse
pages from the previous source.

The handoff artifact contains generated reports, profiles, and logs. Keep them
in the Actions artifact; do not commit them to the repository.

## Measure an incremental case or profile

Add an input-only case to the indexed manifest, validate it with the parity
contract loader, and select the changed case or its profile against the
existing instrumented source/build. `--case-id` and `--profile` are repeatable;
profiles scope ASGI cases, while native contracts are selected with
`--case-id native:<id>`:

```sh
UV_PROJECT_ENVIRONMENT=target/coverage-oracle uv sync --python 3.12 --locked \
  --only-group benchmark --only-group uvicorn-oracle --no-install-project
uv run --python 3.12 --locked --group benchmark python scripts/run_unified_coverage.py \
  --oracle-python target/coverage-oracle/bin/python \
  --output build/asgi-coverage/incremental/coverage-report.json \
  --artifacts-dir build/asgi-coverage/incremental/artifacts \
  --profile http3 --matrix-repeats 0
```

Use `--case-id CASE_ID --matrix-repeats 0` for a single case, or repeat
`--case-id` to select a small batch. Use `--profile http1`, `http2`, `http3`,
`cli`, or `python-api` to select a profile group. Add `--skip-build` only when
the installed instrumented extension was built from the same source state.
Use this incremental path after a related source or input change, and reuse
the same-source measurement when those inputs and the build have not changed.
Full acceptance still requires a complete exact-source matrix.

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

## Lifespan mode coverage progress (2026-10-26)

Added two input-only direct `uvicorn_rs.Server` parity cases to cover the
documented boolean lifespan option and invalid mode rejection:

- `python-api.direct-server-lifespan-boolean-false` maps to Uvicorn's
  `lifespan="off"`. Its selected run also exercises a pre-bound listener,
  request-limit jitter, and `cancel_startup()` after readiness.
- `python-api.direct-server-rejects-invalid-lifespan-mode` compares rejection
  of an unsupported string through each public server API.

Both cases passed once with complete per-case attribution and no
infrastructure failures in `selected-lifespan-mode-final.json` (run
`537ee5e3a2104056b86e2f654ddc2540`, report SHA-256
`ca1778d5d088dfa49f866057c35262f2760afd577543789ad4f28b651b749620`). The
boolean case used the pre-bound listener and jitter inputs. This is a
selected-case measurement, not a complete-suite receipt. It uses instrumented
extension SHA-256
`696971351481671c4ba18b8bc92b87768e4c28ee6942177448c49753d1617c18` and
source/input identity SHA-256
`ed179b84d8d4f60d7fa09ff9eaebc970f6f699488a6ae1af50b416bedf3c3ee3`.

The earlier one-pass full diagnostic `coverage-current-source-once.json` (run
`4d45912cb1084ed8b4e1d08a22a21b53`, report SHA-256
`6b84d61748bce0c41d2510b32cf2e9f46e5423868bb33187d6354ad15d250063`) passed
1,112/1,112 cases and attributed 1,058/1,058 source-bound cases, with no case
or infrastructure failures. It measured 12,951/13,098 regions and
9,615/9,703 lines. It predates these two inputs and is diagnostic only; it had
zero complete verification repeats and no accepted independent Coverage-MCP
receipt. The complete exact-current-source, three-repeat coverage gate remains
open.

### Startup failure waiter coverage (2026-10-26)

Added the input-only case `python-api.concurrent-startup-failure-waiter`. It
holds lifespan startup open while the public `wait_startup_failed()` call is
waiting, then sends `lifespan.startup.failed`; both implementations report a
failed, not-started server. The target also drops a standalone native
`ServerControl` while its waiter is pending and verifies that the closed
watch channel returns `false`.

The selected case passed once with complete attribution and no infrastructure
failures: run `828b69bdd3bd4512956f19f9a59e8ded`, report
`concurrent-startup-failure-waiter-final.json`, SHA-256
`bf20aa4d7e00d5f07e7d5e7424dfd57a1c909db8714647347c31d7b10f395bc8`. It uses
`src/lib.rs` SHA-256
`f59da9165e78423e0b4699cef2697c6f063e2c18f47591601662976cc285723f` and
instrumented extension SHA-256
`696971351481671c4ba18b8bc92b87768e4c28ee6942177448c49753d1617c18`.
Coverage-MCP reports two remaining spans for this method in the selected
report: the generated `#[pymethods]` wrapper span and the `Stopped` match arm.
The report is selected-case evidence, so other cases may cover the latter.
Incremental comparison against the earlier one-pass full diagnostic was
rejected because that baseline has failed verification status; no union or
marginal gain is claimed. Full exact-source coverage, three complete repeats,
and the independent review remain open.

### Startup cancellation before listener bind (2026-10-26)

Added the input-only case `python-api.cancel-startup-before-listener-and-shutdown-lifespan`. It holds ASGI lifespan startup, requests shutdown before the listener binds, then releases startup and checks that `serve()` finishes without cancellation and emits both startup and shutdown lifecycle events. The parity comparison checks the shared Uvicorn contract; the target-specific requirement verifies that `uvicorn-rs` remains unstarted through shutdown.

The selected case passed once with complete attribution and no infrastructure failures: run `f72433fb3f314f5882fdf4d43f36f264`; report `startup-cancel-before-listener-after-fix.json`, SHA-256 `cfa913db89dfd8f44a836565d93429baf84dceda6361d558ee1bf836b9d9c633`. It binds to dirty source revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source/input identity SHA-256 `86d0b9a45d7df461162f27d9b1058cf212eb18b97269ef1836e40b3173fd6d60`, and instrumented extension SHA-256 `696971351481671c4ba18b8bc92b87768e4c28ee6942177448c49753d1617c18`. This is selected-case evidence only; full exact-source coverage, three complete repeats, and accepted independent Coverage-MCP review remain open.

### Listener setup failure runs lifespan shutdown (2026-10-26)

Added the input-only case `python-api.server-startup-bind-failure-shuts-down-lifespan`. It runs a lifespan-enabled server against the deterministic invalid-host startup failure and compares startup/shutdown events, the unstarted state, and the completed failing serve task against Uvicorn 0.54.0.

The selected case passed once with complete attribution and no infrastructure failures: run `0f3e0168ef6d4c03a799b856558d3968`; report `startup-bind-failure-lifespan-final.json`, SHA-256 `c235f64b236b9a540e3c9fdef88b726ee130e1734eb545755e4caf2ec0fc07c8`. Both implementations observed `lifespan.startup` followed by `lifespan.shutdown`, `server_started=false`, and a finished serve task. It binds to dirty source revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source/input identity SHA-256 `853232ba6cd92fadbf95b6025240c48f78582ca9cf8b2401e42710238f25f77f`, and instrumented extension SHA-256 `696971351481671c4ba18b8bc92b87768e4c28ee6942177448c49753d1617c18`. This remains selected-case evidence; the exact-source full coverage gate and independent review remain open.

### Native WebSocket selected group (2026-10-27)

After the WebSocket handshake fault case changed `websocket.rs` and the native
manifest, ran the affected native WebSocket group once: 43/43 selected cases
passed, including all three selected fault contracts, with zero case or
infrastructure failures. The run ID is
`d5309e715482459d9c81cce3d95393bf`; report
`selected-native-websocket-group.json` has SHA-256
`4a0d5de38be7aeb0e8876f59cd3950b5d9ff670f9e438291f8efd99ede41bb7f`.

The report binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`
and source/input digest
`cca93cb5da697e348fba35763d12443e0db8421d9e5b252f6fbfda0599199f40`. The
instrumented extension SHA-256 is
`801fcbf2a23917639db023a9fa9931aebe27f37a8a92d300461d21ad342b34aa` and the
native runner SHA-256 is
`a5066f23ecd68a2d8628c3a24464edd0fb59e6c690ce5169ff5f1a3bbc877731`. This
selected subset attributes 2,689/13,127 regions and 2,221/9,722 lines; it is
not a full-coverage or three-repeat receipt. It uses the same source/input
digest as the separately selected extension-negotiation fault case, but a
different extension build, so the two selected reports are not merged. The
complete exact-source matrix and independent Coverage-MCP review remain open.

### Native WebSocket handler error observation (2026-10-27)

Added the input-only case
`http1.native-websocket-handler-error-is-observed`. The client completes a
WebSocket handshake, sends a text message, and receives no application frame
after the handler returns an error. The configured server error observer must
report the error in the connection phase with its source chain intact. The
selected case passed 1/1 with complete case attribution, zero failures, and
zero retries: run `242a64eb1bcc4ab1bd1056ad79db87b5`, report
`selected-websocket-handler-error.json`, SHA-256
`57d0b851255411b79c94609187f5176fa67cf225c6332b8448ace46316b76d1a`.

It binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source/input digest
`a954d9fd36940de01ff9fe435eb99c8a01dd9669f9b0fc5a804659223966a52a`, and
instrumented extension SHA-256
`48242e1f6ef008da2f9274e9078e3eff2badd88c961a884234e1def229e4cf63`. The
single-case report attributes 1,383/13,127 regions and 1,207/9,722 lines; it
does not certify the full matrix. Complete exact-source coverage, all three
matrix repeats, and independent Coverage-MCP review remain open.

### Direct-server invalid lifespan type (2026-10-27)

Added input-only case `python-api.direct-server-rejects-invalid-lifespan-type`
to exercise a value that is neither a string nor a boolean. The selected
parity and unified coverage run both passed 1/1; case attribution is complete
with zero failures, infrastructure retries, or matrix repeats. This case
hits the final `LifespanMode::from_python` rejection path. Unified run
`918bdda1ce4046439d29a749e3cc9425`; report
`selected-lifespan-invalid-type-coverage.json`, SHA-256
`f0f94f5924637bb57b85388dafbbe41c6e604989702d1ada392c8b25512f0a4b`.

The report binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source/input digest
`1a4707ad26214c92eb700e2c9e1d09017c5b61cbcb1cd03df2cb090f9419c508`, and
instrumented extension SHA-256
`7ca14686782476576e48ac44ae5197814d9f1fe910b4831782f0569a6f3f8bb7`. The
case attributes 73 regions. This is selected-case evidence only; full
exact-source coverage, three matrix repeats, and accepted independent
Coverage-MCP review remain open.

### Direct-server boolean-enabled lifespan (2026-10-27)

Added input-only case `python-api.direct-server-lifespan-boolean-true` to cover
the direct Python `Server(lifespan=True)` conversion. The target's boolean
`True` maps to Uvicorn's `"auto"` mode; both implementations completed startup
and shutdown with a clean exit. The selected parity and unified coverage run
passed 1/1 with complete attribution, no infrastructure failures, no retries,
and no matrix repeats. The case covers the `Auto` branch in
`LifespanMode::from_python` (`src/lib.rs:3315`).

The report is
`target/asgi-coverage/selected-lifespan-boolean-true-20261027-attempt2.json`
(run `4013d123f2684dcfa9a730c1942fbd5f`, report SHA-256
`33295be123b567b88ace649213f0f60c03c0ed2b078fce0efb4a91f7eef73bc3`), bound
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source digest
`2ada60f740dfe5fb8955b67171ee437c64810af7faf8814135e9fc39da58b009`,
`src/lib.rs` SHA-256
`53abec96793f977e9587ebc1011c864b556141267a9e90f4e56ec19b5540b281`, and
instrumented extension SHA-256
`597d1887f68bab9a0bbd3c58ab03ec0a3d44b51360bc62ba7558c18f9470a87f`. This is
selected-case evidence only; it does not refresh full-source coverage, satisfy
the three-repeat gate, or provide an independent Coverage-MCP receipt.

### Module-CLI concurrency-limit parity (2026-10-27)

Added input-only case
`python-api.module-cli-applies-concurrency-limit` to verify that
`--limit-concurrency 1` reaches the server through the module CLI. Uvicorn
0.54.0 and the target both return HTTP 503 for the first request, emit the
concurrency-limit warning, and exit cleanly after SIGINT. The selected parity
and unified coverage run passed 1/1 with complete attribution, no
infrastructure failures, retries, or verification repeats. The selected case
attributes 2,054 regions.

The report is
`target/asgi-coverage/selected-cli-concurrency-limit-20261027.json` (run
`b616dda2b87d45bd985423b3b53b6904`, report SHA-256
`1b6471d77384f59a4417c1ac33c051f2814834ae8a7a6329d0584fa8fe72d2b0`), bound
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source digest
`02f8393bec6cbe624b5afc749032609692befcfef4253c4f5cdbc7552c49281d`,
`src/lib.rs` SHA-256
`53abec96793f977e9587ebc1011c864b556141267a9e90f4e56ec19b5540b281`, and
instrumented extension SHA-256
`d1cdd7955095a0d61c85412d1e3c41aaebd93904a0558136c5f26bc916f94657`. This is
selected-case evidence only; the full coverage gate, three repeats, and
independent Coverage-MCP review remain open.

### Non-UTF-8 client CA startup rejection (2026-10-27)

Added input-only case
`python-api.config-server-rejects-non-utf8-client-ca-file`. It gives both
implementations a CA file containing non-UTF-8 bytes and requires TLS server
configuration to fail before serving. The probe keeps its own client trust
anchor valid so the observation measures server startup rather than client
context setup.

The selected unified run passed 1/1 with complete attribution, zero case or
infrastructure failures, and zero retries: run
`7d3203c103644d7c9341fa8ebfb26e9d`. Report SHA-256:
`b98e5dc958db8020f2c5a3a2721cdc7034478cf98931605ace5f293704f47df8`; source
and input identity SHA-256:
`8d22380c11db8c26087357651d69195523ed728a8be9da7807dc070e7ec68a52`; native
extension SHA-256:
`7ca14686782476576e48ac44ae5197814d9f1fe910b4831782f0569a6f3f8bb7`. The
attribution receipt confirms the case covered the non-UTF-8 conversion branch
in `load_client_cert_verifier` (`src/lib.rs:5703`). This is selected-case
evidence only; the full-source coverage gate and independent Coverage-MCP
review remain open.

### Infallible compressed WebSocket close conversion (2026-10-27)

The current-source draft report identified an uncovered error-propagation
region in `WebSocketSession::close` for Yawc sessions. That call can only pass
`WebSocketMessage::Close(frame)` to `yawc_message_to_frame`; the converter can
fail only for `WebSocketMessage::Frame`, which is unreachable at this call
site. The close conversion now uses the infallible `yawc_close_frame` helper,
shared with the general message converter. This removes the impossible error
path without changing WebSocket framing or raw-frame send errors.

The existing target-contract case
`http1.native-websocket-permessage-deflate-close-without-code` passed 1/1 with
complete attribution, no failures or infrastructure retries, and no matrix
repeats. Unified run `5d3e8813b01546f081bc23934cae8c16`; report
`coverage-yawc-close-infallible-20261027.json`, SHA-256
`6f39f3d47ee2cfb6cbf120ecdea3057dcbd304701a0214567d3eba9e7179b78a`. It binds
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source/input
identity SHA-256 `6a0f7332963933a4a9057d751ab71dcbbe9ff0d2e63cb9ef2050a7c14b649feb`,
`crates/uvicorn-rs/src/websocket.rs` SHA-256
`aa9a4dfe60eff4da017eec29c5b78da3a19dfe7fffa72b94ec137b9b775e6e35`, and
instrumented extension SHA-256
`a6119a5e5e782f29f548c9623e094268aa7296288163121d235ef6fbc20f31cb`. The
selected report attributes 1,677 regions to this case and contains no uncovered
spans in the changed close path. Full exact-source coverage, three complete
matrix repeats, and accepted independent Coverage-MCP review remain open.

### Accepted Yawc session setup error contracts (2026-10-27)

Added two target-only fault contracts after a valid extension-bearing WebSocket
handshake. One injects a Yawc session-construction error and verifies that the
adapter converts and reports it through the HTTP/1 connection observer. The
other injects a non-UTF-8 negotiated-extension value after response generation
to exercise the `HeaderValue::to_str` error conversion. Both cases verify the
101 handshake, the observed server error, and listener recovery.

Both cases passed in one selected run with complete attribution, no case or
infrastructure failures, and zero matrix repeats. The run is
`3edff43f3989446184c83ab8e5662ae9`; report
`target/asgi-coverage/coverage-yawc-session-errors-final-20261027.json`,
SHA-256 `866b1d8658a1022ef72fbc7c90c4db4bbb7a6a48b886bdb4b971cdc79ff22b91`.
It binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
digest `82e049f06c5309c02f47dc5e2581242b80081bd88067fdcff9dcdc966c27f3bd`,
native manifest SHA-256
`12a38ff0ca7b49109b30d7f1730eaee9ada586d79ec5c81b961d3a32e42569ab`,
`crates/uvicorn-rs/src/websocket.rs` SHA-256
`a25ebe8f45639e14530a90c02170c94474f400261213ac82d497fec120fff47a`, and
instrumented extension SHA-256
`d363ed1410bca7af9805150b5e6657b77308165a2b5ce59b9eda5631e757c7d8`.
Attribution covers 1,621 regions across the two selected cases. This report is
still an incomplete selected subset; its 13,241-region denominator and missing
regions do not represent a full current-source run. The full matrix, three
complete repeats, and accepted zero-gap Coverage-MCP review remain open.

### Selected Unix-socket permission error path (2026-10-27)

Added the target-only case
`python-api.fault.uds-permissions-error-propagates-and-cleans-lifespan` to
inject a deterministic `set_permissions` error in coverage builds. It verifies
that startup fails before the server starts, the serve task finishes with the
error, and lifespan startup/shutdown cleanup completes. The first selected
attempt exposed the harness applying the ordinary successful-startup
expectations to a fault case; the fault matcher was corrected, then the case
passed 1/1 with no case or infrastructure failures.

The selected report is
`target/asgi-coverage/coverage-uds-permissions-error-20261027.json`, run
`69e47921a249435c80924c0fcc4daf25`, case run
`a8be6ebb9b994605a64eede654e3c49f`, report SHA-256
`9b4537f6edfa72a3a11f5968ab4360c82926ecf9e59326b7fdab3391eb13d970`, source
SHA-256 `76e57f7d810c15e58d3d9cdbf2aca67db28f5d781992a4cc675d3b63c39ec928`,
and instrumented extension SHA-256
`8ebf16713c705f88f179b7dac26bedd71db606c30daf3c9392546f06548634d7`. The
report's recorded source files match the current checkout. Coverage-MCP
matched this selected report's source receipt and reported tests passed; a
focused query for `bind_unix_listener` at `src/lib.rs:6393` returned no gap
groups. This selected subset's 957/13,265 regions and 724/9,843 lines are not
aggregate coverage evidence. The full-source gate, three complete passes, and
accepted independent zero-gap review remain open.
