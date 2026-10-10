# Hosted benchmark #13 disconnect-case evidence

This evidence compares the exact hosted failure with 60 focused runs of the normal release wheel from a clean detached checkout of `72dfa51f98a3a3518679ccaf7115d3bae6d8ac5f`. The 50 additional local reports were collected after the hosted `parity.json` row was supplied.

## Hosted result

The artifact row for `http1.disconnect-before-first-asgi-receive` is preserved in [hosted-parity-failure.json](hosted-parity-failure.json). Uvicorn's follow-up body is `http.disconnect`; uvicorn-rs's is `http.request,http.disconnect`. Both observations report a disconnect, status 200, an open keep-alive connection, and successful follow-up response. This is an actual first-event ordering mismatch, not the separate expected missing-certificate startup failure.

The hosted run is [benchmark #13](https://github.com/appunni-m/uvicorn-rs/actions/runs/38061568654), artifact `11673441894`, macOS ARM64 job `114240719626`. It failed parity before timing. The hosted source SHA-256 was `56cccea49215b2b96cf7028ec01804c7142b0f364f91bbd957b1114ab13b65fb`; the wheel SHA-256 was `f1ceeb5b9ee97c52535f30369c415fe63068352936c2b87ee910bd9201a3f9bf`. It ran Python 3.12.13, Uvicorn 0.54.0, and uvloop 0.23.0 on a three-CPU macOS 15.7.9 ARM64 virtual M1 runner.

## Local exact-commit repetitions

The same input-only case passed **60/60** independent invocations on local macOS ARM64. Every oracle and target observation matched: `disconnect_event=true`, follow-up status 200, follow-up body `http.disconnect`, and connection kept alive. The first ten runs are `repeat-1.json` through `repeat-10.json`; the additional fifty are `repeat-11.json` through `repeat-60.json`. [repeat-summary-60.json](repeat-summary-60.json) includes every report digest and run ID.

This local evidence does not erase or explain the hosted mismatch. The fixture waits 50 ms after its app-side checkpoint, but that delay does not acknowledge that the Rust connection task observed TCP EOF before the app's first `receive()`. Hyper's HTTP/1 connection is expected to poll for EOF during the request; source inspection has not established why the hosted event order differed. The root cause remains unconfirmed, and no production fix is claimed.

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

The 60 raw results are `repeat-1.json` through `repeat-60.json`. `repeat-summary-60.json` records all report digests and run IDs. `hosted-parity-failure.json` contains only the relevant row from the user-provided archive; the archive's unrelated contents were not imported.
