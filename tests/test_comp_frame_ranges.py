"""Comp frame range consistency: canonical integer displayStartFrame.

Covers the stdlib helper ``helixae_protocol.comp_frame_range()``, the
protocol builders that report or mutate comp frame ranges (against a small
CPU-only After Effects DOM fixture), and the tree renderer integration that
consumes the helper.  No Prism, Qt or live After Effects required; the
builder tests execute ExtendScript in Node, like ``test_protocol_sweep``.
"""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'frame_range_protocol', ROOT / 'Scripts/helixae_protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


# A minimal CompItem/RenderQueue DOM.  displayStartTime is derived from the
# integer displayStartFrame, so the fixture behaves like After Effects for
# every value the builders write.  Individual tests override properties to
# reproduce float32 seconds and comps that refuse a mutation.
FIXTURE = r'''
const vm = require('vm');
let next = 10, all = [], undo = 0;

class OutputModule {
    constructor() { this._file = null; }
    applyTemplate(name) { this.template = name; }
    getSettings() { return {Format: 'PNG Sequence', Depth: 'Millions of Colors', Channels: 'RGB'}; }
    set file(value) { this._file = value; }
    get file() { return this._file; }
}

class RenderQueueItem {
    constructor(comp) {
        this.comp = comp;
        this.timeSpanStart = 0;
        this.timeSpanDuration = comp.duration;
        this.om = new OutputModule();
    }
    outputModule(index) { return this.om; }
    remove() { queue.items = queue.items.filter((entry) => entry !== this); }
}

class CompItem {
    constructor(name) {
        this.name = name || 'Comp';
        this.id = next++;
        this.width = 1920;
        this.height = 1080;
        this.pixelAspect = 1;
        this.frameRate = 25;
        this._startFrame = 0;
        this._duration = 5;
        this._layers = [];
        all.push(this);
    }
    get frameDuration() { return 1 / this.frameRate; }
    get displayStartFrame() { return this._startFrame; }
    set displayStartFrame(value) { this._startFrame = Math.round(value); }
    get displayStartTime() { return this._startFrame / this.frameRate; }
    set displayStartTime(value) { this._startFrame = Math.round(value * this.frameRate); }
    get duration() { return this._duration; }
    set duration(value) { this._duration = value; }
    get startTime() { return 0; }
    get workAreaStart() { return 0; }
    get workAreaDuration() { return this._duration; }
    get numLayers() { return this._layers.length; }
    layer(index) { return this._layers[index - 1]; }
}

// After Effects that keeps reporting its old start frame / frame rate: the
// mutation is silently not applied, which must never be reported as success.
class LockedStartComp extends CompItem {
    constructor(name) { super(name); this.lockedStart = this._startFrame; }
    get displayStartFrame() { return this.lockedStart; }
    set displayStartFrame(value) { }
}

class FixedRateComp extends CompItem {
    constructor(name) { super(name); this._rate = 25; }
    get frameRate() { return this._rate; }
    set frameRate(value) { if (!this.fixedRate) { this._rate = value; } }
}

// Fails once in the middle of a mutation (the duration write) but can be
// restored, because the second write goes through.
class ThrowingDurationComp extends CompItem {
    constructor(name) { super(name); this.throwDurationOnce = false; }
    get duration() { return this._duration; }
    set duration(value) {
        if (this.throwDurationOnce) {
            this.throwDurationOnce = false;
            throw new Error('duration rejected');
        }
        this._duration = value;
    }
}

// Rejects every duration write, including the restore attempt.
class StubbornDurationComp extends CompItem {
    constructor(name) { super(name); this.rejectDuration = false; }
    get duration() { return this._duration; }
    set duration(value) {
        if (this.rejectDuration) { throw new Error('duration rejected'); }
        this._duration = value;
    }
}

let queue = {
    items: [],
    get numItems() { return this.items.length; },
    item(index) { return this.items[index - 1]; }
};
queue.items.add = (comp) => {
    const item = new RenderQueueItem(comp);
    queue.items.push(item);
    return item;
};

let project = {
    activeItem: null,
    itemByID: (id) => all.find((entry) => entry.id === id),
    item: (index) => all[index - 1],
    get numItems() { return all.length; },
    renderQueue: queue
};

class File { constructor(path) { this.fsName = path; } }

let ctx = {
    JSON, Math, CompItem, File, GetSettingsFormat: {STRING: 1},
    app: {
        project,
        beginUndoGroup: () => { undo++; },
        endUndoGroup: () => { undo--; }
    }
};

function run(script) { return JSON.parse(vm.runInNewContext(script, ctx)); }
'''


