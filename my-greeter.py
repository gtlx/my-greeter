#!/usr/bin/env python3
"""
my-greeter - 自写的 greetd greeter (前端)
通信协议: 见 https://man.archlinux.org/man/greetd-ipc.7.en
"""

import os
import sys
import json
import struct
import socket
import tomllib
import shutil
import termios
import tty
import select
from pathlib import Path
import configparser

# ─── 配置 ──────────────────────────────────────────────

CONFIG_PATHS = [
    Path("/etc/my-greeter/config.toml"),
    Path.home() / ".config" / "my-greeter" / "config.toml",
    Path(__file__).parent / "config.toml",
]

DEFAULT_CONFIG = {
    "log": {"enable": False, "path": "/tmp/my-greeter.log"},
    "auth": {"default_user": "", "auto_login": False},
    "branding": {"title": "Welcome"},
}

SESSION_DIRS = [
    Path("/usr/share/wayland-sessions"),
    Path("/usr/share/xsessions"),
]


def load_config() -> dict:
    for path in CONFIG_PATHS:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    return DEFAULT_CONFIG


# ─── 日志系统 ──────────────────────────────────────────

_log_handle = None
_log_enabled = False


def init_log(config: dict):
    global _log_handle, _log_enabled
    cfg = config.get("log", {})
    if not cfg.get("enable", False):
        _log_enabled = False
        return
    path = Path(cfg.get("path", "/tmp/my-greeter.log"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _log_handle = open(path, "a", encoding="utf-8")
        _log_enabled = True
    except Exception:
        _log_enabled = False


def log(level: str, msg: str):
    if not _log_enabled or _log_handle is None:
        return
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        _log_handle.write(f"[{ts}] [{level}] {msg}\n")
        _log_handle.flush()
    except Exception:
        pass


# ─── 主题系统 ──────────────────────────────────────────

ANSI_COLORS = {
    "black": 30, "red": 31, "green": 32, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36, "white": 37,
    "bright_black": 90, "bright_red": 91, "bright_green": 92,
    "bright_yellow": 93, "bright_blue": 94, "bright_magenta": 95,
    "bright_cyan": 96, "bright_white": 97,
}

ANSI_ATTRS = {
    "bold": 1, "dim": 2, "italic": 3, "underline": 4,
    "blink": 5, "reverse": 7,
}

RESET = "\033[0m"


def parse_style(style_str: str) -> str:
    if not style_str or not style_str.strip():
        return ""
    parts = style_str.strip().lower().split()
    codes = []
    for p in parts:
        if p in ANSI_COLORS:
            codes.append(str(ANSI_COLORS[p]))
        elif p in ANSI_ATTRS:
            codes.append(str(ANSI_ATTRS[p]))
    if not codes:
        return ""
    return "\033[" + ";".join(codes) + "m"


def styled(text: str, style: str) -> str:
    ansi = parse_style(style)
    if not ansi:
        return text
    return ansi + text + RESET


DEFAULT_THEME = {
    "title": "cyan bold",
    "sep": "",
    "plugin": "green",
    "label": "yellow",
    "input": "white",
    "error": "red bold",
    "session": "white",
    "session_default": "cyan",
    "session_highlight": "cyan bold",
    "session_normal": "",
    "user_highlight": "cyan bold",
    "user_normal": "",
}


# ─── 自动检测桌面环境 ──────────────────────────────────

def scan_sessions() -> list[dict]:
    """自动扫描已安装的桌面环境"""
    sessions = []
    for dir_path in SESSION_DIRS:
        if not dir_path.is_dir():
            continue
        session_type = dir_path.name.replace("-sessions", "")
        for desktop_file in sorted(dir_path.glob("*.desktop")):
            try:
                parser = configparser.ConfigParser()
                parser.read(desktop_file)
                if "Desktop Entry" not in parser:
                    continue
                entry = parser["Desktop Entry"]
                name = entry.get("Name", desktop_file.stem)
                exec_cmd = entry.get("Exec", "")
                if not exec_cmd:
                    continue
                sessions.append({
                    "name": name,
                    "exec": exec_cmd,
                    "type": session_type,
                })
            except Exception:
                continue
    return sessions


# ─── 用户检测 ──────────────────────────────────────────

EXCLUDED_USERS = {"nobody", "nobody", "nfsnobody", "guest"}


def list_users(min_uid: int = 1000) -> list[str]:
    users = []
    try:
        for line in Path("/etc/passwd").read_text().splitlines():
            parts = line.split(":")
            if len(parts) < 7:
                continue
            name, _, uid_str, _, _, _, shell = parts
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            if uid < min_uid or name in EXCLUDED_USERS:
                continue
            if shell in ("/usr/bin/nologin", "/bin/false", "/sbin/nologin"):
                continue
            users.append(name)
    except Exception:
        pass
    return sorted(users)


# ─── 插件系统 ────────────────────────────────────────────

PLUGIN_DIRS = [
    Path.home() / ".config" / "my-greeter" / "plugins",
    Path(__file__).parent / "plugins",
]


def load_plugins() -> list[str]:
    from subprocess import run, TimeoutExpired, CalledProcessError
    plugin_lines = []
    seen = set()
    for dir_path in PLUGIN_DIRS:
        if not dir_path.is_dir():
            continue
        for f in sorted(dir_path.iterdir()):
            if f.name.startswith(".") or not os.access(f, os.X_OK):
                continue
            if f.name in seen:
                continue
            seen.add(f.name)
            try:
                r = run([f], capture_output=True, timeout=2, text=True)
                for line in r.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if "lines" in data:
                        plugin_lines.extend(data["lines"])
            except TimeoutExpired:
                log("WARN", f"plugin timed out: {f.name}")
                continue
            except (CalledProcessError, json.JSONDecodeError, OSError):
                log("WARN", f"plugin failed: {f.name}")
                continue
    return plugin_lines


# ─── 终端工具 ──────────────────────────────────────────

def center_print(text: str, width: int, style: str = ""):
    padding = max(0, (width - len(text)) // 2)
    print(" " * padding + styled(text, style))


def clear_screen():
    print("\033[2J\033[H", end="")


def move_to(row: int, col: int = 0):
    print(f"\033[{row};{col}H", end="")


def hide_cursor():
    print("\033[?25l", end="")


def show_cursor():
    print("\033[?25h", end="")


# ─── 键盘输入（方向键支持）─────────────────────────────

def _raw_getch(timeout: float | None = None) -> str | None:
    """
    读取一个字符（raw 模式）。
    timeout=None 阻塞等待；timeout 秒数则超时返回 None。
    """
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        if timeout is not None:
            r, _, _ = select.select([fd], [], [], timeout)
            if not r:
                return None
        ch = sys.stdin.read(1)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def get_key(timeout: float | None = None) -> str | None:
    """
    读取一个按键。
    timeout=None 阻塞等待；timeout 秒数则超时返回 None。
    返回: 'UP', 'DOWN', 'ENTER', 'q', 其他字符, 或 None(超时)
    """
    ch = _raw_getch(timeout)
    if ch is None:
        return None
    if ch == "\033":
        seq = _raw_getch(0.05)  # 短超时区分 ESC 和方向键
        if seq is None:
            return "ESC"
        seq2 = _raw_getch(0.05)
        if seq2 is None:
            return None
        combo = seq + seq2
        if combo == "[A":
            return "UP"
        elif combo == "[B":
            return "DOWN"
        elif combo == "[C":
            return "RIGHT"
        elif combo == "[D":
            return "LEFT"
        return None
    elif ch in ("\r", "\n"):
        return "ENTER"
    elif ch in ("\x03",):
        raise KeyboardInterrupt
    return ch


def select_user(users: list[str], theme: dict, columns: int, top: int) -> str | None:
    if not users:
        return None
    idx = 0
    hl = theme.get("user_highlight", "cyan bold")
    nm = theme.get("user_normal", "")
    lbl = theme.get("label", "yellow")

    hide_cursor()
    while True:
        save_line = top
        for i, u in enumerate(users):
            move_to(save_line + i + 1, 0)
            style = hl if i == idx else nm
            prefix = " ▸ " if i == idx else "   "
            center_print(f"{prefix}{u}", columns, style)
        move_to(save_line + len(users) + 1, 0)
        center_print("  [↑↓ 切换   Enter 确认]", columns, lbl)

        key = get_key()
        if key == "UP":
            idx = (idx - 1) % len(users)
        elif key == "DOWN":
            idx = (idx + 1) % len(users)
        elif key == "ENTER":
            show_cursor()
            return users[idx]
        elif key == "q":
            show_cursor()
            return None
    show_cursor()


def select_session_with_timeout(
    sessions: list[dict], theme: dict, columns: int, top_row: int, timeout_s: int = 3
) -> dict | None:
    """
    等待用户选择 session。显示提示后：
    - 按 ↑↓ 切换 → 进入完整选择模式
    - 按 Enter 或无操作 timeout_s 秒 → 返回第一个（默认）session
    - 返回 None 表示退出
    """
    if not sessions:
        return None

    default = sessions[0]
    default_name = default["name"]
    start_msg = f"  Starting {default_name}..."
    auto_msg = f"  (↑↓ choose session, auto-start in {timeout_s}s)"

    sh = theme.get("session_highlight", "cyan bold")
    sn = theme.get("session_normal", "")
    st = theme.get("session_default", "cyan")
    lbl = theme.get("label", "yellow")

    hide_cursor()

    # 先显示默认启动提示
    move_to(top_row, 0)
    center_print(start_msg, columns, st)
    move_to(top_row + 1, 0)
    center_print(auto_msg, columns, lbl)

    # 等用户按键（带超时）
    key = get_key(timeout_s)

    if key is None:
        # 超时，启动默认
        show_cursor()
        return default

    if key == "ENTER":
        show_cursor()
        return default

    if key == "q":
        show_cursor()
        return None

    # UP 或 DOWN → 进入完整选择模式
    idx = 0
    showing = True

    while True:
        if showing:
            # 渲染 session 列表
            help_line = "  [↑↓ 切换   Enter 确认]"
            for i, s in enumerate(sessions):
                line = top_row + i + 1
                move_to(line, 0)
                style = sh if i == idx else sn
                prefix = " ▸ " if i == idx else "   "
                center_print(f"{prefix}{s['name']}", columns, style)
            move_to(top_row + len(sessions) + 1, 0)
            center_print(help_line, columns, lbl)

        if key == "UP":
            idx = (idx - 1) % len(sessions)
            showing = True
        elif key == "DOWN":
            idx = (idx + 1) % len(sessions)
            showing = True
        elif key == "ENTER":
            show_cursor()
            return sessions[idx]
        elif key == "q":
            show_cursor()
            return None
        else:
            showing = False

        key = get_key()


# ─── greetd IPC 协议 ───────────────────────────────────

class GreetdClient:
    def __init__(self):
        sock_path = os.environ.get("GREETD_SOCK")
        if not sock_path:
            log("ERROR", "GREETD_SOCK not set")
            print("ERROR: GREETD_SOCK not set", file=sys.stderr)
            sys.exit(1)
        log("DEBUG", f"connecting to GREETD_SOCK={sock_path}")
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(sock_path)

    def _send(self, obj: dict):
        payload = json.dumps(obj).encode("utf-8")
        header = struct.pack("I", len(payload))
        self.sock.sendall(header + payload)

    def _recv(self) -> dict:
        raw_len = self.sock.recv(4)
        if not raw_len:
            return {"type": "error", "error_type": "error",
                    "description": "connection closed"}
        length = struct.unpack("I", raw_len)[0]
        data = b""
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return json.loads(data.decode("utf-8"))

    def create_session(self, username: str) -> dict:
        self._send({"type": "create_session", "username": username})
        return self._recv()

    def post_auth_response(self, response: str = None):
        msg = {"type": "post_auth_message_response"}
        if response is not None:
            msg["response"] = response
        self._send(msg)
        return self._recv()

    def start_session(self, cmd: list[str], env: list[str] = None):
        self._send({"type": "start_session", "cmd": cmd, "env": env or []})
        return self._recv()

    def cancel_session(self):
        self._send({"type": "cancel_session"})

    def close(self):
        self.sock.close()


# ─── TUI ──────────────────────────────────────────────

def tui_login(config: dict):
    columns, lines = shutil.get_terminal_size()
    auth_cfg = config.get("auth", {})
    brand = config.get("branding", {})
    theme = {**DEFAULT_THEME, **(config.get("theme") or {})}

    plugin_lines = load_plugins()
    log("INFO", f"loaded {len(plugin_lines)} plugin lines")

    title = f"  {brand.get('title', 'Welcome')}"
    sep = f"  {'─' * len(title)}"

    # ---- 用户选择 ----
    default_user = auth_cfg.get("default_user", "")
    auto_login = auth_cfg.get("auto_login", False)
    available_users = list_users()

    if auto_login and default_user:
        username = default_user
    elif len(available_users) == 1:
        username = available_users[0]
    else:
        username = ""

    need_user_select = len(available_users) >= 2 and not auto_login

    if need_user_select:
        ui_height = 3 + 2 + (1 if plugin_lines else 0) + len(plugin_lines) + len(available_users) + 2
    else:
        ui_height = 3 + 2 + (1 if plugin_lines else 0) + len(plugin_lines)

    top_padding = max(0, (lines - ui_height) // 2)

    clear_screen()
    print("\n" * top_padding, end="")

    center_print(title, columns, theme["title"])
    center_print(sep, columns, theme["sep"])
    if plugin_lines:
        print()
        for line in plugin_lines:
            center_print(f"  {line}", columns, theme["plugin"])
    print()

    # ---- 用户列表（方向键选择）----
    if need_user_select:
        current_top = top_padding + 3 + (1 if plugin_lines else 0) + len(plugin_lines)
        username = select_user(available_users, theme, columns, current_top)
        if username is None:
            return
        for i in range(len(available_users) + 2):
            move_to(current_top + i + 1, 0)
            print(" " * columns)

    # ---- 显示用户 ----
    label = styled("  User:", theme["label"])
    value = styled(f" {username}", theme["input"])
    text = label + value
    offset = max(0, (columns - len("  User: ") - len(username)) // 2)
    print(" " * offset + text)

    if not username:
        log("WARN", "no user selected, exiting")
        return

    log("INFO", f"login attempt: user={username}")

    # ---- 连接 greetd 并认证 ----
    client = GreetdClient()
    resp = client.create_session(username)

    while resp["type"] != "success":
        if resp["type"] == "auth_message":
            msg_type = resp.get("auth_message_type", "visible")
            msg_text = resp.get("auth_message", "")
            padded_msg = f"  {msg_text}"
            styled_msg = styled(padded_msg, theme["label"])
            offset = max(0, (columns - len(padded_msg)) // 2)
            if msg_type == "secret":
                from getpass import getpass
                sys.stdout.write(" " * offset + styled_msg)
                sys.stdout.flush()
                answer = getpass("")
            elif msg_type in ("info", "error"):
                stl = theme["error"] if msg_type == "error" else theme["label"]
                center_print(f"  [{msg_type}] {msg_text}", columns, stl)
                resp = client.post_auth_response()
                continue
            else:
                answer = input(" " * offset + styled_msg)
            resp = client.post_auth_response(answer)
        elif resp["type"] == "error":
            desc = resp.get("description", "unknown")
            log("WARN", f"auth error: {desc}")
            center_print(f"  Error: {desc}", columns, theme["error"])
            client.close()
            return

    log("INFO", f"auth success: user={username}")

    # ---- session 选择（带超时，默认自动启动）----
    session_list = scan_sessions()
    if not session_list:
        center_print("  No sessions available", columns, theme["error"])
        client.close()
        return

    current_top = top_padding + 3 + (1 if plugin_lines else 0) + len(plugin_lines) + 2
    selected = select_session_with_timeout(session_list, theme, columns, current_top, timeout_s=3)

    if selected is None:
        center_print("  Cancelled", columns, theme["error"])
        client.close()
        return

    # 清除 session 选择提示
    for i in range(len(session_list) + 3):
        move_to(current_top + i, 0)
        print(" " * columns)

    cmd = selected["exec"]
    log("INFO", f"starting session: {cmd} for user={username}")
    center_print(f"  Starting {selected['name']}...", columns, theme["session_default"])

    resp = client.start_session([cmd])
    if resp["type"] == "success":
        log("INFO", "session started, greeter exiting")
        client.close()
        os._exit(0)
    else:
        desc = resp.get("description", "start failed")
        log("ERROR", f"start session failed: {desc}")
        center_print(f"  Error: {desc}", columns, theme["error"])
        client.close()


# ─── 入口 ──────────────────────────────────────────────

def main():
    config = load_config()
    init_log(config)
    log("INFO", "greeter started")
    try:
        tui_login(config)
    except KeyboardInterrupt:
        log("INFO", "user cancelled (Ctrl+C)")
        print()
        sys.exit(0)
    except Exception as e:
        log("ERROR", f"unhandled exception: {e}")
        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
