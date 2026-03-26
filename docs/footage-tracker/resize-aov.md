# Resize AOV Images

## What is Resize AOV Images?

This tool batch-resizes an EXR image sequence to a smaller resolution. It's used to create **proxy versions** of heavy 3D render passes so After Effects can play them back faster during compositing.

Only appears on **3D render footage** (EXR sequences).

---

## When Would You Use This?

- Your EXR sequences are **4K or larger** and AE is slow to preview
- You want to work on comp layout and timing before switching to full-res renders
- You need a **lightweight version** of AOV passes to share or review without transferring full-res files

---

## How to Use It

1. Right-click a 3D footage item in the Footage Tracker
2. Hover over **Resize AOV Images**
3. Select the target resolution from the submenu
4. The tool processes the image sequence and saves the resized version

---

## Notes

!!! info
    The resize runs using **OpenImageIO**, a professional image processing library. It handles EXR correctly, preserving colour space and channel data.

!!! warning
    Resized images are saved alongside the originals, not overwriting them. This is a one-time batch operation — it does not create a live link. If new frames are rendered, you'll need to resize again.
