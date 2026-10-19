# -*- coding: utf-8 -*-
"""Regression tests for footage_tracker.bypass_keys (stdlib only)."""

import importlib.util
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "bypass_keys.py")


def _load():
    spec = importlib.util.spec_from_file_location("bypass_keys", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bypass_keys = _load()


class TestKeyFormats(unittest.TestCase):
    def test_footage_key_three_part(self):
        self.assertEqual(
            bypass_keys.footage_key("SH030", "Lighting_Humans", "beauty"),
            "footage_SH030_Lighting_Humans_beauty",
        )

    def test_footage_key_two_part(self):
        self.assertEqual(
            bypass_keys.footage_key("SH030", "LowRes"),
            "footage_SH030_LowRes",
        )

    def test_footage_key_empty_when_missing_parts(self):
        self.assertEqual(bypass_keys.footage_key("", "LowRes", "beauty"), "")
        self.assertEqual(bypass_keys.footage_key("SH030", "", "beauty"), "")

    def test_footage_key_empty_aov_falls_back_to_two_part(self):
        self.assertEqual(
            bypass_keys.footage_key("SH030", "LowRes", ""),
            "footage_SH030_LowRes",
        )

    def test_comp_key(self):
        self.assertEqual(
            bypass_keys.comp_key(12, "Main"), "comp_12_Main"
        )


class TestApply2DDuplicateSuffix(unittest.TestCase):
    def test_identity_when_text_equals_identifier(self):
        self.assertEqual(
            bypass_keys.apply_2d_duplicate_suffix("LowRes", "[2D] LowRes"),
            "LowRes",
        )

    def test_pb_prefix_identity(self):
        self.assertEqual(
            bypass_keys.apply_2d_duplicate_suffix("LowRes", "[PB] LowRes"),
            "LowRes",
        )

    def test_duplicate_suffix_folded(self):
        self.assertEqual(
            bypass_keys.apply_2d_duplicate_suffix("LowRes", "[2D] LowRes (1)"),
            "LowRes (1)",
        )

    def test_suffix_without_prefix_still_folds(self):
        self.assertEqual(
            bypass_keys.apply_2d_duplicate_suffix("LowRes", "LowRes (2)"),
            "LowRes (2)",
        )

    def test_non_string_inputs(self):
        self.assertEqual(bypass_keys.apply_2d_duplicate_suffix(None, "[2D] x"), "")
        self.assertEqual(bypass_keys.apply_2d_duplicate_suffix("LowRes", None), "LowRes")


class TestKeyFromItemData(unittest.TestCase):
    def test_comps_branch_comp_id_precedence(self):
        data = {"group": "Comps", "compId": "42", "id": "7", "comp_id": "9",
                "compName": "Main", "original_name": "Other", "name": "Third"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "comp_42_Main"
        )

    def test_comps_branch_fallback_ids(self):
        data = {"group": "Comps", "id": "7", "name": "Third"}
        self.assertEqual(bypass_keys.key_from_item_data(data), "comp_7_Third")

    def test_comps_branch_original_name(self):
        data = {"group": "Comps", "comp_id": 9, "original_name": "Other"}
        self.assertEqual(bypass_keys.key_from_item_data(data), "comp_9_Other")

    def test_three_part_footage(self):
        data = {"group": "3D Renders", "shot": "SH030",
                "identifier": "Lighting_Humans", "aov": "beauty"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data),
            "footage_SH030_Lighting_Humans_beauty",
        )

    def test_2d_without_aov_folds_tree_text_suffix(self):
        data = {"group": "2D Renders", "shot": "SH030", "identifier": "LowRes",
                "aov": "", "tree_text": "[2D] LowRes (1)"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_SH030_LowRes (1)"
        )

    def test_2d_without_aov_uses_plain_identifier(self):
        data = {"group": "2D Renders", "shot": "SH030", "identifier": "LowRes",
                "aov": "", "tree_text": "[PB] LowRes"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_SH030_LowRes"
        )

    def test_2d_without_aov_no_tree_text(self):
        data = {"group": "2D Renders", "shot": "SH030", "identifier": "LowRes",
                "aov": "", "original_name": "LowRes"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_SH030_LowRes"
        )

    def test_fallback_shot_original_name(self):
        data = {"group": "3D Renders", "shot": "SH030", "original_name": "clip.mov"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_SH030_clip.mov"
        )

    def test_fallback_group_original_name(self):
        data = {"group": "Resources", "original_name": "clip.mov"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_Resources_clip.mov"
        )

    def test_fallback_path(self):
        data = {"group": "External", "path": "X:/media/clip.mov"}
        self.assertEqual(
            bypass_keys.key_from_item_data(data), "footage_X:/media/clip.mov"
        )

    def test_non_dict_returns_none(self):
        self.assertIsNone(bypass_keys.key_from_item_data(None))
        self.assertIsNone(bypass_keys.key_from_item_data("x"))


