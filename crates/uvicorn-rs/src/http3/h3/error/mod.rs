//! This module contains the error handling logic and types for the h3 crate.

mod codes;

#[cfg(feature = "http3")]
pub mod connection_error_creators;
#[cfg(not(feature = "http3"))]
pub(crate) mod connection_error_creators;

#[cfg(feature = "http3")]
pub mod internal_error;
#[cfg(not(feature = "http3"))]
pub(crate) mod internal_error;

mod error;

pub use codes::Code;
pub use error::{ConnectionError, LocalError, StreamError};
