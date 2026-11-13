"""Local checks for the XMP-evidence repair flow (no AE, no NAS, no writes)."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import repair_xmp_evidence as xmp
import repair_selected_render_dependencies as repair

VERSION = 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Renders/2dRender/HighRes/v0011'
KEY = VERSION.lower()
EVIDENCE = {'movie': xmp.MOVIES[KEY], 'movie_sha256': 'a' * 64, 'composition_id': '265',
            'full_path': 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Scenefiles/LookDev/HighRes/SQ020-SH020_HighRes_v0040.aep',
            'render_queue_item_id': '86',
            'metadata': {'sourceScene': 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Scenefiles/LookDev/HighRes/SQ020-SH020_HighRes_v0040.aep',
                         'dependencies': ['scene-wide']}}
COMP = {'id': '265', 'name': 'SQ020-SH020_HighRes_v0001'}
BLOCK = {'context': {'application': 'aftereffects', 'type': 'composition',
                     'identifier': '265', 'name': COMP['name']},
         'dependencies': [], 'externalFiles': []}


def fake_scan_response(scene=COMP and EVIDENCE['full_path'], comp=COMP, footage=(), path=None):
    return {'result': True, 'path': path or scene, 'compName': comp['name'],
            'scan': {'result': True, 'composition': comp, 'footage': list(footage)}}


class EvidenceChecks(unittest.TestCase):
    def test_matching_evidence_returns_source(self):
        self.assertEqual(xmp.check_evidence(VERSION, dict(EVIDENCE)), EVIDENCE['full_path'])

    def test_source_mismatch_rejected(self):
        bad = dict(EVIDENCE, full_path='X:/other_v0039.aep')
        with self.assertRaises(RuntimeError):
            xmp.check_evidence(VERSION, bad)
        bad = dict(EVIDENCE, metadata={'sourceScene': 'X:/other_v0039.aep'})
        with self.assertRaises(RuntimeError):
            xmp.check_evidence(VERSION, bad)

    def test_invalid_composition_id_rejected(self):
        with self.assertRaises(RuntimeError):
            xmp.check_evidence(VERSION, dict(EVIDENCE, composition_id='0'))
        with self.assertRaises(ValueError):
            xmp.check_evidence(VERSION, dict(EVIDENCE, composition_id='nope'))

    def test_unknown_version_has_no_movie_mapping(self):
        with self.assertRaises(RuntimeError):
            xmp.repair_target('X:/Cytonics_CYT108/Unknown/v0001', lambda p: 'x', apply=False)


class ScanScriptTests(unittest.TestCase):
    def test_single_wrap_with_identity_and_hint(self):
        script = xmp.scan_script('265', 'HighRes')
        self.assertTrue(script.startswith('(function ()'))
        self.assertIn('itemByID(265)', script)
        self.assertIn('instanceof CompItem', script)
        self.assertIn('"HighRes"', script)
        self.assertNotIn('renderQueue', script)

    def test_hint_escaping(self):
        self.assertIn('"BG\\"quoted"', xmp.scan_script('17', 'BG"quoted'))


class RepairFlowTests(unittest.TestCase):
    def setUp(self):
        self.classifier = lambda path: '01_3D_Renders'

    def test_dry_run_builds_block_without_write(self):
        with mock.patch.object(xmp, 'nas', return_value={VERSION: EVIDENCE}) as nas_mock, \
                mock.patch.object(xmp.audit, 'open_scene') as open_scene, \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(
                    footage=[{'id': '1', 'name': 'a', 'path': 'X:/Renders/3dRender/a.1001.exr'}])) as ae_mock, \
                mock.patch.object(xmp.audit, 'inspect',
                                  return_value=[{'path': 'X:/Renders/3dRender/a.1001.exr', 'exists': True}]):
            node, write = xmp.repair_target(VERSION, self.classifier, apply=False)
        self.assertIsNone(write)
        self.assertEqual(node['status'], 'dry-run')
        self.assertEqual(node['block']['dependencies'], ['X:/Renders/3dRender/a.1001.exr'])
        self.assertEqual(node['composition_name'], COMP['name'])
        self.assertEqual(node['xmp_evidence']['composition_id'], '265')
        nas_mock.assert_called_once()
        open_scene.assert_called_once()
        self.assertEqual(ae_mock.call_count, 1)

    def test_missing_paths_excluded_but_recorded(self):
        with mock.patch.object(xmp, 'nas', return_value={VERSION: EVIDENCE}), \
                mock.patch.object(xmp.audit, 'open_scene'), \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(
                    footage=[{'id': '1', 'name': 'a', 'path': 'X:/Renders/3dRender/a.1001.exr'},
                             {'id': '2', 'name': 'gone', 'path': 'X:/Renders/3dRender/gone.1001.exr'}])), \
                mock.patch.object(xmp.audit, 'inspect',
                                  return_value=[{'path': 'X:/Renders/3dRender/a.1001.exr', 'exists': True},
                                                {'path': 'X:/Renders/3dRender/gone.1001.exr', 'exists': False}]):
            node, _ = xmp.repair_target(VERSION, self.classifier, apply=False)
        self.assertEqual(node['block']['dependencies'], ['X:/Renders/3dRender/a.1001.exr'])
        self.assertEqual(node['missing'], ['X:/Renders/3dRender/gone.1001.exr'])

    def test_apply_publishes_expected_metadata(self):
        def fake_nas(code, payload=None):
            if payload and 'run' in payload:
                return {'status': 'updated', 'target': 't', 'backup': 'b',
                        'original_sha256': 'x', 'backup_sha256': 'x', 'new_sha256': 'y'}
            return {VERSION: EVIDENCE}
        with mock.patch.object(xmp, 'nas', side_effect=fake_nas) as nas_mock, \
                mock.patch.object(xmp.audit, 'open_scene'), \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(
                    footage=[{'id': '1', 'name': 'a', 'path': 'X:/Renders/3dRender/a.1001.exr'}])), \
                mock.patch.object(xmp.audit, 'inspect',
                                  return_value=[{'path': 'X:/Renders/3dRender/a.1001.exr', 'exists': True}]):
            node, write = xmp.repair_target(VERSION, self.classifier, apply=True)
        self.assertEqual(write['status'], 'updated')
        self.assertEqual(node['status'], 'updated')
        payload = nas_mock.call_args_list[-1].args[1]
        self.assertEqual(payload['expected'], EVIDENCE['metadata'])
        self.assertEqual(payload['block']['context']['identifier'], '265')

    def test_project_change_aborts(self):
        with mock.patch.object(xmp, 'nas', return_value={VERSION: EVIDENCE}), \
                mock.patch.object(xmp.audit, 'open_scene'), \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(path='X:/elsewhere.aep')):
            with self.assertRaises(RuntimeError):
                xmp.repair_target(VERSION, self.classifier, apply=False)

    def test_comp_identity_mismatch_aborts(self):
        with mock.patch.object(xmp, 'nas', return_value={VERSION: EVIDENCE}), \
                mock.patch.object(xmp.audit, 'open_scene'), \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(
                    comp={'id': '999', 'name': COMP['name']})):
            with self.assertRaises(RuntimeError):
                xmp.repair_target(VERSION, self.classifier, apply=False)

    def test_unexpected_comp_name_rejected_before_scan_use(self):
        script = xmp.scan_script('265', 'HighRes')
        self.assertIn('Unexpected composition name', script)

    def test_unverifiable_nas_existence_aborts(self):
        with mock.patch.object(xmp, 'nas', return_value={VERSION: EVIDENCE}), \
                mock.patch.object(xmp.audit, 'open_scene'), \
                mock.patch.object(xmp.audit, 'ae', return_value=fake_scan_response(
                    footage=[{'id': '1', 'name': 'a', 'path': 'X:/Renders/3dRender/a.1001.exr'}])), \
                mock.patch.object(xmp.audit, 'inspect',
                                  return_value=[{'path': 'X:/Renders/3dRender/a.1001.exr', 'exists': None}]):
            with self.assertRaises(RuntimeError):
                xmp.repair_target(VERSION, self.classifier, apply=False)


class JournalUpdateTests(unittest.TestCase):
    def test_update_replaces_node_and_clears_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'journal.json')
            report = {'run': 'r', 'nodes': {'other': {'status': 'updated'}},
                      'errors': [{'version': VERSION, 'error': 'old transport error'}]}
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(report, handle)
            node = {'version': VERSION, 'status': 'updated', 'write': {'status': 'updated'}}
            xmp.update_journal(path, {KEY: node})
            with open(path, encoding='utf-8') as handle:
                updated = json.load(handle)
            self.assertEqual(updated['nodes'][KEY]['status'], 'updated')
            self.assertEqual(updated['nodes']['other']['status'], 'updated')
            self.assertEqual(updated['errors'], [])


if __name__ == '__main__':
    unittest.main()
