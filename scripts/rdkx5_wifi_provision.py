#!/usr/bin/env python3
import argparse
import re
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import threading
import time
import urllib.parse


HOTSPOT_SSID = "RDKX5-Setup"
HOTSPOT_IP = "192.168.88.1"
HOTSPOT_CIDR = "192.168.88.1/24"
WIFI_INTERFACE = "wlan0"
WIFI_WAIT_SECONDS = 30


def run_command(args, timeout=10, check=False):
    result = subprocess.run(
        args,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def wifi_connection_name(ssid):
    safe_ssid = re.sub(r"[^A-Za-z0-9_.-]+", "_", ssid).strip("_")
    if not safe_ssid:
        safe_ssid = "network"
    return f"RDKX5-WiFi-{safe_ssid[:48]}"


class Nmcli:
    def __init__(self, runner=run_command):
        self.runner = runner

    def has_connected_wifi(self, iface=WIFI_INTERFACE):
        output = self.runner(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            timeout=10,
        )
        for line in output.splitlines():
            parts = line.split(":", 3)
            if len(parts) >= 3 and parts[0] == iface and parts[1] == "wifi":
                return parts[2] == "connected"
        return False

    def connect_wifi(self, ssid, password, iface=WIFI_INTERFACE):
        connection_name = wifi_connection_name(ssid)
        args = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            args.extend(["password", password])
        args.extend(["ifname", iface, "name", connection_name])
        self.runner(args, timeout=45, check=True)
        self.runner(
            [
                "nmcli",
                "con",
                "modify",
                connection_name,
                "connection.autoconnect",
                "yes",
                "connection.permissions",
                "",
            ],
            timeout=20,
            check=True,
        )

    def rescan_wifi(self):
        self.runner(["nmcli", "device", "wifi", "rescan"], timeout=20, check=False)

    def list_wifi(self):
        return self.runner(
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            timeout=20,
        )

    def _hotspot_profile_exists(self):
        output = self.runner(["nmcli", "-t", "-f", "NAME,UUID", "con", "show"], timeout=10, check=False)
        uuids = []
        for line in output.splitlines():
            name, _, uuid = line.partition(":")
            if name == HOTSPOT_SSID and uuid:
                uuids.append(uuid)
        for uuid in uuids[1:]:
            self.runner(["nmcli", "con", "delete", "uuid", uuid], timeout=20, check=False)
        return bool(uuids)

    def start_hotspot(self, iface=WIFI_INTERFACE):
        commands = []
        if not self._hotspot_profile_exists():
            commands.append(
                ["nmcli", "con", "add", "type", "wifi", "ifname", iface, "con-name", HOTSPOT_SSID, "autoconnect", "no", "ssid", HOTSPOT_SSID]
            )
        commands.extend([
            ["nmcli", "con", "modify", HOTSPOT_SSID, "802-11-wireless.mode", "ap"],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "802-11-wireless.band", "bg"],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "ipv4.method", "shared", "ipv4.addresses", HOTSPOT_CIDR],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "ipv6.method", "ignore"],
            ["nmcli", "con", "up", HOTSPOT_SSID],
        ])
        for command in commands:
            self.runner(command, timeout=20, check=False)
        active = self.runner(["nmcli", "-t", "-f", "NAME", "con", "show", "--active"], timeout=10, check=False)
        if HOTSPOT_SSID not in active.splitlines():
            raise RuntimeError(f"{HOTSPOT_SSID} hotspot did not become active")

    def stop_hotspot(self):
        self.runner(["nmcli", "con", "down", HOTSPOT_SSID], timeout=20, check=False)


class ConnectionStatus:
    def __init__(self):
        self._message = ""
        self._networks = []
        self._lock = threading.Lock()

    def set(self, message):
        with self._lock:
            self._message = message

    def get(self):
        with self._lock:
            return self._message

    def set_networks(self, networks):
        with self._lock:
            self._networks = list(networks)

    def get_networks(self):
        with self._lock:
            return list(self._networks)


def ensure_provisioning_mode(nmcli, iface=WIFI_INTERFACE, wait_seconds=WIFI_WAIT_SECONDS):
    deadline = time.monotonic() + wait_seconds
    while True:
        if nmcli.has_connected_wifi(iface):
            return "connected"
        if time.monotonic() >= deadline:
            break
        time.sleep(1)
    nmcli.start_hotspot(iface)
    return "hotspot"


def parse_wifi_list(output):
    networks = []
    seen = set()
    for line in output.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        ssid, signal, security = parts
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({"ssid": ssid, "signal": signal, "security": security})
    return networks


def load_networks(nmcli):
    nmcli.rescan_wifi()
    return parse_wifi_list(nmcli.list_wifi())


