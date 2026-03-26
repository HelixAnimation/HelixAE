# HelixAE

A [Prism Pipeline](https://prism-pipeline.com/) plugin for Adobe After Effects. Forked from the official Prism AE plugin and extended with footage tracking, Kitsu integration, AOV management, and render export.

---

## Features

- **Footage Tracker** — Live overview of all footage in your AE project with version, FPS, frame range, and resolution tracking
- **Version Management** — Detect and update outdated footage versions in one click
- **Kitsu Integration** — Sync frame ranges, FPS, and task statuses directly from Kitsu
- **Import Dialog** — Import 3D renders, 2D renders, and playblasts with AOV-level control
- **Shot Switch** — Redirect footage to the same render pass in a different shot
- **AOV Resize** — Batch-resize EXR sequences for proxy workflows
- **Composition Management** — Sync comp frame range and FPS from Kitsu, remove unused items
- **AE Project Organiser** — Auto-organise project items into clean folder structures
- **Render & Export** — Add shots to the AE render queue with Prism version management

---

## Requirements

- [Prism Pipeline](https://prism-pipeline.com/) 2.x
- Adobe After Effects 2020 or later
- Windows 10/11
- Python 3.11 (bundled with Prism)

---

## Installation

1. Clone or download this repository
2. In Prism, go to **Settings → Plugins**
3. Add the plugin path pointing to this folder
4. Restart Prism and open After Effects

The CEP extension is installed automatically by the plugin on first launch.

---

## Documentation

Full artist documentation is available at:

**[chorbest.github.io/HelixAE](https://chorbest.github.io/HelixAE/)**

---

## License

Licensed under the [GNU Lesser General Public License v3.0](LICENSE).
Forked from the official [Prism Pipeline AE plugin](https://github.com/RichardFrangenberg/Prism).
