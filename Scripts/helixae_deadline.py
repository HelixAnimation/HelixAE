# -*- coding: utf-8 -*-
"""Deadline AfterEffects job/plugin info builders.

Pure-stdlib module, loaded flat (``import helixae_deadline``) like
``helixae_protocol``, so it stays unit-testable without Prism, Qt, or the
Deadline client tools.  It only builds the ``jobInfos``/``pluginInfos``
dicts that ``Prism_Deadline_Functions.deadlineSubmitJob()`` writes to the
``.job`` info files and passes to ``deadlinecommand``; it never calls
Deadline or After Effects itself (that lives in ``helixae_export.py``).

Design note on the ``Comp``/``Output`` plugin-info fields, confirmed
against ``custom/plugins/AfterEffects/AfterEffects.py``'s
``RenderArgument()`` and the stock ``SubmitAEToDeadline.jsx``: with
``Comp`` set, the worker runs ``aerender -project <scene> -comp "<Comp>"
-s <start> -e <end> -output "<Output>"`` (``-output`` only when non-empty)
followed by fixed ``-v``/``-close``/``-sound`` flags. ``aerender -comp``
renders the composition's *first currently-queued* render-queue item,
using that item's own output module, and ``-output`` only overrides its
file path -- it does not change the module/template. This is exactly why
``helixae_export.py`` checks for another locally queued item on the same
comp before submitting: if one exists, "first queued" may not be ours.
``Output`` itself must be the raw After Effects ``outputModule.file.fsName``
with AE's ``[#####]`` sequence padding kept as-is (``SubmitAEToDeadline.jsx``
writes it unmodified); only the job-info ``OutputFilename0`` is converted to
Deadline's ``#####`` form via ``to_deadline_output_filename()``.
"""

import os
import re

MOVIE_EXTENSIONS = {
    ".mov", ".mp4", ".m4v", ".avi", ".mxf", ".mkv", ".wmv", ".mpg", ".mpeg",
}


def is_movie_output(path):
    """Return True when ``path``'s extension is a movie container."""
    if not isinstance(path, str) or not path:
        raise ValueError("output path is required")
    return os.path.splitext(path)[1].lower() in MOVIE_EXTENSIONS


def to_deadline_output_filename(path):
    """Convert AE's ``[#####]`` sequence padding to Deadline's ``#####`` form."""
    if not isinstance(path, str) or not path:
        raise ValueError("output path is required")
    return re.sub(r"\[(#+)\]", r"\1", path)


def ae_major_version(app_version_str):
    """Parse the leading integer from AE's ``app.version`` (e.g. ``'25.1'`` -> 25)."""
    match = re.match(r"\s*(\d+)", str(app_version_str or ""))
    if not match:
        raise ValueError(
            "could not parse After Effects version: %r" % (app_version_str,)
        )
    major = int(match.group(1))
    if major <= 0:
        raise ValueError(
            "invalid After Effects major version: %r" % (app_version_str,)
        )
    return major


def format_frame_range(start_frame, end_frame):
    """Return Deadline's ``"<start>-<end>"`` frame range string."""
    start = int(start_frame)
    end = int(end_frame)
    if end < start:
        raise ValueError("end frame before start frame")
    return "%d-%d" % (start, end)


def resolve_chunk_size(output_path, frames_per_task, start_frame, end_frame):
    """Movie containers must render as one task; sequences use ``frames_per_task``."""
    start = int(start_frame)
    end = int(end_frame)
    if end < start:
        raise ValueError("end frame before start frame")
    if is_movie_output(output_path):
        return end - start + 1
    frames_per_task = int(frames_per_task)
    if frames_per_task <= 0:
        raise ValueError("frames per task must be positive")
    return frames_per_task


def resolve_concurrent_tasks(output_path, concurrent_tasks):
    """Movie containers render as one task, so concurrency is forced to 1."""
    if is_movie_output(output_path):
        return 1
    concurrent_tasks = int(concurrent_tasks)
    if concurrent_tasks <= 0:
        raise ValueError("concurrent tasks must be positive")
    return concurrent_tasks


WORKER_MODE_ALL = "all"
WORKER_MODE_THIS_PC = "this_pc"
WORKER_MODE_WHITELIST = "whitelist"
WORKER_MODE_BLACKLIST = "blacklist"
WORKER_MODES = (
    WORKER_MODE_ALL,
    WORKER_MODE_THIS_PC,
    WORKER_MODE_WHITELIST,
    WORKER_MODE_BLACKLIST,
)


def parse_worker_names(output):
    """Parse ``deadlinecommand -GetSlaveNames`` output into sorted unique names.

    Returns ``[]`` for empty/failed output (``False``/``None``/error text).
    """
    if not isinstance(output, str) or not output.strip() or "Error" in output:
        return []
    names = []
    seen = set()
    for line in output.splitlines():
        name = line.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return sorted(names, key=str.lower)


def resolve_this_pc_worker(hostname, worker_names):
    """Return the Deadline worker name for this machine.

    Matches ``hostname`` case-insensitively against the known workers and
    returns the worker's own spelling. When the worker list is unknown
    (empty) the hostname is used as-is. Returns ``None`` when the list is
    known but this machine isn't a Deadline worker.
    """
    if not isinstance(hostname, str) or not hostname.strip():
        raise ValueError("could not determine this computer's name")
    hostname = hostname.strip()
    if not worker_names:
        return hostname
    for name in worker_names:
        if name.lower() == hostname.lower():
            return name
    return None


