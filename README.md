# Codex Keyboard MCP

**Codex Keyboard MCP** is a Windows-only, local MCP (Model Context Protocol) server that gives Codex / ChatGPT agents full control of the keyboard and lets them operate applications and games that run with administrator privileges.

It is a clean, dependency-free Python project (requires Python 3.11 or later) that speaks the MCP protocol over **stdio** and installs as a Codex tool server.

**Why two processes?**

On Windows, User Interface Privilege Isolation (UIPI) blocks a normal-integrity process from sending input to a higher-integrity window. Elevating the stdio process itself would break the stdin/stdout connection the agent relies on, so the server splits into two components:

```
Codex ──STDIO──> non-elevated MCP bridge ──authenticated 127.0.0.1:47831──> admin keyboard broker ──SendInput──> target window
```

The first time `keyboard_start_elevated_broker` is called, Windows shows a UAC prompt; after the user clicks **Yes**, the broker stays alive so the agent keeps control of elevated apps without re-prompting. The project never bypasses the UAC secure desktop.

**Key capabilities**

- Inspect the bridge/broker integrity level and the current foreground window
- List visible windows and focus one by handle, title, or process name
- Type Unicode text
- Press single keys, modifier combos, and repeat a key
- Hold keys, separated key-down/key-up, and an emergency "release all tracked keys"
- Run an ordered sequence of up to 100 actions
- Choose between `virtual_key` and `scan_code` input modes (game controls prefer `scan_code`)
- Optional window-handle / title / process guards to prevent typing into the wrong window after focus changes

**Security & design notes**

- The broker listens only on the IPv4 loopback address `127.0.0.1:47831` and authenticates with a per-user 32-byte random key; IPC parses size-limited JSON and never deserializes arbitrary objects.
- The server does not log typed text and has no network egress.
- Key holds and sequences are capped at 30 seconds, and keys are released automatically on any error.
- Games using exclusive input, kernel-level anti-cheat, or that explicitly drop injected `SendInput` events may still reject synthetic input; administrator privileges cannot override such product policies.
- Use it only on programs you are authorized to control and test.

---

这是一个只面向 Windows 的本地 STDIO MCP 服务，让 Codex/Agent 能发送键盘输入，并能正常控制以管理员权限运行的应用或游戏窗口。

项目不依赖第三方 Python 包。需要 Python 3.11 或更高版本。

## 为什么分成两个进程

Windows 的 UIPI 会阻止普通权限进程向高完整性窗口发送输入。直接把 STDIO MCP 进程提权又容易破坏 Codex 与服务之间的标准输入/输出连接，因此本项目使用：

```text
Codex ──STDIO──> 普通权限 MCP bridge ──认证的 127.0.0.1:47831──> 管理员 keyboard broker ──SendInput──> 目标窗口
```

首次调用 `keyboard_start_elevated_broker` 时，Windows 会显示 UAC 确认框。用户手动点“是”后，broker 会保持运行，Agent 后续无需因为目标程序是管理员权限而失去控制。项目不会、也不应绕过 UAC 安全桌面。

## 能力

- 检查 bridge/broker 的完整性级别与当前前台窗口
- 列出可见窗口并按句柄、标题或进程名聚焦
- 输入 Unicode 文本
- 单键、组合键、重复按键
- 长按、独立 key-down/key-up、紧急释放所有受控按键
- 一次执行一组有序键盘动作
- `virtual_key` 与 `scan_code` 两种输入模式；游戏控制优先尝试 `scan_code`
- 可选的窗口句柄/标题/进程守卫，防止焦点漂移后误输入

## 安装到 Codex

