# RDK X5 局域网桌面串流设计

## 目标

让 RDK X5 在不连接显示器、键盘和鼠标的情况下，开机后自动进入可远程访问的桌面环境。调试电脑或手机与 RDK X5 处于同一局域网时，可以通过 RustDesk 连接设备桌面，打开终端、VS Code、RViz 和 MoveIt 调试界面。

首版范围只覆盖同一局域网访问，不做公网穿透和自建 ID/Relay 服务器。公网访问可以在局域网方案稳定后再单独设计。

## 已确认约束

- 目标设备为 D-Robotics RDK X5，Ubuntu 22.04，ARM64 / aarch64。
- 远程访问方式首选 RustDesk 完整桌面串流。
- RDK X5 开机后允许 `sunrise` 用户自动登录桌面。
- 首版只要求电脑、手机和 RDK X5 在同一个局域网。
- 测试阶段可以使用固定 RustDesk 无人值守密码，但密码不能硬编码到公开仓库。
- 现有 `RDKX5-Setup` 热点网页配网服务继续作为断网兜底入口。

## 参考依据

- RustDesk Linux 文档建议 Ubuntu / Debian 使用 `.deb` 包安装，并说明 Wayland 支持仍偏实验，登录屏远程访问仍需要 X11。
- RustDesk Client Deployment 文档提供了 `rustdesk --password` 配置无人值守密码的部署方式。

参考链接：

- https://rustdesk.com/docs/en/client/linux/
- https://rustdesk.com/docs/en/self-host/client-deployment/

## 方案取舍

### 方案一：RustDesk + 自动登录 + X11 桌面

开机后设备自动连接 Wi-Fi，`sunrise` 用户自动进入 X11 桌面，RustDesk 服务随系统启动。部署脚本安装 ARM64 RustDesk 包，并通过参数或交互输入设置无人值守密码。

这是首版推荐方案。它最接近本地插显示器的体验，能直接操作 RViz、VS Code 和终端。主要风险是无显示器时图形栈可能没有有效屏幕，需要准备虚拟显示兜底。

### 方案二：VNC 桌面

使用 `x11vnc`、TigerVNC 等方案提供桌面访问。

该方案局域网内简单可用，但手机体验、安全性、后续外网扩展都不如 RustDesk。它可以作为 RustDesk 在 RDK X5 上不可用时的备用方向，不作为首选实现。

### 方案三：ROS 远程调试，不串流桌面

RDK X5 只运行硬件节点和控制器，电脑运行 RViz / MoveIt 可视化，通过 ROS 2 网络远程调试。

该方案性能压力最低，也适合最终产品化拆分，但不能满足“设备不用带显示器仍可看到设备桌面”的当前目标。

## 首版架构

首版由四层组成：

1. 配网层：复用 `rdkx5-wifi-provision.service`。开机后如果设备不能进入已保存 Wi-Fi，则启动 `RDKX5-Setup` 热点和 `http://192.168.88.1` 配网页面。
2. 桌面层：配置显示管理器让 `sunrise` 自动登录，并优先使用 X11 会话。
3. 串流层：安装 RustDesk ARM64 客户端，启用 RustDesk systemd 服务，设置无人值守访问密码。
4. 验证层：通过 SSH 和 RustDesk 双路径验证设备状态，确保没显示器时仍能恢复和调试。

## 启动流程

1. RDK X5 上电启动。
2. NetworkManager 尝试连接已保存 Wi-Fi。
3. 配网服务等待固定时间。如果 Wi-Fi 可用，则不启动热点；如果 Wi-Fi 不可用，则启动 `RDKX5-Setup` 热点。
4. Wi-Fi 可用后，系统进入图形目标。
5. 显示管理器自动登录 `sunrise` 用户，启动 X11 桌面会话。
6. RustDesk 服务启动并读取已配置的无人值守密码。
7. 用户在同一局域网内用电脑或手机 RustDesk 客户端连接 RDK X5。
8. 进入桌面后可打开终端、VS Code、RViz 或 MoveIt 调试流程。

