# Reproducible benchmark runner proposal

These files are prepared under the ignored build directory. They have not been
promoted, executed, dispatched, committed, or published. Promotion must occur
after the current source and harness fingerprinted experiment finishes.

| Candidate | Intended tracked path |
| --- | --- |
| `run_benchmark_categories.py` | `scripts/run_benchmark_categories.py` |
| `analyze_benchmark_categories.py` | `scripts/analyze_benchmark_categories.py` |
| `benchmark-categories.yml` | `.github/workflows/benchmark-categories.yml` |

## Local command interface

Prepare the checkout `.venv/bin/python`, normal release server wheel, coherent
independent `starlette-rs-py` wheel, and the four normal release Rust clients
before capturing the identity. The workflow candidate supplies the complete
build and installation sequence. Use direct `.venv/bin/python` after installing
the optional framework wheel: another syncing command could remove that wheel.

```sh
.venv/bin/python scripts/run_benchmark_categories.py \
  --capture-identity target/benchmark-preparation/parity-before.json
.venv/bin/python scripts/run_parity.py \
  --output target/benchmark-preparation/parity.json
.venv/bin/python scripts/run_benchmark_categories.py \
  --parity-before-identity target/benchmark-preparation/parity-before.json \
  --parity-report target/benchmark-preparation/parity.json \
  --output-dir target/benchmark-categories \
  --duration 5 --warmup 1 --concurrency 64 --repetitions 3 --seed 20261005
```

Every output directory and before-parity file must be new. Omitting
`--output-dir` creates a timestamp and UUID directory beneath
`target/benchmark-categories/`. The wrapper never retries invalid timing rows
or loosens host contention guards. A rerun is a separate retained experiment.
`--category-timeout` defaults to 1,200 seconds per category. Optional
`--expected-source-sha256`, `--expected-native-sha256`, and
`--expected-public-cases` allow externally reviewed pins; none are platform
constants in the reusable command.

The complete public case denominator is derived from the current maintained
manifest and indexed inputs. Every public case must pass; no fault-contract
cases or smaller filter are accepted as this gate. The report's exact native
binary, Cargo.lock, Git revision, Python version, runner, fixtures, manifest,
input file hashes, and H3 client are checked. A full source, harness, app,
installed dependency, and client freeze captured before parity must still
match before benchmarking and after each category.

The wrapper uses the checkout `.venv/bin/python` because the maintained category
commands use that interpreter. Normal-binary scans reject coverage, fault, and
diagnostic instrumentation; coverage environment variables must be absent,
including empty definitions. Stock reference package source/native files are
verified against installed RECORD hashes. Editable or modified reference and
framework packages are rejected. A dirty server checkout remains explicit,
provisional local evidence.

## Default workload plan

The wrapper reads workload names and any server exclusions directly from the
maintained category scripts. The current plan is:

| Category | Reference | Rust candidate | Rows at three repetitions |
| --- | --- | --- | ---: |
| HTTP/1.1 | Uvicorn / uvloop / httptools | uvicorn-rs / uvloop | 72 |
| HTTP/2 | Hypercorn / uvloop | uvicorn-rs / uvloop | 42 |
| HTTP/3 | Hypercorn / uvloop | uvicorn-rs / uvloop | 33 |
| WebSockets | Uvicorn / uvloop / websockets | uvicorn-rs / uvloop | 18 |
| Lifespan and shutdown | Uvicorn / uvloop / httptools | uvicorn-rs / uvloop | 6 |
| Total | | | 171 |

HTTP/1.1 includes fixed responses, large bodies, two response chunk shapes,
two upload shapes, slow readers, 32-header scopes, context variables,
synchronous callables returning awaitables, deliberate exceptions, and the
independent framework route. HTTP/2 includes protocol scope, fixed and large
responses, response chunks, two upload shapes, and slow readers. HTTP/3 includes
scope, fixed and large responses, response chunks, slow readers, and a
target-only upload observation. WebSockets include handshake, text echo, and
64 KiB binary echo. Lifecycle rows each measure independent idle and active
server process lifetimes, synchronized application entry, cancellation,
lifespan completion, and SIGTERM exit.

Maintained overrides apply unchanged: HTTP/1.1 slow readers use concurrency 8;
HTTP/2 and HTTP/3 slow readers use concurrency 2, each at 4 MiB/s. HTTP/1.1
exceptions use concurrency 1, at most 200 requests, one second and no warmup.
WebSocket handshakes use concurrency 1, at most 500 handshakes and no warmup.
H2/H3 request concurrency shares at most four multiplexed connections. The
default workload time is about 954 seconds of warmup/load plus lifecycle,
startup, drain, hashing, and observer overhead; healthy runs commonly require
roughly 18–25 minutes after compilation. Failures retain partial observations.

## Output and interpretation

`run.json` records arguments, tools, the public parity gate, full identities,
each command, exact expected row count, report hash, failure count, timing
validity count, cleanup receipt, and suite status. `events.jsonl` records phase
transitions. Each category retains its original JSON, JSONL checkpoints,
provenance sidecars, runner logs, and individual server logs; lifecycle also
retains phase measurements. A category deadline, decoding failure, server
failure, or interruption retains those files. Cleanup only signals captured
owned PIDs whose creation times still match, preserving unrelated processes.

