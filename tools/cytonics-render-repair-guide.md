# Cytonics CYT108 — historical render dependency repair guide

Read-only NAS inventory: 2026-10-19. No production JSON was changed by this inventory.

## Scope and evidence

Selected Edit/MAIN outputs: HighRes v0019, v0016, v0015, v0012, v0011, v0005;
LowRes v0007. Some outputs are MP4, even though the request calls them MOVs.

Six have recorded, existing AE sources. HighRes v0011 has an empty sourceScene.
The six traceable edits reference 45 distinct direct input publishes: 41 AE
renders and four Maya/Houdini playblasts. Every direct input has versioninfo.json
and an existing source scene. None of these seven edit JSONs or 45 direct input
JSONs had renderDependencies at inspection time.

IMPORTANT: these are historical SCENE-WIDE dependency references, not proof that
every input was used in the rendered composition. Repair the edit compositions
first, then use their new renderDependencies arrays to select the shot repairs.
Comp names cannot be inferred from task names: several HighRes scenes contain
comps named LowRes. Choose the historical render comp yourself in AE.

## 1. Start with the edit compositions

Common root for every path below:

`X:\Cytonics_CYT108\03_Production\Shots\`

Each source and target column is relative to that root. Open the source, run
repair_render_dependencies.jsx, select the intended edit composition, then
select the matching target JSON. Do not save a new scene version first.

| Edit output | AE source to open | JSON to select |
|---|---|---|
| HighRes v0019 | `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0041.aep` | `Edit\MAIN\Renders\2dRender\HighRes\v0019\versioninfo.json` |
| HighRes v0016 | `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0029.aep` | `Edit\MAIN\Renders\2dRender\HighRes\v0016\versioninfo.json` |
| HighRes v0015 | `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0028.aep` | `Edit\MAIN\Renders\2dRender\HighRes\v0015\versioninfo.json` |
| HighRes v0012 | `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0025.aep` | `Edit\MAIN\Renders\2dRender\HighRes\v0012\versioninfo.json` |
| HighRes v0011 | **UNRESOLVED — see below** | `Edit\MAIN\Renders\2dRender\HighRes\v0011\versioninfo.json` |
| HighRes v0005 | `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0012.aep` | `Edit\MAIN\Renders\2dRender\HighRes\v0005\versioninfo.json` |
| LowRes v0007 | `Edit\MAIN\Scenefiles\LookDev\LowRes\Edit-MAIN_LowRes_v0019.aep` | `Edit\MAIN\Renders\2dRender\LowRes\v0007\versioninfo.json` |

### First repair — complete paths ready to paste

Open:

`X:\Cytonics_CYT108\03_Production\Shots\Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0041.aep`

Target:

`X:\Cytonics_CYT108\03_Production\Shots\Edit\MAIN\Renders\2dRender\HighRes\v0019\versioninfo.json`

After repair, tell the assistant which target was updated. It can read the new
block and narrow the shot worklist to the actual selected comp's inputs.

### HighRes v0011 — unresolved source

Its JSON has sourceScene="", empty dependencies/externalFiles, date
24.07.26 14:30:28 and comment "Option C for the Audio".

Candidate ONLY: `Edit\MAIN\Scenefiles\LookDev\HighRes\Edit-MAIN_HighRes_v0024.aep`.
Its sidecar references `Cytonics CYT-108_2026.07.23_C_2.wav`; its generation time
is 2026-07-24T12:27:13.865772Z. The next known output, HighRes v0012, records
scene v0025 and "Option D for the Audio"; that sidecar references D_2.wav.
This supports investigating v0024, but DOES NOT establish the v0011 mapping.
Confirm using the saved render queue/output path or your historical knowledge.

The current repair script intentionally rejects a missing sourceScene. It
cannot repair v0011 as-is; resolve its source first and handle that case
explicitly. Do not point it at v0024 and assume it will proceed.

## 2. Direct shot AE renders — candidate repair inventory

This table is deduplicated across the six traceable edits. Repair only entries
still referenced after the edit composition scans.

To build full paths for a row:

- Convert shot `SQ020-SH020` to folder `SQ020\SH020`.
- **Open source:** `<root><shot folder>\Scenefiles\LookDev\<source column>`.
- **Choose JSON:** `<root><shot folder>\Renders\2dRender\<render column>\versioninfo.json`.
- H19/H16/H15/H12/H05 refer to the selected Edit/MAIN HighRes versions;
  L07 refers to selected Edit/MAIN LowRes v0007.

| Shot | Render task/version | Source below Scenefiles\LookDev | Referenced by edits |
|---|---|---|---|
| SQ010-SH010 | `HighRes\v0001` | `HighRes\SQ010-SH010_HighRes_v0008.aep` | H19 H16 H15 H12 H05 |
| SQ010-SH010 | `LowRes\v0006` | `LowRes\SQ010-SH010_LowRes_v0015.aep` | L07 |
| SQ010-SH020 | `HighRes\v0001` | `HighRes\SQ010-SH020_HighRes_v0003.aep` | H19 H16 H15 H12 H05 |
| SQ010-SH020 | `LowRes\v0005` | `LowRes\SQ010-SH020_LowRes_v0013.aep` | L07 |
| SQ010-SH030 | `HighRes\v0001` | `HighRes\SQ010-SH030_HighRes_v0004.aep` | H19 H16 H15 H12 H05 |
| SQ010-SH030 | `LowRes\v0004` | `LowRes\SQ010-SH030_LowRes_v0011.aep` | L07 |
| SQ020-SH010 | `HighRes\v0004` | `HighRes\SQ020-SH010_HighRes_v0008.aep` | H05 |
| SQ020-SH010 | `HighRes\v0006` | `HighRes\SQ020-SH010_HighRes_v0016.aep` | H19 H16 H15 H12 |
| SQ020-SH010 | `LowRes\v0008` | `LowRes\SQ020-SH010_LowRes_v0020.aep` | L07 |
| SQ020-SH020 | `HighRes\v0004` | `HighRes\SQ020-SH020_HighRes_v0019.aep` | H05 |
| SQ020-SH020 | `HighRes\v0011` | `HighRes\SQ020-SH020_HighRes_v0040.aep` | H12 |
| SQ020-SH020 | `HighRes\v0012` | `HighRes\SQ020-SH020_HighRes_v0041.aep` | H16 H15 |
| SQ020-SH020 | `HighRes\v0015` | `HighRes\SQ020-SH020_HighRes_v0052.aep` | H19 |
| SQ020-SH020 | `LowRes\v0004` | `LowRes\SQ020-SH020_LowRes_v0018.aep` | L07 |
| SQ020-SH030 | `HighRes\v0001` | `HighRes\SQ020-SH030_HighRes_v0002.aep` | H05 |
| SQ020-SH030 | `HighRes\v0003` | `HighRes\SQ020-SH030_HighRes_v0007.aep` | H19 H16 H15 H12 |
| SQ020-SH030 | `LowRes\v0002` | `LowRes\SQ020-SH030_LowRes_v0007.aep` | L07 |
| SQ020-SH050 | `HighRes\v0004` | `HighRes\SQ020-SH050_HighRes_v0007.aep` | H05 |
| SQ020-SH050 | `HighRes\v0005` | `HighRes\SQ020-SH050_HighRes_v0010.aep` | H19 H16 H15 H12 |
| SQ020-SH060 | `HighRes\v0001` | `HighRes\SQ020-SH060_HighRes_v0009.aep` | H19 H16 H15 H12 |
| SQ020-SH060 | `LowRes\v0004` | `HighRes\SQ020-SH060_HighRes_v0008.aep` | H05 |
| SQ030-SH010 | `HighRes\v0002` | `HighRes\SQ030-SH010_HighRes_v0007.aep` | H19 H16 H15 H12 H05 |
| SQ030-SH010 | `LowRes\v0004` | `LowRes\SQ030-SH010_LowRes_v0009.aep` | L07 |
| SQ030-SH020 | `HighRes\v0003` | `LightBeam\SQ030-SH020_LightBeam_v0018.aep` | H12 H05 |
| SQ030-SH020 | `HighRes\v0005` | `LightBeam\SQ030-SH020_LightBeam_v0019.aep` | H16 H15 |
| SQ030-SH020 | `HighRes\v0007` | `LightBeam\SQ030-SH020_LightBeam_v0020.aep` | H19 |
| SQ030-SH020 | `LowRes\v0005` | `LightBeam\SQ030-SH020_LightBeam_v0013.aep` | L07 |
| SQ030-SH030 | `HighRes\v0001` | `HighRes\SQ030-SH030_HighRes_v0002.aep` | H12 H05 |
| SQ030-SH030 | `HighRes\v0003` | `HighRes\SQ030-SH030_HighRes_v0006.aep` | H16 H15 |
| SQ030-SH030 | `HighRes\v0004` | `HighRes\SQ030-SH030_HighRes_v0011.aep` | H19 |
| SQ030-SH030 | `LowRes\v0002` | `LowRes\SQ030-SH030_LowRes_v0009.aep` | L07 |
| SQ030-SH040 | `HighRes\v0001` | `HighRes\SQ030-SH040_HighRes_v0003.aep` | H12 H05 |
| SQ030-SH040 | `HighRes\v0003` | `HighRes\SQ030-SH040_HighRes_v0006.aep` | H16 H15 |
| SQ030-SH040 | `HighRes\v0005` | `HighRes\SQ030-SH040_HighRes_v0008.aep` | H19 |
| SQ030-SH040 | `LowRes\v0001` | `LowRes\SQ030-SH040_LowRes_v0005.aep` | L07 |
| SQ030-SH050 | `HighRes\v0001` | `HighRes\SQ030-SH050_HighRes_v0002.aep` | H19 H16 H15 H12 H05 |
| SQ030-SH050 | `LowRes\v0002` | `LowRes\SQ030-SH050_LowRes_v0005.aep` | L07 |
| SQ030-SH060 | `HighRes\v0002` | `HighRes\SQ030-SH060_HighRes_v0007.aep` | H19 H16 H15 H12 H05 |
| SQ040-SH010 | `HighRes\v0002` | `HighRes\SQ040-SH010_HighRes_v0015.aep` | H05 |
| SQ040-SH010 | `HighRes\v0005` | `HighRes\SQ040-SH010_HighRes_v0020.aep` | H19 H16 H15 H12 |
| SQ040-SH010 | `LowRes\v0003` | `LowRes\SQ040-SH010_LowRes_v0012.aep` | L07 |

For SQ020-SH020 HighRes v0015, the user already identified the intended comp as
`SQ020-SH020_HighRes_v0001` in source scene v0052. This confirmation does not
automatically apply to other versions or scenes.

## 3. Direct playblasts — not AE repair targets

Paths below use the same root. Preserve their normal metadata chain; do not
apply the AE composition script to Maya/Houdini versions.

| Edit | Playblast JSON | Source scene |
|---|---|---|
| H19 | `SQ020\SH020\Playblasts\Extra_protease\v0004\versioninfo.json` | `SQ020\SH020\Scenefiles\Animation\Extra_protease\SQ020-SH020_Extra_protease_v0017.ma` |
| L07 | `SQ020\SH050\Playblasts\Layout\v0002\versioninfo.json` | `SQ020\SH050\Scenefiles\Layout\Layout\SQ020-SH050_Layout_v0003.hip` |
| L07 | `SQ020\SH060\Playblasts\Layout\v0001\versioninfo.json` | `SQ020\SH060\Scenefiles\Layout\Layout\SQ020-SH060_Layout_v0002.hip` |
| L07 | `SQ030\SH060\Playblasts\Layout\v0004\versioninfo.json` | `SQ030\SH060\Scenefiles\Layout\Layout\SQ030-SH060_Layout_v0006.ma` |

## 4. Nested 2D renders — conditional follow-up

Recursively following the existing top-level dependency arrays finds 35 more
version directories beyond the seven edits and 45 direct inputs: 32 with JSON
and existing AE source scenes, three without versioninfo.json. The walk was
deduplicated/cycle-guarded. This is a candidate graph, not the final comp graph;
older scenes contain previous outputs and unused background renders.

After each shot repair, follow only its new renderDependencies. Use the same
source/target path construction rules from section 2 for these rows.

| Shot | Render task/version | Source below Scenefiles\LookDev |
|---|---|---|
| SQ010-SH010 | `LowRes\v0007` | `HighRes\SQ010-SH010_HighRes_v0003.aep` |
| SQ010-SH010 | `LowRes\v0005` | `LowRes\SQ010-SH010_LowRes_v0012.aep` |
| SQ010-SH010 | `LowRes\v0004` | `LowRes\SQ010-SH010_LowRes_v0009.aep` |
| SQ010-SH010 | `LowRes\v0003` | `LowRes\SQ010-SH010_LowRes_v0008.aep` |
| SQ010-SH010 | `LowRes\v0001` | `LowRes\SQ010-SH010_LowRes_v0003.aep` |
| SQ020-SH010 | `BG\v0006` | `HighRes\SQ020-SH010_HighRes_v0015.aep` |
| SQ020-SH010 | `BG\v0005` | `HighRes\SQ020-SH010_HighRes_v0013.aep` |
| SQ020-SH010 | `BG\v0004` | `HighRes\SQ020-SH010_HighRes_v0007.aep` |
| SQ020-SH010 | `BG\v0003` | `HighRes\SQ020-SH010_HighRes_v0003.aep` |
| SQ020-SH010 | `BG\v0002` | `LowRes\SQ020-SH010_LowRes_v0019.aep` |
| SQ020-SH020 | `BG\v0014` | `HighRes\SQ020-SH020_HighRes_v0047.aep` |
| SQ020-SH020 | `BG\v0011` | `HighRes\SQ020-SH020_HighRes_v0039.aep` |
| SQ020-SH020 | `BG\v0010` | `HighRes\SQ020-SH020_HighRes_v0030.aep` |
| SQ020-SH020 | `BG\v0009` | `HighRes\SQ020-SH020_HighRes_v0028.aep` |
| SQ020-SH020 | `BG\v0007` | `HighRes\SQ020-SH020_HighRes_v0023.aep` |
| SQ020-SH020 | `BG\v0005` | `HighRes\SQ020-SH020_HighRes_v0015.aep` |
| SQ020-SH020 | `BG\v0004` | `HighRes\SQ020-SH020_HighRes_v0007.aep` |
| SQ020-SH020 | `BG\v0002` | `LowRes\SQ020-SH020_LowRes_v0011.aep` |
| SQ020-SH020 | `HighRes\v0013` | `HighRes\SQ020-SH020_HighRes_v0046.aep` |
| SQ020-SH020 | `HighRes\v0003` | `HighRes\SQ020-SH020_HighRes_v0016.aep` |
| SQ020-SH020 | `SQ030-SH010_BG\v0001` | `HighRes\SQ020-SH020_HighRes_v0013.aep` |
| SQ020-SH030 | `BG\v0002` | `HighRes\SQ020-SH030_HighRes_v0006.aep` |
| SQ020-SH030 | `BG\v0001` | `HighRes\SQ020-SH030_HighRes_v0004.aep` |
| SQ020-SH030 | `LowRes\v0001` | `LowRes\SQ020-SH030_LowRes_v0003.aep` |
| SQ020-SH050 | `HighRes\v0003` | `HighRes\SQ020-SH050_HighRes_v0006.aep` |
| SQ030-SH020 | `No_Signals\v0009` | `HighRes\SQ030-SH020_HighRes_v0013.aep` |
| SQ030-SH020 | `No_Signals\v0007` | `HighRes\SQ030-SH020_HighRes_v0011.aep` |
| SQ030-SH020 | `No_Signals\v0004` | `HighRes\SQ030-SH020_HighRes_v0005.aep` |
| SQ030-SH020 | `No_Signals\v0003` | `LowRes\SQ030-SH020_LowRes_v0017.aep` |
| SQ030-SH020 | `LightBeam\v0002` | `LightBeam\SQ030-SH020_LightBeam_v0005.aep` |
| SQ030-SH020 | `LowRes\v0001` | `LowRes\SQ030-SH020_LowRes_v0009.aep` |
| SQ030-SH060 | `LowRes\v0001` | `LowRes\SQ030-SH060_LowRes_v0006.aep` |

Missing JSONs (source mapping unavailable through versioninfo):

- `SQ020\SH010\Renders\2dRender\BG\v0001\versioninfo.json`
- `SQ020\SH020\Renders\2dRender\BG\v0001\versioninfo.json`
- `SQ020\SH020\Renders\2dRender\BG\v0013\versioninfo.json`

The script patches an existing JSON; it cannot invent these missing records.
Investigate only if the repaired comp graph still reaches these versions.

## Operating loop

1. Open the exact source listed for a render version.
2. Run the temporary JSX and explicitly choose the historical rendered comp.
3. Select that render version's versioninfo.json, not the scene's similarly
   named `<scene stem>versioninfo.json`.
4. Review dependencies and any missing inputs; Back Up & Update when correct.
5. Have the assistant verify the new JSON/backup and read the new dependency
   block before deciding which scene to open next.
6. Continue recursively through referenced 2D publish versions, once per
   version; the archive resolver also follows each publish's own metadata.

This inventory does not validate every media frame or 3D publish dependency.
It verifies the source-scene mappings and target-JSON existence stated above.
