"""
Phoenix Lights — full stack + 14-night magnetometer baseline + enriched exports.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.anomaly import ConvergenceEngine
from core.track import EventTrack
from core.treasure_hunt_summary import write_summary_file
from lenses import magnetometer as mag_lens
from investigate_ticks import export_bundle
from sniffer import AVAILABLE_LENSES, OUTPUTS_DIR, load_event, run_lens


DEFAULT_EVENT_KEY = "phoenix_lights_1997"

STACK = [
    "magnetometer",
    "spaceweather",
    "omni",
    "asos",
    "nexrad",
    "lightning",
    "infrasound",
    "powergrid",
    "adsb",
]


def _witness_dt(val) -> datetime.datetime:
    if isinstance(val, datetime.datetime):
        dt = val
    else:
        s = str(val).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def shift_event_days(event: dict, delta_days: int) -> dict:
    e = copy.deepcopy(event)
    for w in e["witnesses"]:
        dt = _witness_dt(w["time"])
        dt2 = dt + datetime.timedelta(days=delta_days)
        w["time"] = dt2.strftime("%Y-%m-%dT%H:%M:%SZ")
    e["date"] = _witness_dt(e["witnesses"][0]["time"]).strftime("%Y-%m-%d")
    return e


def mag_summary(track: EventTrack) -> dict:
    r = mag_lens.run(track)
    an = r.get("anomalies", [])
    peaks = {}
    for sid, fields in r.get("station_data", {}).items():
        for comp, ts in fields.items():
            if hasattr(ts, "score"):
                peaks[f"{sid}_{comp}"] = round(float(ts.score.max()), 3)
    return {
        "anomaly_count_2sigma": len(an),
        "per_station_peak_sigma": peaks,
    }


def percentile_rank(value: float, population: list) -> float | None:
    if not population:
        return None
    below = sum(1 for x in population if x < value)
    return round(100.0 * below / len(population), 1)


def _slug(track: EventTrack) -> str:
    return track.name.lower().replace(" ", "_")


def main():
    parser = argparse.ArgumentParser(
        description="Full lens stack + 14-night mag baseline + exports + treasure summary",
    )
    parser.add_argument(
        "--event",
        default=DEFAULT_EVENT_KEY,
        help=f"Event JSON stem under events/ (default: {DEFAULT_EVENT_KEY})",
    )
    args = parser.parse_args()
    event_key = args.event

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    raw = load_event(event_key)
    track = EventTrack(raw)

    print(f"=== Model stack: {track.name} ({event_key}) ===\n")

    # --- 14-night magnetometer mesh (±7 days excluding event night)
    offsets = list(range(-7, 0)) + list(range(1, 8))
    baseline_nights: list = []
    baseline_counts: list = []
    baseline_tuc_y: list = []

    print("[baseline mesh] INTERMAGNET nights ±7d (excluding event day)")
    for d in offsets:
        tr = EventTrack(shift_event_days(raw, d))
        print(f"  offset {d:+} {tr.date} …", end=" ", flush=True)
        s = mag_summary(tr)
        baseline_nights.append({"day_offset": d, "date": tr.date, **s})
        baseline_counts.append(s["anomaly_count_2sigma"])
        baseline_tuc_y.append(s["per_station_peak_sigma"].get("TUC_Y", 0.0))
        print(f"count={s['anomaly_count_2sigma']} TUC_Y_peak={s['per_station_peak_sigma'].get('TUC_Y')}")

    print("\n[event night] magnetometer")
    event_mag = mag_summary(track)
    print(f"  count={event_mag['anomaly_count_2sigma']} peaks={event_mag['per_station_peak_sigma']}")

    baseline_minus1 = next(x for x in baseline_nights if x["day_offset"] == -1)
    ratio_1 = None
    if baseline_minus1["anomaly_count_2sigma"]:
        ratio_1 = round(
            event_mag["anomaly_count_2sigma"] / baseline_minus1["anomaly_count_2sigma"], 3
        )

    rank_count = percentile_rank(float(event_mag["anomaly_count_2sigma"]), baseline_counts)
    ev_y = float(event_mag["per_station_peak_sigma"].get("TUC_Y", 0))
    rank_y = percentile_rank(ev_y, baseline_tuc_y)

    convergence = ConvergenceEngine(track, window_minutes=10)
    lens_results = {}

    print("\n[lens stack]")
    for name in STACK:
        if name not in AVAILABLE_LENSES:
            continue
        print(f"  → {name}")
        result = run_lens(name, track, **{})
        lens_results[name] = result
        an = result.get("anomalies", [])
        if an:
            convergence.add_lens(name, an)

    ion_extra = {}
    if "ionosphere" in AVAILABLE_LENSES:
        print("  → ionosphere (metadata)")
        ion_r = run_lens("ionosphere", track, **{})
        ion_extra = {
            "ionosphere_anomaly_rows": len(ion_r.get("anomalies", [])),
            "ionosphere_note": ion_r.get("note"),
            "ionex_status": ion_r.get("ionex_status"),
        }

    paths = export_bundle(
        track,
        convergence,
        lens_results,
        min_lenses=2,
        window_minutes=10,
        output_dir=OUTPUTS_DIR,
    )
    b = paths["bundle"]

    merged_all = b["sensor_bundles_merged"]
    merged_inst = b["sensor_bundles_instrument_merged"]

    model_payload = {
        "meta": {
            "event": track.name,
            "event_key": event_key,
            "intent": "Treasure-hunt stack + 14-night mag baseline + merged coincidence",
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mag_count_note": (
                "magnetometer anomaly_count sums >2σ hits across the fetched mesh "
                "(TUC + BOU + FRD + SIT), not a single observatory."
            ),
        },
        "magnetometer_baseline_minus1day": baseline_minus1,
        "magnetometer_event_night": event_mag,
        "event_to_baseline_minus1_ratio": ratio_1,
        "magnetometer_14night_offsets": baseline_nights,
        "percentile_event_count_vs_14nights": rank_count,
        "percentile_event_TUC_Y_peak_vs_14nights": rank_y,
        "lens_stack": STACK,
        "counts_by_lens": b["counts_by_lens"],
        "bundles_merged_all_lenses": len(merged_all),
        "bundles_merged_instrument_only": len(merged_inst),
        "top_bundles_merged_all": merged_all[:10],
        "top_bundles_merged_instrument": merged_inst[:10],
        "witness_lens_families": b["witness_nearby_lens_families"],
        "witness_instrument_only": b["witness_nearby_instrument_only"],
        "ionosphere_meta": ion_extra,
        "artifact_paths": {
            "sensor_ticks_full_json": paths["json"],
            "sensor_ticks_instrument_json": paths["instrument_json"],
            "sensor_ticks_csv": paths["csv"],
            "sensor_ticks_md": paths["md"],
        },
    }

    treasure_md = write_summary_file(
        track,
        lens_results,
        OUTPUTS_DIR,
        bundle=b,
        model_payload=model_payload,
        artifact_paths=model_payload["artifact_paths"],
        window_minutes=10.0,
        print_to_stdout=True,
    )
    model_payload["artifact_paths"]["treasure_hunt_summary_md"] = treasure_md

    out_json = os.path.join(OUTPUTS_DIR, f"{_slug(track)}_model_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(model_payload, f, indent=2, default=str)

    print("\n=== Summary ===")
    print(f"  Event mag count (>2σ):     {event_mag['anomaly_count_2sigma']}")
    print(f"  vs −1 day ratio:           {ratio_1}")
    print(
        f"  Percentile count vs ±7d:   {rank_count}%  "
        f"(% of mesh nights with lower total >2σ count than event night)"
    )
    print(f"  Percentile TUC_Y peak:     {rank_y}%")
    print(f"  Bundles merged (all):      {len(merged_all)}")
    print(f"  Bundles merged (instrument): {len(merged_inst)}")
    print(f"\n  Wrote {out_json}")

    if sys.platform == "win32":
        try:
            os.startfile(os.path.normpath(treasure_md))
        except OSError:
            pass


if __name__ == "__main__":
    main()
