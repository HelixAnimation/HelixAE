import importlib.util
import ast
import sys
import threading
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('resize_transaction', os.path.join(
    ROOT, 'Scripts', 'footage_tracker', 'resize_transaction.py'))
transaction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transaction)


class ResizeTransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = os.path.join(self.directory.name, 'image.exr')
        self.backups = os.path.join(self.directory.name, 'backup')
        self.write(self.source, b'original')

    def write(self, path, content):
        with open(path, 'wb') as stream:
            stream.write(content)

    def read(self, path):
        with open(path, 'rb') as stream:
            return stream.read()

    def render(self, source, target):
        self.assertNotEqual(source, target)
        self.assertEqual(os.path.dirname(target), os.path.dirname(source))
        self.assertEqual(os.path.splitext(target)[1], '.exr')
        self.write(target, b'resized')
        return True, None

    def test_success_retains_original_backup(self):
        self.assertEqual(transaction.replace_image(self.source, self.backups, self.render), (True, None))
        self.assertEqual(self.read(self.source), b'resized')
        self.assertEqual(self.read(os.path.join(self.backups, 'image.exr')), b'original')
        self.assertFalse(any(name.startswith('.helixae') for name in os.listdir(self.directory.name)))

    def test_partial_write_validation_failure_preserves_original(self):
        def failed(source, target):
            self.write(target, b'partial')
            return False, 'invalid channels'
        ok, reason = transaction.replace_image(self.source, self.backups, failed)
        self.assertFalse(ok)
        self.assertIn('invalid channels', reason)
        self.assertEqual(self.read(self.source), b'original')

    def test_replace_failure_preserves_original_and_backup(self):
        with patch.object(transaction.os, 'replace', side_effect=PermissionError('locked')):
            ok, reason = transaction.replace_image(self.source, self.backups, self.render)
        self.assertFalse(ok)
        self.assertIn('locked', reason)
        self.assertEqual(self.read(self.source), b'original')
        self.assertEqual(self.read(os.path.join(self.backups, 'image.exr')), b'original')

    def test_existing_backup_never_overwritten(self):
        os.makedirs(self.backups)
        backup = os.path.join(self.backups, 'image.exr')
        self.write(backup, b'earlier original')
        self.assertFalse(transaction.replace_image(self.source, self.backups, self.render)[0])
        self.assertEqual(self.read(backup), b'earlier original')
        self.assertEqual(self.read(self.source), b'original')

    def test_external_source_change_is_not_overwritten(self):
        def changed(source, target):
            self.render(source, target)
            self.write(source, b'external update')
            return True, None
        self.assertFalse(transaction.replace_image(self.source, self.backups, changed)[0])
        self.assertEqual(self.read(self.source), b'external update')

    def test_empty_output_rejected(self):
        self.assertFalse(transaction.replace_image(
            self.source, self.backups, lambda *_: (True, None))[0])
        self.assertEqual(self.read(self.source), b'original')

    def test_cancel_between_files_has_accurate_counts(self):
        second = os.path.join(self.directory.name, 'second.exr')
        self.write(second, b'second original')
        result = transaction.resize_batch([self.source, second], self.backups,
            self.render, canceled=lambda: self.read(self.source) == b'resized')
        self.assertEqual((result['success'], result['failed'], result['skipped']), (1, 0, 1))
        self.assertTrue(result['canceled'])
        self.assertEqual(self.read(second), b'second original')

    def test_no_result_is_failure(self):
        result = transaction.resize_batch([self.source], self.backups, lambda *_: None)
        self.assertEqual((result['success'], result['failed'], result['skipped']), (0, 1, 0))

    def test_nested_action_rejected_and_guard_released(self):
        class Core:
            messages = []
            def popup(self, message):
                self.messages.append(message)
        class Owner:
            core = Core()
            @transaction.exclusive_resize_action
            def run(self, nested=False):
                if nested:
                    self.run()
                return 'done'
        owner = Owner()
        self.assertEqual(owner.run(True), 'done')
        self.assertEqual(len(owner.core.messages), 1)
        self.assertEqual(owner.run(), 'done')

    def test_cancel_is_processed_while_file_worker_is_busy(self):
        second = os.path.join(self.directory.name, 'second.exr')
        self.write(second, b'second original')
        cancel = threading.Event()
        started = threading.Event()
        main_thread = threading.get_ident()
        progress_threads = []
        def slow_render(source, target):
            self.assertNotEqual(threading.get_ident(), main_thread)
            started.set()
            # Work cannot finish until the GUI event pump handles Cancel.
            self.assertTrue(cancel.wait(2))
            return self.render(source, target)
        def pump():
            self.assertEqual(threading.get_ident(), main_thread)
            if started.is_set():
                cancel.set()
        result = transaction.run_background(
            lambda report: transaction.resize_batch(
                [self.source, second], self.backups, slow_render,
                report, cancel.is_set),
            lambda *_: progress_threads.append(threading.get_ident()), pump)
        self.assertTrue(result['canceled'])
        self.assertEqual((result['success'], result['skipped']), (1, 1))
        self.assertEqual(self.read(second), b'second original')
        self.assertTrue(progress_threads)
        self.assertEqual(set(progress_threads), {main_thread})

    def test_worker_exception_reaches_caller(self):
        def failed(report):
            raise RuntimeError('worker failed')
        with self.assertRaisesRegex(RuntimeError, 'worker failed'):
            transaction.run_background(failed, lambda *_: None, lambda: None)


class ImageResizeGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, 'Scripts', 'footage_tracker', 'image_resizer.py')
        with open(path, encoding='utf-8') as stream:
            tree = ast.parse(stream.read())
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == 'resizeImage')
        method.decorator_list = []
        namespace = {'os': os, 'OIIO_AVAILABLE': True}
        exec(compile(ast.Module(body=[method], type_ignores=[]), path, 'exec'), namespace)
        cls.resize = staticmethod(namespace['resizeImage'])

    def test_in_place_call_rejected_before_loading_library(self):
        ok, reason = self.resize(None, 'frame.exr', 'frame.exr', (64, 64), 'lanczos3')
        self.assertFalse(ok)
        self.assertIn('temporary file', reason)

    def test_deep_image_rejected_before_algorithm_or_write(self):
        buffer = SimpleNamespace(spec=lambda: SimpleNamespace(deep=True), read=lambda: True)
        backend = SimpleNamespace(ImageBuf=lambda _: buffer)
        with patch.dict(sys.modules, {'OpenImageIO': backend}):
            ok, reason = self.resize(None, 'source.exr', 'target.exr', (64, 64), 'lanczos3')
        self.assertFalse(ok)
        self.assertIn('Deep EXR', reason)
