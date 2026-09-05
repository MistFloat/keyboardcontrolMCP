from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Callable

from . import __version__
from .ipc import broker_status, launch_broker, request_broker
from .runtime import BROKER_HOST, BROKER_PORT
from .win32 import foreground_window, integrity_level


SERVER_NAME = "codex-keyboard-control"
LATEST_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", LATEST_PROTOCOL}

INSTRUCTIONS = (
    "Windows keyboard control, including administrator apps. Before sending input, call "
    "keyboard_status; if broker_ready is false, call keyboard_start_elevated_broker and ask "
    "the user to approve the Windows UAC prompt. Prefer keyboard_list_windows then "
    "keyboard_focus_window. For every input call, set expected_window_handle or "
    "expected_process_name to prevent focus mistakes. Use scan_code mode for games and "
    "virtual_key mode for normal apps/shortcuts. Never attempt to automate the UAC secure "
    "desktop. Call keyboard_release_all after interrupted key-down workflows."
)

GUARD_PROPERTIES: dict[str, Any] = {
    "expected_window_handle": {
        "description": "Optional foreground-window guard as an integer or 0x-prefixed string.",
        "anyOf": [{"type": "integer"}, {"type": "string"}],
    },
    "expected_title_contains": {
        "type": "string",
        "minLength": 1,
        "description": "Optional case-insensitive substring required in the foreground title.",
    },
    "expected_process_name": {
        "type": "string",
        "minLength": 1,
        "description": "Optional exact foreground executable name, for example game.exe.",
    },
}

MODE_PROPERTY = {
    "type": "string",
    "enum": ["virtual_key", "scan_code"],
    "default": "virtual_key",
    "description": "Use scan_code for games/raw-input style controls; use virtual_key for apps and shortcuts.",
}


def _object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _annotations(
    title: str,
    *,
    read_only: bool = False,
    idempotent: bool = False,
) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "keyboard_status",
        "description": (
            "Check the STDIO bridge, elevated broker, integrity levels, foreground window, "
            "and any keys currently held by the broker. Call this first."
        ),
        "inputSchema": _object_schema(),
        "annotations": _annotations("Keyboard status", read_only=True, idempotent=True),
    },
    {
        "name": "keyboard_start_elevated_broker",
        "description": (
            "Start the administrator keyboard broker. Windows shows a UAC consent prompt "
            "that the user must approve manually; UAC's secure desktop is intentionally not automated."
        ),
        "inputSchema": _object_schema(),
        "annotations": _annotations("Start elevated keyboard broker", idempotent=True),
    },
    {
        "name": "keyboard_list_windows",
        "description": "List visible top-level Windows windows so a target can be selected safely.",
        "inputSchema": _object_schema(
            {
                "title_contains": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional case-insensitive title filter.",
                },
                "process_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional exact executable-name filter.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            }
        ),
        "annotations": _annotations("List windows", read_only=True, idempotent=True),
    },
    {
        "name": "keyboard_focus_window",
        "description": (
            "Bring a visible top-level window to the foreground. Prefer a handle returned by "
            "keyboard_list_windows; otherwise the topmost matching title/process is selected."
        ),
        "inputSchema": _object_schema(
            {
                "window_handle": {
                    "anyOf": [{"type": "integer"}, {"type": "string"}],
                    "description": "Window handle as an integer or 0x-prefixed string.",
                },
                "title_contains": {"type": "string", "minLength": 1},
                "process_name": {"type": "string", "minLength": 1},
            }
        ),
        "annotations": _annotations("Focus window"),
    },
    {
        "name": "keyboard_type_text",
        "description": (
            "Type Unicode text into the current foreground window using SendInput. This is for "
            "text entry; use keyboard_press_key or scan-code actions for game controls."
        ),
        "inputSchema": _object_schema(
            {
                "text": {"type": "string", "maxLength": 20000},
                "interval_ms": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 0},
                **GUARD_PROPERTIES,
            },
            ["text"],
        ),
        "annotations": _annotations("Type text"),
    },
    {
        "name": "keyboard_press_key",
        "description": (
            "Press and release one key, optionally with modifiers and repeats. Examples: key=F5, "
            "or key=C with modifiers=[ctrl]."
        ),
        "inputSchema": _object_schema(
            {
                "key": {"type": "string", "minLength": 1},
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 8,
                    "default": [],
                },
                "repeats": {"type": "integer", "minimum": 1, "maximum": 100, "default": 1},
                "interval_ms": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 50},
                "mode": MODE_PROPERTY,
                **GUARD_PROPERTIES,
            },
            ["key"],
        ),
        "annotations": _annotations("Press key"),
    },
    {
        "name": "keyboard_hold_keys",
        "description": (
            "Hold one or more keys simultaneously for a bounded duration, then always release "
            "them. Suitable for game movement; duration is capped at 30 seconds."
        ),
        "inputSchema": _object_schema(
            {
                "keys": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "maxItems": 8,
                },
                "duration_ms": {"type": "integer", "minimum": 1, "maximum": 30000},
                "mode": MODE_PROPERTY,
                **GUARD_PROPERTIES,
            },
            ["keys", "duration_ms"],
        ),
        "annotations": _annotations("Hold keys"),
    },
    {
        "name": "keyboard_key_down",
        "description": (
            "Press a key without releasing it. Use only when a later key_up is required and call "
            "keyboard_release_all if the workflow is interrupted."
        ),
        "inputSchema": _object_schema(
            {"key": {"type": "string", "minLength": 1}, "mode": MODE_PROPERTY, **GUARD_PROPERTIES},
            ["key"],
        ),
        "annotations": _annotations("Key down"),
    },
    {
        "name": "keyboard_key_up",
        "description": "Release a key previously sent with keyboard_key_down.",
        "inputSchema": _object_schema(
            {"key": {"type": "string", "minLength": 1}, "mode": MODE_PROPERTY, **GUARD_PROPERTIES},
            ["key"],
        ),
        "annotations": _annotations("Key up", idempotent=True),
    },
    {
        "name": "keyboard_release_all",
        "description": "Emergency safety action: release every key currently tracked as down by the broker.",
        "inputSchema": _object_schema(),
        "annotations": _annotations("Release all tracked keys", idempotent=True),
    },
    {
        "name": "keyboard_stop_elevated_broker",
        "description": (
            "Release all tracked keys and stop the administrator broker. A later keyboard action "
            "will require starting it again and approving UAC again."
        ),
        "inputSchema": _object_schema(),
        "annotations": _annotations("Stop elevated keyboard broker", idempotent=True),
    },
    {
        "name": "keyboard_elevated_self_test",
        "description": (
            "Temporarily create a diagnostic window at the broker's administrator integrity, "
            "send real Unicode and scan-code input to it, verify the received value, then close it."
        ),
        "inputSchema": _object_schema(),
        "annotations": _annotations("Test elevated keyboard input"),
    },
    {
        "name": "keyboard_sequence",
        "description": (
            "Run up to 100 type/press/key_down/key_up/hold/wait actions as one ordered operation. "
            "Total hold/wait time is capped at 30 seconds; held keys are released on any error."
        ),
        "inputSchema": _object_schema(
            {
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["type", "press", "key_down", "key_up", "hold", "wait"],
                            },
                            "text": {"type": "string"},
                            "key": {"type": "string", "minLength": 1},
                            "keys": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "minItems": 1,
                                "maxItems": 8,
                            },
                            "modifiers": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                                "maxItems": 8,
                            },
                            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 30000},
                            "interval_ms": {"type": "integer", "minimum": 0, "maximum": 1000},
                            "repeats": {"type": "integer", "minimum": 1, "maximum": 100},
                            "mode": MODE_PROPERTY,
                        },
                        "required": ["op"],
                        "additionalProperties": False,
                    },
                },
                **GUARD_PROPERTIES,
            },
            ["actions"],
        ),
        "annotations": _annotations("Run keyboard sequence"),
    },
]


