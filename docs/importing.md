# Importing

## Opening the Import Dialog

Use the **Import Media** button in the CEP panel, or right-click empty space in the Footage Tracker, to open the Import dialog.

---

## Selecting a Shot

1. Click **Choose...** at the top of the dialog
2. A shot browser will open — select the shot(s) you want to import from
3. The dialog will populate with all available renders for that shot

---

## Filtering by Type

Use the type filter checkboxes to narrow down what's shown:

| Filter | What it shows |
|---|---|
| **3D** | 3D renders (EXR sequences, AOV passes) |
| **2D** | 2D renders (composited outputs, painted frames) |
| **PB** | Playblasts (animation previews) |

All three are checked by default. Uncheck any you don't need.

---

## The Import Table

The table shows all available footage matching your filters:

| Column | Description |
|---|---|
| **Shot** | Shot name |
| **Type** | 3D / 2D / PB |
| **Task / Identifier** | The task or render identifier |
| **AOV** | AOV pass name (for 3D renders) |
| **Version** | Latest available version |
| **Status** | Shows ✓ if already imported into the current AE project |

You can select multiple rows (Ctrl+click or Shift+click).

---

## Search

Press **Ctrl+Space** to open the search bar. It filters across Shot, Type, Task, AOV, and Version columns. Wildcards are supported (`*`, `?`).

---

## Importing

1. Select the rows you want
2. Click **Import Selected**

The footage will be imported into your AE project and organized into the appropriate folders automatically.

---

## Adding Footage to a Composition

After importing, you can add any footage item directly to a composition from the Footage Tracker:

1. Right-click the footage item
2. **Add to Comp → Current Comp** — adds it to whichever comp you have open
3. **Add to Comp → Choose Comp...** — opens a picker to select the target comp

This works on already-imported footage at any time, not just right after importing.