def _record(**overrides):
    record = {
        'compId': '7',
        'name': 'SQ01_SH0010_main',
        'duration': '20.0',
        'frameRate': '25',
        'displayStartFrame': 0,
        'displayStartTime': '0.0',
        'inPoint': '0.0',
    }
    record.update(overrides)
    return record


class CompFrameRangeHelperTests(unittest.TestCase):
    """comp_frame_range() is the single Python source of truth."""

    # Values read live from AE 2025 test comps (500 frames).  The Project
    # panel showed In Point 01001 for the aligned starts and 01000 for the
    # starts AE stored just below frame 1001, at every frame rate.
    AE_STARTS = (
        (24, '41.7083333333333', '41.7083320617676'),
        (30, '33.3666666666667', '33.3666648864746'),
        (60, '16.6833333333333', '16.6833324432373'),
    )

    def test_aligned_start_matches_ae_project_panel(self):
        for fps, aligned, _ in self.AE_STARTS:
            record = _record(displayStartFrame=1001, displayStartTime=aligned,
                             inPoint=aligned, frameRate=str(fps),
                             duration=repr(500 / fps))
            self.assertEqual(p.comp_frame_range(record), (1001, 1500), fps)

    def test_start_below_frame_shows_ae_start_not_display_start_frame(self):
        # displayStartFrame still reads 1001, but AE shows and uses 1000:
        # the tracker must show 1000 so Kitsu's 1001 is flagged.
        for fps, _, below in self.AE_STARTS:
            record = _record(displayStartFrame=1001, displayStartTime=below,
                             inPoint=below, frameRate=str(fps),
                             duration=repr(500 / fps))
            self.assertEqual(p.comp_frame_range(record), (1000, 1499), fps)

    def test_zero_start_frame_is_valid(self):
        record = _record(displayStartFrame=0, displayStartTime='0', frameRate='25',
                         duration='5')
        self.assertEqual(p.comp_frame_range(record), (0, 124))

    def test_negative_start_frame_is_valid(self):
        record = _record(displayStartFrame=-10, displayStartTime='-0.4166667',
                         inPoint='-0.4166667', frameRate='24', duration='2')
        self.assertEqual(p.comp_frame_range(record), (-10, 37))

    def test_display_start_frame_only_without_seconds(self):
        record = _record(displayStartFrame=1000.99999, frameRate='30',
                         duration='16.666666666666668')
        record.pop('displayStartTime')
        record.pop('inPoint')
        self.assertEqual(p.comp_frame_range(record), (1001, 1500))

    def test_missing_display_start_frame_falls_back_to_seconds(self):
        record = _record(frameRate='30', duration='16.666666666666668')
        record.pop('displayStartFrame')
        record['displayStartTime'] = '33.366666666666667'
        self.assertEqual(p.comp_frame_range(record), (1001, 1500))

    def test_malformed_display_start_frame_falls_back_to_in_point(self):
        record = _record(displayStartFrame='N/A', inPoint='33.366666666666667',
                         frameRate='30', duration='16.666666666666668')
        record.pop('displayStartTime')
        self.assertEqual(p.comp_frame_range(record), (1001, 1500))

    def test_invalid_display_start_time_falls_back_to_in_point(self):
        record = _record(displayStartFrame='N/A', displayStartTime='N/A',
                         inPoint='33.366666666666667', frameRate='30',
                         duration='16.666666666666668')
        self.assertEqual(p.comp_frame_range(record), (1001, 1500))

    def test_unrepresentable_values_raise(self):
        with self.assertRaises(ValueError):
            p.comp_frame_range(_record(frameRate='1e308', duration='1e308'))
        with self.assertRaises(ValueError):
            p.comp_frame_range(_record(displayStartFrame='N/A',
                                       displayStartTime='1e308', frameRate='2',
                                       duration='10'))

    def test_parsed_comp_record_shape_is_supported(self):
        # parse_comp_records stringifies every field, including "N/A" values.
        response = json.dumps([
            {'compId': 7, 'name': 'comp', 'duration': '', 'frameRate': ''},
        ])
        records, error = p.parse_comp_records(response)
        self.assertIsNone(error)
        with self.assertRaises(ValueError):
            p.comp_frame_range(records[0])

    def test_invalid_inputs_raise_instead_of_inventing_a_range(self):
        cases = (
            _record(frameRate='fast'),
            _record(frameRate='0'),
            _record(frameRate='-30'),
            _record(frameRate=''),
            _record(frameRate='nan'),
            _record(duration=''),
            _record(duration='N/A'),
            _record(duration='0'),
            _record(duration='-1'),
            _record(displayStartFrame='', displayStartTime='', inPoint=''),
        )
        for record in cases:
            with self.assertRaises(ValueError, msg=repr(record)):
                p.comp_frame_range(record)
        with self.assertRaises(ValueError):
            p.comp_frame_range(None)
        with self.assertRaises(ValueError):
            p.comp_frame_range(['not', 'a', 'dict'])

    def test_fractional_frame_rate(self):
        record = _record(displayStartFrame=1001, frameRate='23.976',
                         displayStartTime=repr(1001 / 23.976),
                         inPoint=repr(1001 / 23.976),
                         duration='20.854187520854188')
        self.assertEqual(p.comp_frame_range(record), (1001, 1500))


