"""
core/treasure_hunt_summary.py
=============================
Human-readable 'treasure hunt' recap after a multi-lens run — printed + saved as Markdown.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

from core.anomaly import ConvergenceEngine
from core.lens_tiers import (
    collapse_magnetometer_family,
    instrument_anomalies_for_convergence,
    is_instrument_lens,
)
from core.track import EventTrack


def _slug(track: EventTrack) -> str:
    return track.name.lower().replace(" ", "_")


def _brief_counts(lens_results: Dict[str, dict]) -> List[str]:
    lines = []
    for name in sorted(lens_results.keys()):
        n = len(lens_results[name].get("anomalies", []))
        extra = lens_results[name].get("series_summary") or lens_results[name].get(
            "station_scores"
        )
        if name == "omni" and isinstance(lens_results[name].get("series_summary"), dict):
            s = lens_results[name]["series_summary"]
            lines.append(
                f"- **{name}**: {n} σ-hits  "
                f"(V_mean≈{s.get('v_mean')} km/s, Bz_mean≈{s.get('bz_mean')} nT, "
                f"V_peak_σ={s.get('v_peak_sigma')}, Bz_peak_σ={s.get('bz_peak_sigma')})"
            )
        elif name == "nexrad":
            scores = lens_results[name].get("station_scores") or {}
            ok = sum(1 for v in scores.values() if not v.get("null_return"))
            lines.append(f"- **{name}**: {n} rows  ({ok} stations with archive listings)")
        elif name == "asos" and isinstance(lens_results[name].get("series_summary"), dict):
            ss = lens_results[name]["series_summary"]
            st = ss.get("stations") or {}
            bits = []
            for sid in sorted(st.keys())[:6]:
                b = st[sid]
                vmin = b.get("event_min_vsby_mi")
                sk = b.get("event_max_sknt")
                wx = b.get("wxcodes_flagged") or []
                wxs = ",".join(wx[:4]) if wx else "—"
                bits.append(
                    f"{sid}: vis_min {vmin} mi max_wind {sk} kt wx[{wxs}]"
                    if vmin is not None
                    else f"{sid}: (no event-window obs)"
                )
            lines.append(f"- **{name}**: {n} σ-hits  ({'; '.join(bits)})")
        else:
            lines.append(f"- **{name}**: {n} anomaly rows")
    return lines


def _asos_markdown_section(lens_results: Dict[str, dict]) -> List[str]:
    ar = lens_results.get("asos")
    if not ar:
        return []
    ss = ar.get("series_summary") or {}
    if ss.get("status") != "ok":
        note = ss.get("error") or ss.get("status")
        return ["", "## Local ASOS / METAR", "", f"_No usable METAR table ({note})._", ""]
    lines = [
        "",
        "## Local ASOS / METAR (witness window)",
        "",
        "Logged aviation observations (IEM archive): **visibility**, **wind**, **sky cover** in METAR; ",
        "good for *point* conditions at each airport, not the whole valley.",
        "",
    ]
    for sid in sorted((ss.get("stations") or {}).keys()):
        b = ss["stations"][sid]
        nwin = b.get("event_window_obs", 0)
        vmin = b.get("event_min_vsby_mi")
        vmax = b.get("event_max_vsby_mi")
        sk = b.get("event_max_sknt")
        wx = b.get("wxcodes_flagged") or []
        wxs = ", ".join(wx) if wx else "none flagged"
        if vmin is not None and vmax is not None:
            vis_line = f"visibility **{vmin}–{vmax} mi** (within window)"
        else:
            vis_line = "no observations inside witness span"
        lines.append(
            f"- **{sid}** ({nwin} obs in window): {vis_line}; max wind **{sk} kt**; "
            f"significant wx: {wxs}."
        )
    lines.append("")
    return lines


def _instrument_convergence_peek(
    track: EventTrack, lens_results: Dict[str, dict], window_minutes: float = 10.0
) -> List[str]:
    ce = ConvergenceEngine(track, window_minutes=window_minutes)
    for ln, res in lens_results.items():
        if not is_instrument_lens(ln):
            continue
        raw = res.get("anomalies", [])
        an = instrument_anomalies_for_convergence(ln, raw)
        if an:
            ce.add_lens(ln, an)
    hits = ce.find_convergence(min_lenses=2, lens_family_fn=collapse_magnetometer_family)
    lines = []
    for h in hits[:5]:
        fam = h.get("lens_families", h["lenses"])
        lines.append(
            f"  - `{str(h['time'])[:19]}Z`  families={fam}  peak_σ≈{h['max_sigma']}  "
            f"strength={h['strength']}"
        )
    return lines


def render_markdown(
    track: EventTrack,
    lens_results: Dict[str, dict],
    *,
    bundle: Optional[dict] = None,
    model_payload: Optional[dict] = None,
    artifact_paths: Optional[dict] = None,
    window_minutes: float = 10.0,
) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Treasure hunt summary — {track.name}",
        f"**Event date:** {track.date}  ·  **Generated:** {now}",
        "",
        "## Where to dig",
    ]
    if artifact_paths:
        for k, p in artifact_paths.items():
            lines.append(f"- **{k}:** `{p}`")
    else:
        lines.append(f"- Default output folder: `outputs/` (slug `{_slug(track)}_*`)")

    lines += ["", "## What we pulled (row counts)", ""]
    lines += _brief_counts(lens_results)
    lines += _asos_markdown_section(lens_results)

    if model_payload:
        lines += ["", "## Magnetometer mesh (if present)", ""]
        mp = model_payload.get("percentile_event_count_vs_14nights")
        my = model_payload.get("percentile_event_TUC_Y_peak_vs_14nights")
        if mp is not None:
            lines.append(
                f"- **Network >2σ hit-count** vs ±7-day mesh nights: **{mp}%** percentile "
                f"(see `mag_count_note` in JSON — sums BOU/FRD/SIT/TUC)."
            )
        if my is not None:
            lines.append(
                f"- **TUC Y-component peak σ** vs mesh nights: **{my}%** percentile."
            )
        note = (model_payload.get("meta") or {}).get("mag_count_note")
        if note:
            lines.append(f"- _Note:_ {note}")

    lines += ["", "## Coincidence glitter (instrument-only families)", ""]
    lines.append(
        "_Nexrad `archive_ok` ticks excluded from strict independence; magnetometer "
        "X/Y/Z collapsed to one family._"
    )
    lines.append("")
    peek = _instrument_convergence_peek(track, lens_results, window_minutes)
    if peek:
        lines.extend(peek)
    else:
        lines.append("_No ≥2-family instrument clusters at this window setting._")

    if bundle:
        ma = bundle.get("sensor_bundles_merged") or []
        mi = bundle.get("sensor_bundles_instrument_merged") or []
        lines += [
            "",
            "## Merged bundles (export)",
            f"- **All lenses merged:** {len(ma)} bundles",
            f"- **Instrument merged:** {len(mi)} bundles",
        ]
        if mi:
            top = mi[0]
            lines.append(
                f"- **Richest instrument bundle anchor:** `{top.get('center_time_utc')}` → "
                f"families **{top.get('lens_families')}**  peak_σ **{top.get('max_sigma')}**"
            )

    lines += [
        "",
        "## How to read this",
        "",
        "This is an **exploratory sweep**: aligned timestamps across noisy sensors, ",
        "not evidence of a single physical mechanism. Small overlaps are **interesting scraps**; ",
        "big σ at one observatory on a quiet solar-wind night is a **better trail marker** than ",
        "a pile of placeholder rows.",
        "",
    ]
    return "\n".join(lines)


def write_summary_file(
    track: EventTrack,
    lens_results: Dict[str, dict],
    output_dir: str,
    *,
    bundle: Optional[dict] = None,
    model_payload: Optional[dict] = None,
    artifact_paths: Optional[dict] = None,
    window_minutes: float = 10.0,
    print_to_stdout: bool = True,
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    md = render_markdown(
        track,
        lens_results,
        bundle=bundle,
        model_payload=model_payload,
        artifact_paths=artifact_paths,
        window_minutes=window_minutes,
    )
    path = os.path.join(output_dir, f"{_slug(track)}_treasure_hunt_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    if print_to_stdout:
        print("\n" + "=" * 60)
        print("TREASURE HUNT SUMMARY (also saved to:)")
        print(path)
        print("=" * 60 + "\n")
        print(md)
        print("\n" + "=" * 60 + "\n")
    return path
