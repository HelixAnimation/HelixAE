"""Real worker races and generated-script execution without Prism/Qt."""
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'Scripts')
sys.path.insert(0, SCRIPTS)
import helixae_refresh as refresh
import helixae_protocol as protocol
sys.path.remove(SCRIPTS)


def wait_for(jobs, predicate, timeout=2):
    events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(jobs.poll())
        if predicate(events):
            return events
        time.sleep(0.002)
    raise AssertionError('Worker did not finish: %r' % events)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.jobs = refresh.BackgroundJobs()

    def tearDown(self):
        self.jobs.stop()

    def test_late_scene_result_discarded(self):
        release = threading.Event()
        self.jobs.request('snapshot', lambda cancel, report: (release.wait(1), 'old')[1])
        self.jobs.invalidate()
        self.jobs.request('snapshot', lambda cancel, report: 'new')
        release.set()
        events = wait_for(self.jobs, lambda events: any(event[2] == 'new' for event in events))
        self.assertEqual([event[2] for event in events if event[1] == 'result'], ['new'])

    def test_burst_coalesces_and_never_runs_same_lane_concurrently(self):
        release = threading.Event()
        calls = []
        self.jobs.request('nas', lambda cancel, report: (calls.append(0), release.wait(1), 0)[-1])
        for index in range(1, 20):
            self.jobs.request('nas', lambda cancel, report, index=index: (calls.append(index), index)[1])
        release.set()
        events = wait_for(self.jobs, lambda events: any(event[2] == 19 for event in events))
        self.assertEqual(calls, [0, 19])
        self.assertEqual([event[2] for event in events if event[1] == 'result'], [19])

    def test_independent_kitsu_lane_does_not_restart_nas(self):
        release = threading.Event()
        generation = self.jobs.request('nas', lambda cancel, report: (release.wait(1), 'nas')[1])
        self.jobs.request('kitsu', lambda cancel, report: 'kitsu')
        events = wait_for(self.jobs, lambda events: any(event[2] == 'kitsu' for event in events))
        self.assertEqual(self.jobs.generations['nas'], generation)
        self.assertFalse(self.jobs.running['nas'][1].is_set())
        release.set()

    def test_invalidate_during_event_delivery_discards_already_queued_old_results(self):
        self.jobs.generations.update(identity=1, nas=1)
        self.jobs.events.put(('identity', 1, 'result', 'new scene'))
        self.jobs.events.put(('nas', 1, 'result', 'old scene'))
        events = iter(self.jobs.poll())
        self.assertEqual(next(events)[0], 'identity')
        # Scene changes while processing the first event on the GUI thread.
        self.jobs.generations['nas'] += 1
        self.assertEqual(list(events), [])

    def test_stop_is_bounded_and_disables_publish(self):
        release = threading.Event()
        self.jobs.request('nas', lambda cancel, report: release.wait(2))
        start = time.monotonic()
        self.jobs.stop()
        self.assertLess(time.monotonic() - start, 0.6)
        self.assertIsNone(self.jobs.request('kitsu', lambda cancel, report: 1))
        release.set()
        self.assertEqual(list(self.jobs.poll()), [])

    def test_worker_exception_is_explicit_failure(self):
        def broken(cancel, report):
            raise OSError('NAS unavailable')
        self.jobs.request('nas', broken)
        events = wait_for(self.jobs, lambda events: bool(events))
        self.assertEqual(events[0], ('nas', 'error', 'NAS unavailable'))


