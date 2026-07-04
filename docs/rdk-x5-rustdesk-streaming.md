# RDK X5 RustDesk 桌面串流说明

本文说明如何在 RDK X5 上配置同一局域网 RustDesk 桌面串流，用于不接显示器时远程打开终端、VS Code、RViz 和 MoveIt 调试界面。

## 适用范围

- 开发板：RDK X5。
- 系统：Ubuntu 22.04 ARM64 / aarch64。
- 网络：RDK X5、电脑或手机处在同一局域网。
- ROS 环境：已按 [RDK X5 部署说明](rdk-x5-deployment.md) 完成 ROS 2 Humble、MoveIt 和 ros2_control 部署。
- 配网兜底：建议已经安装 `RDKX5-Setup` 网页配网服务，断网时可通过热点恢复 Wi-Fi。

## 安装

先从 RustDesk 发布页下载 Linux ARM64 `.deb` 包到 RDK X5，再在仓库根目录运行：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --deb /path/to/rustdesk-arm64.deb
```

如果系统中已经安装 RustDesk，可以省略 `--deb`：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh
```

脚本会交互提示输入 RustDesk 无人值守密码。

不要把真实现场密码写入脚本、文档、测试或提交记录；仓库中只使用 `<现场测试密码>` 这类占位。

## 默认配置

安装脚本默认做以下配置：

- 目标桌面用户为 `sunrise`，并配置 GDM 自动登录。
- 在 GDM 配置中设置 `WaylandEnable=false`，优先使用 X11 桌面会话。
- 启用 RustDesk systemd 服务，并重启 `rustdesk`。
- RustDesk 无人值守密码默认由脚本交互输入。

脚本会配置 GDM / X11，但这不保证所有无 HDMI 环境都能生成可串流桌面。如果不接显示器时仍然黑屏，建议使用 HDMI dummy 或接入临时显示器完成验证。

## 验证

安装完成后，在 RDK X5 上检查：

```bash
systemctl status rustdesk
rustdesk --get-id
hostname -I
```

记录 `rustdesk --get-id` 输出的 RustDesk ID，以及 `hostname -I` 中的局域网 IP。电脑或手机连接同一局域网后，打开 RustDesk 客户端，输入 RustDesk ID 和部署时设置的密码连接桌面。

## 自动化/临时测试

非敏感测试环境可以用 `--password '<现场测试密码>'` 传入临时密码：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --deb /path/to/rustdesk-arm64.deb --password '<现场测试密码>'
```

这种方式只适合自动化或临时测试，因为密码会暴露在 shell history 和 process argv 中。

## 不接显示器验证流程

1. 保持 SSH 可用，确认能通过局域网登录 RDK X5。
2. 运行安装脚本并记录 RustDesk ID。
3. 重启 RDK X5。
4. 不接显示器、键盘和鼠标，等待系统自动连接 Wi-Fi 并进入 `sunrise` 桌面。
5. 在同一局域网内用电脑 RustDesk 客户端连接。
6. 再用手机 RustDesk 客户端连接，确认能看到完整桌面并能打开终端。
7. 打开 RViz 或 MoveIt 调试界面，确认画面刷新正常。
8. 如果能连接但画面黑屏，接入 HDMI dummy 后重试；必要时临时接显示器确认桌面会话是否正常启动。

## 配网兜底

如果设备开机后没有进入目标 Wi-Fi，`RDKX5-Setup` 热点配网服务会作为兜底入口启动。电脑连接 `RDKX5-Setup` 后，在浏览器打开：

```text
http://192.168.88.1
```

完成配网后，电脑或手机切回目标局域网，再使用 RustDesk 连接 RDK X5。

## 排查

### RustDesk ID 为空

- 确认 RustDesk 已安装：`command -v rustdesk`。
- 查看服务状态：`systemctl status rustdesk`。
- 重启服务后再查询：`sudo systemctl restart rustdesk && rustdesk --get-id`。
- 如果刚安装完成，等待几十秒后重试。

### 能 SSH 但看不到桌面

- 确认 GDM 正常运行：`systemctl status gdm3`。
- 确认目标用户存在：`id sunrise`。
- 确认 GDM 配置中有 `AutomaticLoginEnable=True`、`AutomaticLogin=sunrise` 和 `WaylandEnable=false`。
- 重启后再连接 RustDesk，避免当前会话仍停留在旧配置。

### 无显示器黑屏

- 脚本会优先配置 X11，但无 HDMI 时仍可能没有有效显示输出。
- 优先插入 HDMI dummy 再重启验证。
- 临时接显示器确认 `sunrise` 是否能自动进入桌面。
- 如果 RViz 画面异常，先验证普通桌面和终端，再单独排查 OpenGL / 图形加速。

### 手机无法连接

- 确认手机和 RDK X5 在同一局域网，且没有连接到访客网络或移动数据。
- 确认 RustDesk ID 输入正确。
- 确认无人值守密码是安装时传入的密码。
- 用 `hostname -I` 查看设备 IP，确认手机所在网段可以访问该地址。

## 安全说明

测试阶段可以使用固定无人值守密码，但真实现场密码不要提交到仓库。需要外网访问、自建 RustDesk ID/Relay 服务器或更细粒度权限控制时，应单独做安全设计。
