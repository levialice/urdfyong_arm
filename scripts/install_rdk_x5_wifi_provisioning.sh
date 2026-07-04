#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/rdkx5-wifi-provision"
SERVICE_NAME="rdkx5-wifi-provision.service"
HOTSPOT_SSID="RDKX5-Setup"
HOTSPOT_IP="192.168.88.1"
START_NOW=0

usage() {
  cat <<USAGE
Usage: sudo ./scripts/install_rdk_x5_wifi_provisioning.sh [--start-now]

Installs the RDK X5 Wi-Fi provisioning service.

Defaults:
  open hotspot SSID: ${HOTSPOT_SSID}
  provisioning page: http://${HOTSPOT_IP}
  boot Wi-Fi wait:   30 seconds

Options:
  --start-now   Start the service immediately after installation.
  -h, --help    Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-now)
      START_NOW=1
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

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command python3
require_command nmcli
require_command systemctl
require_command install

if ! systemctl is-enabled NetworkManager.service >/dev/null 2>&1 && \
   ! systemctl is-active NetworkManager.service >/dev/null 2>&1; then
  echo "NetworkManager.service is not enabled or active; enable it before using this installer." >&2
  exit 1
fi

echo "[rdkx5-wifi-provision] Installing files"
install -d -m 0755 "${INSTALL_DIR}"
install -m 0755 "${REPO_ROOT}/scripts/rdkx5_wifi_provision.py" "${INSTALL_DIR}/rdkx5_wifi_provision.py"
install -m 0644 "${REPO_ROOT}/systemd/${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"

echo "[rdkx5-wifi-provision] Enabling ${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable rdkx5-wifi-provision.service

if [[ "${START_NOW}" -eq 1 ]]; then
  echo "[rdkx5-wifi-provision] Starting ${SERVICE_NAME}"
  systemctl restart "${SERVICE_NAME}"
fi

cat <<DONE
[rdkx5-wifi-provision] Installed.

On next boot, if saved Wi-Fi does not connect within 30 seconds:
  1. Connect your computer to the open hotspot: ${HOTSPOT_SSID}
  2. Open: http://${HOTSPOT_IP}
  3. Select target Wi-Fi and submit the password.

Status commands:
  systemctl status ${SERVICE_NAME}
  journalctl -u ${SERVICE_NAME} -f
DONE
