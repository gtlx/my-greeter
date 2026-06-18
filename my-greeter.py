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


# ─── 键盘输入 ──────────────────────────────────────────

def get_key(timeout: float | None = None) -> str | None:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        def _read(t=None):
            if t is not None:
                r, _, _ = select.select([fd], [], [], t)
                if not r:
                    return None
            return sys.stdin.read(1)
        ch = _read(timeout)
        if ch is None:
            return None
        if ch == "\033":
            s1 = _read(0.05)
            if s1 is None:
                return "ESC"
            s2 = _read(0.05)
            if s2 is None:
                return None
            c = s1 + s2
            if c == "[A": return "UP"
            if c == "[B": return "DOWN"
            if c == "[C": return "RIGHT"
            if c == "[D": return "LEFT"
            return None
        elif ch in ("\r", "\n"):
            return "ENTER"
        elif ch in ("\x03",):
            raise KeyboardInterrupt
        elif ch in ("\x7f", "\b"):
            return "BACKSPACE"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_password(prompt: str, columns: int, theme: dict) -> str:
    """读取密码，每输入一个字符显示一个 *"""
    buf = ""
    label_style = theme.get("label", "yellow")
    styled_prompt = styled(prompt, label_style)
    offset = max(0, (columns - len(prompt)) // 2)

    # 显示提示
    sys.stdout.write(" " * offset + styled_prompt)
    sys.stdout.flush()

    while True:
        key = get_key()
        if key == "ENTER":
            print()
            return buf
        elif key == "BACKSPACE":
            if buf:
                buf = buf[:-1]
                # 退格：光标左移，清字符，再左移
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif key and len(key) == 1 and key.isprintable():
            buf += key
            sys.stdout.write("*")
            sys.stdout.flush()
        elif key == "q":
            # 允许取消
            return ""


def select_user(users: list[str], theme: dict, columns: int, top: int) -> str | None:
    if not users:
        return None
    idx = 0
    hl = theme.get("user_highlight", "cyan bold")
    nm = theme.get("user_normal", "")
    lbl = theme.get("label", "yellow")

    hide_cursor()
    while True:
        for i, u in enumerate(users):
            move_to(top + i + 1, 0)
            style = hl if i == idx else nm
            prefix = " ▸ " if i == idx else "   "
            center_print(f"{prefix}{u}", columns, style)
        move_to(top + len(users) + 1, 0)
        center_print("  [↑↓ 切换   Enter 确认]", columns, lbl)

        key = get_key()
        if key == "UP": idx = (idx - 1) % len(users)
        elif key == "DOWN": idx = (idx + 1) % len(users)
        elif key == "ENTER":
            show_cursor()
            return users[idx]
        elif key == "q":
            show_cursor()
            return None
    show_cursor()


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

def tui_login(config: dict, preview: bool = False):
    columns, lines = shutil.get_terminal_size()
    auth_cfg = config.get("auth", {})
    brand = config.get("branding", {})
    theme = {**DEFAULT_THEME, **(config.get("theme") or {})}

    plugin_lines = load_plugins()
    log("INFO", f"loaded {len(plugin_lines)} plugin lines")

    title = f"  {brand.get('title', 'Welcome')}"
    sep = f"  {'─' * len(title)}"

    ui_height = 3 + 2 + (1 if plugin_lines else 0) + len(plugin_lines) + 4
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

    session_line = top_padding + 3 + (1 if plugin_lines else 0) + len(plugin_lines) + 1
    user_line = session_line + 1
    pwd_line = user_line + 1

    # ---- session 选择 ----
    session_list = scan_sessions()
    if not session_list:
        log("ERROR", "no sessions found")
        center_print("  No sessions available", columns, theme["error"])
        return

    sess_idx = 0
    # 从配置预填用户名
    default_user = auth_cfg.get("default_user", "")
    username = default_user if not auth_cfg.get("auto_login") else default_user
    password = ""
    field = "user" if not default_user else "password"  # 有默认用户则直接跳到密码
    # 如果 auto_login 并且有默认用户，也先停在密码

    def render_all():
        # Session 行
        s = session_list[sess_idx]
        text = f"  Session: {s['name']}  [\u2190 \u2192]"
        move_to(session_line, 0)
        print(" " * columns, end="")
        move_to(session_line, 0)
        center_print(text, columns, theme["session_default"] if sess_idx == 0 else theme["session_highlight"])

        # User 行
        user_text = f"  User: {username}"
        cursor = "" if field != "user" else "\u258c"
        move_to(user_line, 0)
        print(" " * columns, end="")
        move_to(user_line, 0)
        center_print(user_text + cursor, columns, theme["label"] if not username else theme["input"])

        # Password 行
        stars = "*" * len(password)
        pwd_text = f"  Password: {stars}"
        cursor = "" if field != "password" else "\u258c"
        move_to(pwd_line, 0)
        print(" " * columns, end="")
        move_to(pwd_line, 0)
        center_print(pwd_text + cursor, columns, theme["label"] if not password else theme["input"])

    render_all()

    while True:
        key = get_key()

        if key == "RIGHT":
            sess_idx = (sess_idx + 1) % len(session_list)
            render_all()
        elif key == "LEFT":
            sess_idx = (sess_idx - 1) % len(session_list)
            render_all()
        elif key == "ENTER":
            if field == "user":
                if username:
                    field = "password"
                    render_all()
                # 没输用户名就继续等
            elif field == "password":
                if password:
                    break  # 提交
        elif key == "TAB":
            field = "password" if field == "user" else "user"
            render_all()
        elif key == "BACKSPACE":
            if field == "user" and username:
                username = username[:-1]
                render_all()
            elif field == "password" and password:
                password = password[:-1]
                render_all()
        elif key == "q":
            return
        elif key and len(key) == 1 and key.isprintable():
            if field == "user":
                username += key
                render_all()
            elif field == "password":
                password += key
                render_all()

    if not username or not password:
        log("WARN", "empty user or password")
        return

    log("INFO", f"login attempt: user={username}")

    # 清除 Session 箭头提示
    move_to(session_line, 0)
    print(" " * columns, end="")
    move_to(session_line, 0)
    center_print(f"  Session: {session_list[sess_idx]['name']}", columns, theme["session_default"] if sess_idx == 0 else theme["session_highlight"])

    if preview:
        print()
        center_print("  [Preview] Auth success!", columns, theme["session_default"])
        center_print(f"  [Preview] Starting session: {session_list[sess_idx]['name']}", columns, theme["plugin"])
        center_print("  Press any key to exit preview", columns, theme["label"])
        get_key()
        return

    # ---- 连接 greetd 并认证 ----
    client = GreetdClient()
    resp = client.create_session(username)

    while resp["type"] != "success":
        if resp["type"] == "auth_message":
            msg_type = resp.get("auth_message_type", "visible")
            msg_text = resp.get("auth_message", "")
            if msg_type == "secret":
                resp = client.post_auth_response(password)
            elif msg_type in ("info", "error"):
                stl = theme["error"] if msg_type == "error" else theme["label"]
                center_print(f"  [{msg_type}] {msg_text}", columns, stl)
                resp = client.post_auth_response()
                continue
            else:
                styled_msg = styled(f"  {msg_text}", theme["label"])
                offset = max(0, (columns - len(f"  {msg_text}")) // 2)
                answer = input(" " * offset + styled_msg)
                resp = client.post_auth_response(answer)
        elif resp["type"] == "error":
            desc = resp.get("description", "unknown")
            log("WARN", f"auth error: {desc}")
            center_print(f"  Error: {desc}", columns, theme["error"])
            client.close()
            return

    log("INFO", f"auth success: user={username}")

    # 清除 session 选择提示行
    move_to(session_line, 0)
    print(" " * columns, end="")
    move_to(session_line, 0)

    # 启动选中的 session
    selected = session_list[sess_idx]
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
    preview = "--preview" in sys.argv
    config = load_config()
    init_log(config)
    if preview:
        log("INFO", "preview mode")
    else:
        log("INFO", "greeter started")
    try:
        tui_login(config, preview=preview)
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
