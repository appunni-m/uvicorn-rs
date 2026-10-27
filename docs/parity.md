# ASGI server parity suite

> **Evidence path note:** Paths under `benchmarks/results/` identify local-only receipts excluded from Git. They are available only in a maintainer working copy when the referenced files are present; hosted artifacts are linked directly where available.

The last fully successful hosted acceptance receipt recorded here is CI run
[39107767728](https://github.com/appunni-m/uvicorn-rs/actions/runs/39107767728)
on commit `dd6ed00f551c02196544ae9452c7b0747452a422`. Its unified matrix
passed 757 cases (543 Python ASGI and 214 Python-free Rust), attribution, and
three complete repeats of each matrix with zero failures, infrastructure
failures, retries, or unrun cases. It measured 9,166/9,166 executable source
regions and 6,768/6,768 normalized physical executable lines. The same run
passed 251/251 installed-wheel public inputs and the native FastAPI-RS →
Starlette-RS → Uvicorn-RS composition inputs. This is historical evidence, not
the current release gate.

At the time this evidence was checked, the code-bearing `main` revision was
`e6856a43f59af5ede1b0311f535272bffade782f`. Its Documentation workflow
[39558584892](https://github.com/appunni-m/uvicorn-rs/actions/runs/39558584892)
passed; as of 2026-10-21 07:01 UTC, push CI
[39558584762](https://github.com/appunni-m/uvicorn-rs/actions/runs/39558584762)
and the ASGI performance matrix
[39558584761](https://github.com/appunni-m/uvicorn-rs/actions/runs/39558584761)
were queued. The most recent completed push-CI run before that revision,
[39553904053](https://github.com/appunni-m/uvicorn-rs/actions/runs/39553904053)
on `e996b96bb`, failed. At that timestamp, the recorded code-bearing revision
had no completed hosted CI or performance result. The hosted Coverage-MCP
status for the historical
receipt is `awaiting_query`; see the
[coverage evidence](coverage.md#current-unified-coverage-status-2026-10-18).

### Focused WSGI POST request-body parity (2026-10-28)

The cases python-api.run-serves-wsgi-post-body and
python-api.module-cli-serves-wsgi-post-body send the finite body wsgi-body-parity
through uvicorn.run() and python -m uvicorn, respectively. Uvicorn 0.54.0 and
uvicorn-rs both return HTTP 200 with the identical response body, including
request-body=wsgi-body-parity, then exit cleanly after SIGINT. Each passed 1/1
on macOS 15.7.7 ARM64 with CPython 3.12.13. The uvicorn.run() receipt is run
209aa53eba3047a0b115fac742524809 (report SHA-256
e7e9a7d3e965252d1f5dbdfcf2a8a3bf3784ebb7d9b13d174e781197f7d1c1a2; Python API
input SHA-256 778b2da53c3c063de19e2c3c167c82785d244bb4c952dea22db519015bab203c).
The module-CLI receipt is run 9ed791ef66cf48388f597003f0a9832b (report SHA-256
d0bcb0afc8cffedbbbfdd2f8996f3545209baa995f2a83c8dbaf085aee74dc32; Python API
input SHA-256 33f011f2b7a85f00ab0cbc8a21ffe16af47476ca4e56b245fedd9c6711fa0f1e).
Both bind to source SHA-256
77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9.

These are local dirty-worktree receipts; hosted CI #435 predates both inputs.
The module-CLI case extends entry-point coverage, while both cases exercise one
finite buffered body. They do not establish streaming uploads, chunked requests,
large bodies, malformed length handling, response streaming, or cross-platform
behavior.

### WSGI chunked transfer-body parity (2026-10-28)

The cases `python-api.run-serves-wsgi-chunked-post-body` and
`python-api.module-cli-serves-wsgi-chunked-post-body` send a POST with
`Transfer-Encoding: chunked` through `uvicorn.run()` and `python -m uvicorn`.
Both implementations return HTTP 200 with identical response bytes including
`request-body=chunked-body`, then exit cleanly after SIGINT. The two selected
cases passed 2/2 on macOS 15.7.7 ARM64 / CPython 3.12.13.

Run `151b22b1467f4970ba0c0fe9f3af5041`; report
`target/kata-progress/python-api-wsgi-chunked-20261028.json`, SHA-256
`b36169be3ccbb62999c2714e531d7217b1be2a19841d25042ba39fb4f678b662`.
It binds Python API input@42 SHA-256
`2cf7c29fc339f412b54754fd73159f2afee47d6f94ee5b775726ca5e3d8ec791`, target
revision `9b4fc703b53b74cd653b441d94d084159c3613c9` with a dirty worktree,
source SHA-256 `77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9`,
runner SHA-256 `e0590361521ddc53c5a1bb6762ef616e90c5750a851d4a9ac642e23247185e79`,
and Python API probe SHA-256
`7b0b9306fa230513549c68f975779723299bf894fec52f903a7930d292156744`.
Each request body uses one transfer-encoding data chunk. That receipt does not
establish multi-chunk bodies, large bodies, malformed lengths, response
streaming, or cross-platform behavior.

### WSGI multi-chunk transfer-body parity (2026-10-28)

The cases `python-api.run-serves-wsgi-multi-chunk-post-body` and
`python-api.module-cli-serves-wsgi-multi-chunk-post-body` send a POST as two
separate transfer-encoding data chunks through `uvicorn.run()` and
`python -m uvicorn`. Together with the two one-chunk cases above, all four
selected cases pass. Each implementation returns HTTP 200 with identical
response bytes including `request-body=chunked-wsgi-body`, then exits cleanly
after SIGINT. The four-case group passed 4/4 on macOS 15.7.7 ARM64 / CPython
3.12.13.

Run `1e07fba3392349d59a05cedf35c7e72f`; report
`target/kata-progress/python-api-wsgi-multichunk-20261028.json`, SHA-256
`8947b843f548d0b4cc75aab38bc12f709a96de30ccf80fac123763b163698966`. It binds
Python API input@43 SHA-256
`b7a0c78400b1f4c83f68c896bc1ab22bf23bad5dff18101d44a632615ae833c0`, target
revision `9b4fc703b53b74cd653b441d94d084159c3613c9` with a dirty worktree,
source SHA-256 `77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9`,
runner SHA-256 `4940a1b12869e87acf651ef4c4e1545a554a9c6148a82efbb3c15da68852fc24`,
and Python API probe SHA-256
`9c3218d757e0bfc80ea0f02bbbb2fc11f8e6a2e7f062013cf4addaa1f3f214c0`.
These cases verify WSGI reads across two transfer chunks, not arbitrary chunk
counts, large uploads, malformed lengths, response streaming, or
cross-platform behavior. Exact-head CI #437 is in progress on commit 9b4fc703b
with input@42; it does not include the local input@43 cases.

## Correctness gate

The behavior gate is the manifest-backed, live source/target matrix, not a unit
test count. The live matrix observes the server boundary by starting real
reference and target server processes and replaying the same indexed network
workflows against each. The `cli` profile runs the same indexed arguments in
separate reference and target processes and compares exit status, stdout, and
stderr byte-for-byte.

For HTTP wire behavior, the applicable IETF specification is authoritative;
ASGI requirements govern the Python application boundary. If a live oracle
observation conflicts with an HTTP RFC or the ASGI specification, preserve the
observed difference as a mismatch and follow the normative requirement. Do not
change the target or expected contract merely to reproduce an oracle quirk.
HTTP/1.1, HTTP/2, and HTTP/3 claims use the applicable
[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html),
[RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html),
[RFC 9113](https://www.rfc-editor.org/rfc/rfc9113.html), and
[RFC 9114](https://www.rfc-editor.org/rfc/rfc9114.html) requirements.

Uvicorn 0.54.0 provides experimental HTTP/2 through `zttp`; the HTTP/2 parity
profile uses that reference with `--http zttp --http2`. A local aggregate run
on macOS ARM64 and CPython 3.12.13 passed all 27 maintained HTTP/2 parity
inputs against Uvicorn 0.54.0 with `zttp` 0.0.34; this is not hosted release
evidence. The previous Hypercorn-based receipts remain historical. The empty
request reset case sends an explicit empty final DATA frame because zttp does
not wake ASGI `receive()` when END_STREAM appears on the initial HEADERS frame;
that alternate encoding is not covered. HTTP/2 response comparisons retain raw
header observations but compare repeated values grouped by field name. They do
not require an order across different field names or compare the
implementation-specific `Server` field. RFC 9110 Section 5.3 makes order
across different field names insignificant while preserving value order for a
repeated name. HTTP/1.1 and HTTP/3 observations keep their declared comparison
fields.

The current input index defines 77 CLI process cases across `python -m uvicorn`
and the installed `uvicorn` command. They cover help and version output,
selected argument errors including the no-argument missing-`APP` diagnostic and
an invalid inherited descriptor, environment precedence, current-directory
console-script import resolution, app loading
with `--app-dir` and `--factory`,
environment-file loading, custom JSON log-config diagnostics, explicit default
runtime options, HTTP and WebSocket selector acceptance, `--ws-max-queue` with
the SansIO selector, unknown-option rejection, limited single-process worker
settings, and startup with `--ws-ping-interval 0` followed by
`--limit-max-requests 0`, plus a selected startup input with both WebSocket
ping interval and timeout set to zero. A historical 38-case snapshot had
passing evidence for source digest
`b34d2cb7e272fa3cb293b6012aaef66f4035da47df0a81cb1677e689feda2a67` and
`cli.json` SHA-256
`bf57f4d6a9ed84490237593e9d719d278ab4eb8bebd751c6d74df23f3ca41b46`: 36
passed in grouped run `294c58a8ab11427995865dc68926cc18` (report
`target/kata-progress/cli-remainder-20261024.json`, SHA-256
`2f0f4f1fd90cd35f13a724025af3fe29b0d1dbf16fc3450fc169d1e912e6d86e`), and
two other cases reused receipts for those same historical digests. At the time
of the one-pass diagnostic, `cli.json` was schema
`uvicorn-rs-parity/input@37` (55 cases; SHA-256
`a670db6808da18b77139b3bc2880a5fd823aadf6c538b1ab63bec54586c5c7c8`). The
current `cli.json` is schema `uvicorn-rs-parity/input@43` (114 cases). It now
includes malformed `UVICORN_INTERFACE`, `UVICORN_LOG_LEVEL`,
`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`, `UVICORN_WS_MAX_SIZE`, and
`UVICORN_WS_PING_TIMEOUT` environment diagnostics and explicit CLI overrides
for each malformed value. It also checks malformed
`UVICORN_LIMIT_MAX_REQUESTS` and `UVICORN_LIMIT_MAX_REQUESTS_JITTER` values and
explicit CLI precedence over each. Three more numeric settings,
`UVICORN_BACKLOG`, `UVICORN_TIMEOUT_KEEP_ALIVE`, and
`UVICORN_TIMEOUT_WORKER_HEALTHCHECK`, have malformed-value and explicit-option
precedence cases. It also checks malformed `UVICORN_WS_MAX_QUEUE`,
`UVICORN_WS_PING_INTERVAL`, and `UVICORN_WS_PER_MESSAGE_DEFLATE` values with
explicit option overrides, plus explicit `--limit-concurrency` precedence over
malformed `UVICORN_LIMIT_CONCURRENCY`. It also compares malformed HTTP,
WebSocket, lifespan, worker-count, and reload-delay environment values with
explicit valid CLI overrides. Four additional cases compare environment and
explicit-option handling for `UVICORN_APP_DIR` and `UVICORN_ENV_FILE`. The
current Python API input is also `input@43`; it includes the host/port
environment listener case, module-CLI concurrency cases for a valid
`UVICORN_LIMIT_CONCURRENCY` value and explicit CLI precedence over valid and
invalid values, and WSGI interface selection and precedence through
`UVICORN_INTERFACE`.
one-pass full unified diagnostic (run `4d45912cb1084ed8b4e1d08a22a21b53`,
report SHA-256
`6b84d61748bce0c41d2510b32cf2e9f46e5423868bb33187d6354ad15d250063`)
includes all 55 CLI inputs, with 55/55 passing. It binds to dirty source
revision `5b1ec29201c963d8590c989b07318bb7366d7922`, has zero complete
verification repeats, and predates the current input inventory.
This is one-pass diagnostic evidence, not a full release-ready profile.
The new `cli.websocket-zero-ping-timeout-is-accepted` input passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. The selected valid graceful-shutdown option case also passes 1/1; it only verifies startup/exit acceptance, not in-flight request cancellation. See [the maintainer receipt](maintainers/uvicorn-0.54.0-contract.md#focused-module-cli-graceful-shutdown-settings-2026-10-27). It starts the module
CLI with `--ws-ping-interval 0` and `--ws-ping-timeout 0`; it does not establish
active WebSocket Ping/Pong behavior. Run
`98338893fcab4a2fbc3113859ea3c311`; receipt
`target/kata-progress/cli-ws-ping-timeout-zero-20261027.json`, SHA-256
`c0cc541d55b801745c5ad4fe543fd619a45ad5eaa1c4195fffaf34e9e1705eec`. The
receipt binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256
`3c6654dd24f30e6b838232518a5c8967c73952a1e722a6ec4d6725568f28fe0d`, native
extension SHA-256
`d1cdd7955095a0d61c85412d1e3c41aaebd93904a0558136c5f26bc916f94657`, and
the then-current `cli.json` SHA-256
`f72fd42df29280ca29161cd312ac3ebb212c99d034cd0698f9007a1d73869a46`. This
selected process check adds no full-profile or release-ready evidence.
`cli.timeout-graceful-shutdown-valid-environment-value-exits-after-startup`
also passes 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
3.12.13. It sets `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=1` without a CLI override
and exits after startup; this checks accepted configuration only, not timeout
cancellation of an in-flight request. Run
`24c550a6a3464489a859b501faf2f6a2`; receipt
`target/kata-progress/9kbx-graceful-timeout-valid-env-20261027.json`, SHA-256
`701091163ad0db64e0b62c3536c5663fb526de961d1249bc4c2a481b930ade26`. The
receipt binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
native extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
the then-current 58-case `cli.json` SHA-256
`bc99598c6cb980a26f58b05746fd47b32e5367f8092ad9efe12e50cf5a32af3f`. This
adds one selected input, not a full profile or release-ready evidence.
`cli.invalid-host-env-is-rejected` passes 1/1 against Uvicorn 0.54.0 on
macOS 15.7.7 ARM64 / CPython 3.12.13: without `--host`, both processes exit
3 with empty stdout/stderr when `UVICORN_HOST=invalid host`. Run
`d8b06f9cb7c44a1d8c9a7c7147c3773a`; receipt
`target/kata-progress/9kbx-invalid-host-env-20261027.json`, SHA-256
`1e0646131004fcaefecf1bf2456620522c7284b090530fb5d12b5af4cc5812a2`. It
binds dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `e69c91726396071cff19ffccf124992bf75c30e63ea233dffbc1c233bc06696a`,
extension SHA-256
`4c84221e0a04be80ba00ce056352cace1d72e3dac7572261121bcf577b543074`, and
the current `cli.json` SHA-256 above. This is one selected environment-error
case, not full CLI parity.
`cli.invalid-timeout-graceful-shutdown-argument-is-rejected` was refreshed once
on the newer dirty source and harness on 2026-10-26. It passed against Uvicorn
0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run
`46b0158ba47f4cb39036f76d47ca2c3f`; report
`target/asgi-parity/cli-invalid-timeout-graceful-shutdown-argument-one-case.json`,
SHA-256 `02e8b65d37e4796075ba8b22083309153cdeb6973a4df3e1253e702cf94ba8be`).
The target binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`,
source digest `7751c5581b0bb2b28a2ebe2df46d5c715088323ccec17b0d88b2fcda912a403d`,
and extension SHA-256 `07807ccd278f6b5cfb23d311c1751b18edfbc5705011937a822e8226956254fd`.
The CLI input hash is unchanged from the earlier selected receipt; the source,
extension, parity runner, and probe fingerprints changed. This refresh validates
the newer dirty source and harness, but adds no unique case coverage and does not
refresh the complete CLI or release gate. The new
`cli.explicit-host-over-invalid-env-starts-server` case passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run
`e65639c480814a329520c7a59a4acd81`; receipt
`target/kata-progress/9kbx-explicit-host-env-20261025.json`, SHA-256
`8ba7b4b25abca16131e99716fff8aaf98cf0f3d36d0d80d7d770f684136bb3fc`; dirty
source SHA-256
`99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`). It
verifies explicit `--host 127.0.0.1` takes precedence over malformed
`UVICORN_HOST` through listener startup. This is one selected case, not a full
CLI profile. The new
`cli.uds-startup-and-clean-exit` case passed 1/1 against Uvicorn 0.54.0 on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1 (run
`71ea692cb1b2432c8235cfe18a2d2ed2`, receipt
`target/kata-progress/9kbx-uds-20261025.json`, SHA-256
`473734af0cffd2d63223c69a2481e12767ab03b8138ed9d7902e54cc65611eea`, source
digest `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`,
CLI input SHA-256
`9bfd77f7f332c584df2441e9c7024cb29a44c8cc42960da29c705a7a8b1a690c`). Both
processes bound the Unix socket, exited 0, and removed the socket; this checks
startup and cleanup without making a request. Separate Python API cases check
UDS requests through the module CLI and `Config`/`Server`. The new
`cli.invalid-file-descriptor-is-rejected` case passed 1/1 against Uvicorn 0.54.0
on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1 (run
`b252f4db99c042d7a941e6ffb84c7c48`, receipt
`target/kata-progress/9kbx-invalid-fd-20261025.json`, SHA-256
`3b062594123016d030b947fc4120fc49c0e005d49e6852ce6687760483f166eb`, source
digest `99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`,
native extension SHA-256
`1666dd0b1e40d046f9ee6d4f011ae940cec6dfa007efcc7f0c7d81c68d865d34`). Both
processes exited 1 with the same bad-file-descriptor outcome. That receipt is
bound to the previous 52-case input digest `897b6b4a4842e8e051c5bcf8985eac33159af4ac183c861038197971f62c691e`; it does not bind the new current matrix. Both are selected dirty-source results and do not establish clean release readiness. The case
`cli.invalid-limit-concurrency-env-is-rejected` passed 1/1 against Uvicorn
0.54.0 on macOS ARM64 / CPython 3.12.13 (run
`2c2fee8ea606497f9fbad3dfc8c0005b`, receipt
`target/kata-progress/cli-invalid-limit-concurrency-env-20261024.json`, SHA-256
`df3c7746ab0bee5c66accf3a9f42a9a86977ada25aadd0d0879a3c33d1d1804c`, source
digest `b34d2cb7e272fa3cb293b6012aaef66f4035da47df0a81cb1677e689feda2a67`,
then-current `cli.json` SHA-256
`331eaa5f201437d6b3903afa2ccdf96fd94a9953720bcae0ca5a30cd9b6ed9a4`). This
local run used Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13. The
`cli.invalid-log-level-is-rejected` case passed 1/1 against Uvicorn 0.54.0
on macOS ARM64 / CPython 3.12.13 (run
`6da47f92baba4d709168f3ed5b953587`, receipt
`target/kata-progress/9kbx-invalid-log-level-20261024.json`, SHA-256
`30a0ecc9ca03f1179b36c801ca6830b12634006e8b29b463fdc80d5080940ae3`, source
digest `52149ee124968d443ccc0372c7c5212199b7feac628abab6cfabf7b21f135dac`,
CLI input SHA-256
`4017f07a931c806ca11870a6d4aa329053b90d19fb7a6a3eb3c6b4f59f53b981`). Both
servers exited 2 and emitted identical validation diagnostics. Four additional
inputs cover invalid `--interface`, `--lifespan`, `--http`, and `--ws` values.
The interface and lifespan cases passed in run
`3fa98416e997426388c6cc53ee0cb364`; its HTTP and WebSocket cases exposed an
early native-runtime guard mismatch. After routing unknown protocol selectors
through Uvicorn-style import resolution, only those two affected cases were
rerun; both passed in run `d7efd11bd64d4caabba720ff8e180202` (receipt
`target/kata-progress/9kbx-invalid-selectors-20261024-after-fix.json`,
SHA-256 `183c6c72b874a5b31eb07ea1b76fe2838708f766a228916f1a9ff4d33541fb98`,
source digest `5cfb5665aad28e09f3dd1e1bf1b4331b579c5aea9cd4936822a5e51d5bd97b1e`,
CLI input SHA-256
`f2db8bdafe0b296f6197780f7288da2739f3f37e38acef92f20a1672c2eec806`). No
unchanged case was replayed. A new `cli.explicit-port-over-invalid-env-starts-server`
input passes 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13:
both CLI processes accept explicit `--port 0` despite malformed
`UVICORN_PORT`, then exit 0 after `--limit-max-requests 0` triggers startup
shutdown. Run `188a09864fa34689bd4d65008b9b9cff`; receipt
`target/kata-progress/9kbx-explicit-port-over-invalid-env-starts-server-20261024.json`,
SHA-256 `af93265d6d50c55d9a351295e7fa08127f7307f404b822f85b8db6938e909fbf`,
runtime source digest
`57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`, native
extension SHA-256
`c0e18852813e9f3755466e6cc6a3bebbe2f67d74a73e9846736e617f9aef2d45`, and
CLI input SHA-256
`34b092559c9919b6dd3f0e0ce6702f47f372477f5e3832a39e5af1d2acb9550b`. The
new `cli.env-file-value-reaches-application-factory` case removes the process
sentinel and confirms that the value from the configured env file reaches the
factory. It passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython
3.12.13; both processes exited 3 with identical output showing
`loaded-from-env-file` (run `6c2e18e456194eceb8aa897b2d354f3d`, receipt
`target/kata-progress/9kbx-envfile-value-reaches-application-factory-20261024.json`,
SHA-256 `94fee7a0e75237444da4f71e9e9f0c2d5a2087dbd0ef3ee9530168b3fab77035`,
source digest `57ed2f030ad86d3088dde78277cfbef472aa1f04a72d544465a57e3ce4d35197`,
native extension SHA-256
`c0e18852813e9f3755466e6cc6a3bebbe2f67d74a73e9846736e617f9aef2d45`). The
existing `cli.explicit-default-runtime-options-are-accepted` case now also passes
`--http h11 --h11-max-incomplete-event-size 131072`. This modified case alone
passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13;
both module processes exited 0 with empty output (run
`232ddb70e3bf4ac8a55196fe6a11116c`, receipt
`target/kata-progress/9kbx-h11-cli-selected-20261025.json`, SHA-256
`5399dab777be38eefd8d161722912b6ab5cbfc13b29e9771645f1163bef39855`, source
digest `4f2e7f1cf45e9aa3f7a08514abe0f47c074e40f865cccc6d21734eeb7d0f6dd3`,
native extension SHA-256
`389d2349f493a628f5b336b89ca80ee450c27a87f5ca9be44bf1dd1afbe36ff3`, CLI
input SHA-256
`38f88cd81cbf74b0f54358f3c29355b3c22734ea7165e95eb13d8e6775d4e12e`). This
confirms CLI acceptance of the configured h11 size; the separate HTTP/1 case
`http1.h11-max-incomplete-event-size-allows-expanded-header` checks its parser
effect. The target was dirty at base revision
`86e72e181d00feca1b4db7f30377d5d9d4345b83`; this selected case is not clean
release evidence. The new `cli.console-h11-and-tls-settings-start-server` case
exercises the installed console entry point with the h11 size option, an
encrypted PKCS#8 key, required client authentication and CA roots, and the
selected TLS cipher suite. The modified case passed 1/1 against Uvicorn 0.54.0
on macOS 15.7.7 ARM64 / CPython 3.12.13; both processes exited 0 with empty
output (run `fa70ab489c4b49568303a0ee9b02ae9a`, receipt
`target/kata-progress/9kbx-console-h11-client-auth-selected-20261025.json`,
SHA-256 `781e03a4a9fcfc26d8b16aeb705d3e41063f051ffa43d49981a19cf6b139b79b`,
source digest `4f2e7f1cf45e9aa3f7a08514abe0f47c074e40f865cccc6d21734eeb7d0f6dd3`,
native extension SHA-256
`389d2349f493a628f5b336b89ca80ee450c27a87f5ca9be44bf1dd1afbe36ff3`, CLI
input SHA-256
`214b141779bc5672e10cac893be047c18d8749999006bb1a3cbe34b8025709b2`). These
selected cases are not clean release evidence. The
input-only
evidence covers listed cases only; it does not establish every CLI
setting or full worker supervision. The zero-interval case checks option
acceptance and startup shutdown; it does not open a WebSocket or verify ping
suppression on an active session. Two focused cases verify
two-worker module-CLI request and
SIGINT shutdown behavior through explicit worker count and `WEB_CONCURRENCY`;
this does not establish full multi-worker supervision. A separate current-draft
case, `python-api.module-cli-worker-crash-restarts`, forces one worker to exit;
both implementations replace it, serve HTTP 200, and exit cleanly after SIGINT.
It passed 1/1 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run
`1a1342f6938a4a329085587ea9acaf3b`; receipt
`target/kata-progress/dhfq-worker-crash-current-20261025.json`, SHA-256
`f353fd6441f5545614e5918affa24fe3777a22b88f8cf5e1873a30533e90a58d`; source
SHA-256
`99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`). This
single path does not establish restart policy or supervisor-signal parity. One
current-draft case, `python-api.module-cli-two-workers-restart-on-sighup`, sends
SIGHUP to the two-worker parent, and compares the restart events. It passed 1/1
against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 (run
`38f51c8865a5457d836acee3f32820ea`; receipt
`target/kata-progress/dhfq-sighup-restart-current-20261025.json`, SHA-256
`64bfdd665259d95b19060b814ba825de7f24ffb133003288480d4bf8bd2095b1`; source
SHA-256
`99fb03f9b2c03933eab493f3f5f1cdd2596a2f2058f1ef6ed9c408da06390113`). Both
servers returned HTTP 200, exited 0, and did not time out. This is one
POSIX-specific signal path, not full worker or supervisor parity. One separate
Python API input starts `python -m uvicorn --reload`, edits a watched Python module,
verifies the replacement body, and shuts down with SIGINT; it passes locally
against Uvicorn 0.54.0 on macOS ARM64 / CPython 3.12.13 with `--workers 2` set.
It passes both without `watchfiles` (candidate `StatReload` fallback, oracle
watchfiles) and with `watchfiles==1.3.0` installed for both. It also compares
Uvicorn's warning that reload ignores the worker count. Reload filters and
other platforms remain unverified. Inherited-listener support beyond the focused
IPv4 and IPv6 module-CLI cases below, Windows, TLS, HTTP/2 or HTTP/3 over
inherited sockets, execution of every
listed option, and full CLI and Python API parity remain unverified. Five
Direct `Config.load()` behavior is covered by two new invalid protocol
import-string cases plus the existing HTTP/2-with-auto-backend case; all three
passed in one selected Python API run against Uvicorn 0.54.0 on macOS ARM64 /
CPython 3.12.13 (run `d6d68906ebe64c8e997ee9bc4b3b40b3`, receipt
`target/kata-progress/gjpr-config-load-invalid-protocols-20261024.json`,
SHA-256 `1ac9057188a4a673a69a83bd87e8c14a4ffdca5a5e752b1c806ef00acc629b8c`,
source digest `e7d3f0ca2c6d82c31eb675e3090d6ba8a16797a498689077c881b427b6683ecf`,
Python API input SHA-256
`b45b07718600e3d228d7b663cdbf5c4721de632ce73cfec02e3189a4a8d536f8`). The
full Python API profile was not rerun.
Five
inherited TCP-listener inputs pass individually against Uvicorn 0.54.0 on
macOS ARM64 / CPython 3.12.13: module
CLI `--fd`, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and
`Server.run(sockets=[...])` with one and two listeners. The two-listener case
requires successful HTTP responses from both sockets and graceful SIGINT exit.
Two additional module-CLI cases pass for inherited IPv6 listeners with one and
two workers on macOS ARM64 / CPython 3.12.13 (run
`bc282b37f69a46a38e8353a94197e2a7`, report SHA-256
`f55d9d1f8227452b0513446e2b96241fc63277c1f359ca761fb570a0ea94ca0f`). Other
IPv6 API paths, Windows, TLS, and HTTP/2 or HTTP/3 over inherited sockets remain
unverified.

A focused refresh now compares the module-CLI startup socket message for both
inherited IPv4 and IPv6 sockets; the cases pass 2/2 against Uvicorn 0.54.0.
The local dirty-source receipt and its input/source digests are recorded in the
[maintainer evidence map](maintainers/uvicorn-0.54.0-contract.md#inherited-fd-startup-log-parity-2026-10-28).

This follows the fixture-matrix approach used by `image-slash-star`/Pillow-RS,
adapted to a network server. Pillow-RS compares Rust operations with pinned
oracle fixtures; this server compares wire-visible behavior with a live,
version-pinned ASGI server because sockets, protocol state, streaming, and
lifecycle are part of the contract. Inputs contain stimuli only, not expected
responses. The Python contract checks validate the matrix and evidence format;
they are not substitutes for the live behavior comparisons.

The TLS WebSocket scope-close input receives an isolated server lifetime. A
server-initiated WebSocket close followed by an immediate new TLS connection
made transport teardown race with the next independent case on both adapters.
The runner starts a fresh reference and target before this input, so each
recorded result belongs to the case's own live request sequence.

The historical shared-write inventory contains 448 workflows across 70 input files and 61
operations: 213 oracle-parity cases and 235 target-only contracts in the
fault-contract envelope.
Of the latter, 233 select internal/client fault paths and two declare public
header-capacity behavior without native injection. Additions
cover shallow lifespan-state copying without rehashing keys, post-response
application shutdown, inline Python completion callbacks, eager-task
asynchronous cleanup, original task-setup exceptions, fallible native runtime
construction, a real non-DATA HTTP/3 response frame, and TLS response drain
after listener admission closes during shutdown. The existing plaintext/TLS
drain cases also hold an idle connection with the partial HTTP/2 preface `PRI `
and require that connection to close while the active response completes.
The historical shared-write denominator for claims of oracle parity is 213; fault
contracts are target-only. **The historical shared-write source's instrumented full regression,
coverage, and normal-build exclusion verification passed.** All 448 attribution
cases and three complete 448-case repeats pass with zero failures,
infrastructure errors, retries or cases not run. The report records
4,763/4,763 native LLVM regions and 3,360/3,360 lines; unfiltered Coverage-MCP has zero gap groups and a matching, passing
source receipt. The scope is default-feature `src/lib.rs` with `cfg(coverage)`
on macOS ARM64. The same source's normal build independently passes 213/213
public oracle comparisons, every exclusion check and three selected live cases:
one HTTP oracle comparison and both public capacity support contracts.
No unit tests were added; these cases use the same black-box workflow matrix.
The [historical shared-write receipt](coverage.md#historical-full-verification-448-cases-shared-write-source)
preserves matching source/native artifacts and links the normal audit and
defending evidence. That normal build was restored at the time of its audit.

The added `http3.peer-close-h3-no-error` case uses the ordinary
`http3.peer-close` workflow and request field `close_error_code: 256`
(`0x100`). The validator accepts explicit integer u62 wire codes only for
HTTP/3 completed ordinary requests. The workflow verifies exact response
bytes, a healthy request on a fresh connection, a scoped connection-error
diagnostic observation and graceful owned-process exit. It starts fresh
profile processes so earlier connection logs cannot contaminate its diagnostic
window. This field controls the test client; it is not a server CLI option.
Typed `H3_NO_ERROR` (`0x100`) and unknown remote HTTP/3 application close codes
are treated as clean peer closure, as required by
[RFC 9114 section 8](https://www.rfc-editor.org/rfc/rfc9114.html#section-8). The
public close-code cases include zero, reserved GREASE `0x21`, an unknown code
`0x111`, and the maximum u62 value. Registered HTTP/3-family application close
codes `0x33`, `0x101`, and `0x200` retain the error path. These cases verify
the response, a healthy request on a fresh connection, scoped diagnostics, and
graceful process exit. They do not exercise a QUIC transport
`CONNECTION_CLOSE` frame; transport-close behavior remains unverified.

## Current HTTP/3 workflows

`http3.sequential-responses-one-connection` sends 128 POST requests through
one connection and compares every response with live Hypercorn. Its maintained
input explicitly sets `h3_grease: false`. A controlled instrumented comparison
with `http3.peer-close-h3-no-error` passed both cases with GREASE disabled;
the enabled arm timed out receiving headers for the first reference request.
The selected pair also enables full-profile HTTPS readiness after lifespan
startup and public reference ERROR logging. The input controls the client,
defaults to `true` when omitted, and adds no server option. See the
[latest recorded source-bound evidence](coverage.md#current-unified-coverage-status-2026-10-17).

`http3.truncated-data-frame-recovery-after-protocol-error` sends valid request
headers followed by a DATA frame that declares one payload byte, then cleanly
ends the QUIC stream without that byte. RFC 9114 section 7.1 requires this to
produce the `H3_FRAME_ERROR` connection error. The focused live case observed
close code `0x106` (262) from uvicorn-rs and a healthy `200` request on a fresh
connection. Hypercorn 0.18.0 instead passed two empty body messages to the ASGI
app and completed the request. The app events and peer close code remain in the
result for diagnosis; parity compares the fresh-connection response, while the
target requirement enforces the RFC error code. This preserves the normative
behavior when the oracle differs.

The target-only `http3.request-task-drain-on-accept-error` operation starts
`/stream-cancel-until-reset` and receives a real status-200 `first/` body chunk.
After the client barrier and the application's held-response event, the runner
arms the existing `http3.connection.accept-error` point and releases a second
request on that same connection. That request completes the pending unarmed
accept so the following accept can consume the fault. The first stream remains
owned until an actual remote application close is observed.

Its structured contract requires an incomplete first response with exactly
`first/`, a real body-stream error and remote close code `0x102`, consumption of
the point, request-task cancellation diagnostics before the original accept
error, exactly one application cancellation-cleanup event before follow-up,
no panic, and a healthy status-200 fresh request without reset. Actual body,
close code, stream error, trigger error, events and scoped server logs are
retained in `target_observation`. Missing barriers, client timeouts or local
closure fail execution; different actual outcomes fail the contract. The
original `fault.http3.connection-accept-error` first-accept case remains intact.
This new workflow passed its selected instrumented case (1/1), with actual
remote code 258, two cancelled-task join diagnostics before the original accept
error, the held/cancelled application events and a healthy fresh follow-up.
The maintained [coverage summary](coverage.md) records the historical
511-case adapter result and the latest complete-scope 595-case baseline. Those
coverage and case totals are snapshots: the source snapshot for that report had
604 cases. The current manifest has 662 cases, including four native HTTP/1
upgrade-session inputs, five inherited TCP-listener inputs, later CLI
environment-precedence inputs, the Python `Config`/`Server.run()` concurrency
case, the h11 selector checks, forced-color comparisons, and custom
INI/JSON/YAML logging through both Python entry points, including the
`UVICORN_LOG_CONFIG` environment binding, plus module-CLI requests using a
non-default TCP backlog and an HTTP/1 keep-alive timeout, and WSGI GET requests
through both `uvicorn.run()` and the module CLI.
The five inherited TCP-listener cases passed individually against Uvicorn
0.54.0 on macOS ARM64 / CPython 3.12.13. The added multiple-listener case
verifies status 200 from each of two IPv4 sockets and a clean server exit; the
selected results do not represent a full-matrix run. The one-socket cases and
the two-socket case have separate source-bound run reports in the ignored
`target/` directory.
The selected results described here are focused results, not a full-matrix
result. Generated per-run reports remain local and Git-ignored. The case passes
full attribution and all three 511-case repeats; the historical report's
region map records which cases cover the final-drain
spans.
The `stream_reset` field follows the existing `recv_data` error convention;
actual remote application close `0x102`, `body_stream_error`,
`connection_closed` and cleanup establish connection-error termination and
cancellation. They do not independently identify a QUIC `RESET_STREAM` frame.

## Request-body pump ownership

The H1/H2/H3 body pumps are registered with a server-owned `JoinSet`; request
handlers no longer leave these network tasks detached from `Server.serve()`.
Pumps stop on the server token, connection closure or request cancellation, and
completed entries are reaped when later requests are registered. HTTP/1.1
continues draining an upload after the app has returned so request framing can
finish and a keep-alive connection can serve another request. In the existing
PyO3 ASGI path, H2 reset cases cover complete and incomplete uploads, require
`http.disconnect` for the reset request, and keep a multiplexed sibling healthy;
a separate response-stream reset case checks app cancellation. These results do
not establish a native Tower disconnect event: Hyper cancels that request
service future on `RST_STREAM`, and the native service API has no equivalent
per-request signal yet. H3 early response with an open upload, body-stream
error, cancellation and follow-up health use real HTTP/3 client/server traffic
through the PyO3 path; native H3 disconnect delivery remains unverified.

The one-connection HTTP/3 sequence sends 128 one-byte POST requests. Each of
the three complete matrix repeats receives 128/128 target responses matching
the oracle. The instrumented per-case run records
`request-body pumps joined: 128` at shutdown, so the same-connection workload
also has an explicit completed-pump count in the retained
evidence receipt (`benchmarks/results/2026-10-06/request-body-pump-ownership-coverage-473/http3-sequential-pump-repeats.json`).

Target-only synchronized contracts drive deterministic body errors, canceled
and completed `JoinSet` reaping, early-response drain termination, and graceful
or deadline-forced shutdown. They assert `http.disconnect` where the ASGI app
can still receive, exact response outcomes, fault consumption, pump completion
or forced join, no unexpected panic, and healthy follow-up/sibling requests.
These contracts use the existing fault-contract envelope and are reported in
the same unified matrix; they are not oracle-parity cases. The earlier
506-case source passed attribution and all three repeats with 5,532/5,532
regions and 3,971/3,971 lines covered. That record is historical; the current
511-case source receipt is linked above. The normal build for the recorded
506-case source separately passed all 243 public oracle cases. The fixed coverage archive (`benchmarks/results/2026-10-06/request-body-pump-ownership-coverage-473/`)
retains the earlier evidence and its Coverage-MCP receipt.

## Concurrent load and zero-grace shutdown workflows

The current input matrix adds one synchronized slow-reader workload per
protocol category and a zero-grace lifecycle case:

| Case | Stimulus | Required observations |
|---|---|---|
| `http1.concurrent-connections-slow-readers-resource-bound` | 32 concurrent connections; 32 response chunks of 2 KiB each; 100 ms pause before reading; four rounds | All connections reach the barrier; response lengths and SHA-256 match; application work returns to zero; follow-up request is healthy. |
| `http2.concurrent-stream-load-slow-reader-resource-bound` | 32 concurrent streams; 32 response chunks of 2 KiB each; 100 ms pause; four rounds | Same response, task, follow-up, and resource checks over multiplexed HTTP/2 streams. |
| `http3.concurrent-stream-load-slow-reader-resource-bound` | 16 concurrent streams; 64 response chunks of 4 KiB each; 100 ms pause; three rounds | Same checks over HTTP/3. The probe disables its optional GREASE setting for this workload. |
| `websocket.concurrent-sessions-slow-reader-resource-bound` | 16 sessions; 16 echoed messages of 4 KiB each; 100 ms pause; four rounds | Message lengths and SHA-256 match; sessions close cleanly; task and follow-up checks pass. |
| `lifespan.zero-timeout-shutdown-cancels-16-active-streams` | Hold 16 HTTP/1.1 ASGI responses, request SIGTERM with graceful timeout 0, and reset the clients | All 16 applications observe cancellation, none completes its response, lifespan shutdown completes, and the server exits within the case's three-second bound. |

The load cases sample server-process-tree RSS, OS threads, and the ASGI app's
Python task count every 5 ms. They require no net idle Python-task growth from
the first to the final round, allowing one task of final-sample scheduling
jitter, and a spread of at most 16 MiB between the last two round-end RSS
samples. The sampler includes worker children and can count
shared pages more than once. The RSS condition is a fixed-workload stability
threshold, not an absolute cap. A response fingerprint is retained instead of
duplicating the full repeated body in the report.

This acceptance adds no body-size, byte-queue, or global connection cap. The
observed RSS stability applies only to these bounded inputs and does not
justify a safe general-purpose byte limit. The decision for this change is to
retain current accepted request behavior; any new byte-based resource limit
needs a separate compatibility contract and parity inputs.

Run the normal oracle set with the default runner, then run attribution and
three complete matrix repeats with the unified coverage runner:

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
UV_PROJECT_ENVIRONMENT=target/parity-oracle uv sync --python 3.12 --locked \
  --only-group benchmark --only-group uvicorn-oracle --no-install-project
uv run --group benchmark python scripts/run_parity.py \
  --oracle-python target/parity-oracle/bin/python \
  --output target/parity-normal.json
uv run --group benchmark python scripts/run_unified_coverage.py \
  --oracle-python target/parity-oracle/bin/python \
  --output build/asgi-coverage/current/coverage-report.json \
  --artifacts-dir build/asgi-coverage/current/artifacts \
  --matrix-repeats 3 --matrix-infra-retries 0 --case-infra-retries 0
```

The exact run retained on 2026-10-07 is linked from [coverage evidence](coverage.md#superseded-full-verification-490-cases).
These checks establish fixed-load parity and bounded cleanup on the listed
workflows. They do not claim high-scale capacity, an absolute memory bound,
network-loss resilience, or throughput/latency improvement. Only the
zero-grace HTTP/1.1 path is exercised during shutdown; protocol-wide shutdown
under concurrent load remains unverified.

## Historical correctness evidence

The previous 447-case source independently passed attribution, three full
repeats, 4,734/4,734 regions, 3,333/3,333 lines and its corrected normal-build
exclusion audit. The later 448-case generic-helper snapshot passed all cases
and aggregate coverage but retained seven MCP function observations. Both
remain source-bound historical records in [coverage evidence](coverage.md);
their profiles do not certify the current source.

Seven attribution cases passed on the source before the header-capacity
correction, with zero failures or retries,
including the two strengthened plaintext/TLS drain cases. Both now match live
Uvicorn and report `idle_connection_closed: true`. The artifact audit verifies
that the before/after pairs used the same runner, fixture, manifest, inputs,
environment, and Cargo lock. The two old outcomes were strict diagnostic
adapter failures; the new outcomes are passing ordinary parity comparisons.
The follow-up full run stopped after 219 passing attribution cases when a
reachable capacity panic was found; it has no complete gate. Those profiles
retain their original source identity and cannot be merged with the corrected
source. See [coverage results](coverage.md) for the historical receipts.

Target-only capacity contracts are declared for valid ASGI response and
WebSocket acceptance headers that exceed the compiled Rust header-map
capacity. They use ordinary public input and the existing target-only envelope,
with harness-owned `public.*` identifiers and no native injection control.
They are declared support contracts, not Uvicorn parity or a new test kind.
Both passed on the corrected native within a nine-case attribution subset
with zero failures or retries. The same two inputs failed before the fix and
triggered two unexpected dependency panic hooks, independently rejected even
with zero target exit codes. The corrected source also passed the complete
preceding 447-case instrumented gate; see [the historical full receipt](coverage.md#historical-full-verification-447-cases-before-normal-build-exclusion-correction)
and [before/after audit](coverage.md#historical-targeted-verification-9-cases-fallible-header-assembly).

The historical 445-case snapshot passed every attribution case and measured all
4,719 Rust regions and 3,329 lines with zero Coverage-MCP gaps. Two full repeats
passed 445/445. The third recorded 436 passes, one adapter infrastructure
failure, and eight cases not run, with zero reported behavioral mismatches.
The plaintext graceful-drain adapter rejected a global `Cancelled` connection
diagnostic after the stream had completed. Its gate remained incomplete and
Coverage-MCP retained `tests: failed`. The strengthened idle-connection inputs
and cancellation correction passed the later historical 447-case full gate.

The preceding 444-case snapshot measured all 4,717 Rust regions and 3,328 lines,
with zero Coverage-MCP gaps, but its complete gate was incomplete: attribution
had 443 passes and one live Uvicorn TLS WebSocket handshake timeout. Each of
three full repeats passed 444/444 with zero mismatches or infrastructure
failures. Coverage-MCP retained `tests: failed`; the passing repetitions do
not replace the missing passing attribution case.

The preceding 442-case snapshot passed attribution and three complete
matrix repeats with zero behavioral or infrastructure failures and no retries:
211 oracle-parity cases and 231 target-only fault contracts. Its unified report
still missed six LLVM regions and four lines. The subsequent lifespan guard
changes and two new fault cases produced the later 444-case snapshot. The
listener ownership fix and strengthened shutdown observations then required a
new gate; the preceding 447-case report supplies that evidence without merging
older profiles.

The historical 423-case source/build passed per-case attribution and three
complete matrix runs, with zero behavior mismatches, infrastructure failures,
or transient retries. Its unified report recorded 100% default native Rust
region and line coverage. That receipt predates the ownership and panic-policy
refactor and does not certify the changed source or stricter panic validator.
See [coverage results](coverage.md) for configuration and source/build receipts.
The subsequent 426-case measurement was incomplete: per-case attribution
recorded 425 passes and one infrastructure failure; each full repeat recorded
426 behavioral passes and one infrastructure failure. Five Rust regions and
one line remained uncovered. The current runner repairs the unused-reference
shutdown-cancellation issue. The preceding 447-case source/build passed its own
complete instrumented gate.
When a supported behavior changes, add a mapped input case and update the
support matrix.

The parity runner starts the reference server and `uvicorn-rs` as separate
processes, imports the same ASGI app in each, sends the same input workflows,
and compares their live public observations. It does not contain golden
responses. The Uvicorn oracle needs its own environment because `uvicorn-rs`
installs the same `uvicorn` import namespace as upstream Uvicorn. The runner
checks that the isolated interpreter imports both the pinned distribution and
module at version 0.54.0 before starting a case. This is a version-pinned,
scoped compatibility check; passing it does not establish complete ASGI
conformance or full Uvicorn compatibility.

## Run it

Build the local extension, sync candidate dependencies, and create the
Uvicorn-only oracle environment before running the live parity input set:

```sh
uv sync --python 3.12 --locked --group benchmark --reinstall-package uvicorn-rs
UV_PROJECT_ENVIRONMENT=target/parity-oracle uv sync --python 3.12 --locked \
  --only-group benchmark --only-group uvicorn-oracle --no-install-project
uv run --group benchmark python scripts/run_parity.py \
  --oracle-python target/parity-oracle/bin/python
```

The default run selects oracle-parity rows. To include the compile-gated
fault-contract workflows in the same result envelope, first build the
instrumented extension and pass `--fault-contracts`:

```sh
uv run --python 3.12 --group benchmark python scripts/build_coverage_extension.py
uv run --python 3.12 --group benchmark python scripts/run_parity.py \
  --oracle-python target/parity-oracle/bin/python --fault-contracts
```

For development, select one or more profile groups with repeatable
`--profile` options, or select individual cases with repeatable `--case-id`
options. For example, `--profile http3` runs only the HTTP/3 parity inputs;
`--case-id http3.response-stream-order --case-id http3.scope-query-header-and-body`
runs only those two cases. Combining the options narrows the case IDs to the
selected profiles. These filters do not change the full acceptance matrix.

Choose the smallest relevant selection after a change: named cases for an
isolated behavior and the containing profile when a shared path affects
multiple cases. Reuse a receipt when the source, case manifest, runner, and
environment are unchanged. Run the complete matrix when an acceptance gate
needs full current-source evidence.

Fault contracts use the same workflow schema, server process, observations,
and coverage report. Their result records `verification: fault-contract`,
the allow-listed point, and `oracle_observation: null`. The historical 235
fault-contract cases cover HTTP, WebSocket, HTTP/2, HTTP/3, lifespan, server
startup, and native binding error paths. Their specific contracts verify
observable failure handling and cleanup; they are not oracle-equivalence cases.
The two `support.*` header-capacity rows use harness-only `public.*` selectors
and ordinary valid ASGI input. They do not write a native fault-control file.
They declare the target's finite-capacity rejection and recovery contract in
the same result envelope, and remain outside the oracle-parity denominator.

The HTTP/3 request-trailer input is another target-only support contract using
ordinary protocol input, not an injected Rust fault. The current result schema
has no separate `support-contract` verification mode, so the input travels in
the `fault-contract` envelope while remaining outside the oracle denominator.
The pinned Hypercorn 0.18.0 HTTP/3 server raises `UnboundLocalError` when it
receives the trailing HEADERS section, before it dispatches the ASGI app. A
focused local run passed 1/1 on the target. Keep the result labeled target-only
until the oracle can execute the request; this result is not an
oracle-equivalence claim.

Production Rust errors propagate through `Result`/`PyResult`. Task-unwind and
mutex-poisoning contracts use the instrumented build's `coverage_panic` helper,
which is absent from production builds. The runner checks every Rust panic-hook
event against the exact source, message, and count expected for that process's
attempted fault cases. Extra, missing, or unexpected events fail verification.
This check runs independently of process-exit validation: an expected injected
panic does not excuse a nonzero exit or waive the declared shutdown policy.
An unexpected panic-hook event also fails verification when the process exits
successfully.

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

| Profile group | Cases | Reference | Why |
|---|---:|---|---|
| HTTP/1.1, including TLS | 122 | Uvicorn 0.54.0, uvloop 0.23.0; httptools 0.8.0 by default, h11 0.16.0 for one case | Same protocol and measured fast Uvicorn stack; includes HTTP parsing, ASGI events, streaming, disconnect, concurrency-limit rejection, TLS 1.2 cipher selection, trusted, disabled, excluded-peer, wildcard, IPv4-CIDR, malformed/empty forwarded-client, all-trusted-chain, duplicate forwarding-field, and unsupported-proto proxy cases, WebSocket-upgrade validation, repeated CLI response headers with disabled Server/Date defaults, and one h11-selected POST scope/body comparison. |
| WebSocket, including TLS | 68 | Uvicorn 0.54.0, uvloop 0.23.0, websockets 17.1 | Same HTTP/1.1 upgrade path, message flow, rejection, disconnect, shutdown, configured message limits, and proxy-derived `ws`/`wss` scope schemes. |
| Startup configuration | 22 | Uvicorn 0.54.0 and the public `uvicorn_rs.Server` API | Same invalid-host, certificate, and private-key startup configurations on both implementations. |
| Lifespan and shutdown | 37 | Uvicorn 0.54.0, uvloop 0.23.0, httptools 0.8.0 | Covers lifespan event/error shapes, shallow state copies, cancellation, listener closure before held-response release over plaintext/TLS, and Rust's public Server.serve() cancellation path. |
| HTTP/2 | 28 | Uvicorn 0.54.0, zttp 0.0.34, TLS ALPN, explicit ASGI mode | Experimental Uvicorn HTTP/2 is selected with `--http zttp --http2`. A prior local aggregate run passed the 27 earlier parity cases with the source adapter. The added zero-concurrency case passed as a selected one-case run and checks the oracle-matched 503 plus the HTTP/2 concurrency observer path. Hosted release evidence and the HTTP/2 category benchmark remain pending. Prior Hypercorn receipts are historical. Includes empty final DATA, concurrent streams, reset, and final-response completion. |
| HTTP/3 | 34 | Hypercorn 0.18.0, aioquic 1.3.0, QUIC, explicit ASGI mode | Hypercorn provides the same-protocol HTTP/3 reference. Includes the 128-response sequence, typed H3 close recovery, and same-connection recovery after a peer close. |
| CLI and environment | 114 | Uvicorn 0.54.0 | Compares selected module/console invocations, argument parsing, environment precedence, current-directory app import resolution, app loading, process outcomes, `--http h11` acceptance, zero WebSocket ping interval startup, graceful-shutdown option/environment acceptance, and explicit-option precedence over malformed backlog, graceful-shutdown, keep-alive, request-limit, worker-healthcheck, WebSocket-size/queue/ping-interval/ping-timeout/deflate, HTTP, WebSocket selector, lifespan, worker-count, and reload-delay environment values and concurrency settings; invalid host/interface/log-level/request-limit/WebSocket environment diagnostics; explicit interface/log-level precedence; environment/explicit-flag resolution for `UVICORN_APP_DIR`, `UVICORN_ENV_FILE`, and `UVICORN_RELOAD_DIRS`; version, factory, FD, h11-size, TLS, HTTP/2, loop, and UDS environment cases; and the missing-path diagnostic for `--reload-dir`. |
| Python API | 241 | Uvicorn 0.54.0 | These are oracle-comparison cases; 23 target-only fault-contract cases have no Uvicorn comparison and are excluded from this count. Compares documented imports/signatures, including logging formatters, deprecated `ServerState` paths and the `Server.run()`/`Server.serve()` methods and the `Server.startup()`, `shutdown()`, `main_loop()`, `on_tick()`, and `capture_signals()` signatures; selected `run` and `Server` lifecycle behavior; configuration error ordering; selected Python event-loop behavior, including a custom import-string loop factory through `uvicorn.run()`; headers, environment files and `FORWARDED_ALLOW_IPS` precedence; module-CLI `UVICORN_RELOAD=true` live reload selection, `UVICORN_RESET_CONTEXTVARS` behavior and explicit-flag precedence, and environment-driven `UVICORN_RELOAD_INCLUDES`/`UVICORN_RELOAD_EXCLUDES` file filtering plus explicit-option precedence; root-path environment handling and explicit `--root-path` precedence; selected host/port, interface, and concurrency settings through `UVICORN_HOST`, `UVICORN_PORT`, `UVICORN_INTERFACE`, and `UVICORN_LIMIT_CONCURRENCY`; explicit `--limit-concurrency` precedence over valid and malformed environment values, plus explicit `--interface asgi3` precedence over `UVICORN_INTERFACE=wsgi`; ASGI2 and focused WSGI selection, including two finite POST bodies and four chunked-transfer POST bodies (two one-chunk and two two-chunk requests) delivered through wsgi.input via uvicorn.run() and python -m uvicorn; trusted proxy headers, including module-CLI `UVICORN_PROXY_HEADERS=false` and `UVICORN_FORWARDED_ALLOW_IPS` precedence; module-CLI `UVICORN_HEADERS`, inherited `UVICORN_FD`, and TLS `UVICORN_SSL_*` environment handling; non-default module-CLI TCP backlog and HTTP/1 keep-alive timeout with live connection checks; HTTPS over a Unix-domain socket; successful application-factory serving through the programmatic API and module CLI; WebSocket message-size enforcement with a non-default `ws_max_queue` value on the auto/SansIO path; positive and zero concurrency-limit behavior, including module-CLI --limit-concurrency 1 returning the oracle-matched 503; warning-level filtering; `UVICORN_LOG_LEVEL=debug` through the module CLI and explicit warning-level precedence over it; access-log suppression plus `UVICORN_ACCESS_LOG` and `UVICORN_USE_COLORS` environment behavior and explicit precedence; `UVICORN_SERVER_HEADER` and `UVICORN_DATE_HEADER` environment suppression with explicit `--server-header` precedence; both CLI color switches; forced ANSI colors through `uvicorn.run()`; custom INI/JSON/YAML logging configuration through `uvicorn.run()` and the module CLI; `UVICORN_WORKERS=2` environment-backed module-CLI startup with two worker processes; inherited TCP listener serving through the module CLI, `uvicorn.run(fd=...)`, `Config(fd=...)` with `Server.run()`, and `Server.run(sockets=[...])` with one or two listeners; `Server.serve()` cancellation during held lifespan startup and after readiness; actual repeated SIGINT delivery to a module-CLI child while an ASGI request remains active; and single-SIGINT graceful-timeout cancellation while an ASGI request remains active. Successful PKCS#8 TLS key loading is compared through `Config`/`Server` and the module CLI, and a wrong-password failure is compared through `Config`/`Server` using the same fixture. Two additional inputs compare successful loading of a traditional AES-256-CBC encrypted RSA PEM through `Config`/`Server` and the matching wrong-password failure. A new input compares a password supplied with an unencrypted RSA key; both implementations serve the request over TLS and shut down cleanly. Six focused mTLS inputs cover trusted client certificates with default negotiation and TLS 1.2, optional anonymous clients with CA-backed and empty-root configurations, rejection of an untrusted client certificate with empty roots, and a trusted TLS 1.2 client through the module CLI. Two more inputs compare invalid `ssl_cert_reqs=3` and empty client-CA startup rejection. The selected TLS cases and their source-scope notes are in [coverage results](coverage.md). WSGI cases check a GET through each entry point with `lifespan="off"`; additional auto-mode cases compare request serving and the unsupported-lifespan fallback with default logging, configured logging, and the module CLI. HTTP-run cases compare normalized server log events, including color presence and configured formatting, alongside HTTP and shutdown outcomes; raw stdout/stderr remain in the evidence. The WSGI POST checks cover finite buffered bodies, one-chunk transfer bodies, and two-chunk transfer bodies; other chunk counts, large bodies, malformed lengths, response streaming, error behavior, application factories, and cross-platform behavior remain unverified. Other log levels and precedence combinations, and exact traceback frame formatting, also remain unverified. |

The previous `input@40` inventory contained 580 declared oracle-parity cases.
The current `input@43` inventory contains 666 declared oracle-parity cases;
six earlier selected environment-backed module-CLI cases pass together, and
the later focused CLI precedence groups pass 1/1, 2/2, 4/4, 6/6, 7/7, 10/10,
and 4/4 twice plus two selected 1/1 cases. The latest hosted installed-wheel
receipt is bound to `input@42`; the earlier 580-case full installed-wheel
receipt remains historical evidence for `input@40`. The `UVICORN_WORKERS=2`
and `UVICORN_RELOAD=true` module-CLI environment
cases each pass 1/1 on the recorded macOS host; the module-CLI
`--reset-contextvars` and missing `--reload-dir` cases also pass 1/1, as does
environment-only `UVICORN_PROXY_HEADERS=false` behavior. The reload comparison retains
event count and order while normalizing supervisor PIDs. The other 349 ASGI
cases are target-only fault/support contracts, and 258 native-core
contract cases bring the current input inventory to 1,251 (993 ASGI and 258 native). Six
historical startup contracts for an experimental Tokio blocking-pool cap were
removed after matched FastAPI uploads showed no repeatable benefit; archived
reports retain their historical counts. The cap is not part of the current
runtime or support contract.

### Hosted installed-wheel public parity — CI #435

The installed normal wheel passed **660/660** declared public Uvicorn 0.54.0
parity cases with zero failures in [CI run #435](https://github.com/appunni-m/uvicorn-rs/actions/runs/40591281095).
The CI evidence checker accepted the receipt.
The receipt binds to commit `f8b5b57f679ca1e5847152c7f1802cabc9b07444`,
source SHA-256
`77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9`,
`input@42`, Ubuntu 24.04 x86-64, and CPython 3.12.13; it records a clean
source checkout. This is complete evidence for the declared public matrix on
that Linux configuration, not full Uvicorn compatibility across platforms.
The CI #435 three-pass unified coverage job was cancelled. [CI #437](https://github.com/appunni-m/uvicorn-rs/actions/runs/40598829834)
is in progress on 9b4fc703b with parity and coverage jobs running. It includes
the committed module-CLI finite WSGI POST case but not the local input@43
chunked-body cases. Documentation run #154 passed on this head. This parity receipt does not stand in for target-only fault
contracts or cross-platform and full CLI/API acceptance.

### Input@40 baseline CLI and Python API profile runs — 2026-10-27

The input@40 CLI baseline passed 60/60 cases against Uvicorn 0.54.0 in
run `c25aac929fd74dcb9ff3d9206653596a`; report
`target/kata-progress/9kbx-cli-current-full-20261027.json`, SHA-256
`fc58678c2f3ab8227fead7ef6f9c4e34b9d5ca823976cebcc4d72c49ba3cb3b7`.
The input@40 Python API baseline passed 209/209 oracle-parity cases in run
`c4f523f43087481f90d90fd74c46c5e8`; report
`target/kata-progress/x3az-python-api-current-full-after-sigint-contract-fix-20261027.json`,
SHA-256 `f45a36e6f32baaaebe8d16b37f19ddf433579f9565f08cd6572e151531009b7e`.
Both reports use manifest SHA-256
`ede173a29d162a002ee37d469f1ecaeeafa5d8e97c15c5bfbc67157b55c6f9be`, CLI
input@40 SHA-256
`b86587d0f2f6d890a9dfef3b974bd2f6b5f5cc109a09fde93c6935e892688cf0`, and
Python API input@40 SHA-256
`3fb4cb2e7e4146060908da556d692ec8654196762261797bf92a352a4f847a96`. They
bind to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, target
source SHA-256 `7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc` on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

The first current-input Python API attempt found that the RSA DES-EDE3
`Config`/`Server.run()` case required exit code 0 even though both Uvicorn and
the target re-raise the captured SIGINT after graceful shutdown. The input now
keeps the response, signal, and no-timeout requirements while comparing the
actual exit code between oracle and target. The corrected full profile passed
209/209. These are local one-pass source-profile results; installed-wheel,
cross-platform, target-only/native, and release verification evidence are
tracked separately below.

### Full installed-wheel public parity after lifespan shutdown fix — 2026-10-27

Built the normal abi3 wheel from the current dirty checkout and installed it in
a fresh candidate environment, separate from the Uvicorn 0.54.0 oracle. The
complete declared public oracle-parity inventory passed **580/580** with zero
behavior failures, infrastructure failures, or cases not run. Receipt:
`target/kata-progress/installed-parity-current-source-20261027/installed-full-parity-after-lifespan-fix.json`, run
`9f5d8332dbd842b08e52372571b0eee2`, SHA-256
`b9ea5b0062a935406fcb45fc8579d3a370470776cb07d82a148bf92a743b7153`. The
installed wheel is
`uvicorn_rs-0.2.2-cp39-abi3-macosx_11_0_arm64.whl`, SHA-256
`8b424d96785e22df63f429104783446ecff81f9136ec15ce4ae64098df4de9fd`.

The first installed run exposed a real mismatch: after the request-drain
timeout cancelled a held request, the target skipped the ASGI lifespan
shutdown handshake, while Uvicorn completed it. The smallest fix removes that
skip from `src/lib.rs`. The existing regression case
`lifespan.post-response-background-task-cancelled-before-server-return` then
passed, as did four other graceful-timeout cases. A final complete installed
matrix passed after the fix.

The receipt binds to dirty revision
`5b1ec29201c963d8590c989b07318bb7366d7922`, target source SHA-256
`eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`, native
extension SHA-256
`74fd52144fbc0b168db90da59de02cffaf5e1a037995beb2a3b6b2792a523535`, manifest
SHA-256 `ede173a29d162a002ee37d469f1ecaeeafa5d8e97c15c5bfbc67157b55c6f9be`, CLI
input@40 SHA-256
`b86587d0f2f6d890a9dfef3b974bd2f6b5f5cc109a09fde93c6935e892688cf0`, and
Python API input@40 SHA-256
`3fb4cb2e7e4146060908da556d692ec8654196762261797bf92a352a4f847a96`. It ran on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. This completes the local
installed public parity matrix only; Linux/Windows and other supported Python
versions, the 349 target-only fault contracts, 258 native-core contracts, and
clean exact-main release acceptance remain open. Benchmark work remains
paused until the supported-platform parity evidence is complete.

The new HTTP/2 case `http2.zero-concurrency-rejects-request-with-503` passed
1/1 in selected coverage run `8db2016852224570b63db99eea9b0a90`. Its report
and source/input identities are recorded in [coverage results](coverage.md).
This receipt is local, dirty-source evidence for one case; it does not replace
the full coverage, three-repeat, hosted, or independent review gates.
The subsequent inherited-listener fault-hook edit changed the source identity,
so this H2 receipt is historical for its recorded digest rather than an
exact-source result for the latest checkout.

The target-only fault contract
`fault.http1.inherited-server-local-address-inspection-error` passed 1/1 in
selected run `53b3ce05c19043ab8b4e5752902f5622`; it exercises startup failure
and lifespan cleanup after an inherited listener address-inspection error.
Its evidence is recorded in [coverage results](coverage.md).

Focused Python API evidence: `python-api.config-server-handles-password-for-unencrypted-key`
passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13; both
servers returned HTTP 200 over TLS and exited successfully after SIGINT. Run
`c23343e64be34a11b5cf80f00f5f3252`; receipt
`target/kata-progress/unencrypted-key-password-parity-20261027.json`, SHA-256
`b3d2789b1525165f4423101e9ddfa42df191d9f30f49d579e9aaa92f4fb2d971`. It binds
dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`3c6654dd24f30e6b838232518a5c8967c73952a1e722a6ec4d6725568f28fe0d`, and
Python API input SHA-256
`951e47c19c1eddd213cbf3d1a1bc7529118e572ad3b094ce500e0e234ceeced7`.

`python-api.module-cli-root-path-envvar-applies-root-path` and
`python-api.module-cli-explicit-root-path-over-envvar` passed 2/2 in one
selected run against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13.
The first case supplies `/mounted` through `UVICORN_ROOT_PATH` without the
explicit option; the second confirms that `--root-path /mounted` overrides
`UVICORN_ROOT_PATH=/from-environment`. Both requests confirmed the expected
ASGI `root_path`, `path`, and `raw_path`. Run
`78131c92534f47fc80c7e8f60cc9925d`; receipt
`target/kata-progress/9kbx-root-path-env-group-20261027.json`, SHA-256
`47a4e500098430596f6f92462c10ca6c745a8991051a48772dc9ad9106f8c390`. It binds
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`3c6654dd24f30e6b838232518a5c8967c73952a1e722a6ec4d6725568f28fe0d`, and
Python API input@38 SHA-256
`48368db819691cf0ef7ed4e5d8389e890498c047870a3f8fa562826b07d077a4`. Full CLI
and platform parity remain open.

`python-api.module-cli-second-sigint-forces-inflight-request-shutdown` passed
1/1 against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust
1.98.1. Both module-CLI processes served HTTP 200, received two actual SIGINT
signals while an ASGI request task was held, exited 0, and did not time out.
Run `5250fc7d6d4145e2a1d206de3621fd91`; report
`target/kata-progress/parity-second-sigint-current-20261027.json`, SHA-256
`3d1d1487fc206a067c1cb58d5a175ac21b0cc88c3b673cd64e982f179521f601`. It binds
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`, native
extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@39 SHA-256
`9cd73e4493708deebe55227a1face7bf3be76ecba8f81c6fc8ebca3b46498feb`.
The receipt stores server log events, but the comparison omits them because
platform-specific traceback details differ during forced cancellation. This
single-platform case does not close broader signal, worker, reload, socket,
or cross-platform process-control parity.

`python-api.module-cli-graceful-timeout-cancels-inflight-request` passed 1/1
against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.
Both processes served HTTP 200, received one SIGINT with
`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=1`, observed cancellation of the held ASGI
task, exited 0, and did not time out. Run
`566af64b1d144153b2e9acb369f9795c`; report
`target/kata-progress/parity-graceful-timeout-current-20261027.json`, SHA-256
`e7b00fa31814e5baf03a7667c4660c11006ba67c5ed57e45994386a81f579eda`. It binds
to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source SHA-256
`7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`, native
extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@39 SHA-256
`4e42e17e08aef42975f49bc4248ec87a9559045d320fe63a45863dd82ad50f67`. This
selected one-platform receipt adds the timeout effect to parity coverage; it
does not establish the full shutdown contract or cross-platform behavior.

`python-api.module-cli-graceful-timeout-flag-cancels-inflight-request` also
passed 1/1, this time setting the timeout through
`--timeout-graceful-shutdown 1`. Both processes served HTTP 200, received one
SIGINT while the ASGI task was held, observed its cancellation, exited 0, and
did not time out. Run `694b96675dca41d593b315f07d0470e7`; report
`target/kata-progress/parity-graceful-timeout-flag-current-20261027.json`,
SHA-256 `d021e11ceb9d5eb27eb089f1006f5329cf4d6aa4a5a5b005ec97ff4c60ee5c87`.
It binds to dirty revision `5b1ec29201c963d8590c989b07318bb7366d7922`, source
SHA-256 `7ba47a4d8cc3aa4b0039058a68b4d8c201b484ebf4ab5df7a15d27c61a2119ae`,
native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`, and
Python API input@40 SHA-256
`f8d6b7873a5c83f173f63866df6f7b3d7503159522db1929b20659dd7332ed72`. The
environment-driven receipt above remains an input@39 record; the full
current-source matrix and cross-platform acceptance are still open.

The non-Linux installed-candidate CI step selects all 77 CLI and 215 Python API
parity cases on macOS. On Windows it selects all 77 CLI and 201 Python API
cases, excluding 14 POSIX-only inputs. Linux
retains its full parity lane. This describes the configured selection only;
the modified draft commit has no hosted workflow evidence yet.

## Module-CLI environment parity — 2026-10-27

Six selected cases pass against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 /
CPython 3.12.13 / Rust 1.98.1: `python-api.module-cli-listener-host-port-from-environment`
binds with `UVICORN_HOST=0.0.0.0` and a dynamically reserved `UVICORN_PORT`
and serves HTTP 200; `python-api.module-cli-concurrency-limit-from-environment`
uses `UVICORN_LIMIT_CONCURRENCY=1` and returns HTTP 503 on both implementations;
`python-api.module-cli-explicit-concurrency-limit-overrides-invalid-environment`
uses `--limit-concurrency 2` to override a malformed environment value and
serves HTTP 200; `python-api.module-cli-explicit-concurrency-limit-overrides-valid-environment`
uses the same CLI limit over `UVICORN_LIMIT_CONCURRENCY=1`, returns HTTP 200,
and confirms the explicit argument takes precedence; `python-api.module-cli-uses-wsgi-interface-from-environment`
selects the WSGI adapter through `UVICORN_INTERFACE=wsgi` and serves HTTP 200
against the WSGI fixture on both implementations; `python-api.module-cli-explicit-interface-overrides-environment`
uses `--interface asgi3` over the conflicting valid `UVICORN_INTERFACE=wsgi`
value and serves the ASGI3 fixture with HTTP 200. All six processes exit 0
after SIGINT, and the normalized
observations match.

Run `6bccbbc39531471f9d5c191bd6a77507`; receipt
`target/kata-progress/python-api-cli-environment-parity-20261027.json`, SHA-256
`eaba087fc44e031c275394917555f2398af6f03ee2e2d16c23c61d6cbc190533`.
It binds Python API input@42 SHA-256
`3e9e033ea06125c39f22c0eecdf8fdf30232894f1a5c61bc54617531a1707753`, dirty
target revision `8b1f90752b092c447ad4e22b20fe477ae8fe6951`, runner SHA-256
`f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`, and
probe SHA-256 `5dcfc30c60f59c6340a519114820d9a19d5e402a4d689883ef398d21075e9809`.
The `@probe-port` value is a parity-runner marker replaced with the reserved
listener port before the child starts; it is not a Uvicorn setting. This is
selected single-platform evidence; the complete input@42 profile, other
supported platforms, and exact release-candidate parity remain open.

## Invalid module-CLI interface environment — 2026-10-27

`cli.invalid-interface-environment-is-rejected` sets
`UVICORN_INTERFACE=invalid` with no `--interface` override. The reference and
target both exit 2, emit the same Click validation error on stderr, and write
no stdout. The focused case passed 1/1 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `39ef3c0dc2ff4e57b83ce3333d6136fc`; receipt
`target/kata-progress/cli-invalid-interface-environment-20261027.json`,
SHA-256 `2b583b6157bc4f116e37812ac3b90253c0741e43301e414dab6f73a648923f48`.
It binds CLI input@42 SHA-256
`5438e5d19a1859488efaac8206b58de270da6f9b727d6103f4c004b73afa23c6`, source
revision `3526377c52e460c6b33d842c5304ff79abe33a32`, dirty target source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`. This
is one selected local case; it does not establish full CLI or environment
parity or release-candidate evidence.

## Explicit module-CLI interface overrides malformed environment — 2026-10-27

`cli.explicit-interface-over-invalid-environment` sets
`UVICORN_INTERFACE=invalid` alongside `--interface asgi3`. Both processes start
and exit 0 with empty stdout and stderr, confirming explicit CLI precedence
over the malformed environment value. The focused case passed 1/1 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `ad1e156e5c4046cb842d125f8b9b5734`; receipt
`target/kata-progress/cli-explicit-interface-over-invalid-environment-20261027.json`,
SHA-256 `2e4f889663b0f5cf289801d094c838dd56e2107b3a59544602f9eb814ffc936d`.
It binds CLI input@42 SHA-256
`480d0cb518805aee2973c907fc6b65b8ffaec4f96fc7bd843b6b0234f6b3252a`, source
revision `e463c71a5558b3073b3b61fabdfaeb4d446844ff`, dirty target source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`. This
is one selected local case; full CLI, environment, platform, and clean
release-candidate parity remain open.

## Explicit module-CLI graceful-shutdown value overrides malformed environment — 2026-10-27

`cli.explicit-graceful-shutdown-over-invalid-environment` sets
`UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=not-a-timeout` alongside the explicit
`--timeout-graceful-shutdown 1` option. Both processes start and exit 0 with
empty stdout and stderr, confirming that the CLI value takes precedence during
parsing and startup. The focused case passed 1/1 against Uvicorn 0.54.0 on
macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `4509a85f97a047cdb5a61631df505397`; receipt
`target/kata-progress/cli-graceful-shutdown-environment-precedence-20261027.json`,
SHA-256 `9a209fc7c71ad43a06492228bc2d60dbb3ca15039df8e4891e4251f14179bf0b`.
It binds CLI input@42 SHA-256
`8acd3ac08225ee0a70d4342f6610e6de04433d96b5c721baa0da5dba27989f54`, source
revision `d70d4f87479d1aaf4f717e31d7202b2446601bab`, dirty target source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`. This
one selected case verifies CLI parsing/startup precedence; the existing held-
request cases remain the evidence for actual graceful-timeout cancellation.

## Module-CLI log-level environment parity — 2026-10-27

Two selected cases pass against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 /
CPython 3.12.13 / Rust 1.98.1. `cli.invalid-log-level-environment-is-rejected`
sets `UVICORN_LOG_LEVEL=verbose`; both processes exit 2 with identical Click
diagnostics and empty stdout. `cli.explicit-log-level-over-invalid-environment`
sets the same malformed value alongside `--log-level critical`; both processes
start and exit 0 with no output. This pairs invalid-value validation with
explicit-option precedence; the separate Python API inputs still cover valid
`debug` environment selection and explicit `warning` precedence.

Run `42902b13b1664d12ad7e1cdc32b3208e`; receipt
`target/kata-progress/cli-log-level-environment-parity-20261027.json`,
SHA-256 `5dad8038cc7f13326dd9d7712ecd759b8c2cc83dc4fb42f5ffebf971849140f5`.
It binds CLI input@42 SHA-256
`bc59fd2ca64f0dea9cfbccc014505c835384b878b7f4cfcbe226dcc27b0f3fc1`, source
revision `ed7dcc482a17d84c38762cb1791e5746585bdb20`, dirty target source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`. This
is a selected two-case local group; full CLI, environment, platform, and clean
release-candidate parity remain open.

## Module-CLI WebSocket environment precedence — 2026-10-27

`cli.explicit-ws-max-size-over-invalid-environment` sets
`UVICORN_WS_MAX_SIZE=not-a-size` with `--ws-max-size 4`, while
`cli.explicit-ws-ping-timeout-over-invalid-environment` sets
`UVICORN_WS_PING_TIMEOUT=not-a-timeout` with explicit zero ping interval and
timeout options. Both implementations start and exit 0 with empty stdout and
stderr, confirming explicit CLI values take precedence during parsing and
startup. The focused group passed 2/2 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `8048f68cd6294618a52571ae87f0faf2`; receipt
`target/kata-progress/cli-websocket-environment-precedence-20261027.json`,
SHA-256 `f89d10c41c93462f48c29aa1baf1d5c91de3b1fc191e7699fcc341235dca5e48`.
It binds CLI input@42 SHA-256
`17783e81689cd9f5f50ce3543d5c4208a74e1459643d4a3160be4793b3a79e5d`, source
revision `d70d4f87479d1aaf4f717e31d7202b2446601bab`, dirty target source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`. These
selected cases verify CLI parsing/startup precedence; they do not exercise
WebSocket sessions or message-limit behavior.

## Module-CLI request-limit environment validation and precedence — 2026-10-27

Four focused cases compare malformed `UVICORN_LIMIT_MAX_REQUESTS` and
`UVICORN_LIMIT_MAX_REQUESTS_JITTER` diagnostics with explicit zero-valued CLI
overrides. The malformed values produce matching exit code 2, stderr, and
empty stdout; the explicit options let both module-CLI processes start and
exit 0 with empty output. The group passed 4/4 against Uvicorn 0.54.0 on macOS
15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `782b0c8fa6334e9dbc74f2835a7f8d63`; receipt
`target/kata-progress/cli-limit-max-requests-environment-20261027.json`,
SHA-256 `7a6476705bbbe6f4af02da0b42b26ca30c6b0e1028040112630d033f05e07ef6`.
It binds CLI input@42 SHA-256
`4fa11196f9123f78a551dbeaa5de1e889cc99eeedf5fa913c09a56603161c185`, target
revision `1e5941497813be80792a124d873a95dd4703dfe0`, dirty source SHA-256
`eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`, runner
SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI numeric settings environment validation and precedence — 2026-10-28

Six focused cases compare malformed `UVICORN_BACKLOG`,
`UVICORN_TIMEOUT_KEEP_ALIVE`, and `UVICORN_TIMEOUT_WORKER_HEALTHCHECK`
diagnostics with explicit CLI overrides. The malformed values produce matching
exit code 2, stderr, and empty stdout; explicit options allow both module-CLI
processes to start and exit 0 with empty output. The group passed 6/6 against
Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `57047586b6af481cacf8476a04680a80`; receipt
`target/kata-progress/cli-numeric-settings-environment-20261028.json`,
SHA-256 `9ac67a299fa8cd4b0ae8609c22bfc7a134cd7862459b31db60ceb60ee612bd7e`.
It binds CLI input@42 SHA-256
`f23cc68aa734dc8ba35de2864ff6c42ea5d1112a332ab804515c1f76bf73c7b1`, target
revision `adf2f1d89f0b688ef537fe44cc8c3d70d61fdbe3`, dirty source SHA-256
`eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`, runner
SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI selector and process-setting environment precedence — 2026-10-28

Ten focused cases compare malformed `UVICORN_HTTP`, `UVICORN_WS`,
`UVICORN_LIFESPAN`, `UVICORN_WORKERS`, and `UVICORN_RELOAD_DELAY` values with
explicit valid options. The HTTP, WebSocket, and lifespan selectors produce
matching diagnostics; the explicit overrides allow both module-CLI processes
to start and exit 0. Worker-count and reload-delay parse diagnostics and their
explicit overrides also match. The group passed 10/10 against Uvicorn 0.54.0
on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `0bd6505fdafb44aeaf21042eb5f75a53`; receipt
`target/kata-progress/cli-selector-environment-20261028.json`, SHA-256
`5cafb45e466f3bebc01f868e5ccf4149855636338ff1add5e399ce2073a044f5`.
It binds CLI input@42 SHA-256
`eb17fe8b9b573585361b919c2832ba6aaa1c7c8d6882ad7f6b66ca6be35912aa`, target
revision `c64e4ffcd242c9f1a83100898119dd8454120798`, a dirty working tree, source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI app-dir and env-file environment precedence — 2026-10-28

Four focused process cases pass 4/4 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1. `UVICORN_APP_DIR` resolves the import
before the expected missing-attribute diagnostic, and explicit `--app-dir`
overrides a conflicting environment path. `UVICORN_ENV_FILE` loads the
fixture value before invoking the application factory, and explicit
`--env-file` overrides a missing environment-supplied path. These comparisons
verify input-source selection and diagnostics; they do not establish complete
CLI environment parity.

Run `0d6243237f964dde9a920e13db4f40f4`; receipt
`target/kata-progress/cli-path-environment-20261028.json`, SHA-256
`2a7c632d851552a59386adb0696d7160296fc0aa0b2641b091d696544531221b`.
It binds CLI input@42 SHA-256
`2570b27ae4295445f63657eca3c5d11ee4520fb8039937918d0d85506bf938be`, target
revision `fcc5151ded2ead1acc3f885d4f164b3b59a865e8`, a dirty input tree, source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI logging boolean environment precedence — 2026-10-28

Four focused HTTP cases pass 4/4 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1. Environment-only
`UVICORN_ACCESS_LOG=false` suppresses the request log, and
`UVICORN_USE_COLORS=true` enables colorized logs. Explicit access-log and
no-color options override opposing environment values. HTTP results, normalized
log events, and process exits match; this is selected behavior, not complete
logging or environment parity.

Run `9551b5abfbca4171afca8604cb66bfad`; receipt
`target/kata-progress/cli-log-env-parity-20261028.json`, SHA-256
`9b60590136ede83e2549d12b3ca671984175c316b7fd14918a9bd617251b515b`.
It binds Python API input@42 SHA-256
`cdc41b19ff0d6133983863ef1023422a8520fa380e9cd659ecb4acaf1c94a968`, target
revision `00b1be106ccb30b89bfbadbd02d64aba829da76c`, a dirty input tree, source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI header environment behavior — 2026-10-28

Two focused HTTP inputs compare `UVICORN_SERVER_HEADER=false` and
`UVICORN_DATE_HEADER=false` with Uvicorn 0.54.0. The environment-only case
passed inside run `d88a648b988641e7b270e3a20ba9c4bd`; that two-case batch also
contained an explicit-precedence case whose live `Date` values differed by one
second. The explicit case now observes only the stable `Server` header and
passes 1/1 in run `2ee7b625a2a146c1b7382aa898385a1f`: explicit
`--server-header` overrides `UVICORN_SERVER_HEADER=false`, while the environment
continues to suppress `Date`. This evidence covers the environment values and
one explicit override; it does not qualify every header combination.

The initial report is
`target/kata-progress/cli-header-env-initial-20261028.json`, SHA-256
`18d50ba4875d387d7ed2d2bdc8e5aa8693c4d5e005aa5ad30200efd837f0da04` (one
case passed and the initial two-case batch failed on the dynamic `Date` value).
The corrected selected report is
`target/kata-progress/cli-header-env-explicit-20261028.json`, SHA-256
`f2b5dc3ad5051c153ec15f3f2fd024a9530120dc5a46627007b5a55510e5d28c`. It binds
Python API input@42 SHA-256
`2c2e27e7d8aa2c88d3b63733d4e827c2cf5af605b441755dea0cc70422df2d59`, target
revision `78d8d41e6732052b42b5835e2c88ce66b6d72c31`, a dirty input tree, source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI reload-directory environment binding — 2026-10-28

Three selected CLI process inputs pass 3/3 against Uvicorn 0.54.0 on macOS
15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. They cover a valid
`UVICORN_RELOAD_DIRS` path, rejection of a nonexistent environment path, and
an explicit `--reload-dir` overriding that invalid environment value. The
environment variable is plural because Click derives it from Uvicorn's
`reload_dirs` parameter. These cases establish parsing and precedence only;
live reload selection and directory watching remain covered by separate
Python API inputs.

Run `48a67c5073a740ae85d3bf39b0d43277`; receipt
`target/kata-progress/cli-reload-dir-env-focused-20261028.json`, SHA-256
`0e76dd9acbb71f10b01f4519db86bf65d263e05cfc2c0c7f7504a1247bb0a0fd`. It binds
CLI input@42 SHA-256
`65e9023ada897cbf009b568753fff9fc98f50431a3d5a51f3353721bc8b96d74`, target
revision `a74224d373fd5150f0c3783a790d8ee38bc2c0f0`, a dirty input tree, source
SHA-256 `3ba1a079d49bee1bcbcc896aedd5406d84ede6da54adc48d716eafd91512432a`,
runner SHA-256 `1fdcbe1cbee7fdda29167dc10684ff612133ab8670da2df234036348288be44d`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.


## Module-CLI reload filters from environment — 2026-10-28

Two focused live reload inputs pass 2/2 against Uvicorn 0.54.0 on macOS
15.7.7 ARM64 / CPython 3.12.13 / Rust 1.98.1. With
`UVICORN_RELOAD_INCLUDES=*.txt` and `UVICORN_RELOAD_EXCLUDES=ignored.txt`, both
module-CLI implementations leave the excluded file change unreloaded, reload
after an included file changes, serve the updated response, and exit cleanly
on SIGINT. A second input sets conflicting environment patterns and explicit
`--reload-include`/`--reload-exclude` values; both implementations apply the
explicit flags. The observations exercise the live WatchFilesReload path.

Run `ee8bb3c811ad44409ddf414b292073a0`; receipt
`target/kata-progress/python-api-reload-filters-env-and-precedence-20261028.json`,
SHA-256 `4919b45fc4a330cd1d2105ef82e7adc16f1555159f66e87ebd3b4fc9abc95938`. It
binds Python API input@42 SHA-256
`c25381305cbf75ab3626c830028b2f24f91156b1d894efad8e952463f971a284`, target
revision `3412a104854cab0885fbc12de509aa5d05445529`, a dirty input tree, source
SHA-256 `3ba1a079d49bee1bcbcc896aedd5406d84ede6da54adc48d716eafd91512432a`,
runner SHA-256 `3b4e281276db086680f9171c55d138b1397cbb812a4cf589d1ccf84847095ca4`,
Python API probe SHA-256
`8c5a3531f388ffe523aa39f5bab24b12a0992859bf2f5fd5915e91bd4e10a909`, and
native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Module-CLI reset-contextvars environment parity — 2026-10-28

Two focused module-CLI cases pass 2/2 against Uvicorn 0.54.0. The first sets
`UVICORN_RESET_CONTEXTVARS=true` and observes an empty request context. The
second sets the environment variable to false and confirms that the explicit
`--reset-contextvars` flag takes precedence. Both return HTTP 200 and exit
cleanly. Full Python API parity remains open.

Run `63a21609687947c7974c80a1d9e4a7c0`; receipt
`target/kata-progress/python-api-reset-contextvars-env-focused-20261028.json`,
SHA-256 `e63b4fcd4319a7fd5a83c4576f1ce3b41def2fa0d633cd589c70a6f271d0a756`.
It binds Python API input@42 SHA-256
`2712ec38ceb44a2aba16b783435f1d6d6035f8aef212e1f5adf8673b408665b4`, target
revision `885968146a613ad1323d7a0c0a1dd9f3d7be4668` with a dirty input tree.

## Worker and reload startup-log parity — 2026-10-28

The 14 worker and reload cases that failed on CI run #432 now pass 14/14
against Uvicorn 0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13 / Rust
1.98.1. The mismatch was an extra `Uvicorn running on ...` message from each
child: Uvicorn's supervisor had already logged the bound listener in the
parent. `Server.startup()` now records whether the caller supplied supervisor
sockets before converting a direct `--fd` into a socket list, preserving the
single-process FD message while suppressing duplicate worker and reload child
messages. The group covers worker startup, shutdown, crashes and replacements,
health-check restarts, inherited IPv4/IPv6 descriptors, TTIN/TTOU, SIGHUP, and
reload from `UVICORN_RELOAD`.

Run `b5228c0251f0492385b1ca422da32659`; receipt
`target/kata-progress/worker-startup-log-parity-focused-20261028.json`,
SHA-256 `aebe48b2e06c899bbf0f538ce9e9826dc1b6d3c4362cdbbff5a7f64d5c72af28`.
It binds Python API input@42 SHA-256
`2712ec38ceb44a2aba16b783435f1d6d6035f8aef212e1f5adf8673b408665b4`, target
revision `885968146a613ad1323d7a0c0a1dd9f3d7be4668` with a dirty tree, source
SHA-256 `f628167194c21d95a8dd71858882f8b0179d90da99161dc387b32f06c5aa9976`,
`python/uvicorn/server.py` SHA-256
`3ed637b75765c44a84ad96a7a2b31cd07e88653d0122a56552a38fd3f0f9cb99`, runner
SHA-256 `42dad293515138a43806baa7b364aca09372a685103757be9341e79512250a87`,
Python API probe SHA-256
`46477f5464dbf8ffbf98f8426666a95d551e8a25bc6689fda9dfb8f63de2fdac`, and
native extension SHA-256
`74fd52144fbc0b168db90da59de02cffaf5e1a037995beb2a3b6b2792a523535`.

## Module-CLI WebSocket and concurrency environment precedence — 2026-10-28

Seven focused cases compare malformed `UVICORN_WS_MAX_QUEUE`,
`UVICORN_WS_PING_INTERVAL`, and `UVICORN_WS_PER_MESSAGE_DEFLATE` diagnostics
with explicit CLI overrides, plus `--limit-concurrency 1` overriding malformed
`UVICORN_LIMIT_CONCURRENCY`. Invalid environment values produce matching
exit code 2 and stderr; the explicit overrides let both module-CLI processes
start and exit 0. The group passed 7/7 against Uvicorn 0.54.0 on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1.

Run `22df1af6e667455886d23af0a723b2be`; receipt
`target/kata-progress/cli-websocket-environment-20261028.json`, SHA-256
`111802b49591e65bd81ff73f8d5cd17bb118e15298dfabb5aca576e36a45cf72`.
It binds CLI input@42 SHA-256
`9e70b50fad81b4b2a122d90046e3c0f9d322c75f09c75c6791212a50382e7714`, target
revision `c64e4ffcd242c9f1a83100898119dd8454120798`, a dirty working tree, source
SHA-256 `eb302a715923469d490bde65c43e8cdff097fd68a6216033921092176b873197`,
runner SHA-256 `f402f9d1eb95969f189139987292ead4cbef7f6bd1543941fcb68ee04f00edbf`,
and native extension SHA-256
`1a168d54b1364f9e6b22eb537aea5f4cd7bd26f214785d402a8f6cb3a83d00bc`.

## Click-derived environment input inventory — 2026-10-28

A read-only inventory audit compared the 52 parameters in pinned Uvicorn 0.54.0
`uvicorn.main.main.params` with environment keys in the maintained CLI and
Python API input files. All 52 derived `UVICORN_*` names have at least one input;
the separate `UVICORN_RS_PARITY_FACTORY_SENTINEL` is a harness variable. This
measures declared input coverage, not behavioral compatibility.

Twelve new CLI environment cases were exercised in focused runs on macOS 15.7.7
ARM64 / CPython 3.12.13 / Rust 1.98.1. The first run passed 11/12; invalid
`UVICORN_LOOP` exposed a warning-order mismatch. After adjusting the candidate's
warning path and stderr normalizer, that single case passed 1/1. Both receipts
bind CLI input@42 SHA-256
`e599244efc6269ce0c6780d248922b7bc1fde1ab71f1d32729439c155eddde0d` and dirty
source based on revision `8cf8ad1fd4348b7d05fff6aa35e77a517152fa4a`:

- Run `70689199b0924b4abbaa992f7883ced0`, 11/12; receipt
  `target/kata-progress/cli-env-bindings-20261028.json`, SHA-256
  `2cf478f4d2a4a91715f2fa18f4d8987c8c5a8b2a5116040d8925e039f1eced64`; source
  SHA-256 `f628167194c21d95a8dd71858882f8b0179d90da99161dc387b32f06c5aa9976`.
- Run `3611e47444a5460983a0a92fca0e9e14`, invalid-loop case 1/1; receipt
  `target/kata-progress/cli-loop-invalid-current-20261028.json`, SHA-256
  `b3741fae5e32bb8a0f0ffcd1c7050737b18b44cb7ac9139047d620f1373266f4`; source
  SHA-256 `77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9`.

Six Python API inputs cover `UVICORN_FORWARDED_ALLOW_IPS` and explicit
precedence, `UVICORN_HEADERS` and explicit precedence, inherited `UVICORN_FD`,
and `UVICORN_SSL_*` TLS configuration. On the same platform, the initial run
passed 5/6; the forwarded-IP case differed only in an ephemeral client port.
After changing that case to use a stable client-address observation, both
forwarded-IP cases passed 2/2. The four other cases passed in the initial run;
their inputs were unchanged by the later route adjustment. The focused receipts
are:

- Run `c968cbad70214bbf8a08ad9b1ac875d0`, 5/6; receipt
  `target/kata-progress/python-api-env-bindings-20261028.json`, SHA-256
  `61ab248b6df5a00422c0be4e0c644af26c1a62c3fb39ca65e6ddb665bd0e3ea0`; it
  binds the earlier Python API input SHA-256
  `349eaf4190d198672fc7f4337412812464f15087df16381150c44670a60e19d9`.
- Run `b324129fe0414d178026cafe824cfb22`, both forwarded-IP cases 2/2; receipt
  `target/kata-progress/python-api-proxy-env-20261028.json`, SHA-256
  `942a4a2d3c3cce6e6799b6a1535fc52f677999e694901d4194510d2b6a560053`; it binds
  the updated Python API input SHA-256
  `8d202f078b9b6e3736a0af360b7c1e01b15cead402d4244e749007f0cd49133b` and dirty
  source SHA-256 `77049980c97caaab495cbbf516b93f213488c549fae214613f4e3c687c70a0e9`.

These selected results are focused receipts. Hosted [CI #435](https://github.com/appunni-m/uvicorn-rs/actions/runs/40591281095)
later passed the complete declared public `input@42` matrix, 660/660, using a
clean-source installed wheel on Linux x86-64. That result does not establish
Windows/macOS parity or full Uvicorn compatibility beyond the declared inputs.

## TLS 1.2 cipher selection

`http1-tls.ssl-ciphers-restricts-negotiated-suite` configures both servers with
`ssl_ciphers="ECDHE-RSA-AES256-GCM-SHA384"` and TLS 1.2, then observes the
negotiated cipher through the client TLS socket. It passed 1/1 against Uvicorn
0.54.0 on macOS 15.7.7 ARM64 / CPython 3.12.13. Both sides negotiated
`ECDHE-RSA-AES256-GCM-SHA384`. Run ID
`8507182448554fce8571e5bd18ea874c`; receipt
`target/kata-progress/ssl-ciphers-negotiated-suite-verified-20261025.json`,
SHA-256 `b3f481298b7214662c27250490bbd0f005c0d1e21179efe20fac45dc186b26b2`;
dirty-source digest
`2d8ba10bd17fdc1cf48b35fa9ee26b42355c78b136662612873ff70c7fd97434`;
TLS input SHA-256
`caaf7b25cd81c45b54a1f4b90bde153c0df7f1bbb47732e063091895404cc145`.
This is one local compatibility case, not full TLS or CLI compatibility
evidence.

`http1.limit-concurrency-returns-503-at-connection-limit` starts both servers
with `--limit-concurrency 1` and sends the same bodyless GET. The selected
Uvicorn 0.54.0 comparison passes on macOS 15.7.7 ARM64 / CPython 3.12.13 for
status, body, content type, server header, and date header. This single case
does not establish behavior for other limits or active HTTP/2 streams. The
separate Python API input below verifies the `uvicorn.run` path.

`python-api.run-applies-concurrency-limit` and
`python-api.config-server-applies-concurrency-limit` each pass 1/1 on macOS
15.7.7 ARM64 / CPython 3.12.13. The first exercises
`uvicorn.run(limit_concurrency=1)`; the second constructs
`uvicorn.Config(limit_concurrency=1)` and calls `uvicorn.Server.run()` in both
processes. Both compare the 503 status, content type, response body, SIGINT
shutdown outcome, and server process exit without comparing
implementation-specific log text. This covers the limit-1 HTTP/1.1 behavior
through the CLI and two Python API paths; other values and protocols remain
open.

The H2/H3 rows are same-protocol ASGI observations against Hypercorn. They are
not described as Uvicorn parity. Server versions and protocol components are
exact requirements in `tests/parity/manifest.json`; a version mismatch
invalidates a run rather than silently changing the oracle. The result also
records the exact Python/runtime versions and native-extension/Cargo-lock
digests for the target.

## Scope and comparison rules

For Python API HTTP-run cases, the result artifact retains raw child stdout and
stderr and parity compares their normalized log events as well as the probe
exit status, HTTP response, shutdown signal, and process outcome. Log events
preserve channel, severity, lifecycle message, access request/status, and
exception class/message. Normalization removes ANSI escapes, replaces process
IDs and ephemeral ports, and omits traceback source paths and line numbers;
the raw logs remain available for review. The focused `Config`/`Server.run()`
and `uvicorn.run()` cases cover default startup, access, and shutdown logging.
Python API calls also retain warnings emitted during each input-selected call
as category and message. The current selected import/signature case compares
the deprecation warning from `uvicorn.main.ServerState` with Uvicorn 0.54.0.
The `python-api.run-applies-numeric-warning-log-level` case emits DEBUG through
CRITICAL application log events and verifies that numeric level 30 keeps
WARNING, ERROR, and CRITICAL while suppressing DEBUG and INFO. The module CLI
cases verify that `--log-level warning` suppresses startup and access INFO
events, `UVICORN_LOG_LEVEL=debug` enables DEBUG application logs, and an
explicit warning option overrides the debug environment value. Other level
and precedence combinations remain unverified. `python-api.run-disables-access-log` and
`python-api.module-cli-disables-access-log` compare `uvicorn.run(access_log=False)`
and `python -m uvicorn --no-access-log`; both suppress the request access event
while preserving the other selected startup and shutdown observations. Other
levels, colors, and exact traceback frame formatting remain unverified. The
`python-api.run-applies-custom-json-log-config` and
`python-api.module-cli-applies-custom-json-log-config` inputs exercise a
user-supplied JSON logging configuration through both public entry points and
compare the resulting application log events against Uvicorn 0.54.0.
The corresponding `python-api.run-applies-custom-ini-log-config` and
`python-api.module-cli-applies-custom-ini-log-config` inputs do the same for
Python's `fileConfig` INI format. The `python-api.run-applies-custom-yaml-log-config`
and `python-api.module-cli-applies-custom-yaml-log-config` inputs use PyYAML
through both entry points. PyYAML is in the benchmark group for parity runs and
in the package's `[standard]` extra for users. The separate
`python-api.module-cli-uses-log-config-from-environment` input confirms the CLI
loads the configured file from `UVICORN_LOG_CONFIG`.

The active manifest and input schema are `uvicorn-rs-parity/manifest@2` and
`uvicorn-rs-parity/input@40`; live artifacts use
`uvicorn-rs-parity/result@5`. Each result records a per-file inventory of the
Rust server and adapter sources, Python `uvicorn` and `uvicorn_rs` modules,
workspace manifests and lockfiles, plus the imported native extension digest.
The harness receipt also fingerprints the runner, source-identity helper,
fixture app, and Python API probe. Earlier archived reports retain their
original schema and identities. Input schema @35 added TLS cipher selection
and negotiated-cipher observation. Input schema @36 added a Python API TLS-key password input;
`scripts/migrate_parity_input_v35_to_v36.py` advances those inputs. Schema @37
adds Python API TLS key format, trust roots, certificate requirements, client
certificates, and TLS-version inputs; `scripts/migrate_parity_input_v36_to_v37.py`
advances maintained documents without changing existing case values. Schema @38
adds an opt-in Python API HTTP-run setting that omits the explicit
`--root-path` option so module-CLI cases can verify `UVICORN_ROOT_PATH`;
`scripts/migrate_parity_input_v37_to_v38.py` advances maintained documents
without changing existing case values. Schema @39 added module-CLI repeated shutdown-signal delivery for a held ASGI
request and an operation that records but does not compare platform-specific
shutdown tracebacks; `scripts/migrate_parity_input_v38_to_v39.py` advances
maintained documents without changing existing case values. Schema @40 adds an
optional module-CLI graceful-shutdown timeout argument to Python API HTTP-run
inputs; `scripts/migrate_parity_input_v39_to_v40.py` advances maintained input
documents without changing their existing case values.

See the [ASGI behavior inventory](asgi-case-inventory.md) for the declared
surface mapped to concrete public case IDs and explicit gaps.

`tests/parity/manifest.json` indexes input-only case files under
`tests/parity/inputs/`; a file can hold multiple cases for one profile. Inputs
contain CLI invocation mode, arguments, environment overrides, working
directory and timeout; network inputs contain request methods, paths, headers,
body bytes, WebSocket messages, disconnect workflows, and shutdown workflows.
They do not contain expected responses or previously captured server output.
The current 114 indexed CLI cases compare module and installed-console invocations,
selected parsing and environment-precedence behavior, current-directory app
import resolution, app loading, environment files, JSON log-config diagnostics,
explicit default runtime options, protocol-selector (including `--http h11`)
and SansIO WebSocket size/queue-option acceptance, unknown-option rejection,
limited single-process worker settings, `--limit-max-requests 0` startup
shutdown, `--ws-ping-interval 0` startup acceptance, malformed
`UVICORN_INTERFACE` rejection and explicit override of that malformed value,
plus malformed `UVICORN_LOG_LEVEL`, `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`,
`UVICORN_LIMIT_MAX_REQUESTS`, `UVICORN_LIMIT_MAX_REQUESTS_JITTER`,
`UVICORN_BACKLOG`, `UVICORN_TIMEOUT_KEEP_ALIVE`,
`UVICORN_TIMEOUT_WORKER_HEALTHCHECK`,
`UVICORN_WS_MAX_SIZE`, and `UVICORN_WS_PING_TIMEOUT` rejection and
explicit-option precedence.
The new cases also cover environment-selected version and factory behavior,
invalid/overridden FD and h11-size values, SSL option validation and precedence,
HTTP/2, loop selection, and UDS startup. A static inventory audit of the pinned
Uvicorn 0.54.0 Click parameters against the combined CLI and Python API input
files finds all 52 derived `UVICORN_*` names represented. This is declared input
coverage only; it does not prove that every binding's behavior passes. The new
Python API inputs also cover environment-provided forwarded-IP policy, response
headers, inherited FD, and TLS options.
The zero-interval case
does not open a WebSocket or verify active-session Ping suppression. The selected
`cli.no-arguments-requires-app` case passes 1/1 with matching exit 2, missing-`APP`
stderr, and empty stdout (see the [maintainer receipt](maintainers/uvicorn-0.54.0-contract.md)).
Selector cases check argument handling;
they do not prove that every option is executed or establish full multi-worker
supervision. One separate reload input changes a watched Python module and
verifies the new response plus graceful SIGINT exit on local macOS ARM64 /
CPython 3.12.13 with `--workers 2`, both without `watchfiles` and with
`watchfiles==1.3.0`. It also compares the warning that reload ignores the
worker count. The candidate's `StatReload` fallback and `WatchFilesReload`
paths both pass. The selected
`python-api.module-cli-reload-respects-include-exclude-globs` case also passes
1/1 with `WatchFilesReload`: changing `ignored.txt` leaves the app response
unchanged, while changing the included `included.txt` reloads the app and
updates the response. Receipt `target/kata-progress/dhfq-reload-filters-20261024.json`
(run ID `35c7bac2545c47968ee1aaa715806fef`, SHA-256
`135b3c57f486b99815027e3ca7bbfe8b336c331e303d489e305f3fefa647f064`)
binds this case to dirty-source SHA-256
`e7d3f0ca2c6d82c31eb675e3090d6ba8a16797a498689077c881b427b6683ecf` on macOS
ARM64 / CPython 3.12.13. It does not qualify other filter patterns or
platforms. Five
inherited-listener cases verify IPv4 TCP listeners on macOS through the module
CLI, `uvicorn.run(fd=...)`, `Config(fd=...)` with
`Server.run()`, and `Server.run(sockets=[...])` with one and two sockets. Two
additional module-CLI cases verify inherited IPv6 listeners with one and two
workers on macOS ARM64 / CPython 3.12.13 (run
`bc282b37f69a46a38e8353a94197e2a7`, report SHA-256
`f55d9d1f8227452b0513446e2b96241fc63277c1f359ca761fb570a0ea94ca0f`). Other
IPv6 API paths, Windows, TLS, and HTTP/2 or HTTP/3 over inherited sockets remain
unverified. Focused Python API inputs cover plain HTTP/1.1 over UDS
through the module CLI and `Config`/`Server`. The selected
`python-api.server-startup-uds-replaces-existing-socket-and-shuts-down-lifespan`
case also checks replacement of an existing UDS pathname and lifespan cleanup
through `Server.serve()`; its one-case dirty-source receipt is documented in
the [maintainer evidence](maintainers/uvicorn-0.54.0-contract.md#existing-uds-pathname-replacement-and-lifespan-cleanup).
These cases do not establish UDS behavior over other protocols or TLS. The fixture app is
shared source code imported in fresh, independent oracle and target processes.
Its exported ASGI callable is synchronous and returns an awaitable. The
Uvicorn adapter forces `--interface asgi3`; the Hypercorn adapter uses its
`asgi:` selector. Both then execute the same callable under the ASGI 3
contract. The profile split keeps protocol-specific stimulus easy to review;
the runner also checks the indexed-file set against the files on disk.

The `http.response-headers` operation records ordered wire fields but compares
duplicate values in order within each header name. The separate
`http.response-headers-ordered` operation compares the complete observed field
sequence. Two focused H1 inputs now pass that strict operation using the local
Hyper `HeaderOrder` extension: one with custom headers and disabled Server/Date
defaults, and one with the defaults enabled. These are separate, source-bound
dirty-draft receipts, not a full H1 response-header matrix. Other H1 cases
still use the normalized operation; the focused H2 observation still differs
from Uvicorn, and H3's client observation passes through `http::HeaderMap` and
does not prove raw wire order. RFC 9110 §5.3 states that order across different field names is not
significant to HTTP semantics; the ASGI HTTP 2.5 response-start contract is
stricter and requires preserving the application order. See [RFC 9110 §5.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.3),
the [ASGI HTTP specification](https://asgi.readthedocs.io/en/latest/specs/www.html),
and the [support matrix](support-matrix.md#supported-behaviors). The per-run
receipt is a local ignored artifact.
For this operation, manifest `observe` retains the wire order and its optional
`compare` list selects the normalized fields used for parity; other operations
compare every observed field by default. The offline CI evidence checker uses
the same comparison projection while still requiring the full observed fields
to be present in both live observations. An operation may declare
`target_requirements` for a normative target behavior when the oracle has a
known protocol deviation; the runner and offline evidence checker enforce those
values on the target observation, while retaining but not comparing the
reference-specific diagnostic fields.

The previous combined input is retained in `tests/parity/archive/` because an
older result artifact records its digest.

The current cases cover:

- plaintext and TLS graceful shutdown that observes refused new connections
  while the process and held response remain active, then releases the response
  and checks its complete bytes, application events, and clean connection close;
  an idle connection carrying a partial HTTP/2 preface must also close without
  causing a transport-failure diagnostic;

- HTTP scope observations, query/header/body transport, status and response
  content type;
- invalid ASGI event and missing `response.start` handling over HTTP/2 and
  HTTP/3, including the empty HTTP/3 500 body matched to Hypercorn;
- a synchronous ASGI callable returning an awaitable, exercised by the HTTP/1.1
  live parity case;
- ordered response streaming and streamed request-body echo;
- H1/H2 response delivery before the app sends its final body event, and a
  response chunk delivered before the client finishes its upload;
- an HTTP/3 response completed while the client keeps a partial POST upload open;
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

The `http3.upload-body-shorter-than-content-length` input deliberately violates
HTTP message framing. Its `http3.invalid-content-length-status` operation
compares only the response status because the reference server does not produce
a stable response body for this malformed request. The case does not claim
body parity or general malformed-framing compatibility.

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
case input-only: do not put captured reference responses in the manifest or
inputs. Operations may declare positive contract invariants, such as a
completed shutdown or a response delivered before the application returns.
Both live implementations must satisfy those invariants as well as agree on
their observations. Target-only fault predicates belong in the runner and
must check public failure, cleanup, or follow-up behavior.
The adapter compares live outputs and stores any mismatches in the generated
result. Add a new oracle profile only for a protocol the current oracle cannot
serve, and state why that server is a valid same-protocol reference. Update the
support matrix when a new behavior is covered, and keep unsupported or
unmeasured cases explicit.

The input loader rejects unknown fields, unsupported schemas, duplicate case
IDs, unindexed files, undeclared profiles/operations, invalid body encodings,
unrepresented declared operations, and observed output fields embedded in
active cases. The runner validates these fail-closed properties before starting
servers and verifies that result accounting cannot omit a selected case. It
selects adapters by declared profile and workflow shape, never by case ID.

Input schema `@10` added optional `headers` and `observe_headers` fields to the
Python API HTTP-run stimulus. Schema `@11` adds optional `interface` and
`application_interface` fields so cases can select Uvicorn's ASGI interface
and the shape of the application callable. Schema `@12` adds an optional,
strict `server_options` object for WebSocket profiles, so the oracle and target
receive the same declared setting. Schema `@13` adds a programmatic WebSocket
run stimulus to the Python API profile. Migrate maintained `@10` inputs with
`python scripts/migrate_parity_input_v10_to_v11.py`, then `@11` inputs with
`python scripts/migrate_parity_input_v11_to_v12.py`, then `@12` inputs with
`python scripts/migrate_parity_input_v12_to_v13.py`. Schema `@14` adds HTTP
proxy server options and Python API request-header/scope stimuli. Migrate
maintained `@13` inputs with `python scripts/migrate_parity_input_v13_to_v14.py`;
each migrator changes only the schema marker and preserves existing case data.
Schema `@15` adds optional process-environment overrides to Python API HTTP-run
inputs so environment-derived settings can be compared with explicit API
arguments. Migrate maintained `@14` inputs with
`python scripts/migrate_parity_input_v14_to_v15.py`; the migrator changes only
the schema marker and preserves existing case data.
Schema `@16` allows proxy-header settings in WebSocket server options for
scheme/scope parity cases. Schema `@17` allows `limit_concurrency` in HTTP
server options. Migrate maintained `@15` inputs with
`python scripts/migrate_parity_input_v15_to_v16.py`, then `@16` inputs with
`python scripts/migrate_parity_input_v16_to_v17.py`; both migrators change only
the schema marker and preserve existing case data. Schema `@18` allows
`limit_concurrency` in the Python API HTTP-run stimulus; migrate maintained
`@17` inputs with `python scripts/migrate_parity_input_v17_to_v18.py`.
Schema `@19` allows the Python API HTTP-run stimulus to invoke `Config` and
`Server.run()` directly; migrate maintained `@18` inputs with
`python scripts/migrate_parity_input_v18_to_v19.py`. This migrator changes only
the schema marker and preserves existing case data.
Schema `@20` adds fixed Python API and module CLI startup-failure stimuli for
`lifespan="on"`; migrate maintained `@19` inputs with
`python scripts/migrate_parity_input_v19_to_v20.py`. This migrator changes only
the schema marker and preserves existing case data. Schema `@21` adds optional
public `method_calls` after a Python API call, allowing cases to compare methods
such as `Config.load()` on constructed objects; migrate maintained `@20` inputs
with `python scripts/migrate_parity_input_v20_to_v21.py`. This migrator changes
only the schema marker and preserves existing case data. Schema `@22` adds
optional event-loop selection and observation to Python API HTTP-run inputs;
migrate maintained `@21` inputs with
`python scripts/migrate_parity_input_v21_to_v22.py`. This migrator changes only
the schema marker and preserves existing case data. Programmatic HTTP-run inputs
may use a `module:factory` loop import path; the module CLI remains limited to its
supported loop selectors, and a focused `uvicorn.run()` case observes that the
returned custom loop is active.
Schema `@24` adds an optional custom logging-config path to Python API HTTP-run
inputs; migrate maintained `@23` inputs with
`python scripts/migrate_parity_input_v23_to_v24.py`. The migration changes only
the schema marker and preserves existing case data.
Schema `@25` adds an optional factory flag to Python API HTTP-run inputs;
migrate maintained `@24` inputs with
`python scripts/migrate_parity_input_v24_to_v25.py`. This migration changes
only the schema marker and preserves existing case data.
Schema `@26` adds an optional backlog value to Python API HTTP-run inputs;
migrate maintained `@25` inputs with
`python scripts/migrate_parity_input_v25_to_v26.py`. This migration changes
only the schema marker and preserves existing case data.
Schema `@27` adds optional `timeout_keep_alive` and
`keep_alive_probe_delay_seconds` values to Python API HTTP-run inputs;
migrate maintained `@26` inputs with
`python scripts/migrate_parity_input_v26_to_v27.py`. This migration changes
only the schema marker and preserves existing case data.
Schema `@28` permits WSGI as the selected server and application interface in
Python API HTTP-run inputs; migrate maintained `@27` inputs with
`python scripts/migrate_parity_input_v27_to_v28.py`. This migration changes
only the schema marker and preserves existing case data.
Schema `@29` permits `workers` and `timeout_worker_healthcheck` in Python API
HTTP-run inputs; migrate maintained `@28` inputs with
`python scripts/migrate_parity_input_v28_to_v29.py`. This migration changes
only the schema marker and preserves existing case data.
Schema `@30` permits `uds` and `observe_unix_scope` in Python API HTTP-run
inputs; migrate maintained `@29` inputs with
`python scripts/migrate_parity_input_v29_to_v30.py`. This migration changes
only the schema marker and preserves existing case data. Schema `@31` adds
`prebound_socket_count` to public Python API cases; migrate maintained `@30`
inputs with `python scripts/migrate_parity_input_v30_to_v31.py`. Schema `@32`
adds `headers`, `server_header`, and `date_header` to HTTP `server_options` so
repeated CLI response-header settings can be compared; migrate maintained
`@31` inputs with `python scripts/migrate_parity_input_v31_to_v32.py`. Both
migrations change only the schema marker and preserve existing case data.
Schema `@33` adds `reset_contextvars` to HTTP server options; migrate maintained
`@32` inputs with `python scripts/migrate_parity_input_v32_to_v33.py`. This
migration changes only the schema marker and preserves existing case data.
Schema `@41` adds the `@probe-port` marker for module-CLI HTTP-run inputs;
the probe substitutes its dynamically reserved listener port into
`UVICORN_PORT` and omits explicit `--host`/`--port` arguments when those
settings are supplied by the environment. Migrate maintained `@40` inputs with
`python scripts/migrate_parity_input_v40_to_v41.py`; this changes only the
schema marker and preserves existing case values.
Schema `@42` allows module-CLI HTTP concurrency cases to source their limit
from `UVICORN_LIMIT_CONCURRENCY`; migrate maintained `@41` inputs with
`python scripts/migrate_parity_input_v41_to_v42.py`. Schema `@43` adds
`request_body_chunks_base64` to Python API WSGI POST inputs so cases can declare
multiple HTTP transfer chunks; migrate maintained `@42` inputs with
`python scripts/migrate_parity_input_v42_to_v43.py`. Both migrations preserve
existing case data and change only the schema marker.
The runner rejects older or mixed input schemas.

## CI evidence

Main CI executes the complete public matrix on an installed normal wheel and
retains its structured result, log, consumer check and normal-build exclusion
audit as `uvicorn-rs-public-parity` for 90 days, including failed runs. A concise
annotation identifies each failing case or infrastructure error.

The separate unified native report retains individual case attribution and
three full repeats as `uvicorn-rs-unified-coverage`. The Linux candidate wheel
also runs the complete public matrix on the exact shipping binary. The
evidence checker verifies current source, native, input and harness identities;
tag assembly requires clean receipts from successful CI on the exact commit.
The former Python unit-test module has been removed; maintained verification
uses these live workflows and evidence contracts. See [release gates](releases.md)
for platform scope and the separate Coverage-MCP review.
