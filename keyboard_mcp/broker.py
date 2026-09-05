from __future__ import annotations

import json
from multiprocessing.connection import Listener
import os
import signal
import threading
import time
from typing import Any, Iterable
import uuid

from .ipc import MAX_IPC_MESSAGE
from .runtime import BROKER_ENDPOINT, BROKER_HOST, BROKER_PORT, load_or_create_authkey
from . import win32


MAX_TEXT_UNITS = 20_000
MAX_SEQUENCE_ACTIONS = 100
MAX_SEQUENCE_WAIT_MS = 30_000
MAX_HOLD_MS = 30_000
MAX_TIMED_OPERATION_MS = 30_000


def _integer(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _mode(value: object) -> str:
    if value is None:
        return "virtual_key"
    if value not in ("virtual_key", "scan_code"):
        raise ValueError("mode must be 'virtual_key' or 'scan_code'")
    return str(value)


def _string_list(value: object, name: str, *, maximum: int = 8) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty array of key names")
    if len(value) > maximum:
        raise ValueError(f"{name} may contain at most {maximum} keys")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"every item in {name} must be a non-empty string")
    return list(value)


def _encoded(payload: dict[str, Any]) -> bytes:
    data = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(data) > MAX_IPC_MESSAGE:
        return json.dumps(
            {
                "ok": False,
                "error": {
                    "type": "ResponseTooLarge",
                    "message": "Broker response exceeded the 1 MiB IPC limit",
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
    return data


class KeyboardBroker:
    def __init__(self) -> None:
        self._pressed: set[tuple[int, str]] = set()
        self._lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self.started_at = time.time()

    def status(self) -> dict[str, Any]:
        return {
            "ready": True,
            "pid": os.getpid(),
            "integrity": win32.integrity_level(),
            "started_at_unix": self.started_at,
            "endpoint": {"host": BROKER_HOST, "port": BROKER_PORT},
            "foreground_window": win32.foreground_window(),
            "pressed_key_count": len(self._pressed),
        }

    @staticmethod
    def _guard_target(params: dict[str, Any]) -> dict[str, object] | None:
        current = win32.foreground_window()
        expected_handle = params.get("expected_window_handle")
        expected_title = params.get("expected_title_contains")
        expected_process = params.get("expected_process_name")
        if expected_handle is None and expected_title is None and expected_process is None:
            return current
        if current is None:
            raise RuntimeError("There is no foreground window")
        if expected_handle is not None:
            parsed = win32.parse_window_handle(expected_handle)
            if int(current["handle"]) != parsed:
                raise RuntimeError(
                    f"Foreground-window guard failed: expected handle 0x{parsed:X}, "
                    f"got {current['handle_hex']}"
                )
        if expected_title is not None:
            if not isinstance(expected_title, str) or not expected_title:
                raise ValueError("expected_title_contains must be a non-empty string")
            if expected_title.casefold() not in str(current["title"]).casefold():
                raise RuntimeError(
                    "Foreground-window guard failed: expected title containing "
                    f"{expected_title!r}, got {current['title']!r}"
                )
        if expected_process is not None:
            if not isinstance(expected_process, str) or not expected_process:
                raise ValueError("expected_process_name must be a non-empty string")
            actual = str(current.get("process_name") or "")
            if actual.casefold() != expected_process.casefold():
                raise RuntimeError(
                    "Foreground-window guard failed: expected process "
                    f"{expected_process!r}, got {actual!r}"
                )
        return current

    @staticmethod
    def _filtered_windows(params: dict[str, Any]) -> list[dict[str, object]]:
        title = params.get("title_contains")
        process = params.get("process_name")
        if title is not None and (not isinstance(title, str) or not title):
            raise ValueError("title_contains must be a non-empty string")
        if process is not None and (not isinstance(process, str) or not process):
            raise ValueError("process_name must be a non-empty string")
        windows = win32.list_windows()
        if title is not None:
            windows = [
                item
                for item in windows
                if title.casefold() in str(item["title"]).casefold()
            ]
        if process is not None:
            windows = [
                item
                for item in windows
                if str(item.get("process_name") or "").casefold() == process.casefold()
            ]
        return windows

    def list_windows(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = _integer(params.get("limit", 100), "limit", minimum=1, maximum=500)
        windows = self._filtered_windows(params)
        return {"count": len(windows), "windows": windows[:limit], "truncated": len(windows) > limit}

    def focus_window(self, params: dict[str, Any]) -> dict[str, Any]:
        handle = params.get("window_handle")
        if handle is not None:
            selected = win32.parse_window_handle(handle)
        else:
            if params.get("title_contains") is None and params.get("process_name") is None:
                raise ValueError(
                    "Provide window_handle, title_contains, or process_name to select a window"
                )
            matches = self._filtered_windows(params)
            if not matches:
                raise ValueError("No visible top-level window matched the selector")
            selected = int(matches[0]["handle"])
        focused = win32.focus_window(selected)
        return {"focused": True, "window": focused}

    def type_text(self, params: dict[str, Any]) -> dict[str, Any]:
        text = params.get("text")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        units = len(text.encode("utf-16-le", errors="surrogatepass")) // 2
        if units > MAX_TEXT_UNITS:
            raise ValueError(f"text may contain at most {MAX_TEXT_UNITS} UTF-16 code units")
        interval = _integer(
            params.get("interval_ms", 0), "interval_ms", minimum=0, maximum=1000
        )
        if units * interval > MAX_TIMED_OPERATION_MS:
            raise ValueError(
                f"text length × interval_ms may not exceed {MAX_TIMED_OPERATION_MS} ms"
            )
        before = self._guard_target(params)
        sent = win32.type_text(text, interval)
        return {"sent_utf16_units": sent, "foreground_window": before}

    def press_key(self, params: dict[str, Any]) -> dict[str, Any]:
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        modifiers_raw = params.get("modifiers", [])
        if not isinstance(modifiers_raw, list) or len(modifiers_raw) > 8:
            raise ValueError("modifiers must be an array containing at most 8 key names")
        if any(not isinstance(item, str) or not item for item in modifiers_raw):
            raise ValueError("every modifier must be a non-empty string")
        repeats = _integer(params.get("repeats", 1), "repeats", minimum=1, maximum=100)
        interval = _integer(
            params.get("interval_ms", 50), "interval_ms", minimum=0, maximum=1000
        )
        if max(repeats - 1, 0) * interval > MAX_TIMED_OPERATION_MS:
            raise ValueError(
                f"repeat delay may not exceed {MAX_TIMED_OPERATION_MS} ms in total"
            )
        mode = _mode(params.get("mode"))
        before = self._guard_target(params)
        for index in range(repeats):
            win32.press_key(key, modifiers_raw, mode=mode)
            if index + 1 < repeats and interval:
                time.sleep(interval / 1000)
        return {
            "key": key,
            "modifiers": modifiers_raw,
            "repeats": repeats,
            "mode": mode,
            "foreground_window": before,
        }

    def _set_keys(self, keys: Iterable[str], *, key_up: bool, mode: str) -> list[int]:
        resolved: list[int] = []
        for key in keys:
            spec = win32.resolve_key(key)
            vks = [*spec.implicit_modifiers, spec.vk]
            if key_up:
                vks.reverse()
            for vk in vks:
                token = (vk, mode)
                if key_up:
                    win32.key_event(vk, key_up=True, mode=mode)
                    self._pressed.discard(token)
                else:
                    win32.key_event(vk, mode=mode)
                    self._pressed.add(token)
                resolved.append(vk)
        return resolved

    def key_down(self, params: dict[str, Any]) -> dict[str, Any]:
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        mode = _mode(params.get("mode"))
        before = self._guard_target(params)
        with self._lock:
            self._set_keys([key], key_up=False, mode=mode)
        return {"key": key, "state": "down", "mode": mode, "foreground_window": before}

    def key_up(self, params: dict[str, Any]) -> dict[str, Any]:
        key = params.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        mode = _mode(params.get("mode"))
        before = self._guard_target(params)
        with self._lock:
            self._set_keys([key], key_up=True, mode=mode)
        return {"key": key, "state": "up", "mode": mode, "foreground_window": before}

    def hold_keys(self, params: dict[str, Any]) -> dict[str, Any]:
        keys = _string_list(params.get("keys"), "keys")
        duration = _integer(
            params.get("duration_ms"), "duration_ms", minimum=1, maximum=MAX_HOLD_MS
        )
        mode = _mode(params.get("mode"))
        before = self._guard_target(params)
        with self._lock:
            self._set_keys(keys, key_up=False, mode=mode)
        try:
            time.sleep(duration / 1000)
        finally:
            with self._lock:
                self._set_keys(reversed(keys), key_up=True, mode=mode)
        return {
            "keys": keys,
            "held_ms": duration,
            "mode": mode,
            "foreground_window": before,
        }

    def release_all(self, _params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            pressed = list(self._pressed)
            errors: list[str] = []
            for vk, mode in reversed(pressed):
                try:
                    win32.key_event(vk, key_up=True, mode=mode)
                except Exception as exc:  # continue releasing the remaining keys
                    errors.append(str(exc))
                finally:
                    self._pressed.discard((vk, mode))
        return {"released_count": len(pressed), "errors": errors}

    def shutdown(self, _params: dict[str, Any]) -> dict[str, Any]:
        released = self.release_all({})

        def exit_after_response() -> None:
            time.sleep(0.15)
            os._exit(0)

        threading.Thread(target=exit_after_response, daemon=True).start()
        return {"stopping": True, **released}

    def self_test(self, _params: dict[str, Any]) -> dict[str, Any]:
        """Create a same-integrity window and verify real Unicode + scan-code input."""
        import tkinter as tk

        title = f"Codex Keyboard MCP Self-Test {uuid.uuid4().hex}"
        expected = "Codex管理员键盘MCP✓"
        received: list[str] = []
        root = tk.Tk()
        root.title(title)
        root.geometry("560x120")
        tk.Label(root, text="Elevated Keyboard MCP self-test").pack(pady=(12, 4))
        entry = tk.Entry(root, width=70)
        entry.pack(padx=12, pady=4)

        def capture(_event: object) -> str:
            received.append(entry.get())
            return "break"

        entry.bind("<Return>", capture)
        try:
            root.update_idletasks()
            root.update()
            matches = [
                item
                for item in win32.list_windows()
                if item["title"] == title and item["pid"] == os.getpid()
            ]
            if not matches:
                raise RuntimeError("The elevated self-test window could not be discovered")
            target = matches[0]
            win32.focus_window(int(target["handle"]))
            entry.focus_force()
            root.update()
            win32.type_text(expected, interval_ms=2)
            win32.press_key("enter", mode="scan_code")
            deadline = time.monotonic() + 3
            while not received and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            actual = received[0] if received else None
            if actual != expected:
                raise AssertionError(
                    f"Elevated input verification failed: expected {expected!r}, got {actual!r}"
                )
            return {
                "success": True,
                "broker_integrity": win32.integrity_level(),
                "target_window": target,
                "unicode_text_verified": True,
                "scan_code_enter_verified": True,
                "received": actual,
            }
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def sequence(self, params: dict[str, Any]) -> dict[str, Any]:
        actions = params.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("actions must be a non-empty array")
        if len(actions) > MAX_SEQUENCE_ACTIONS:
            raise ValueError(f"actions may contain at most {MAX_SEQUENCE_ACTIONS} items")
        wait_budget = 0
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError("every sequence action must be an object")
            op = action.get("op")
            if op == "wait":
                wait_budget += _integer(
                    action.get("duration_ms"), "duration_ms", minimum=0, maximum=MAX_HOLD_MS
                )
            elif op == "hold":
                wait_budget += _integer(
                    action.get("duration_ms"), "duration_ms", minimum=1, maximum=MAX_HOLD_MS
                )
            elif op == "type":
                text = action.get("text")
                if not isinstance(text, str):
                    raise ValueError("type action text must be a string")
                units = len(text.encode("utf-16-le", errors="surrogatepass")) // 2
                interval = _integer(
                    action.get("interval_ms", 0), "interval_ms", minimum=0, maximum=1000
                )
                wait_budget += units * interval
            elif op == "press":
                repeats = _integer(
                    action.get("repeats", 1), "repeats", minimum=1, maximum=100
                )
                interval = _integer(
                    action.get("interval_ms", 50), "interval_ms", minimum=0, maximum=1000
                )
                wait_budget += max(repeats - 1, 0) * interval
        if wait_budget > MAX_SEQUENCE_WAIT_MS:
            raise ValueError(
                f"total wait/hold time may not exceed {MAX_SEQUENCE_WAIT_MS} ms"
            )

        guard = {
            name: params[name]
            for name in (
                "expected_window_handle",
                "expected_title_contains",
                "expected_process_name",
            )
            if name in params
        }
        completed = 0
        try:
            for action in actions:
                op = action.get("op")
                merged = {**action, **guard}
                if op == "type":
                    self.type_text(merged)
                elif op == "press":
                    self.press_key(merged)
                elif op == "key_down":
                    self.key_down(merged)
                elif op == "key_up":
                    self.key_up(merged)
                elif op == "hold":
                    self.hold_keys(merged)
                elif op == "wait":
                    time.sleep(int(action["duration_ms"]) / 1000)
                else:
                    raise ValueError(
                        f"Unsupported sequence op {op!r}; use type, press, key_down, key_up, hold, or wait"
                    )
                completed += 1
        except Exception:
            self.release_all({})
            raise
        return {"completed_actions": completed, "total_actions": len(actions)}

    def dispatch(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "status": self.status,
            "list_windows": self.list_windows,
            "focus_window": self.focus_window,
            "type_text": self.type_text,
            "press_key": self.press_key,
            "key_down": self.key_down,
            "key_up": self.key_up,
            "hold_keys": self.hold_keys,
            "release_all": self.release_all,
            "self_test": self.self_test,
            "shutdown": self.shutdown,
            "sequence": self.sequence,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unknown broker action: {action!r}")
        if action == "status":
            return handler()  # type: ignore[call-arg]
        if action in {"list_windows", "release_all", "shutdown"}:
            return handler(params)  # type: ignore[call-arg]
        with self._operation_lock:
            return handler(params)  # type: ignore[call-arg]


def _handle_connection(connection: Any, broker: KeyboardBroker) -> None:
    try:
        raw = connection.recv_bytes(MAX_IPC_MESSAGE)
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("IPC request must be a JSON object")
        action = request.get("action")
        params = request.get("params", {})
        if not isinstance(action, str):
            raise ValueError("IPC action must be a string")
        if not isinstance(params, dict):
            raise ValueError("IPC params must be an object")
        result = broker.dispatch(action, params)
        response = {"ok": True, "result": result}
    except Exception as exc:
        response = {
            "ok": False,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    try:
        connection.send_bytes(_encoded(response))
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        connection.close()


def run_broker(*, allow_medium: bool = False) -> None:
    level = win32.integrity_level()
    if not level["elevated"] and not allow_medium:
        raise SystemExit("The keyboard broker must run with high integrity (administrator).")

    authkey = load_or_create_authkey()
    broker = KeyboardBroker()

    def release_before_exit(_signum: int, _frame: object) -> None:
        broker.release_all({})
        raise SystemExit(0)

    signal.signal(signal.SIGINT, release_before_exit)
    signal.signal(signal.SIGTERM, release_before_exit)

    listener = Listener(BROKER_ENDPOINT, family="AF_INET", authkey=authkey)
    try:
        while True:
            connection = listener.accept()
            thread = threading.Thread(
                target=_handle_connection,
                args=(connection, broker),
                daemon=True,
            )
            thread.start()
    finally:
        broker.release_all({})
        listener.close()