## 部署脚本设计

后续实现建议新增独立脚本：

```bash
./scripts/install_rdk_x5_rustdesk_streaming.sh
```

脚本职责：

- 检查系统版本、CPU 架构和当前用户。
- 安装桌面串流所需基础依赖。
- 获取或安装 RustDesk ARM64 `.deb` 包。
- 配置 RustDesk systemd 服务并确认服务运行。
- 通过参数或交互方式设置无人值守密码。
- 配置 `sunrise` 自动登录。
- 配置或提示切换到 X11 会话。
- 输出 RustDesk ID、设备 IP、验证命令和重启提示。

密码处理规则：

- 仓库不保存默认 RustDesk 密码。
- 脚本可以支持 `--password <value>` 方便现场测试。
- 如果未传入 `--password`，脚本交互提示输入。
- 脚本输出可以显示本次设置的密码，但文档不记录真实现场密码。

## 显示与无显示器风险

无显示器场景下，桌面串流可能遇到三类问题：

1. 登录屏或桌面跑在 Wayland，会导致 RustDesk 在登录前或无显示器时不可控。
2. 没有 HDMI 显示器时，系统可能不创建有效显示输出。
3. RViz 依赖 OpenGL，虚拟显示或远程桌面环境可能存在渲染限制。

首版处理策略：

- 优先配置 X11。
- 优先验证真实 HDMI 或 HDMI dummy 插头场景。
- 如果无 HDMI dummy 仍无法创建桌面，再引入 Xorg dummy 配置作为第二阶段补充。
- 保留 SSH 作为紧急维护入口，避免 RustDesk 配置失败后失联。

## 错误处理

- RustDesk 安装包下载失败：脚本输出手动下载地址，并允许用户把 `.deb` 放到本地路径后重试。
- ARM64 包不存在或名称变化：脚本停止，不安装 x86_64 包。
- `rustdesk --password` 失败：脚本保留服务状态和日志提示，不静默通过。
- 自动登录配置失败：脚本提示需要接显示器或通过 SSH 手动修复。
- 重启后无法进入 Wi-Fi：继续依赖 `RDKX5-Setup` 热点配网兜底。
- RustDesk 无法显示桌面：先检查 X11 会话，再检查是否存在有效显示输出。

## 验证计划

本地代码验证：

- Shell 脚本静态检查。
- 单元测试覆盖参数解析、ARM64 包选择、密码参数不写入仓库、关键配置文本生成。

设备侧验证：

1. SSH 登录 RDK X5，确认系统为 ARM64 Ubuntu 22.04。
2. 执行串流部署脚本并记录 RustDesk ID。
3. 重启设备，不连接显示器。
4. 确认设备自动连接局域网，SSH 可达。
5. 使用电脑 RustDesk 客户端连接设备桌面。
6. 使用手机 RustDesk 客户端连接设备桌面。
7. 打开终端和 VS Code。
8. 打开 RViz 或运行 MoveIt smoke test。
9. 删除或断开 Wi-Fi 后重启，确认热点配网仍可恢复网络。

## 不在首版范围

- 公网 RustDesk 访问。
- 自建 RustDesk ID/Relay 服务器。
- Web 控制台控制机械臂。
- 自动启动机械臂控制流程。
- 机械臂动作安全互锁。

这些内容后续应作为独立设计继续推进。

## 成功标准

- RDK X5 不接显示器时，开机后能自动进入局域网。
- 用户能通过 RustDesk 从电脑连接完整桌面。
- 用户能通过 RustDesk 从手机连接完整桌面。
- 设备重启后串流服务仍可用。
- 如果 Wi-Fi 不可用，设备仍能回退到 `RDKX5-Setup` 配网页面。
- 仓库中不包含真实现场 RustDesk 密码或其他敏感凭据。
