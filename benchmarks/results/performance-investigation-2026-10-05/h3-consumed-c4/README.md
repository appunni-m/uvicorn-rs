# Controlled consumed-request H3 load diagnostic

6/6 response/lifecycle checks passed; 1 valid timing and 5 host-invalid; no qualified matched ratio.

Same consumed app, one-byte request, strict body/status checks, GREASE disabled, four QUIC connections, five-second load, one-second warmup, three planned repetitions; only concurrency differs from the preserved c64 attempt. Normal source C7/native 0e and the exact public parity gate stayed stable. Artifacts are original unchanged copies. The client used application close code zero; later protocol-correct client changes must use separate identities and attempts.
