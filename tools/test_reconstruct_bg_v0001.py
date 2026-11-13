"""Disposable-file checks for movie provenance and no-clobber BG creation."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

import reconstruct_bg_v0001 as bg


class BGReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = 'X:/Cytonics_CYT108/source.aep'
        self.version = 'X:/Cytonics_CYT108/BG/v0001'
        self.movie = self.version + '/bg.mov'
        self.dependency = 'X:/Cytonics_CYT108/input.exr'
        self.target = self.local(self.version) + '/versioninfo.json'
        os.makedirs(os.path.dirname(self.target))
        for path, raw in [(self.source, b'scene'), (self.dependency, b'frame')]:
            with open(self.local(path), 'wb') as handle:
                handle.write(raw)
        with open(os.path.splitext(self.local(self.source))[0] + 'versioninfo.json', 'w') as handle:
            json.dump({'sequence': 'SQ020', 'shot': 'SH020', 'user': 'scene_artist'}, handle)
        with open(os.path.splitext(self.local(self.source))[0] + '_archiveinfo.json', 'w') as handle:
            json.dump({'source_paths': {'3d_renders': [self.dependency]}}, handle)
        self.write_movie(self.source)
        self.metadata = {'version': 'v0001', 'sourceScene': self.source, 'dependencies': [self.dependency],
                         'externalFiles': [], 'renderDependencies': {
                             'context': {'application': 'aftereffects', 'type': 'composition',
                                         'identifier': '17', 'name': 'SQ020-SH020_BG_v0001'},
                             'dependencies': [self.dependency], 'externalFiles': []}}

    def local(self, path):
        return self.tmp.name + '/' + path[3:]

    def write_movie(self, source, comp_id='17'):
        xml = ('<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:c="http://ns.adobe.com/creatorAtom/1.0/" '
               'xmlns:d="http://ns.adobe.com/xmp/1.0/DynamicMedia/" d:videoFrameRate="24">'
               '<c:aeProjectLink c:fullPath="' + source + '" c:compositionID="' + comp_id + '" '
               'c:renderQueueItemID="23"/></x:xmpmeta>').encode('utf-8')
        with open(self.local(self.movie), 'wb') as handle:
            handle.write(struct.pack('>I4s', len(xml) + 8, b'moov') + xml)

    def remote(self, code, payload, race=False):
        code = code.replace("'/volume1/Renders/X/'", repr(self.tmp.name + '/'))
        if race:
            code = code.replace('os.link(stage,target)', "open(target,'xb').write(b'concurrent');os.link(stage,target)")
        return subprocess.run([sys.executable, '-c', code], input=json.dumps(payload), capture_output=True, text=True)

    def preflight(self):
        return self.remote(bg.PREFLIGHT, {'version': self.version, 'source': self.source, 'movie': self.movie})

    def create(self, evidence, race=False, expected_context=None):
        payload = {'version': self.version, 'movie': self.movie, 'metadata': self.metadata, 'evidence': evidence}
        if expected_context is not None:
            payload['expected_context'] = expected_context
        return self.remote(bg.CREATE, payload, race=race)

    def test_movie_link_and_create_round_trip(self):
        preflight = self.preflight()
        self.assertEqual(preflight.returncode, 0, preflight.stderr)
        evidence = json.loads(preflight.stdout)
        self.assertEqual(evidence['movie_project_link']['compositionID'], '17')
        self.assertFalse(os.path.exists(self.target))
        result = self.create(evidence)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.target, 'rb') as handle:
            raw = handle.read()
        self.assertEqual(json.loads(raw), self.metadata)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), json.loads(result.stdout)['new_sha256'])

    def test_wrong_embedded_source_is_rejected(self):
        self.write_movie('X:/Cytonics_CYT108/other.aep')
        self.assertNotEqual(self.preflight().returncode, 0)
        self.assertFalse(os.path.exists(self.target))

    def test_racing_target_is_preserved(self):
        evidence = json.loads(self.preflight().stdout)
        result = self.create(evidence, race=True)
        self.assertNotEqual(result.returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), b'concurrent')
        self.assertFalse(any(n.endswith('.tmp') for n in os.listdir(os.path.dirname(self.target))))

    def test_changed_source_aborts(self):
        evidence = json.loads(self.preflight().stdout)
        with open(self.local(self.source), 'wb') as handle:
            handle.write(b'new state')
        self.assertNotEqual(self.create(evidence).returncode, 0)
        self.assertFalse(os.path.exists(self.target))

    def test_existing_target_is_preserved(self):
        evidence = json.loads(self.preflight().stdout)
        with open(self.target, 'wb') as handle:
            handle.write(b'original')
        self.assertNotEqual(self.create(evidence).returncode, 0)
        with open(self.target, 'rb') as handle:
            self.assertEqual(handle.read(), b'original')

    def test_other_comp_must_match_movie_link_and_explicit_context(self):
        self.write_movie(self.source, comp_id='113')
        result = self.remote(bg.PREFLIGHT, {'version': self.version, 'source': self.source,
                                            'movie': self.movie, 'composition_id': '113'})
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        context = dict(self.metadata['renderDependencies']['context'], identifier='113', name='LowRes_v0001')
        self.metadata['renderDependencies']['context'] = context
        created = self.create(evidence, expected_context=context)
        self.assertEqual(created.returncode, 0, created.stderr)

    def test_mismatched_movie_comp_is_rejected(self):
        result = self.remote(bg.PREFLIGHT, {'version': self.version, 'source': self.source,
                                            'movie': self.movie, 'composition_id': '113'})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(self.target))


if __name__ == '__main__':
    unittest.main()
