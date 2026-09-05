from __future__ import annotations

import json
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any

from .runtime import BROKER_ENDPOINT, BROKER_HOST, BROKER_PORT, load_or_create_authkey
from .win32 import integrity_level


MAX_IPC_MESSAGE = 1_048_576


def _encode_message(message: dict[str, Any]) -> bytes:
    payload = json.dumps(
        message, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(payload) > MAX_IPC_MESSAGE:
        raise ValueError("IPC message exceeds the 1 MiB limit")
    return payload


def _decode_message(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_IPC_MESSAGE:
        raise ValueError("IPC message exceeds the 1 MiB limit")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("IPC message must be a JSON object")
    return value


def request_broker(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    authkey = load_or_create_authkey()
    connection = Client(BROKER_ENDPOINT, family="AF_INET", authkey=authkey)
    try:
        connection.send_bytes(
            _encode_message({"action": action, "params": params or {}})
        )
        response = _decode_message(connection.recv_bytes(MAX_IPC_MESSAGE))
    finally:
        connection.close()
    if response.get("ok") is not True:
        error = response.get("error")
        if not isinstance(error, dict):
            raise RuntimeError("Elevated broker returned an invalid error response")
        error_type = str(error.get("type", "BrokerError"))
        message = str(error.get("message", "Unknown broker error"))
        raise RuntimeError(f"{error_type}: {message}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Elevated broker returned an invalid result")
    return result


def broker_status() -> dict[str, Any] | None:
    try:
        return request_broker("status")
    except (
        AuthenticationError,
        FileNotFoundError,
        ConnectionError,
        EOFError,
        OSError,
        ValueError,
    ):
        return None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def launch_broker() -> dict[str, Any]:
    existing = broker_status()
    if existing is not None:
        integrity = existing.get("integrity")
        if not isinstance(integrity, dict) or integrity.get("elevated") is not True:
            raise RuntimeError(
                "A broker answered on the authenticated pipe but is not elevated; "
                "stop it before starting the administrator broker"
            )
        return {"started": False, "broker": existing}

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(BROKER_ENDPOINT)
    except OSError as exc:
        raise RuntimeError(
            f"Fixed broker port {BROKER_HOST}:{BROKER_PORT} is already occupied by another process"
        ) from exc
    finally:
        probe.close()

    # Ensure the key exists before crossing the integrity boundary. The elevated
    # process reads the same per-user file and therefore derives the same pipe.
    load_or_create_authkey()
    arguments = ["-m", "keyboard_mcp", "--broker"]
    cwd = str(_project_root())

    if bool(integrity_level()["elevated"]):
        creation_flags = 0
        creation_flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [sys.executable, *arguments],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
        )
    else:
        import ctypes

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.ShellExecuteW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_int,
        )
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        parameters = subprocess.list2cmdline(arguments)
        result = shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            parameters,
            cwd,
            0,  # SW_HIDE
        )
        result_code = int(result or 0)
        if result_code <= 32:
            if result_code == 5:
                raise PermissionError("UAC elevation was denied by the user")
            raise OSError(f"ShellExecuteW could not start the elevated broker ({result_code})")

    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status = request_broker("status")
            integrity = status.get("integrity")
            if not isinstance(integrity, dict) or integrity.get("elevated") is not True:
                raise RuntimeError("The started keyboard broker is not running at high integrity")
            return {"started": True, "broker": status}
        except (
            AuthenticationError,
            FileNotFoundError,
            ConnectionError,
            EOFError,
            OSError,
            ValueError,
        ) as exc:
            last_error = exc
            time.sleep(0.15)
    raise TimeoutError(
        "The broker did not become ready within 20 seconds after the UAC request"
        + (f": {last_error}" if last_error else "")
    )
