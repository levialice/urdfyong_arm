# RDK X5 LAN Desktop Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reviewed installer and documentation for RDK X5 same-LAN RustDesk desktop streaming, so the board can be used without a monitor after boot.

**Architecture:** Keep the streaming setup separate from the existing ROS 2 and Wi-Fi provisioning installers. Add one Bash installer for RustDesk, X11-oriented auto-login, and service checks; add unittest coverage that verifies safe password handling, ARM64-only install behavior, and documentation links.

**Tech Stack:** Bash, systemd, NetworkManager-adjacent Ubuntu desktop configuration, RustDesk CLI, Python unittest.

---

## File Structure

- Create: `scripts/install_rdk_x5_rustdesk_streaming.sh`
  - Installs and configures same-LAN RustDesk desktop streaming on RDK X5.
  - Accepts `--password`, `--deb`, `--user`, `--no-autologin`, `--no-x11-config`, and `--dry-run`.
  - Never stores a default password in the repository.
- Create: `docs/rdk-x5-rustdesk-streaming.md`
  - User-facing setup, verification, rollback, and troubleshooting guide.
- Create: `tests/test_install_rdk_x5_rustdesk_streaming.py`
  - Static and behavioral tests for installer text, arguments, password safety, ARM64 checks, and expected commands.
- Modify: `README.md`
  - Add a short entry pointing to the RustDesk streaming installer and guide.
- Modify: `docs/rdk-x5-deployment.md`
  - Link the streaming guide from the existing remote-control section.

## Task 1: Add Installer Test Skeleton

**Files:**
- Create: `tests/test_install_rdk_x5_rustdesk_streaming.py`
- Target later: `scripts/install_rdk_x5_rustdesk_streaming.sh`

- [ ] **Step 1: Write failing tests for the missing installer**

Create `tests/test_install_rdk_x5_rustdesk_streaming.py` with:

```python
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_rdk_x5_rustdesk_streaming.sh"


class RustDeskStreamingInstallerTest(unittest.TestCase):
    def read_installer(self):
        return INSTALLER.read_text(encoding="utf-8")

    def test_installer_file_exists(self):
        self.assertTrue(INSTALLER.exists())

    def test_help_mentions_supported_options(self):
        result = subprocess.run(
            ["bash", str(INSTALLER), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertIn("--password", result.stdout)
        self.assertIn("--deb", result.stdout)
        self.assertIn("--user", result.stdout)
        self.assertIn("--no-autologin", result.stdout)
        self.assertIn("--no-x11-config", result.stdout)
        self.assertIn("--dry-run", result.stdout)

    def test_installer_requires_arm64_and_never_x86_64(self):
        text = self.read_installer()

        self.assertIn("aarch64", text)
        self.assertIn("arm64", text)
        self.assertNotIn("x86_64.deb", text)

    def test_installer_does_not_hardcode_site_password(self):
        text = self.read_installer()

        self.assertNotRegex(text, r"--password ['\"][0-9]{8,}['\"]")
        self.assertNotRegex(text, r"RUSTDESK_PASSWORD=['\"][0-9]{8,}['\"]")
        self.assertIn("--password", text)
        self.assertIn("read -r -s", text)

    def test_dry_run_does_not_require_root(self):
        result = subprocess.run(
            ["bash", str(INSTALLER), "--dry-run", "--password", "test-pass"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertIn("[rdkx5-rustdesk] Dry run", result.stdout)
        self.assertIn("Target user: sunrise", result.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: FAIL because the installer file is absent before this task.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
git add tests/test_install_rdk_x5_rustdesk_streaming.py
git commit -m "添加 RDK X5 串流安装脚本测试"
```

## Task 2: Implement Installer Argument Parsing and Safety Checks

**Files:**
- Create: `scripts/install_rdk_x5_rustdesk_streaming.sh`
- Test: `tests/test_install_rdk_x5_rustdesk_streaming.py`

- [ ] **Step 1: Add the installer with argument parsing**

