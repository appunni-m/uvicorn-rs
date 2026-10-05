# Unmodified Hypercorn HTTP/3 diagnostics

All original directories, empty checkpoints, metadata, complete reports,
runner logs and server error logs are retained byte for byte. Package source
and native files were checked against their installed RECORD hashes in the
original evidence; no edited or editable reference distribution is recorded.
The reference was Hypercorn 0.18.0 with aioquic 1.3.0 and uvloop 0.23.0.

- `c1-1s-warm0-20261005-a`: sandbox/infrastructure failure finding a numeric
  port available to TCP and UDP; no load or server outcome was recorded.
- `c1-1s-warm0-20261005-b`: concurrency-one functional observation passed its
  response/lifecycle checks, with an empty server log. Its timing remained
  invalid due to unrelated host CPU activity and is not a speed comparison.
- `c16-1s-warm0-20261005-a`: the client timed out awaiting H3 response headers;
  the retained client diagnostic in `runner.log` records 69 completed requests
  and 16 failures. The full
  post-shutdown server log contains an unhandled UDP-task ExceptionGroup with
  `KeyError(72)` and the terminal `KeyError: 72`, along with the task-group
  shutdown error. `72` is the stream key, not a count of 72 errors. The category
  deliberately has no successful final report or fabricated successful row.

These functional diagnostics do not prove an upstream root cause and do not
justify altering the stock reference or reducing the concurrency of a purported
matched performance comparison. `summary.json` classifies the recorded outcomes;
the raw logs remain authoritative and unchanged.
