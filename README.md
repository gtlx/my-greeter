# my-greeter

自写的 greetd greeter（前端）。

## 结构

```
my-greeter.py      ← 主程序
config.toml        ← 你自己的配置文件
安装与启动.md       ← 安装步骤
```

## 快速开始

### 1. 安装 greetd（后端）

```bash
sudo pacman -S greetd
```

### 2. 给 greeter 用户进入家目录的权限

```bash
sudo setfacl -m u:greeter:x /home/gtlx
```

只给了 `x`（穿过）权限，不能读不能写。

### 3. 配置 greetd

编辑 `/etc/greetd/config.toml`：

```toml
[terminal]
vt = 1

[default_session]
command = "/home/gtlx/软件/my-greeter/my-greeter.py"
user = "greeter"
```

### 4. 停用 lemurs，启用 greetd

```bash
sudo systemctl disable --now lemurs
sudo systemctl enable --now greetd
```

### 5. 测试

按 `Ctrl+Alt+F1` 切到 TTY1，应该能看到登录界面。

## 配置

编辑 `config.toml` 即可，不需要改 greetd 的配置。

## 原理

通过 `$GREETD_SOCK` 环境变量找到 greetd 的 Unix socket，
按 IPC 协议发送 JSON 消息完成登录流程。
