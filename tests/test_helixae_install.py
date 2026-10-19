import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("helixae_install", ROOT / "Scripts/helixae_install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prism = self.root / "Prism & Company"
        self.plugin = self.root / "Client's éclair!"
        runtime = self.prism / "Python313/python.exe"
        script = self.plugin / "Scripts/HelixAE_MenuTools.py"
        runtime.parent.mkdir(parents=True)
        script.parent.mkdir(parents=True)
        runtime.write_bytes(b"runtime")
        script.write_bytes(b"script")
        self.archive = self.root / "panel.zip"
        self.files = {name: ("new:" + name).encode() for name in installer.REQUIRED_FILES}
        self.write_archive()
        self.template = self.root / "launcher.cmd"
        self.template.write_text('@echo off\nset "PRISM_ROOT=PRISMROOT"\nset "HELIXAE_PLUGIN=PLUGINROOT"\n', encoding="utf-8")
        self.dest = self.root / "extensions"
        (self.dest / "helixae").mkdir(parents=True)
        (self.dest / "helixae/old.txt").write_bytes(b"old panel")
        (self.dest / "helixae.cmd").write_bytes(b"old launcher")

    def write_archive(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as package:
            for name, data in self.files.items():
                package.writestr(name, data)
            if extra:
                package.writestr(*extra)

    def install(self):
        return installer.install(self.archive, self.template, str(self.dest), str(self.prism), str(self.plugin))

    def assert_old(self):
        self.assertEqual((self.dest / "helixae/old.txt").read_bytes(), b"old panel")
        self.assertEqual((self.dest / "helixae.cmd").read_bytes(), b"old launcher")

    def test_success_expands_paths_and_verifies_payload(self):
        self.assertTrue(self.install())
        installer.verify_files(str(self.dest / "helixae"), self.files)
        launcher = (self.dest / "helixae.cmd").read_bytes().decode("utf-8")
        self.assertIn(str(self.plugin), launcher)
        self.assertIn("DisableDelayedExpansion", launcher)
        self.assertNotIn("PLUGINROOT", launcher)
        self.assertFalse(list(self.dest.glob(".helixae-install-*")))

    def test_corrupt_zip_preserves_old(self):
        self.archive.write_bytes(b"broken")
        with self.assertRaises(zipfile.BadZipFile):
            self.install()
        self.assert_old()

    def test_missing_runtime_preserves_old(self):
        (self.prism / "Python313/python.exe").unlink()
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            self.install()
        self.assert_old()

    def test_missing_required_member_preserves_old(self):
        del self.files["index.html"]
        self.write_archive()
        with self.assertRaises(ValueError):
            self.install()
        self.assert_old()

    def test_unsafe_members_preserve_old(self):
        for member in ("../escape", "/absolute", "C:/absolute", "js\\escape", "JS/main.js"):
            with self.subTest(member=member):
                self.write_archive((member, b"bad"))
                with self.assertRaises(ValueError):
                    self.install()
                self.assert_old()

    def test_symlink_rejected(self):
        entry = zipfile.ZipInfo("link")
        entry.external_attr = 0o120777 << 16
        with zipfile.ZipFile(self.archive, "a") as package:
            package.writestr(entry, "outside")
        with self.assertRaises(ValueError):
            self.install()
        self.assert_old()

    def test_publish_failure_rolls_back_both_targets(self):
        original = os.replace
        def replace(source, target):
            if str(source).endswith("launcher.cmd"):
                raise PermissionError("launcher locked")
            return original(source, target)
        with mock.patch.object(installer.os, "replace", side_effect=replace):
            with self.assertRaisesRegex(RuntimeError, "previous integration restored"):
                self.install()
        self.assert_old()

    def test_post_publish_hash_failure_rolls_back(self):
        original = installer.verify_files
        def verify(folder, files):
            if str(folder) == str(self.dest / "helixae"):
                raise IOError("hash mismatch")
            return original(folder, files)
        with mock.patch.object(installer, "verify_files", side_effect=verify):
            with self.assertRaisesRegex(RuntimeError, "restored"):
                self.install()
        self.assert_old()

    def test_failed_recovery_keeps_backup_and_reports_location(self):
        original = os.replace
        def replace(source, target):
            if str(source).endswith(("launcher.cmd", "previous-0")):
                raise PermissionError("locked")
            return original(source, target)
        with mock.patch.object(installer.os, "replace", side_effect=replace):
            with self.assertRaisesRegex(RuntimeError, "backups retained"):
                self.install()
        stages = list(self.dest.glob(".helixae-install-*"))
        self.assertEqual(len(stages), 1)
        self.assertEqual((stages[0] / "previous-0/old.txt").read_bytes(), b"old panel")

    def test_invalid_template_preserves_old(self):
        self.template.write_text("no placeholders", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.install()
        self.assert_old()


if __name__ == "__main__":
    unittest.main()
