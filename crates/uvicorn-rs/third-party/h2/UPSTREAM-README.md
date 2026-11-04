# Vendored `h2`

This directory is vendored from the `h2` 0.4.20 crate. Its registry source
records upstream revision `b0e890842ac16d3c76836fd4fcc06421acb15fa7` in
`.cargo_vcs_info.json`.

The local patch adds an HTTP/2 `HeaderOrder` response extension and carries the
requested repeated field sequence to the HPACK encoder. It is used by the
Python ASGI adapter to preserve the header order supplied in ASGI
`http.response.start`. Responses without the extension, inbound requests, and
trailers retain the upstream behavior.

Keep the upstream `LICENSE` with this source. When updating the vendored crate,
reapply and review the local changes against the new upstream implementation.
