#!/usr/bin/env python3
import argparse
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
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

    def connect_wifi(self, ssid, password):
        args = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            args.extend(["password", password])
        self.runner(args, timeout=45, check=True)

    def rescan_wifi(self):
        self.runner(["nmcli", "device", "wifi", "rescan"], timeout=20, check=False)

    def list_wifi(self):
        return self.runner(
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
            timeout=20,
        )

    def start_hotspot(self, iface=WIFI_INTERFACE):
        commands = [
            ["nmcli", "con", "add", "type", "wifi", "ifname", iface, "con-name", HOTSPOT_SSID, "autoconnect", "no", "ssid", HOTSPOT_SSID],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "802-11-wireless.mode", "ap"],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "802-11-wireless.band", "bg"],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "ipv4.method", "shared", "ipv4.addresses", HOTSPOT_CIDR],
            ["nmcli", "con", "modify", HOTSPOT_SSID, "ipv6.method", "ignore"],
            ["nmcli", "con", "up", HOTSPOT_SSID],
        ]
        for command in commands:
            self.runner(command, timeout=20, check=False)

    def stop_hotspot(self):
        self.runner(["nmcli", "con", "down", HOTSPOT_SSID], timeout=20, check=False)


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
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RDK X5 Wi-Fi Setup</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 32px auto; padding: 0 16px; }}
    label {{ display: block; margin-top: 16px; font-weight: 600; }}
    input, button {{ box-sizing: border-box; width: 100%; padding: 10px; margin-top: 6px; font-size: 16px; }}
    button {{ cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; }}
    .message {{ margin: 16px 0; padding: 10px; background: #eef6ff; }}
  </style>
</head>
<body>
  <h1>RDK X5 Wi-Fi Setup</h1>
  <p>Connect to hotspot <strong>{HOTSPOT_SSID}</strong>, then open <strong>http://{HOTSPOT_IP}</strong>.</p>
  <p class="message">{escaped_message}</p>
  <form method="post" action="/connect">
    <label for="ssid">Wi-Fi SSID</label>
    <input id="ssid" name="ssid" list="wifi-list" required>
    <datalist id="wifi-list">
      {options}
    </datalist>
    <label for="password">Wi-Fi Password</label>
    <input id="password" name="password" type="password">
    <button type="submit">Connect</button>
  </form>
  <table>
    <thead><tr><th>SSID</th><th>Signal</th><th>Security</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def connect_from_form(nmcli, body):
    form = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    ssid = form.get("ssid", [""])[0].strip()
    password = form.get("password", [""])[0]
    if not ssid:
        return False, "SSID is required."
    try:
        nmcli.connect_wifi(ssid, password)
        nmcli.stop_hotspot()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, f"Failed to connect to {ssid}: {detail}"
    return True, f"Connected to {ssid}. Switch your computer back to that network."


def make_handler(nmcli):
    class ProvisionHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._send_page("")

        def do_POST(self):
            if self.path != "/connect":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            _success, message = connect_from_form(nmcli, body)
            self._send_page(message)

        def _send_page(self, message):
            networks = load_networks(nmcli)
            body = render_index(networks, message).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
