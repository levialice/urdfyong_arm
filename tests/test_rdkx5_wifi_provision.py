import importlib.util
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "rdkx5_wifi_provision.py"

spec = importlib.util.spec_from_file_location("rdkx5_wifi_provision", MODULE_PATH)
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or []
        self.calls = []

    def __call__(self, args, timeout=10, check=False):
        self.calls.append((args, timeout, check))
        if self.outputs:
            return self.outputs.pop(0)
        return ""


class FailingConnectRunner(FakeRunner):
    def __call__(self, args, timeout=10, check=False):
        self.calls.append((args, timeout, check))
        if args[:4] == ["nmcli", "device", "wifi", "connect"]:
            raise subprocess.CalledProcessError(10, args, stderr="Secrets were required, but not provided")
        return ""


class NmcliHelperTest(unittest.TestCase):
    def test_connect_wifi_passes_ssid_and_password_as_args(self):
        runner = FakeRunner([""])
        nm = provision.Nmcli(runner=runner)

        nm.connect_wifi("Lab WiFi", "pw with spaces")

        self.assertEqual(
            runner.calls[0][0],
            ["nmcli", "device", "wifi", "connect", "Lab WiFi", "password", "pw with spaces"],
        )

    def test_connected_wifi_detects_connected_wireless_device(self):
        runner = FakeRunner(["wlan0:wifi:connected:levi\neth0:ethernet:unavailable:\n"])
        nm = provision.Nmcli(runner=runner)

        self.assertTrue(nm.has_connected_wifi("wlan0"))


class WebRenderingTest(unittest.TestCase):
    def test_render_index_contains_setup_address_and_form(self):
        html = provision.render_index([{"ssid": "levi", "signal": "90", "security": "WPA2"}], "")

        self.assertIn("RDKX5-Setup", html)
        self.assertIn("192.168.88.1", html)
        self.assertIn('name="ssid"', html)
        self.assertIn('name="password"', html)
        self.assertIn("/scan", html)

    def test_parse_wifi_list_ignores_blank_ssids(self):
        rows = provision.parse_wifi_list("levi:90:WPA2\n:80:WPA2\nGuest:50:\n")

        self.assertEqual([row["ssid"] for row in rows], ["levi", "Guest"])

    def test_load_networks_rescans_before_listing(self):
        runner = FakeRunner(["", "levi:90:WPA2\nGuest:60:\n"])
        nm = provision.Nmcli(runner=runner)

        rows = provision.load_networks(nm)

        self.assertEqual([row["ssid"] for row in rows], ["levi", "Guest"])
        self.assertEqual(runner.calls[0][0], ["nmcli", "device", "wifi", "rescan"])
        self.assertEqual(
            runner.calls[1][0],
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
        )

    def test_render_index_says_manual_ssid_is_supported_when_no_scan_results(self):
        html = provision.render_index([], "热点已启动")

        self.assertIn("手动输入", html)
        self.assertIn("刷新 Wi-Fi 列表", html)


class StatusCacheTest(unittest.TestCase):
    def test_connection_status_keeps_cached_networks(self):
        status = provision.ConnectionStatus()

        self.assertEqual(status.get_networks(), [])
        status.set_networks([{"ssid": "levi", "signal": "80", "security": "WPA2"}])

        self.assertEqual(status.get_networks()[0]["ssid"], "levi")


class BootBehaviorTest(unittest.TestCase):
    def test_does_not_start_hotspot_when_wifi_is_connected(self):
        runner = FakeRunner(["wlan0:wifi:connected:levi\n"])
        nm = provision.Nmcli(runner=runner)

        result = provision.ensure_provisioning_mode(nm, iface="wlan0", wait_seconds=0)

        self.assertEqual(result, "connected")
        self.assertFalse(any("RDKX5-Setup" in " ".join(call[0]) for call in runner.calls))

    def test_starts_open_hotspot_when_wifi_is_not_connected(self):
        runner = FakeRunner(["wlan0:wifi:disconnected:\n", "", "", "", "", "", ""])
        nm = provision.Nmcli(runner=runner)

        result = provision.ensure_provisioning_mode(nm, iface="wlan0", wait_seconds=0)

        self.assertEqual(result, "hotspot")
        commands = [" ".join(call[0]) for call in runner.calls]
        self.assertTrue(any("con add type wifi" in cmd and "RDKX5-Setup" in cmd for cmd in commands))
        self.assertTrue(any("ipv4.addresses 192.168.88.1/24" in cmd for cmd in commands))


class ConnectFormTest(unittest.TestCase):
    def test_run_connect_job_stops_hotspot_before_connecting(self):
        runner = FakeRunner(["", "", "wlan0:wifi:connected:Lab WiFi\n"])
        nm = provision.Nmcli(runner=runner)
        status = provision.ConnectionStatus()

        provision.run_connect_job(nm, "Lab WiFi", "secret pw", status, iface="wlan0")

        self.assertIn("Connected to Lab WiFi", status.get())
        self.assertEqual(runner.calls[0][0], ["nmcli", "con", "down", "RDKX5-Setup"])
        self.assertEqual(
            runner.calls[1][0],
            ["nmcli", "device", "wifi", "connect", "Lab WiFi", "password", "secret pw"],
        )

    def test_run_connect_job_restores_hotspot_when_connect_fails(self):
        runner = FailingConnectRunner()
        nm = provision.Nmcli(runner=runner)
        status = provision.ConnectionStatus()

        provision.run_connect_job(nm, "Lab WiFi", "bad pw", status, iface="wlan0", retry_delay=0)

        commands = [" ".join(call[0]) for call in runner.calls]
        self.assertIn("Failed to connect to Lab WiFi", status.get())
        self.assertTrue(any(cmd == "nmcli con down RDKX5-Setup" for cmd in commands))
        self.assertTrue(any("nmcli con up RDKX5-Setup" in cmd for cmd in commands))

    def test_start_connect_job_returns_before_switching_networks(self):
        runner = FakeRunner()
        nm = provision.Nmcli(runner=runner)
        status = provision.ConnectionStatus()
        scheduled = []

        success, message = provision.start_connect_job(
            nm,
            b"ssid=Lab+WiFi&password=secret+pw",
            status,
            starter=lambda target, args: scheduled.append((target, args)),
        )

        self.assertTrue(success)
        self.assertIn("Connecting to Lab WiFi", message)
        self.assertEqual(runner.calls, [])
        self.assertEqual(len(scheduled), 1)

    def test_connect_from_form_rejects_missing_ssid(self):
        runner = FakeRunner()
        nm = provision.Nmcli(runner=runner)
        status = provision.ConnectionStatus()

        success, message = provision.start_connect_job(nm, b"password=secret", status)

        self.assertFalse(success)
        self.assertIn("SSID", message)
        self.assertEqual(runner.calls, [])


class CliDefaultsTest(unittest.TestCase):
    def test_arg_parser_defaults_match_design(self):
        parser = provision.build_arg_parser()
        args = parser.parse_args(["--serve"])

        self.assertTrue(args.serve)
        self.assertEqual(args.iface, "wlan0")
        self.assertEqual(args.wait_seconds, 30)
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 80)


if __name__ == "__main__":
    unittest.main()
