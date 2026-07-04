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


def run_bash_installer(*args, check=True):
    try:
        result = subprocess.run(
            ["bash", bash_path(INSTALLER), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise unittest.SkipTest("bash is not available") from exc

    output = (result.stdout or "") + (result.stderr or "")
    normalized_output = output.replace("\x00", "")
    if "E_ACCESSDENIED" in normalized_output or "CreateInstance" in normalized_output:
        raise unittest.SkipTest("bash/WSL is not available in this environment")

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )

    return result


class RustDeskStreamingInstallerTest(unittest.TestCase):
    def read_installer(self):
        return INSTALLER.read_text(encoding="utf-8")

    def test_installer_file_exists(self):
        self.assertTrue(INSTALLER.exists())

    def test_help_mentions_supported_options(self):
        result = run_bash_installer("--help")

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
        result = run_bash_installer("--dry-run", "--password", "test-pass")

        self.assertIn("[rdkx5-rustdesk] Dry run", result.stdout)
        self.assertIn("Target user: sunrise", result.stdout)

    def test_options_reject_missing_value_before_next_option(self):
        for option in ("--password", "--user", "--deb"):
            with self.subTest(option=option):
                result = run_bash_installer(option, "--dry-run", check=False)

                self.assertEqual(2, result.returncode)
                self.assertIn(option, result.stderr)
                self.assertIn("requires a non-option value", result.stderr)

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


if __name__ == "__main__":
    unittest.main()
