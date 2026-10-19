# -*- coding: utf-8 -*-
"""Regression tests for footage_tracker.cache_store (stdlib only)."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "cache_store.py")


def _load():
    spec = importlib.util.spec_from_file_location("cache_store", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cache_store = _load()


class TestNormalizePath(unittest.TestCase):
    def test_backslashes_to_slashes(self):
        self.assertEqual(cache_store.normalize_path("Z:\\a\\b"), "Z:/a/b")

    def test_forward_slashes_unchanged(self):
        self.assertEqual(cache_store.normalize_path("Z:/a/b"), "Z:/a/b")

    def test_non_string_raises(self):
        with self.assertRaises(TypeError):
            cache_store.normalize_path(123)
        with self.assertRaises(TypeError):
            cache_store.normalize_path(None)


class TestIsVersionFolder(unittest.TestCase):
    def test_plain_versions(self):
        for name in ("v0001", "v0007", "v0012", "v1234"):
            self.assertTrue(cache_store.is_version_folder(name), name)

    def test_suffixed_not_plain(self):
        for name in ("v0012 (mp4)", "v0007_exr", "v1", "version", "V0007"):
            self.assertFalse(cache_store.is_version_folder(name), name)

    def test_non_string_is_false(self):
        self.assertFalse(cache_store.is_version_folder(None))
        self.assertFalse(cache_store.is_version_folder(7))


class TestVersionSortKey(unittest.TestCase):
    def test_newest_first(self):
        versions = ["v0001", "v0003", "v0002"]
        versions.sort(key=cache_store.version_sort_key)
        self.assertEqual(versions, ["v0003", "v0002", "v0001"])

    def test_plain_before_suffix(self):
        versions = ["v0007 (mp4)", "v0007", "v0006"]
        versions.sort(key=cache_store.version_sort_key)
        self.assertEqual(versions, ["v0007", "v0007 (mp4)", "v0006"])

    def test_newer_base_beats_older_suffixed(self):
        versions = ["v0007 (mp4)", "v0008"]
        versions.sort(key=cache_store.version_sort_key)
        self.assertEqual(versions, ["v0008", "v0007 (mp4)"])

    def test_non_version_sorts_last_stable(self):
        versions = ["v0002", "notaversion"]
        versions.sort(key=cache_store.version_sort_key)
        self.assertEqual(versions[0], "v0002")


class TestGetCacheKey(unittest.TestCase):
    def test_3d_render_path_with_sequence(self):
        path = (
            "X:/Project/03_Production/Shots/SQ020/SH030/Renders/3dRender/"
            "Lighting_Humans/v0016/beauty/SQ020-SH030_beauty_v0016.0001.exr"
        )
        self.assertEqual(
            cache_store.get_cache_key(path), "SQ020-SH030/Lighting_Humans"
        )

    def test_shot_without_sequence(self):
        path = "X:/P/SH030/Renders/Lighting/v0002/a.mov"
        self.assertEqual(cache_store.get_cache_key(path), "SH030/Lighting")

    def test_lowercase_sequence_and_shot(self):
        path = "X:/P/sh010/ch02/sh010/lit/v0001/a.exr"
        # 'ch02' precedes 'sh010'? No: path order is sh010 first.
        # Path parts: X:, P, sh010, ch02, sh010, lit, v0001...
        # First sh010 has predecessor 'P' (not a sequence); second sh010
        # has predecessor ch02 → sequence detected on the second one.
        self.assertEqual(cache_store.get_cache_key(path), "ch02-sh010/lit")

    def test_backslash_path(self):
        path = "X:\\Project\\SQ020\\SH030\\Lighting_Humans\\v0016\\a.exr"
        self.assertEqual(
            cache_store.get_cache_key(path), "SQ020-SH030/Lighting_Humans"
        )

    def test_suffixed_version_folder_still_detects_task(self):
        path = "X:/P/SH030/Lighting/v0012 (mp4)/a.mov"
        self.assertEqual(cache_store.get_cache_key(path), "SH030/Lighting")

    def test_no_shot_returns_none(self):
        self.assertIsNone(cache_store.get_cache_key("X:/assets/v0001/a.exr"))

    def test_no_version_returns_none(self):
        self.assertIsNone(cache_store.get_cache_key("X:/P/SH030/Lighting/a.exr"))

    def test_empty_and_bytes(self):
        self.assertIsNone(cache_store.get_cache_key(""))
        self.assertIsNone(cache_store.get_cache_key(None))
        key = cache_store.get_cache_key(b"X:/P/SH030/Lighting/v0001/a.exr")
        self.assertEqual(key, "SH030/Lighting")


class TestValidateCache(unittest.TestCase):
    def _good_cache(self):
        return {
            "version": 1,
            "project_path": "X:/proj",
            "versions": {
                "SH030/Lighting": {
                    "allVersions": ["v0002", "v0001"],
                    "latestVersion": "v0002",
                    "last_scanned": "2026-09-30T10:00:00",
                }
            },
        }

    def test_good_cache_passes(self):
        clean, error = cache_store.validate_cache(self._good_cache())
        self.assertIsNone(error)
        self.assertIn("SH030/Lighting", clean["versions"])

    def test_missing_root_key_rejected(self):
        bad = self._good_cache()
        del bad["project_path"]
        clean, error = cache_store.validate_cache(bad)
        self.assertIsNone(clean)
        self.assertIn("project_path", error)

    def test_non_dict_rejected(self):
        clean, error = cache_store.validate_cache([1, 2])
        self.assertIsNone(clean)
        self.assertIsNotNone(error)

    def test_bad_entries_dropped_good_kept(self):
        data = self._good_cache()
        data["versions"]["broken1"] = {"allVersions": "v0001", "latestVersion": "v0001"}
        data["versions"]["broken2"] = {"allVersions": ["v0001"], "latestVersion": ""}
        data["versions"]["broken3"] = "not-a-dict"
        data["versions"]["broken4"] = {
            "allVersions": ["v0001", 7],
            "latestVersion": "v0001",
        }
        clean, error = cache_store.validate_cache(data)
        self.assertIsNone(error)
        self.assertIn("SH030/Lighting", clean["versions"])
        for broken in ("broken1", "broken2", "broken3", "broken4"):
            self.assertNotIn(broken, clean["versions"])

    def test_versions_not_dict_rejected(self):
        data = self._good_cache()
        data["versions"] = []
        clean, error = cache_store.validate_cache(data)
        self.assertIsNone(clean)
        self.assertIsNotNone(error)


class TestEntryIsFresh(unittest.TestCase):
    def test_recent_scan_is_fresh(self):
        entry = {"last_scanned": "2026-09-30T10:00:00"}
        self.assertTrue(
            cache_store.entry_is_fresh(entry, "2026-09-30T10:02:00", 300)
        )

    def test_old_scan_is_stale(self):
        entry = {"last_scanned": "2026-09-30T10:00:00"}
        self.assertFalse(
            cache_store.entry_is_fresh(entry, "2026-09-30T10:10:01", 300)
        )

    def test_boundary_exactly_at_limit_is_fresh(self):
        entry = {"last_scanned": "2026-09-30T10:00:00"}
        self.assertTrue(
            cache_store.entry_is_fresh(entry, "2026-09-30T10:05:00", 300)
        )

    def test_missing_timestamp_is_stale(self):
        self.assertFalse(cache_store.entry_is_fresh({}, "2026-09-30T10:00:00", 300))
        self.assertFalse(
            cache_store.entry_is_fresh(None, "2026-09-30T10:00:00", 300)
        )

    def test_garbage_timestamp_is_stale(self):
        entry = {"last_scanned": "not-a-date"}
        self.assertFalse(
            cache_store.entry_is_fresh(entry, "2026-09-30T10:00:00", 300)
        )

    def test_none_now_uses_wall_clock(self):
        entry = {"last_scanned": "2000-01-01T00:00:00"}
        self.assertFalse(cache_store.entry_is_fresh(entry, None, 300))


class TestAtomicWriteJson(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="helixae_cache_test_")
        self.path = os.path.join(self.tmpdir, "cache.json")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_and_read_back(self):
        ok, error = cache_store.atomic_write_json(self.path, {"a": 1})
        self.assertTrue(ok)
        self.assertIsNone(error)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 1})

    def test_no_temp_files_left_behind(self):
        cache_store.atomic_write_json(self.path, {"a": 1})
        cache_store.atomic_write_json(self.path, {"a": 2})
        leftovers = [n for n in os.listdir(self.tmpdir) if n != "cache.json"]
        self.assertEqual(leftovers, [])

    def test_overwrite_is_replace_not_append(self):
        cache_store.atomic_write_json(self.path, {"big": "x" * 5000})
        cache_store.atomic_write_json(self.path, {"small": 1})
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"small": 1})

    def test_creates_missing_directory(self):
        nested = os.path.join(self.tmpdir, "sub", "dir", "cache.json")
        ok, error = cache_store.atomic_write_json(nested, {"a": 1})
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(nested))

    def test_unicode_payload(self):
        ok, _ = cache_store.atomic_write_json(self.path, {"n": "Client's éclair — umã"})
        self.assertTrue(ok)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["n"], "Client's éclair — umã")

    def test_empty_path_fails_cleanly(self):
        ok, error = cache_store.atomic_write_json("", {"a": 1})
        self.assertFalse(ok)
        self.assertIsNotNone(error)

    def test_failure_keeps_previous_file_intact(self):
        cache_store.atomic_write_json(self.path, {"a": 1})
        # A non-serializable object fails after the temp file is created;
        # the original file must survive and no temp may remain.
        ok, error = cache_store.atomic_write_json(self.path, {"bad": object()})
        self.assertFalse(ok)
        self.assertIsNotNone(error)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 1})
        leftovers = [n for n in os.listdir(self.tmpdir) if n != "cache.json"]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
