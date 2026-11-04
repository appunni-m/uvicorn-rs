//! HTTP/3 client and server
#![deny(missing_docs, clippy::self_named_module_files)]
#![allow(clippy::derive_partial_eq_without_eq)]

pub mod client;

mod config;
//pub mod error;
pub mod ext;
pub mod quic;

pub mod server;

//pub use error::Error;

mod buf;

mod shared_state;

#[cfg(feature = "http3")]
pub use shared_state::{ConnectionState, SharedState};

pub mod error;

#[cfg(feature = "http3")]
#[allow(missing_docs)]
pub mod connection;
#[cfg(feature = "http3")]
#[allow(missing_docs)]
pub mod frame;
#[cfg(feature = "http3")]
#[allow(missing_docs)]
pub mod proto;
#[cfg(feature = "http3")]
#[allow(missing_docs)]
pub mod stream;
#[cfg(feature = "http3")]
#[allow(missing_docs)]
pub mod webtransport;

#[cfg(not(feature = "http3"))]
mod connection;
#[cfg(not(feature = "http3"))]
mod frame;
#[cfg(not(feature = "http3"))]
mod proto;
#[cfg(not(feature = "http3"))]
mod stream;
#[cfg(not(feature = "http3"))]
mod webtransport;

#[allow(dead_code)]
mod qpack;
