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
from pathlib import Path
import configparser

# ─── 配置 ──────────────────────────────────────────────

CONFIG_PATHS = [
    Path("/etc/my-greeter/config.toml"),
    Path.home() / ".config" / "my-greeter" / "config.toml",
    Path(__file__).parent / "config.toml",
]

DEFAULT_CONFIG = {
    "log": {
        "enable": False,
        "path": "/tmp/my-greeter.log",
    },
    "ui": {
        "theme": "dark",
    },
    "sessions": {
        "default": "",
        "extra": [],
    },
    "auth": {
        "default_user": "",
        "auto_login": False,
    },
    "branding": {
        "title": "Welcome",
    },
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
    "select": "yellow",
    "user_highlight": "cyan bold",
    "user_normal": "",
}


# ─── 自动检测桌面环境 ──────────────────────────────────

def scan_sessions() -> list[dict]:
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
                    "file": desktop_file.name,
                })
            except Exception:
                continue
    return sessions


def merge_sessions(config_sessions: dict) -> list[dict]:
    scanned = scan_sessions()
    extra = config_sessions.get("extra", [])
    default_exec = config_sessions.get("default", "")
    seen = set()
    merged = []
    for s in scanned:
        key = s["exec"]
        if key not in seen:
            seen.add(key)
            merged.append(s)
    for item in extra:
        if isinstance(item, str):
            cmd, name = item, item
        elif isinstance(item, dict):
            cmd = item.get("exec", "")
            name = item.get("name", cmd)
        else:
            continue
        if cmd and cmd not in seen:
            seen.add(cmd)
            merged.append({"name": name, "exec": cmd, "type": "user"})
    if default_exec:
        for s in merged:
            s["default"] = s["exec"] == default_exec
    elif merged:
        merged[0]["default"] = True
    return merged


# ─── 用户检测 ──────────────────────────────────────────

EXCLUDED_USERS = {"nobody", "nobody", "nfsnobody", "guest"}


def list_users(min_uid: int = 1000) -> list[str]:
    """读取 /etc/passwd，返回真实可登录的用户列表"""
    users = []
    try:
        for line in Path("/etc/passwd").read_text().splitlines():
            parts = line.split(":")
            if len(parts) < 7:
                continue
            name, _, uid_str, _, _, _, shell = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            # 系统用户（UID < min_uid）或排除名单里的跳过
            if uid < min_uid or name in EXCLUDED_USERS:
                continue
            # 没有登录 shell 的也跳过
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
    """将光标移动到指定行列（用于局部刷新）"""
    print(f"\033[{row};{col}H", end="")


def save_cursor():
    print("\033[s", end="")


def restore_cursor():
    print("\033[u", end="")


# ─── 键盘输入（方向键支持）─────────────────────────────

def get_key() -> str:
    """
    读取一个按键。返回：
      'UP', 'DOWN', 'ENTER', 'q', 或其他字符
    """
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\033":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "UP"
            elif seq == "[B":
                return "DOWN"
            elif seq == "[C":
                return "RIGHT"
            elif seq == "[D":
                return "LEFT"
            return None
        elif ch in ("\r", "\n"):
            return "ENTER"
        elif ch in ("\x03",):
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_user(users: list[str], theme: dict, columns: int, top: int) -> str | None:
    """
    方向键选择用户。返回选中的用户名，或 None（退出）。
    只有 >= 2 个用户时才会调用。
    """
    if not users:
        return None
    idx = 0
    hl = theme.get("user_highlight", "cyan bold")
    nm = theme.get("user_normal", "")
    lbl = theme.get("label", "yellow")

    while True:
        save_cursor()
        # 在指定位置渲染用户列表
        for i, u in enumerate(users):
            line = top + i + 1
            move_to(line, 0)
            style = hl if i == idx else nm
            prefix = " ▸ " if i == idx else "   "
            center_print(f"{prefix}{u}", columns, style)
        move_to(top + len(users) + 1, 0)
        center_print("  [↑↓ 切换   Enter 确认]", columns, lbl)

        key = get_key()
        if key == "UP":
            idx = (idx - 1) % len(users)
        elif key == "DOWN":
            idx = (idx + 1) % len(users)
        elif key == "ENTER":
            return users[idx]
        elif key == "q":
            return None


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


# ─── TUI（居中 + 主题 + 方向键切换）────────────────────

def tui_login(config: dict):
    columns, lines = shutil.get_terminal_size()
    auth_cfg = config["auth"]
    sessions = config["sessions"]
    brand = config["branding"]
    theme = {**DEFAULT_THEME, **(config.get("theme") or {})}

    plugin_lines = load_plugins()
    log("INFO", f"loaded {len(plugin_lines)} plugin lines")

    title = f"  {brand['title']}"
    sep = f"  {'─' * len(brand['title'])}"

    # ---- 用户选择 ----
    default_user = auth_cfg.get("default_user", "")
    auto_login = auth_cfg.get("auto_login", False)
    available_users = list_users()

    if auto_login and default_user:
        username = default_user
    elif len(available_users) == 1:
        username = available_users[0]
    elif default_user and default_user in available_users:
        # 直接预选中，但还是显示选择界面
        username = default_user
    else:
        username = ""

    # 如果有多个用户，显示方向键选择界面
    need_user_select = len(available_users) >= 2 and not auto_login

    if need_user_select:
        # 重新计算布局：加上用户列表
        ui_height = 3 + 2 + (1 if plugin_lines else 0) + len(plugin_lines) + len(available_users) + 2
    else:
        ui_height = 3 + 2 + (1 if plugin_lines else 0) + len(plugin_lines)

    top_padding = max(0, (lines - ui_height) // 2)

    clear_screen()
    print("\n" * top_padding, end="")

    # ---- 标题 ----
    center_print(title, columns, theme["title"])
    center_print(sep, columns, theme["sep"])
    if plugin_lines:
        print()
        for line in plugin_lines:
            center_print(f"  {line}", columns, theme["plugin"])
    print()

    # ---- 用户列表（方向键）----
    if need_user_select:
        current_top = top_padding + 3 + (1 if plugin_lines else 0) + len(plugin_lines)
        username = select_user(available_users, theme, columns, current_top)
        if username is None:
            return
        # 选中后清除用户列表
        for i in range(len(available_users) + 2):
            move_to(current_top + i + 1, 0)
            print(" " * columns)

    # ---- 显示选中的用户 ----
    label = styled(f"  User:", theme["label"])
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

    # ---- 自动选择 session（不再提示）----
    session_list = merge_sessions(sessions)
    if not session_list:
        center_print("  No sessions available", columns, theme["error"])
        client.close()
        return

    # 找默认 session
    selected = None
    for s in session_list:
        if s.get("default"):
            selected = s
            break
    if not selected:
        selected = session_list[0]

    cmd = selected["exec"]
    log("INFO", f"starting session: {cmd} for user={username}")

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
