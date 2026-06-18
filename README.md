# my-greeter

自写的 greetd greeter（前端）。

## 结构

```
my-greeter.py       ← 主程序
config.toml         ← 配置文件
plugins/
├── clock.py        ← 示例插件：时钟
└── sysinfo.py      ← 示例插件：系统信息
```

## 快速开始

### 1. 安装 greetd 并配置

```bash
sudo pacman -S greetd
sudo setfacl -m u:greeter:x /home/gtlx
```

编辑 `/etc/greetd/config.toml`：

```toml
[terminal]
vt = 1

[default_session]
command = "/home/gtlx/软件/my-greeter/my-greeter.py"
user = "greeter"
```

### 2. 启用

```bash
sudo systemctl disable --now lemurs
sudo systemctl enable --now greetd
```

按 `Ctrl+Alt+F1` 测试。

## 配置

编辑 `config.toml`：

```toml
[auth]
default_user = "gtlx"       # 默认用户名
auto_login = false           # true 跳过用户名输入，直接输密码

[sessions]
default = "niri-session"     # 默认 session
extra = ["bash"]             # 额外 session（系统自动扫描 .desktop）

[branding]
title = "gtlx's machine"    # 标题
```

## 插件

插件是可执行文件，放在以下目录：

| 目录 | 说明 |
|------|------|
| `~/.config/my-greeter/plugins/` | 用户插件（推荐） |
| 脚本同目录的 `plugins/` | 项目自带插件 |

插件**启动时执行一次**，将自己的输出行通过 JSON 格式打印到 stdout：

```json
{"name":"clock","lines":["14:30:00"]}
```

可以**用任何语言写**——shell、Python、Rust、Go 都行。

### 示例：shell 插件（~/.config/my-greeter/plugins/clock.sh）

```bash
#!/bin/bash
echo "{\"name\":\"clock\",\"lines\":[\"$(date '+%H:%M:%S')\"]}"
```

### 示例：Python 插件

```python
#!/usr/bin/env python3
import json
from datetime import datetime
print(json.dumps({"name": "clock", "lines": [datetime.now().strftime("%H:%M:%S")]}))
```

### 示例：随意写

```bash
#!/bin/bash
# 显示昨天吃了什么
echo '{"name":"memory","lines":["昨晚上吃的火锅"]}'
```

装一个插件就是复制文件 + 加可执行权限：

```bash
cp my-plugin.sh ~/.config/my-greeter/plugins/
chmod +x ~/.config/my-greeter/plugins/my-plugin.sh
```

重启 greetd 看效果：

```bash
sudo systemctl restart greetd
```

## 原理

通过 `$GREETD_SOCK` 找到 greetd 的 Unix socket，按 IPC 协议发 JSON 消息完成登录。