def resolve_worker_filter(mode, selected_workers=None, this_pc=None):
    """Return the job-info ``Whitelist``/``Blacklist`` entry for a worker mode.

    ``all`` -> ``{}``; ``this_pc`` -> whitelist of just ``this_pc``;
    ``whitelist`` needs at least one worker (an empty whitelist would never
    render); ``blacklist`` with no workers is the same as ``all``.
    """
    if mode not in WORKER_MODES:
        raise ValueError("unknown worker mode: %r" % (mode,))
    if mode == WORKER_MODE_ALL:
        return {}
    if mode == WORKER_MODE_THIS_PC:
        if not isinstance(this_pc, str) or not this_pc.strip():
            raise ValueError("this computer is not a Deadline worker")
        workers = [this_pc.strip()]
    else:
        workers = []
        seen = set()
        for name in selected_workers or []:
            name = str(name).strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                workers.append(name)
    for name in workers:
        if "," in name or "=" in name or "\n" in name:
            raise ValueError("invalid worker name: %r" % (name,))
    if mode == WORKER_MODE_BLACKLIST:
        return {"Blacklist": ",".join(workers)} if workers else {}
    if not workers:
        raise ValueError("Whitelist is empty: select at least one worker")
    return {"Whitelist": ",".join(workers)}


def add_environment_item(job_infos, key, value):
    """Append ``key=value`` as the next free ``EnvironmentKeyValue<n>`` entry.

    Mirrors ``Prism_Deadline_Functions.addEnvironmentItem`` so later calls
    from Deadline's own submission code (project-level env vars) continue
    the numbering instead of colliding with these.
    """
    idx = 0
    while True:
        k = "EnvironmentKeyValue" + str(idx)
        if k not in job_infos:
            job_infos[k] = "%s=%s" % (key, value)
            return job_infos
        idx += 1


def job_info_file_path(home_dir):
    return os.path.join(home_dir, "temp", "helixae_submit_info.job")


def plugin_info_file_path(home_dir):
    return os.path.join(home_dir, "temp", "helixae_plugin_info.job")


def build_job_infos(
    name,
    comment,
    pool,
    secondary_pool,
    group,
    priority,
    start_frame,
    end_frame,
    chunk_size,
    output_path,
    prism_project,
    prism_source_scene,
    concurrent_tasks=1,
    limit_concurrent_tasks_to_cpus=True,
    suspended=False,
    worker_filter=None,
):
    """Build the Deadline job-info dict for one AfterEffects job."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("job name is required")
    priority = int(priority)
    if not (0 <= priority <= 100):
        raise ValueError("priority must be between 0 and 100: %r" % (priority,))
    chunk_size = int(chunk_size)
    if chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    concurrent_tasks = int(concurrent_tasks)
    if concurrent_tasks <= 0:
        raise ValueError("concurrent tasks must be positive")
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("output path is required")

    job_infos = {
        "Plugin": "AfterEffects",
        "Name": name,
        "Comment": comment or "",
        "Pool": pool or "none",
        "SecondaryPool": secondary_pool or "",
        "Group": group or "none",
        "Priority": priority,
        "Frames": format_frame_range(start_frame, end_frame),
        "ChunkSize": chunk_size,
        "ConcurrentTasks": concurrent_tasks,
        "LimitConcurrentTasksToNumberOfCpus": (
            "true" if limit_concurrent_tasks_to_cpus else "false"
        ),
        "OutputFilename0": to_deadline_output_filename(output_path),
    }
    add_environment_item(job_infos, "prism_project", prism_project)
    add_environment_item(job_infos, "prism_source_scene", prism_source_scene)
    if suspended:
        job_infos["InitialStatus"] = "Suspended"
    for key, value in (worker_filter or {}).items():
        if key not in ("Whitelist", "Blacklist"):
            raise ValueError("unsupported worker filter key: %r" % (key,))
        job_infos[key] = value
    return job_infos


def build_plugin_infos(comp_name, output_path, major_version, app_version_str, scene_file=None):
    """Build the Deadline plugin-info dict for one AfterEffects job.

    ``scene_file`` is only set when the project's ``submitScenes`` setting
    is disabled; when scenes are submitted as auxiliary files (the default,
    matching ``Prism_Deadline_Functions.sm_render_submitJob``), ``SceneFile``
    is omitted and Deadline resolves it from the copied auxiliary file.
    """
    if not isinstance(comp_name, str) or not comp_name.strip():
        raise ValueError("composition name is required")
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("output path is required")
    major = int(major_version)
    if major <= 0:
        raise ValueError(
            "invalid After Effects major version: %r" % (major_version,)
        )

    plugin_infos = {
        "Comp": comp_name,
        # Raw AE fsName, [#####] padding kept -- see module docstring.
        "Output": output_path,
        "Version": "%d.0" % major,
    }
    if app_version_str:
        plugin_infos["SubmittedFromVersion"] = str(app_version_str)
    if scene_file:
        plugin_infos["SceneFile"] = scene_file
    return plugin_infos


def parse_job_id(result):
    """Extract the job id from ``deadlinecommand``'s submission output.

    Mirrors ``Prism_Deadline_Functions.getJobIdFromSubmitResult``.  Returns
    ``None`` (never raises) when no ``JobID=`` line is present, e.g. on a
    failed submission.
    """
    text = "" if result is None else str(result)
    for line in text.splitlines():
        if line.startswith("JobID"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                job_id = parts[1].strip().strip("\r")
                if job_id:
                    return job_id
    return None
