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

You can manually reassign footage to a different shot, task or pass:

- Right-click → **Change Shot** → pick from the list or choose **Custom...**
- Right-click → **Change 2D/3D Identifier** → pick or type a custom name
- Right-click → **Change AOV** (3D renders only) → pick another pass of the same identifier

**Change AOV** keeps the footage's current version when that version contains
the chosen pass; otherwise it uses the newest version that does. The current
AOV is shown at the top of the submenu and is not offered as a target.

!!! warning
    After changing shot, identifier or AOV, the tracker will look for the matching render in the new location. Make sure the target render exists before changing.