Create `scripts/install_rdk_x5_rustdesk_streaming.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

TARGET_USER="sunrise"
RUSTDESK_PASSWORD=""
RUSTDESK_DEB=""
CONFIGURE_AUTOLOGIN=1
CONFIGURE_X11=1
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh [options]

Installs same-LAN RustDesk desktop streaming support for RDK X5.

Options:
  --password VALUE     Set RustDesk unattended access password.
  --deb PATH           Install RustDesk from a local arm64 .deb package.
  --user USER          Desktop user to auto-login. Default: sunrise.
  --no-autologin       Skip display-manager auto-login changes.
  --no-x11-config      Skip X11 display-manager changes.
  --dry-run            Print planned actions without changing the system.
  -h, --help           Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)
      RUSTDESK_PASSWORD="${2:-}"
      shift
      ;;
    --deb)
      RUSTDESK_DEB="${2:-}"
      shift
      ;;
    --user)
      TARGET_USER="${2:-}"
      shift
      ;;
    --no-autologin)
      CONFIGURE_AUTOLOGIN=0
      ;;
    --no-x11-config)
      CONFIGURE_X11=0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

log() {
  echo "[rdkx5-rustdesk] $*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[rdkx5-rustdesk] Dry run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

validate_architecture() {
  local arch
  arch="$(uname -m)"
  case "${arch}" in
    aarch64|arm64)
      ;;
    *)
      echo "Unsupported architecture: ${arch}. RDK X5 streaming installer requires ARM64 / aarch64." >&2
      exit 1
      ;;
  esac
}

prompt_password_if_needed() {
  if [[ -z "${RUSTDESK_PASSWORD}" ]]; then
    read -r -s -p "RustDesk unattended password: " RUSTDESK_PASSWORD
    echo
  fi

  if [[ -z "${RUSTDESK_PASSWORD}" ]]; then
    echo "RustDesk password cannot be empty." >&2
    exit 1
  fi
}

main() {
  log "Target user: ${TARGET_USER}"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run only; no system changes will be made."
    return 0
  fi

  if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run as root: sudo $0" >&2
    exit 1
  fi

  validate_architecture
  require_command apt-get
  require_command systemctl
  require_command loginctl
  require_command install
  prompt_password_if_needed

  log "Safety checks passed."
}

main "$@"
```

- [ ] **Step 2: Make the installer executable**

Run:

```bash
git update-index --chmod=+x scripts/install_rdk_x5_rustdesk_streaming.sh
```

- [ ] **Step 3: Run the installer tests**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit the installer skeleton**

Run:

```bash
git add scripts/install_rdk_x5_rustdesk_streaming.sh tests/test_install_rdk_x5_rustdesk_streaming.py
git commit -m "添加 RDK X5 RustDesk 串流安装脚本"
```

## Task 3: Add RustDesk Installation and Service Configuration

**Files:**
- Modify: `scripts/install_rdk_x5_rustdesk_streaming.sh`
- Modify: `tests/test_install_rdk_x5_rustdesk_streaming.py`

- [ ] **Step 1: Add tests for RustDesk install behavior**

Append these methods to `RustDeskStreamingInstallerTest`:

```python
    def test_installer_installs_local_deb_with_apt(self):
        text = self.read_installer()

        self.assertIn("install_rustdesk", text)
        self.assertIn('apt-get install -y "${RUSTDESK_DEB}"', text)
        self.assertIn("rustdesk --password", text)
        self.assertIn("systemctl restart rustdesk", text)

    def test_installer_prints_rustdesk_id(self):
        text = self.read_installer()

        self.assertIn("rustdesk --get-id", text)
        self.assertIn("RustDesk ID", text)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: FAIL because `install_rustdesk`, `rustdesk --password`, and ID output are absent before this task.

- [ ] **Step 3: Implement RustDesk installation functions**

Insert these functions before `main()`:

```bash
install_rustdesk() {
  if [[ -n "${RUSTDESK_DEB}" ]]; then
    if [[ ! -f "${RUSTDESK_DEB}" ]]; then
      echo "RustDesk deb not found: ${RUSTDESK_DEB}" >&2
      exit 1
    fi
    case "${RUSTDESK_DEB}" in
      *arm64.deb|*aarch64.deb)
        ;;
      *)
        echo "RustDesk deb must be an ARM64 / aarch64 package: ${RUSTDESK_DEB}" >&2
        exit 1
        ;;
    esac
    run apt-get install -y "${RUSTDESK_DEB}"
  elif command -v rustdesk >/dev/null 2>&1; then
    log "RustDesk is already installed."
  else
    echo "RustDesk is not installed. Download the Linux ARM64 .deb from https://github.com/rustdesk/rustdesk/releases and rerun with --deb PATH." >&2
    exit 1
  fi
}

