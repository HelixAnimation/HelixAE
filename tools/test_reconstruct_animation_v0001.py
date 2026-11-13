"""Disposable filesystem tests for create-only Maya publish reconstruction."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

import reconstruct_animation_v0001 as reconstruction


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = 'X:/Cytonics_CYT108/Scene/test.ma'
        self.version = 'X:/Cytonics_CYT108/Export/Animation/v0001'
        self.dependency = 'X:/Cytonics_CYT108/Rig/v0001/rig.ma'
        self.scene = self.local(self.source)
        self.target = self.local(self.version) + '/versioninfo.json'
        self.abc = self.local(self.version) + '/SQ020-SH021_Animation_v0001.abc'
        for directory in [os.path.dirname(self.scene), os.path.dirname(self.target), os.path.dirname(self.local(self.dependency))]:
            os.makedirs(directory, exist_ok=True)
        with open(self.local(self.dependency), 'wb') as handle:
            handle.write(b'rig')
        states = {'states': [{'stateclass': 'ImportFile', 'filepath': self.dependency},
                             {'stateclass': 'Export', 'productname': 'Animation',
                              'lastexportpath': self.version + '/SQ020-SH021_Animation_v0001.abc'}]}
        self.raw_scene = ('currentUnit -l centimeter -a degree -t film;\n'
                          'file -r -type "mayaAscii" ' + json.dumps(self.dependency) + ';\n'
                          'fileInfo "PrismStates" ' + json.dumps(json.dumps(states)) + ';\n').encode('ascii')
        with open(self.scene, 'wb') as handle:
            handle.write(self.raw_scene)
        with open(os.path.splitext(self.scene)[0] + 'versioninfo.json', 'w') as handle:
            json.dump({'sequence': 'SQ020', 'shot': 'SH021', 'username': 'Scene Artist', 'user': 'artist'}, handle)
        self.raw_abc = ('Maya 2022 AbcExport v1.0;Exported from: ' + self.source).encode('ascii')
        with open(self.abc, 'wb') as handle:
            handle.write(self.raw_abc)
        self.payload = {'version': self.version, 'source': self.source, 'apply': True,
                        'scene_sha256': hashlib.sha256(self.raw_scene).hexdigest(),
                        'tail_sha256': hashlib.sha256(self.raw_abc).hexdigest()}

    def local(self, path):
        return self.tmp.name + '/' + path[3:]

    def run_transaction(self, race=False):
        code = reconstruction.TRANSACTION.replace("'/volume1/Renders/X/'", repr(self.tmp.name + '/'))
        if race:
            code = code.replace('os.link(stage,target)', "open(target,'xb').write(b'concurrent writer');os.link(stage,target)")
        return subprocess.run([sys.executable, '-c', code], input=json.dumps(self.payload),
                              capture_output=True, text=True)

    def test_creates_scene_wide_metadata_without_claiming_exporter(self):
        result = self.run_transaction()
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record['status'], 'reconstructed')
        with open(self.target) as handle:
            data = json.load(handle)
        self.assertEqual(data['dependencies'], [self.dependency])
        self.assertEqual(data['sourceScene'], self.source)
        self.assertEqual(data['version'], 'v0001')
        self.assertNotIn('user', data)
        self.assertNotIn('username', data)
        self.assertNotIn('renderDependencies', data)
        with open(self.scene, 'rb') as handle:
            self.assertEqual(handle.read(), self.raw_scene)
        with open(self.abc, 'rb') as handle:
            self.assertEqual(handle.read(), self.raw_abc)
        self.assertFalse(any(n.endswith('.tmp') for n in os.listdir(os.path.dirname(self.target))))

    def test_existing_json_is_never_overwritten(self):
        with open(self.target, 'wb') as handle:
            handle.write(b'original')
        self.assertNotEqual(self.run_transaction().returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), b'original')

    def test_racing_writer_is_never_overwritten(self):
        self.assertNotEqual(self.run_transaction(race=True).returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), b'concurrent writer')
        self.assertFalse(any(n.endswith('.tmp') for n in os.listdir(os.path.dirname(self.target))))

    def test_missing_input_leaves_metadata_absent(self):
        os.unlink(self.local(self.dependency))
        self.assertNotEqual(self.run_transaction().returncode, 0)
        self.assertFalse(os.path.exists(self.target))

    def test_prepare_does_not_publish(self):
        self.payload['apply'] = False
        result = self.run_transaction()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'prepared')
        self.assertFalse(os.path.exists(self.target))


if __name__ == '__main__':
    unittest.main()
