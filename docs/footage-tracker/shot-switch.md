# Shot Switch

## What is Shot Switch?

**Shot Switch** lets you redirect a footage item to the same render pass in a **different shot**, while keeping the identifier and AOV intact. HelixAE automatically picks the latest available version in the target shot.

This is different from **Change Shot** — here's the distinction:

| | Shot Switch | Change Shot |
|---|---|---|
| **Use case** | Flip between shot variants (e.g. hero vs VFX shot) | Point footage at a completely different shot |
| **Identifier/AOV** | Preserved automatically | You choose manually |
| **Version** | Auto-selects latest | You choose manually |

---

## When Would You Use This?

Common scenarios:

- A shot has a **hero version** and a **VFX variant** (e.g. `sh010` and `sh010_vfx`) and you need to switch between them for a review
- You're building a **comp template** that needs to work across multiple shots — switch the shot to test it
- A shot was **renamed or split** and you need to redirect your existing comp to the new shot

---

## How to Use It

1. Right-click the footage item in the Footage Tracker
2. Hover over **Shot Switch**
3. The submenu lists all available alternative shots
4. Click the target shot — HelixAE updates the footage path to the latest version of the same identifier/AOV in that shot

---

## Notes

!!! info
    **Shot Switch only appears** if HelixAE detects alternative shots with matching renders. If the submenu is empty or missing, no matching renders were found in other shots.

If you need to switch to a shot with a **different identifier or AOV**, use **Change Shot** instead (right-click → Change Shot), which gives you full manual control.
