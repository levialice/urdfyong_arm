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

require_option_value() {
  local option="$1"
  local value="${2-}"

  if [[ -z "${value}" || "${value}" == -* ]]; then
    echo "Option ${option} requires a non-option value." >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)
      require_option_value "$1" "${2-}"
      RUSTDESK_PASSWORD="$2"
      shift
      ;;
    --deb)
      require_option_value "$1" "${2-}"
      RUSTDESK_DEB="$2"
      shift
      ;;
    --user)
      require_option_value "$1" "${2-}"
      TARGET_USER="$2"
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

validate_target_user_name() {
  if [[ ! "${TARGET_USER}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]]; then
    echo "Invalid target user name: ${TARGET_USER}" >&2
    exit 1
  fi
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

install_rustdesk() {
  if command -v rustdesk >/dev/null 2>&1; then
    log "RustDesk is already installed."
    return 0
  fi

  if [[ -n "${RUSTDESK_DEB}" ]]; then
    local deb_path
    local deb_arch
    if [[ ! -f "${RUSTDESK_DEB}" ]]; then
      echo "RustDesk deb not found: ${RUSTDESK_DEB}" >&2
      exit 1
    fi
    case "${RUSTDESK_DEB}" in
      *arm64.deb|*aarch64.deb)
        ;;
      *)
        echo "RustDesk deb filename should look like an ARM64 / aarch64 package; verifying metadata: ${RUSTDESK_DEB}" >&2
        ;;
    esac
    deb_path="$(realpath "${RUSTDESK_DEB}")"
    deb_arch="$(dpkg-deb -f "${deb_path}" Architecture 2>/dev/null || true)"
    if [[ "${deb_arch}" != "arm64" ]]; then
      echo "RustDesk deb architecture must be arm64; got: ${deb_arch:-unknown}" >&2
      exit 1
    fi
    run apt-get install -y "${deb_path}"
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
      install -m 0644 /dev/null "${file}"
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
  else
    python3 - "${file}" "${key}" "${value}" <<'PY'
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
target_key = sys.argv[2]
target_value = sys.argv[3]

existing_stat = path.stat() if path.exists() else None
lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
section_re = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[#;].*)?$")
key_re = re.compile(rf"^\s*#?\s*{re.escape(target_key)}\s*=")

daemon_start = None
daemon_end = len(lines)
current_section = None
for index, line in enumerate(lines):
    match = section_re.match(line.rstrip("\r\n"))
    if not match:
        continue

    if current_section == "daemon" and daemon_end == len(lines):
        daemon_end = index

    current_section = match.group(1).strip()
    if current_section == "daemon" and daemon_start is None:
        daemon_start = index
        daemon_end = len(lines)

if daemon_start is None:
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] = lines[-1] + "\n"
    if lines and lines[-1].strip():
        lines.append("\n")
    lines.extend(["[daemon]\n", f"{target_key}={target_value}\n"])
else:
    rewritten = []
    for index, line in enumerate(lines):
        if index == daemon_end:
            rewritten.append(f"{target_key}={target_value}\n")
        if daemon_start < index < daemon_end and key_re.match(line.rstrip("\r\n")):
            continue
        rewritten.append(line)
    if daemon_end == len(lines):
        rewritten.append(f"{target_key}={target_value}\n")
    lines = rewritten

fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as tmp:
        tmp.writelines(lines)
    if existing_stat is None:
        os.chmod(tmp_name, 0o644)
    else:
        os.chmod(tmp_name, stat.S_IMODE(existing_stat.st_mode))
        try:
            os.chown(tmp_name, existing_stat.st_uid, existing_stat.st_gid)
        except (AttributeError, PermissionError):
            pass
    os.replace(tmp_name, path)
except Exception:
    try:
        os.unlink(tmp_name)
    finally:
        raise
PY
  fi
}

configure_autologin() {
  if [[ "${CONFIGURE_AUTOLOGIN}" -eq 0 ]]; then
    log "Skipping auto-login configuration."
    return 0
  fi

  validate_target_user_name

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

main() {
  validate_target_user_name
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
  require_command realpath
  require_command dpkg-deb
  require_command python3
  prompt_password_if_needed

  install_rustdesk
  configure_rustdesk
  configure_autologin
  configure_x11_session
  print_connection_info

  log "Safety checks passed."
}

if [[ "${RDKX5_RUSTDESK_INSTALLER_TESTING:-0}" != 1 ]]; then
  main "$@"
fi
