# -*- coding: utf-8 -*-
"""Regression tests for Scripts/helixae_protocol.py (Phase 3).

Loaded by file path (like test_helixae_bridge.py) so the suite stays
stdlib-only: no Prism, no Qt, no package __init__ imports.
"""

import importlib.util
import json
import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "helixae_protocol.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("helixae_protocol", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = _load_module()


class PolyfillTests(unittest.TestCase):
    def test_polyfill_prepended_when_json_used(self):
        script = p.ensure_json_polyfill("return JSON.stringify({});")
        self.assertTrue(script.lstrip().startswith("if(typeof JSON==='undefined')"))
        self.assertIn("JSON.stringify({})", script)

    def test_no_double_wrap(self):
        once = p.ensure_json_polyfill("JSON.stringify(1);")
        twice = p.ensure_json_polyfill(once)
        self.assertEqual(once.count("if(typeof JSON==='undefined')"), 1)
        self.assertEqual(twice, once)

    def test_no_polyfill_without_json(self):
        script = "app.project.save(new File('x'));"
        self.assertEqual(p.ensure_json_polyfill(script), script)


class JsStringTests(unittest.TestCase):
    def test_apostrophe_and_quotes(self):
        embedded = p.js_string("Client's \"Job\"")
        self.assertEqual(embedded, '"Client\'s \\"Job\\""')

    def test_backslash_paths(self):
        embedded = p.js_string("Z:\\Renders\\shot_v0001")
        self.assertEqual(embedded, '"Z:\\\\Renders\\\\shot_v0001"')

    def test_unicode_is_ascii_escaped(self):
        embedded = p.js_string(u"éclair umaçã")
        self.assertTrue(embedded.startswith('"'))
        self.assertTrue(embedded.isascii())
        self.assertIn("\\u00e9", embedded)

    def test_newline_escaped(self):
        embedded = p.js_string("line1\nline2")
        self.assertEqual(embedded, '"line1\\nline2"')

    def test_bytes_accepted(self):
        self.assertEqual(p.js_string(b"abc"), '"abc"')

    def test_non_string_rejected(self):
        with self.assertRaises(TypeError):
            p.js_string(5)
        with self.assertRaises(TypeError):
            p.js_string(None)


class ResponseParsingTests(unittest.TestCase):
    def test_none_is_failure(self):
        data, error = p.parse_json_response(None)
        self.assertIsNone(data)
        self.assertIn("empty response", error)

    def test_empty_bytes_is_failure(self):
        data, error = p.parse_json_response(b"")
        self.assertIsNone(data)
        self.assertIn("empty response", error)

    def test_whitespace_is_failure(self):
        data, error = p.parse_json_response("   \n\t ")
        self.assertIsNone(data)
        self.assertIn("empty response", error)

    def test_invalid_json_is_failure(self):
        data, error = p.parse_json_response("{'result': True}")
        self.assertIsNone(data)
        self.assertIn("invalid JSON", error)

    def test_non_object_is_failure(self):
        for payload in ('[1, 2]', '42', '"text"', "null", "true"):
            data, error = p.parse_json_response(payload)
            self.assertIsNone(data, payload)
            self.assertIn("malformed", error)

    def test_valid_object(self):
        data, error = p.parse_json_response('{"result": true, "details": "ok"}')
        self.assertIsNone(error)
        self.assertEqual(data, {"result": True, "details": "ok"})

    def test_bytes_decoded_utf8(self):
        data, error = p.parse_json_response(
            '{"result": true, "name": "éclair"}'.encode("utf-8")
        )
        self.assertIsNone(error)
        self.assertEqual(data["name"], u"éclair")

    def test_array_parser(self):
        data, error = p.parse_json_array('[{"a": 1}, {"b": 2}]')
        self.assertIsNone(error)
        self.assertEqual(len(data), 2)
        data, error = p.parse_json_array('{"a": 1}')
        self.assertIsNone(data)
        self.assertIn("malformed", error)

    def test_ack_result_extraction(self):
        ok, err = p.ack_result({"result": True}, None)
        self.assertTrue(ok)
        self.assertIsNone(err)
        ok, err = p.ack_result({"result": False, "details": "nope"}, None)
        self.assertFalse(ok)
        _, err = p.ack_result({"details": "missing"}, None)
        self.assertIn("missing result", err)
        _, err = p.ack_result(None, "transport failure")
        self.assertEqual(err, "transport failure")