configure_rustdesk() {
  require_command rustdesk
  run systemctl enable rustdesk
  run rustdesk --password "${RUSTDESK_PASSWORD}"
  run systemctl restart rustdesk
}

print_connection_info() {
  local rustdesk_id
  rustdesk_id="$(rustdesk --get-id 2>/dev/null || true)"
  echo "..............................................."
  if [[ -n "${rustdesk_id}" ]]; then
    echo "RustDesk ID: ${rustdesk_id}"
  else
    echo "RustDesk ID: not available yet; check with: rustdesk --get-id"
  fi
  echo "Target user: ${TARGET_USER}"
  echo "Connection scope: same LAN"
  echo "..............................................."
}
```

Then update `main()` after `prompt_password_if_needed`:

```bash
  install_rustdesk
  configure_rustdesk
  print_connection_info
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit RustDesk install behavior**

Run:

```bash
git add scripts/install_rdk_x5_rustdesk_streaming.sh tests/test_install_rdk_x5_rustdesk_streaming.py
git commit -m "完善 RDK X5 RustDesk 安装配置"
```

## Task 4: Add Auto-Login and X11 Configuration

**Files:**
- Modify: `scripts/install_rdk_x5_rustdesk_streaming.sh`
- Modify: `tests/test_install_rdk_x5_rustdesk_streaming.py`

- [ ] **Step 1: Add tests for display manager configuration**

Append these methods to `RustDeskStreamingInstallerTest`:

```python
    def test_installer_configures_autologin_and_x11(self):
        text = self.read_installer()

        self.assertIn("configure_autologin", text)
        self.assertIn("AutomaticLoginEnable=True", text)
        self.assertIn("AutomaticLogin=${TARGET_USER}", text)
        self.assertIn("WaylandEnable=false", text)

    def test_installer_allows_skipping_autologin_and_x11(self):
        text = self.read_installer()

        self.assertIn("CONFIGURE_AUTOLOGIN=0", text)
        self.assertIn("CONFIGURE_X11=0", text)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: FAIL because auto-login and X11 functions are absent before this task.

- [ ] **Step 3: Implement GDM configuration helpers**

Insert these functions before `main()`:

```bash
detect_gdm_config() {
  if [[ -f /etc/gdm3/custom.conf ]]; then
    echo "/etc/gdm3/custom.conf"
  elif [[ -f /etc/gdm/custom.conf ]]; then
    echo "/etc/gdm/custom.conf"
  else
    echo "/etc/gdm3/custom.conf"
  fi
}

ensure_daemon_section() {
  local file="$1"
  if [[ ! -f "${file}" ]]; then
    run install -d -m 0755 "$(dirname "${file}")"
    if [[ "${DRY_RUN}" -eq 0 ]]; then
      printf '[daemon]\n' > "${file}"
    else
      log "Dry run: would create ${file} with [daemon] section"
    fi
  elif ! grep -q '^\[daemon\]' "${file}"; then
    if [[ "${DRY_RUN}" -eq 0 ]]; then
      printf '\n[daemon]\n' >> "${file}"
    else
      log "Dry run: would append [daemon] to ${file}"
    fi
  fi
}

set_gdm_key() {
  local file="$1"
  local key="$2"
  local value="$3"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "Dry run: would set ${key}=${value} in ${file}"
  elif grep -q "^#\\?${key}=" "${file}"; then
    sed -i "s|^#\\?${key}=.*|${key}=${value}|" "${file}"
  else
    sed -i "/^\\[daemon\\]/a ${key}=${value}" "${file}"
  fi
}

configure_autologin() {
  if [[ "${CONFIGURE_AUTOLOGIN}" -eq 0 ]]; then
    log "Skipping auto-login configuration."
    return 0
  fi

  if ! id "${TARGET_USER}" >/dev/null 2>&1; then
    echo "Target user does not exist: ${TARGET_USER}" >&2
    exit 1
  fi

  local gdm_config
  gdm_config="$(detect_gdm_config)"
  ensure_daemon_section "${gdm_config}"
  set_gdm_key "${gdm_config}" "AutomaticLoginEnable" "True"
  set_gdm_key "${gdm_config}" "AutomaticLogin" "${TARGET_USER}"
}

