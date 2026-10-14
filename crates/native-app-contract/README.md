# native-app-contract

`native-app-contract` defines runtime-neutral startup and shutdown hooks for
Rust web applications. Frameworks implement the trait without depending on a
server or async runtime; a server decides when to invoke the hooks and applies
the deadlines.

## Requirements

- Rust 1.85 or newer
- Edition 2021
- No runtime dependency and no optional Cargo features

## Install

This repository currently prepares source-archive candidates. Registry
publication is outside the release workstream. The versioned dependency below
applies after publication; use a local checkout or reviewed candidate archive
for the prototype.

```toml
[dependencies]
native-app-contract = "0.1"
```

## Implement lifecycle hooks

```rust
use native_app_contract::{
    ApplicationLifecycle, ApplicationLifecycleError, ApplicationLifecycleFuture,
};

struct Lifecycle;

impl ApplicationLifecycle for Lifecycle {
    fn startup(&self) -> ApplicationLifecycleFuture<'_> {
        Box::pin(async { Ok::<(), ApplicationLifecycleError>(()) })
    }

    fn shutdown(&self) -> ApplicationLifecycleFuture<'_> {
        Box::pin(async { Ok::<(), ApplicationLifecycleError>(()) })
    }
}

fn main() {
    let lifecycle = Lifecycle;
    let _startup = lifecycle.startup();
    let _shutdown = lifecycle.shutdown();
}
```

Return failures as `Err`. A server may cancel a hook by dropping its future
when the configured timeout expires. Startup runs before request acceptance;
shutdown runs after request draining or cancellation. This contract does not
define ASGI lifespan messages.

## Use with a server

The Python-free [`uvicorn-rs` server](https://github.com/appunni-m/uvicorn-rs/blob/main/crates/uvicorn-rs/README.md)
re-exports this contract and accepts an `Arc<dyn ApplicationLifecycle>` in
`ServerConfig::application_lifecycle`. See its
[support matrix](https://github.com/appunni-m/uvicorn-rs/blob/main/docs/support-matrix.md)
for the server behavior and current limitations.

This crate has no dependency on Uvicorn-RS, Starlette-RS, FastAPI-RS, PyO3, or
Tokio. It is licensed under either BSD-3-Clause or MIT, at your option. The
crate archive includes both license texts and the required attribution
notices.
