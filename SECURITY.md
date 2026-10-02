# Security policy

`uvicorn-rs` is experimental and has not received a security audit. Protocol
probes and CI do not establish that it is safe to expose to public traffic.

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Use GitHub's
private vulnerability reporting / Security Advisories for this repository if
that feature is enabled. Its availability has not been verified for this
repository. If private reporting is unavailable, contact the repository owner
through their GitHub profile and ask for a private disclosure route before
sending exploit details.

There is currently no published response-time commitment or supported-release
window. Include the affected revision, protocol, configuration, reproduction
steps, and impact. Avoid including real credentials or user data.

Known security-coverage gaps include the absence of a complete HTTP parser and
request-smuggling test suite, exhaustive malformed-frame tests, broad HTTP/3
interoperability coverage, and an independent security review. See the
[support matrix](docs/support-matrix.md) for tested protocol scope.
