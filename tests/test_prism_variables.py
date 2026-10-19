import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "Scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from HelixAE_Variables import HelixAE_Variables  # noqa: E402
from Prism_HelixAE_Variables import Prism_HelixAE_Variables  # noqa: E402


class PrismVariablesShimTests(unittest.TestCase):
    def test_shim_exposes_the_existing_class(self):
        self.assertIs(Prism_HelixAE_Variables, HelixAE_Variables)

    def test_shim_preserves_plugin_metadata(self):
        variables = Prism_HelixAE_Variables(None, None)
        self.assertEqual(variables.pluginName, "HelixAE")
        self.assertEqual(variables.pluginType, "App")
        self.assertEqual(variables.platforms, ["Windows"])


if __name__ == "__main__":
    unittest.main()
