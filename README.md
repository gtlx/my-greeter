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
[log]
enable = false                # 开启日志
path = "/tmp/my-greeter.log"   # 日志文件路径

[auth]
default_user = "gtlx"       # 默认用户名
auto_login = false           # true 跳过用户名输入，直接输密码

[sessions]
default = "niri-session"     # 默认 session
extra = ["bash"]             # 额外 session（系统自动扫描 .desktop）

[branding]
title = "gtlx's machine"    # 标题

[theme]
title = "cyan bold"          # 标题样式
sep = ""                     # 分隔线样式
plugin = "green"             # 插件输出样式
label = "yellow"             # 提示文字样式
input = "white"              # 输入文字样式
error = "red bold"           # 错误提示样式
session = "white"            # session 列表样式
session_default = "cyan"     # 默认 session 样式
select = "yellow"            # 选择提示样式
```

### 日志

默认不写文件。开启后输出到 `/tmp/` 下，重启自动清空。

日志格式：
```
[2026-06-18 18:45:55] [INFO] greeter started
[2026-06-18 18:45:55] [INFO] login attempt: user=gtlx
[2026-06-18 18:45:55] [INFO] auth success: user=gtlx
[2026-06-18 18:45:55] [INFO] starting session: niri-session
[2026-06-18 18:45:55] [INFO] session started, greeter exiting
```

记录的事件：

| 级别 | 记录内容 |
|------|---------|
| `INFO` | 启动、登录尝试、认证成功、session 启动 |
| `WARN` | 插件超时/失败、空用户名、认证失败 |
| `ERROR` | session 启动失败、未捕获异常 |
| `DEBUG` | socket 连接信息 |

### 支持的颜色和属性

**颜色：** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`
**亮色：** `bright_black`, `bright_red`, `bright_green`, `bright_yellow`, `bright_blue`, `bright_magenta`, `bright_cyan`, `bright_white`
**属性：** `bold`, `dim`, `italic`, `underline`, `blink`, `reverse`

组合写法：`"cyan bold"`, `"yellow underline"`, `"bright_white bold"`

## 插件

插件是在登录界面**启动时执行一次**的可执行文件，输出内容会显示在标题下方。

### 插件协议

插件**启动时往 stdout 输出一行 JSON**：

```json
{"name":"插件名","lines":["第一行","第二行"]}
```

### 示例：shell 插件

```bash
#!/bin/bash
# ~/.config/my-greeter/plugins/clock.sh
echo '{"name":"clock","lines":["'$(date '+%H:%M:%S')'"]}'
```

### 示例：Python 插件

```python
#!/usr/bin/env python3
import json
from datetime import datetime
print(json.dumps({"name":"clock","lines":[datetime.now().strftime("%H:%M:%S")]}))
```

### 示例：Rust / Go / C / 任意语言

只要能生成可执行文件、输出一行 JSON 到 stdout 就行。

### 插件目录

| 目录 | 说明 |
|------|------|
| `~/.config/my-greeter/plugins/` | 用户自己的插件 |
| 脚本同目录下的 `plugins/` | 项目自带的示例插件 |

### 安装插件

```bash
cp my-plugin.sh ~/.config/my-greeter/plugins/
chmod +x ~/.config/my-greeter/plugins/my-plugin.sh
sudo systemctl restart greetd
```

插件出错（超时、非 JSON、返回值非 0）会被**静默跳过**，不影响登录。

## 原理

通过 `$GREETD_SOCK` 找到 greetd 的 Unix socket，按 IPC 协议发 JSON 消息完成登录。
