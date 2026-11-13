# Render Dependency Repair Runbook

How to migrate old render `versioninfo.json` files to output-scoped
`renderDependencies` metadata so HelixArchive archives only the files actually
used by each rendered composition. Written for future runs: the artist provides
the render versions (movies, screenshots, or Prism paths); everything below is
the procedure that was proven on Cytonics_CYT108 (66 repaired + 3 reconstructed,
all verified).

Schema being added to each render version (all other fields are preserved):

```json
"renderDependencies": {
  "context": {"application": "aftereffects", "type": "composition",
              "identifier": "<AE comp id>", "name": "<comp name>"},
  "dependencies": ["<3D/2D render sequences actually used>"],
  "externalFiles": ["<resources/external files actually used>"]
}
```

Resolver rules and the HelixArchive contract: `docs/helixarchive-render-dependencies.md`.

## Requirements

- `ssh helix` — After Effects running, MCP bridge panel open (Auto-run ON).
  The repair tools talk to AE through the bridge mailbox in
  `C:/Users/<user>/AppData/Local/ae-mcp-bridge/` (staged command JSON +
  polled result JSON, one request at a time). After AE restarts the panel must
  be reopened or every call fails with "AE query failed".
- `ssh nassk` — the NAS (`X:` maps to `/volume1/Renders/X/`, `Z:` to
  `/volume1/Renders/`).
- Local repo checkout; all tools live in `tools/` which is **local-only**
  (`dev_sync.sh` does not deploy it). Nothing here is part of the plugin.
- No unsaved changes in AE; the tools refuse to run dirty.

## Evidence hierarchy for comp identity (strongest first)

1. **Completed render-queue match** — open the version's recorded
   `sourceScene`, find Done queue items whose output path lands in the target
   version directory (movies must match the exact existing filename). Requires
   one unique comp ID per output; conflicting comps = refuse.
2. **Movie XMP `creatorAtom:aeProjectLink`** — AE embeds `compositionID` and
   `fullPath` in the output movie at render time. Cross-checked against the
   JSON's `sourceScene` before use. Use this when queue enumeration is
   impossible or crashes AE.
3. **Artist confirmation** (`--confirmed-comp NAME`,
   `--confirmed-source PATH`) — explicit authority when scenes were overwritten
   or `sourceScene` is empty. The artist names the comp/source; the tool never
   guesses.
4. **Reconstruction (create-only)** — for versions with **no** JSON at all.
   Provenance must come from the render artifact itself (Alembic tail strings,
   movie moov XMP), verified against the source scene's saved states. No backup
   is possible; publication is create-only via `os.link` (never overwrites).

Never infer the comp from the AE active comp, the version/task name, or
`used_in_comps` sidecar lists. Those are hints for investigation only.

## Tools

| Tool | Purpose |
|---|---|
| `audit_render_dependency_samples.py` | Read-only recursive dependency audit (AE queue scans + NAS metadata walk, cycle-guarded, full-depth). Produces `cytonics-sample-dependency-audit.json/.md`. |
| `repair_selected_render_dependencies.py` | The batch repair engine. Roots = selected edit outputs; recursively follows publishes; per-version queue-evidence scans; backup-first atomic publish; resumable journal + `--verify-only`. |
| `repair_xmp_evidence.py` | XMP-evidence variant for versions whose queue enumeration crashes AE or has no queue match. One script round trip per scene. Appends to the same journal. |
| `reconstruct_animation_v0001.py` / `reconstruct_bg_v0001.py` / `reconstruct_no_signals_v0001.py` | Create-only reconstructions for missing JSONs (Maya Alembic provenance / AE movie XMP provenance; the last is a subclass template). |
| `repair_render_dependencies.jsx` (in `Resources/`) | Manual in-AE fallback: dialog to pick comp + target JSON, backup-first update. Use when automation is not wanted. |
| `cytonics-render-repair-guide.md` | Worked example: scene/JSON pair tables for one full project. |

## Standard workflow

1. **Inventory** (NAS-only, read-only): read each target `versioninfo.json`
   (`sourceScene`, existing fields), confirm the source `.aep` exists, list the
   version directory's actual outputs. Report unresolved/ambiguous mappings to
   the artist before touching anything.
2. **Dry-run scan**: open each source scene, match the render queue, run
   `build_comp_dependency_script` + strict `parse_comp_dependency_result`,
   classify with the real `FootageUtils.detectFolderType`, check existence on
   the NAS. The producer contract **excludes missing paths** from the block;
   they are reported, never written.