class BuilderValidationTests(unittest.TestCase):
    def test_set_frame_range_validates(self):
        with self.assertRaises(ValueError):
            p.build_set_frame_range("abc", 100)
        with self.assertRaises(ValueError):
            p.build_set_frame_range(100, "xyz")
        with self.assertRaises(ValueError):
            p.build_set_frame_range(200, 100)  # end before start
        script = p.build_set_frame_range("100", " 200 ")
        self.assertIn("displayStartFrame = 100;", script)
        self.assertIn("comp.duration = (200 - 100 + 1)", script)

    def test_set_fps_validates(self):
        with self.assertRaises(ValueError):
            p.build_set_fps(0)
        with self.assertRaises(ValueError):
            p.build_set_fps(-25)
        with self.assertRaises(ValueError):
            p.build_set_fps("fast")
        script = p.build_set_fps("24")
        self.assertIn("comp.frameRate = 24.0;", script)

    def test_paths_validated(self):
        for builder, args in (
            (p.build_save_scene, ("",)),
            (p.build_save_scene, ("   ",)),
            (p.build_open_scene, ("",)),
            (p.build_import_media, ("",)),
            (p.build_replace_active_item, ("",)),
            (p.build_replace_item, (1, "")),
            (p.build_add_to_render_queue, ("", "Lossless")),
            (p.build_import_footage_item, ("", "SQ01_SH0010", "chars", "beauty")),
        ):
            with self.assertRaises(ValueError, msg=builder.__name__):
                builder(*args)

    def test_replace_item_index_validated(self):
        with self.assertRaises(ValueError):
            p.build_replace_item(0, "Z:/x")
        with self.assertRaises(ValueError):
            p.build_replace_item(-3, "Z:/x")
        with self.assertRaises(ValueError):
            p.build_replace_item("one", "Z:/x")

    def test_template_validated(self):
        with self.assertRaises(ValueError):
            p.build_add_to_render_queue("Z:/out", "")
        with self.assertRaises(ValueError):
            p.build_add_to_render_queue("Z:/out", "  ")
        with self.assertRaises(ValueError):
            p.build_render_with_template("")
        with self.assertRaises(ValueError):
            p.build_render_with_template(None)

    def test_import_footage_item_validates_strings(self):
        args = ("Z:/media", "", "chars", "beauty")
        with self.assertRaises(ValueError):
            p.build_import_footage_item(*args)
        with self.assertRaises(ValueError):
            p.build_import_footage_item("Z:/media", "shot", "chars", "")
        with self.assertRaises(ValueError):
            p.build_import_footage_item("Z:/media", "shot", "chars", "aov", fps=-5)

    def test_import_footage_item_fps_embedded(self):
        script = p.build_import_footage_item("Z:/m", "s", "c", "a", fps=25)
        self.assertIn("conformFrameRate = 25.0", script)
        script = p.build_import_footage_item("Z:/m", "s", "c", "a", fps=None)
        self.assertIn("if (null !== null", script)


class BuilderShapeTests(unittest.TestCase):
    def _check_shape(self, script):
        self.assertIn("JSON.stringify", script)
        self.assertIn("try {", script)
        self.assertIn('} catch (e) {', script)
        self.assertEqual(script.count("{"), script.count("}"))
        self.assertEqual(script.count("("), script.count(")"))

    def test_query_builders_shape(self):
        for script in (
            p.build_has_active_comp(),
            p.build_get_composition_names(),
            p.build_get_frame_range(),
            p.build_get_fps(),
            p.build_get_app_version(),
            p.build_get_current_file(),
            p.build_get_footage_from_project(),
            p.build_get_output_module_templates(),
            p.build_get_active_comp_info(),
            p.build_comp_dependency_script(12),
            p.build_collect_footage_records(),
            p.build_collect_tracker_footage(),
            p.build_collect_comp_records(),
        ):
            self._check_shape(script)

    def test_mutation_builders_shape(self):
        for script in (
            p.build_set_frame_range(1, 100),
            p.build_set_fps(25),
            p.build_save_scene("Z:/p/shot.aep"),
            p.build_open_scene("Z:/p/shot.aep"),
            p.build_import_media("Z:/p/clip.mov"),
            p.build_replace_active_item("Z:/p/clip.mov"),
            p.build_replace_item(3, "Z:/p/clip.mov"),
            p.build_add_to_render_queue("Z:/out", "Lossless"),
            p.build_add_to_render_queue("Z:/out", "Lossless", 7),
            p.build_render_with_template("Lossless"),
            p.build_import_footage_item("Z:/m", "shot", "chars", "beauty"),
        ):
            self._check_shape(script)

    def test_apostrophe_path_embedding(self):
        script = p.build_save_scene("Z:/Client's Job/shot_v2.aep")
        # js_string double-quotes the literal, so apostrophes are safe
        self.assertIn('new File("Z:/Client\'s Job/shot_v2.aep");', script)

    def test_unicode_path_embedding(self):
        script = p.build_open_scene(u"C:\\Users\\DimitarHelix\\éclair\\uça.aep")
        self.assertIn("\\u00e9clair", script)
        self.assertIn("\\u00e7a.aep", script)

    def test_template_name_with_quote_embedding(self):
        script = p.build_add_to_render_queue("Z:/out", "PNG 'Helix'")
        self.assertIn('"PNG \'Helix\'"', script)

    def test_queue_builder_validates_comp_and_cleans_up(self):
        script = p.build_add_to_render_queue("Z:/out.mov", "Lossless")
        self.assertIn("instanceof CompItem", script)
        self.assertIn("renderQueueItem.remove()", script)  # cleanup path
        self.assertIn("applyTemplate(", script)

    def test_save_builder_confirms_disk_state(self):
        script = p.build_save_scene("Z:/p/shot.aep")
        self.assertIn("app.project.save(target)", script)
        self.assertIn("fromCharCode(92)", script)  # backslash normalization


