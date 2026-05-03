"""
lenses/mapview.py
=================
Generates a multi-panel map visualization from sniffer output.
Reads the report JSON and produces a high-quality PNG showing:
- Geographic track colored by speed
- Witness markers with timestamps
- NEXRAD station coverage rings
- Convergence event highlights
- Magnetometer sigma timeline
- Speed profile chart

Run standalone:
    python lenses/mapview.py --event phoenix_lights_1997
Or it runs automatically at end of sniffer.py if included in lenses.
"""

import json
import os
import sys
import datetime
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
import matplotlib.cm as cm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.track import EventTrack, haversine_km

# ── COLORS ───────────────────────────────────────────────────────────────────
BG    = "#030906"
PANEL = "#040e07"
GRN   = "#00ff41"
GDIM  = "#00aa2b"
GFNT  = "#011a06"
RED   = "#ff1a44"
AMB   = "#ffaa00"
BLU   = "#00aaff"
WHT   = "#c8ffd4"
DIM   = "#005c14"
MONO  = "monospace"

# ── ARIZONA OUTLINE (simplified polygon) ─────────────────────────────────────
AZ_LATS = [37.00, 37.00, 36.50, 31.33, 31.33, 31.33, 32.72, 34.00, 35.18, 36.15, 37.00]
AZ_LONS = [-114.05,-109.05,-109.05,-109.05,-111.07,-114.82,-114.72,-114.63,-114.57,-114.05,-114.05]

# ── NEXRAD STATIONS ───────────────────────────────────────────────────────────
NEXRAD = {
    "KFSX": (34.574, -111.198),
    "KIWA": (33.289, -111.670),
    "KEMX": (31.893, -110.630),
    "KYUX": (32.495, -114.656),
}

CITIES = [
    ("PHOENIX",      33.45, -112.07),
    ("TUCSON",       32.22, -110.97),
    ("FLAGSTAFF",    35.20, -111.65),
    ("HENDERSON NV", 36.04, -114.50),
    ("PRESCOTT",     34.54, -112.80),
    ("CHANDLER",     33.28, -111.50),
    ("YUMA",         32.69, -114.50),
]


def speed_color(speed_kmh, ref_max=706):
    """Color based on speed relative to reference max."""
    if speed_kmh <= ref_max * 0.68:  # Below cruise
        return GRN
    elif speed_kmh <= ref_max:        # Below max
        return AMB
    else:                              # Exceeds max
        return RED


def load_report(event_name, reports_dir="outputs"):
    path = os.path.join(reports_dir, f"{event_name}_report.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Report not found: {path}\nRun sniffer first.")
    with open(path) as f:
        return json.load(f)


def load_event(event_name, events_dir="events"):
    path = os.path.join(events_dir, f"{event_name}.json")
    with open(path) as f:
        return json.load(f)


