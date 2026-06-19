# NAS 系统思路（讨论记录）

## 整体架构

```
my-greeter → 登录认证 → niri/sway 桌面 → 浏览器 → NAS WebUI
```

## 分层设计

### 1. 登录层 — my-greeter（已有）
- greetd + my-greeter 负责用户认证
- 认证成功后启动桌面环境（niri 等）
- 以后可拆出 daemon 给 WebUI 复用认证

### 2. 桌面层 — 不重复造轮子
- Wayland 合成器用现成的（niri/sway）
- 应用启动：扫描 `/usr/share/applications/*.desktop`
- 不需要自研应用商店

### 3. NAS WebUI — 重点自研
- **后端**：Rust（Axum / Actix-web）
- **功能**：硬盘挂载、多用户管理、Docker 管理
- **系统命令**：lsblk、mount/umount、useradd/usermod、docker API
- **前端**：React/Svelte + shadcn/ui 或 Ant Design
- **风格**：类 TrueNAS/Unraid 深色主题

### 4. my-greeter 在 NAS 中的角色
- 只负责登录这一个界面
- 之后可前后端分离：my-greeter-daemon + 多前端（TTY/Web/API）
- 与 NAS WebUI 无直接耦合

## 开发顺序建议

1. my-greeter 前后端分离（可选增强）
2. NAS 后端基本功能（硬盘、用户、Docker）
3. NAS WebUI
4. .desktop 应用启动器（可选）

## 后续开始

创建新 git 分支，从零搭建 NAS 后端项目。
