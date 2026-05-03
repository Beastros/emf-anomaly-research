# UAP Sniffer (Share-Cleaned)

This repository is currently organized around one public-facing artifact:

## Start Here

- **Primary share page:** `outputs/phoenix_lights_report.md`
- **Short version:** `outputs/phoenix_lights_signal_share_note.md`

If you are sharing findings publicly (e.g., Reddit), use the report above as the canonical summary.

---

## What This Repo Contains

- Event configs and witness tracks
- Sensor lenses (magnetometer, spaceweather, radar/archive checks, etc.)
- Analysis scripts and experiments
- Generated output artifacts

Some historical scripts and folders are retained for reproducibility/session history and are not part of the share-ready narrative.

Archived one-off/top-level scripts are now under `archive/legacy-top-level/`.

---

## Minimal Run Commands

```bash
python sniffer.py --event phoenix_lights_1997 --lenses all
python phoenix_run_models.py --event phoenix_lights_1997
```

---

## Data Policy

This project uses publicly available archives where possible.  
Some potentially valuable corroboration datasets are not publicly accessible for the historical windows being analyzed.
