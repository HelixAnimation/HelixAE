# Resize AOV Images

## What is Resize AOV Images?

This tool batch-resizes an EXR image sequence to a smaller resolution, replacing its
source frames after preserving backups. Smaller frames can play back faster in After Effects.

Only appears on **3D render footage** (EXR sequences).

---

## When Would You Use This?

- Your EXR sequences are **4K or larger** and AE is slow to preview
- You want to reduce the resolution of an existing image sequence
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
    The resize runs using **OpenImageIO**. Output dimensions and channels are checked
    before replacement. Deep, multipart and mipmapped images are rejected. Validate
    ID/Cryptomatte results on your installed OpenImageIO version before production use.

!!! warning
    Resized images **replace the source frames**. Originals remain in the backup folder
    reported by the tool. A failed file leaves its source intact. **Cancel** lets the
    current file finish safely, then skips remaining files; the summary reports completed,
    failed and skipped counts. This is a one-time operation; newly rendered frames are
    not resized automatically.