在 PowerShell 中运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1
```

已有同名配置时，明确使用 `-Force` 更新：

```powershell
.\scripts\install.ps1 -Force
```

安装脚本等价于把下面的 STDIO 服务加入 Codex（路径会自动使用当前项目的绝对路径）：

```powershell
codex mcp add keyboard-control -- py -3 E:\keyboardcontrolMCP\run_server.py
```

然后重启 Codex/ChatGPT 桌面客户端。在任务中可以先让 Agent：

1. 调用 `keyboard_status`。
2. 若 `broker_ready` 为 `false`，调用 `keyboard_start_elevated_broker`；此时用户手动确认 UAC。
3. 调用 `keyboard_list_windows` 和 `keyboard_focus_window` 选定目标。
4. 发送输入时带上 `expected_window_handle` 或 `expected_process_name`。

Codex 当前支持本地 STDIO MCP，桌面客户端、CLI 和 IDE 扩展共享同一 MCP 配置。参见 [OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。

## 工具

| 工具 | 作用 |
|---|---|
| `keyboard_status` | 检查 bridge、broker、权限和前台窗口 |
| `keyboard_start_elevated_broker` | 请求 UAC 并启动管理员 broker |
| `keyboard_list_windows` | 列出/筛选可见顶层窗口 |
| `keyboard_focus_window` | 将目标窗口置于前台 |
| `keyboard_type_text` | 输入 Unicode 文本 |
| `keyboard_press_key` | 单键、组合键或重复按键 |
| `keyboard_hold_keys` | 在限定时间内同时长按多个键 |
| `keyboard_key_down` / `keyboard_key_up` | 分离的按下/释放操作 |
| `keyboard_release_all` | 释放 broker 记录的全部按下键 |
| `keyboard_elevated_self_test` | 创建管理员测试窗口并验证真实输入链路 |
| `keyboard_stop_elevated_broker` | 释放按键并停止管理员 broker |
| `keyboard_sequence` | 有序执行最多 100 个动作 |

常见按键名包括 `A`–`Z`、`0`–`9`、`F1`–`F24`、`enter`、`escape`、`tab`、`space`、`ctrl`、`shift`、`alt`、`win`、方向键、`home`、`end`、`insert`、`delete`、`pageup` 和 `pagedown`。

### 游戏输入示例

让角色向前移动 800 毫秒：

```json
{
  "keys": ["W"],
  "duration_ms": 800,
  "mode": "scan_code",
  "expected_process_name": "game.exe"
}
```

执行 `Ctrl+Shift+F1`：

```json
{
  "key": "F1",
  "modifiers": ["ctrl", "shift"],
  "mode": "virtual_key",
  "expected_window_handle": "0x123456"
}
```

## 测试

运行全部自动化测试：

```powershell
python -m unittest discover -s tests -v
```

运行会创建一个临时测试窗口并真正发送按键的烟雾测试：

```powershell
python tests\manual_keyboard_smoke.py
```

烟雾测试使用独立的临时认证端点和普通完整性 broker，不触碰其他应用。管理员链路可在安装后通过 `keyboard_start_elevated_broker` 的返回值确认：`broker.integrity.elevated` 必须是 `true`。也可以调用 `keyboard_elevated_self_test`，它会短暂打开一个管理员完整性测试窗口，验证 Unicode 输入和扫描码 Enter 后自动关闭。

完整的管理员烟雾测试会触发一次 UAC：

```powershell
python tests\elevated_keyboard_smoke.py
```


## 安全与限制

- broker 固定监听 IPv4 回环地址 `127.0.0.1:47831`（不使用 8080，也不绑定局域网网卡），并使用每用户 32 字节随机密钥做握手；IPC 只解析有大小限制的 JSON，不反序列化任意对象。
- 服务不会记录输入文本，不包含联网功能。
- `keyboard_hold_keys` 单次最多 30 秒，动作序列总等待/长按最多 30 秒；序列出错时会自动释放已按下的键。
- UAC/登录安全桌面不可自动操作。
- 采用独占输入、内核级反作弊或主动丢弃 `SendInput` 注入事件的游戏，可能仍会拒绝合成输入；管理员权限不能绕过此类产品策略。窗口化/无边框模式通常比独占全屏更易可靠聚焦。
- 请只在你有权控制和测试的程序上使用。

## 卸载

```powershell
.\scripts\uninstall.ps1
```

若还要删除当前用户的随机认证密钥，明确添加：

```powershell
.\scripts\uninstall.ps1 -RemoveRuntimeData
```