class ProtocolCompFrameRangeTests(unittest.TestCase):
    """Builders read/write the integer start frame and verify their work."""

    def execute(self, script, setup, inspect='({})'):
        code = (FIXTURE + setup
                + '\nlet result = run(' + json.dumps(script) + ');'
                + 'console.log(JSON.stringify({result, state: ' + inspect
                + ', undo}));')
        output = subprocess.run(['node', '-e', code], check=True,
                                capture_output=True, text=True)
        return json.loads(output.stdout)

    def comp_setup(self, frame_rate='25', start_frame='0', frames='500'):
        return (
            "comp = new CompItem('SQ01_SH0010');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = %s;\n"
            "comp.displayStartFrame = %s;\n"
            "comp.duration = %s / comp.frameRate;\n"
            % (frame_rate, start_frame, frames)
        )

    # -- set_comp_fps -----------------------------------------------------

    def test_set_fps_preserves_integer_start_and_frame_count(self):
        out = self.execute(
            p.build_set_comp_fps(10, 30), self.comp_setup(),
            '({start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate),'
            ' rate: comp.frameRate, duration: comp.duration})')
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['result']['startFrame'], 0)
        self.assertEqual(out['result']['endFrame'], 499)
        self.assertEqual(out['result']['frameCount'], 500)
        self.assertEqual(out['state']['start'], 0)
        self.assertEqual(out['state']['frames'], 500)
        self.assertEqual(out['state']['rate'], 30)
        self.assertAlmostEqual(out['state']['duration'], 500 / 30.0, places=9)
        self.assertEqual(out['undo'], 0)

    def test_set_fps_keeps_1001_at_same_rate(self):
        out = self.execute(
            p.build_set_comp_fps(10, 25), self.comp_setup(start_frame='1001'),
            '({start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate)})')
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['state'], {'start': 1001, 'frames': 500})

    def test_set_fps_fractional_rate_keeps_frames(self):
        out = self.execute(
            p.build_set_comp_fps(10, 23.976),
            self.comp_setup(frame_rate='25', start_frame='1001', frames='500'),
            '({start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate),'
            ' duration: comp.duration})')
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['result']['frameRate'], 23.976)
        self.assertEqual(out['result']['startFrame'], 1001)
        self.assertEqual(out['result']['endFrame'], 1500)
        self.assertEqual(out['result']['frameCount'], 500)
        self.assertEqual(out['state']['start'], 1001)
        self.assertEqual(out['state']['frames'], 500)
        self.assertAlmostEqual(out['state']['duration'], 500 / 23.976, places=9)

    def test_set_fps_keeps_zero_and_negative_starts(self):
        for start_frame in ('0', '-10'):
            out = self.execute(
                p.build_set_comp_fps(10, 50),
                self.comp_setup(start_frame=start_frame, frames='125'),
                '({start: comp.displayStartFrame,'
                ' frames: Math.round(comp.duration * comp.frameRate)})')
            self.assertTrue(out['result']['result'], out['result'])
            self.assertEqual(out['state'], {'start': int(start_frame),
                                            'frames': 125})

    def test_set_fps_reports_refused_mutation_as_failure(self):
        setup = (
            "comp = new FixedRateComp('Locked');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 25;\n"
            "comp.displayStartFrame = 1001;\n"
            "comp.duration = 20;\n"
            "comp.fixedRate = true;\n"
        )
        out = self.execute(p.build_set_comp_fps(10, 30), setup,
                           '({rate: comp.frameRate, start: comp.displayStartFrame})')
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'verification_failed')
        self.assertEqual(out['result']['expectedStartFrame'], 1001)
        self.assertTrue(out['result']['restored'])
        self.assertEqual(out['result']['restoreErrors'], [])
        self.assertEqual(out['result']['restoredStartFrame'], 1001)
        self.assertEqual(out['state']['rate'], 25)
        self.assertEqual(out['undo'], 0)

    def test_set_fps_restores_after_partial_failure(self):
        setup = (
            "comp = new ThrowingDurationComp('Partial');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 25;\n"
            "comp.displayStartFrame = 1001;\n"
            "comp.duration = 20;\n"
            "comp.throwDurationOnce = true;\n"
        )
        out = self.execute(
            p.build_set_comp_fps(10, 30), setup,
            '({rate: comp.frameRate, start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate)})')
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'mutation_failed')
        self.assertTrue(out['result']['restored'])
        self.assertEqual(out['result']['restoreErrors'], [])
        self.assertEqual(out['result']['restoredStartFrame'], 1001)
        self.assertEqual(out['result']['restoredFrameRate'], 25)
        self.assertEqual(out['state'], {'rate': 25, 'start': 1001, 'frames': 500})
        self.assertEqual(out['undo'], 0)

    def test_set_fps_reports_restore_failure(self):
        setup = (
            "comp = new StubbornDurationComp('Stubborn');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 25;\n"
            "comp.displayStartFrame = 1001;\n"
            "comp.duration = 20;\n"
            "comp.rejectDuration = true;\n"
        )
        out = self.execute(p.build_set_comp_fps(10, 30), setup)
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'mutation_failed')
        self.assertFalse(out['result']['restored'])
        self.assertTrue(out['result']['restoreErrors'])
        self.assertIn('not fully restored', out['result']['details'])
        self.assertEqual(out['undo'], 0)

    # -- set_comp_frame_range --------------------------------------------

    def test_frame_range_uses_integer_start_frame(self):
        out = self.execute(
            p.build_set_comp_frame_range(10, 1001, 1500, 30),
            self.comp_setup(frame_rate='30', start_frame='0', frames='1'),
            '({start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate),'
            ' duration: comp.duration})')
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['result']['startFrame'], 1001)
        self.assertEqual(out['result']['endFrame'], 1500)
        self.assertEqual(out['result']['frameCount'], 500)
        self.assertEqual(out['state']['start'], 1001)
        self.assertEqual(out['state']['frames'], 500)
        self.assertEqual(out['undo'], 0)

    def test_frame_range_uses_actual_comp_rate_over_stale_record(self):
        # The record still says 25 fps but the comp is 30 fps: 500 requested
        # frames must stay 500 frames at the comp's real rate.
        out = self.execute(
            p.build_set_comp_frame_range(10, 1001, 1500, 25),
            self.comp_setup(frame_rate='30', start_frame='0', frames='1'),
            '({start: comp.displayStartFrame,'
            ' frames: Math.round(comp.duration * comp.frameRate),'
            ' duration: comp.duration})')
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['result']['startFrame'], 1001)
        self.assertEqual(out['result']['endFrame'], 1500)
        self.assertEqual(out['result']['frameCount'], 500)
        self.assertEqual(out['state']['start'], 1001)
        self.assertEqual(out['state']['frames'], 500)
        self.assertAlmostEqual(out['state']['duration'], 500 / 30.0, places=9)
        self.assertEqual(out['undo'], 0)

    def test_frame_range_zero_and_negative_start(self):
        for start_frame, end_frame in ((0, 124), (-10, 14)):
            out = self.execute(
                p.build_set_comp_frame_range(10, start_frame, end_frame, 25),
                self.comp_setup(frame_rate='25', frames='1'),
                '({start: comp.displayStartFrame,'
                ' frames: Math.round(comp.duration * comp.frameRate)})')
            self.assertTrue(out['result']['result'], out['result'])
            self.assertEqual(out['result']['startFrame'], start_frame)
            self.assertEqual(out['result']['endFrame'], end_frame)
            self.assertEqual(out['state'], {'start': start_frame,
                                            'frames': end_frame - start_frame + 1})

    def test_frame_range_reports_refused_mutation_as_failure(self):
        setup = (
            "comp = new LockedStartComp('Locked');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 25;\n"
            "comp.lockedStart = 1000;\n"
            "comp.duration = 20;\n"
        )
        out = self.execute(p.build_set_comp_frame_range(10, 1001, 1500, 25),
                           setup, '({start: comp.displayStartFrame})')
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'verification_failed')
        self.assertEqual(out['result']['actualStartFrame'], 1000)
        self.assertTrue(out['result']['restored'])
        self.assertEqual(out['result']['restoredStartFrame'], 1000)
        self.assertEqual(out['undo'], 0)

    def test_frame_range_restores_after_partial_failure(self):
        setup = (
            "comp = new ThrowingDurationComp('Partial');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 30;\n"
            "comp.displayStartFrame = 1001;\n"
            "comp.duration = 500 / 30;\n"
            "comp.throwDurationOnce = true;\n"
        )
        out = self.execute(p.build_set_comp_frame_range(10, 100, 199, 30),
                           setup, '({start: comp.displayStartFrame,'
                                  ' frames: Math.round(comp.duration * comp.frameRate)})')
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'mutation_failed')
        self.assertTrue(out['result']['restored'])
        self.assertEqual(out['result']['restoreErrors'], [])
        self.assertEqual(out['state'], {'start': 1001, 'frames': 500})
        self.assertEqual(out['undo'], 0)

    def test_frame_range_reports_restore_failure(self):
        setup = (
            "comp = new StubbornDurationComp('Stubborn');\n"
            "project.activeItem = comp;\n"
            "comp.frameRate = 30;\n"
            "comp.displayStartFrame = 1001;\n"
            "comp.duration = 500 / 30;\n"
            "comp.rejectDuration = true;\n"
        )
        out = self.execute(p.build_set_comp_frame_range(10, 100, 199, 30), setup)
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['result']['reason'], 'mutation_failed')
        self.assertFalse(out['result']['restored'])
        self.assertTrue(out['result']['restoreErrors'])
        self.assertIn('not fully restored', out['result']['details'])
        self.assertEqual(out['undo'], 0)

    # -- queries ----------------------------------------------------------

    def test_collect_comp_records_reports_integer_range(self):
        script = p.build_collect_comp_records()
        out = self.execute(
            script,
            self.comp_setup(frame_rate='30', start_frame='1001', frames='500'),
            'run(%s)' % json.dumps(script))
        self.assertEqual(len(out['state']), 1)
        record = out['state'][0]
        self.assertEqual(record['startFrame'], 1001)
        self.assertEqual(record['endFrame'], 1500)
        self.assertEqual(record['displayStartFrame'], 1001)

    def test_collect_comp_records_ignores_conflicting_seconds(self):
        setup = self.comp_setup(frame_rate='30', start_frame='1001', frames='500')
        setup += (
            "Object.defineProperty(comp, 'displayStartTime',"
            " {get: () => 1000 / 30, configurable: true});\n"
        )
        script = p.build_collect_comp_records()
        out = self.execute(script, setup, 'run(%s)' % json.dumps(script))
        record = out['state'][0]
        self.assertEqual(record['displayStartFrame'], 1001)
        self.assertEqual(record['startFrame'], 1001)
        self.assertEqual(record['endFrame'], 1500)
        records, error = p.parse_comp_records(json.dumps(out['state']))
        self.assertIsNone(error)
        self.assertEqual(records[0]['startFrame'], '1001')

    def test_get_comp_info_reports_integer_range(self):
        out = self.execute(
            p.build_get_comp_info(10),
            self.comp_setup(frame_rate='30', start_frame='1001', frames='500'))
        self.assertTrue(out['result']['result'], out['result'])
        self.assertEqual(out['result']['startFrame'], 1001)
        self.assertEqual(out['result']['endFrame'], 1500)
        self.assertEqual(out['result']['frameRange'], '1001-1500')
        self.assertEqual(out['result']['frameCount'], 500)

    def test_get_comp_info_falls_back_when_display_start_frame_missing(self):
        # Older AE builds / partially filled records have no usable integer.
        setup = self.comp_setup(frame_rate='30', start_frame='1001', frames='500')
        setup += (
            "Object.defineProperty(comp, 'displayStartFrame',"
            " {value: undefined, configurable: true});\n"
        )
        out = self.execute(p.build_get_comp_info(10), setup)
        self.assertEqual(out['result']['startFrame'], 1001)
        self.assertEqual(out['result']['endFrame'], 1500)

    # -- render queue ack -------------------------------------------------

    def test_render_queue_ack_uses_integer_frames(self):
        out = self.execute(
            p.build_add_to_render_queue('Z:/renders/beauty.exr', 'Lossless', 10),
            self.comp_setup(frame_rate='30', start_frame='1001', frames='500'),
            '({queued: queue.numItems, comp: queue.items[0].comp.id})')
        ack = out['result']
        self.assertTrue(ack['result'], ack)
        self.assertEqual(ack['startFrame'], 1001)
        self.assertEqual(ack['endFrame'], 1500)
        self.assertEqual(ack['frameCount'], 500)
        self.assertEqual(ack['displayStartFrame'], 1001)
        self.assertEqual(ack['fps'], 30)
        self.assertEqual(ack['compId'], '10')
        self.assertEqual(ack['queueItemIndex'], 1)
        self.assertEqual(ack['outputFile'], 'Z:/renders/beauty.exr')
        self.assertEqual(out['state'], {'queued': 1, 'comp': 10})

    def test_render_queue_ack_fractional_rate(self):
        out = self.execute(
            p.build_add_to_render_queue('Z:/renders/beauty.exr', 'Lossless', 10),
            self.comp_setup(frame_rate='23.976', start_frame='1001', frames='500'))
        ack = out['result']
        self.assertTrue(ack['result'], ack)
        self.assertEqual((ack['startFrame'], ack['endFrame']), (1001, 1500))
        self.assertEqual(ack['frameCount'], 500)

    def test_render_queue_failure_is_reported_and_cleaned_up(self):
        setup = self.comp_setup(frame_rate='30', start_frame='1001', frames='500')
        setup += "queue.items.add = (c) => new RenderQueueItem(c);\n"
        out = self.execute(
            p.build_add_to_render_queue('Z:/renders/beauty.exr', 'Lossless', 10),
            setup, '({queued: queue.numItems})')
        self.assertFalse(out['result']['result'])
        self.assertIn('not created', out['result']['details'])
        self.assertEqual(out['state']['queued'], 0)


