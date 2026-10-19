# -*- coding: utf-8 -*-
"""Regression tests for fast version scanning in FootageUtils."""

import importlib.util
import os
import tempfile
import unittest
from unittest import mock


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SPEC = importlib.util.spec_from_file_location(
    "footage_utils", os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "utils.py")
)
utils = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(utils)


class TestParseFootagePathVersions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.task = os.path.join(self.temp.name, "Lighting")
        for version in ("v0001", "v0002", "v0003", "v0004"):
            os.makedirs(os.path.join(self.task, version))
        # v0004 is empty, v0002 is empty; v0003 and v0001 contain media.
        for version in ("v0001", "v0003"):
            with open(os.path.join(self.task, version, "render.mov"), "w"):
                pass

    def _track_version_checks(self):
        original = utils.FootageUtils.versionHasFootage
        calls = []

        def tracked(path):
            calls.append(path)
            return original(path)

        utils.FootageUtils.versionHasFootage = staticmethod(tracked)
        self.addCleanup(
            setattr, utils.FootageUtils, "versionHasFootage", staticmethod(original)
        )
        return calls

    def test_fast_mode_checks_only_newest_until_media(self):
        calls = self._track_version_checks()
        info = utils.FootageUtils.parseFootagePath(
            os.path.join(self.task, "v0001", "render.mov"),
            verify_versions=False,
        )
        self.assertEqual(info["latestVersion"], "v0003")
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("v0004"))
        self.assertTrue(calls[1].endswith("v0003"))

    def test_full_mode_filters_empty_versions(self):
        info = utils.FootageUtils.parseFootagePath(
            os.path.join(self.task, "v0001", "render.mov")
        )
        self.assertEqual(info["latestVersion"], "v0003")
        self.assertEqual(info["allVersions"], ["v0003", "v0001"])

    def test_cache_reuses_task_scan(self):
        calls = self._track_version_checks()
        cache = {}
        first = utils.FootageUtils.parseFootagePath(
            os.path.join(self.task, "v0001", "render.mov"),
            cache,
            verify_versions=False,
        )
        second = utils.FootageUtils.parseFootagePath(
            os.path.join(self.task, "v0003", "render.mov"),
            cache,
            verify_versions=False,
        )
        self.assertEqual(first["latestVersion"], "v0003")
        self.assertEqual(second["latestVersion"], "v0003")
        self.assertEqual(len(calls), 2)

    def test_skip_scan_does_not_touch_filesystem(self):
        with mock.patch.object(
            utils.os, "listdir", side_effect=AssertionError("filesystem accessed")
        ), mock.patch.object(
            utils.os.path, "exists", side_effect=AssertionError("filesystem accessed")
        ):
            info = utils.FootageUtils.parseFootagePath(
                os.path.join(self.task, "v0001", "render.mov"),
                scan_versions=False,
            )
        self.assertEqual(info["currentVersion"], "v0001")
        self.assertEqual(info["latestVersion"], "v0001")
        self.assertEqual(info["allVersions"], ["v0001"])


if __name__ == "__main__":
    unittest.main()
