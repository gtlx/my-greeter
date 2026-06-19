# my-greeter

自写的 greetd greeter（Rust 版）。

## 结构

```
my-greeter/
├── Cargo.toml
├── config.toml         ← 配置文件
├── plugins/
│   ├── clock.py        ← 时钟插件
│   └── sysinfo.py      ← 系统信息插件
└── src/
    ├── main.rs         ← 入口 + 事件循环
    ├── app.rs          ← 状态机
    ├── config.rs       ← 配置 + 主题
    ├── ipc.rs          ← greetd IPC 协议
    ├── plugins.rs      ← 插件系统
    └── ui.rs           ← ratatui 渲染
```

## 快速开始

### 1. 安装 greetd

```bash
sudo pacman -S greetd
sudo setfacl -m u:greeter:x /home/gtlx
```

### 2. 配置 greetd

编辑 `/etc/greetd/config.toml`：

```toml
[terminal]
vt = 1

[default_session]
command = "/home/gtlx/软件/my-greeter/target/release/my-greeter"
user = "greeter"
```

### 3. 编译

```bash
cd /home/gtlx/软件/my-greeter
cargo build --release
```

### 4. 预览

```bash
./target/release/my-greeter --preview
```

### 5. 启用

```bash
sudo systemctl disable --now lemurs
sudo systemctl enable --now greetd
```

## 配置

编辑 `config.toml`：

```toml
[auth]
default_user = "gtlx"       # 默认用户名，自动填入
auto_login = false           # true 跳过用户名输入

[branding]
title = "gtlx's machine"    # 顶部标题

[theme]
title = "cyan bold"          # 标题样式
separator = "dark gray"      # 标题下方横线
border = "white"             # 输入框边框（未聚焦）
border_focus = "#FFA500"     # 输入框边框（聚焦时，支持 hex 色）
text = "white"               # 输入文字（未聚焦）
text_focus = "#FFA500"       # 输入文字（聚焦时）
plugin = "green"             # 插件输出文字
hint = "dark gray"           # 底部快捷键提示
error = "red bold"           # 错误提示
session = "dark gray"       # Session 切换器（未聚焦）
session_focus = "white bold" # Session 切换器（聚焦时）
```

### 支持的样式

**颜色名：** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`,
`dark_gray`, `gray`, `light_red`, `light_green`, `light_yellow`, `light_blue`,
`light_magenta`, `light_cyan`, `orange`

**Hex 色：** `#FFA500`, `#1a1a2e` 等任何 6 位 RGB

**修饰符：** `bold`, `dim`, `italic`, `underline`

组合写法：`"cyan bold"`, `"white bold"`, `"#FFA500 bold"`

## 操作

| 按键 | 作用 |
|------|------|
| `Tab` / `↓` | 下一个焦点 |
| `↑` / `Shift+Tab` | 上一个焦点 |
| `←` `→` | 切换 Session |
| `Enter` | 确认 / 跳转下一字段 |
| `Esc` | 回到 Session 行 |
| `Ctrl+U` / `Ctrl+L` | 清空当前输入 |
| `Ctrl+H` / `Backspace` | 删除上一个字符 |
| `F1` | 关机 |
| `F2` | 重启 |
| `q` | 退出 greeter |

## 插件

插件是可执行文件，启动时执行一次，输出 JSON 到 stdout：

```json
{"name":"clock","lines":["14:30:00"]}
```

放在 `~/.config/my-greeter/plugins/` 或项目 `plugins/` 目录。

### 示例：shell 插件

```bash
#!/bin/bash
echo '{"name":"clock","lines":["'$(date '+%H:%M:%S')'"]}'
```

### 示例：Python 插件

```python
#!/usr/bin/env python3
import json
from datetime import datetime
print(json.dumps({"name":"clock","lines":[datetime.now().strftime("%H:%M:%S")]}))
```
