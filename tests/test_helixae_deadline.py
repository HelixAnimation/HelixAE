# -*- coding: utf-8 -*-
"""Regression tests for Scripts/helixae_deadline.py.

Loaded by file path (like test_helixae_protocol.py) so the suite stays
stdlib-only: no Prism, no Qt, no package __init__ imports.
"""

import importlib.util
import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "helixae_deadline.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("helixae_deadline", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


d = _load_module()


class IsMovieOutputTests(unittest.TestCase):
    def test_movie_extensions(self):
        for path in ("Z:/out.mov", "Z:/out.mp4", "Z:/out.MXF", "Z:/out.avi"):
            self.assertTrue(d.is_movie_output(path), path)

    def test_sequence_extensions(self):
        for path in ("Z:/out.png", "Z:/out.exr", "Z:/out.[#####].jpg"):
            self.assertFalse(d.is_movie_output(path), path)

    def test_empty_path_rejected(self):
        with self.assertRaises(ValueError):
            d.is_movie_output("")
        with self.assertRaises(ValueError):
            d.is_movie_output(None)


class SequencePaddingTests(unittest.TestCase):
    def test_bracket_padding_converted(self):
        self.assertEqual(
            d.to_deadline_output_filename("Z:/out/name_[#####].png"),
            "Z:/out/name_#####.png",
        )

    def test_no_padding_unchanged(self):
        self.assertEqual(d.to_deadline_output_filename("Z:/out.mov"), "Z:/out.mov")

    def test_empty_path_rejected(self):
        with self.assertRaises(ValueError):
            d.to_deadline_output_filename("")


class AeMajorVersionTests(unittest.TestCase):
    def test_parses_leading_integer(self):
        self.assertEqual(d.ae_major_version("25.1"), 25)
        self.assertEqual(d.ae_major_version("24.6.3"), 24)
        self.assertEqual(d.ae_major_version("17.0"), 17)

    def test_invalid_rejected(self):
        for bad in ("", None, "beta", "-5.0"):
            with self.assertRaises(ValueError):
                d.ae_major_version(bad)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            d.ae_major_version("0.0")


class FrameRangeTests(unittest.TestCase):
    def test_formats_range(self):
        self.assertEqual(d.format_frame_range(1001, 1050), "1001-1050")

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValueError):
            d.format_frame_range(50, 10)


class ChunkSizeTests(unittest.TestCase):
    def test_movie_output_is_one_chunk(self):
        self.assertEqual(d.resolve_chunk_size("Z:/out.mov", 10, 1001, 1050), 50)

    def test_sequence_uses_frames_per_task(self):
        self.assertEqual(d.resolve_chunk_size("Z:/out.png", 10, 1001, 1050), 10)

    def test_invalid_frames_per_task_rejected(self):
        with self.assertRaises(ValueError):
            d.resolve_chunk_size("Z:/out.png", 0, 1001, 1050)

    def test_end_before_start_rejected(self):
        with self.assertRaises(ValueError):
            d.resolve_chunk_size("Z:/out.png", 10, 1050, 1001)


class ConcurrentTasksTests(unittest.TestCase):
    def test_movie_output_forces_single_task(self):
        self.assertEqual(d.resolve_concurrent_tasks("Z:/out.mov", 8), 1)
        self.assertEqual(d.resolve_concurrent_tasks("Z:/out.mp4", 1), 1)

    def test_sequence_uses_requested_value(self):
        self.assertEqual(d.resolve_concurrent_tasks("Z:/out.png", 4), 4)

    def test_invalid_value_rejected(self):
        with self.assertRaises(ValueError):
            d.resolve_concurrent_tasks("Z:/out.png", 0)
        with self.assertRaises(ValueError):
            d.resolve_concurrent_tasks("Z:/out.png", -1)


class AddEnvironmentItemTests(unittest.TestCase):
    def test_appends_at_next_free_index(self):
        job_infos = {"EnvironmentKeyValue0": "already=set"}
        d.add_environment_item(job_infos, "prism_project", "Z:/proj.yml")
        self.assertEqual(job_infos["EnvironmentKeyValue1"], "prism_project=Z:/proj.yml")

    def test_starts_at_zero_when_empty(self):
        job_infos = {}
        d.add_environment_item(job_infos, "k", "v")
        self.assertEqual(job_infos["EnvironmentKeyValue0"], "k=v")