class NasInventoryTests(unittest.TestCase):
    def test_ae_inventory_needs_no_filesystem_and_never_overlays_actual_values(self):
        snapshot = {'footage': [{'footageId': '4', 'path': 'Z:/task/v0001/beauty/a.exr',
                                'name': 'A', 'fps': '24', 'width': '1920', 'startFrame': '1001'}], 'comps': []}
        nas = {snapshot['footage'][0]['path']: {'published': {'fps': 30, 'startframe': 1}}}
        with patch.object(refresh.os, 'scandir', side_effect=AssertionError('GUI scan')):
            tree = refresh.build_inventory(snapshot, lambda path, name: ('SQ-SH', 'Lighting', 'beauty', '3D Renders', 'render'), nas)
        row = tree['3D Renders']['SQ-SH']['Lighting']['beauty'][0]
        self.assertEqual((row['fps'], row['startFrame']), ('24', '1001'))
        self.assertEqual(row['published']['fps'], 30)
        self.assertEqual(row['versionInfo']['checkState'], 'unchecked')
        self.assertFalse(row['isLatest'])

    def test_shared_version_and_metadata_reads_deduplicated_and_json_only_not_media(self):
        with tempfile.TemporaryDirectory() as root:
            task = os.path.join(root, 'Lighting')
            os.makedirs(os.path.join(task, 'v0001', 'beauty'))
            os.makedirs(os.path.join(task, 'v0002'))
            for name in ['a.1001.exr', 'b.1001.exr']:
                with open(os.path.join(task, 'v0001', 'beauty', name), 'w') as handle:
                    handle.write('fixture')
            with open(os.path.join(task, 'v0002', 'versioninfo.json'), 'w') as handle:
                json.dump({}, handle)
            paths = [os.path.join(task, 'v0001', 'beauty', name) for name in ['a.1001.exr', 'b.1001.exr']]
            result = refresh.check_nas({'footage': [{'path': path} for path in paths]}, {}, threading.Event(), lambda value: None)
            self.assertEqual((result['directoryScans'], result['metadataReads']), (1, 1))
            for path in paths:
                self.assertEqual(result['paths'][path]['versionInfo']['allVersions'], ['v0001'])

    def test_nas_failure_retains_last_known_versions_and_marks_stale(self):
        path = 'Z:/task/v0001/beauty/file.exr'
        previous = {path: {'versionInfo': {'currentVersion': 'v0001', 'latestVersion': 'v0002', 'allVersions': ['v0002', 'v0001']}}}
        with patch.object(refresh.os, 'scandir', side_effect=OSError('unavailable')):
            result = refresh.check_nas({'footage': [{'path': path}]}, previous, threading.Event(), lambda value: None)
        self.assertTrue(result['errors'])
        self.assertEqual(result['paths'][path]['versionInfo']['allVersions'], ['v0002', 'v0001'])
        self.assertEqual(result['paths'][path]['versionInfo']['checkState'], 'stale')


