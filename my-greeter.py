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
from pathlib import Path

# ─── 配置 ──────────────────────────────────────────────

CONFIG_PATHS = [
    Path("/etc/my-greeter/config.toml"),
    Path.home() / ".config" / "my-greeter" / "config.toml",
    Path(__file__).parent / "config.toml",
]

DEFAULT_CONFIG = {
    "ui": {
        "theme": "dark",
        "show_clock": True,
        "time_format": "%H:%M:%S",
    },
    "sessions": {
        "default": "niri-session",
        "list": ["niri-session", "sway", "Hyprland", "bash"],
    },
    "branding": {
        "title": "Welcome",
        "greeting": "Enter password for %s",
    },
}


def load_config() -> dict:
    for path in CONFIG_PATHS:
        if path.exists():
            with open(path, "rb") as f:
                return tomllib.load(f)
    return DEFAULT_CONFIG


# ─── greetd IPC 协议 ───────────────────────────────────

class GreetdClient:
    """通过 Unix socket 跟 greetd 通信"""

    def __init__(self):
        sock_path = os.environ.get("GREETD_SOCK")
        if not sock_path:
            print("ERROR: GREETD_SOCK 环境变量未设置", file=sys.stderr)
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
                    "description": "连接已关闭"}
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


# ─── 简陋 TUI（文本登录界面）────────────────────────────

def tui_login(config: dict):
    """
    简单的终端登录流程。
    后续可以换成 textual / prompt_toolkit / urwid 等 TUI 框架。
    """
    cfg = config["ui"]
    sessions = config["sessions"]
    brand = config["branding"]

    print(f"\n  {brand['title']}")
    print(f"  {'─' * len(brand['title'])}\n")

    # 用户名
    username = input("  Username: ").strip()
    if not username:
        return

    # 连接 greetd
    client = GreetdClient()

    # create_session 已经消费了第一个响应，用它进入认证循环
    resp = client.create_session(username)

    # PAM 认证循环
    while resp["type"] != "success":
        if resp["type"] == "auth_message":
            msg_type = resp.get("auth_message_type", "visible")
            msg_text = resp.get("auth_message", "")
            if msg_type == "secret":
                from getpass import getpass
                answer = getpass(f"  {msg_text}")
            elif msg_type in ("info", "error"):
                print(f"  [{msg_type}] {msg_text}")
                # 纯信息消息，无需 response 字段
                resp = client.post_auth_response()
                continue
            else:
                answer = input(f"  {msg_text}")
            resp = client.post_auth_response(answer)
        elif resp["type"] == "error":
            print(f"  ERROR: {resp.get('description', 'unknown')}")
            client.close()
            return

    # 选择 session
    print("\n  Sessions:")
    session_list = sessions["list"]
    for i, sess in enumerate(session_list, 1):
        print(f"    {i}. {sess}")
    try:
        choice = input(f"  Select [1/{len(session_list)}] (default=1): ").strip()
        idx = int(choice) - 1 if choice else 0
        selected = session_list[idx]
    except (ValueError, IndexError):
        selected = sessions["default"]

    # 启动 session
    resp = client.start_session([selected])
    if resp["type"] == "success":
        client.close()
        # 正常退出，greetd 接管启动 session
        os._exit(0)
    else:
        print(f"  ERROR: {resp.get('description', '启动失败')}")
        client.close()


# ─── 入口 ──────────────────────────────────────────────

def main():
    config = load_config()
    try:
        tui_login(config)
    except KeyboardInterrupt:
        print("\n  Bye.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