class BuildJobInfosTests(unittest.TestCase):
    def _base_kwargs(self, **overrides):
        kwargs = dict(
            name="shot010 - Main",
            comment="",
            pool="none",
            secondary_pool="",
            group="none",
            priority=50,
            start_frame=1001,
            end_frame=1050,
            chunk_size=10,
            output_path="Z:/out/name_[#####].png",
            prism_project="Z:/proj.yml",
            prism_source_scene="Z:/shot010_v0003.aep",
        )
        kwargs.update(overrides)
        return kwargs

    def test_basic_fields(self):
        job_infos = d.build_job_infos(**self._base_kwargs())
        self.assertEqual(job_infos["Plugin"], "AfterEffects")
        self.assertEqual(job_infos["Name"], "shot010 - Main")
        self.assertEqual(job_infos["Frames"], "1001-1050")
        self.assertEqual(job_infos["ChunkSize"], 10)
        self.assertEqual(job_infos["OutputFilename0"], "Z:/out/name_#####.png")
        self.assertNotIn("InitialStatus", job_infos)

    def test_concurrent_tasks_fields(self):
        job_infos = d.build_job_infos(
            **self._base_kwargs(concurrent_tasks=4, limit_concurrent_tasks_to_cpus=False)
        )
        self.assertEqual(job_infos["ConcurrentTasks"], 4)
        self.assertEqual(job_infos["LimitConcurrentTasksToNumberOfCpus"], "false")

    def test_default_concurrent_tasks_limited_to_cpus(self):
        job_infos = d.build_job_infos(**self._base_kwargs())
        self.assertEqual(job_infos["ConcurrentTasks"], 1)
        self.assertEqual(job_infos["LimitConcurrentTasksToNumberOfCpus"], "true")

    def test_suspended_sets_initial_status(self):
        job_infos = d.build_job_infos(**self._base_kwargs(suspended=True))
        self.assertEqual(job_infos["InitialStatus"], "Suspended")

    def test_environment_items_present(self):
        job_infos = d.build_job_infos(**self._base_kwargs())
        self.assertEqual(job_infos["EnvironmentKeyValue0"], "prism_project=Z:/proj.yml")
        self.assertEqual(
            job_infos["EnvironmentKeyValue1"], "prism_source_scene=Z:/shot010_v0003.aep"
        )

    def test_invalid_priority_rejected(self):
        with self.assertRaises(ValueError):
            d.build_job_infos(**self._base_kwargs(priority=101))
        with self.assertRaises(ValueError):
            d.build_job_infos(**self._base_kwargs(priority=-1))

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            d.build_job_infos(**self._base_kwargs(name=""))

    def test_pool_and_group_defaults(self):
        job_infos = d.build_job_infos(**self._base_kwargs(pool="", group=""))
        self.assertEqual(job_infos["Pool"], "none")
        self.assertEqual(job_infos["Group"], "none")


class BuildPluginInfosTests(unittest.TestCase):
    def test_basic_fields(self):
        plugin_infos = d.build_plugin_infos(
            comp_name="SH010_Main",
            output_path="Z:/out/name_[#####].png",
            major_version=25,
            app_version_str="25.1",
        )
        self.assertEqual(plugin_infos["Comp"], "SH010_Main")
        # Output keeps AE's raw [#####] padding; only OutputFilename0 (in
        # build_job_infos) is converted to Deadline's bare-hash form.
        self.assertEqual(plugin_infos["Output"], "Z:/out/name_[#####].png")
        self.assertEqual(plugin_infos["Version"], "25.0")
        self.assertEqual(plugin_infos["SubmittedFromVersion"], "25.1")
        self.assertNotIn("SceneFile", plugin_infos)

    def test_scene_file_included_when_given(self):
        plugin_infos = d.build_plugin_infos(
            comp_name="SH010_Main",
            output_path="Z:/out.mov",
            major_version=25,
            app_version_str="25.1",
            scene_file="Z:/shot010_v0003.aep",
        )
        self.assertEqual(plugin_infos["SceneFile"], "Z:/shot010_v0003.aep")

    def test_empty_comp_name_rejected(self):
        with self.assertRaises(ValueError):
            d.build_plugin_infos(
                comp_name="",
                output_path="Z:/out.mov",
                major_version=25,
                app_version_str="25.1",
            )

    def test_invalid_major_version_rejected(self):
        with self.assertRaises(ValueError):
            d.build_plugin_infos(
                comp_name="SH010_Main",
                output_path="Z:/out.mov",
                major_version=0,
                app_version_str="25.1",
            )