class KitsuWorkerTests(unittest.TestCase):
    def fixture_session(self, payloads, calls):
        class Session:
            def __init__(self):
                self.headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def get(self, url, timeout):
                calls.append((url, timeout))
                class Response:
                    def raise_for_status(self):
                        pass
                    def json(self):
                        return payloads[url.split('/data/')[1]]
                return Response()
        return Session

    def test_batch_shots_resolution_and_episodes_without_manager_calls(self):
        calls = []
        payloads = {'projects': [{'id': 'prj', 'name': 'Demo', 'fps': '24', 'resolution': [1920, 1080]}],
                    'projects/prj/sequences': [{'id': 'seq', 'name': 'SQ01', 'parent_id': 'ep'}],
                    'projects/prj/episodes': [{'id': 'ep', 'name': 'EP01'}],
                    'projects/prj/shots': [{'id': str(i), 'name': 'SH%03d' % i, 'parent_id': 'seq',
                                            'data': {'frame_in': 1001, 'frame_out': 1100, 'resolution_id': 'r'}} for i in range(10)],
                    'resolutions/r': {'name': '2048x1152'}}
        result = refresh.fetch_kitsu({'host': 'https://fixture/api', 'token': 'fixture', 'projectName': 'Demo'},
                                     threading.Event(), lambda value: None, self.fixture_session(payloads, calls))
        self.assertEqual(len(calls), 5)  # No per-shot queries; shared resolution fetched once.
        self.assertTrue(all(timeout == (5, 20) for _, timeout in calls))
        self.assertEqual(result['shots'][0]['sequence'], 'EP01 - SQ01')
        self.assertEqual(result['shots'][0]['frameRange'], '1001-1100')
        self.assertEqual(result['shots'][0]['width'], 2048)
        self.assertEqual(result['shots'][0]['fps'], 24)

    def test_auth_unavailable_does_not_open_login_or_contact_network(self):
        with self.assertRaisesRegex(ValueError, 'not authenticated'):
            refresh.fetch_kitsu(None, threading.Event(), lambda value: None,
                               lambda: self.fail('Network used without auth'))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        path = os.path.join(SCRIPTS, 'footage_tracker', 'refresh_controller.py')
        with open(path, encoding='utf-8') as handle:
            parsed = ast.parse(handle.read())
        node = next(node for node in parsed.body if isinstance(node, ast.ClassDef))
        class Timer:
            def __init__(self, parent):
                self.timeout = SimpleNamespace(connect=lambda callback: None)
            def setInterval(self, value):
                pass
            def start(self):
                pass
            def stop(self):
                pass
        namespace = {'QObject': object, 'QTimer': Timer, 'QApplication': SimpleNamespace(instance=lambda: None),
                     'helixae_refresh': refresh, 'copy': copy, 'time': time, 'json': json}
        exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), namespace)
        self.controller = namespace['RefreshController'](SimpleNamespace(core=SimpleNamespace(projectPath='P')))
        self.controller._progress = lambda: None

    def tearDown(self):
        self.controller.stop()

    def test_prepare_after_identity_probe_without_opening_dialog(self):
        snapshot = {'scene': {'path': 'P/shot.aep', 'token': '1'}, 'footage': [], 'comps': [], 'snapshotSeconds': 0.01}
        controller = self.controller
        controller._kitsu_after_snapshot = False
        controller.refresh_kitsu = lambda: None
        controller._request_nas = lambda: None
        with patch.object(refresh, 'scene_identity', return_value=snapshot['scene']), \
                patch.object(refresh, 'collect_snapshot', return_value=snapshot):
            deadline = time.monotonic() + 2
            while controller.snapshot is None and time.monotonic() < deadline:
                controller._poll()
                time.sleep(0.002)
        self.assertIs(controller.snapshot, snapshot)
        self.assertIsNone(controller.tracker)  # Never constructs a dialog/tracker.

    def test_cached_attach_does_not_rescan_or_query_ae(self):
        controller = self.controller
        controller.snapshot = {'footage': [], 'comps': []}
        controller._apply_kitsu = lambda: None
        tracker = SimpleNamespace(dlg_footage=None)
        controller.attach(tracker)
        self.assertEqual(controller.jobs.generations, {})
        self.assertTrue(controller._render_due)

    def test_failed_snapshot_preserves_last_good_inventory(self):
        controller = self.controller
        last_good = {'scene': {'path': 'P/shot.aep', 'token': '1'}, 'footage': [], 'comps': []}
        controller.snapshot = last_good
        controller._next_probe = time.monotonic() + 60
        def broken(cancel, report):
            raise ValueError('Bridge unavailable')
        with patch.object(refresh, 'collect_snapshot', broken):
            controller.refresh_footage()
            deadline = time.monotonic() + 2
            while 'snapshot' not in controller.errors and time.monotonic() < deadline:
                controller._poll()
                time.sleep(0.002)
        self.assertIs(controller.snapshot, last_good)
        self.assertIn('Bridge unavailable', controller.errors['snapshot'])

    def test_kitsu_request_does_not_request_snapshot_or_nas(self):
        controller = self.controller
        controller._capture_kitsu = lambda: {}
        with patch.object(refresh, 'fetch_kitsu', return_value={'shots': [], 'seconds': 0, 'requests': 0}):
            controller.refresh_kitsu()
        self.assertEqual(set(controller.jobs.generations), {'kitsu'})


