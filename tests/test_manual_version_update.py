"""Manual version updates must work without the legacy synchronous refresh."""
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_method(class_name, method_name, filename, namespace):
    tree = ast.parse((ROOT / 'Scripts/footage_tracker' / filename).read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[method_name]



class ManualVersionUpdateTests(unittest.TestCase):
    def setUp(self):
        class QObject:
            def __init__(self):
                pass

        class Tracker(QObject):
            pass

        def handler(tracker):
            # Logging must already exist when operation handlers are created.
            self.assertEqual(tracker.debugLog, [])
            return Mock()

        namespace = {
            'AEFootageTracker': Tracker,
            'FootageUtils': Mock(),
            'KitsuIntegration': Mock(return_value=SimpleNamespace(kitsu=None)),
        }
        for name in ('AEOperations', 'TreeOperations', 'UISetup', 'ImportShots',
                     'StartupWarnings'):
            namespace[name] = handler
        initialize = load_method('AEFootageTracker', '__init__', 'tracker.py', namespace)
        main = SimpleNamespace(core=Mock(), _getFootagePreparation=Mock())
        self.initialize = lambda tracker: initialize(tracker, main)
        self.tracker = Tracker()
        self.initialize(self.tracker)
        self.tracker.showSelectableMessage = Mock()
        self.tracker.updateStatistics = Mock()
        self.tracker.loadFootageData = Mock()
        self.tracker.dlg_footage = SimpleNamespace(statusBar=Mock())
        self.tracker.utils.isSequence.return_value = True
        self.ops = SimpleNamespace(
            tracker=self.tracker,
            _resolveNewVersionPath=Mock(return_value='Z:/v0002/beauty.1001.exr'),
            _getFootageProperties=Mock(return_value=({'conformFrameRate': 25}, None)),
            _replaceFootageInAE=Mock(return_value=(True, None)),
        )
        self.update = load_method('AEOperations', 'updateFootageVersion',
                                  'ae_operations.py', {
                                      're': re, 'QBrush': Mock(), 'QColor': Mock(),
                                      'Qt': SimpleNamespace(UserRole=256),
                                      'QTimer': SimpleNamespace(singleShot=Mock()),
                                  })
        self.item = Mock()
        self.data = dict(id=17, path='Z:/v0001/beauty.1001.exr',
                         currentVersion='v0001', latestVersion='v0002')

    def test_new_trackers_own_independent_logs(self):
        self.assertEqual(self.tracker.debugLog, [])
        other = type(self.tracker)()
        # Run the real constructor a second time, not the old tree loader.
        self.initialize(other)
        self.tracker.debugLog.append('first tracker only')
        self.assertEqual(other.debugLog, [])
        self.assertIsNot(self.tracker.debugLog, other.debugLog)

    def test_manual_update_before_legacy_refresh(self):
        self.assertTrue(self.update(self.ops, self.item, 'v0002', self.data))
        self.ops._replaceFootageInAE.assert_called_once_with(
            17, 'Z:/v0002/beauty.1001.exr', True, 25)
        self.assertEqual(self.data['currentVersion'], 'v0002')
        self.assertEqual(self.data['path'], 'Z:/v0002/beauty.1001.exr')
        self.item.setData.assert_called_once_with(2, 257, 'current')
        self.tracker.loadFootageData.assert_called_once_with()
        self.tracker.showSelectableMessage.assert_not_called()
        self.assertEqual(len(self.tracker.debugLog), 2)

    def test_failed_replacement_preserves_version_and_skips_refresh(self):
        self.ops._replaceFootageInAE.return_value = (False, 'No bridge response')
        before = self.data.copy()
        self.assertFalse(self.update(self.ops, self.item, 'v0002', self.data))
        self.assertEqual(self.data, before)
        self.item.setText.assert_not_called()
        self.tracker.loadFootageData.assert_not_called()
        self.tracker.showSelectableMessage.assert_called_once()


if __name__ == '__main__':
    unittest.main()
