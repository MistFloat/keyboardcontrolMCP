from __future__ import annotations

import os
from pathlib import Path
import secrets


TOKEN_BYTES = 32
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 47831
BROKER_ENDPOINT = (BROKER_HOST, BROKER_PORT)


def runtime_dir() -> Path:
    override = os.environ.get("KEYBOARD_MCP_RUNTIME_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    return Path(local_app_data) / "CodexKeyboardMCP"


def authkey_path() -> Path:
    return runtime_dir() / "authkey.bin"


def load_or_create_authkey() -> bytes:
    folder = runtime_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = authkey_path()
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        data = secrets.token_bytes(TOKEN_BYTES)
        try:
            # Exclusive creation prevents two MCP instances from silently choosing
            # different keys during first-run startup.
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            data = path.read_bytes()
    if len(data) != TOKEN_BYTES:
        raise RuntimeError(f"Invalid broker auth key at {path}")
    return data
