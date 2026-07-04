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