def _status(_arguments: dict[str, Any]) -> dict[str, Any]:
    broker = broker_status()
    return {
        "platform": sys.platform,
        "bridge_pid": os.getpid(),
        "bridge_integrity": integrity_level(),
        "broker_endpoint": {"host": BROKER_HOST, "port": BROKER_PORT},
        "bridge_foreground_window": foreground_window(),
        "broker_ready": broker is not None,
        "broker": broker,
        "next_action": (
            "ready"
            if broker is not None
            else "Call keyboard_start_elevated_broker and have the user approve UAC."
        ),
    }


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "keyboard_status": _status,
    "keyboard_start_elevated_broker": lambda _arguments: launch_broker(),
    "keyboard_list_windows": lambda arguments: request_broker("list_windows", arguments),
    "keyboard_focus_window": lambda arguments: request_broker("focus_window", arguments),
    "keyboard_type_text": lambda arguments: request_broker("type_text", arguments),
    "keyboard_press_key": lambda arguments: request_broker("press_key", arguments),
    "keyboard_hold_keys": lambda arguments: request_broker("hold_keys", arguments),
    "keyboard_key_down": lambda arguments: request_broker("key_down", arguments),
    "keyboard_key_up": lambda arguments: request_broker("key_up", arguments),
    "keyboard_release_all": lambda arguments: request_broker("release_all", arguments),
    "keyboard_elevated_self_test": lambda arguments: request_broker("self_test", arguments),
    "keyboard_stop_elevated_broker": lambda arguments: request_broker("shutdown", arguments),
    "keyboard_sequence": lambda arguments: request_broker("sequence", arguments),
}


def _tool_result(result: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            }
        ],
        "structuredContent": result,
        "isError": is_error,
    }


def _call_tool(params: object) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _tool_result(
            {"error": "InvalidParams", "message": "tools/call params must be an object"},
            is_error=True,
        )
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or name not in TOOL_HANDLERS:
        return _tool_result(
            {"error": "UnknownTool", "message": f"Unknown keyboard tool: {name!r}"},
            is_error=True,
        )
    if not isinstance(arguments, dict):
        return _tool_result(
            {"error": "InvalidArguments", "message": "Tool arguments must be an object"},
            is_error=True,
        )
    try:
        return _tool_result(TOOL_HANDLERS[name](arguments))
    except Exception as exc:
        if os.environ.get("KEYBOARD_MCP_DEBUG") == "1":
            traceback.print_exc(file=sys.stderr)
        return _tool_result(
            {"error": type(exc).__name__, "message": str(exc)}, is_error=True
        )


def _response(message_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def _handle_message(message: object) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request")
    message_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return _error(message_id, -32600, "Invalid Request")
    if method.startswith("notifications/"):
        return None
    if "id" not in message:
        return None
    if method == "initialize":
        params = message.get("params", {})
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol = requested if requested in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
        return _response(
            message_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": __version__},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})
    if method == "tools/call":
        return _response(message_id, _call_tool(message.get("params")))
    return _error(message_id, -32601, "Method not found")


def run_stdio_server() -> None:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw_line in stdin:
        if not raw_line.strip():
            continue
        try:
            message = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = _error(None, -32700, "Parse error")
        else:
            response = _handle_message(message)
        if response is not None:
            payload = json.dumps(
                response,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            stdout.write(payload + b"\n")
            stdout.flush()
