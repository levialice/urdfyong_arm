# RDK X5 开机热点配网设计

## 目标

在 RDK X5 开机后，如果 30 秒内没有成功连接到已保存的 Wi-Fi，设备自动开启一个无密码热点。调试电脑连接该热点后，通过浏览器打开配网页面，填写目标 Wi-Fi 信息。设备连接成功后关闭热点，进入正常局域网，后续可通过 RustDesk 等局域网串流工具访问。

## 默认配置

| 项目 | 默认值 |
| --- | --- |
| Wi-Fi 等待时间 | 30 秒 |
| 热点 SSID | `RDKX5-Setup` |
| 热点密码 | 无密码开放热点 |
| 热点网段 | `192.168.88.0/24` |
| 设备热点地址 | `192.168.88.1` |
| 配网页面 | `http://192.168.88.1` |
| Wi-Fi 管理方式 | NetworkManager / `nmcli` |
| 服务管理方式 | systemd |

开放热点便于现场调试，但只建议在实验室、果园现场等受控环境使用；公共环境中不建议长期保持开放热点。

## 启动流程

1. `systemd` 在开机后启动配网守护服务。
2. 服务等待 NetworkManager 自动连接已保存 Wi-Fi，等待时间为 30 秒。
3. 如果 `wlan0` 已获得正常局域网地址，服务保持空闲，不开启热点。
4. 如果 30 秒后仍未联网，服务创建或启动 `RDKX5-Setup` 热点。
5. 热点固定设备地址为 `192.168.88.1/24`，电脑连接热点后由 NetworkManager 共享模式分配地址。
6. 设备启动本地 Web 配网页面，监听 `0.0.0.0:80`。
7. 用户在电脑浏览器打开 `http://192.168.88.1`。
8. 页面展示附近 Wi-Fi 列表，用户选择 SSID 并输入密码。
9. 后端调用 `nmcli` 保存并连接目标 Wi-Fi。
10. 连接成功后关闭热点和配网页面，设备进入目标局域网。

## 页面功能

配网页面保持轻量，优先满足现场可用性：

- 显示设备当前网络状态。
- 扫描并展示附近 Wi-Fi SSID。
- 支持手动输入隐藏 SSID。
- 输入 Wi-Fi 密码并提交。
- 显示连接进度、成功或失败原因。
- 连接成功后提示用户切换回目标局域网访问设备。

## 后端行为

后端服务负责把网页操作转换为 NetworkManager 操作：

- 通过 `nmcli device wifi rescan` 触发扫描。
- 通过 `nmcli --terse --fields SSID,SIGNAL,SECURITY device wifi list` 获取热点列表。
- 通过 `nmcli device wifi connect <ssid> password <password>` 保存并连接 Wi-Fi。
- 连接成功后停止热点连接。
- 连接失败时保留热点，方便用户重新输入。

为避免命令注入，SSID 和密码只作为子进程参数传入，不拼接 shell 命令字符串。

## systemd 服务划分

建议拆成两个服务，职责更清晰：

| 服务 | 职责 |
| --- | --- |
| `rdkx5-wifi-provision.service` | 开机检查联网状态，必要时开启热点和 Web 服务 |
| `rdkx5-wifi-provision-web.service` | 运行本地 Web 配网页面 |

也可以在首版实现中合并为一个服务，后续再拆分。

## NetworkManager 热点配置

热点由 NetworkManager 管理，避免手写 `hostapd` 和 `dnsmasq` 配置与系统网络管理冲突。建议创建持久连接配置：

```bash
nmcli con add type wifi ifname wlan0 con-name RDKX5-Setup autoconnect no ssid RDKX5-Setup
nmcli con modify RDKX5-Setup 802-11-wireless.mode ap
nmcli con modify RDKX5-Setup 802-11-wireless.band bg
nmcli con modify RDKX5-Setup ipv4.method shared ipv4.addresses 192.168.88.1/24
nmcli con modify RDKX5-Setup ipv6.method ignore
```

无密码热点不设置 `wifi-sec` 相关字段。

## RustDesk 串流衔接

配网服务只负责确保设备能进入目标局域网，不直接启动或配置 RustDesk。进入目标局域网后，RustDesk 可以使用 LAN 发现、固定 IP、主机名或后续单独配置的服务入口进行连接。

## 验证方法

1. 已保存 Wi-Fi 可用时重启设备，确认 30 秒后不会开启热点。
2. 删除或断开目标 Wi-Fi 后重启设备，确认出现 `RDKX5-Setup` 开放热点。
3. 电脑连接热点，访问 `http://192.168.88.1`。
4. 输入可用 Wi-Fi 后确认设备加入目标局域网。
5. 确认热点关闭，设备可以通过目标局域网 SSH 或 RustDesk 访问。
6. 输入错误密码，确认热点不会关闭，页面能提示失败并允许重试。

## 首版实现说明

首版实现使用 Python 标准库 HTTP 服务，不额外依赖 Flask。开机检测、热点控制和网页配网合并在 `rdkx5-wifi-provision.service` 一个 systemd 服务中，后续如果需要更复杂的页面或认证，再拆分独立 Web 服务。

首版包含以下文件：

- `scripts/install_rdk_x5_wifi_provisioning.sh`
- `scripts/rdkx5_wifi_provision.py`
- `systemd/rdkx5-wifi-provision.service`
- 配套测试，覆盖命令生成、状态判断、网页渲染和失败重试逻辑。
