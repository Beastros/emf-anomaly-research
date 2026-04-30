"""
lenses/spaceweather.py — Fixed Kp fetch for historical data
"""

import datetime
import requests
import numpy as np


def fetch_kp_1997(year, month):
    """
    Fetch Kp from GFZ Potsdam — authoritative source, works for 1932-present.
    Uses the Kp_ap_Ap_SN_F107_since_1932.txt consolidated file.
    """
    print(f"    [spaceweather] Fetching Kp from GFZ Potsdam for {year}-{month:02d}...")

    # Primary: GFZ consolidated file
    url = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            records = []
            for line in r.text.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 12:
                    continue
                try:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    if y != year or m != month:
                        continue
                    # Kp values are in columns 7-14 (8 per day, 3-hour intervals)
                    for hour_idx in range(8):
                        col = 7 + hour_idx
                        if col < len(parts):
                            kp = float(parts[col])
                            t  = datetime.datetime(y, m, d, hour_idx*3, 0, 0,
                                                   tzinfo=datetime.timezone.utc)
                            records.append({"time": t, "kp": kp})
                except (ValueError, IndexError):
                    continue
            if records:
                print(f"    [spaceweather] Got {len(records)} Kp records from GFZ")
                return records
    except Exception as e:
        print(f"    [spaceweather] GFZ primary failed: {e}")

    # Fallback: NOAA FTP mirror
    url2 = f"https://www.ngdc.noaa.gov/stp/GEOMAG/kp_ap/{year}kp.txt"
    try:
        r = requests.get(url2, timeout=20)
        if r.status_code == 200:
            records = []
            for line in r.text.split("\n"):
                parts = line.split()
                if len(parts) < 10:
                    continue
                try:
                    y2 = int(parts[0])
                    m2 = int(parts[1])
                    d2 = int(parts[2])
                    if y2 != year or m2 != month:
                        continue
                    for hour_idx in range(8):
                        if 3 + hour_idx < len(parts):
                            kp = float(parts[3 + hour_idx]) / 10
                            t  = datetime.datetime(y2, m2, d2, hour_idx*3, 0, 0,
                                                   tzinfo=datetime.timezone.utc)
                            records.append({"time": t, "kp": kp})
                except (ValueError, IndexError):
                    continue
            if records:
                print(f"    [spaceweather] Got {len(records)} Kp records from NOAA")
                return records
    except Exception as e:
        print(f"    [spaceweather] NOAA fallback failed: {e}")

    return []


def run(track, **kwargs):
    t_start, t_end = track.time_window(60)
    year  = t_start.year
    month = t_start.month

    records = fetch_kp_1997(year, month)

    # Filter to event window ±6 hours
    pad = datetime.timedelta(hours=6)
    event_kp = [r for r in records if t_start - pad <= r["time"] <= t_end + pad]

    if not event_kp:
        print(f"    [spaceweather] No Kp data for event window")
        return {
            "kp_analysis": {
                "status":  "unavailable",
                "note":    "Check manually: https://kp.gfz-potsdam.de",
                "max_kp":  None,
                "storm_level": "unknown",
                "solar_explanation_possible": "unknown",
                "interpretation": "Kp unavailable — cannot rule out solar origin for magnetometer anomalies",
            },
            "anomalies": [],
            "lens": "spaceweather",
        }

    kp_vals = [r["kp"] for r in event_kp]
    max_kp  = max(kp_vals)
    mean_kp = round(float(np.mean(kp_vals)), 2)

    print(f"    [spaceweather] Event window Kp: max={max_kp}  mean={mean_kp}")

    if max_kp >= 5:
        storm_level    = f"G{min(5,int(max_kp-4))} geomagnetic storm"
        solar_possible = True
    elif max_kp >= 4:
        storm_level    = "Active (unsettled)"
        solar_possible = True
    elif max_kp >= 3:
        storm_level    = "Unsettled"
        solar_possible = False
    else:
        storm_level    = "Quiet"
        solar_possible = False

    interpretation = (
        f"Kp max={max_kp} ({storm_level}). "
        + ("Solar activity COULD explain magnetometer anomalies — verify."
           if solar_possible else
           "LOW Kp — solar activity does NOT explain magnetometer anomalies. Anomalies are localized.")
    )

    print(f"    [spaceweather] {interpretation}")

    anomalies = []
    if not solar_possible:
        anomalies.append({
            "time":  track.start_time,
            "field": "Kp_confirmation",
            "sigma": 3.0,
            "value": max_kp,
            "note":  f"Low Kp ({max_kp}) — magnetometer anomalies confirmed NOT solar in origin",
        })

    return {
        "kp_analysis": {
            "status":  "ok",
            "kp_values": [{"time": r["time"].isoformat(), "kp": r["kp"]} for r in event_kp],
            "max_kp":  max_kp,
            "mean_kp": mean_kp,
            "storm_level": storm_level,
            "solar_explanation_possible": solar_possible,
            "interpretation": interpretation,
        },
        "anomalies": anomalies,
        "lens": "spaceweather",
    }
