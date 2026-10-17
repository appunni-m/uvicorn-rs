# Local h3 patch

This is the upstream `h3` 0.0.8 crate source, retained under its original MIT
license with two narrow HTTP/3 receive-path corrections in `src/connection.rs`
and `src/frame.rs`.

`RequestStream::poll_recv_data` skips zero-length DATA frames. HTTP/3 permits
empty DATA frames; returning `None` for one makes consumers mistake it for
end-of-body and can reject the next valid DATA frame while checking for
trailers. The loop continues polling until it finds non-empty body data,
trailers, end-of-stream, or a pending/error result.

`FrameStream::poll_data` returns `UnexpectedEnd` if the QUIC stream ends before
the declared DATA-frame payload is complete. RFC 9114 §7.1 requires a cleanly
terminated stream with a truncated final frame to cause `H3_FRAME_ERROR`; the
unchanged upstream branch returned end-of-body for this condition. The live
parity case `http3.truncated-data-frame-recovery-after-protocol-error` checks
the wire error code and a subsequent healthy connection.

The root workspace's `[patch.crates-io]` uses this source. The standalone
`crates/uvicorn-rs` package currently resolves registry `h3` 0.0.8 and does
not inherit the root override when built as an external dependency. Keep that
crate-archive claim blocked until the correction is available through its
external dependency graph and the extracted-archive case passes. Remove this
local override once a published upstream `h3` release provides both behaviors.