class TreeRendererFrameRangeTests(unittest.TestCase):
    """The tracker UI must share the helper instead of re-deriving frames."""

    PATH = ROOT / 'Scripts/footage_tracker/tree_renderer.py'

    def _functions(self):
        tree = ast.parse(self.PATH.read_text(encoding='latin-1'))
        return {node.name: node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)}

    def test_all_comp_views_use_comp_frame_range(self):
        functions = self._functions()
        for name in ('updatePreparedCells', '_renderCompItem',
                     '_createCompFrameRangeWidget'):
            self.assertIn(name, functions)
            calls = [node for node in ast.walk(functions[name])
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == 'comp_frame_range']
            self.assertTrue(calls, '%s does not call comp_frame_range' % name)

    def test_frame_range_widget_shows_ae_range(self):
        tree = ast.parse(self.PATH.read_text(encoding='latin-1'))
        node = next(item for item in ast.walk(tree)
                    if isinstance(item, ast.FunctionDef)
                    and item.name == '_createCompFrameRangeWidget')
        node.decorator_list = []
        labels = []

        class QLabel:
            def __init__(self):
                labels.append(self)
                self.value = None

            def setAlignment(self, *args):
                pass

            def setText(self, text):
                self.value = text

            def text(self):
                return self.value

            def setProperty(self, *args):
                pass

            def setStyleSheet(self, *args):
                pass

        class QWidget:
            pass

        class QHBoxLayout:
            def __init__(self, *args):
                pass

            def setContentsMargins(self, *args):
                pass

            def addWidget(self, *args):
                pass

        namespace = {
            'QLabel': QLabel,
            'QWidget': QWidget,
            'QHBoxLayout': QHBoxLayout,
            'Qt': SimpleNamespace(AlignCenter=1),
            'comp_frame_range': p.comp_frame_range,
        }
        module = ast.fix_missing_locations(
            ast.Module(body=[node], type_ignores=[]))
        exec(compile(module, str(self.PATH), 'exec'), namespace)
        tracker = SimpleNamespace(
            tw_footage=SimpleNamespace(setItemWidget=lambda *args: None))
        record = _record(displayStartFrame=1001,
                         displayStartTime='33.3666648864746',
                         inPoint='33.3666648864746', frameRate='30',
                         duration='16.666666666666668')
        namespace['_createCompFrameRangeWidget'](
            SimpleNamespace(tracker=tracker), SimpleNamespace(), record, 3)
        self.assertEqual([label.value for label in labels], ['1000-1499'])


if __name__ == '__main__':
    unittest.main()
