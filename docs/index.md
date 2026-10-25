# uvicorn-rs

The PyPI distribution is named `uvicorn-rs` and provides the familiar
`uvicorn` command and import namespace. It has not been released yet, and the
current source does not match Uvicorn's full public contract. If you need
verified drop-in behavior today, keep using upstream Uvicorn.

## Choose what you want to do

- **Check before replacing Uvicorn:** [compatibility status, future install
  steps, and rollback instructions](uvicorn-compatibility.md).
- **Try a Python app from a checkout:** [quickstart](quickstart.md). This does
  not install a released distribution or prove full compatibility.
- **Configure or deploy an evaluation:** [configuration](configuration.md)
  and [deployment guidance](deployment.md).
- **Check protocol and ASGI behavior:** [support matrix](support-matrix.md).

The Rust library is Python-free. The `uvicorn-rs-py` name refers to the
internal Cargo/PyO3 adapter, not the PyPI distribution.

## Project information

- [Benchmark results](benchmark-results.md)
- [Contributing](https://github.com/appunni-m/uvicorn-rs/blob/main/CONTRIBUTING.md)
- [Security reporting](https://github.com/appunni-m/uvicorn-rs/blob/main/SECURITY.md)
- [Support expectations](https://github.com/appunni-m/uvicorn-rs/blob/main/SUPPORT.md)
- [License](https://github.com/appunni-m/uvicorn-rs/blob/main/LICENSE)

Architecture decisions, detailed protocol evidence, coverage, benchmark methods, and release engineering are grouped under Maintainers in the site navigation.
