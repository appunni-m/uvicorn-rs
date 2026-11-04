#![forbid(unsafe_code)]
#![warn(missing_docs)]

//! Runtime-neutral lifecycle contracts for Rust-native web applications.
//!
//! Frameworks can implement these hooks without depending on a server or an
//! async runtime. A server owns when hooks run and applies its configured
//! startup and shutdown deadlines.

use std::{error::Error, future::Future, pin::Pin};

/// A typed application failure returned by a lifecycle hook.
pub type ApplicationLifecycleError = Box<dyn Error + Send + Sync + 'static>;

/// A boxed lifecycle future that does not require a particular async runtime.
pub type ApplicationLifecycleFuture<'a> =
    Pin<Box<dyn Future<Output = Result<(), ApplicationLifecycleError>> + Send + 'a>>;

/// The lifecycle hook that a server is invoking or reporting as failed.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ApplicationLifecycleStage {
    /// Application initialization before request acceptance.
    Startup,
    /// Application resource release after request draining.
    Shutdown,
}

/// Application startup and shutdown hooks shared by native servers and frameworks.
///
/// Implementations usually hold application state through shared ownership,
/// because request services may be cloned independently by the server. Startup
/// completes before the server accepts requests. Shutdown runs after the
/// server has stopped accepting and drained or cancelled active requests.
///
/// Each hook must return its failures as `Err`; servers may cancel a hook by
/// dropping its future when the configured timeout expires.
///
/// # Example
///
/// ```rust
/// use asgi_lifespan_protocol_rs::{
///     ApplicationLifecycle, ApplicationLifecycleError, ApplicationLifecycleFuture,
/// };
///
/// struct Lifecycle;
///
/// impl ApplicationLifecycle for Lifecycle {
///     fn startup(&self) -> ApplicationLifecycleFuture<'_> {
///         Box::pin(async { Ok::<(), ApplicationLifecycleError>(()) })
///     }
///
///     fn shutdown(&self) -> ApplicationLifecycleFuture<'_> {
///         Box::pin(async { Ok::<(), ApplicationLifecycleError>(()) })
///     }
/// }
///
/// # fn main() {
/// let lifecycle = Lifecycle;
/// let _startup = lifecycle.startup();
/// let _shutdown = lifecycle.shutdown();
/// # }
/// ```
pub trait ApplicationLifecycle: Send + Sync + 'static {
    /// Initializes application-owned resources before request acceptance.
    fn startup(&self) -> ApplicationLifecycleFuture<'_>;

    /// Releases application-owned resources after request draining completes.
    fn shutdown(&self) -> ApplicationLifecycleFuture<'_>;
}
