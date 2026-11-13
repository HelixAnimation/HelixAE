"""Project Browser opening must use the long-running operation transport."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock


class SceneOpenTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'Scripts' / 'HelixAE_Functions.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        method = next(node for cls in tree.body if isinstance(cls, ast.ClassDef)
                      for node in cls.body if isinstance(node, ast.FunctionDef)
                      and node.name == 'openScene')
        method.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {}
        exec(compile(module, str(source), 'exec'), namespace)
        self.open_scene = namespace['openScene']
        self.core = Mock()
        self.facade = SimpleNamespace(ae_core=self.core,
                                      sendCmd=Mock(side_effect=AssertionError('short timeout')))

    def test_browser_uses_operation_transport_and_preserves_arguments(self):
        self.core.openScene.return_value = True
        self.assertTrue(self.open_scene(self.facade, 'browser', "Z:/Client's Job/scene.aep", True))
        self.core.openScene.assert_called_once_with('browser', "Z:/Client's Job/scene.aep", force=True)
        self.facade.sendCmd.assert_not_called()

    def test_failure_is_not_reported_as_success(self):
        self.core.openScene.return_value = False
        self.assertFalse(self.open_scene(self.facade, 'browser', 'missing.aep'))

    def test_swallowed_core_exception_is_not_success(self):
        self.core.openScene.return_value = None
        self.assertIsNone(self.open_scene(self.facade, 'browser', 'scene.aep'))


class CoreSceneOpenTests(unittest.TestCase):
    def setUp(self):
        import socket
        source = Path(__file__).resolve().parents[1] / 'Scripts' / 'helixae_core.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('openScene', 'executeAppleScript', '_execute_script')]
        for method in methods:
            method.decorator_list = []
        self.socket = MagicMock()
        self.socket.timeout = socket.timeout
        self.bridge = Mock()
        import json
        self.protocol = SimpleNamespace(
            build_open_scene=Mock(return_value='open-script'),
            parse_json_response=lambda result: (json.loads(result), None),
            ensure_json_polyfill=lambda script: script,
        )
        namespace = dict(socket=self.socket, helixae_bridge=self.bridge,
                         helixae_protocol=self.protocol)
        module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
        exec(compile(module, str(source), 'exec'), namespace)
        self.methods = namespace
        self.preparation = Mock()
        self.core = SimpleNamespace(
            core=Mock(), main=SimpleNamespace(_footage_preparation=self.preparation),
            _execute_script=Mock(return_value='{"result": true}'))

    def test_scene_open_uses_ten_minute_transport_and_confirms_success(self):
        self.assertTrue(self.methods['openScene'](self.core, None, 'scene.aep'))
        self.core._execute_script.assert_called_once_with('open-script', timeout=600.0)
        self.preparation.scene_opened.assert_called_once_with()

    def test_timeout_reports_uncertain_outcome_without_retry_or_refresh(self):
        self.core._execute_script.side_effect = self.socket.timeout('timed out')
        self.assertFalse(self.methods['openScene'](self.core, None, 'scene.aep'))
        self.core._execute_script.assert_called_once()
        self.preparation.scene_opened.assert_not_called()
        message = self.core.core.popup.call_args[0][0]
        self.assertIn('may still be loading', message)
        self.assertIn('not been cancelled', message)

    def test_unconfirmed_open_never_succeeds(self):
        self.core._execute_script.return_value = '{"result": false}'
        self.assertFalse(self.methods['openScene'](self.core, None, 'scene.aep'))
        self.preparation.scene_opened.assert_not_called()

    def test_default_transport_timeout_remains_two_minutes(self):
        self.methods['executeAppleScript'](self.core, 'query')
        self.core._execute_script.assert_called_once_with('query', timeout=120.0)

    def test_raw_transport_applies_timeout_and_preserves_frame(self):
        sock = self.socket.socket.return_value.__enter__.return_value
        self.methods['_execute_script'](self.core, 'open-script', timeout=600.0)
        sock.settimeout.assert_called_once_with(600.0)
        sock.sendall.assert_called_once_with(self.bridge.frame_ae_request.return_value)
        self.bridge.recv_ae_response.assert_called_once_with(sock)

    def test_raw_receive_timeout_reaches_operation_handler(self):
        self.bridge.recv_ae_response.side_effect = self.socket.timeout('timed out')
        with self.assertRaises(self.socket.timeout):
            self.methods['_execute_script'](self.core, 'open-script', timeout=600.0)
