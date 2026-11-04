# Hyper HTTP/1 header-order patch

This directory vendors Hyper 1.12.0 from crates.io and patches its HTTP/1
server encoder to support the public `hyper::ext::HeaderOrder` response
extension. Hyper's `HeaderMap` groups values by name, so it cannot represent
interleaved ASGI response fields by itself.

The patch is limited to the HTTP/1 server encoder. Without the extension,
Hyper retains its original behavior. HTTP/2 and other Hyper code are unchanged.
The upstream feature request is tracked at
<https://github.com/hyperium/hyper/issues/3914>.

The upstream crate retains its MIT license in `LICENSE`; the original normalized
manifest and source tree are preserved for reproducible Cargo builds.