class CompDependencyProtocolTests(unittest.TestCase):
    def test_active_comp_query_shape(self):
        script = p.build_get_active_comp_info()
        self.assertIn("app.project.activeItem", script)
        self.assertIn("compId: String(comp.id)", script)
        self.assertIn("compName: comp.name", script)

    def test_dependency_script_walks_nested_and_hidden_layers(self):
        script = p.build_comp_dependency_script(7)
        self.assertIn("itemByID(7)", script)
        self.assertIn("comp.numLayers", script)
        self.assertIn("walkComp(src)", script)
        self.assertIn("visitedComps", script)
        self.assertIn("instanceof FileSource", script)
        self.assertIn("file.fsName", script)
        # Visibility and enabled state must never filter the walk.
        self.assertNotIn("layer.enabled", script)
        self.assertNotIn("layer.visible", script)

    def test_dependency_script_validates_comp_id(self):
        for invalid in (0, -1, "abc", None):
            with self.assertRaises(ValueError):
                p.build_comp_dependency_script(invalid)

    def test_queue_builder_uses_explicit_comp_id(self):
        script = p.build_add_to_render_queue("Z:/out.mov", "Lossless", 7)
        self.assertIn("itemByID(7)", script)
        self.assertIn("compId: String(comp.id)", script)
        self.assertIn("compName: comp.name", script)
        self.assertNotIn("app.project.activeItem", script)

    def test_queue_builder_defaults_to_active_comp(self):
        script = p.build_add_to_render_queue("Z:/out.mov", "Lossless")
        self.assertIn("app.project.activeItem", script)

    def test_parse_dependency_success(self):
        payload = json.dumps(
            {
                "result": True,
                "composition": {"id": 9, "name": "SH010_Main"},
                "footage": [
                    {
                        "id": 1,
                        "name": "beauty",
                        "path": "Z:\\Renders\\beauty.0001.exr",
                    }
                ],
            }
        )
        parsed, error = p.parse_comp_dependency_result(payload)
        self.assertIsNone(error)
        self.assertEqual(parsed["composition"], {"id": "9", "name": "SH010_Main"})
        self.assertEqual(parsed["footage"][0]["path"], "Z:/Renders/beauty.0001.exr")

    def test_parse_dependency_valid_empty_footage(self):
        payload = json.dumps(
            {
                "result": True,
                "composition": {"id": "9", "name": "Empty"},
                "footage": [],
            }
        )
        parsed, error = p.parse_comp_dependency_result(payload)
        self.assertIsNone(error)
        self.assertEqual(parsed["footage"], [])

    def test_parse_dependency_failures(self):
        for payload in (
            None,
            b"",
            b"   ",
            "not json",
            "[]",
            json.dumps({"result": False, "details": "comp not found"}),
            json.dumps({"result": True, "footage": []}),
            json.dumps(
                {"result": True, "composition": {"id": 1, "name": "x"}}
            ),
            json.dumps(
                {
                    "result": True,
                    "composition": {"id": 1, "name": "x"},
                    "footage": [{"id": 1, "name": "a"}],
                }
            ),
        ):
            parsed, error = p.parse_comp_dependency_result(payload)
            self.assertIsNone(parsed, repr(payload))
            self.assertTrue(error, repr(payload))


