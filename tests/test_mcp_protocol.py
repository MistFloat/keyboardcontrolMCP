from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.name == "nt", "Windows-only project")
class McpProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        environment = os.environ.copy()
        environment["KEYBOARD_MCP_RUNTIME_DIR"] = self.temp.name
        self.process = subprocess.Popen(
            [sys.executable, str(ROOT / "run_server.py")],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def tearDown(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.process.wait(timeout=5)
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()
        self.temp.cleanup()

    def request(self, message: dict[str, object]) -> dict[str, object]:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            self.fail(f"MCP server closed stdout: {stderr}")
        value = json.loads(line)
        self.assertEqual(value["jsonrpc"], "2.0")
        return value

    def test_initialize_list_and_status(self) -> None:
        initialized = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        result = initialized["result"]
        self.assertEqual(result["serverInfo"]["name"], "codex-keyboard-control")
        self.assertIn("administrator apps", result["instructions"])

        tools = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )["result"]["tools"]
        names = {tool["name"] for tool in tools}
        self.assertEqual(len(names), 13)
        self.assertIn("keyboard_start_elevated_broker", names)
        self.assertIn("keyboard_sequence", names)

        status = self.request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "keyboard_status", "arguments": {}},
            }
        )["result"]
        self.assertFalse(status["isError"])
        self.assertFalse(status["structuredContent"]["broker_ready"])

    def test_unknown_tool_is_a_tool_error(self) -> None:
        response = self.request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "missing", "arguments": {}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["error"], "UnknownTool")


if __name__ == "__main__":
    unittest.main()
