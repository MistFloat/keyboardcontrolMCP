from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from keyboard_mcp.ipc import request_broker


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.name == "nt", "Windows-only project")
class BrokerIpcTests(unittest.TestCase):
    def test_authenticated_json_ipc(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            environment = os.environ.copy()
            environment["KEYBOARD_MCP_RUNTIME_DIR"] = temp
            process = subprocess.Popen(
                [sys.executable, "-m", "keyboard_mcp", "--broker", "--allow-medium"],
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                with patch.dict(os.environ, {"KEYBOARD_MCP_RUNTIME_DIR": temp}):
                    deadline = time.monotonic() + 8
                    while True:
                        try:
                            status = request_broker("status")
                            break
                        except (FileNotFoundError, ConnectionError, EOFError, OSError):
                            if time.monotonic() >= deadline:
                                stderr = process.stderr.read() if process.stderr else ""
                                self.fail(f"broker did not start: {stderr}")
                            time.sleep(0.05)
                    self.assertTrue(status["ready"])
                    self.assertEqual(status["pid"], process.pid)
                    windows = request_broker("list_windows", {"limit": 5})
                    self.assertLessEqual(len(windows["windows"]), 5)
                    released = request_broker("release_all")
                    self.assertEqual(released["released_count"], 0)
                    with self.assertRaisesRegex(RuntimeError, "Unknown broker action"):
                        request_broker("definitely_not_an_action")
            finally:
                process.terminate()
                process.wait(timeout=5)
                if process.stderr:
                    process.stderr.close()


if __name__ == "__main__":
    unittest.main()
