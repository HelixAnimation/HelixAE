import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dev_panel", ROOT / "dev_panel.py")
dev_panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev_panel)


SIGNATURE = b'<signatures><Signature><SignedInfo/></Signature></signatures>'


class DevPanelTests(unittest.TestCase):
    def test_production_manifest_declares_supported_cep_runtime(self):
        manifest = ET.parse(ROOT / "Integration/helixae/CSXS/manifest.xml").getroot()
        runtime = manifest.find("ExecutionEnvironment/RequiredRuntimeList/RequiredRuntime")
        self.assertIsNotNone(runtime, "CEP discovery requires an explicit runtime")
        self.assertEqual(runtime.get("Name"), "CSXS")
        # AE 16 ships CEP 9; the minimum runtime must also support that host.
        self.assertLessEqual(float(runtime.get("Version")), 9.0)
        for extension in manifest.findall("ExtensionList/Extension"):
            self.assertEqual(extension.get("Version"), manifest.get("ExtensionBundleVersion"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "panel"
        (self.source / "CSXS").mkdir(parents=True)
        (self.source / "js").mkdir()
        (self.source / "index.html").write_bytes(b"index")
        (self.source / "CSXS/manifest.xml").write_bytes(b"manifest")
        (self.source / "js/main.js").write_bytes(b"main")
        self.archive = self.root / "panel.zip"
        self.write_archive(signature=SIGNATURE)

    def write_archive(self, signature=None, extra=None):
        with zipfile.ZipFile(self.archive, "w") as package:
            for name in ("index.html", "CSXS/manifest.xml", "js/main.js"):
                package.write(self.source / name, name)
            mimetype = self.source / "mimetype"
            if mimetype.exists():
                package.writestr("mimetype", mimetype.read_bytes().rstrip(b"\r\n"))
            if extra:
                package.writestr(*extra)
            if signature is not None:
                package.writestr("META-INF/signatures.xml", signature)

    def test_panel_files_rejects_source_signature(self):
        (self.source / "META-INF").mkdir()
        (self.source / "META-INF/signatures.xml").write_bytes(SIGNATURE)
        with self.assertRaisesRegex(ValueError, "must not contain"):
            dev_panel.panel_files(self.source)

    def test_check_archive_accepts_signed_match(self):
        self.assertEqual(
            dev_panel.check_archive(self.archive, dev_panel.panel_files(self.source)),
            "signed",
        )

    def test_check_archive_rejects_unsigned_by_default(self):
        self.write_archive(signature=None)
        with self.assertRaisesRegex(ValueError, "unsigned"):
            dev_panel.check_archive(self.archive, dev_panel.panel_files(self.source))

    def test_check_archive_allows_unsigned_for_development(self):
        self.write_archive(signature=None)
        self.assertEqual(
            dev_panel.check_archive(
                self.archive, dev_panel.panel_files(self.source), allow_unsigned=True
            ),
            "unsigned",
        )

    def test_check_archive_normalizes_signed_mimetype(self):
        (self.source / "mimetype").write_bytes(
            b"application/vnd.adobe.air-ucf-package+zip\r\n"
        )
        self.write_archive(signature=SIGNATURE)
        self.assertEqual(
            dev_panel.check_archive(self.archive, dev_panel.panel_files(self.source)),
            "signed",
        )

    def test_check_archive_rejects_extra_member(self):
        self.write_archive(signature=SIGNATURE, extra=("extra.js", b"extra"))
        with self.assertRaisesRegex(ValueError, "extra"):
            dev_panel.check_archive(self.archive, dev_panel.panel_files(self.source))

    def test_check_archive_rejects_content_mismatch(self):
        (self.source / "js/main.js").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs"):
            dev_panel.check_archive(self.archive, dev_panel.panel_files(self.source))

    def test_archive_signature_state(self):
        self.assertEqual(dev_panel.archive_signature_state(self.root / "missing.zip"), "missing")
        self.assertEqual(dev_panel.archive_signature_state(self.archive), "signed")
        broken = self.root / "broken.zip"
        broken.write_bytes(b"not a zip")
        self.assertEqual(dev_panel.archive_signature_state(broken), "malformed")

    def test_build_refuses_to_replace_signed_archive(self):
        with self.assertRaisesRegex(ValueError, "Refusing"):
            dev_panel.build_archive(self.archive, dev_panel.panel_files(self.source))

    def test_build_replaces_signed_archive_when_explicit(self):
        dev_panel.build_archive(
            self.archive, dev_panel.panel_files(self.source), allow_unsigned=True
        )
        self.assertEqual(dev_panel.archive_signature_state(self.archive), "unsigned")

    def test_stage_panel_files(self):
        destination = self.root / "staged"
        dev_panel.stage_panel_files(dev_panel.panel_files(self.source), destination)
        self.assertEqual((destination / "js/main.js").read_bytes(), b"main")
        self.assertFalse((destination / "META-INF/signatures.xml").exists())


if __name__ == "__main__":
    unittest.main()
