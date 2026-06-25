# my-greeter

自写的 greetd greeter（Rust 版）。卡片式/面板式布局，支持自适应宽窄屏、Unicode 装饰、插件定位、密码可见切换。

## 特性

- **🎴 卡片式布局**：外层大面板 + 内部左右/上下分栏
- **📐 自适应响应**：宽屏(≥80列)水平分栏，窄屏垂直堆叠，极小屏极简模式
- **🎨 Unicode 装饰**：圆角边框、箭头(◀▶)、图标(👤🔑⊞)、粗圆点密码(●)
- **👁 密码可见切换**：`Ctrl+T` 切换密码明文/掩码显示
- **📍 插件定位**：插件可声明 `position: "left"|"center"|"right"`
- **🖼 背景填充**：可选点阵背景图案 或 ASCII 艺术水印图案（`patterns/` 文件夹）
- **🎯 渐变/强调色**：`accent` 色独立配置，聚焦时高亮明显

## 结构

```
my-greeter/
├── Cargo.toml
├── config.toml         ← 配置文件
├── patterns/           ← 背景图案文件 (.txt)
│   ├── arch.txt        ← Arch Linux 风格
│   ├── wave.txt        ← 波浪图案
│   ├── hex.txt         ← 六边形网格
│   ├── mountain.txt    ← 山脉图案
│   └── nix.txt         ← NixOS 风格
├── plugins/
│   ├── clock.py        ← 像素风时钟插件
│   └── sysinfo.py      ← 系统信息插件
└── src/
    ├── main.rs         ← 入口 + 事件循环
    ├── app.rs          ← 状态机 + 插件位置
    ├── config.rs       ← 配置 + 主题
    ├── ipc.rs          ← greetd IPC 协议
    ├── plugins.rs      ← 插件系统
    └── ui.rs           ← ratatui 渲染（布局/卡片/自适应）
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
title = "gtlx's machine"    # 面板标题

[theme]
# 布局模式: "auto"=根据宽度自适应, "horizontal"=始终水平, "vertical"=始终垂直
layout = "auto"
title = "cyan bold"          # 标题样式
separator = "dark gray"      # 分隔线
border = "white"             # 输入框边框（未聚焦）
border_focus = "#FFA500"     # 输入框边框（聚焦时，支持 hex 色）
text = "white"               # 输入文字（未聚焦）
text_focus = "#FFA500"       # 输入文字（聚焦时）
plugin = "green"             # 插件输出文字
hint = "dark gray"           # 底部快捷键提示
error = "red bold"           # 错误提示
session = "dark gray"        # Session 选择器（未聚焦）
session_focus = "white bold" # Session 选择器（聚焦时）
panel_title = "cyan bold"    # 外层大面板标题
accent = "#FFA500"           # 强调色（聚焦边框/标题高亮）
background = ""              # 旧版点阵背景: ""=无, "dark gray"=灰色点阵, "none"=无
background_pattern = "arch"   # ASCII 图案背景: 图案文件名(不含.txt), 空=禁用
background_pattern_dir = "patterns"  # 图案文件目录
background_style = "dark gray"       # 图案绘制颜色（建议暗色 = 水印效果）
```

### 支持的样式

**颜色名：** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`,
`dark_gray`, `gray`, `light_red`, `light_green`, `light_yellow`, `light_blue`,
`light_magenta`, `light_cyan`, `orange`

**Hex 色：** `#FFA500`, `#1a1a2e` 等任何 6 位 RGB

**修饰符：** `bold`, `dim`, `italic`, `underline`

组合写法：`"cyan bold"`, `"white bold"`, `"#FFA500 bold"`

## 背景图案

my-greeter 支持用 ASCII 艺术字符作为终端背景水印，独立于前景的登录面板。

### 内置图案

```
patterns/
├── arch.txt      ← █ Arch Linux 风格（19行, 40字符宽）
├── hex.txt       ⬡ 六边形网格（9行, 46字符宽）
├── mountain.txt  ▲ 山脉（19行, 77字符宽）
├── nix.txt       ❄ NixOS 风格雪花（41行, 87字符宽）
└── wave.txt      ≈ 波浪（33行, 66字符宽）
```

### 切换图案

改 `config.toml` 的 `background_pattern` 字段即可：

```toml
[theme]
background_pattern = "arch"      # 使用 arch.txt
background_pattern = "hex"       # 使用 hex.txt
background_pattern = "wave"      # 使用 wave.txt
background_pattern = ""           # 禁用图案背景
```

### 使用自定义图案

1. 在 `patterns/` 目录下新建 `.txt` 文件
2. 写入任意 ASCII 字符图案
3. 配置中填文件名（不含 `.txt`）

```
# 例如创建 mylogo.txt：
patterns/
└── mylogo.txt        ← 自定义图案
```

```toml
background_pattern = "mylogo"
```

图案文件也可以放在其他位置，用路径指定：

```toml
background_pattern = "/home/gtlx/.config/my-greeter/custom.txt"
background_pattern = "./dev-pattern.txt"
background_pattern = "../shared/pattern.txt"
```