class PreparedCellTests(unittest.TestCase):
    def test_enrichment_keeps_leaf_identity_and_does_not_rebuild_tree(self):
        path = os.path.join(SCRIPTS, 'footage_tracker', 'tree_renderer.py')
        with open(path, encoding='utf-8') as handle:
            cls = next(node for node in ast.parse(handle.read()).body if isinstance(node, ast.ClassDef))
        namespace = {'Qt': SimpleNamespace(UserRole=32), 'QBrush': lambda *args: args,
                     'QColor': lambda *args: args}
        for name in ('updatePreparedCells', '_setFootageStatus'):
            method = copy.deepcopy(next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name))
            method.decorator_list = []
            exec(compile(ast.Module(body=[method], type_ignores=[]), path, 'exec'), namespace)
        class Item:
            def __init__(self):
                self.payload = {'type': 'footage', 'id': 4, 'identifier': 'Lighting', 'shot': 'SQ01-SH010'}
                self.texts = {0: 'beauty', 3: '1001-1048'}
            def data(self, column, role):
                return self.payload if column == 0 else None
            def setData(self, column, role, value):
                if column == 0:
                    self.payload = value
            def text(self, column):
                return self.texts.get(column, '')
            def setText(self, column, text):
                self.texts[column] = text
            def setBackground(self, *args):
                pass
            def setForeground(self, *args):
                pass
            def setToolTip(self, *args):
                pass
            def childCount(self):
                return 0
        item = Item()
        tree = SimpleNamespace(topLevelItemCount=lambda: 1, topLevelItem=lambda index: item,
                               clear=lambda: self.fail('Enrichment rebuilt tree'))
        tracker = SimpleNamespace(tw_footage=tree, _prepared_ignored_items={},
                                  getKitsuDataForShot=lambda shot: None,
                                  data_parser=SimpleNamespace(extractCurrentShotFromProject=lambda: 'SQ01-SH010'),
                                  startup_warnings=SimpleNamespace(_generateItemKey=lambda entry, key: entry.get('path')))
        renderer = SimpleNamespace(tracker=tracker, _createVersionWidget=lambda *args: None,
                                   _createFPSWidget=lambda *args: None, _checkAndApplyBypassStyling=lambda *args: None)
        renderer._setFootageStatus = lambda *args: namespace['_setFootageStatus'](renderer, *args)
        record = {'footageId': '4', 'name': 'Image', 'path': 'Z:/Lighting/v0001/beauty/a.exr',
                  'group': '3D Renders', 'shotName': 'SQ01-SH010', 'width': '1920', 'height': '1080',
                  'fps': '24', 'isLatest': False,
                  'versionInfo': {'currentVersion': 'v0001', 'currentVersionFull': 'v0001',
                                  'latestVersion': 'v0001', 'allVersions': ['v0001'], 'checkState': 'unchecked'}}
        hierarchy = {'3D Renders': {'SQ01-SH010': {'Lighting': {'beauty': [record]}}}}
        namespace['updatePreparedCells'](renderer, hierarchy)
        self.assertIs(tree.topLevelItem(0), item)
        self.assertEqual(item.texts[2], 'Checking…')
        self.assertEqual(tracker._cached_issue_counts['outdated'], 0)
        record['versionInfo'].update(checkState='checked', latestVersion='v0002', allVersions=['v0002', 'v0001'])
        namespace['updatePreparedCells'](renderer, hierarchy)
        self.assertIs(tree.topLevelItem(0), item)
        self.assertEqual(item.texts[2], '⚠ Outdated')
        self.assertEqual(tracker._cached_issue_counts['outdated'], 1)


