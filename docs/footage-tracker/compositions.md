# Compositions

## Overview

The Footage Tracker also displays your **compositions** in the tree, grouped under the Comps section. You can manage them directly from the tracker.

---

## Right-Click Menu on a Composition

Right-click any composition in the tracker to get these options:

| Action | What it does |
|---|---|
| **Open Composition** | Opens the comp in the After Effects timeline |
| **Reveal in Project** | Selects the comp in the AE Project panel |
| **Show Info** | Displays composition metadata (resolution, FPS, frame range, duration) |
| **Set Frame Range from Kitsu** | Updates the comp's in/out points to match the shot's frame range in Kitsu |
| **Set FPS from Kitsu** | Updates the comp's FPS to match the shot's FPS in Kitsu |
| **Set From Kitsu** | Applies both frame range and FPS from Kitsu in one step |
| **Remove Unused** | Removes all comps and footage items not used by this composition |
| **Bypass / Unbypass** | Hides or shows the comp in the tracker tree |

---

## Syncing Comps to Kitsu

If your shot's frame range or FPS has been updated in Kitsu, you can sync your comp in one click:

1. Right-click the composition in the tracker
2. Choose **Set From Kitsu**

This updates both the frame range and FPS of the comp to match what's in Kitsu.

---

## Remove Unused

**Remove Unused** is a cleanup tool. It scans the selected composition and removes any AE project items (comps, footage) that aren't referenced by it. Use this before rendering or archiving to keep the project clean.

!!! warning
    This action cannot be undone. Make sure you have a saved version before running it.
