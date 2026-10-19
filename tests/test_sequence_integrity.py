import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Scripts'))
import helixae_sequence as sequence
import helixae_refresh as refresh
import helixae_protocol as protocol
sys.path.pop(0)


class IntegrityTests(unittest.TestCase):
    def test_gaps_empty_files_and_aov_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            for name, content in [('Beauty.1001.exr', b'a'), ('Beauty.1003.exr', b''),
                                  ('Depth.1002.exr', b'a'), ('Beauty.1002.png', b'a')]:
                Path(folder, name).write_bytes(content)
            value = sequence.check_sequences([str(Path(folder, 'Beauty.1001.exr'))], threading.Event(), lambda v: None)
            row = value['results'][0]
            self.assertEqual(row['missing'], [[1002, 1002]])
            self.assertEqual(row['empty'], ['Beauty.1003.exr'])
            self.assertEqual(row['range'], [1001, 1003])
            self.assertEqual(row['files'], 2)
            self.assertFalse(row['errors'])

    def test_huge_gap_is_one_range_not_million_frame_allocation(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('shot.00000001.exr', 'shot.99999999.exr'):
                Path(folder, name).write_bytes(b'a')
            value = sequence.check_sequences([str(Path(folder, 'shot.00000001.exr'))], threading.Event(), lambda v: None)
            self.assertEqual(value['results'][0]['missing'], [[2, 99999998]])

    def test_duplicate_paths_read_once_and_remain_unmodified(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "Client's Beauty.1001.exr")
            path.write_bytes(b'original')
            with patch.object(sequence.os, 'listdir', wraps=os.listdir) as listing:
                value = sequence.check_sequences([str(path)] * 3, threading.Event(), lambda v: None)
            self.assertEqual(listing.call_count, 1)
            self.assertEqual(len(value['results']), 1)
            self.assertEqual(path.read_bytes(), b'original')

    def test_failed_directory_never_reports_success(self):
        with patch.object(sequence.os, 'listdir', side_effect=PermissionError('NAS unavailable')):
            row = sequence.check_sequences(['/missing/Beauty.1001.exr'], threading.Event(), lambda v: None)['results'][0]
        self.assertIn('NAS unavailable', row['errors'][0])
        self.assertIn('Check failed', sequence.format_results({'results': [row], 'canceled': False}))

    def test_cancel_before_scan(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(sequence.os, 'listdir') as listing:
            value = sequence.check_sequences(['/x/Beauty.1001.exr'], cancel, lambda v: None)
        listing.assert_not_called()
        self.assertTrue(value['canceled'])

    def test_movie_and_non_numbered_image_not_sequences(self):
        self.assertIsNone(sequence.sequence_pattern('shot_v0001.mov'))
        self.assertIsNone(sequence.sequence_pattern('Beauty.exr'))

    def test_stat_error_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'Beauty.1001.exr')
            path.write_bytes(b'file')
            with patch.object(sequence.os, 'stat', side_effect=OSError('disconnected')):
                row = sequence.check_sequences([str(path)], threading.Event(), lambda v: None)['results'][0]
            self.assertTrue(row['errors'])

    def test_lane_cancel_does_not_cancel_other_checks(self):
        jobs = refresh.BackgroundJobs()
        gate = threading.Event()
        def integrity(cancel, report):
            gate.wait(1)
            return 'old integrity'
        jobs.request('integrity', integrity)
        jobs.request('nas', lambda cancel, report: 'NAS preserved')
        jobs.invalidate('integrity')
        gate.set()
        events = []
        deadline = time.monotonic() + 2
        while jobs.running and time.monotonic() < deadline:
            events.extend(jobs.poll())
            time.sleep(.005)
        events.extend(jobs.poll())
        jobs.stop()
        self.assertIn(('nas', 'result', 'NAS preserved'), events)
        self.assertNotIn(('integrity', 'result', 'old integrity'), events)


class ReplacementTests(unittest.TestCase):
    def run_script(self, rate=0, setter_failure=False, field_separation=0):
        script = protocol.build_replace_footage_by_id(10, "Z:/Client's/Beauty.1001.exr", True)
        fixture = '''const vm=require('vm');
        function FootageItem(){};
        const item=new FootageItem(); item.name='Beauty';
        item.mainSource={isStill:false, conformFrameRate:RATE, alphaMode:2, invertAlpha:true,
          fieldSeparationType:FIELDS, highQualityFieldSeparation:true};
        let qualityWrites=0, qualityValue=false;
        item.replaceWithSequence=function(file,alphabetical){
          this.mainSource={isStill:false, conformFrameRate:30};
          Object.defineProperty(this.mainSource,'highQualityFieldSeparation',{
            get(){return qualityValue;}, set(value){
              qualityWrites++; if(this.fieldSeparationType===0) throw Error('field separation is OFF');
              qualityValue=value;
            }});
          if (FAIL) Object.defineProperty(this.mainSource,'alphaMode',{set(){throw Error('unsupported')}});
        };
        function File(path){this.exists=true;this.fsName=path;}
        const result=vm.runInNewContext(SCRIPT,{app:{project:{itemByID(){return item;}}},FootageItem,File,FieldSeparationType:{OFF:0}});
        process.stdout.write(JSON.stringify({result:JSON.parse(result),rate:item.mainSource.conformFrameRate,
          alpha:item.mainSource.alphaMode,invert:item.mainSource.invertAlpha,qualityWrites,qualityValue}));
        '''.replace('RATE', json.dumps(rate)).replace('FAIL', json.dumps(setter_failure)).replace('FIELDS', json.dumps(field_separation)).replace('SCRIPT', json.dumps(script))
        result = subprocess.run(['node'], input=fixture, text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_native_rate_zero_not_forced_to_25(self):
        result = self.run_script()
        self.assertTrue(result['result']['result'])
        self.assertEqual(result['rate'], 0)
        self.assertEqual(result['alpha'], 2)
        self.assertTrue(result['invert'])

    def test_fractional_conform_rate_retained(self):
        self.assertEqual(self.run_script(23.976)['rate'], 23.976)

    def test_inactive_high_quality_field_separation_is_not_written_or_warned(self):
        result = self.run_script(field_separation=0)
        self.assertTrue(result['result']['result'])
        self.assertEqual(result['qualityWrites'], 0)
        self.assertEqual(result['result']['warnings'], [])

    def test_active_high_quality_field_separation_is_preserved(self):
        result = self.run_script(field_separation=1)
        self.assertTrue(result['result']['result'])
        self.assertEqual(result['qualityWrites'], 1)
        self.assertTrue(result['qualityValue'])
        self.assertEqual(result['result']['warnings'], [])

    def test_partial_interpretation_failure_explicit_after_successful_replacement(self):
        result = self.run_script(setter_failure=True)
        self.assertTrue(result['result']['result'])
        self.assertIn('alphaMode', result['result']['warnings'][0])


if __name__ == '__main__':
    unittest.main()