def generate_map(event_name, reports_dir="outputs", events_dir="events",
                 mag_data=None, convergence_events=None):
    """
    Generate full multi-panel map visualization.
    mag_data: dict of {field: AnomalyTimeseries} from magnetometer lens (optional)
    convergence_events: list of convergence hits from convergence engine (optional)
    """
    report     = load_report(event_name, reports_dir)
    event_data = load_event(event_name, events_dir)
    track      = EventTrack(event_data)
    segments   = track.segments()
    witnesses  = [w for w in track.witnesses if w.get("conf", 1) >= 0]
    ref_max    = event_data.get("reference_max_kmh", 706)

    fig = plt.figure(figsize=(20, 14), facecolor=BG)
    gs  = GridSpec(3, 3, figure=fig,
                   left=0.04, right=0.97, top=0.93, bottom=0.05,
                   hspace=0.45, wspace=0.3)

    # ── Panel 1: Main geographic map (spans 2 cols, 2 rows) ──────────────────
    ax_map = fig.add_subplot(gs[0:2, 0:2])
    ax_map.set_facecolor("#010402")
    ax_map.tick_params(colors=DIM, labelsize=7)
    for sp in ax_map.spines.values():
        sp.set_color("#0a2211")

    # Grid
    for lat in range(31, 38):
        ax_map.axhline(lat, color=GFNT, linewidth=0.4, linestyle="--")
        ax_map.text(-115.3, lat+0.05, f"{lat}°N", color=DIM, fontsize=6, fontfamily=MONO)
    for lon in range(-115, -108):
        ax_map.axvline(lon, color=GFNT, linewidth=0.4, linestyle="--")
        ax_map.text(lon+0.05, 30.85, f"{lon}°", color=DIM, fontsize=6, fontfamily=MONO, rotation=45)

    # Arizona outline
    ax_map.plot(AZ_LONS, AZ_LATS, color=GDIM, linewidth=1.5, alpha=0.8)
    ax_map.fill(AZ_LONS, AZ_LATS, alpha=0.05, color=GRN)

    # NEXRAD stations
    for sid, (slat, slon) in NEXRAD.items():
        circle = plt.Circle((slon, slat), 230/111, fill=False,
                            color=GDIM, linewidth=0.5, linestyle="--", alpha=0.5)
        ax_map.add_patch(circle)
        ax_map.plot(slon, slat, "o", color=GRN, markersize=6, zorder=5)
        ax_map.plot(slon, slat, "o", color=BG,  markersize=3, zorder=6)
        ax_map.text(slon+0.1, slat+0.1, sid, color=GRN, fontsize=7,
                   fontfamily=MONO, fontweight="bold", zorder=7)

    # Track segments colored by speed
    for seg in segments:
        # Find witness positions for this segment
        w1 = next((w for w in track.witnesses if w.get("desc","").startswith(seg["from"][:15])), None)
        w2 = next((w for w in track.witnesses if w.get("desc","").startswith(seg["to"][:15])), None)
        if not w1 or not w2:
            continue
        color = speed_color(seg["speed_kmh"], ref_max)
        lw    = 2.5 if seg["speed_kmh"] > ref_max else 1.8

        ax_map.plot([w1["lon"], w2["lon"]], [w1["lat"], w2["lat"]],
                   color=color, linewidth=lw, alpha=0.85, zorder=4,
                   solid_capstyle="round")

        # Speed label at midpoint
        mlat = (w1["lat"] + w2["lat"]) / 2
        mlon = (w1["lon"] + w2["lon"]) / 2
        label = f"{seg['speed_kmh']:.0f}"
        ax_map.text(mlon, mlat, label, color=color, fontsize=6.5,
                   fontfamily=MONO, fontweight="bold", ha="center",
                   path_effects=[pe.withStroke(linewidth=2, foreground=BG)], zorder=8)

        # Direction arrow
        dlat = w2["lat"] - w1["lat"]
        dlon = w2["lon"] - w1["lon"]
        ax_map.annotate("", xy=(mlon + dlon*0.15, mlat + dlat*0.15),
                       xytext=(mlon - dlon*0.01, mlat - dlat*0.01),
                       arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2),
                       zorder=9)

    # Witness markers
    t0 = track.start_time
    for i, w in enumerate(witnesses):
        mins = (w["time"] - t0).total_seconds() / 60
        conf = w.get("conf", 0.5)
        color = RED if conf >= 0.9 else AMB
        size  = 10 if conf >= 0.9 else 7

        ax_map.plot(w["lon"], w["lat"], "^", color=color,
                   markersize=size, zorder=10, alpha=0.9)
        ax_map.plot(w["lon"], w["lat"], "^", color=BG,
                   markersize=size//2, zorder=11)

        # Timestamp label
        ts = w["time"].strftime("%H:%M")
        ax_map.text(w["lon"]+0.1, w["lat"]+0.12,
                   f"{ts}\n{w.get('desc','')[:18]}",
                   color=color, fontsize=5.5, fontfamily=MONO,
                   path_effects=[pe.withStroke(linewidth=1.5, foreground=BG)],
                   zorder=12, va="bottom")

    # Convergence event highlights
    if convergence_events:
        for c in convergence_events:
            pos = c.get("position")
            if pos:
                glow = plt.Circle((pos["lon"], pos["lat"]), 0.3,
                                  fill=True, color=RED, alpha=0.15, zorder=3)
                ring = plt.Circle((pos["lon"], pos["lat"]), 0.3,
                                  fill=False, color=RED, linewidth=1, alpha=0.6, zorder=3)
                ax_map.add_patch(glow)
                ax_map.add_patch(ring)

    # City labels
    for name, lat, lon in CITIES:
        ax_map.text(lon, lat, name, color=DIM, fontsize=6,
                   fontfamily=MONO, alpha=0.8, ha="center")

    ax_map.set_xlim(-115.5, -108.5)
    ax_map.set_ylim(30.7, 37.5)
    ax_map.set_title("FORMATION TRACK — SPEED & HEADING ANALYSIS",
                    color=GRN, fontfamily=MONO, fontsize=10, pad=8)

    # Legend
    legend_elements = [
        mpatches.Patch(color=GRN, label=f"< {int(ref_max*0.68)} km/h (sub-cruise)"),
        mpatches.Patch(color=AMB, label=f"< {ref_max} km/h (within A-10 max)"),
        mpatches.Patch(color=RED, label=f"> {ref_max} km/h (EXCEEDS A-10 MAX)"),
    ]
    ax_map.legend(handles=legend_elements, facecolor=BG, edgecolor="#0a2211",
                 labelcolor=WHT, fontsize=7, loc="lower right",
                 framealpha=0.9)

    # ── Panel 2: Speed profile (top right) ────────────────────────────────────
    ax_spd = fig.add_subplot(gs[0, 2])
    ax_spd.set_facecolor("#010402")
    ax_spd.tick_params(colors=DIM, labelsize=7)
    for sp in ax_spd.spines.values():
        sp.set_color("#0a2211")

    seg_labels = [f"S{i+1}" for i in range(len(segments))]
    seg_speeds = [s["speed_kmh"] for s in segments]
    seg_colors = [speed_color(s, ref_max) for s in seg_speeds]

    bars = ax_spd.bar(seg_labels, seg_speeds, color=seg_colors, edgecolor=BG, linewidth=0.5)
    ax_spd.axhline(ref_max, color=RED, linewidth=1, linestyle="--",
                  label=f"A-10 max ({ref_max} km/h)", alpha=0.8)
    ax_spd.axhline(480, color=AMB, linewidth=0.7, linestyle=":",
                  label="A-10 cruise (~480 km/h)", alpha=0.6)

    for bar, speed in zip(bars, seg_speeds):
        ax_spd.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                   f"{speed:.0f}", ha="center", va="bottom",
                   color=WHT, fontsize=6, fontfamily=MONO)

    ax_spd.set_title("SPEED PROFILE (km/h)", color=GRN, fontfamily=MONO, fontsize=8)
    ax_spd.set_ylabel("km/h", color=DIM, fontfamily=MONO, fontsize=7)
    ax_spd.legend(facecolor=BG, edgecolor="#0a2211", labelcolor=DIM, fontsize=6)
    ax_spd.set_ylim(0, max(seg_speeds) * 1.15)

    # ── Panel 3: Heading profile (middle right) ───────────────────────────────
    ax_hdg = fig.add_subplot(gs[1, 2])
    ax_hdg.set_facecolor("#010402")
    ax_hdg.tick_params(colors=DIM, labelsize=7)
    for sp in ax_hdg.spines.values():
        sp.set_color("#0a2211")

    seg_headings = [s["heading"] for s in segments]
    mean_hdg     = np.mean(seg_headings)
    hdg_colors   = [RED if abs(h - mean_hdg) > 60 else GRN for h in seg_headings]

    ax_hdg.bar(seg_labels, seg_headings, color=hdg_colors, edgecolor=BG, linewidth=0.5)
    ax_hdg.axhline(mean_hdg, color=AMB, linewidth=1, linestyle="--",
                  label=f"Mean heading {mean_hdg:.0f}°", alpha=0.8)
    ax_hdg.set_title("HEADING (degrees)", color=GRN, fontfamily=MONO, fontsize=8)
    ax_hdg.set_ylabel("°", color=DIM, fontfamily=MONO, fontsize=7)
    ax_hdg.legend(facecolor=BG, edgecolor="#0a2211", labelcolor=DIM, fontsize=6)

    for i, (bar, hdg) in enumerate(zip(ax_hdg.patches, seg_headings)):
        ax_hdg.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                   f"{hdg:.0f}°", ha="center", va="bottom",
                   color=RED if hdg_colors[i] == RED else WHT,
                   fontsize=6, fontfamily=MONO)

    # ── Panel 4: Timeline (full bottom row) ───────────────────────────────────
    ax_tl = fig.add_subplot(gs[2, 0:3])
    ax_tl.set_facecolor("#010402")
    ax_tl.tick_params(colors=DIM, labelsize=7)
    for sp in ax_tl.spines.values():
        sp.set_color("#0a2211")

    t0_min = 0
    # Plot speed as area fill along timeline
    seg_times  = []
    seg_spd_tl = []
    for seg in segments:
        t1 = (seg["from_time"] - track.start_time).total_seconds() / 60 if isinstance(seg["from_time"], datetime.datetime) else 0
        t2 = (seg["to_time"]   - track.start_time).total_seconds() / 60 if isinstance(seg["to_time"], datetime.datetime) else 0
        seg_times.extend([t1, t2])
        seg_spd_tl.extend([seg["speed_kmh"], seg["speed_kmh"]])

    if seg_times:
        ax_tl.fill_between(seg_times, seg_spd_tl, alpha=0.2, color=GRN)
        ax_tl.plot(seg_times, seg_spd_tl, color=GRN, linewidth=1.5)
        ax_tl.axhline(ref_max, color=RED, linewidth=1, linestyle="--", alpha=0.7,
                     label=f"A-10 max {ref_max} km/h")

    # Witness markers on timeline
    for w in witnesses:
        t_min = (w["time"] - track.start_time).total_seconds() / 60
        conf  = w.get("conf", 0.5)
        color = RED if conf >= 0.9 else AMB
        ax_tl.axvline(t_min, color=color, linewidth=1.2, alpha=0.8)
        ax_tl.text(t_min + 0.3, ax_tl.get_ylim()[1] * 0.95 if ax_tl.get_ylim()[1] > 0 else 800,
                  w["time"].strftime("%H:%M"),
                  color=color, fontsize=6, fontfamily=MONO, rotation=45, ha="left")

    # Convergence events on timeline
    if convergence_events:
        for c in convergence_events:
            ct = (c["time"] - track.start_time).total_seconds() / 60 if isinstance(c["time"], datetime.datetime) else 0
            n  = c.get("lens_count", 2)
            ax_tl.axvspan(ct - 3, ct + 3, alpha=0.15 * n, color=RED)
            ax_tl.text(ct, 50, f"{c['max_sigma']:.1f}σ",
                      color=RED, fontsize=6, fontfamily=MONO, ha="center",
                      path_effects=[pe.withStroke(linewidth=1.5, foreground=BG)])

    ax_tl.set_xlabel("Minutes from event start", color=DIM, fontfamily=MONO, fontsize=8)
    ax_tl.set_ylabel("Speed (km/h)", color=DIM, fontfamily=MONO, fontsize=8)
    ax_tl.set_title("EVENT TIMELINE — SPEED + WITNESS REPORTS + CONVERGENCE EVENTS",
                   color=GRN, fontfamily=MONO, fontsize=8)
    ax_tl.legend(facecolor=BG, edgecolor="#0a2211", labelcolor=DIM, fontsize=7)

    # ── Title ────────────────────────────────────────────────────────────────
    verdict    = report.get("verdict", {})
    conclusion = verdict.get("conclusion", "")
    fig.suptitle(
        f"UAP SNIFFER — {report['meta']['event'].upper()} — {report['meta']['date']}\n"
        f"{conclusion}",
        color=GRN, fontfamily=MONO, fontsize=11, y=0.97
    )

    # Stats box
    stats = (
        f"Avg: {report['track']['avg_speed_kmh']} km/h  "
        f"Max: {report['track']['max_speed_kmh']} km/h  "
        f"Anomalies: {sum(report['lenses'].values())}  "
        f"Convergence: {report['convergence']['events']}"
    )
    fig.text(0.5, 0.01, stats, ha="center", color=DIM,
            fontfamily=MONO, fontsize=8)

    # Save
    os.makedirs(reports_dir, exist_ok=True)
    out_path = os.path.join(reports_dir, f"{event_name}_map.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"  Map saved: {out_path}")
    return out_path


def run(track, mag_data=None, convergence_events=None, **kwargs):
    """Called by sniffer.py as a lens."""
    print(f"    [mapview] Generating map visualization...")
    event_name = track.name.lower().replace(" ", "_")
    out = generate_map(
        event_name,
        convergence_events=convergence_events,
        **{k: v for k, v in kwargs.items() if k in ("reports_dir", "events_dir")}
    )
    return {"anomalies": [], "lens": "mapview", "output": out}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate UAP track map")
    parser.add_argument("--event",       required=True, help="Event name")
    parser.add_argument("--reports-dir", default="outputs")
    parser.add_argument("--events-dir",  default="events")
    args = parser.parse_args()

    out = generate_map(args.event, args.reports_dir, args.events_dir)
    print(f"Done: {out}")
