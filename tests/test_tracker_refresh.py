"""Exercise refresh orchestration with bridge failures without importing Qt."""
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protocol', ROOT / 'Scripts/helixae_protocol.py')
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


def load_method(class_name, method_name, filename, namespace):
    tree = ast.parse((ROOT / 'Scripts/footage_tracker' / filename).read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[method_name]


class ReopenSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.identity = ('Z:/Project', 'Z:/Project/scene.aep')
        self.obj = SimpleNamespace(
            _footageSnapshotIdentity=Mock(return_value=self.identity),
            _footage_snapshot_identity=self.identity,
            _stored_hierarchy={'Resources': {}},
            tree_ops=SimpleNamespace(tree_renderer=Mock(), updateStatistics=Mock()),
            updateCheckIssuesButton=Mock(), tw_footage=Mock(),
            dlg_footage=SimpleNamespace(statusBar=Mock()))
        self.restore = load_method('AEFootageTracker', '_restoreCachedFootageData',
                                   'tracker.py', {})

    def test_same_scene_reopens_without_scan(self):
        self.assertTrue(self.restore(self.obj))
        self.obj.tree_ops.tree_renderer.renderHierarchyTree.assert_called_once_with(
            self.obj._stored_hierarchy)

    def test_other_scene_requires_scan(self):
        self.obj._footageSnapshotIdentity.return_value = ('Z:/Project', 'other.aep')
        self.assertFalse(self.restore(self.obj))
        self.obj.tree_ops.tree_renderer.renderHierarchyTree.assert_not_called()

    def test_bridge_unavailable_does_not_reuse_unidentified_scene(self):
        self.obj._footageSnapshotIdentity.return_value = None
        self.assertFalse(self.restore(self.obj))

    def test_no_successful_snapshot_requires_scan(self):
        self.obj._stored_hierarchy = None
        self.assertFalse(self.restore(self.obj))

    def test_valid_empty_snapshot_is_reusable(self):
        self.obj._stored_hierarchy = {}
        self.assertTrue(self.restore(self.obj))


class RefreshFailureTests(unittest.TestCase):
    def setUp(self):
        self.previous = {'Resources': {'old': ['footage']}}
        self.tree = Mock()
        self.main = SimpleNamespace(
            ae_core=SimpleNamespace(executeAppleScript=Mock()),
            _footage_hierarchy=self.previous)
        self.tracker = SimpleNamespace(
            tw_footage=self.tree, dlg_footage=SimpleNamespace(statusBar=Mock()),
            kitsuShotData={}, kitsu_integration=SimpleNamespace(),
            loadKitsuShotData=Mock(), updateCheckIssuesButton=Mock(),
            _stored_hierarchy=self.previous, main=self.main)
        self.obj = SimpleNamespace(
            _load_generation=0, tracker=self.tracker, main=self.main,
            core=SimpleNamespace(popup=Mock()),
            data_parser=Mock(), hierarchy_builder=Mock(), tree_renderer=Mock(),
            saveTreeExpansionState=Mock(), restoreTreeExpansionState=Mock(),
            updateStatistics=Mock())
        self.refresh = load_method('TreeOperations', 'loadFootageData', 'tree_operations.py',
                                   {'helixae_protocol': protocol})

    def assert_preserved(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.refresh(self.obj)
        self.tree.clear.assert_not_called()
        self.obj.tree_renderer.renderHierarchyTree.assert_not_called()
        self.assertIs(self.tracker._stored_hierarchy, self.previous)
        self.assertIs(self.main._footage_hierarchy, self.previous)
        self.obj.core.popup.assert_called_once()

    def test_swallowed_bridge_failure_preserves_snapshot(self):
        self.main.ae_core.executeAppleScript.return_value = None
        self.assert_preserved()

    def test_invalid_comp_query_preserves_snapshot(self):
        self.main.ae_core.executeAppleScript.side_effect = [b'[]', b'EvalScript error.']
        self.assert_preserved()

    def test_hierarchy_error_preserves_snapshot(self):
        self.main.ae_core.executeAppleScript.side_effect = [b'[]', b'[]']
        self.obj.hierarchy_builder.buildHierarchy.side_effect = OSError('NAS unavailable')
        self.assert_preserved()


if __name__ == '__main__':
    unittest.main()
