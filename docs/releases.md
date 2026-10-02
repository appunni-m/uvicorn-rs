# Release candidates

The project currently builds **release candidates**, not public releases. The
crate manifest sets `publish = false`; CI does not publish to crates.io or
PyPI, create a GitHub Release, or create or move tags. The repository has not
selected a license, so these workflow artifacts are retained for project
review and are not a public distribution channel.

## Candidate checks

The main CI workflow is the source of release artifacts. For a pushed commit on
`main`, it runs the Rust and Python protocol checks, builds and smoke-tests one
CPython `abi3` wheel on each configured runner, and builds a source distribution
on Linux. The current artifact targets are:

| Artifact | Build runner | Validation |
|---|---|---|
| Linux x86-64 wheel | Ubuntu 24.04 x86-64 | Install the wheel; import the native module; run CLI help |
| macOS ARM64 wheel | macOS 14 ARM64 | Install the wheel; import the native module; run CLI help |
| Windows x86-64 wheel | Windows Server 2022 x86-64 | Install the wheel; import the native module; run CLI help |
| Source distribution | Ubuntu 24.04 x86-64 | Required build inputs are checked when assembling a tagged candidate |

These are configured CI checks; support is not established until the hosted run
for the relevant commit succeeds. They do not establish the declared minimum
Python or Rust versions, all ASGI behavior, or production readiness. See the
[support matrix](support-matrix.md) for behavioral coverage and open gaps.

## Assemble a tagged candidate

After the exact commit has passed the complete `CI` workflow on `main`, a
maintainer may push an **annotated** `vMAJOR.MINOR.PATCH` tag pointing at that
commit. Cargo, Python project metadata, and both lockfiles must already carry
the same version. The `Release candidate` workflow then:

1. checks that the tag is annotated and points to the workflow's commit;
2. verifies the tag version against `Cargo.toml`, `pyproject.toml`, `Cargo.lock`,
   and `uv.lock`;
3. requires a successful `CI` run on `main` for that exact commit;
4. downloads only the wheel and source artifacts from that run, validates their
   versions/platform tags/required source files, and writes `SHA256SUMS`;
5. retains the verified bundle as a GitHub Actions artifact for 90 days.

The workflow intentionally has read-only repository permissions apart from
reading artifacts from Actions. It has no registry credentials, OIDC token
permission, tag-writing permission, or GitHub Release creation step. An
annotated tag requests candidate assembly; it does not claim a supported
release. Do not push a tag until license selection, release notes, the support
matrix, and the intended public distribution path have been reviewed.

Dependabot checks the Cargo manifests and pinned GitHub Actions weekly. Review
those updates, keep action references pinned to full commit SHAs, and require
the normal CI workflow to pass before tagging.

The candidate workflow does not reproduce tests on the tag. It consumes the
artifact set from the successful main CI run for the exact tagged commit and
fails if those artifacts have expired or are incomplete. Artifacts expire after
90 days; rerun CI on the exact commit before requesting candidate assembly if
needed.
