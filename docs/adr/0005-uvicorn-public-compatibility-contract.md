# ADR 0005: Uvicorn public compatibility contract

- **Status:** Accepted
- **Date:** 2026-10-19
- **Supersedes:** The Uvicorn CLI/API non-goal in [ADR 0003](0003-rust-native-service-contract.md)

## Context

The project now has two server paths: a Python-free Rust library for Rust services and a Python adapter for standard Python ASGI applications. The earlier decision treated full Uvicorn CLI/API compatibility as out of scope. The product goal has changed: a Python user should eventually be able to install the `uvicorn-rs` PyPI distribution in place of upstream Uvicorn and continue using the `uvicorn` command, import namespace, public APIs, and documented server behavior.

The PyPI distribution is named `uvicorn-rs`, following the project's `pillow-rs` convention. The installed Python module and executable are intentionally named `uvicorn` so existing applications and deployment commands can keep their expected interface. The root Cargo integration package and optional extra console script retain the internal name `uvicorn-rs-py`. The package is experimental and has not yet passed this contract.

## Decision

1. Keep uvicorn-rs as the Python-free Rust server package, independent of Starlette-RS and FastAPI-RS.
2. Name the PyPI distribution `uvicorn-rs`. When released as a replacement, it provides the `uvicorn` import namespace and console command.
3. Use upstream Uvicorn 0.54.0 as the initial pinned compatibility reference. Record the source revision and version. Before a public compatibility release, confirm that the selected reference remains appropriate. Adopting a later Uvicorn release requires an explicit version decision and parity requalification; a passing version does not imply future-version support.
4. Match the documented user-facing public surface for the declared version: CLI options and outputs, environment settings and precedence, imports and signatures, app-loading modes, protocols, lifespan, signals, sockets, reload, workers, graceful shutdown, and errors.
5. Keep Python code as a thin adaptation layer. Rust owns the network runtime and protocol implementation. Python ASGI applications remain on their Python-owned asyncio or uvloop loop; Python callables, context, ASGI messages, exceptions, and cancellation must retain their required semantics at that boundary.
6. Prove claimed behavior through the existing input-only parity system against a live upstream Uvicorn installation and the installed `uvicorn-rs` artifact. Do not treat an ASGI-only protocol pass as proof of CLI/API compatibility.
7. Do not claim drop-in compatibility or publish a compatible release until the complete declared matrix passes for the supported Python and operating-system combinations.

## Installation and package ownership

The two distributions install overlapping `uvicorn` files. Users must uninstall upstream Uvicorn before installing `uvicorn-rs` in the same environment. The documented replacement guide must include a rollback procedure that removes `uvicorn-rs` and reinstalls the chosen upstream Uvicorn version. Installing both distributions together is unsupported because their file ownership overlaps.

This does not require taking ownership of the upstream PyPI distribution name uvicorn. The Rust Cargo package remains usable without Python.

## Consequences

- The current `uvicorn-rs-py` extra command and `uvicorn_rs.Server` API are prototype interfaces. They do not satisfy this ADR.
- The compatibility inventory and support matrix must distinguish current behavior, planned behavior, and version-qualified verified behavior.
- Options that are not implemented must fail or be reported unsupported; silently accepting and ignoring them is not compatibility.
- The Rust runtime, Python package layout, public Python API, process control, documentation, candidate artifact, and CI parity matrix all become release gates.
- Compatibility with Starlette-RS and FastAPI-RS native service composition remains a separate Rust integration. Their Python adapters remain separate packages and do not create a server dependency in the native framework crates.
