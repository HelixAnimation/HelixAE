# HelixArchive Render Dependency Migration

This guide describes the HelixArchive resolver change required to consume
output-scoped render metadata from HelixAE, Houdini, and other DCCs.

The producer is already implemented in HelixAE. The required change is in
HelixArchive's dependency walker.

## Confirmed HelixAE Contract

Each render version's `versioninfo.json` keeps the existing scene-wide fields
and adds one output-scoped block:

```json
{
  "sourceScene": "X:/Project/Scenefiles/shot_v0060.aep",
  "dependencies": [
    "X:/Project/Renders/3dRender/Lighting/v0018/beauty/shot.1001.exr"
  ],
  "externalFiles": [
    "X:/Project/Resources/reference.mov"
  ],
  "renderDependencies": {
    "context": {
      "application": "aftereffects",
      "type": "composition",
      "identifier": "123",
      "name": "SH010_MainComp"
    },
    "dependencies": [
      "X:/Project/Renders/3dRender/Lighting/v0018/beauty/shot.1001.exr"
    ],
    "externalFiles": [
      "X:/Project/Resources/reference.mov"
    ]
  }
}
```

A Houdini producer can use the identical block and arrays with a different
context, for example:

```json
"context": {
  "application": "houdini",
  "type": "node",
  "identifier": "/out/karma1",
  "name": "karma1"
}
```

The fields have these meanings:

| Field | Scope | Meaning |
|---|---|---|
| top-level `dependencies` | Scene | 3D and 2D render footage used anywhere in the AE project |
| top-level `externalFiles` | Scene | Resource and external footage used anywhere in the AE project |
| `renderDependencies.dependencies` | Output | 3D and 2D render footage reachable from the queued render context |
| `renderDependencies.externalFiles` | Output | Resource and external footage reachable from the queued render context |
| `renderDependencies.context` | Output | Informational DCC and render-context identity captured when the render was queued |

All dependency entries in `renderDependencies` are absolute path strings with
forward slashes. The lists are sorted and deduplicated by HelixAE. A numbered
image sequence is represented by one existing frame, which HelixArchive must
expand with its existing `_expand_numbered_candidate()` logic.

The comp walk includes nested precompositions and examines all layers,
including hidden and disabled layers. It records file-backed AE
`FootageItem` sources only. Generated media, fonts, plugins, expressions, and
other non-file AE requirements are outside this contract.

If HelixAE cannot scan the composition and the artist chooses Continue, it
removes `renderDependencies` rather than writing a misleading empty block. If
only some source files are missing, the valid block is written without those
missing paths.

## Important Sidecar Distinction

HelixAE's actual `<project_stem>_archiveinfo.json` shape is:

```json
{
  "source_paths": {
    "3d_renders": [],
    "2d_renders": [],
    "resources": []
  },
  "resource_paths": [],
  "external_paths": []
}
```

The sidecar remains scene-wide. HelixAE copies its render paths into the
top-level `dependencies` array and its resource/external paths into the
top-level `externalFiles` array.

HelixArchive currently reads `sourceScene`, discovers the sidecar, and adds
its scene-wide `source_paths` before processing `versioninfo.json` dependency
entries. Merely preferring `renderDependencies` over the top-level arrays is
therefore insufficient: the sidecar paths would still reintroduce the whole
scene.

When a valid `renderDependencies` block exists, the resolver must:

1. Keep collecting the referenced `.aep` itself when it exists.
2. Do not add that source scene's `_archiveinfo.json` paths.
3. Ignore the top-level scene-wide `dependencies` and `externalFiles` arrays.
4. Resolve both arrays inside `renderDependencies` through the existing normal
   dependency path, including sequence expansion and recursive Prism publish
   walking.

The sidecar and top-level arrays remain the fallback for old renders and for
new renders where the comp scan failed.

## Resolver Selection Rules

Treat a render block as authoritative when:

- `renderDependencies` is a dictionary;
- `dependencies` is a list;
- `externalFiles` is a list; and
- every entry in both lists is a non-empty string.

The `context` object is useful for diagnostics and UI labels, but it should
not control path resolution. HelixAE writes `application: "aftereffects"`,
`type: "composition"`, and string `identifier` and `name` values. Houdini can
use the same block with its own application, node type, identifier, and name.
Rejecting otherwise usable paths because this label is malformed would
unnecessarily fall back to scene-wide collection.

A valid block with two empty arrays is authoritative. It means the render
context has no file-backed inputs. Do not fall back to scene-wide metadata
because the lists are empty.

A few HelixAE renders created before the universal rename can contain the
short-lived `compDependencies` key. HelixArchive can accept it as a legacy
alias when `renderDependencies` is absent. New metadata must only write
`renderDependencies`.

Use this behavior matrix:

| `renderDependencies` state | Collect source scene | Read scene-wide metadata | Read top-level arrays | Read render arrays |
|---|---:|---:|---:|---:|
| Valid and populated | Yes | No | No | Yes |
| Valid and empty | Yes | No | No | Yes |
| Valid legacy `compDependencies` | Yes | No | No | Yes |
| Missing | Yes | Yes | Yes | No |
| Malformed | Yes | Yes | Yes | No |

## Suggested Implementation

Add a small parser near the other metadata helpers in `dep_walker.py`:

