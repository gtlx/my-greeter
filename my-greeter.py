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
            except (TimeoutExpired, CalledProcessError, json.JSONDecodeError, OSError):
                continue  # 插件出错就跳过，不阻塞
    return plugin_lines


# ─── 终端居中工具 ──────────────────────────────────────

def center_print(text: str, width: int):
    """居中打印一行文本"""
    padding = max(0, (width - len(text)) // 2)
    print(" " * padding + text)


def clear_screen():
    """清屏"""
    print("\033[2J\033[H", end="")


# ─── greetd IPC 协议 ───────────────────────────────────

class GreetdClient:
    """通过 Unix socket 跟 greetd 通信"""

    def __init__(self):
        sock_path = os.environ.get("GREETD_SOCK")
        if not sock_path:
            print("ERROR: GREETD_SOCK not set", file=sys.stderr)
            sys.exit(1)
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


# ─── TUI（居中登录界面）────────────────────────────────

def tui_login(config: dict):
    columns, lines = shutil.get_terminal_size()
    auth_cfg = config["auth"]
    sessions = config["sessions"]
    brand = config["branding"]

    # 加载插件
    plugin_lines = load_plugins()

    # 标题行
    title = f"  {brand['title']}"
    sep = f"  {'─' * len(brand['title'])}"

    # 计算界面总行数
    # +2: 标题上下各一个空行
    ui_height = 2 + 2 + 1 + (1 if plugin_lines else 0) + len(plugin_lines)
    # +1: 输入行
    ui_height += 1
    top_padding = max(0, (lines - ui_height) // 2)

    clear_screen()

    # 垂直居中
    print("\n" * top_padding, end="")

    # 水平居中
    center_print(title, columns)
    center_print(sep, columns)

    # 插件输出行
    if plugin_lines:
        print()
        for line in plugin_lines:
            center_print(f"  {line}", columns)

    print()

    # 用户名
    default_user = auth_cfg.get("default_user", "")
    if auth_cfg.get("auto_login") and default_user:
        username = default_user
        print(f"{' ' * ((columns - len(f'  User: {username}')) // 2)}  User: {username}")
    else:
        prompt = f"  User{f' [{default_user}]' if default_user else ''}: "
        # 将光标移到居中位置再输入
        offset = (columns - len(prompt)) // 2
        sys.stdout.write(" " * offset + prompt)
        sys.stdout.flush()
        raw = input().strip()
        username = raw if raw else default_user

    if not username:
        return

    # 连接 greetd
    client = GreetdClient()

    # create_session 已消费第一个响应，直接进入认证循环
    resp = client.create_session(username)

    while resp["type"] != "success":
        if resp["type"] == "auth_message":
            msg_type = resp.get("auth_message_type", "visible")
            msg_text = resp.get("auth_message", "")
            prompt_centered = " " * ((columns - len(f"  {msg_text}")) // 2)
            if msg_type == "secret":
                from getpass import getpass
                sys.stdout.write(prompt_centered + f"  {msg_text}")
                sys.stdout.flush()
                answer = getpass("")
            elif msg_type in ("info", "error"):
                center_print(f"  [{msg_type}] {msg_text}", columns)
                resp = client.post_auth_response()
                continue
            else:
                answer = input(prompt_centered + f"  {msg_text}")
            resp = client.post_auth_response(answer)
        elif resp["type"] == "error":
            center_print(f"  Error: {resp.get('description', 'unknown')}", columns)
            client.close()
            return

    # 选择 session
    session_list = merge_sessions(sessions)

    if not session_list:
        center_print("  No sessions available", columns)
        client.close()
        return

    default_idx = 0
    for i, s in enumerate(session_list):
        if s.get("default"):
            default_idx = i
            break

    print()
    center_print("Sessions:", columns)
    for i, s in enumerate(session_list, 1):
        marker = " <" if s.get("default") else ""
        tag = f" [{s.get('type', '?')}]"
        text = f"  {i}. {s['name']}{tag}{marker}"
        center_print(text, columns)

    prompt = f"  Select [1-{len(session_list)}] ({default_idx + 1}): "
    offset = (columns - len(prompt)) // 2
    sys.stdout.write(" " * offset + prompt)
    sys.stdout.flush()
    raw = input().strip()
    try:
        idx = int(raw) - 1 if raw else default_idx
        selected = session_list[idx]
    except (ValueError, IndexError):
        selected = session_list[default_idx]

    # 启动 session
    resp = client.start_session([selected["exec"]])
    if resp["type"] == "success":
        client.close()
        os._exit(0)
    else:
        center_print(f"  Error: {resp.get('description', 'start failed')}", columns)
        client.close()


# ─── 入口 ──────────────────────────────────────────────

def main():
    config = load_config()
    try:
        tui_login(config)
    except KeyboardInterrupt:
        print()
        sys.exit(0)
    except Exception as e:
        print(f"\n  Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
