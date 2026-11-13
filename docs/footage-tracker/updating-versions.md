# Updating Footage Versions

## Why Update Versions?

When a 3D artist renders a new version of a shot, your AE project still points to the old version. The Footage Tracker detects this and lets you update in a few clicks.

---

## Updating a Single Item

1. Right-click the outdated footage item in the tracker
2. Go to **Sync → Version**
3. The footage in your AE project is updated to the latest version

---

## Updating All Outdated at Once

If multiple items are outdated:

1. Look at the statistics bar at the bottom of the tracker
2. You'll see a count of outdated items
3. Use **Update All Outdated** to update everything in one step

---

## Changing Shot, Identifier or AOV Manually

Right-click any 2D or 3D render → **Change…**:

- **Current Shot (SQxx-SHxxx)** — switch the selected footage to the shot in
  the current `.aep`, keeping each item's identifier and AOV. Versions are
  resolved automatically. This is the fastest path and opens no dialog.
- **Shot…** — choose another shot from a list. Identifier and AOV are kept and
  the latest matching version is used.
- **Identifier…** — choose another identifier for the selected shot/type. The
  latest version is used.
- **AOV…** (3D renders only) — choose another pass for the current identifier.
  The current version is kept when it contains that pass; otherwise the newest
  version with the pass is used.
- **Custom…** — open the combined Shot / Identifier / AOV dialog with a
  preview of every target and the **Advanced — Path Variables…** editor.

The menu itself does not scan the filesystem; each list is built only when its
action is clicked.

!!! warning
    The target render must exist on disk. A missing shot/identifier/AOV is
    reported and is never silently replaced with a different pass.