def render_index(networks, message):
    options = "\n".join(
        f'<option value="{html.escape(row["ssid"], quote=True)}">'
        for row in networks
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['ssid'])}</td>"
        f"<td>{html.escape(row['signal'])}</td>"
        f"<td>{html.escape(row['security'] or 'Open')}</td>"
        "</tr>"
        for row in networks
    )
    escaped_message = html.escape(message)
    if rows:
        network_table = rows
    else:
        network_table = '<tr><td colspan="3">暂无扫描结果，可先手动输入 SSID，或点击“刷新 Wi-Fi 列表”。</td></tr>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RDK X5 Wi-Fi 配网</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 32px auto; padding: 0 16px; }}
    label {{ display: block; margin-top: 16px; font-weight: 600; }}
    input, button {{ box-sizing: border-box; width: 100%; padding: 10px; margin-top: 6px; font-size: 16px; }}
    a.button {{ display: block; box-sizing: border-box; width: 100%; padding: 10px; margin-top: 12px; border: 1px solid #999; text-align: center; color: #111; text-decoration: none; }}
    button {{ cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; }}
    .message {{ margin: 16px 0; padding: 10px; background: #eef6ff; }}
  </style>
</head>
<body>
  <h1>RDK X5 Wi-Fi 配网</h1>
  <p>当前已连接设备热点 <strong>{HOTSPOT_SSID}</strong>，配网页面地址 <strong>http://{HOTSPOT_IP}</strong>。</p>
  <p>如果列表没有目标 Wi-Fi，可以直接手动输入 SSID 和密码。</p>
  <p class="message">{escaped_message}</p>
  <a class="button" href="/scan">刷新 Wi-Fi 列表</a>
  <form method="post" action="/connect">
    <label for="ssid">Wi-Fi 名称 / SSID</label>
    <input id="ssid" name="ssid" list="wifi-list" required>
    <datalist id="wifi-list">
      {options}
    </datalist>
    <label for="password">Wi-Fi 密码</label>
    <input id="password" name="password" type="password">
    <button type="submit">连接 Wi-Fi</button>
  </form>
  <table>
    <thead><tr><th>SSID</th><th>信号</th><th>加密</th></tr></thead>
    <tbody>{network_table}</tbody>
  </table>
</body>
</html>
"""


def parse_connect_form(body):
    form = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    ssid = form.get("ssid", [""])[0].strip()
    password = form.get("password", [""])[0]
    return ssid, password


def _command_error_detail(exc):
    return (exc.stderr or exc.stdout or str(exc)).strip()


def run_connect_job(nmcli, ssid, password, status, iface=WIFI_INTERFACE, retry_delay=1):
    status.set(f"Connecting to {ssid}. The setup hotspot may disconnect briefly.")
    try:
        nmcli.stop_hotspot()
        time.sleep(retry_delay)
        nmcli.connect_wifi(ssid, password, iface=iface)
        if nmcli.has_connected_wifi(iface):
            status.set(f"Connected to {ssid}. Switch your computer back to that network.")
        else:
            status.set(f"Connection command finished, but {iface} is not connected. Restoring setup hotspot.")
            nmcli.start_hotspot(iface)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = _command_error_detail(exc)
        status.set(f"Failed to connect to {ssid}: {detail}. Restoring setup hotspot.")
        nmcli.start_hotspot(iface)


def start_connect_job(nmcli, body, status, iface=WIFI_INTERFACE, starter=None):
    ssid, password = parse_connect_form(body)
    if not ssid:
        return False, "SSID is required."
    message = f"Connecting to {ssid}. The setup hotspot may disconnect. If it fails, reconnect to {HOTSPOT_SSID} and reload this page."
    status.set(message)
    args = (nmcli, ssid, password, status, iface)
    if starter is None:
        thread = threading.Thread(target=run_connect_job, args=args, daemon=True)
        thread.start()
    else:
        starter(run_connect_job, args)
    return True, message


def make_handler(nmcli):
    status = ConnectionStatus()

    class ProvisionHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/scan":
                try:
                    status.set_networks(load_networks(nmcli))
                    self._send_page("扫描完成。若没有目标 Wi-Fi，请手动输入 SSID。")
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    self._send_page(f"扫描失败：{_command_error_detail(exc)}。请手动输入 SSID。")
                return
            self._send_page(status.get())

        def do_POST(self):
            if self.path != "/connect":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            _success, message = start_connect_job(nmcli, body, status)
            self._send_page(message)

        def _send_page(self, message):
            networks = status.get_networks()
            body = render_index(networks, message).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                print("Client disconnected before response completed.", flush=True)

        def log_message(self, fmt, *args):
            print(f"{self.address_string()} - {fmt % args}")

    return ProvisionHandler


def serve(nmcli, host="0.0.0.0", port=80):
    server = HTTPServer((host, port), make_handler(nmcli))
    print(f"RDK X5 Wi-Fi provisioning page: http://{HOTSPOT_IP}")
    server.serve_forever()


def build_arg_parser():
    parser = argparse.ArgumentParser(description="RDK X5 Wi-Fi provisioning service")
    parser.add_argument("--serve", action="store_true", help="wait for Wi-Fi, then serve provisioning page if needed")
    parser.add_argument("--iface", default=WIFI_INTERFACE, help="Wi-Fi interface to manage")
    parser.add_argument("--wait-seconds", type=int, default=WIFI_WAIT_SECONDS, help="seconds to wait for saved Wi-Fi")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP listen host")
    parser.add_argument("--port", type=int, default=80, help="HTTP listen port")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    nmcli = Nmcli()
    if not args.serve:
        parser.print_help()
        return 2
    mode = ensure_provisioning_mode(nmcli, iface=args.iface, wait_seconds=args.wait_seconds)
    if mode == "connected":
        print("Wi-Fi is already connected; provisioning hotspot not started.")
        return 0
    serve(nmcli, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
