from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keyboard_mcp.ipc import request_broker  # noqa: E402


def wait_for_broker(timeout: float = 8) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return request_broker("status")
        except (FileNotFoundError, ConnectionError, EOFError, OSError):
            time.sleep(0.05)
    raise TimeoutError("test broker did not become ready")


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This smoke test is Windows-only.")

    with tempfile.TemporaryDirectory(prefix="keyboard-mcp-smoke-") as temp:
        previous_runtime = os.environ.get("KEYBOARD_MCP_RUNTIME_DIR")
        os.environ["KEYBOARD_MCP_RUNTIME_DIR"] = temp
        environment = os.environ.copy()
        title = f"Codex Keyboard MCP Smoke {uuid.uuid4().hex}"
        output = Path(temp) / "received.txt"
        expected = "Codex键盘MCP✓"

        broker = subprocess.Popen(
            [sys.executable, "-m", "keyboard_mcp", "--broker", "--allow-medium"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        target: subprocess.Popen[bytes] | None = None
        try:
            status = wait_for_broker()
            target = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "tests" / "keyboard_target.py"),
                    "--title",
                    title,
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            deadline = time.monotonic() + 8
            window: dict[str, object] | None = None
            while time.monotonic() < deadline:
                matches = request_broker("list_windows", {"title_contains": title})
                if matches["windows"]:
                    window = matches["windows"][0]
                    break
                time.sleep(0.05)
            if window is None:
                raise TimeoutError("test target window did not appear")

            request_broker("focus_window", {"window_handle": window["handle"]})
            request_broker(
                "sequence",
                {
                    "expected_window_handle": window["handle"],
                    "actions": [
                        {"op": "type", "text": expected, "interval_ms": 5},
                        {"op": "press", "key": "enter", "mode": "scan_code"},
                    ],
                },
            )

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not output.exists():
                time.sleep(0.05)
            actual = output.read_text(encoding="utf-8") if output.exists() else None
            if actual != expected:
                raise AssertionError(f"keyboard smoke test failed: expected {expected!r}, got {actual!r}")
            print(
                "PASS: real SendInput Unicode + scan-code Enter reached the guarded target; "
                f"broker integrity={status['integrity']['name']}"
            )
        finally:
            if target is not None and target.poll() is None:
                target.terminate()
                target.wait(timeout=5)
            broker.terminate()
            broker.wait(timeout=5)
            if previous_runtime is None:
                os.environ.pop("KEYBOARD_MCP_RUNTIME_DIR", None)
            else:
                os.environ["KEYBOARD_MCP_RUNTIME_DIR"] = previous_runtime


if __name__ == "__main__":
    main()

