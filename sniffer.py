"""
sniffer.py
==========
UAP Multi-Lens Analysis Framework — Main entry point.

Usage:
    python sniffer.py --event phoenix_lights_1997 --lenses all
    python sniffer.py --event phoenix_lights_1997 --lenses magnetometer,spaceweather,nexrad
    python sniffer.py --list-events
    python sniffer.py --list-lenses
"""

import argparse
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.track import EventTrack
from core.anomaly import ConvergenceEngine
from core.report import generate_report

EVENTS_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

AVAILABLE_LENSES = {
    "nexrad":       "lenses.nexrad",
    "magnetometer": "lenses.magnetometer",
    "spaceweather": "lenses.spaceweather",
    "lightning":    "lenses.lightning",
    "infrasound":   "lenses.infrasound",
    "ionosphere":   "lenses.ionosphere",
    "powergrid":    "lenses.powergrid",
    "adsb":         "lenses.adsb",
}


def load_event(name):
    path = os.path.join(EVENTS_DIR, f"{name}.json")
    if not os.path.exists(path):
        candidates = [f[:-5] for f in os.listdir(EVENTS_DIR) if f.endswith(".json")]
        raise FileNotFoundError(f"Event '{name}' not found. Available: {candidates}")
    with open(path) as f:
        return json.load(f)


def import_lens(lens_name):
    import importlib
    return importlib.import_module(AVAILABLE_LENSES[lens_name])


