from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Iterable


if os.name != "nt":
    raise RuntimeError("keyboard_mcp.win32 is available on Windows only")


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

ULONG_PTR = ctypes.c_size_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC_EX = 4
SW_RESTORE = 9

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetClassNameW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.EnumWindows.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = ctypes.c_short
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

advapi32.OpenProcessToken.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
)
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
)
advapi32.GetTokenInformation.restype = wintypes.BOOL
advapi32.GetSidSubAuthorityCount.argtypes = (wintypes.LPVOID,)
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = (wintypes.LPVOID, wintypes.DWORD)
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)


VK: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    "num0": 0x60,
    "num1": 0x61,
    "num2": 0x62,
    "num3": 0x63,
    "num4": 0x64,
    "num5": 0x65,
    "num6": 0x66,
    "num7": 0x67,
    "num8": 0x68,
    "num9": 0x69,
    "multiply": 0x6A,
    "add": 0x6B,
    "subtract": 0x6D,
    "decimal": 0x6E,
    "divide": 0x6F,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
    "volume_mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "media_next": 0xB0,
    "media_previous": 0xB1,
    "media_stop": 0xB2,
    "media_play_pause": 0xB3,
}
VK.update({chr(code).casefold(): code for code in range(ord("A"), ord("Z") + 1)})
VK.update({str(number): ord(str(number)) for number in range(10)})
VK.update({f"f{number}": 0x6F + number for number in range(1, 25)})
VK_NORMALIZED = {
    name.replace("_", "").replace("-", ""): value for name, value in VK.items()
}

EXTENDED_KEYS = {
    0x21,
    0x22,
    0x23,
    0x24,
    0x25,
    0x26,
    0x27,
    0x28,
    0x2D,
    0x2E,
    0x5B,
    0x5C,
    0x5D,
    0x6F,
    0xA3,
    0xA5,
}


@dataclass(frozen=True)
class KeySpec:
    vk: int
    implicit_modifiers: tuple[int, ...] = ()


def _windows_error(message: str) -> OSError:
    code = ctypes.get_last_error()
    return ctypes.WinError(code, message)


def integrity_level() -> dict[str, int | str | bool]:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise _windows_error("OpenProcessToken failed")
    try:
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(
            token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(needed)
        )
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token,
            TOKEN_INTEGRITY_LEVEL,
            buffer,
            needed,
            ctypes.byref(needed),
        ):
            raise _windows_error("GetTokenInformation failed")
        label = ctypes.cast(buffer, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        count = advapi32.GetSidSubAuthorityCount(label.Label.Sid).contents.value
        rid = advapi32.GetSidSubAuthority(label.Label.Sid, count - 1).contents.value
    finally:
        kernel32.CloseHandle(token)

    if rid >= 0x00004000:
        name = "system"
    elif rid >= 0x00003000:
        name = "high"
    elif rid >= 0x00002000:
        name = "medium"
    else:
        name = "low"
    return {"name": name, "rid": rid, "elevated": rid >= 0x00003000}


def resolve_key(key: str) -> KeySpec:
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty string")
    normalized = key.strip().casefold().replace("_", "").replace("-", "")
    aliases = {
        "pgup": "pageup",
        "pgdn": "pagedown",
        "del": "delete",
        "ins": "insert",
        "windows": "win",
        "cmd": "win",
        "option": "alt",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in VK_NORMALIZED:
        return KeySpec(VK_NORMALIZED[normalized])
    if len(key) == 1:
        encoded = user32.VkKeyScanW(key)
        if encoded == -1:
            raise ValueError(f"Character {key!r} is not available in the active keyboard layout")
        vk = encoded & 0xFF
        shift_state = (encoded >> 8) & 0xFF
        modifiers: list[int] = []
        if shift_state & 1:
            modifiers.append(VK["shift"])
        if shift_state & 2:
            modifiers.append(VK["ctrl"])
        if shift_state & 4:
            modifiers.append(VK["alt"])
        return KeySpec(vk, tuple(modifiers))
    raise ValueError(f"Unsupported key name: {key!r}")


def _keyboard_input(
    vk: int, *, key_up: bool = False, mode: str = "virtual_key"
) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    scan = 0
    event_vk = vk
    if mode == "scan_code":
        mapped = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
        if not mapped:
            raise ValueError(f"No hardware scan code is available for virtual key 0x{vk:02X}")
        scan = mapped & 0xFF
        event_vk = 0
        flags |= KEYEVENTF_SCANCODE
        if mapped & 0xFF00 in (0xE000, 0xE100):
            flags |= KEYEVENTF_EXTENDEDKEY
    elif mode != "virtual_key":
        raise ValueError("mode must be 'virtual_key' or 'scan_code'")
    if mode == "virtual_key" and vk in EXTENDED_KEYS:
        flags |= KEYEVENTF_EXTENDEDKEY
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(event_vk, scan, flags, 0, 0))


def _unicode_input(code_unit: int, *, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, code_unit, flags, 0, 0))


