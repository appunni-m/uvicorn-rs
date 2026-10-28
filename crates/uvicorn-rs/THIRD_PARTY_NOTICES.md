# Third-party source notices

The HTTP/3 implementation is vendored inside `uvicorn-rs` and compiled by its
optional `http3` Cargo feature. The source retains the upstream MIT license.

- The protocol implementation in `src/http3/h3/` is based on the MIT-licensed
  `h3` 0.0.8 source from [hyperium/h3](https://github.com/hyperium/h3).
- `src/http3/h3_quinn.rs` is based on the MIT-licensed `h3-quinn` 0.0.10
  source from [hyperium/h3](https://github.com/hyperium/h3).
- `src/http3/transport.rs` adapts Quinn stream buffering and error conversion.
  It adds request-scoped peer-stop observation and uses the Quinn read future
  directly for cancellation-safe request-body reads.
- `third-party/h3/` and `third-party/h3-quinn/` retain upstream README and
  license text in the Cargo archive.

The WebSocket `permessage-deflate` implementation uses the Yawc 0.5.0 crate,
licensed under MPL-2.0. Its source is obtained as a Cargo dependency rather
than vendored; `third-party/yawc/LICENSE` retains the upstream license text.
Yawc is used for sessions where the HTTP/1.1 handshake negotiated compression.

The Python ASGI adapter uses the MIT-licensed `h2` 0.4.20 source from
[hyperium/h2](https://github.com/hyperium/h2), vendored under
`third-party/h2/`. Its local `HeaderOrder` extension preserves the response
field sequence supplied by ASGI when the adapter's HTTP/2 path encodes HPACK.
The published `uvicorn-rs` Cargo crate uses the registry dependency and does
not package this adapter-only patch.

The adapted transport code is available under the MIT license:

Copyright (c) 2020 h3 authors

Permission is hereby granted, free of charge, to any
person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the
Software without restriction, including without
limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice
shall be included in all copies or substantial portions
of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
