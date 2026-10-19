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
| **Output Module** | Select which render template to use |
| **Local output** | Toggle whether output goes to local or network path |

Click **Add to Render Queue** to save and queue the render.

This does **not** start rendering. In After Effects, check the queued composition and
output settings, then click **Render** in the Render Queue. Export metadata is written
only after After Effects confirms that the queue item was created successfully.

The dialog shows which composition will be queued. That composition is captured when the
dialog opens and is queued by identity, so changing the active composition in After
Effects does not change the render.

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
- **Stop** cancels the queue operation. The project save has already happened.

Because the snapshot is taken when the render is queued, editing the composition
afterwards does not update it. Re-queue the render to refresh the metadata.

---

## After Rendering

After Effects writes the media to the versioned output path selected when queuing.
Queuing reserves the output version and writes metadata; it does not confirm that media
has rendered. Once usable media exists, other artists can discover it on refresh.
