# -*- coding: utf-8 -*-
"""Regression tests for the composition cleanup protocol (Phase 1).

Covers the critical bug where a composition using exactly one footage item
produced a response without the old ';;' separator, so its used-item set was
parsed as empty and used footage could be offered for deletion.

The module under test is loaded directly from its file path so the
footage_tracker package __init__ (which imports Qt-dependent modules) is
never executed.
"""

import importlib.util
import json
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "comp_cleanup.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("helixae_comp_cleanup", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load_module()


def _ok_response(used_footage=None, used_comps=None,
                 unused_footage=None, unused_comps=None):
    payload = {
        "status": "ok",
        "used": {
            "footage": used_footage or {},
            "comps": used_comps or {},
        },
        "unused": {
            "footage": unused_footage or {},
            "comps": unused_comps or {},
        },
    }
    return json.dumps(payload)


class TestSingleItemRegression(unittest.TestCase):
    """One used footage item must never be offered for removal."""

    def test_single_footage_item_is_parsed(self):
        response = _ok_response(
            used_footage={"12": "SQ01_SH010_beauty_v001.mov"},
            used_comps={"3": "Main"},
            unused_footage={},
            unused_comps={"7": "Old Comp"},
        )
        parsed = cc.parse_unused_items_result(response)
        self.assertTrue(parsed["ok"])
        self.assertIsNone(parsed["error"])
        self.assertIsNone(parsed["reason"])
        self.assertEqual(
            parsed["used"]["footage"],
            {"12": "SQ01_SH010_beauty_v001.mov"},
        )
        self.assertEqual(parsed["used"]["comps"], {"3": "Main"})
        self.assertEqual(parsed["unused"]["footage"], {})
        self.assertEqual(parsed["unused"]["comps"], {"7": "Old Comp"})

    def test_single_unused_item_is_parsed(self):
        response = _ok_response(
            used_footage={"12": "plate.mov"},
            used_comps={"3": "Main"},
            unused_footage={"15": "garbage.png"},
            unused_comps={},
        )
        parsed = cc.parse_unused_items_result(response)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["unused"]["footage"], {"15": "garbage.png"})

    def test_empty_project_unused_still_valid(self):
        response = _ok_response(
            used_footage={}, used_comps={"3": "Solo"},
            unused_footage={}, unused_comps={},
        )
        parsed = cc.parse_unused_items_result(response)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["used"]["comps"], {"3": "Solo"})
        self.assertEqual(parsed["unused"]["footage"], {})


class TestNestedPrecomps(unittest.TestCase):
    def test_multi_level_dependencies_preserved(self):
        used_footage = {"10": "a.exr", "11": "b.mov", "12": "c.png"}
        used_comps = {"3": "Main", "4": "PreA", "5": "PreB"}
        response = _ok_response(
            used_footage=used_footage,
            used_comps=used_comps,
            unused_footage={"20": "leftover.mov"},
            unused_comps={"6": "UnusedComp"},
        )
        parsed = cc.parse_unused_items_result(response)
        self.assertTrue(parsed["ok"])
        self.assertEqual(len(parsed["used"]["footage"]), 3)
        self.assertEqual(len(parsed["used"]["comps"]), 3)
        self.assertEqual(parsed["unused"]["footage"], {"20": "leftover.mov"})
        self.assertEqual(parsed["unused"]["comps"], {"6": "UnusedComp"})


class TestNameIntegrity(unittest.TestCase):
    def test_delimiter_characters_survive(self):
        tricky = {
            "30": "A;;B",
            "31": "COMP:1::x",
            "32": "name'with'quotes",
            "33": "line\nbreak",
        }
        response = _ok_response(unused_footage=tricky)
        parsed = cc.parse_unused_items_result(response)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["unused"]["footage"], tricky)

    def test_unicode_names_survive_bytes_roundtrip(self):
        response = _ok_response(
            used_footage={"5": "Client's éclair — umaçã.mov"},
        )
        parsed = cc.parse_unused_items_result(response.encode("utf-8"))
        self.assertTrue(parsed["ok"])
        self.assertEqual(
            parsed["used"]["footage"]["5"], "Client's éclair — umaçã.mov"
        )


class TestReasonStatuses(unittest.TestCase):
    def test_no_project(self):
        parsed = cc.parse_unused_items_result(
            json.dumps({"status": "no_project"}))
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["reason"], cc.STATUS_NO_PROJECT)
        self.assertEqual(parsed["unused"]["footage"], {})

    def test_comp_not_found(self):
        parsed = cc.parse_unused_items_result(
            json.dumps({"status": "comp_not_found"}))
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["reason"], cc.STATUS_COMP_NOT_FOUND)

    def test_not_a_comp(self):
        parsed = cc.parse_unused_items_result(
            json.dumps({"status": "not_a_comp"}))
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["reason"], cc.STATUS_NOT_A_COMP)


