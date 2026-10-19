"""Project Browser opening must use the long-running operation transport."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class SceneOpenTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'Scripts' / 'HelixAE_Functions.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for cls in tree.body if isinstance(cls, ast.ClassDef)
                      for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'openScene')
        method.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {}
        exec(compile(module, str(source), 'exec'), namespace)
        self.open_scene = namespace['openScene']
        self.core = Mock()
        self.facade = SimpleNamespace(ae_core=self.core,
                                      sendCmd=Mock(side_effect=AssertionError('short timeout')))

    def test_browser_uses_operation_transport_and_preserves_arguments(self):
        self.core.openScene.return_value = True
        self.assertTrue(self.open_scene(self.facade, 'browser', "Z:/Client's Job/scene.aep", True))
        self.core.openScene.assert_called_once_with('browser', "Z:/Client's Job/scene.aep", force=True)
        self.facade.sendCmd.assert_not_called()

    def test_failure_is_not_reported_as_success(self):
        self.core.openScene.return_value = False
        self.assertFalse(self.open_scene(self.facade, 'browser', 'missing.aep'))

    def test_swallowed_core_exception_is_not_success(self):
        self.core.openScene.return_value = None
        self.assertIsNone(self.open_scene(self.facade, 'browser', 'scene.aep'))