3. **Publish** (per version, atomic on the NAS):
   - refuse if the live JSON changed since the scan (`expected` check);
   - write byte-verified backup `<target>.before-render-deps.<run>.bak`
     (mode `xb`, never overwrites an existing backup);
   - stage in the same directory, re-parse, verify all unrelated fields are
     unchanged, `os.replace`, re-verify both files.
4. **Verify**: `--verify-only <journal>` independently re-reads production
   targets and backups (SHA-256 + field equality) and regenerates the `.md`
   report. Finish with a NAS-only recursive walk: every reachable AE publish
   must have a valid scoped block, zero unscoped versions.

## Command patterns

```bash
# Full chain from the selected edit renders (resume a journal any number of times)
python tools/repair_selected_render_dependencies.py --apply --resume tools/<run>.json --mcp
python tools/repair_selected_render_dependencies.py --apply --resume tools/<run>.json --mcp --retry-mappings

# One version at a time after an AE crash (always do this, not batches)
python tools/repair_selected_render_dependencies.py --apply --resume tools/<run>.json --mcp \
    --max-ae 1 --only-version "X:/<project>/.../<task>/v0011"

# Artist-confirmed comp (scene currently open, dirty allowed, never saves/switches)
python tools/repair_selected_render_dependencies.py --apply --resume tools/<run>.json --mcp \
    --confirmed-comp "SQ020-SH010_HighRes_v0005" --only-version "X:/.../v0006"

# Fill an EMPTY sourceScene with artist-authorized evidence
python tools/repair_selected_render_dependencies.py --apply --resume tools/<run>.json --mcp \
    --confirmed-source "X:/.../scene_v0024.aep" --only-version "X:/.../v0011"

# XMP-evidence repairs for queue-less / crash-prone versions
python tools/repair_xmp_evidence.py --apply --only-version "X:/.../v0011"

# Independent verification + report regeneration
python tools/repair_selected_render_dependencies.py --verify-only tools/<run>.json
```

Multiple comps feeding one version directory are legal (context becomes
`type: "composition-set"` with both compositions listed).

## Hard-won gotchas

- **Some scenes crash AE during render-queue enumeration** (Cytonics
  `SQ020-SH020_HighRes_v0040.aep` did, three times). Symptom: open succeeds,
  the next queue query kills AE. Solution: skip the queue entirely — use the
  movie XMP for identity (`repair_xmp_evidence.py`) and scan the comp in ONE
  round trip. Never batch attempts on a scene that crashed; run one
  `--max-ae 1` per restart.
- **AE must be clean before switching projects.** Dirty projects are saved to
  Temp recovery copies first (logged in the journal), but prefer the artist
  resolving dirt beforehand.
- **AE's own save flow complicates evidence**: HelixAE saves the scene BEFORE
  queueing, so the completed item may only exist in LATER saved versions.
  `--retry-mappings` opens later scene versions for identity evidence only,
  then reopens the exact original source for the dependency scan
  (`queue_evidence_scene` in the journal).
- `sourceScene` can disagree with reality in both directions (stale
  scene-overwrites, post-render saves). The render artifact (queue output path
  or movie XMP) outranks the JSON. `field_updates` in the publish transaction
  only ever fills an EMPTY `sourceScene`; replacing a non-empty one requires an
  explicit decision and is recorded in the journal/report.
- **Missing `versioninfo.json` cannot be "repaired"** — the producer requires
  an original to back up. Reconstruction is a separate, stricter path with
  create-only publication and no user/username attribution (the exporter is
  unknown; never copy the scene artist's identity).
- Paths are case-sensitive on the NAS; normalize `X:`/`Z:`/UNC consistently
  (the audit module's `norm`/`local` helpers do this).
- Sequences are represented by ONE existing representative frame
  (e.g. `...1001.exr`); HelixArchive expands them. Missing representatives are
  excluded from blocks but visible in audit reports.
- Audio lands in `externalFiles`, never `dependencies`.
- Empty-but-valid blocks are authoritative (comp uses no file-backed inputs).
  A failed scan + Continue must REMOVE the key, never write an empty fake
  (panel behavior; the batch tools just refuse).

## After the run

- Hand `tools/<run>.md` (verified report) to whoever runs HelixArchive.
- Leave the journals and backups in place; the NAS backups are the rollback.
- Tools are local-only and project-specific by design (hardcoded roots). For a
  new project: duplicate the roots/paths, keep the transaction and evidence
  logic untouched.
