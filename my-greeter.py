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
        "enable": False,      # 是否写日志文件
        "path": "/tmp/my-greeter.log",  # 日志文件路径
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
    """初始化日志（在主流程开始时调用一次）"""
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
    """写入日志行。level: INFO / WARN / ERROR / DEBUG"""
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
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
    "bright_black": 90,
    "bright_red": 91,
    "bright_green": 92,
    "bright_yellow": 93,
    "bright_blue": 94,
    "bright_magenta": 95,
    "bright_cyan": 96,
    "bright_white": 97,
}

ANSI_ATTRS = {
    "bold": 1,
    "dim": 2,
    "italic": 3,
    "underline": 4,
    "blink": 5,
    "reverse": 7,
}

RESET = "\033[0m"


def parse_style(style_str: str) -> str:
    """
    解析样式字符串，返回 ANSI 转义码。
    例如: "cyan bold" → "\033[36;1m"
          "red"       → "\033[31m"
          ""          → ""（空白/不配置就无色）
    """
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
    """给文本套上样式，如果 style 为空就原样返回"""
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
}


# ─── 自动检测桌面环境 ──────────────────────────────────

def scan_sessions() -> list[dict]:
    """扫描系统安装的桌面环境，返回 [{name, exec, type}, ...]"""
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
    """合并系统检测 + 用户配置的 session 列表"""
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
            cmd = item
            name = item
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


# ─── 插件系统 ────────────────────────────────────────────

PLUGIN_DIRS = [
    Path.home() / ".config" / "my-greeter" / "plugins",
    Path(__file__).parent / "plugins",
]


def load_plugins() -> list[str]:
    """
    扫描插件目录，运行每个可执行文件，收集输出行。
    插件协议：每行一个 JSON {"name":"...", "lines":["...","..."]}
    """
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
    """居中打印一行文本（可选 ANSI 样式）"""
    padding = max(0, (width - len(text)) // 2)
    print(" " * padding + styled(text, style))


def clear_screen():
    """清屏"""
    print("\033[2J\033[H", end="")


# ─── greetd IPC 协议 ───────────────────────────────────

class GreetdClient:
    """通过 Unix socket 跟 greetd 通信"""

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
        self._send({
            "type": "start_session",
            "cmd": cmd,
            "env": env or [],
        })
        return self._recv()

    def cancel_session(self):
        self._send({"type": "cancel_session"})

    def close(self):
        self.sock.close()


# ─── TUI（居中 + 主题登录界面）─────────────────────────

def tui_login(config: dict):
    columns, lines = shutil.get_terminal_size()
    auth_cfg = config["auth"]
    sessions = config["sessions"]
    brand = config["branding"]
    theme = {**DEFAULT_THEME, **(config.get("theme") or {})}

    # 加载插件
    plugin_lines = load_plugins()
    log("INFO", f"loaded {len(plugin_lines)} plugin lines")

    title = f"  {brand['title']}"
    sep = f"  {'─' * len(brand['title'])}"

    # 计算界面总行数
    ui_height = 2 + 2 + 1 + (1 if plugin_lines else 0) + len(plugin_lines) + 1
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

    # 用户名
    default_user = auth_cfg.get("default_user", "")
    if auth_cfg.get("auto_login") and default_user:
        username = default_user
        label = styled("  User:", theme["label"])
        value = styled(f" {username}", theme["input"])
        text = label + value
        offset = max(0, (columns - len("  User: ") - len(username)) // 2)
        print(" " * offset + text)
    else:
        prompt_text = f"  User{f' [{default_user}]' if default_user else ''}: "
        styled_prompt = styled(prompt_text, theme["label"])
        offset = max(0, (columns - len(prompt_text)) // 2)
        sys.stdout.write(" " * offset + styled_prompt)
        sys.stdout.flush()
        raw = input().strip()
        username = raw if raw else default_user

    if not username:
        log("WARN", "empty username, exiting")
        return

    log("INFO", f"login attempt: user={username}")

    # 连接 greetd
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
            desc = resp.get('description', 'unknown')
            log("WARN", f"auth error: {desc}")
            center_print(f"  Error: {desc}", columns, theme["error"])
            client.close()
            return

    log("INFO", f"auth success: user={username}")

    # 选择 session
    session_list = merge_sessions(sessions)
    if not session_list:
        center_print("  No sessions available", columns, theme["error"])
        client.close()
        return

    default_idx = 0
    for i, s in enumerate(session_list):
        if s.get("default"):
            default_idx = i
            break

    print()
    center_print("Sessions:", columns, theme["label"])
    for i, s in enumerate(session_list, 1):
        marker = " <" if s.get("default") else ""
        tag = f" [{s.get('type', '?')}]"
        text = f"  {i}. {s['name']}{tag}{marker}"
        stl = theme["session_default"] if s.get("default") else theme["session"]
        center_print(text, columns, stl)

    prompt_text = f"  Select [1-{len(session_list)}] ({default_idx + 1}): "
    styled_prompt = styled(prompt_text, theme["select"])
    offset = max(0, (columns - len(prompt_text)) // 2)
    sys.stdout.write(" " * offset + styled_prompt)
    sys.stdout.flush()
    raw = input().strip()
    try:
        idx = int(raw) - 1 if raw else default_idx
        selected = session_list[idx]
    except (ValueError, IndexError):
        selected = session_list[default_idx]

    cmd = selected["exec"]
    log("INFO", f"starting session: {cmd} for user={username}")

    resp = client.start_session([cmd])
    if resp["type"] == "success":
        log("INFO", f"session started, greeter exiting")
        client.close()
        os._exit(0)
    else:
        desc = resp.get('description', 'start failed')
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
