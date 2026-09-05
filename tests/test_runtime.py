from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from keyboard_mcp import runtime
from keyboard_mcp import win32


@unittest.skipUnless(os.name == "nt", "Windows-only project")
class RuntimeTests(unittest.TestCase):
    def test_authkey_is_stable_and_endpoint_is_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, {"KEYBOARD_MCP_RUNTIME_DIR": temp}):
                first = runtime.load_or_create_authkey()
                second = runtime.load_or_create_authkey()
                self.assertEqual(first, second)
                self.assertEqual(len(first), runtime.TOKEN_BYTES)
                self.assertEqual(Path(temp) / "authkey.bin", runtime.authkey_path())
                self.assertEqual(runtime.BROKER_ENDPOINT, ("127.0.0.1", 47831))

    def test_native_input_layout_matches_windows_x64_abi(self) -> None:
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(win32.INPUT), expected)

    def test_key_resolution_and_integrity(self) -> None:
        self.assertEqual(win32.resolve_key("F12").vk, 0x7B)
        self.assertEqual(win32.resolve_key("page-down").vk, 0x22)
        level = win32.integrity_level()
        self.assertIn(level["name"], {"low", "medium", "high", "system"})
        self.assertIsInstance(level["elevated"], bool)


if __name__ == "__main__":
    unittest.main()
