"""Per-shot Kitsu FPS decisions and shot-dialog wiring without Qt."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fps_decisions', ROOT / 'Scripts/helixae_kitsu.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ShotFpsTests(unittest.TestCase):
    def test_shot_overrides_project_including_fractional_rates(self):
        self.assertEqual(module.shot_fps({'data': {'fps': '23.976'}, 'fps': 60}, 24, 25), 23.976)
        self.assertEqual(module.shot_fps({'fps': '29.97'}, 24, 25), 29.97)

    def test_invalid_values_fall_through(self):
        for value in (None, '', 'bad', 0, -1, 'nan', 'inf', '-inf', True, [], {}):
            with self.subTest(value=value):
                self.assertEqual(module.shot_fps({'data': {'fps': value}}, 24, 30), 24)
                self.assertEqual(module.shot_fps({'data': {'fps': value}}, value, 30), 30)
                self.assertEqual(module.shot_fps({'data': {'fps': value}}, value, value), 25)
        self.assertEqual(module.shot_fps(None, 24), 24)

    def test_dialog_displays_and_stores_shot_fps(self):
        path = ROOT / 'Scripts/footage_tracker/ae_kitsu.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'addShotToTree')
        class Item:
            def __init__(self):
                self.text = {}
                self.payload = None
            def setText(self, column, value):
                self.text[column] = value
            def setForeground(self, *args):
                pass
            def setData(self, column, role, value):
                self.payload = value
        namespace = {'shot_fps': module.shot_fps, 'QTreeWidgetItem': Item,
                     'Qt': SimpleNamespace(UserRole=32), 'QBrush': lambda x: x,
                     'QColor': lambda *args: args}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
        for failed_fetch in (False, True):
            def get_shot(shot_id):
                if failed_fetch:
                    raise OSError('offline')
                return {'data': {'fps': '23.976'}}
            manager = SimpleNamespace(gazu=SimpleNamespace(shot=SimpleNamespace(get_shot=get_shot)),
                                      getTasksFromEntity=lambda *args, **kwargs: [])
            dialog = SimpleNamespace(core=SimpleNamespace(getConfig=lambda *args, **kwargs: 25))
            children = []
            namespace['addShotToTree'](dialog, SimpleNamespace(addChild=children.append),
                                       {'id': 'shot', 'shot': 'SH010'}, 24, manager)
            expected = 24 if failed_fetch else 23.976
            self.assertEqual(children[0].payload['fps'], expected)
            self.assertEqual(children[0].text[2], format(expected, '.2f'))