### 图案搜索路径

不指定绝对路径时，按以下顺序查找 `{background_pattern_dir}/{name}.txt`：

| 优先级 | 路径 |
|--------|------|
| 1 | 项目根目录下的 `patterns/` |
| 2 | 当前目录下的 `patterns/` |
| 3 | `~/.config/my-greeter/patterns/` |
| 4 | 可执行文件同目录下的 `patterns/` |

`background_pattern_dir` 也可以改为其他目录名或绝对路径：

```toml
background_pattern_dir = "my_art"          # 项目根下的 my_art/
background_pattern_dir = "/etc/my-greeter/arts"  # 绝对路径
```

### 调整水印颜色

```toml
background_style = "dark gray"     # 暗灰色，最不明显
background_style = "gray"          # 灰色，隐约可见
background_style = "light blue"    # 浅蓝色
background_style = "dark gray bold"  # 暗灰色加粗
background_style = "#1a1a2e"       # 深色 hex 色
background_style = ""               # 默认白色（较明显）
```

建议使用 `dark gray` 或自定义深色，形成**水印暗纹**效果。

### 渲染行为

- 背景图案**先绘制**，登录面板和输入框**后绘制**（覆盖在背景之上）
- 图案**垂直居中**于终端
- 图案宽于终端时**居中截取**可见部分
- 图案窄于终端时**居中对齐**，两侧补空白
- 图案高度超过终端时**从底部截取**
- 图案找不到或禁用时，**回退到旧版点阵背景**（`background` 字段）

### 示例效果示意

```
┌──────────────────────────────┐  ← 登录面板覆盖在背景上
│       ┌──── Login ───────┐   │
│       │  ◀ ⊞ sway ▶      │   │
│       │  gtlx             │   │
│       │  ●●●●●●●          │   │
│       └──────────────────┘   │
│                              │
│  ░░░░░  ░░░  ░░░  ░░░  ░░░  │  ← 背景水印隐约透出
│    ░      ░    ░    ░    ░    │
└──────────────────────────────┘
```

## 操作

| 按键 | 作用 |
|------|------|
| `Tab` / `↓` | 下一个焦点 |
| `↑` / `Shift+Tab` | 上一个焦点 |
| `←` `→` | 切换 Session |
| `Enter` | 确认 / 跳转下一字段 |
| `Esc` | 回到 Session 行 |
| `Ctrl+T` | 切换密码可见 |
| `Ctrl+U` / `Ctrl+L` | 清空当前输入 |
| `Ctrl+H` / `Backspace` | 删除上一个字符 |
| `F1` | 关机 |
| `F2` | 重启 |
| `q` | 退出 greeter |

## 插件

插件是可执行文件，启动时执行一次，输出 JSON 到 stdout：

```json
{"name":"clock","lines":[" ██  ██    ██ "],"position":"center"}
```

| JSON 字段 | 说明 |
|-----------|------|
| `name` | 插件名（可选） |
| `lines` | 显示文本行数组（必填） |
| `position` | `"left"` / `"center"` / `"right"`（默认 `"center"`） |

放在 `~/.config/my-greeter/plugins/` 或项目 `plugins/` 目录。

### 示例：shell 插件

```bash
#!/bin/bash
echo '{"name":"clock","lines":["'$(date '+%H:%M:%S')'"],"position":"center"}'
```

### 示例：Python 插件（指定位置）

```python
#!/usr/bin/env python3
import json
from datetime import datetime
print(json.dumps({
    "name": "clock",
    "lines": [datetime.now().strftime("%H:%M:%S")],
    "position": "center"
}))
```

## 布局说明

### 宽屏 (≥80列) — 水平分栏
```
┌─── gtlx's machine ───────────────────────────┐
│ ┌─────────────┐  ┌──── Login ───────────────┐│
│ │             │  │ ┌─ Session ───────────┐  ││
│ │  时钟(居中)  │  │ │  ◀ ⊞ sway ▶ ▪       │  ││
│ │             │  │ └─────────────────────┘  ││
│ │             │  │ ┌─ 👤 Login name ─────┐  ││
│ │  sysinfo    │  │ │ gtlx                │  ││
│ │             │  │ └─────────────────────┘  ││
│ │             │  │ ┌─ 🔑 Password ───────┐  ││
│ │             │  │ │ ●●●●●               │  ││
│ │             │  │ └─────────────────────┘  ││
│ └─────────────┘  └──────────────────────────┘│
│    Tab/↓:focus  ←→:session  …  Ctrl+T:reveal │
└──────────────────────────────────────────────┘
```

### 窄屏 (<80列) — 垂直堆叠
```
┌─── gtlx's machine ───┐
│ ┌────────────────────┐│
│ │     时钟(居中)      ││
│ │     sysinfo        ││
│ └────────────────────┘│
│ ┌─── Login ──────────┐│
│ │  Session / Login   ││
│ │  / Password        ││
│ └────────────────────┘│
│    Tab:focus  …       │
└───────────────────────┘
```
