# Cytonics — missing publish metadata investigation

Read-only investigation, 2026-10-19. Follow-up to
`cytonics-sample-dependency-audit.md`. No production JSON or source scene was
saved, repaired, or recreated. AE was restored to HighRes scene v0046.

## SQ020–SH021 Animation v0001 — exact source confirmed

Existing output (25,608,689,743 bytes):

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH021\Export\Animation\v0001\SQ020-SH021_Animation_v0001.abc`

Missing publish metadata:

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH021\Export\Animation\v0001\versioninfo.json`

Confirmed existing source:

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH021\Scenefiles\Animation\Animation\SQ020-SH021_Animation_v0005.ma`

Evidence:

- The Alembic Ogawa metadata near the end of the output contains:
  - `_ai_Application=Maya 2022 AbcExport v1.0`
  - `_ai_DateWritten=Thu May 21 14:52:24 2026`
  - `_ai_Description=Exported from: X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH021/Scenefiles/Animation/Animation/SQ020-SH021_Animation_v0005.ma`
- The source Maya ASCII file's embedded PrismStates JSON contains an Export
  state whose `lastexportpath` equals the exact Animation v0001 Alembic path.
- Later scenes also retain that old export state, so that state alone would
  not prove provenance; the Alembic's own embedded source confirms v0005.
- The v0005 scene's saved import states refer to CYT108 Rigging v0001 and
  Protease Modeling v0002. Those are leads for reconstructing upstream
  metadata, not a claim that all source dependencies have been fully scanned.

This is a Maya export. Do not assign an AE composition block to it. Its source
is now known, but missing publish metadata still requires deliberate recovery
or reconstruction. The scene's own versioninfo lacks dependency arrays.

## SQ020–SH020 BG v0013 — composition confirmed; media absent

Output directory exists but contains **zero entries**, including no JSON:

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH020\Renders\2dRender\BG\v0013`

Missing referenced frame:

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH020\Renders\2dRender\BG\v0013\SQ020-SH020_BG_v0013_00000.png`

Confirmed composition: `SQ020-SH020_BG_v0001`, AE item ID **17**.

Saved AE queue evidence, inspected by opening the sources with warnings
temporarily suppressed and querying the bridge:

| Existing source scene | Queue count | Completed BG v0013 items |
|---|---:|---|
| `SQ020-SH020_HighRes_v0044.aep` | 58 | None |
| `SQ020-SH020_HighRes_v0045.aep` | 60 | 59, 60 |
| `SQ020-SH020_HighRes_v0046.aep` | 70 | 59, 60, 61, 64, 66, 67, 68 |

Every matching completed item points to composition ID 17 and output:

`X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH020\Renders\2dRender\BG\v0013\SQ020-SH020_BG_v0013_[#####].png`

The two relevant existing scene paths are:

- `X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH020\Scenefiles\LookDev\HighRes\SQ020-SH020_HighRes_v0045.aep`
- `X:\Cytonics_CYT108\03_Production\Shots\SQ020\SH020\Scenefiles\LookDev\HighRes\SQ020-SH020_HighRes_v0046.aep`

Scene v0045 is the earliest checked snapshot with completed BG v0013 renders;
v0046 records additional completed renders to the same version. Queue history
proves the comp-to-output mapping, but does not prove the exact project state
that produced the final overwrite. No original publish JSON survives in the
directory to settle the sourceScene value.

The missing publish directories were also checked at the direct mirrored
paths under the common NAS `#recycle` locations; no corresponding directory
was found there. This was not an exhaustive snapshot/backup search.

Creating versioninfo alone cannot recover the absent image sequence. The
current AE producer excludes this missing footage path when regenerating
HighRes v0013 metadata; the earlier audit intentionally displayed it as a
diagnostic unresolved reference. Preserve that distinction when repairing.

## Result

- Animation v0001: source-scene mapping resolved with embedded output provenance.
- BG v0013: exact comp resolved and source snapshots located; original final
  render source state remains ambiguous, and the rendered media is absent.
- No missing publish JSON has been written. Decide how to handle the missing
  BG media separately from the metadata repair.
