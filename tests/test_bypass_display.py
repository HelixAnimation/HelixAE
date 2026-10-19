"""Bypass edits repaint cached cells without inventory/network refreshes."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'Scripts/footage_tracker'


def method(filename, name, globals=None):
    path = ROOT / filename
    tree = ast.parse(path.read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    namespace = globals or {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), namespace)
    return namespace[name]


class BypassDisplayTests(unittest.TestCase):
    def test_controller_queues_same_snapshot_without_starting_jobs(self):
        warnings = SimpleNamespace()
        tracker = SimpleNamespace(startup_warnings=warnings)
        snapshot = {'xmp': 'old bypass payload'}
        obj = SimpleNamespace(scene={'path': 'Z:/scene.aep'}, tracker=tracker, snapshot=snapshot, _render_due=False)
        ignored = {'outdated': {'footage_SH_LowRes'}}
        method('refresh_controller.py', 'update_bypasses')(obj, ignored, 'Z:\\scene.aep')
        self.assertTrue(obj._render_due)
        self.assertIs(obj.snapshot, snapshot)
        self.assertEqual(warnings._ignored_items_cache['outdated'], {'footage_SH_LowRes'})
        self.assertEqual(warnings._ignored_items_cache_file, 'Z:/scene.aep')
        ignored['outdated'].clear()
        self.assertEqual(tracker._prepared_ignored_items['outdated'], {'footage_SH_LowRes'})

    def test_stale_scene_edit_cannot_change_current_scene(self):
        obj = SimpleNamespace(scene={'path': 'Z:/new.aep'}, _render_due=False)
        method('refresh_controller.py', 'update_bypasses')(obj, {'outdated': {'old'}}, 'Z:/old.aep')
        self.assertFalse(obj._render_due)

    def test_context_bypass_and_unbypass_do_not_refresh_inventory(self):
        ignored = {key: set() for key in ('outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch')}
        saved = []
        warnings = SimpleNamespace(_getIgnoredItems=lambda: ignored, _saveIgnoredItems=lambda data: saved.append({k: set(v) for k, v in data.items()}), _updateCachedIssueCounts=lambda: None)
        tracker = SimpleNamespace(startup_warnings=warnings, updateCheckIssuesButton=lambda: None)
        obj = SimpleNamespace(tracker=tracker, _buildItemKey=lambda item, data: 'footage_SH_LowRes')
        item = SimpleNamespace(data=lambda *args: {'type': 'footage'}, text=lambda column: '[2D] LowRes')
        globals = {'Qt': SimpleNamespace(UserRole=1)}
        method('context_menu_bypass.py', '_bypassTreeItem', globals)(obj, item)
        method('context_menu_bypass.py', '_unbypassTreeItem', globals)(obj, item)
        self.assertTrue(all('footage_SH_LowRes' in values for values in saved[0].values()))
        self.assertTrue(all(not values for values in saved[1].values()))

    def test_ctrl_click_toggle_needs_no_tree_refresh(self):
        ignored = {'outdated': set()}
        warnings = SimpleNamespace(_getIgnoredItems=lambda: ignored, _saveIgnoredItems=lambda data: None)
        tracker = SimpleNamespace(startup_warnings=warnings, tw_footage=SimpleNamespace(columnAt=lambda x: 2))
        obj = SimpleNamespace(tracker=tracker, _generateTreeItemKey=lambda item, data: 'footage_SH_LowRes')
        item = SimpleNamespace(data=lambda *args: {'type': 'footage'})
        pos = SimpleNamespace(x=lambda: 0)
        toggle = method('tree_operations_core.py', '_handleCtrlClickBypass', {'Qt': SimpleNamespace(UserRole=1)})
        toggle(obj, item, pos)
        self.assertEqual(ignored['outdated'], {'footage_SH_LowRes'})
        toggle(obj, item, pos)
        self.assertEqual(ignored['outdated'], set())


if __name__ == '__main__':
    unittest.main()
