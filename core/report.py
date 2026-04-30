"""
core/report.py
==============
Generates structured convergence reports from multi-lens analysis.
Outputs JSON + markdown.
"""

import json
import datetime
import os
from typing import List


def generate_report(track, convergence_engine, output_dir: str = "reports") -> dict:
    os.makedirs(output_dir, exist_ok=True)

    vel   = track.velocity_summary()
    conv  = convergence_engine.summary()
    segs  = track.segments()

    report = {
        "meta": {
            "event":         track.name,
            "date":          track.date,
            "generated":     datetime.datetime.utcnow().isoformat(),
            "description":   track.description,
        },
        "track": {
            "witnesses":       len(track.witnesses),
            "duration_min":    track.duration_minutes(),
            "total_dist_km":   sum(s["dist_km"] for s in segs),
            "avg_speed_kmh":   vel["avg_speed_kmh"],
            "max_speed_kmh":   vel["max_speed_kmh"],
            "heading_std_deg": vel["heading_std_deg"],
            "anomalous_segments": vel.get("segments_exceeding_max", []),
            "heading_reversals":  vel["anomalous_headings"],
        },
        "lenses":      conv["per_lens"],
        "convergence": {
            "events":         conv["convergence_events"],
            "top":            conv["top_convergences"],
        },
        "null_return": convergence_engine.lens_results.get("nexrad", []),
        "verdict": _verdict(vel, conv),
    }

    # Save JSON
    slug = track.name.lower().replace(" ", "_")
    json_path = os.path.join(output_dir, f"{slug}_report.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Save markdown
    md_path = os.path.join(output_dir, f"{slug}_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_to_markdown(report))

    print(f"\n  Report saved: {json_path}")
    print(f"  Report saved: {md_path}")

    return report


def _verdict(vel: dict, conv: dict) -> dict:
    flags = []

    if vel.get("segments_exceeding_max"):
        n = len(vel["segments_exceeding_max"])
        flags.append(f"{n} track segments exceed reference aircraft maximum speed")

    if vel.get("anomalous_headings"):
        flags.append(f"{len(vel['anomalous_headings'])} anomalous heading changes detected")

    total_anom = sum(conv["per_lens"].values())
    if total_anom > 10:
        flags.append(f"{total_anom} total anomalies across {len(conv['per_lens'])} independent datasets")

    n_conv = conv["convergence_events"]
    if n_conv > 0:
        flags.append(f"{n_conv} multi-dataset convergence events (simultaneous anomalies across independent sensors)")

    if not flags:
        conclusion = "No significant anomalies detected. Event consistent with conventional explanation."
    elif len(flags) == 1:
        conclusion = "Minor anomaly detected. Warrants further investigation."
    elif len(flags) <= 3:
        conclusion = "Multiple independent anomalies detected. Conventional explanation faces significant challenges."
    else:
        conclusion = "Strong multi-dataset anomaly convergence. Event exhibits characteristics inconsistent with conventional explanation across all tested sensor types."

    return {"flags": flags, "conclusion": conclusion}


def _to_markdown(report: dict) -> str:
    r = report
    m = r["meta"]
    t = r["track"]
    v = r["verdict"]
    lines = [
        f"# UAP Analysis Report: {m['event']}",
        f"**Date:** {m['date']}  |  **Generated:** {m['generated'][:10]}",
        f"\n{m.get('description','')}",
        "\n---\n",
        "## Track Summary",
        f"- Witnesses: {t['witnesses']}",
        f"- Duration: {t['duration_min']:.1f} minutes",
        f"- Total distance: {t['total_dist_km']:.1f} km",
        f"- Average speed: {t['avg_speed_kmh']} km/h",
        f"- Maximum speed: {t['max_speed_kmh']} km/h",
        f"- Heading consistency (std): {t['heading_std_deg']}°",
        "\n## Dataset Anomalies",
    ]

    for lens, count in r["lenses"].items():
        lines.append(f"- **{lens}**: {count} anomalies")

    lines += ["\n## Convergence Events"]
    conv = r["convergence"]
    lines.append(f"Total multi-dataset convergence events: **{conv['events']}**\n")
    for c in conv.get("top", [])[:3]:
        pos = c.get("position")
        pos_str = f"{pos['lat']:.3f}°N, {pos['lon']:.3f}°W" if pos else "unknown"
        lines.append(f"- **{c['time']}** | Lenses: {', '.join(c['lenses'])} | Peak: {c['max_sigma']}σ | Position: {pos_str}")

    lines += ["\n## Verdict", "**Anomaly Flags:**"]
    for flag in v["flags"]:
        lines.append(f"- {flag}")
    lines.append(f"\n**Conclusion:** {v['conclusion']}")

    return "\n".join(lines)
