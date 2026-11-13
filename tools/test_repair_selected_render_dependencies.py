"""Local disposable-filesystem checks for the temporary repair transaction."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import repair_selected_render_dependencies as repair


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.version = 'X:/Cytonics_CYT108/Test/v0001'
        self.directory = os.path.join(self.tmp.name, 'Cytonics_CYT108', 'Test', 'v0001')
        os.makedirs(self.directory)
        self.target = os.path.join(self.directory, 'versioninfo.json')
        self.old = {'sourceScene': 'X:/source.aep', 'dependencies': ['scene-wide'],
                    'compDependencies': {'keep': True}, 'custom': [1, None, 'α']}
        self.raw = json.dumps(self.old, ensure_ascii=False, indent=4).encode('utf-8')
        with open(self.target, 'wb') as handle:
            handle.write(self.raw)
        self.block = {'context': {'application': 'aftereffects', 'type': 'composition',
                                  'identifier': '265', 'name': 'Main'},
                      'dependencies': [], 'externalFiles': []}

    def publish(self, expected=None, run='test', field_updates=None):
        code = repair.PUBLISH.replace("'/volume1/Renders/X/'", repr(self.tmp.name + '/'))
        return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                              input=json.dumps({'version': self.version, 'run': run,
                                                'expected': self.old if expected is None else expected,
                                                'block': self.block,
                                                'field_updates': field_updates or {}}))

    def test_backup_and_preserve_every_other_field(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record['status'], 'updated')
        with open(record['backup'], 'rb') as handle:
            self.assertEqual(handle.read(), self.raw)
        with open(self.target, encoding='utf-8') as handle:
            data = json.load(handle)
        self.assertEqual(data.pop('renderDependencies'), self.block)
        self.assertEqual(data, self.old)
        self.assertEqual(record['original_sha256'], record['backup_sha256'])
        self.assertFalse(any(n.endswith('.tmp') for n in os.listdir(self.directory)))

    def test_changed_original_is_not_overwritten(self):
        result = self.publish(expected={'different': True})
        self.assertNotEqual(result.returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), self.raw)
        self.assertEqual(os.listdir(self.directory), ['versioninfo.json'])

    def test_existing_backup_is_never_overwritten(self):
        path = self.target + '.before-render-deps.test.bak'
        with open(path, 'wb') as handle:
            handle.write(b'previous backup')
        self.assertNotEqual(self.publish().returncode, 0)
        with open(path, 'rb') as handle:
            self.assertEqual(handle.read(), b'previous backup')
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), self.raw)

    def test_repeat_is_noop(self):
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        updated = dict(self.old, renderDependencies=self.block)
        result = self.publish(expected=updated, run='second')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'already-current')
        self.assertFalse(os.path.exists(self.target + '.before-render-deps.second.bak'))

    def test_authorized_empty_source_is_filled_and_backed_up(self):
        self.old['sourceScene'] = ''
        self.raw = json.dumps(self.old, ensure_ascii=False).encode('utf-8')
        with open(self.target, 'wb') as handle:
            handle.write(self.raw)
        source = 'X:/Cytonics_CYT108/Edit_v0024.aep'
        result = self.publish(field_updates={'sourceScene': source})
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        with open(record['backup'], 'rb') as handle:
            self.assertEqual(handle.read(), self.raw)
        with open(self.target, encoding='utf-8') as handle:
            updated = json.load(handle)
        self.assertEqual(updated.pop('renderDependencies'), self.block)
        self.assertEqual(updated, dict(self.old, sourceScene=source))

    def test_source_correction_cannot_replace_nonempty_source(self):
        result = self.publish(field_updates={'sourceScene': 'X:/Cytonics_CYT108/other.aep'})
        self.assertNotEqual(result.returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), self.raw)
        self.assertEqual(os.listdir(self.directory), ['versioninfo.json'])

    def test_real_classifier(self):
        classifier = repair.classify_folder()
        self.assertEqual(classifier('X:/p/Renders/3dRender/beauty.1001.exr'), '01_3D_Renders')
        self.assertEqual(classifier('X:/p/Playblasts/Layout/v0001/a.jpg'), '02_2D_Renders')
        self.assertEqual(classifier('X:/p/04_Resources/a.png'), '03_Resources')

    def test_queue_requires_completed_exact_output(self):
        version = 'X:/p/Renders/2dRender/HighRes/v0001'
        movie = version + '/main.mov'
        queue = [
            {'done': True, 'compId': '1', 'outputs': [movie.replace('/', '\\')]},
            {'done': False, 'compId': '2', 'outputs': [movie]},
            {'done': True, 'compId': '3', 'outputs': [version + '/different.mov']},
            {'done': True, 'compId': '4', 'outputs': [version + '0/main.mov']},
        ]
        matches = repair.queue_matches({'queue': queue}, {'version': version}, {movie.lower()})
        self.assertEqual(set(matches), {'1'})

    def test_variants_retain_both_compositions(self):
        version = 'X:/p/v0001'
        movies = {version.lower() + '/main.mov', version.lower() + '/subtitles.mov'}
        queue = [{'done': True, 'compId': '1', 'outputs': [version + '/main.mov']},
                 {'done': True, 'compId': '2', 'outputs': [version + '/subtitles.mov']}]
        self.assertEqual(set(repair.queue_matches({'queue': queue}, {'version': version}, movies)), {'1', '2'})

    def test_confirmed_comp_scans_current_dirty_project_without_saving_or_opening(self):
        node = {'source': 'X:/source.aep'}
        comp = {'id': '191', 'name': 'HighRes_v0005'}
        replies = [{'result': True, 'comps': [comp]},
                   {'result': True, 'path': 'X:\\source.aep', 'scan': {
                       'result': True, 'composition': comp,
                       'footage': [{'id': '2', 'name': 'plate', 'path': 'X:/plate.mov'}]}}]
        with mock.patch.object(repair.audit, 'state', return_value={'path': 'X:/source.aep', 'dirty': True}), \
                mock.patch.object(repair.audit, 'ae', side_effect=replies) as ae, \
                mock.patch.object(repair.audit, 'open_scene') as opening:
            self.assertEqual(repair.scan_confirmed_comp(node, comp['name']), ['X:/plate.mov'])
            opening.assert_not_called()
            self.assertEqual(ae.call_count, 2)
            self.assertTrue(node['scanned_dirty_project'])
            self.assertEqual(node['composition'], comp)

    def test_confirmed_comp_rejects_duplicate_names(self):
        comp = {'id': '191', 'name': 'Main'}
        with mock.patch.object(repair.audit, 'state', return_value={'path': 'X:/source.aep', 'dirty': False}), \
                mock.patch.object(repair.audit, 'ae', return_value={'comps': [comp, dict(comp, id='192')]}):
            with self.assertRaisesRegex(RuntimeError, 'exactly one comp'):
                repair.scan_confirmed_comp({'source': 'X:/source.aep'}, 'Main')


if __name__ == '__main__':
    unittest.main()
