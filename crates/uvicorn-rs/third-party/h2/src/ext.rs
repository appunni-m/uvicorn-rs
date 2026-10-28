//! Extensions specific to the HTTP/2 protocol.

use crate::hpack::BytesStr;

use bytes::Bytes;
use http::header::HeaderName;
use std::fmt;

/// The order of response header fields to use when encoding an HTTP/2 response.
///
/// `http::HeaderMap` groups values by name and cannot represent interleaved
/// fields. Attach this extension when the application-provided field order
/// must be retained on the wire. Header names absent from this sequence are
/// encoded afterward using the map's normal iteration order.
#[derive(Clone, Debug)]
pub struct HeaderOrder(Vec<HeaderName>);

impl HeaderOrder {
    /// Creates a response header order from header names.
    ///
    /// Include a name once for each field with that name. Repeated names retain
    /// the order of their values in the response's `HeaderMap`.
    pub fn new(names: impl IntoIterator<Item = HeaderName>) -> Self {
        Self(names.into_iter().collect())
    }

    /// Adds fields before the current sequence, such as server-generated
    /// default headers that precede application headers.
    pub fn prepend(&mut self, names: impl IntoIterator<Item = HeaderName>) {
        let mut prefix: Vec<_> = names.into_iter().collect();
        prefix.append(&mut self.0);
        self.0 = prefix;
    }

    /// Returns the ordered header names.
    pub fn names(&self) -> &[HeaderName] {
        &self.0
    }
}

/// Represents the `:protocol` pseudo-header used by
/// the [Extended CONNECT Protocol].
///
/// [Extended CONNECT Protocol]: https://datatracker.ietf.org/doc/html/rfc8441#section-4
#[derive(Clone, Eq, PartialEq)]
pub struct Protocol {
    value: BytesStr,
}

impl Protocol {
    /// Converts a static string to a protocol name.
    pub const fn from_static(value: &'static str) -> Self {
        Self {
            value: BytesStr::from_static(value),
        }
    }

    /// Returns a str representation of the header.
    pub fn as_str(&self) -> &str {
        self.value.as_str()
    }

    pub(crate) fn try_from(bytes: Bytes) -> Result<Self, std::str::Utf8Error> {
        Ok(Self {
            value: BytesStr::try_from(bytes)?,
        })
    }
}

impl<'a> From<&'a str> for Protocol {
    fn from(value: &'a str) -> Self {
        Self {
            value: BytesStr::from(value),
        }
    }
}

impl AsRef<[u8]> for Protocol {
    fn as_ref(&self) -> &[u8] {
        self.value.as_ref()
    }
}

impl fmt::Debug for Protocol {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        self.value.fmt(f)
    }
}
