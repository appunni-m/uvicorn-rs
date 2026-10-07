# macOS ARM64 package reproduction for CI run #35

This local run reproduces the macOS ARM64 wheel build and installed-wheel
consumer step that failed in [CI run #35](https://github.com/appunni-m/uvicorn-rs/actions/runs/37672645704).

## Result

- macOS 15.7.7 ARM64; CPython 3.12.10 for both wheel build and consumer.
- Rust/Cargo 1.98.1; Maturin 1.14.1.
- `maturin build --release --locked` produced
  `uvicorn_rs-0.1.0-cp39-abi3-macosx_11_0_arm64.whl`.
- The exact wheel installed in a fresh CPython 3.12.10 environment and
  `scripts/check_installed_wheel.py` passed.
- `scripts/release_evidence.py record --allow-dirty` validated the wheel,
  consumer receipt, metadata, RECORD hashes, licenses and native architecture.
- Wheel SHA-256:
  `ab3ac30886a0cbddccbf127fda1a54df895e8ebff3da026cfb937a87dcca7282`.
- Native extension SHA-256:
  `0e75d893144bb2a87819904e7356a532ca844eaef7b35d16d97b54e6cffb1485`.

The build manifest deliberately records `state: local preparation` and
`source_dirty: true`. This is a diagnostic reproduction, not a candidate
artifact and not evidence that explains the hosted runner failure. The job log
for run #35 was not available through the unauthenticated Actions endpoint.

## Reproduction

With CPython 3.12.10 installed as `PY31210`:

```sh
uvx --from maturin==1.14.1 maturin build --release --locked \
  --interpreter "$PY31210" --out dist
uv venv --python "$PY31210" /tmp/uvicorn-rs-consumer
uv pip install --python /tmp/uvicorn-rs-consumer/bin/python \
  --no-deps dist/uvicorn_rs-0.1.0-cp39-abi3-macosx_11_0_arm64.whl
/tmp/uvicorn-rs-consumer/bin/python scripts/check_installed_wheel.py \
  --wheel dist/uvicorn_rs-0.1.0-cp39-abi3-macosx_11_0_arm64.whl \
  --output dist/consumer-macos-arm64.json
```

`build-manifest-macos-arm64.json` binds the exact checkout source hashes,
toolchain, wheel and consumer receipt. `SHA256SUMS` covers every file in this
archive except itself.