class TestBridgeFailures(unittest.TestCase):
    def test_none_response_is_failure(self):
        parsed = cc.parse_unused_items_result(None)
        self.assertFalse(parsed["ok"])
        self.assertIn("empty response", parsed["error"])

    def test_empty_bytes_response_is_failure(self):
        parsed = cc.parse_unused_items_result(b"")
        self.assertFalse(parsed["ok"])
        self.assertIn("empty response", parsed["error"])

    def test_whitespace_response_is_failure(self):
        parsed = cc.parse_unused_items_result("   \n ")
        self.assertFalse(parsed["ok"])

    def test_old_delimiter_format_is_rejected(self):
        parsed = cc.parse_unused_items_result(
            "FOOTAGE:12::plate.mov;;COMP:3::Main")
        self.assertFalse(parsed["ok"])
        self.assertIn("invalid JSON", parsed["error"])

    def test_error_status_is_failure(self):
        parsed = cc.parse_unused_items_result(
            json.dumps({"status": "error", "detail": "boom"}))
        self.assertFalse(parsed["ok"])
        self.assertIn("boom", parsed["error"])

    def test_malformed_ok_payload_is_failure(self):
        parsed = cc.parse_unused_items_result(
            json.dumps({"status": "ok", "used": {"footage": "not-a-dict"}}))
        self.assertFalse(parsed["ok"])

    def test_missing_status_is_failure(self):
        parsed = cc.parse_unused_items_result(json.dumps({"used": {}}))
        self.assertFalse(parsed["ok"])


class TestRemovalProtocol(unittest.TestCase):
    def test_parse_mixed_results(self):
        response = json.dumps({
            "status": "ok",
            "results": {
                "1": "removed",
                "2": "not_found",
                "3": "retained",
                "4": "wrong_type",
                "5": "error: cannot remove locked item",
            },
        })
        parsed = cc.parse_remove_items_result(response)
        self.assertTrue(parsed["ok"])
        summary = cc.summarize_removal_results(parsed["results"])
        self.assertEqual(summary["removed"], 1)
        self.assertEqual(summary["not_found"], 1)
        self.assertEqual(summary["retained"], 1)
        self.assertEqual(summary["wrong_type"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(
            summary["failed_details"],
            ["5: error: cannot remove locked item"],
        )

    def test_parse_removal_failure_modes(self):
        for bad in (None, b"", "", "not json", json.dumps({"status": "error", "detail": "x"})):
            parsed = cc.parse_remove_items_result(bad)
            self.assertFalse(parsed["ok"])
            self.assertTrue(parsed["error"])

    def test_summarize_unknown_status_counts_as_failed(self):
        summary = cc.summarize_removal_results({"9": "something_new"})
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["failed_details"], ["9: something_new"])


class TestScriptBuilders(unittest.TestCase):
    def test_query_script_embedds_comp_id_and_json(self):
        script = cc.build_unused_items_script(42)
        self.assertIn("var target = app.project.itemByID(42);", script)
        self.assertIn("JSON.stringify", script)
        self.assertIn("hxWalkComp", script)
        self.assertNotIn("__COMP_ID__", script)
        self.assertNotIn("__ITEM_IDS__", script)

    def test_removal_script_embeds_ids_and_undo_group(self):
        script = cc.build_remove_items_script(42, [7, "8", 9])
        self.assertIn("var target = app.project.itemByID(42);", script)
        self.assertIn("var itemIds = [7,8,9];", script)
        self.assertEqual(script.count("beginUndoGroup"), 1)
        self.assertEqual(script.count("endUndoGroup"), 1)
        self.assertNotIn("__COMP_ID__", script)
        self.assertNotIn("__ITEM_IDS__", script)

    def test_removal_script_retained_guard_present(self):
        script = cc.build_remove_items_script(1, [2])
        self.assertIn('results[id] = "retained";', script)
        self.assertIn('results[id] = "not_found";', script)
        self.assertIn('results[id] = "wrong_type";', script)

    def test_invalid_comp_id_rejected(self):
        for bad in (None, "abc", 0, -3):
            with self.assertRaises((TypeError, ValueError)):
                cc.build_unused_items_script(bad)

    def test_invalid_item_ids_rejected(self):
        with self.assertRaises(ValueError):
            cc.build_remove_items_script(1, [])
        for bad in (["x"], [0], [-1]):
            with self.assertRaises((TypeError, ValueError)):
                cc.build_remove_items_script(1, bad)

    def test_numeric_string_ids_normalized(self):
        script = cc.build_remove_items_script("42", ["7", 8])
        self.assertIn("var itemIds = [7,8];", script)


if __name__ == "__main__":
    unittest.main()