class TestKeyFromTreeItem(unittest.TestCase):
    def test_3d_render_aov_from_item_text(self):
        key = bypass_keys.key_from_tree_item(
            "footage", "beauty", "SH030", "Lighting_Humans"
        )
        self.assertEqual(key, "footage_SH030_Lighting_Humans_beauty")

    def test_3d_detection_requires_identifier_differs_from_text(self):
        # identifier == item_text → not treated as 3D; identifier stays and
        # aov is empty → two-part key.
        key = bypass_keys.key_from_tree_item(
            "footage", "Lighting_Humans", "SH030", "Lighting_Humans"
        )
        self.assertEqual(key, "footage_SH030_Lighting_Humans")

    def test_2d_label_folds_suffix(self):
        key = bypass_keys.key_from_tree_item(
            "footage", "[2D] LowRes (1)", "SH030", "LowRes"
        )
        self.assertEqual(key, "footage_SH030_LowRes (1)")

    def test_pb_label_two_part(self):
        key = bypass_keys.key_from_tree_item(
            "footage", "[PB] LowRes", "SH030", "LowRes"
        )
        self.assertEqual(key, "footage_SH030_LowRes")

    def test_missing_identifier_falls_back_to_item_text(self):
        key = bypass_keys.key_from_tree_item("footage", "LowRes", "SH030", "")
        self.assertEqual(key, "footage_SH030_LowRes")

    def test_no_shot_falls_back_to_path(self):
        key = bypass_keys.key_from_tree_item(
            "footage", "LowRes", "", "", path="X:/media/clip.mov"
        )
        self.assertEqual(key, "footage_X:/media/clip.mov")

    def test_comp_branch(self):
        key = bypass_keys.key_from_tree_item(
            "comp", "Main", "SH030", "", comp_id=12, comp_name="Main"
        )
        self.assertEqual(key, "comp_12_Main")

    def test_unknown_type_returns_none(self):
        self.assertIsNone(
            bypass_keys.key_from_tree_item("folder", "x", "SH030", "y")
        )


class TestCrossBuilderParity(unittest.TestCase):
    """Tree-item keys and data-dict keys must agree for the same item."""

    def test_same_3d_item(self):
        from_tree = bypass_keys.key_from_tree_item(
            "footage", "beauty", "SH030", "Lighting_Humans"
        )
        from_data = bypass_keys.key_from_item_data(
            {"group": "3D Renders", "shot": "SH030",
             "identifier": "Lighting_Humans", "aov": "beauty"}
        )
        self.assertEqual(from_tree, from_data)

    def test_same_2d_item_with_suffix(self):
        from_tree = bypass_keys.key_from_tree_item(
            "footage", "[2D] LowRes (1)", "SH030", "LowRes"
        )
        from_data = bypass_keys.key_from_item_data(
            {"group": "2D Renders", "shot": "SH030", "identifier": "LowRes",
             "aov": "", "tree_text": "[2D] LowRes (1)"}
        )
        self.assertEqual(from_tree, from_data)

    def test_same_comp(self):
        from_tree = bypass_keys.key_from_tree_item(
            "comp", "Main", "SH030", "", comp_id=12, comp_name="Main"
        )
        from_data = bypass_keys.key_from_item_data(
            {"group": "Comps", "compId": "12", "compName": "Main"}
        )
        self.assertEqual(from_tree, from_data)


if __name__ == "__main__":
    unittest.main()
