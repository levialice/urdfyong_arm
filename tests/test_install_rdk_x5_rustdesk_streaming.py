import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "scripts" / "install_rdk_x5_rustdesk_streaming.sh"
_BASH_AVAILABLE = None


def bash_path(path):
    if path.drive:
        drive = path.drive.rstrip(":").lower()
        parts = [part for part in path.parts[1:] if part not in ("\\", "/")]
        return "/mnt/" + drive + "/" + "/".join(parts)
    return str(path)


def require_bash_available():
    global _BASH_AVAILABLE
    if _BASH_AVAILABLE is not None:
        if not _BASH_AVAILABLE:
            raise unittest.SkipTest("bash/WSL is not available in this environment")
        return

    try:
        result = subprocess.run(
            ["bash", "-lc", "true"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            errors="replace",
        )
    except FileNotFoundError as exc:
        _BASH_AVAILABLE = False
        raise unittest.SkipTest("bash is not available") from exc

    if result.returncode != 0:
        _BASH_AVAILABLE = False
        raise unittest.SkipTest("bash/WSL is not available in this environment")

    _BASH_AVAILABLE = True


def run_bash_installer(*args, check=True):
    require_bash_available()
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


def run_bash_script(script, check=True):
    if os.name == "nt":
        raise unittest.SkipTest("bash behavior tests require a Unix shell")

    require_bash_available()
    try:
        result = subprocess.run(
            ["bash", "-lc", script],
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
        self.assertIn('realpath "${RUSTDESK_DEB}"', text)
        self.assertIn('apt-get install -y "${deb_path}"', text)
        self.assertNotIn('apt-get install -y "${RUSTDESK_DEB}"', text)
        self.assertIn("rustdesk --password", text)
        self.assertIn("systemctl restart rustdesk", text)

    def test_installer_checks_existing_rustdesk_before_deb_install(self):
        text = self.read_installer()

        self.assertNotIn("elif command -v rustdesk", text)
        installed_check = text.index("if command -v rustdesk")
        deb_check = text.index('if [[ -n "${RUSTDESK_DEB}" ]]')
        deb_install = text.index('apt-get install -y "${deb_path}"')

        self.assertLess(installed_check, deb_check)
        self.assertLess(installed_check, deb_install)

    def test_installer_prints_rustdesk_id(self):
        text = self.read_installer()

        self.assertIn("print_connection_info", text)
        self.assertIn("rustdesk --get-id", text)
        self.assertIn("RustDesk ID", text)
        self.assertIn("Target user", text)
        self.assertIn("same LAN", text)

    def test_installer_configures_autologin_and_x11(self):
        text = self.read_installer()

        self.assertIn("configure_autologin", text)
        self.assertIn("AutomaticLoginEnable", text)
        self.assertIn("AutomaticLogin", text)
        self.assertIn("WaylandEnable", text)
        self.assertIn("false", text)

    def test_installer_allows_skipping_autologin_and_x11(self):
        text = self.read_installer()

        self.assertIn("CONFIGURE_AUTOLOGIN=0", text)
        self.assertIn("CONFIGURE_X11=0", text)

    def test_installer_validates_target_user_before_installing_rustdesk(self):
        text = self.read_installer()

        self.assertIn("validate_target_user_name", text)
        self.assertIn("^[a-z_][a-z0-9_-]*[$]?$", text)
        self.assertIn("Invalid target user name", text)

        validation_call = text.index("validate_target_user_name")
        main_body = text.index("main()")
        target_user_log = text.index('log "Target user: ${TARGET_USER}"', main_body)
        install_call = text.index("install_rustdesk", main_body)
        validation_in_main = text.index("validate_target_user_name", main_body)

        self.assertLess(validation_in_main, target_user_log)
        self.assertLess(validation_in_main, install_call)
        self.assertGreater(validation_in_main, validation_call)

    def test_gdm_key_updates_are_section_scoped_without_sed_replacement(self):
        text = self.read_installer()

        self.assertNotIn("sed -i", text)
        self.assertNotIn('grep -q "^#\\\\?${key}="', text)
        self.assertIn("[daemon]", text)
        self.assertIn("current_section", text)
        self.assertIn("os.replace", text)

    def test_set_gdm_key_preserves_file_metadata_on_atomic_replace(self):
        text = self.read_installer()

        self.assertIn("existing_stat = path.stat()", text)
        self.assertIn("stat.S_IMODE(existing_stat.st_mode)", text)
        self.assertIn("os.chmod(tmp_name", text)
        self.assertIn("os.chown(tmp_name, existing_stat.st_uid, existing_stat.st_gid)", text)
        self.assertIn("0o644", text)
        self.assertLess(text.index("os.chmod(tmp_name"), text.index("os.replace(tmp_name, path)"))

    def test_set_gdm_key_only_updates_daemon_section(self):
        temp_root = REPO_ROOT / "tmp_test_artifacts"
        try:
            temp_root.mkdir(exist_ok=True)
        except PermissionError as exc:
            raise unittest.SkipTest("temporary test directory is not writable") from exc

        config = temp_root / f"custom-{self.id().replace('.', '-')}.conf"
        try:
            config.write_text(
                "[security]\n"
                "WaylandEnable=true\n"
                "\n"
                "[daemon]\n"
                "#AutomaticLoginEnable=False\n"
                "\n"
                "[other]\n"
                "WaylandEnable=true\n",
                encoding="utf-8",
            )
        except PermissionError as exc:
            raise unittest.SkipTest("temporary test file is not writable") from exc

        script = (
            "set -euo pipefail\n"
            f"export INSTALLER={bash_path(INSTALLER)!r}\n"
            f"export GDM_CONFIG={bash_path(config)!r}\n"
            "export RDKX5_RUSTDESK_INSTALLER_TESTING=1\n"
            'source "$INSTALLER"\n'
            'set_gdm_key "$GDM_CONFIG" "WaylandEnable" "false"\n'
            'set_gdm_key "$GDM_CONFIG" "AutomaticLoginEnable" "True"\n'
            'cat "$GDM_CONFIG"\n'
        )
        try:
            result = run_bash_script(script)
        finally:
            try:
                config.unlink()
            except FileNotFoundError:
                pass
            try:
                temp_root.rmdir()
            except OSError:
                pass

        self.assertIn("[security]\nWaylandEnable=true", result.stdout)
        self.assertIn("[other]\nWaylandEnable=true", result.stdout)
        daemon_section = result.stdout.split("[daemon]\n", 1)[1].split("\n[other]\n", 1)[0]
        self.assertIn("AutomaticLoginEnable=True\n", daemon_section)
        self.assertIn("WaylandEnable=false\n", daemon_section)

    def test_set_gdm_key_collapses_duplicate_daemon_keys(self):
        temp_root = REPO_ROOT / "tmp_test_artifacts"
        try:
            temp_root.mkdir(exist_ok=True)
        except PermissionError as exc:
            raise unittest.SkipTest("temporary test directory is not writable") from exc

        config = temp_root / f"custom-{self.id().replace('.', '-')}.conf"
        try:
            config.write_text(
                "[daemon]\n"
                "WaylandEnable=true\n"
                "#WaylandEnable=true\n"
                "AutomaticLoginEnable=True\n"
                "WaylandEnable=maybe\n"
                "\n"
                "[other]\n"
                "WaylandEnable=true\n",
                encoding="utf-8",
            )
        except PermissionError as exc:
            raise unittest.SkipTest("temporary test file is not writable") from exc

        script = (
            "set -euo pipefail\n"
            f"export INSTALLER={bash_path(INSTALLER)!r}\n"
            f"export GDM_CONFIG={bash_path(config)!r}\n"
            "export RDKX5_RUSTDESK_INSTALLER_TESTING=1\n"
            'source "$INSTALLER"\n'
            'set_gdm_key "$GDM_CONFIG" "WaylandEnable" "false"\n'
            'cat "$GDM_CONFIG"\n'
        )
        try:
            result = run_bash_script(script)
        finally:
            try:
                config.unlink()
            except FileNotFoundError:
                pass
            try:
                temp_root.rmdir()
            except OSError:
                pass

        daemon_section = result.stdout.split("[daemon]\n", 1)[1].split("\n[other]\n", 1)[0]
        self.assertEqual(1, daemon_section.count("WaylandEnable="))
        self.assertIn("WaylandEnable=false\n", daemon_section)
        self.assertIn("AutomaticLoginEnable=True\n", daemon_section)
        self.assertIn("[other]\nWaylandEnable=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