def run_lens(lens_name, track, **kwargs):
    print(f"\n[LENS] {lens_name.upper()}")
    try:
        lens   = import_lens(lens_name)
        result = lens.run(track, **kwargs)
        n      = len(result.get("anomalies", []))
        print(f"  → {n} anomalies detected")
        return result
    except Exception as e:
        print(f"  → ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"anomalies": [], "lens": lens_name, "error": str(e)}


def print_banner():
    print("""
╔══════════════════════════════════════════════════════╗
║       UAP MULTI-LENS ANALYSIS FRAMEWORK              ║
║       Multi-Dataset Anomaly Convergence Engine       ║
╚══════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(description="UAP Multi-Lens Analysis Framework")
    parser.add_argument("--event",       help="Event name (without .json)")
    parser.add_argument("--lenses",      default="all", help="Comma-separated lenses or 'all'")
    parser.add_argument("--list-events", action="store_true")
    parser.add_argument("--list-lenses", action="store_true")
    parser.add_argument("--threshold",   type=float, default=2.0)
    parser.add_argument("--convergence", type=int,   default=2)
    parser.add_argument("--ncei-token",       default=None)
    parser.add_argument("--earthdata-token",  default=None)
    parser.add_argument("--opensky-user",     default=None)
    parser.add_argument("--opensky-pass",     default=None)
    parser.add_argument("--eia-key",          default=None)
    args = parser.parse_args()

    print_banner()

    if args.list_events:
        for f in sorted(os.listdir(EVENTS_DIR)):
            if f.endswith(".json"):
                d = load_event(f[:-5])
                print(f"  {f[:-5]:40s} {d.get('date','')} — {d.get('name','')}")
        return

    if args.list_lenses:
        for name, mod in AVAILABLE_LENSES.items():
            print(f"  {name:20s} {mod}")
        return

    if not args.event:
        parser.print_help()
        return

    # ── Load event ──────────────────────────────────────────────
    print(f"Loading event: {args.event}")
    event_data = load_event(args.event)
    track      = EventTrack(event_data)

    print(f"\nEvent:     {track.name}")
    print(f"Date:      {track.date}")
    print(f"Witnesses: {len(track.witnesses)}")
    print(f"Duration:  {track.duration_minutes():.1f} minutes")

    # ── Velocity ─────────────────────────────────────────────────
    print("\n── VELOCITY ────────────────────────────────────────────")
    ref_max = event_data.get("reference_max_kmh")
    vel     = track.velocity_summary(ref_max)
    print(f"  Avg speed: {vel['avg_speed_kmh']} km/h")
    print(f"  Max speed: {vel['max_speed_kmh']} km/h")
    if ref_max:
        exceed = vel.get("segments_exceeding_max", [])
        print(f"  Reference max ({event_data.get('reference_aircraft','?')}: {ref_max} km/h)")
        print(f"  Segments exceeding max: {len(exceed)}/{len(vel['segments'])}")
        for s in exceed:
            print(f"    {s['from'][:30]:30s} → {s['speed_kmh']} km/h  hdg={s['heading']}°")
    if vel["anomalous_headings"]:
        print(f"  Heading reversals: {len(vel['anomalous_headings'])}")
        for h in vel["anomalous_headings"]:
            print(f"    {h['from'][:25]:25s} → {h['heading']}°  {h['speed_kmh']} km/h")

    # ── Select lenses ────────────────────────────────────────────
    if args.lenses == "all":
        selected = list(AVAILABLE_LENSES.keys())
    else:
        selected = [l.strip() for l in args.lenses.split(",")]
        bad = [l for l in selected if l not in AVAILABLE_LENSES]
        if bad:
            print(f"Unknown lenses: {bad}  Available: {list(AVAILABLE_LENSES.keys())}")
            return

    lens_kwargs = {
        "ncei_token":      args.ncei_token,
        "earthdata_token": args.earthdata_token,
        "opensky_user":    args.opensky_user,
        "opensky_pass":    args.opensky_pass,
        "eia_key":         args.eia_key,
    }

    # ── Run lenses + feed convergence engine ─────────────────────
    print("\n── LENS ANALYSIS ───────────────────────────────────────")
    convergence  = ConvergenceEngine(track, window_minutes=10)
    lens_results = {}

    for lens_name in selected:
        result = run_lens(lens_name, track, **lens_kwargs)
        lens_results[lens_name] = result

        # *** THIS IS THE FIX — feed anomalies into convergence engine ***
        anomalies = result.get("anomalies", [])
        if anomalies:
            convergence.add_lens(lens_name, anomalies)

        # Print lens-specific insights
        if lens_name == "spaceweather":
            kp = result.get("kp_analysis", {})
            if kp.get("status") == "ok":
                print(f"  Kp max={kp['max_kp']}  storm={kp['storm_level']}")
                print(f"  Solar explanation possible: {kp['solar_explanation_possible']}")
                print(f"  → {kp['interpretation']}")
            elif kp.get("status") == "unavailable":
                print(f"  Kp data unavailable: {kp.get('note','')}")

        if lens_name == "magnetometer":
            for station, fields in result.get("station_data", {}).items():
                for fid, ts in fields.items():
                    peak = float(ts.score.max()) if hasattr(ts, 'score') else 0
                    n    = len(ts.anomalies(args.threshold)) if hasattr(ts, 'anomalies') else 0
                    if n > 0 or peak > 2:
                        print(f"  {station} {fid}: {n} anomalies  peak={peak:.2f}σ")

        if lens_name == "nexrad":
            for sid, info in result.get("station_scores", {}).items():
                print(f"  {sid}: files={info['files_found']}  null={info['null_return']}  score={info['max_score']}")

        if lens_name == "powergrid":
            affected = result.get("anomalies", [])
            if affected:
                print(f"  Grid monitors within 30km of track: {len(affected)}")
                for a in affected[:3]:
                    print(f"    {a['monitor']:20s} dist={a['dist_km']}km  est_dev={a['est_dev_mhz']}mHz")

    # ── Convergence ──────────────────────────────────────────────
    print("\n── CONVERGENCE ─────────────────────────────────────────")
    conv_events = convergence.find_convergence(min_lenses=args.convergence)
    print(f"  Multi-dataset convergence events: {len(conv_events)}")
    for c in conv_events[:5]:
        pos = c.get("position")
        pos_str = f"({pos['lat']:.2f}, {pos['lon']:.2f})" if pos else ""
        print(f"  {str(c['time'])[:19]}  lenses={c['lenses']}  peak={c['max_sigma']}σ  {pos_str}")

    # ── Summary ──────────────────────────────────────────────────
    print("\n── SUMMARY ─────────────────────────────────────────────")
    total = sum(len(r.get("anomalies", [])) for r in lens_results.values())
    print(f"  Lenses run:       {len(selected)}")
    print(f"  Total anomalies:  {total}")
    print(f"  Convergence hits: {len(conv_events)}")
    print(f"  Lenses with data: {[k for k,v in lens_results.items() if v.get('anomalies')]}")

    # ── Report ───────────────────────────────────────────────────
    print("\n── REPORT ──────────────────────────────────────────────")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report = generate_report(track, convergence, REPORTS_DIR)
    print(f"\n  Flags: {report['verdict']['flags']}")
    print(f"  Conclusion: {report['verdict']['conclusion']}")
    print("\n✓ Done.")


if __name__ == "__main__":
    main()