class ParseJobIdTests(unittest.TestCase):
    def test_parses_job_id(self):
        result = "Some banner text\nJobID=5f3c1a2b9e8d7c0012345678\nDone"
        self.assertEqual(d.parse_job_id(result), "5f3c1a2b9e8d7c0012345678")

    def test_no_job_id_returns_none(self):
        self.assertIsNone(d.parse_job_id("Error: something failed"))

    def test_none_result_returns_none(self):
        self.assertIsNone(d.parse_job_id(None))

    def test_strips_trailing_carriage_return(self):
        result = "JobID=abc123\r\n"
        self.assertEqual(d.parse_job_id(result), "abc123")


class InfoFilePathTests(unittest.TestCase):
    def test_job_info_file_path(self):
        path = d.job_info_file_path("/home/user")
        self.assertTrue(path.endswith(os.path.join("temp", "helixae_submit_info.job")))

    def test_plugin_info_file_path(self):
        path = d.plugin_info_file_path("/home/user")
        self.assertTrue(path.endswith(os.path.join("temp", "helixae_plugin_info.job")))


class ParseWorkerNamesTests(unittest.TestCase):
    def test_sorted_unique(self):
        out = "DESKTOP-B\r\nhelix-2\nDESKTOP-A\n\ndesktop-b\n"
        self.assertEqual(d.parse_worker_names(out), ["DESKTOP-A", "DESKTOP-B", "helix-2"])

    def test_failed_output(self):
        for out in (None, False, "", "   ", "Error: could not connect"):
            self.assertEqual(d.parse_worker_names(out), [], out)


class ThisPcWorkerTests(unittest.TestCase):
    def test_case_insensitive_match_returns_worker_spelling(self):
        self.assertEqual(
            d.resolve_this_pc_worker("desktop-vl66k9c", ["DESKTOP-VL66K9C", "HELIX-2"]),
            "DESKTOP-VL66K9C",
        )

    def test_not_a_worker(self):
        self.assertIsNone(d.resolve_this_pc_worker("OTHER", ["HELIX-2"]))

    def test_unknown_list_uses_hostname(self):
        self.assertEqual(d.resolve_this_pc_worker(" PC1 ", []), "PC1")

    def test_missing_hostname(self):
        with self.assertRaises(ValueError):
            d.resolve_this_pc_worker("", ["A"])


class WorkerFilterTests(unittest.TestCase):
    def test_all(self):
        self.assertEqual(d.resolve_worker_filter("all", ["A"]), {})

    def test_this_pc(self):
        self.assertEqual(
            d.resolve_worker_filter("this_pc", ["A", "B"], "PC1"), {"Whitelist": "PC1"}
        )
        with self.assertRaises(ValueError):
            d.resolve_worker_filter("this_pc", [], None)

    def test_whitelist(self):
        self.assertEqual(
            d.resolve_worker_filter("whitelist", ["A", " B ", "a"]), {"Whitelist": "A,B"}
        )
        with self.assertRaises(ValueError):
            d.resolve_worker_filter("whitelist", [])

    def test_blacklist(self):
        self.assertEqual(d.resolve_worker_filter("blacklist", ["A", "B"]), {"Blacklist": "A,B"})
        self.assertEqual(d.resolve_worker_filter("blacklist", []), {})

    def test_invalid(self):
        with self.assertRaises(ValueError):
            d.resolve_worker_filter("pool", ["A"])
        with self.assertRaises(ValueError):
            d.resolve_worker_filter("whitelist", ["A,B"])

    def test_build_job_infos_applies_filter(self):
        kwargs = dict(
            name="job", comment="", pool="none", secondary_pool="", group="ae",
            priority=50, start_frame=1, end_frame=10, chunk_size=5,
            output_path="X:/out_[####].png", prism_project="p", prism_source_scene="s",
        )
        self.assertNotIn("Whitelist", d.build_job_infos(**kwargs))
        infos = d.build_job_infos(worker_filter={"Whitelist": "PC1"}, **kwargs)
        self.assertEqual(infos["Whitelist"], "PC1")
        self.assertEqual(infos["Pool"], "none")
        with self.assertRaises(ValueError):
            d.build_job_infos(worker_filter={"Pool": "x"}, **kwargs)


if __name__ == "__main__":
    unittest.main()
