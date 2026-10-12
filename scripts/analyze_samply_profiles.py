#!/usr/bin/env python3
"""Summarize Samply profiles without treating inclusive stacks as CPU shares.

On macOS, locally available Mach-O images are symbolicated with atos. System
shared-cache images stay at library/address granularity because their on-disk
stubs are not a reliable symbol source for the loaded image.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


HEX_ADDRESS = re.compile(r"^0x[0-9a-fA-F]+$")
SYMBOL_OFFSET = re.compile(r"\s+\+\s+\d+$")
RUST_SYMBOL = re.compile(r"^(_?(?:R|ZN)[A-Za-z0-9_]+)(.*)$")


def _read_profile(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as profile_file:
        profile = json.load(profile_file)
    if not isinstance(profile.get("threads"), list) or not profile["threads"]:
        raise ValueError(f"{path}: missing Samply thread profiles")
    if profile.get("meta", {}).get("sampleUnits", {}).get("threadCPUDelta") != "µs":
        raise ValueError(f"{path}: unexpected threadCPUDelta units")
    return profile


def _image_base(path: Path) -> int:
    """Return the Mach-O __TEXT VM address used by atos for sampled offsets."""
    if shutil.which("otool") is None:
        return 0
    result = subprocess.run(
        ["otool", "-l", str(path)], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        return 0
    in_text_segment = False
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("cmd "):
            in_text_segment = False
        elif stripped == "segname __TEXT":
            in_text_segment = True
        elif in_text_segment and stripped.startswith("vmaddr "):
            try:
                return int(stripped.split()[1], 16)
            except (IndexError, ValueError):
                return 0
    return 0


def _image_path(profile_path: Path, library: dict) -> Path | None:
    if library.get("name") == "_native.abi3.so":
        preserved = profile_path.parent / "normal-native.abi3.so"
        if preserved.is_file():
            return preserved
    raw_path = library.get("path")
    if raw_path:
        image = Path(raw_path)
        if image.is_file():
            return image
    return None


def _symbolicate(
    profile: dict, profile_path: Path, rustfilt: str | None
) -> tuple[dict, list[str]]:
    """Symbolicate local binaries only; return (image path, address) -> name."""
    notes = []
    if os.uname().sysname != "Darwin" or shutil.which("atos") is None:
        return {}, ["Local Mach-O symbolication unavailable on this platform."]

    addresses_by_image = defaultdict(set)
    for thread in profile["threads"]:
        frames = thread.get("frameTable", {})
        funcs = thread.get("funcTable", {})
        resources = thread.get("resourceTable", {})
        for frame_index, address in enumerate(frames.get("address", [])):
            try:
                func_index = frames["func"][frame_index]
                resource_index = funcs["resource"][func_index]
                library_index = resources["lib"][resource_index]
                library = profile["libs"][library_index]
            except (IndexError, KeyError, TypeError):
                continue
            image = _image_path(profile_path, library)
            if image is None or str(image).startswith(("/usr/lib/", "/System/")):
                continue
            addresses_by_image[image].add(int(address))

    symbols = {}
    for image, addresses in addresses_by_image.items():
        base = _image_base(image)
        ordered = sorted(addresses)
        for start in range(0, len(ordered), 100):
            batch = ordered[start : start + 100]
            command = ["atos", "-o", str(image), "-l", hex(base)]
            command.extend(hex(base + address) for address in batch)
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            lines = result.stdout.splitlines()
            if result.returncode != 0 or len(lines) != len(batch):
                notes.append(f"atos did not resolve all addresses in {image}.")
                continue
            for address, line in zip(batch, lines, strict=True):
                symbol = line.strip()
                if symbol and not HEX_ADDRESS.fullmatch(symbol):
                    symbols[(str(image), address)] = SYMBOL_OFFSET.sub("", symbol)

    mangled = sorted(
        {
            match.group(1)
            for symbol in symbols.values()
            if (match := RUST_SYMBOL.match(symbol))
        }
    )
    demangler = rustfilt or shutil.which("rustfilt")
    if mangled and demangler:
        demangled = {}
        for start in range(0, len(mangled), 100):
            batch = mangled[start : start + 100]
            result = subprocess.run(
                [demangler, *batch], text=True, capture_output=True, check=False
            )
            lines = result.stdout.splitlines()
            if result.returncode != 0 or len(lines) != len(batch):
                notes.append("rustfilt could not demangle every sampled Rust symbol.")
                continue
            demangled.update(zip(batch, lines, strict=True))
        for key, symbol in list(symbols.items()):
            match = RUST_SYMBOL.match(symbol)
            if match and demangled.get(match.group(1), match.group(1)) != match.group(1):
                symbols[key] = demangled[match.group(1)] + match.group(2)
    elif mangled:
        notes.append(
            "Rust symbols are resolved but remain mangled; install rustfilt or pass --rustfilt to demangle them."
        )

    if any(
        lib.get("path", "").startswith(("/usr/lib/", "/System/"))
        for lib in profile.get("libs", [])
    ):
        notes.append(
            "System shared-cache function names remain unresolved; their sampled library ownership is reported."
        )
    return symbols, notes


def _frame_rows(thread: dict, profile: dict, symbols: dict, profile_path: Path) -> list[dict]:
    frame_table = thread["frameTable"]
    function_table = thread["funcTable"]
    resource_table = thread["resourceTable"]
    strings = thread["stringArray"]
    rows = []
    for frame_index, address in enumerate(frame_table["address"]):
        function_index = frame_table["func"][frame_index]
        resource_index = function_table["resource"][function_index]
        try:
            library_index = resource_table["lib"][resource_index]
            library = profile["libs"][library_index]
            library_name = library.get("name", "unknown")
            image = _image_path(profile_path, library)
            image_path = str(image) if image is not None else library.get("path", "")
        except (IndexError, KeyError, TypeError):
            library_name = "unknown"
            image_path = ""
        name_index = function_table["name"][function_index]
        raw_name = strings[name_index] if name_index is not None else "unknown"
        symbol = symbols.get((image_path, int(address)), raw_name)
        rows.append(
            {
                "library": library_name,
                "image_path": image_path,
                "address": int(address),
                "symbol": symbol,
            }
        )
    return rows


def _aggregate(
    label: str, path: Path, profile: dict, rustfilt: str | None
) -> dict:
    symbols, symbolication_notes = _symbolicate(profile, path, rustfilt)
    receipt_path = path.parent / "profile-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    load_started = datetime.fromisoformat(receipt["load_started_at"]).timestamp() * 1000
    load_finished = datetime.fromisoformat(receipt["load_finished_at"]).timestamp() * 1000
    profile_started = profile.get("meta", {}).get("startTime")
    if not isinstance(profile_started, (int, float)):
        raise ValueError(f"{path}: missing Samply profile start time")
    load_start_ms = load_started - profile_started
    load_end_ms = load_finished - profile_started
    profile_sample_times = [
        sample_time
        for thread in profile["threads"]
        for sample_time in thread.get("samples", {}).get("time", [])
        if isinstance(sample_time, (int, float)) and math.isfinite(sample_time)
    ]
    first_sample_ms = min(profile_sample_times) if profile_sample_times else None
    last_sample_ms = max(profile_sample_times) if profile_sample_times else None
    covered_start_ms = max(load_start_ms, first_sample_ms) if first_sample_ms is not None else None
    covered_end_ms = min(load_end_ms, last_sample_ms) if last_sample_ms is not None else None
    covered_load_ms = (
        max(0.0, covered_end_ms - covered_start_ms)
        if covered_start_ms is not None and covered_end_ms is not None
        else 0.0
    )
    thread_totals = Counter()
    thread_counts = Counter()
    library_cpu = Counter()
    exclusive_cpu = Counter()
    inclusive_cpu = Counter()
    positive_samples = 0
    zero_samples = 0
    process_cpu_us = 0
    per_thread = []
    threads_with_blocking_pool_loop = set()

    for thread in profile["threads"]:
        rows = _frame_rows(thread, profile, symbols, path)
        samples = thread.get("samples", {})
        stacks = thread.get("stackTable", {})
        sample_stacks = samples.get("stack", [])
        sample_deltas = samples.get("threadCPUDelta", [])
        sample_times = samples.get("time", [])
        if not (len(sample_stacks) == len(sample_deltas) == len(sample_times)):
            raise ValueError(f"{path}: profile sample arrays differ in length")
        thread_cpu = 0
        thread_positive_samples = 0
        for stack_id, delta, sample_time in zip(
            sample_stacks,
            sample_deltas,
            sample_times,
            strict=True,
        ):
            if not isinstance(sample_time, (int, float)) or not (
                load_start_ms <= sample_time <= load_end_ms
            ):
                continue
            if not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta < 0:
                continue
            if delta == 0:
                zero_samples += 1
                continue
            if stack_id is None or not isinstance(stack_id, int):
                continue
            try:
                frame_id = stacks["frame"][stack_id]
                row = rows[frame_id]
            except (IndexError, KeyError, TypeError):
                continue
            weight = int(delta)
            positive_samples += 1
            thread_positive_samples += 1
            thread_cpu += weight
            process_cpu_us += weight
            library_cpu[row["library"]] += weight
            exclusive_cpu[(row["library"], row["symbol"])] += weight

            prefix = stacks["prefix"][stack_id]
            call_path = [row]
            while prefix is not None:
                parent = rows[stacks["frame"][prefix]]
                call_path.append(parent)
                inclusive_cpu[(parent["library"], parent["symbol"])] += weight
                prefix = stacks["prefix"][prefix]
            inclusive_cpu[(row["library"], row["symbol"])] += weight
            if any(
                "tokio::runtime::blocking::pool::Inner>::run" in frame["symbol"]
                for frame in call_path
            ):
                threads_with_blocking_pool_loop.add(thread.get("tid"))

        thread_name = thread.get("name", "unknown")
        thread_totals[thread_name] += thread_cpu
        thread_counts[thread_name] += int(thread_cpu > 0)
        if thread_cpu:
            per_thread.append(
                {
                    "name": thread_name,
                    "tid": thread.get("tid"),
                    "cpu_us": thread_cpu,
                    "sampled_rows": thread_positive_samples,
                }
            )

    def ranked(counter: Counter, limit: int = 100) -> list[dict]:
        return [
            {
                "library": library,
                "symbol": symbol,
                "cpu_us": weight,
                "cpu_ms": round(weight / 1000, 3),
                "percent_of_process_sampled_cpu": round(
                    100 * weight / process_cpu_us, 2
                )
                if process_cpu_us
                else None,
            }
            for (library, symbol), weight in counter.most_common(limit)
        ]

    per_thread.sort(key=lambda row: row["cpu_us"], reverse=True)
    return {
        "label": label,
        "profile_path": str(path),
        "profile_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "receipt_path": str(receipt_path),
        "receipt_status": receipt.get("status"),
        "server": receipt.get("server"),
        "workload": receipt.get("workload"),
        "concurrency": receipt.get("concurrency"),
        "source_sha256": receipt.get("identity_before", {}).get("source_sha256"),
        "native_extension_sha256": receipt.get("identity_before", {})
        .get("native_extension", {})
        .get("sha256"),
        "python_runtime": receipt.get("runtime_before", {}).get("python"),
        "profile_time_window_ms": {
            "first_sample": first_sample_ms,
            "last_sample": last_sample_ms,
            "load_started": load_start_ms,
            "load_finished": load_end_ms,
            "load_covered_by_profile": covered_load_ms,
        },
        "os": profile.get("meta", {}).get("oscpu"),
        "sample_interval_ms": profile.get("meta", {}).get("interval"),
        "samply_profile_symbolicated": profile.get("meta", {}).get("symbolicated"),
        "thread_cpu_delta_unit": profile["meta"]["sampleUnits"]["threadCPUDelta"],
        "process_sampled_cpu_us": process_cpu_us,
        "process_sampled_cpu_ms": round(process_cpu_us / 1000, 3),
        "positive_cpu_delta_rows": positive_samples,
        "zero_cpu_delta_rows": zero_samples,
        "library_cpu": [
            {
                "library": library,
                "cpu_us": value,
                "cpu_ms": round(value / 1000, 3),
                "percent_of_process_sampled_cpu": round(
                    100 * value / process_cpu_us, 2
                )
                if process_cpu_us
                else None,
            }
            for library, value in library_cpu.most_common()
        ],
        "thread_cpu": [
            {
                "name": name,
                "threads_with_cpu_samples": thread_counts[name],
                "cpu_us": cpu_us,
                "cpu_ms": round(cpu_us / 1000, 3),
                "percent_of_process_sampled_cpu": round(
                    100 * cpu_us / process_cpu_us, 2
                )
                if process_cpu_us
                else None,
            }
            for name, cpu_us in thread_totals.most_common()
        ],
        "threads_with_blocking_pool_loop_samples": len(
            threads_with_blocking_pool_loop
        ),
        "blocking_pool_loop_thread_ids": sorted(
            tid for tid in threads_with_blocking_pool_loop if tid is not None
        ),
        "top_exclusive_functions": ranked(exclusive_cpu),
        "top_inclusive_functions": ranked(inclusive_cpu),
        "top_threads": per_thread[:20],
        "symbolication_notes": symbolication_notes,
    }


def _markdown(report: dict) -> str:
    lines = [
        "# Samply profile attribution",
        "",
        "Diagnostic-only on-CPU attribution from Samply thread CPU-delta weights. "
        "Profiles are not benchmark timings and do not provide a speed comparison.",
        "",
    ]
    for run in report["profiles"]:
        lines.extend(
            [
                f"## {run['label']}",
                "",
                f"- OS: {run['os']}",
                f"- Sampled process CPU weight: {run['process_sampled_cpu_ms']:.3f} ms "
                f"across {run['positive_cpu_delta_rows']} positive CPU-delta rows.",
                f"- Profile SHA-256: {run['profile_sha256']}",
                f"- Server/workload: {run['server']} / {run['workload']}, "
                f"concurrency {run['concurrency']}.",
                f"- Captured active-load window: {run['profile_time_window_ms']['load_covered_by_profile']:.1f} ms.",
                f"- Threads with a sampled Tokio blocking-pool loop: {run['threads_with_blocking_pool_loop_samples']}.",
                f"- Source SHA-256: {run['source_sha256']}",
                "",
                "### CPU by sampled image",
                "",
                "| Image | Sampled CPU (ms) | Share |",
                "|---|---:|---:|",
            ]
        )
        for row in run["library_cpu"]:
            lines.append(
                f"| {row['library']} | {row['cpu_ms']:.3f} | "
                f"{row['percent_of_process_sampled_cpu']:.2f}% |"
            )
        lines.extend(
            [
                "",
                "### Top exclusive sampled functions",
                "",
                "| Image | Function | Sampled CPU (ms) | Share |",
                "|---|---|---:|---:|",
            ]
        )
        for row in run["top_exclusive_functions"][:15]:
            symbol = row["symbol"].replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {row['library']} | {symbol} | {row['cpu_ms']:.3f} | "
                f"{row['percent_of_process_sampled_cpu']:.2f}% |"
            )
        lines.extend(
            [
                "",
                "### CPU by thread name",
                "",
                "| Thread name | Threads with CPU samples | Sampled CPU (ms) | Share |",
                "|---|---:|---:|---:|",
            ]
        )
        for row in run["thread_cpu"]:
            lines.append(
                f"| {row['name']} | {row['threads_with_cpu_samples']} | "
                f"{row['cpu_ms']:.3f} | {row['percent_of_process_sampled_cpu']:.2f}% |"
            )
        if run["symbolication_notes"]:
            lines.extend(["", "### Symbolication notes", ""])
            lines.extend(f"- {note}" for note in run["symbolication_notes"])
        lines.append("")
    lines.extend(
        [
            "## Reading these profiles",
            "",
            "Exclusive rows attribute a positive CPU-delta sample to its innermost sampled "
            "frame. Inclusive rows count it at every caller and overlap; do not add them. "
            "System shared-cache function names may remain unresolved, while sampled library "
            "ownership is retained. The name tokio-rt-worker does not prove a thread is an "
            "async scheduler worker; Tokio blocking-pool threads can share it.",
            "",
            "The raw captures include startup and warmup; this report filters samples to the "
            "receipt's active HTTP-load interval. Samply may cover only part of that interval, "
            "which is reported above. Sampling perturbs execution, so these profiles support "
            "hotspot hypotheses only. Use host-clean, correctness-gated, unprofiled matched "
            "runs for throughput, latency, CPU/request, and memory claims.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help="Samply profile with a readable label; repeat for each run",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument(
        "--rustfilt",
        help="optional path to rustfilt; otherwise use it from PATH when available",
    )
    args = parser.parse_args()

    runs = []
    for item in args.profile:
        label, separator, raw_path = item.partition("=")
        if not separator or not label or not raw_path:
            parser.error(f"invalid --profile {item!r}; expected LABEL=PATH")
        path = Path(raw_path).resolve()
        if not path.is_file():
            parser.error(f"profile does not exist: {path}")
        runs.append(_aggregate(label, path, _read_profile(path), args.rustfilt))

    report = {
        "schema_version": 1,
        "diagnostic_only": True,
        "timing_valid": False,
        "profiles": runs,
        "interpretation": [
            "Positive threadCPUDelta rows are weighted in microseconds and grouped by innermost frame.",
            "Inclusive call-path weights overlap and are not additive.",
            "System library function names may remain unresolved because macOS uses a dyld shared cache.",
            "Profiles include startup and warmup and do not establish comparative performance.",
        ],
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "profiles": len(runs),
                "json": str(args.json_output),
                "markdown": str(args.markdown_output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
