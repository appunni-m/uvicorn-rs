# Hosted benchmark #13 disconnect-case local reproduction

This focused reproduction reran the exact-commit normal release wheel on a clean detached checkout of `72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f` after macOS ARM64 benchmark job `114240719626` reported `http1.disconnect-before-first-asgi-receive` with a generic public-field mismatch.

## Result

The input-only parity case passed **10/10** independent runner invocations on macOS ARM64. Each run matched the oracle and target exactly:

- `disconnect_event`: `true`
- follow-up response: HTTP 200, body `http.disconnect`, connection kept alive

This does not reproduce or explain the hosted mismatch. The hosted annotation does not contain the differing observation values, and the benchmark artifact is not downloadable anonymously. The exact case row was requested so the hosted values can be compared.

## Identity

- Commit: `72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f` (clean)
- Rust source SHA-256: `56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`
- Normal native extension SHA-256: `9a4861fffa5e761b41b32c953939f7d29bf8e642363538635a80cf21ca10b057`
- Runner SHA-256: `ad87c439762344df83e1156d1e4cf65e5ab8486d654c2d46485ce338aa3977ed`
- App fixture SHA-256: `122691ef690520c5dd681e72913ca8ae2635cd17413118c81510b112a24f4454`
- HTTP/1 input SHA-256: `0ab368fc6f49057c4dd85bb1215f5c2142563206c7033bb46ad378b5ddf50ed3`
- Python: `3.12.13`
- OS: `macOS-15.7.7-arm64-arm-64bit`
- Uvicorn reference: `0.54.0`
- Rust: `rustc 1.98.1 (48a229cea 2026-09-01)`

## Reproduction

```sh
.venv/bin/python scripts/run_parity.py \
  --case-id http1.disconnect-before-first-asgi-receive \
  --output /tmp/disconnect-parity.json
```

The ten raw results are `repeat-1.json` through `repeat-10.json`; `repeat-summary.json` records each run ID and file digest.
