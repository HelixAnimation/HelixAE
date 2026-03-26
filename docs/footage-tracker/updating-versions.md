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

## Changing Shot or Identifier Manually

You can manually reassign footage to a different shot or task:

- Right-click → **Change Shot** → pick from the list or choose **Custom...**
- Right-click → **Change 2D/3D Identifier** → pick or type a custom name

!!! warning
    After changing shot or identifier, the tracker will look for the matching render in the new location. Make sure the target render exists before changing.