@unittest.skipUnless(shutil.which('node'), 'Node required for generated ExtendScript fixture')
class SnapshotScriptTests(unittest.TestCase):
    def test_invalid_previous_project_reference_does_not_block_snapshot_identity(self):
        fixture = r'''
        const vm = require('vm');
        const oldState={path:'',token:'old'};
        Object.defineProperty(oldState,'project',{get(){throw Error('Object is invalid');}});
        const context=vm.createContext({app:{project:{file:{fsName:'Z:/open.aep'}}},
                                       $:{global:{__helixTrackerScene:oldState}}});
        process.stdout.write(vm.runInContext(SCRIPT,context));
        '''.replace('SCRIPT', json.dumps(protocol.build_get_tracker_identity()))
        result = subprocess.run(['node'], input=fixture, text=True, capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertTrue(data['result'])
        self.assertEqual(data['scene']['path'], 'Z:/open.aep')
        self.assertNotEqual(data['scene']['token'], 'old')

    def test_identity_probe_is_cheap_and_distinguishes_same_path_reopen_and_save_as(self):
        fixture = r'''
        const vm = require('vm');
        const project=() => ({file:{fsName:'Z:/same.aep'}, get numItems(){throw Error('Full scan in identity probe');}});
        const context=vm.createContext({app:{project:project()}, $:{global:{}}});
        const probe=() => JSON.parse(vm.runInContext(SCRIPT,context)).scene;
        const first=probe(), same=probe();
        context.app.project=project(); const reopened=probe();
        context.app.project.file.fsName='Z:/saved-as.aep'; const saved=probe();
        context.app.project.file=null; const unsaved=probe();
        process.stdout.write(JSON.stringify({first,same,reopened,saved,unsaved}));
        '''.replace('SCRIPT', json.dumps(protocol.build_get_tracker_identity()))
        result = subprocess.run(['node'], input=fixture, text=True, capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data['first'], data['same'])
        self.assertNotEqual(data['first']['token'], data['reopened']['token'])
        self.assertNotEqual(data['reopened']['token'], data['saved']['token'])
        self.assertEqual(data['unsaved']['path'], '')

    def test_one_enumeration_one_layer_traversal_and_parent_map(self):
        fixture = r'''
        const vm = require('vm');
        let itemCalls = 0, layerCalls = 0;
        function FileSource(file) {this.file=file; this.isStill=false; this.nativeFrameRate=24; this.conformFrameRate=0;}
        function FootageItem() {
            this.id=10; this.name="Client's éclair.1001.exr";
            this.file={fsName:'Z:/task/v0001/beauty/image.1001.exr',name:'image.1001.exr'};
            this.frameRate=24; this.duration=2; this.width=1920; this.height=1080;
            this.mainSource=new FileSource(this.file); this.parentFolder=null;
        }
        function CompItem(id, name, sources) {
            Object.assign(this, {id, name, width:1920, height:1080, duration:2,
                frameRate:24, frameDuration:1/24, displayStartTime:0, pixelAspect:1,
                bgColor:[0,0,0], workAreaStart:0, workAreaDuration:2, parentFolder:null,
                numLayers:sources.length});
            this.layer=function(n) {layerCalls++; return {source:sources[n-1]};};
        }
        const footage=new FootageItem();
        const child=new CompItem(20,'Precomp', [footage]);
        const parent=new CompItem(30,'Main', [child,child,footage]);
        const items=[footage,child,parent];
        const app={project:{numItems:3, file:{fsName:'Z:/scene.aep'}, xmpPacket:'',
            item(n) {itemCalls++; return items[n-1];}}};
        const context={app, FootageItem, CompItem, FileSource, $:{global:{}}};
        const output=JSON.parse(vm.runInNewContext(SCRIPT,context));
        process.stdout.write(JSON.stringify({output,itemCalls,layerCalls}));
        '''.replace('SCRIPT', json.dumps(protocol.build_tracker_snapshot()))
        result = subprocess.run(['node'], input=fixture, text=True, capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertTrue(data['output']['result'], data['output'])
        self.assertEqual(data['itemCalls'], 3)
        self.assertEqual(data['layerCalls'], 4)
        self.assertEqual(data['output']['comps'][0]['parentComps'], 'Main')
        self.assertTrue(data['output']['comps'][0]['isPrecomp'])
        snapshot, error = protocol.parse_tracker_snapshot(json.dumps(data['output']))
        self.assertIsNone(error)
        self.assertEqual(snapshot['footage'][0]['startFrame'], '1001')
        self.assertEqual(snapshot['footage'][0]['endFrame'], '1048')

    def test_snapshot_rejects_missing_scene_and_failed_queries(self):
        for value in [None, b'', json.dumps({'result': False}), json.dumps({'result': True})]:
            with self.subTest(value=value):
                snapshot, error = protocol.parse_tracker_snapshot(value)
                self.assertIsNone(snapshot)
                self.assertTrue(error)
