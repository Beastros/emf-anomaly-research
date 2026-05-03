# UAP Sniffer

UAP Sniffer is a reproducible, event-timeline-first analysis framework for historical anomalous events.
It asks one core question:

> Do independent public sensor datasets show time-aligned anomaly markers during the same window as a reported event?

This repo combines witness-track timing with physical sensor archives (magnetometer, space weather, radar/archive availability, infrasound, weather) and scores anomalies using rolling-baseline sigma methods.

## Start Here

- **Public report page (GitHub Pages):** `docs/index.html`
- **Canonical Phoenix report (markdown):** `outputs/phoenix_lights_report.md`
- **Short share note:** `outputs/phoenix_lights_signal_share_note.md`

If you are sharing the project publicly, use the Phoenix report as the primary artifact.

## Why This Project Is Interesting

- It treats historical events as analyzable timelines rather than only narrative claims.
- It focuses on reproducible, timestamped markers from public datasets.
- It supports cross-lens convergence checks to reduce single-sensor overfitting.
- It preserves methods and intermediate mechanics, not only final narrative output.

## Core Method (High Level)

1. Build an event track from known points/timestamps.
2. Pull public sensor streams around the event window.
3. Compute rolling-baseline sigma anomalies per lens.
4. Detect overlap windows where multiple lenses spike close in time.
5. Export machine-readable results + human-readable reports.

## Repo Layout

- `sniffer.py`: main event-runner CLI
- `phoenix_run_models.py`: orchestrated model run + export flow
- `core/`: anomaly logic, report generation, event/model primitives
- `lenses/`: sensor adapters (magnetometer, omni, asos, nexrad, etc.)
- `events/`: event definitions
- `outputs/`: public-facing markdown artifacts
- `tools/`: one-off probes and data diagnostics
- `archive/legacy-top-level/`: older scripts retained for reproducibility/history

## Minimal Run Commands

```bash
python sniffer.py --event phoenix_lights_1997 --lenses all
python phoenix_run_models.py --event phoenix_lights_1997
```

## Data Policy

This project uses publicly available archives where possible.
Some high-value corroboration layers are not publicly accessible for historical windows.