configure_x11_session() {
  if [[ "${CONFIGURE_X11}" -eq 0 ]]; then
    log "Skipping X11 configuration."
    return 0
  fi

  local gdm_config
  gdm_config="$(detect_gdm_config)"
  ensure_daemon_section "${gdm_config}"
  set_gdm_key "${gdm_config}" "WaylandEnable" "false"
}
```

Then update `main()` after `configure_rustdesk`:

```bash
  configure_autologin
  configure_x11_session
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit display manager configuration**

Run:

```bash
git add scripts/install_rdk_x5_rustdesk_streaming.sh tests/test_install_rdk_x5_rustdesk_streaming.py
git commit -m "添加 RDK X5 桌面自动登录配置"
```

## Task 5: Add Documentation and README Links

**Files:**
- Create: `docs/rdk-x5-rustdesk-streaming.md`
- Modify: `README.md`
- Modify: `docs/rdk-x5-deployment.md`
- Modify: `tests/test_install_rdk_x5_rustdesk_streaming.py`

- [ ] **Step 1: Add documentation tests**

Append these methods to `RustDeskStreamingInstallerTest`:

```python
    def test_streaming_docs_are_linked(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        deployment = (REPO_ROOT / "docs" / "rdk-x5-deployment.md").read_text(encoding="utf-8")

        self.assertIn("install_rdk_x5_rustdesk_streaming.sh", readme)
        self.assertIn("rdk-x5-rustdesk-streaming.md", readme)
        self.assertIn("rdk-x5-rustdesk-streaming.md", deployment)

    def test_streaming_doc_mentions_headless_verification(self):
        doc = (REPO_ROOT / "docs" / "rdk-x5-rustdesk-streaming.md").read_text(encoding="utf-8")

        self.assertIn("RustDesk ID", doc)
        self.assertIn("不接显示器", doc)
        self.assertIn("同一局域网", doc)
        self.assertIn("RDKX5-Setup", doc)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: FAIL because `docs/rdk-x5-rustdesk-streaming.md` and README links are absent before this task.

- [ ] **Step 3: Create the user-facing streaming guide**

Create `docs/rdk-x5-rustdesk-streaming.md` with:

```markdown
# RDK X5 RustDesk 桌面串流说明

本文说明如何让 RDK X5 在不接显示器的情况下，通过同一局域网内的 RustDesk 客户端访问完整 Ubuntu 桌面。

## 适用范围

- RDK X5 / Ubuntu 22.04 / ARM64。
- 电脑或手机与 RDK X5 在同一局域网。
- 已完成基础 ROS 2 / MoveIt 部署。
- 已安装或准备安装 `RDKX5-Setup` 热点配网服务。

## 安装

先从 RustDesk 发布页下载 Linux ARM64 `.deb` 包到 RDK X5，然后运行：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --deb /path/to/rustdesk-arm64.deb --password '<现场测试密码>'
```

如果 RustDesk 已经安装，可以省略 `--deb`：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --password '<现场测试密码>'
```

脚本默认配置：

- `sunrise` 用户自动登录桌面。
- GDM 登录屏关闭 Wayland，优先使用 X11。
- RustDesk 服务开机自启动。
- RustDesk 无人值守密码由命令行参数或交互输入提供。

## 验证

```bash
systemctl status rustdesk
rustdesk --get-id
hostname -I
```

记录输出中的 RustDesk ID。电脑或手机连接同一局域网后，打开 RustDesk 客户端，输入该 ID 和部署时设置的密码。

完整无显示器验证流程：

1. 拔掉 HDMI 显示器。
2. 重启 RDK X5。
3. 等待设备自动连接 Wi-Fi。
4. 从电脑 SSH 登录设备，确认设备在线。
5. 使用 RustDesk 连接设备桌面。
6. 打开终端、VS Code、RViz 或 MoveIt smoke test。

## 配网兜底

如果设备开机后没有进入目标 Wi-Fi，现有 `RDKX5-Setup` 热点配网服务会启动。连接热点后打开：

```text
http://192.168.88.1
```

配好 Wi-Fi 后，再回到目标局域网使用 RustDesk。

## 排查

- RustDesk ID 为空：运行 `systemctl restart rustdesk` 后再执行 `rustdesk --get-id`。
- 能 SSH 但看不到桌面：确认 GDM 配置中 `WaylandEnable=false`，并确认 `sunrise` 已自动登录。
- 无显示器时黑屏：先使用 HDMI dummy 插头验证；如果仍失败，再补充 Xorg dummy 配置。
- 手机无法连接：确认手机与 RDK X5 在同一局域网，且 RustDesk ID 和无人值守密码正确。

