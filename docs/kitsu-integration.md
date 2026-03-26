# Kitsu Integration

## What is Kitsu?

Kitsu is the studio's hub for shot management, task tracking, reviews, and feedback. HelixAE connects to Kitsu to pull in shot data — frame ranges, FPS, task statuses — and display it directly in the Footage Tracker.

---

## What Data Comes from Kitsu

| Data | Where it's used |
|---|---|
| **Shot frame range** | Shown in the Frame Range column; used to detect mismatches with your comp |
| **Shot FPS** | Shown in the FPS column; used to detect FPS mismatches |
| **Task status** | Displayed as a colour-coded indicator next to footage items |
| **Task name** | Shown in the tracker tree |

---

## Status Colours

Each footage item in the tracker can show a colour from Kitsu representing the task's current status (e.g. In Progress, Pending Review, Done). These colours come directly from your Kitsu project configuration.

---

## Refreshing Kitsu Data

Kitsu data is cached for **5 minutes** to keep things fast. To refresh:

- Click the **⟳ Refresh** button in the tracker toolbar
    - **Footage** — reloads AE footage using cached Kitsu data (fast)
    - **Kitsu** — forces a fresh fetch from the Kitsu server (bypasses cache)

---

## Opening Shots & Tasks in Kitsu

Right-click any footage item in the tracker:

- **Open Shot in Kitsu** — opens the shot page in your browser
- **Open Task in Kitsu** — opens the specific task page in your browser

This is a quick way to jump to the review or leave a comment without leaving AE.

---

## Syncing from Kitsu

Right-click a footage item → **Sync** submenu:

| Option | What it does |
|---|---|
| **Version** | Updates footage to the latest version from Kitsu |
| **FPS** | Sets footage FPS to match Kitsu |
| **Frame Range** | Sets footage frame range to match Kitsu |
| **Resolution** | Sets footage resolution to match Kitsu |
