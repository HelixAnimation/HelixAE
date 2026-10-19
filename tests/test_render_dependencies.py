# -*- coding: utf-8 -*-
"""Regression tests for output-scoped render dependency metadata."""

import importlib.util
import json
import os
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(
    REPO_ROOT, "Scripts", "helixae_render_deps.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "helixae_render_deps_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rd = _load_module()

COMP = {"id": "101", "name": "SH010_Main"}
CONTEXT = {
    "application": "aftereffects",
    "type": "composition",
    "identifier": "101",
    "name": "SH010_Main",
}


def _classify(path):
    if "3dRender" in path:
        return "01_3D_Renders"
    if "2dRender" in path:
        return "02_2D_Renders"
    if "Resources" in path:
        return "03_Resources"
    return "04_External"


class RenderDependencyBlockTests(unittest.TestCase):
    def test_render_and_external_classification(self):
        records = [
            {"id": "1", "name": "beauty", "path": "Z:\\Renders\\3dRender\\beauty.0001.exr"},
            {"id": "2", "name": "comp", "path": "Z:\\Renders\\2dRender\\comp.mov"},
            {"id": "3", "name": "hdr", "path": "Z:\\Resources\\hdri.hdr"},
            {"id": "4", "name": "stock", "path": "Z:\\Library\\stock.mov"},
        ]
        block, missing = rd.build_render_dependencies_block(
            COMP, records, _classify, path_exists=lambda _: True
        )
        self.assertEqual(missing, [])
        self.assertEqual(block["context"], CONTEXT)
        self.assertEqual(
            block["dependencies"],
            [
                "Z:/Renders/2dRender/comp.mov",
                "Z:/Renders/3dRender/beauty.0001.exr",
            ],
        )
        self.assertEqual(
            block["externalFiles"],
            ["Z:/Library/stock.mov", "Z:/Resources/hdri.hdr"],
        )

    def test_missing_paths_are_reported_and_excluded(self):
        records = [
            {"id": "1", "name": "ok", "path": "Z:/Renders/3dRender/ok.exr"},
            {"id": "2", "name": "gone", "path": "Z:/Renders/3dRender/gone.exr"},
        ]
        block, missing = rd.build_render_dependencies_block(
            COMP,
            records,
            _classify,
            path_exists=lambda path: path.endswith("ok.exr"),
        )
        self.assertEqual(missing, ["Z:/Renders/3dRender/gone.exr"])
        self.assertEqual(
            block["dependencies"], ["Z:/Renders/3dRender/ok.exr"]
        )

    def test_empty_scan_writes_empty_lists(self):
        block, missing = rd.build_render_dependencies_block(
            COMP, [], _classify, path_exists=lambda _: True
        )
        self.assertEqual(missing, [])
        self.assertEqual(block["dependencies"], [])
        self.assertEqual(block["externalFiles"], [])

    def test_duplicate_paths_are_deduplicated(self):
        records = [
            {"id": "1", "name": "a", "path": "Z:/Renders/3dRender/a.exr"},
            {"id": "2", "name": "a-copy", "path": "Z:\\Renders\\3dRender\\a.exr"},
        ]
        block, _ = rd.build_render_dependencies_block(
            COMP, records, _classify, path_exists=lambda _: True
        )
        self.assertEqual(block["dependencies"], ["Z:/Renders/3dRender/a.exr"])

    def test_invalid_composition_rejected(self):
        with self.assertRaises(ValueError):
            rd.build_render_dependencies_block(
                {"name": "no id"}, [], _classify, path_exists=lambda _: True
            )
        with self.assertRaises(ValueError):
            rd.build_render_dependencies_block(
                {"id": "1"}, [], _classify, path_exists=lambda _: True
            )


class VersionInfoApplicationTests(unittest.TestCase):
    def test_apply_sets_block(self):
        vinfo = {
            "dependencies": ["all"],
            "compDependencies": {"composition": COMP},
        }
        block = {
            "context": CONTEXT,
            "dependencies": ["one"],
            "externalFiles": [],
        }
        rd.apply_render_dependencies(vinfo, block)
        self.assertEqual(vinfo["renderDependencies"], block)
        self.assertNotIn("compDependencies", vinfo)
        self.assertEqual(vinfo["dependencies"], ["all"])

    def test_apply_none_clears_stale_key(self):
        vinfo = {
            "renderDependencies": {"context": CONTEXT},
            "compDependencies": {"composition": COMP},
        }
        rd.apply_render_dependencies(vinfo, None)
        self.assertNotIn("renderDependencies", vinfo)
        self.assertNotIn("compDependencies", vinfo)

    def test_atomic_write_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "versioninfo.json")
            data = {"renderDependencies": {"context": CONTEXT}}
            rd.write_json_atomic(path, data)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), data)
            self.assertEqual(
                [name for name in os.listdir(tmp) if name.endswith(".tmp")],
                [],
            )


if __name__ == "__main__":
    unittest.main()