```python
def _render_dependency_entries(data):
    """Return (authoritative, entries, context)."""
    block = data.get("renderDependencies")
    legacy = False
    if block is None:
        block = data.get("compDependencies")
        legacy = block is not None
    if not isinstance(block, dict):
        return False, [], None

    dependencies = block.get("dependencies")
    external_files = block.get("externalFiles")
    if not isinstance(dependencies, list) or not isinstance(external_files, list):
        return False, [], None

    entries = dependencies + external_files
    if any(not isinstance(entry, str) or not entry.strip() for entry in entries):
        return False, [], None

    context = block.get("context")
    if legacy and not isinstance(context, dict):
        composition = block.get("composition")
        if isinstance(composition, dict):
            context = {
                "application": "aftereffects",
                "type": "composition",
                "identifier": str(composition.get("id", "")),
                "name": str(composition.get("name", "")),
            }
    if not isinstance(context, dict):
        context = None

    return True, entries, context
```

In `walk_dependencies()`, select the dependency source once per version:

```python
has_render_scope, dependency_entries, context = _render_dependency_entries(data)

source_scene = data.get("sourceScene", "")
if source_scene:
    scene_path = os.path.normpath(source_scene)

    # Preserve the existing source-scene collection and depth handling.
    if _path_exists(scene_path, cache):
        collected.add(scene_path)

    # A valid render block replaces this scene-wide expansion.
    if not has_render_scope:
        for path in read_aftereffects_archive_dependencies(scene_path, cache):
            if _path_exists(path, cache):
                collected.add(path)
                record["inputs"].add(path)

if not has_render_scope:
    dependency_entries = []
    for field in ("dependencies", "externalFiles"):
        values = data.get(field, [])
        if isinstance(values, list):
            dependency_entries.extend(values)

for entry in dependency_entries:
    for candidate in expand_dependency_entry(entry, cache):
        # Keep the existing find_version_dir(), recursive walk, loose-file,
        # sequence, depth, and provenance behavior here.
        resolve_dependency_candidate(candidate)
```

The exact integration should reuse the current dependency loop instead of
adding a second implementation. The only semantic changes should be selecting
the source arrays and conditionally suppressing sidecar expansion.

Do not globally disable `read_aftereffects_archive_dependencies()`. It remains
needed for:

- legacy render metadata without `renderDependencies`; and
- loose `.aep` dependencies encountered through the existing recursive walk.

## Recursion and Sequence Handling

Pass render entries through `expand_dependency_entry()` exactly like existing
top-level entries. Although HelixAE currently emits strings, using the shared
path keeps all established behavior:

- `_expand_numbered_candidate()` expands representative frames;
- `find_version_dir()` detects a Prism publish and recursively follows its
  `versioninfo.json` chain;
- loose files remain leaf dependencies;
- loose `.aep` files can still use their own sidecars; and
- existing case-insensitive deduplication remains unchanged.

This is intentionally different from sidecar `source_paths`, which are added
directly and do not recurse through a discovered Prism version. Output-scoped
entries should use the recursive versioninfo path because they occupy the
same role as the existing top-level dependency arrays.

## Cache and Provenance Changes

Do not cache `renderDependencies` by `sourceScene`. Two render versions can
reference the same `.aep` but queue different compositions. The render block is
owned by the render version's `versioninfo.json`.

The existing sidecar cache keyed by scene path can remain unchanged for the
legacy fallback.

For provenance:

- keep the source `.aep` as an input of the render version;
- record the resolved render paths in that version's `record["inputs"]`;
- do not record suppressed scene-wide sidecar paths; and
- optionally retain the `context` fields for display or
  diagnostics.

If `build_working_scene_index()` continues grouping solely by source scene,
multiple render contexts from one scene may appear as a union in a scene UI
filter. That does not make archive resolution incorrect because provenance
remains per version. If the UI must distinguish render contexts, key scene
entries by normalized source scene plus `context.application`, `context.type`,
and `context.identifier` instead of source scene alone.

## Required Regression Tests

Add focused tests around `walk_dependencies()` and `resolve_and_collect()`:

1. A valid render block collects output-scoped paths but not top-level-only or
   sidecar-only paths.
2. A valid empty render block does not fall back to the sidecar or top-level
   arrays.
3. Missing `renderDependencies` preserves the complete legacy behavior.
4. Malformed `renderDependencies` preserves the complete legacy behavior.
5. Both render arrays are processed and sequence-expanded.
6. A render dependency inside a Prism version directory recursively follows
   that version's metadata.
7. Two versions referencing the same `.aep` but different contexts retain
   different dependency sets in provenance.
8. A fresh resolve still gets a fresh operation cache.
9. Existing loose `.aep` dependency sidecar resolution remains unchanged.
10. Missing render paths are skipped using the existing missing-path behavior.

The most important regression assertion is that a path present only in the
scene sidecar or top-level arrays is absent when a valid render block exists.

## Rollout

This change is backward compatible at the metadata boundary:

- old HelixAE renders without output-scoped metadata use the legacy resolver;
- short-lived `compDependencies` metadata can be read as a compatibility alias;
- new renders with a successful scan use output-scoped resolution;
- new renders continued after a failed scan have no render block and use the
  legacy resolver; and
- top-level fields and `_archiveinfo.json` remain unchanged for older tools.

No After Effects installation or `.aep` parser is required in HelixArchive.
The resolver remains metadata-driven.
