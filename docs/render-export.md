# Render & Export

## Rendering a Shot

When your comp is ready, use HelixAE to add it to the After Effects Render Queue.

---

## Opening the Render Dialog

Click **Render...** in the CEP panel.

---

## The Export Dialog

The panel's **Render...** button opens the Prism-managed export dialog:

| Field | Description |
|---|---|
| **Task** | The Prism task this export belongs to |
| **Use next version** | Automatically increments to the next version number (on by default) |
| **Comment** | Optional comment saved with this export version |
| **Output Template** | An output-module template available in After Effects |
| **Local output** | Toggle whether output goes to local or network path |

Click **Add to Render Queue** to queue and save the render.

This does **not** start rendering. In After Effects, check the queued composition and
output settings, then click **Render** in the Render Queue. The render-queue item is
added first, then the scene is saved as a new version so the saved `.aep` already
contains it; export metadata is written only after After Effects confirms the queue
item was created successfully.

The dialog shows which composition will be queued. That composition is captured when the
dialog opens and is queued by identity, so changing the active composition in After
Effects does not change the render.

---

## Output templates

The dialog lists the output-module templates that exist in your After Effects. HelixAE
does not ship, load or manage templates. The selected template's format, depth,
channels and audio are read from AE and checked again when the item is queued; the
file extension comes from AE's actual format. A template whose format has no known
extension is rejected rather than given a guessed `.avi`.

After Effects does not store the Output Module's output color space in a template,
and scripting cannot set or read it, so set it yourself in the queued item's Output
Module Settings > Color Management.

For ACES editorial output: ACES EXRs -> 32-bit comp -> PNG 8-bit with the correct
sRGB display output baked in. A later encoding job must not apply ACES again.
The confirmed output module is saved into the `.aep` for both local and Deadline
renders; workers need compatible AE/codecs/OCIO configurations. This does **not**
yet create a dependent sequence-to-video conversion job.

---

## Submitting to Deadline

If the project's Deadline plugin is set up, the export dialog shows an additional
**Submit to Deadline** group (hidden entirely when Deadline isn't available):

| Field | Description |
|---|---|
| **Group** | Deadline group, loaded the first time the group is checked. Pools aren't offered for now; jobs go to pool `none` |
| **Workers** | **All workers**; **Only this PC** (whitelists just your machine, which must be a Deadline worker); **Whitelist** (only the checked workers); **Blacklist** (every worker except the checked ones). Workers must also be in the Group. **Refresh workers** re-reads the list from Deadline |
| **Priority** | Job priority, 0-100 (default 50) |
| **Frames per Task** | Frames per Deadline task for image-sequence outputs (default 10; see below for movie outputs) |
| **Concurrent Tasks** | How many `aerender` processes may run at once on the same worker for this job (1-16, default 6). Each one is a separate process with its own memory footprint, so raise this only if the worker has the RAM to spare. Only useful for image sequences; a worker's own "Concurrent Task Limit Override" can still cap it. |
| **Limit to CPU count** | Caps concurrent tasks to the worker's CPU count (on by default) |
| **Submit suspended** | Submits the job suspended so it can be reviewed before it starts rendering |

These are remembered per Prism user and restored next time the dialog opens.

Checking **Submit to Deadline** changes what **Add to Render Queue** does: the local
render-queue item is still added and the scene still saved exactly as described above -
the saved `.aep` is the file Deadline's After Effects worker opens on the farm - and the
Deadline job is submitted afterwards. A failed Deadline submission never removes the
local render-queue item or its metadata; the render still exists locally either way.

### Duplicate-composition rule

Deadline's After Effects worker runs `aerender -comp "<name>"`, which renders a
composition's **first currently-queued** render-queue item using that item's own output
module. After a Deadline submission the local queue item for that comp stays "Queued" in
After Effects, so queuing the *next* version of the same composition before resolving
this would make the farm job silently re-render the stale item instead of the new one.

HelixAE checks for other queued items on the same composition before adding the new one
and before saving. If any are found, you're asked to **Uncheck and Continue** (unticks
the conflicting items in the Render Queue panel) or **Cancel**.

### Movie vs. sequence outputs

Movie-container outputs (`.mov`, `.mp4`, `.avi`, `.mxf`, etc.) always render as a single
Deadline task with a single concurrent task, since one movie file can't be rendered by
multiple `aerender` processes at once. **Frames per Task** and **Concurrent Tasks** only
take effect for image-sequence outputs.

### AE 2025+ on the farm

The Deadline repository's stock `AfterEffects` worker plugin only ships render
executables up to AE 2020 (17.0). Farm rendering with AE 2025 or later needs a
`custom/plugins/AfterEffects` override on the repository adding a `RenderExecutable25_0`
(or newer) entry pointing at the installed `aerender.exe` - if a submission fails with a
"could not find executable" error, ask the Deadline repository admin to check for that
override rather than treating it as a HelixAE bug.

---

## Dependency Metadata

The render `versioninfo.json` keeps the scene-wide `dependencies` and `externalFiles`
arrays and adds a DCC-independent `renderDependencies` object for the queued output:

```json
"renderDependencies": {
  "context": {
    "application": "aftereffects",
    "type": "composition",
    "identifier": "123",
    "name": "SH010_MainComp"
  },
  "dependencies": ["Z:/.../beauty.0001.exr"],
  "externalFiles": ["Z:/.../plate.mov"]
}
```

`renderDependencies.dependencies` contains the 3D and 2D render files used by
every layer in the composition, including nested precompositions and disabled
or hidden layers. `renderDependencies.externalFiles` contains resources and
external footage. Image sequences are represented by one file; the archive
tool expands the sequence.

Dependencies are collected before the render is queued. If the scan fails, or if source
files are missing, HelixAE asks whether to **Continue** or **Stop**:

- **Continue** queues the render without `renderDependencies` when the scan failed, or with
  only the files that exist when sources are missing.
- **Stop** cancels before anything is queued or saved.

Because the snapshot is taken when the render is queued, editing the composition
afterwards does not update it. Re-queue the render to refresh the metadata.

---

## After Rendering

After Effects writes the media to the versioned output path selected when queuing.
Queuing reserves the output version and writes metadata; it does not confirm that media
has rendered. Once usable media exists, other artists can discover it on refresh.
