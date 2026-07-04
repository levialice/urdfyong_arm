import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_rdk_x5_wifi_provisioning.sh"
UNIT = REPO_ROOT / "systemd" / "rdkx5-wifi-provision.service"


class WifiProvisionInstallerTest(unittest.TestCase):
    def test_installer_copies_script_and_enables_service(self):
        text = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("/opt/rdkx5-wifi-provision", text)
        self.assertIn("rdkx5_wifi_provision.py", text)
        self.assertIn("systemctl enable rdkx5-wifi-provision.service", text)

    def test_installer_mentions_open_hotspot_defaults(self):
        text = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("RDKX5-Setup", text)
        self.assertIn("192.168.88.1", text)
        self.assertIn("open hotspot", text)

    def test_systemd_unit_runs_after_network_manager(self):
        text = UNIT.read_text(encoding="utf-8")

        self.assertIn("After=NetworkManager.service", text)
        self.assertIn(
            "ExecStart=/usr/bin/python3 /opt/rdkx5-wifi-provision/rdkx5_wifi_provision.py --serve",
            text,
        )
        self.assertIn("Restart=on-failure", text)


if __name__ == "__main__":
    unittest.main()
