import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_rdk_x5_rustdesk_streaming.sh"


def bash_path(path):
    if path.drive:
        drive = path.drive.rstrip(":").lower()
        parts = [part for part in path.parts[1:] if part not in ("\\", "/")]
        return "/mnt/" + drive + "/" + "/".join(parts)
    return str(path)


class RustDeskStreamingInstallerTest(unittest.TestCase):
    def read_installer(self):
        return INSTALLER.read_text(encoding="utf-8")

    def test_installer_file_exists(self):
        self.assertTrue(INSTALLER.exists())

    def test_help_mentions_supported_options(self):
        result = subprocess.run(
            ["bash", bash_path(INSTALLER), "--help"],
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
            ["bash", bash_path(INSTALLER), "--dry-run", "--password", "test-pass"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertIn("[rdkx5-rustdesk] Dry run", result.stdout)
        self.assertIn("Target user: sunrise", result.stdout)

    def test_options_reject_missing_value_before_next_option(self):
        for option in ("--password", "--user", "--deb"):
            with self.subTest(option=option):
                result = subprocess.run(
                    ["bash", bash_path(INSTALLER), option, "--dry-run"],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                self.assertEqual(2, result.returncode)
                self.assertIn(option, result.stderr)
                self.assertIn("requires a non-option value", result.stderr)


if __name__ == "__main__":
    unittest.main()
