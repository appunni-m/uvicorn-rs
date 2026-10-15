# HTTP/3 transport adapter

The bidirectional stream buffering and transport error conversions in
`src/http3/transport.rs` are adapted from h3-quinn 0.0.10, maintained by the h3
authors at <https://github.com/hyperium/h3>.

The reviewed upstream source is `h3-quinn/src/lib.rs` at commit
`2dc3412bdf6083451920d5bfd7a9484d054c1859`. The crates.io archive SHA-256 is
`8b2e732c8d91a74731663ac8479ab505042fbf547b9a207213ab7fbcbfc4f8b4`.
The local adapter uses public h3 and Quinn APIs, adds a connection-scoped
registry of owned send-stream stop futures, and delegates unidirectional
streams to the unmodified h3-quinn dependency. Its receive wrapper polls
Quinn's cancel-safe `read_chunk` future directly.

The following upstream license applies to those adapted portions:

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
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
