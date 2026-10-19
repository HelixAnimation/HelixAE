"""Shot ownership regressions, independent of Prism and Qt."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'kitsu_keys', ROOT / 'Scripts/footage_tracker/kitsu_keys.py')
keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keys)


class ShotKeysTests(unittest.TestCase):
    def test_unique_alias(self):
        shot = {'shot': 'SH010', 'sequence': 'SQ01', 'id': 'a'}
        result, dropped = keys.build_shot_key_map([shot], lambda s: s)
        self.assertIs(result['SH010'], shot)
        self.assertIs(result['SQ01-SH010'], shot)
        self.assertEqual(dropped, [])

    def test_collision_never_selects_an_arbitrary_sequence(self):
        shots = [{'shot': 'SH010', 'sequence': seq, 'id': seq}
                 for seq in ('SQ01', 'SQ02', 'SQ03')]
        for order in (shots, list(reversed(shots))):
            result, dropped = keys.build_shot_key_map(order, lambda s: s['id'])
            self.assertNotIn('SH010', result)
            self.assertEqual(dropped, ['SH010'])
            for seq in ('SQ01', 'SQ02', 'SQ03'):
                self.assertEqual(result[seq + '-SH010'], seq)

    def test_unsequenced_owner_is_also_ambiguous(self):
        shots = [{'shot': 'SH010', 'sequence': ''},
                 {'shot': 'SH010', 'sequence': 'SQ02'}]
        for order in (shots, list(reversed(shots))):
            result, _ = keys.build_shot_key_map(order, lambda s: s)
            self.assertNotIn('SH010', result)
            self.assertIn('SQ02-SH010', result)

    def test_already_qualified_and_unsequenced_names(self):
        for name, seq in [('SQ01-SH010', 'SQ01'), ('SH020', '')]:
            self.assertEqual(keys.get_effective_keys(name, seq), (name, None))

    def test_invalid_records_skipped_and_callback_once(self):
        calls = []
        shots = [None, {}, {'shot': 42}, {'shot': 'éclair', 'sequence': 'Seq'}]
        result, _ = keys.build_shot_key_map(shots, lambda s: calls.append(s) or s)
        self.assertEqual(len(calls), 1)
        self.assertIn('Seq-éclair', result)

    def test_invalid_inputs(self):
        for name in ('', None, 12):
            with self.assertRaises(ValueError):
                keys.qualified_shot_key(name, '')
        with self.assertRaises(TypeError):
            keys.build_shot_key_map(None, lambda s: s)
        with self.assertRaises(TypeError):
            keys.build_shot_key_map([], None)


if __name__ == '__main__':
    unittest.main()
