"""Focused contract checks for intentional lifecycle cancellation diagnostics."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_lifecycle_bench  # noqa: E402


def module_path(name: str) -> Path:
    module = importlib.import_module(name)
    return Path(module.__file__).resolve()


def source_frame(path: Path, function: str, statement: str) -> list[str]:
    source_lines = path.read_text().splitlines()
    matching = [index for index, line in enumerate(source_lines, 1) if line.strip() == statement]
    if not matching:
        raise AssertionError(f"{statement!r} is missing from {path}")
    number = matching[0]
    return [f'  File "{path}", line {number}, in {function}', f"    {source_lines[number - 1].strip()}"]


def cancellation_output(extra_frame: list[str] | None = None) -> str:
    bridge = module_path("uvicorn_rs._bridge")
    server = module_path("uvicorn.server")
    proxy = module_path("uvicorn.middleware.proxy_headers")
    locks = module_path("asyncio.locks")
    app = ROOT / "examples/bench_fastapi_lifecycle.py"
    frames = []
    frames += source_frame(bridge, "invoke", "await app(scope, receive, send)")
    frames += source_frame(server, "tracked_app", "await app(scope, receive, tracked_send)")
    frames += source_frame(proxy, "__call__", "return await self.app(scope, receive, send)")
    try:
        fastapi_routing = module_path("fastapi.routing")
    except ModuleNotFoundError as error:
        if error.name != "fastapi":
            raise
    else:
        frames += source_frame(
            fastapi_routing,
            "run_endpoint_function",
            "return await dependant.call(**values)",
        )
    if extra_frame is not None:
        frames += extra_frame
    frames += source_frame(app, "hold", "await asyncio.Event().wait()")
    frames += source_frame(locks, "wait", "await fut")
    return "\n".join([
        "APP_HOLD_STARTED",
        "uvicorn-rs: listener shutdown exceeded the graceful timeout",
        "APP_CANCELLED_BY_SHUTDOWN",
        "ERROR:    Exception in ASGI application",
        "Traceback (most recent call last):",
        *frames,
        "asyncio.exceptions.CancelledError",
        "LIFESPAN_SHUTDOWN_COMPLETE",
    ])


class RustLifecycleCancellationDiagnostics(unittest.TestCase):
    def test_accepts_only_source_verified_held_task_cancellation(self):
        result = run_lifecycle_bench.diagnostic_gate(
            cancellation_output(), {"kind": "rust"}, "active", 0, None, None,
        )
        receipt = result["diagnostic_normalization_receipt"]
        self.assertEqual(len(receipt), 2)
        self.assertEqual(
            receipt[0]["kind"],
            "single deliberately held Rust task cancellation traceback",
        )
        self.assertEqual(result["server_lifecycle_gate"], "passed")

    def test_rejects_a_different_exception_type_in_the_traceback(self):
        output = cancellation_output().replace(
            "asyncio.exceptions.CancelledError\n",
            "ValueError: unrelated application failure\n",
        )
        with self.assertRaisesRegex(RuntimeError, "incomplete or repeated ASGI traceback"):
            run_lifecycle_bench.diagnostic_gate(
                output, {"kind": "rust"}, "active", 0, None, None,
            )

    def test_rejects_a_frame_outside_the_installed_server_stack(self):
        test_path = Path(__file__).resolve()
        output = cancellation_output(
            source_frame(
                test_path,
                "untrusted_frame",
                "ROOT = Path(__file__).resolve().parents[1]",
            )
        )
        with self.assertRaisesRegex(RuntimeError, "outside the known framework/asyncio stack"):
            run_lifecycle_bench.diagnostic_gate(
                output, {"kind": "rust"}, "active", 0, None, None,
            )


if __name__ == "__main__":
    unittest.main()
