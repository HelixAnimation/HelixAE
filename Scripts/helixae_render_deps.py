# -*- coding: utf-8 -*-
"""Output-scoped render dependency metadata.

Pure-stdlib helpers used by the export flow.  The AE walk itself lives in
``helixae_protocol``; this module only classifies the returned file-backed
footage records and updates the render ``versioninfo.json`` atomically.

The block intentionally mirrors the existing scene-wide fields so the
archive tool can choose between all scene dependencies and the subset
needed to reproduce one render output::

    "renderDependencies": {
        "context": {
            "application": "aftereffects",
            "type": "composition",
            "identifier": "123",
            "name": "SH010_MainComp"
        },
        "dependencies": ["..."],
        "externalFiles": ["..."]
    }
"""

import json
import os
import tempfile

_RENDER_GROUPS = ("01_3D_Renders", "02_2D_Renders")


def normalize_path(path):
    """Return a forward-slash path suitable for JSON metadata."""
    if isinstance(path, bytes):
        path = path.decode("utf-8")
    return str(path).replace("\\", "/")


def build_render_dependencies_block(
    composition,
    footage_records,
    classify_folder,
    path_exists=os.path.exists,
):
    """Build the universal ``renderDependencies`` block for an AE comp.

    ``classify_folder`` must accept a path and return one of the
    ``FootageUtils.detectFolderType`` values.  Render categories go to
    ``dependencies``; everything else goes to ``externalFiles``.
    Non-existent paths are reported separately instead of being silently
    written as usable dependencies.

    Returns ``(block, missing_paths)``.
    """
    if not isinstance(composition, dict):
        raise ValueError("composition must be an object")
    comp_id = composition.get("id")
    comp_name = composition.get("name")
    if comp_id is None or not str(comp_id).strip():
        raise ValueError("composition id is required")
    if not isinstance(comp_name, str):
        raise ValueError("composition name is required")

    dependencies = set()
    external_files = set()
    missing = set()
    seen = set()

    for record in footage_records or []:
        if not isinstance(record, dict):
            raise ValueError("malformed footage record")
        path = normalize_path(record.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)

        if not path_exists(path):
            missing.add(path)
            continue

        group = classify_folder(path)
        if group in _RENDER_GROUPS:
            dependencies.add(path)
        else:
            external_files.add(path)

    block = {
        "context": {
            "application": "aftereffects",
            "type": "composition",
            "identifier": str(comp_id),
            "name": comp_name,
        },
        "dependencies": sorted(dependencies),
        "externalFiles": sorted(external_files),
    }
    return block, sorted(missing)


def apply_render_dependencies(versioninfo, block):
    """Set or clear the output-scoped block on a versioninfo dict."""
    # Remove metadata written by the short-lived AE-specific schema.
    versioninfo.pop("compDependencies", None)
    if block is None:
        versioninfo.pop("renderDependencies", None)
    else:
        versioninfo["renderDependencies"] = block


def write_json_atomic(path, data):
    """Write JSON next to ``path`` and replace the target atomically."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(
        prefix=".%s." % os.path.basename(path),
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
