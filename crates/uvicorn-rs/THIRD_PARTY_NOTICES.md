# HTTP/3 third-party source notices

The HTTP/3 protocol and Quinn transport are separate registry packages:

- [`uvicorn-rs-h3`](https://github.com/appunni-m/uvicorn-rs/blob/main/crates/uvicorn-rs-h3/README.md) is based on the MIT-licensed
  `h3` 0.0.8 source from [hyperium/h3](https://github.com/hyperium/h3). The
  upstream source README and license are preserved in that package. The fork
  adds the receive-path corrections described in its README.
- [`uvicorn-rs-h3-quinn`](https://github.com/appunni-m/uvicorn-rs/blob/main/crates/uvicorn-rs-h3-quinn/README.md) is based on the
  MIT-licensed `h3-quinn` 0.0.10 source from
  [hyperium/h3](https://github.com/hyperium/h3). Its upstream source README and
  license are preserved in that package. The fork uses `uvicorn-rs-h3` so both
  crates share the same H3 protocol types.
- `src/http3/transport.rs` adapts the Quinn stream buffering and error
  conversion approach from `h3-quinn` 0.0.10. It adds request-scoped peer-stop
  observation and uses the Quinn read future directly for cancellation-safe
  request-body reads.

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