def send_inputs(events: Iterable[INPUT]) -> int:
    items = list(events)
    if not items:
        return 0
    array_type = INPUT * len(items)
    array = array_type(*items)
    sent = user32.SendInput(len(items), array, ctypes.sizeof(INPUT))
    if sent != len(items):
        code = ctypes.get_last_error()
        detail = f"SendInput inserted {sent} of {len(items)} events"
        if code:
            raise ctypes.WinError(code, detail)
        raise OSError(
            detail
            + "; Windows may be blocking input across an integrity-level or secure-desktop boundary"
        )
    return sent


def key_event(vk: int, *, key_up: bool = False, mode: str = "virtual_key") -> None:
    send_inputs([_keyboard_input(vk, key_up=key_up, mode=mode)])


def press_key(
    key: str, modifiers: Iterable[str] = (), *, mode: str = "virtual_key"
) -> None:
    spec = resolve_key(key)
    modifier_specs = [resolve_key(item) for item in modifiers]
    modifier_vks = [item.vk for item in modifier_specs]
    for implicit in spec.implicit_modifiers:
        if implicit not in modifier_vks:
            modifier_vks.append(implicit)
    events = [_keyboard_input(vk, mode=mode) for vk in modifier_vks]
    events.append(_keyboard_input(spec.vk, mode=mode))
    events.append(_keyboard_input(spec.vk, key_up=True, mode=mode))
    events.extend(
        _keyboard_input(vk, key_up=True, mode=mode) for vk in reversed(modifier_vks)
    )
    send_inputs(events)


def type_text(text: str, interval_ms: int = 0) -> int:
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    utf16 = text.encode("utf-16-le", errors="surrogatepass")
    units = [int.from_bytes(utf16[index : index + 2], "little") for index in range(0, len(utf16), 2)]
    if interval_ms <= 0:
        events: list[INPUT] = []
        for unit in units:
            events.extend((_unicode_input(unit), _unicode_input(unit, key_up=True)))
        send_inputs(events)
    else:
        for unit in units:
            send_inputs((_unicode_input(unit), _unicode_input(unit, key_up=True)))
            time.sleep(interval_ms / 1000)
    return len(units)


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(length + 1, 2))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _process_path(pid: int) -> str | None:
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        kernel32.CloseHandle(process)


def window_info(hwnd: int) -> dict[str, object]:
    pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    path = _process_path(pid.value)
    return {
        "handle": int(hwnd),
        "handle_hex": f"0x{int(hwnd):X}",
        "title": _window_text(hwnd),
        "class_name": _class_name(hwnd),
        "pid": pid.value,
        "thread_id": thread_id,
        "process_name": Path(path).name if path else None,
        "process_path": path,
        "visible": bool(user32.IsWindowVisible(hwnd)),
    }


def foreground_window() -> dict[str, object] | None:
    hwnd = user32.GetForegroundWindow()
    return window_info(hwnd) if hwnd else None


def list_windows() -> list[dict[str, object]]:
    handles: list[int] = []

    @WNDENUMPROC
    def callback(hwnd: wintypes.HWND, _lparam: wintypes.LPARAM) -> bool:
        if user32.IsWindowVisible(hwnd) and _window_text(hwnd):
            handles.append(int(hwnd))
        return True

    if not user32.EnumWindows(callback, 0):
        raise _windows_error("EnumWindows failed")
    return [window_info(hwnd) for hwnd in handles]


def parse_window_handle(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip(), 0)
    raise ValueError("window_handle must be an integer or a decimal/0x-prefixed string")


def focus_window(hwnd: int) -> dict[str, object]:
    target = window_info(hwnd)
    if not target["visible"]:
        raise ValueError(f"Window {target['handle_hex']} is not visible")

    user32.ShowWindow(hwnd, SW_RESTORE)
    current_thread = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    foreground_pid = wintypes.DWORD()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
        if foreground
        else 0
    )
    target_thread = int(target["thread_id"])
    attached: list[int] = []
    try:
        for thread in (foreground_thread, target_thread):
            if thread and thread != current_thread and thread not in attached:
                if user32.AttachThreadInput(current_thread, thread, True):
                    attached.append(thread)
        user32.BringWindowToTop(hwnd)
        success = bool(user32.SetForegroundWindow(hwnd))
    finally:
        for thread in reversed(attached):
            user32.AttachThreadInput(current_thread, thread, False)

    time.sleep(0.08)
    actual = user32.GetForegroundWindow()
    if not success or actual != hwnd:
        raise OSError(
            f"Windows refused to focus {target['handle_hex']}; current foreground window is "
            f"{f'0x{int(actual):X}' if actual else 'none'}"
        )
    return window_info(hwnd)
