# -*- coding: utf-8 -*-
"""Regression tests for Scripts/footage_tracker/version_paths.py.

The module is stdlib-only and loaded by file path so the Qt-importing
footage_tracker package __init__ is never triggered.
"""

import importlib.util
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SPEC = importlib.util.spec_from_file_location(
    "version_paths", os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "version_paths.py")
)
vp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vp)

_PROTOCOL_SPEC = importlib.util.spec_from_file_location(
    "helixae_protocol", os.path.join(REPO_ROOT, "Scripts", "helixae_protocol.py")
)
protocol = importlib.util.module_from_spec(_PROTOCOL_SPEC)
_PROTOCOL_SPEC.loader.exec_module(protocol)


class TestExtractVersionToken(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(vp.extract_version_token("v0003"), "v0003")

    def test_decorated(self):
        self.assertEqual(vp.extract_version_token("v0003 (mp4)"), "v0003")
        self.assertEqual(vp.extract_version_token("v0012 (jpg) "), "v0012")

    def test_missing_raises(self):
        self.assertRaises(ValueError, vp.extract_version_token, "version3")
        self.assertRaises(ValueError, vp.extract_version_token, "")
        self.assertRaises(ValueError, vp.extract_version_token, "0003")

    def test_non_string_raises(self):
        self.assertRaises(TypeError, vp.extract_version_token, 3)
        self.assertRaises(TypeError, vp.extract_version_token, None)


class TestVersionFolderIndex(unittest.TestCase):
    def test_3d_layout(self):
        # .../SH010/Lighting/v0002/beauty.####.exr -> index 4
        parts = ["Z:", "Align", "SH010", "Lighting", "v0002"]
        self.assertEqual(vp.version_folder_index(parts), 4)

    def test_no_version_folder(self):
        self.assertEqual(vp.version_folder_index(["Z:", "Align", "SH010"]), -1)

    def test_only_first_version_folder(self):
        self.assertEqual(vp.version_folder_index(["v0001", "v0002"]), 0)

    def test_non_string_entries_raise(self):
        self.assertRaises(TypeError, vp.version_folder_index, [3, "v0001"])


class TestSubstituteVersionInFilename(unittest.TestCase):
    def test_mov(self):
        self.assertEqual(
            vp.substitute_version_in_filename("SQ02-SH010_HighRes_v0002.mov", "v0003"),
            "SQ02-SH010_HighRes_v0003.mov",
        )

    def test_no_doubling(self):
        # THE regression: old code produced "_vv0003_" when newVersion
        # already carried the leading 'v'.
        result = vp.substitute_version_in_filename("name_v0002_x", "v0003")
        self.assertEqual(result, "name_v0003_x")
        self.assertNotIn("vv", result)

    def test_sequence_frame_suffix(self):
        self.assertEqual(
            vp.substitute_version_in_filename(
                "SQ02-SH010_Lighting_v0002.1001.exr", "v0003"
            ),
            "SQ02-SH010_Lighting_v0003.1001.exr",
        )

    def test_bracket_container(self):
        self.assertEqual(
            vp.substitute_version_in_filename("SH010_v0002[mp4].mov", "v0003"),
            "SH010_v0003[mp4].mov",
        )

    def test_underscore_suffix(self):
        self.assertEqual(
            vp.substitute_version_in_filename("SH010_v0002_Z.1001.exr", "v0003"),
            "SH010_v0003_Z.1001.exr",
        )

    def test_no_token_returns_unchanged(self):
        self.assertEqual(
            vp.substitute_version_in_filename("plainname.mov", "v0003"), "plainname.mov"
        )

    def test_invalid_version_raises(self):
        self.assertRaises(ValueError, vp.substitute_version_in_filename, "a_v0001.mov", "0003")
        self.assertRaises(TypeError, vp.substitute_version_in_filename, "a_v0001.mov", 3)


class TestBuildNewVersionPath(unittest.TestCase):
    def test_3d_layout(self):
        old = "Z:/Projects/Align/03_workfiles/SH010/Lighting/v0002/SQ02-SH010_Lighting_v0002.1001.exr"
        new = vp.build_new_version_path(old, "v0003")
        self.assertEqual(
            new,
            "Z:/Projects/Align/03_workfiles/SH010/Lighting/v0003/SQ02-SH010_Lighting_v0003.1001.exr",
        )

    def test_backslash_input_normalized(self):
        old = "Z:\\Projects\\SH010\\Lighting\\v0002\\SH010_Lighting_v0002.mov"
        new = vp.build_new_version_path(old, "v0003")
        self.assertEqual(new, "Z:/Projects/SH010/Lighting/v0003/SH010_Lighting_v0003.mov")

    def test_no_version_folder_raises(self):
        self.assertRaises(
            ValueError, vp.build_new_version_path, "Z:/media/plain.mov", "v0003"
        )

    def test_invalid_version_raises(self):
        self.assertRaises(
            ValueError,
            vp.build_new_version_path,
            "Z:/a/v0001/a_v0001.mov",
            "version3",
        )

    def test_invalid_path_raises(self):
        self.assertRaises(ValueError, vp.build_new_version_path, "", "v0003")
        self.assertRaises(ValueError, vp.build_new_version_path, 12, "v0003")
        self.assertRaises(ValueError, vp.build_new_version_path, None, "v0003")


class TestFootageBaseName(unittest.TestCase):
    def test_deterministic_full_name(self):
        # THE regression: the old lazy regex collapsed every filename to
        # its first character ('S' for both of these).
        self.assertEqual(vp.footage_base_name("SQ02-SH010_HighRes_v0002.mov"), "SQ02-SH010_HighRes")
        self.assertEqual(vp.footage_base_name("SQ02-SH010_Lighting_v0002.1001.exr"), "SQ02-SH010_Lighting")

    def test_unittest_style_names(self):
        self.assertEqual(vp.footage_base_name("test_name_v0001.mov"), "test_name")
        self.assertEqual(vp.footage_base_name("complicated_name_2_v0003.mov"), "complicated_name")

    def test_no_extension(self):
        self.assertEqual(vp.footage_base_name("plain"), "plain")

    def test_non_string_raises(self):
        self.assertRaises(TypeError, vp.footage_base_name, None)


class TestIsFootageFile(unittest.TestCase):
    def test_media_extensions(self):
        for name in ("a.mov", "b.exr", "c.png", "d.jpg", "e.mp4", "f.tif", "g.tga"):
            self.assertTrue(vp.is_footage_file(name), name)

    def test_non_media(self):
        for name in ("versioninfo.json", "notes.txt", ".gitignore", "thumb.db"):
            self.assertFalse(vp.is_footage_file(name), name)

    def test_non_string_raises(self):
        self.assertRaises(TypeError, vp.is_footage_file, 5)


class TestMatchFootageFile(unittest.TestCase):
    def test_prefers_video_over_frame_numbered(self):
        listing = [
            "SH010_Lighting_v0003.1001.exr",
            "SH010_Lighting_v0003.mov",
        ]
        self.assertEqual(
            vp.match_footage_file(listing, "SH010_Lighting"), "SH010_Lighting_v0003.mov"
        )

    def test_frame_numbered_when_no_video(self):
        listing = ["SH010_Lighting_v0003.0999.exr", "SH010_Lighting_v0003.1001.exr"]
        # deterministic: sorted order decides between equal categories
        self.assertEqual(
            vp.match_footage_file(listing, "SH010_Lighting"),
            "SH010_Lighting_v0003.0999.exr",
        )

    def test_no_match_returns_none(self):
        # Deterministic matching: unrelated files are NOT arbitrarily
        # picked (the old code grabbed the first directory entry).
        listing = ["aaa.mov", "bbb.mov"]
        self.assertIsNone(vp.match_footage_file(listing, "SH010_Lighting"))

    def test_same_base_required(self):
        listing = ["SH010_Lighting_v0003.mov", "SH010_Beauty_v0003.mov"]
        self.assertEqual(
            vp.match_footage_file(listing, "SH010_Lighting_v0002.mov"),
            "SH010_Lighting_v0003.mov",
        )

    def test_empty_listing_returns_none(self):
        self.assertIsNone(vp.match_footage_file([], "SH010_Lighting"))

    def test_ignores_non_media(self):
        listing = ["versioninfo.json", "SH010_Lighting_v0003.mov"]
        self.assertEqual(
            vp.match_footage_file(listing, "SH010_Lighting"), "SH010_Lighting_v0003.mov"
        )

    def test_no_version_token_required_in_listing(self):
        listing = ["render.mov"]
        self.assertEqual(vp.match_footage_file(listing, "render"), "render.mov")


class TestSortedListing(unittest.TestCase):
    def test_sorted(self):
        self.assertEqual(vp.sorted_listing.__doc__ is not None, True)
        # sorted_listing needs a directory; verify OSError safety via a
        # guaranteed-missing path.
        self.assertEqual(vp.sorted_listing("/nonexistent/helixae/path"), [])


class TestProtocolBuildersPhase4(unittest.TestCase):
    """The seven builders added for ae_operations/shot_switcher."""

    def _balanced(self, script):
        self.assertIn("JSON.stringify", script)
        self.assertEqual(script.count("{"), script.count("}"))
        self.assertEqual(script.count("("), script.count(")"))

    def test_get_footage_properties(self):
        s = protocol.build_get_footage_properties(123)
        self._balanced(s)
        self.assertIn("itemByID(123)", s)

    def test_id_validation(self):
        self.assertRaises(ValueError, protocol.build_get_footage_properties, "12a")
        self.assertRaises(ValueError, protocol.build_get_footage_properties, "")
        self.assertRaises(ValueError, protocol.build_get_footage_properties, True)
        self.assertRaises(ValueError, protocol.build_get_footage_properties, None)

    def test_replace_footage_by_id_still(self):
        s = protocol.build_replace_footage_by_id(
            55, r"Z:\Client's\beauty_v0003.mov", sequence=False
        )
        self._balanced(s)
        self.assertIn("itemByID(55)", s)
        self.assertIn(".replace(", s)
        self.assertNotIn("replaceWithSequence", s)
        self.assertIn("Client's", s)  # apostrophe survives js_string

    def test_replace_footage_by_id_sequence_keeps_conform(self):
        s = protocol.build_replace_footage_by_id(
            55, "Z:/renders/beauty.####.exr", sequence=True, conform_fps=25.0
        )
        self.assertIn("replaceWithSequence", s)
        self.assertIn("alphabeticOrder = false", s)
        self.assertIn("(25.0 !== null) ? 25.0 : previousRate", s)
        self.assertIn("conformFrameRate = targetRate", s)

    def test_replace_footage_by_id_previous_rate_preserved(self):
        s = protocol.build_replace_footage_by_id(55, "Z:/a/b.mov", sequence=False)
        # previousRate is read and re-applied when no explicit fps
        self.assertIn("previousRate = item.mainSource.conformFrameRate", s)
        self.assertIn("(null !== null) ? null : previousRate", s)

    def test_set_footage_fps(self):
        s = protocol.build_set_footage_fps(55, 23.976)
        self._balanced(s)
        self.assertIn("mainSource.conformFrameRate", s)
        self.assertRaises(ValueError, protocol.build_set_footage_fps, 55, 0)
        self.assertRaises(ValueError, protocol.build_set_footage_fps, 55, -5)

    def test_set_comp_fps(self):
        s = protocol.build_set_comp_fps("77", 25)
        self._balanced(s)
        self.assertIn("itemByID(77)", s)

    def test_set_comp_frame_range(self):
        s = protocol.build_set_comp_frame_range(77, 1001, 1085, 24.0)
        self._balanced(s)
        self.assertIn("displayStartTime", s)
        # reversed range rejected
        self.assertRaises(ValueError, protocol.build_set_comp_frame_range, 77, 1085, 1001, 24.0)

    def test_set_comp_resolution(self):
        s = protocol.build_set_comp_resolution(77, 1920, 1080)
        self._balanced(s)
        self.assertRaises(ValueError, protocol.build_set_comp_resolution, 77, 0, 1080)
        self.assertRaises(ValueError, protocol.build_set_comp_resolution, 77, 1920, -5)

    def test_replace_ack_round_trip(self):
        s = protocol.build_replace_footage_by_id(9, "Z:/x.mov", sequence=False)
        self.assertIn("try {", s)
        self.assertIn("catch (e)", s)


if __name__ == "__main__":
    unittest.main()
