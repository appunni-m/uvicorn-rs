# HTTP/3 task reaping: failed coverage attempt 1

Frozen source `c7bd494d…`, instrumented native `41bf61b2…`, 450 inputs. Every individual attribution case passed, but the required full gate failed.

- Regions: 4,776/4,778; lines: 3,369/3,371. The two missing regions are the owned HTTP/3 request-task final drain.
- Unfiltered Coverage-MCP: one function group, two missing observations; source matches; tests failed.
- Complete repeats 1 and 2: 403 passed, one infrastructure error, 46 not run. Repeat 3: 402 passed, two infrastructure errors, 46 not run. No infrastructure retries.
- All repeats timed out in stock Hypercorn on the first public 128-request sequence. Repeat 3 additionally recorded a Uvicorn WebSocket TLS handshake timeout.
- The separate old/new regression proof passed its defending checks: identical two healthy responses; old deferred joins observed the task error only after peer close; current live reaping observed it before peer close. This does not compensate for the failed full gate.

The gzip reports and attribution tar preserve original bytes. Source/input snapshots, raw repeat results and logs, baseline common coverage-only seam, build receipts, and superseded 449-case attempts are retained. Binary extensions and raw LLVM profiles remain under the referenced local build paths and are not committed. No successful 100% coverage claim applies to this attempt.
