# The Interface

## Opening the Footage Tracker

Click **Footage Tracker...** in the CEP panel. Scene data is prepared in the background
after opening a project, so reopening the tracker can reuse it. If preparation is
still running, the AE inventory appears first and NAS/Kitsu checks follow.

The displayed FPS, dimensions and frame range are AE values. Published metadata is
kept separately and appears in tooltips where available.

---

## The Tree

The main area of the tracker is a tree view showing all footage organised into groups:

- **3D Renders** — EXR sequences and AOV passes
- **2D Renders** — Composited outputs
- **Playblasts** — Animation previews
- **External** — Footage not managed by Prism
- **Comps** — Your After Effects compositions

Each footage item shows the following columns:

| Column | Description |
|---|---|
| **Shot / Identifier / AOV** | The item name, organised hierarchically |
| **Version** | The version currently in your AE project |
| **Status** | Version check result, or composition usage information |
| **Frame Range** | Footage frame range (highlights red if mismatched) |
| **FPS** | Footage FPS (highlights red if mismatched) |
| **Resolution** | Footage resolution |

---

## The Statistics Bar

At the bottom of the tracker, a bar shows:

- **Total footage count**
- **Number of outdated versions**
- **⚠ Check Issues (N)** button — appears when issues are detected (see [Check Issues](check-issues.md))
- An animated progress bar while scene preparation/checks run. The status text
  identifies the current stage; **Checks incomplete** means results are still
  pending or a check was unavailable.

---

## The Refresh Button

Click the **⟳ Refresh** dropdown to reload data:

- **Footage** — refresh the AE inventory and NAS versions in the background,
  keeping the current Kitsu results.
- **Kitsu** — fetch fresh Kitsu data in the background, reusing the current
  inventory and NAS results.

The same actions are available in the middle-click circular menu. Existing rows
remain usable during a same-scene refresh, and enrichment preserves selection,
expansion, filters and scroll position. After switching scenes, old rows are
disabled until the new AE inventory arrives.

**Checking…**, **Cached — NAS unavailable**, and **Not checked** are deliberately
distinct from **Up to date** and **Outdated**. If Kitsu authentication is unavailable,
sign in through Prism and use the existing **Kitsu** refresh action.

---

## Window Controls

- **📌 Always on Top** — Pin the tracker above AE. Click again to unpin. State is saved between sessions.
- **📁 Export Archive** — Export a JSON file with all footage information (useful for archiving or reporting)

---

## Search Bar

Press **Ctrl+Space** to open a floating search bar. Type to filter the tree by Shot, Identifier, AOV, or Version. Wildcards supported (`*`, `?`). Press **Escape** to close.

---

## Navigating to Footage

Right-click any footage item for quick navigation:

- **Reveal in Project** — Selects and highlights the item in the AE Project panel. Useful when you need to find where a render lives without searching manually.
- **Reveal in Compositions** — Shows every composition in the project that uses this footage. Helpful before swapping a version so you know what will be affected.

---

## File Actions

Right-click any footage item for quick file access:

- **Open** — Opens the footage file in its default application (e.g. DJV for EXR sequences)
- **Copy Path** — Copies the full file path to your clipboard
- **Open in Explorer** — Opens the containing folder in Windows Explorer

---

## Bypass / Unbypass

**Bypass** hides an item from the tracker tree without removing it from your AE project. Use it to declutter the view when you have reference footage or old items you're keeping but not actively working with.

Right-click any item → **Bypass** to hide it, **Unbypass** to bring it back.