## 安全说明

测试阶段可以使用固定密码。公开仓库中不要保存真实现场密码。后续外网访问、自建 RustDesk ID/Relay 服务器、机械臂 Web 控制台应单独设计。
```

- [ ] **Step 4: Update README**

Add this paragraph after the Wi-Fi provisioning section in `README.md`:

```markdown
RDK X5 还可以配置同一局域网内的 RustDesk 桌面串流，用于不接显示器时远程打开终端、VS Code 和 RViz：

```bash
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --deb /path/to/rustdesk-arm64.deb --password '<现场测试密码>'
```

说明见 [RDK X5 RustDesk 桌面串流说明](docs/rdk-x5-rustdesk-streaming.md)。
```

- [ ] **Step 5: Update deployment guide**

Add this sentence under the remote-control advice section in `docs/rdk-x5-deployment.md`:

```markdown
如果现场希望 RDK X5 不接显示器也能查看完整桌面，可参考 [RDK X5 RustDesk 桌面串流说明](rdk-x5-rustdesk-streaming.md) 配置同一局域网 RustDesk 访问。
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```bash
python -m unittest tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit documentation**

Run:

```bash
git add README.md docs/rdk-x5-deployment.md docs/rdk-x5-rustdesk-streaming.md tests/test_install_rdk_x5_rustdesk_streaming.py
git commit -m "补充 RDK X5 RustDesk 串流文档"
```

## Task 6: Full Local Verification and Device Handoff

**Files:**
- Modify only if verification exposes a defect:
  - `scripts/install_rdk_x5_rustdesk_streaming.sh`
  - `tests/test_install_rdk_x5_rustdesk_streaming.py`
  - `docs/rdk-x5-rustdesk-streaming.md`

- [ ] **Step 1: Run all local tests**

Run:

```bash
python -m unittest tests/test_deploy_rdk_x5_script.py tests/test_install_rdk_x5_wifi_provisioning.py tests/test_rdkx5_wifi_provision.py tests/test_install_rdk_x5_rustdesk_streaming.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Check the installer help**

Run:

```bash
bash scripts/install_rdk_x5_rustdesk_streaming.sh --help
```

Expected: help output lists `--password`, `--deb`, `--user`, `--no-autologin`, `--no-x11-config`, and `--dry-run`.

- [ ] **Step 3: Check dry-run output**

Run:

```bash
bash scripts/install_rdk_x5_rustdesk_streaming.sh --dry-run --password test-pass
```

Expected: output includes:

```text
[rdkx5-rustdesk] Target user: sunrise
[rdkx5-rustdesk] Dry run only; no system changes will be made.
```

- [ ] **Step 4: Confirm no sensitive password is committed**

Run:

```bash
rg -n "RUSTDESK_PASSWORD=['\"][0-9]{8,}|--password ['\"][0-9]{8,}" scripts docs tests README.md
```

Expected: no real site password appears. The literal placeholder `现场测试密码` may appear in docs; real numeric passwords must not.

- [ ] **Step 5: Check git status**

Run:

```bash
git status --short
```

Expected: clean working tree after commits.

- [ ] **Step 6: Prepare device-side command for user terminal**

Use this command template after copying or pulling the branch on RDK X5:

```bash
cd /home/sunrise/桌面/ws_moveit/6_axis_robotic_arm
sudo ./scripts/install_rdk_x5_rustdesk_streaming.sh --password '<现场测试密码>'
systemctl status rustdesk --no-pager
rustdesk --get-id
```

Expected: RustDesk service is active or restartable, and RustDesk ID is printed.

## Self-Review Checklist

- Spec coverage:
  - Same-LAN RustDesk desktop streaming is covered by Tasks 2 and 3.
  - Auto-login and X11 are covered by Task 4.
  - Password safety is covered by Tasks 1, 2, and 6.
  - Documentation and user verification are covered by Tasks 5 and 6.
  - Wi-Fi provisioning remains a separate fallback and is documented in Task 5.
- Placeholder scan:
  - The plan uses concrete commands and code blocks rather than unresolved markers.
  - Every code-changing task includes concrete code or concrete file text.
- Scope check:
  - Public network access, self-hosted RustDesk server, Web control panels, and robot motion safety remain outside this implementation plan.