class TrackerRecordParsingTests(unittest.TestCase):
    def _response(self, records):
        return json.dumps(records).encode("utf-8")

    def test_none_and_empty_are_failures(self):
        for payload in (None, b"", b"   ", "not json", "[1, 2]"):
            footage, error = p.parse_footage_records(payload)
            self.assertEqual(footage, [])
            self.assertTrue(error, repr(payload))
            comps, error = p.parse_comp_records(payload)
            self.assertEqual(comps, [])
            self.assertTrue(error, repr(payload))

    def test_footage_null_fields_become_na(self):
        response = self._response(
            [
                {
                    "footageId": 12,
                    "name": "plate",
                    "path": "Z:\\Renders\\plate.0001.exr",
                    "fps": None,
                    "duration": None,
                    "startFrame": None,
                    "endFrame": None,
                    "width": None,
                    "height": None,
                }
            ]
        )
        records, error = p.parse_footage_records(response)
        self.assertIsNone(error)
        record = records[0]
        self.assertEqual(record["fps"], "N/A")
        self.assertEqual(record["duration"], "N/A")
        self.assertEqual(record["startFrame"], "N/A")
        self.assertEqual(record["endFrame"], "N/A")
        self.assertEqual(record["width"], "N/A")
        self.assertEqual(record["height"], "N/A")
        self.assertEqual(record["footageId"], "12")
        self.assertEqual(record["path"], "Z:/Renders/plate.0001.exr")

    def test_footage_unicode_and_delimiters_survive(self):
        name = u"Client's éclair;;umaçã.mov"
        response = self._response(
            [
                {
                    "footageId": "3",
                    "name": name,
                    "path": "Z:/Client's/job.mov",
                    "fps": "25.00",
                    "duration": "10.00",
                    "startFrame": 100,
                    "endFrame": 350,
                }
            ]
        )
        records, error = p.parse_footage_records(response)
        self.assertIsNone(error)
        self.assertEqual(records[0]["name"], name)
        self.assertEqual(records[0]["startFrame"], "100")
        self.assertEqual(records[0]["endFrame"], "350")
        self.assertEqual(records[0]["fps"], "25.00")

    def test_footage_malformed_entry(self):
        response = self._response(["just a string"])
        records, error = p.parse_footage_records(response)
        self.assertEqual(records, [])
        self.assertIn("malformed footage record", error)

    def test_valid_empty_footage_is_not_error(self):
        records, error = p.parse_footage_records(self._response([]))
        self.assertEqual(records, [])
        self.assertIsNone(error)

    def test_comp_records_parsed(self):
        response = self._response(
            [
                {
                    "compId": 7,
                    "name": "SQ01_SH0010_main",
                    "width": 1920,
                    "height": 1080,
                    "pixelAspect": 1,
                    "duration": "10.00",
                    "frameRate": "25.00",
                    "frameDuration": "0.040000",
                    "inPoint": "0.00",
                    "outPoint": "10.00",
                    "displayStartFrame": 0,
                    "workAreaStart": "0.00",
                    "workAreaDuration": "10.00",
                    "startFrame": 0,
                    "endFrame": 249,
                    "isPrecomp": True,
                    "parentComps": "master",
                    "numLayers": 5,
                }
            ]
        )
        records, error = p.parse_comp_records(response)
        self.assertIsNone(error)
        record = records[0]
        self.assertEqual(record["compId"], "7")
        self.assertEqual(record["width"], "1920")
        self.assertTrue(record["isPrecomp"])
        self.assertEqual(record["parentComps"], "master")

    def test_comp_valid_empty_is_not_error(self):
        records, error = p.parse_comp_records(self._response([]))
        self.assertEqual(records, [])
        self.assertIsNone(error)


class SimulatedRoundTripTests(unittest.TestCase):
    """Simulate AE-side replies to the protocol's scripts."""

    def test_save_ack_round_trip(self):
        reply = json.dumps(
            {"result": True, "path": "Z:\\Pipeline\\shot_v0001.aep"}
        ).encode("utf-8")
        data, error = p.parse_json_response(reply)
        ack, error = p.ack_result(data, error)
        self.assertTrue(ack)
        self.assertIsNone(error)

    def test_save_failure_round_trip(self):
        reply = json.dumps(
            {
                "result": False,
                "details": "project was not saved to the requested path",
                "path": None,
            }
        ).encode("utf-8")
        data, error = p.parse_json_response(reply)
        ack, error = p.ack_result(data, error)
        self.assertIsNone(error)
        self.assertFalse(ack)

    def test_transport_failure_never_success(self):
        # err_catcher converts exceptions into None on the Qt GUI thread.
        for failure in (None, b"", b"\x00"):
            data, error = p.parse_json_response(failure)
            ack, error2 = p.ack_result(data, error)
            self.assertIsNone(ack)
            self.assertTrue(error or error2)

    def test_import_footage_ack(self):
        reply = json.dumps({"result": True, "itemId": 42}).encode("utf-8")
        data, error = p.parse_json_response(reply)
        ack, error = p.ack_result(data, error)
        self.assertTrue(ack)
        self.assertEqual(data["itemId"], 42)

    def test_script_error_reply(self):
        reply = json.dumps(
            {"result": False, "details": "script error: Error: bad template"}
        ).encode("utf-8")
        data, error = p.parse_json_response(reply)
        ack, error = p.ack_result(data, error)
        self.assertFalse(ack)
        self.assertIn("bad template", data["details"])


if __name__ == "__main__":
    unittest.main()