The pure JSON analyzer automatically produces `analysis.json`, `analysis.md`,
and an execution log even after category failures. It can also be run alone:

```sh
.venv/bin/python scripts/analyze_benchmark_categories.py \
  --input-dir target/benchmark-categories \
  --output-json target/benchmark-categories/analysis.json \
  --output-markdown target/benchmark-categories/analysis.md
```

At least three unique matching repetitions must pass correctness, lifecycle,
normal binary/identity, dependency, and host contention gates on both servers
before a pair produces medians or ratios. Raw invalid rows, exclusions,
duplicates, missing rows, and reason counts remain visible. No medians are
created for an incomplete category. Every metric separately needs at least
three finite matching values. H3 uploads have no qualifying Hypercorn pair;
deliberate exception speed remains unranked because diagnostic policies differ.

Workflow success means all planned category correctness observations completed.
It does not establish speed improvement. `analysis.json` can legitimately say
`no_qualified_pairs` after a successful workflow. No overall winner,
statistical significance, or comparison across protocol latency clocks is
inferred. Latency cells are medians of each run's percentiles rather than pooled
request percentiles. Same-host closed-loop clients have no coordinated omission
correction or open-loop offered-rate evidence.

Sustained server CPU is observed live process-tree CPU deltas over the recorded
load/monitor boundary. Client CPU is complete reaped-child RUSAGE_CHILDREN
accounting across setup/load/drain/report only when explicitly marked. Lifecycle
complete CPU covers the spawned and reaped server lifetime; its separate cold
start elapsed boundary also includes observer, free-port, and environment
preparation. RSS is sampled process-tree RSS. These boundaries must remain
separate in tables and conclusions.

The four Rust protocol clients are prebuilt and frozen before parity. HTTP/1.1's
C/libcurl client is built by its maintained runner before that category's first
timed sample and is checked before and after each sample. Its source and tool
versions are frozen; its actual binary SHA belongs to the HTTP/1.1 category
receipt, rather than the earlier public parity receipt. The slow reader uses
the maintained Node client. No build occurs inside a measured workload.

## Manual CI proposal

The separate workflow has only `workflow_dispatch`, read-only repository
permissions, pinned existing project actions, one Ubuntu 24.04 job, Python
3.12.13, Rust 1.98.1, and stock benchmark references from `uv.lock`. It builds a
normal release server wheel and clients before parity and timing. Actual Linux
native/client SHA values are captured rather than compared with a macOS binary.
No coverage or diagnostic binary is measured. This workflow does not claim
Linux 100% region coverage; existing coverage receipts remain separate.

The optional framework comes from the public repository
`https://github.com/appunni-m/starlette-rs.git`, immutable revision
`738c43362938896c268ca29b9a9a2a5942df510c`, outside the server checkout. Its
coherent normal wheel is built with pinned maturin 1.14.1, release and locked
Cargo dependencies, without source edits, installed only in the benchmark
environment, and retained with source archive, revision, wheel SHA, installed
native SHA, RECORD SHA, and build logs. This adds no server runtime dependency
or bundled framework. The benchmark still crosses into Python to run ASGI
applications; installing a Rust-backed framework does not remove that boundary.

Preparation, wheel, parity, raw category, server log, checkpoint, and analysis
artifacts are uploaded on success or failure. The Markdown analysis is attached
to the workflow summary. Manual dispatch requires the workflow to be registered
on the repository default branch; selecting a branch afterward runs that
branch's files. This candidate has not been dispatched.

A fresh hosted VM is an operationally isolated run, without a guarantee of
dedicated physical cores or no noisy neighbors. Hosted image/system library and
Node versions are recorded but not immutable; ImageOS, ImageVersion, runner
architecture, and runner name are retained when provided. Client, server, and observer share
the VM. Three valid pairs are descriptive evidence; independent dedicated-host
runs and an open-loop generator are still needed for stronger latency claims.

## Static review and remaining verification

The candidates are based on the maintained live result contracts and public
configuration flags. A bounded independent static review confirmed exact public
parity selection, target identity binding, H3 target-only row completeness,
sequential execution and owned-PID cleanup. Equality-to-zero ambiguity was
tightened to require integer counters and real Boolean timing flags. No private
reference implementation patch, log suppression, or panic exception was added.
Both Python candidates passed static AST parsing. The workflow passed static YAML
parsing and manual-trigger, permissions, full action-SHA, and coverage-environment
checks; an independent review found no blocking static defect.

The framework origin and immutable revision were read locally. Anonymous public
readability of that commit has not been verified. The CI framework wheel uses
Rust 1.98.1; the earlier macOS framework receipt used Rust 1.96.1. This is a new
Linux build bound to its own source, wheel, native, and parity receipts, without
reproducing or pinning the earlier macOS native hashes.

Remaining verification after promotion: Python syntax/CLI checks; a fresh normal
Linux build; a full public parity result tied to its captured binary; a short
functional runner smoke using new output directories; then the complete manual
benchmark job and artifact review. These steps have not been run for the
candidates. The current performance objective remains unproven until the
matched, correctness-gated evidence demonstrates a repeatable improvement.
