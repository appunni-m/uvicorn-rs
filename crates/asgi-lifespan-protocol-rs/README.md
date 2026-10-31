# asgi-lifespan-protocol-rs

`asgi-lifespan-protocol-rs` defines runtime-neutral startup and shutdown hooks
for Rust web applications. Its API is intentionally small: the lifecycle
trait, its boxed future and error types, and the startup/shutdown stage enum.
It does not define HTTP request/response, routing, middleware, or ASGI APIs.

Frameworks can implement the hooks without depending on a server or async
runtime; a server decides when to invoke them and applies the deadlines. The
Python-free `uvicorn-rs` server depends on and re-exports this crate, so
frameworks can depend on this contract without taking a dependency on the
server itself. The package name identifies its ASGI lifecycle role while
remaining independent of any particular server or runtime.

## Requirements

- Rust 1.85 or newer
- Rust 2024 edition
- No runtime dependency and no optional Cargo features

## Install

Version 0.2.0 is prepared for the next release. The version below is a Cargo
semver requirement, not an exact patch pin. A committed `Cargo.lock` selects
the exact versions for an application build.

```toml
[dependencies]
asgi-lifespan-protocol-rs = "0.2"
```

## Implement lifecycle hooks

```rust
use asgi_lifespan_protocol_rs::{
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
