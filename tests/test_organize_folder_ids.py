# -*- coding: utf-8 -*-
"""Regression tests for organize folder-ID result keys.

The organize manager depends on Qt/Prism, so these inspect the source
directly.  ``createFolderStructure`` returns ``folder_id``; reading the
AE-style ``folderId`` made every target folder ID 0 and every move fail
with ``target_folder_not_found``.
"""

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORGANIZE_SOURCE = os.path.join(
    REPO_ROOT, "Scripts", "footage_tracker", "ae_organize_manager.py")
OPERATIONS_SOURCE = os.path.join(
    REPO_ROOT, "Scripts", "footage_tracker", "ae_operations.py")


class TestOrganizeFolderIds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ORGANIZE_SOURCE, encoding="utf-8") as handle:
            cls.organize = handle.read()
        with open(OPERATIONS_SOURCE, encoding="utf-8") as handle:
            cls.operations = handle.read()

    def test_organize_reads_folder_id_result_key(self):
        self.assertEqual(
            self.organize.count("result.get('folder_id'"), 2,
            "both single- and multi-folder organize paths must read folder_id",
        )
        self.assertNotIn("result.get('folderId', 0)", self.organize)

    def test_operations_exposes_both_folder_id_keys(self):
        self.assertIn("'folder_id': folder_id", self.operations)
        self.assertIn("'folderId': folder_id", self.operations)

    def test_organize_reads_deleted_count_result_key(self):
        self.assertNotIn("get('deletedCount'", self.organize)
        self.assertEqual(self.organize.count("get('deleted_count'"), 2)


if __name__ == "__main__":
    unittest.main()
