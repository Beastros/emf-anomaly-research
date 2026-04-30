"""
lenses/adsb.py
==============
ADS-B gap and anomaly detection.
Looks for aircraft that disappeared from tracking, reappeared unexpectedly,
or showed anomalous behavior in the event corridor.
A UAP operating in the same airspace would cause ATC to redirect traffic
or generate unexplained track gaps.

Sources:
- ADS-B Exchange historical data (adsbexchange.com)
- OpenSky Network archive (opensky-network.org)
- FAA ASDI archive (requires FOIA for historical)
"""

import datetime
import requests
import numpy as np
from core.track import haversine_km


OPENSKY_URL = "https://opensky-network.org/api/flights/departure"
OPENSKY_STATES = "https://opensky-network.org/api/states/all"


def fetch_opensky_states(bbox: dict, t_unix: int) -> list:
    """
    Fetch aircraft states from OpenSky at a given Unix timestamp.
    OpenSky historical API requires registration.
    """
    params = {
        "lamin": bbox["min_lat"],
        "lomin": bbox["min_lon"],
        "lamax": bbox["max_lat"],
        "lomax": bbox["max_lon"],
        "time":  t_unix,
    }
    try:
        r = requests.get(OPENSKY_STATES, params=params, timeout=15)
        if r.status_code == 200:
            data   = r.json()
            states = data.get("states", []) or []
            return [
                {
                    "icao24":    s[0],
                    "callsign":  (s[1] or "").strip(),
                    "lat":       s[6],
                    "lon":       s[5],
                    "altitude":  s[7],
                    "velocity":  s[9],
                    "heading":   s[10],
                    "on_ground": s[8],
                }
                for s in states if s[6] and s[5]
            ]
        elif r.status_code == 403:
            print(f"    [adsb] OpenSky historical requires login at opensky-network.org")
    except Exception as e:
        print(f"    [adsb] OpenSky error: {e}")
    return []


def find_track_gaps(aircraft_states: list, time_interval_min: float) -> list:
    """
    Find aircraft that disappear and reappear — possible ATC avoidance.
    """
    gaps = []
    icao_history = {}

    for state in aircraft_states:
        icao = state.get("icao24")
        if icao not in icao_history:
            icao_history[icao] = []
        icao_history[icao].append(state)

    for icao, history in icao_history.items():
        if len(history) > 1:
            # Check for temporal gaps
            for i in range(len(history) - 1):
                dt_min = time_interval_min  # Interval between snapshots
                if dt_min > 10:  # Gap > 10 minutes = suspicious
                    gaps.append({
                        "icao24":    icao,
                        "callsign":  history[i].get("callsign", ""),
                        "gap_min":   dt_min,
                        "last_seen": history[i],
                        "reappeared": history[i+1],
                    })
    return gaps


def compute_density_baseline(states_before: list, states_during: list,
                              states_after: list) -> dict:
    """
    Compare aircraft density during event vs before/after.
    Unusual clearing of airspace = anomaly.
    """
    n_before = len(states_before)
    n_during = len(states_during)
    n_after  = len(states_after)

    baseline = (n_before + n_after) / 2 if (n_before + n_after) > 0 else 1
    deviation = (n_during - baseline) / baseline if baseline > 0 else 0

    return {
        "before": n_before,
        "during": n_during,
        "after":  n_after,
        "baseline": round(baseline, 1),
        "deviation_pct": round(deviation * 100, 1),
        "anomalous": deviation < -0.3,  # 30% fewer aircraft = suspicious
    }


def run(track, opensky_user: str = None, opensky_pass: str = None, **kwargs) -> dict:
    """Run ADS-B gap detection lens."""
    print(f"    [adsb] Scanning for aircraft tracking anomalies...")

    t_start, t_end = track.time_window(30)
    bbox = track.bounding_box()
    anomalies = []
    density = {}

    # Sample at 3 time points
    t_before = t_start - datetime.timedelta(minutes=30)
    t_mid    = t_start + (t_end - t_start) / 2
    t_after  = t_end + datetime.timedelta(minutes=30)

    states_before = fetch_opensky_states(bbox, int(t_before.timestamp()))
    states_during = fetch_opensky_states(bbox, int(t_mid.timestamp()))
    states_after  = fetch_opensky_states(bbox, int(t_after.timestamp()))

    if states_before or states_during or states_after:
        density = compute_density_baseline(states_before, states_during, states_after)
        print(f"    [adsb] Aircraft density — before:{density['before']} during:{density['during']} after:{density['after']}")

        if density["anomalous"]:
            anomalies.append({
                "time":   t_mid,
                "field":  "adsb_density",
                "sigma":  abs(density["deviation_pct"]) / 10,
                "note":   f"Airspace {abs(density['deviation_pct'])}% below baseline density during event",
            })
    else:
        print(f"    [adsb] No OpenSky data — historical archive requires account at opensky-network.org")
        print(f"    [adsb] Register: https://opensky-network.org/")

    return {
        "density_analysis": density,
        "anomalies":        anomalies,
        "lens":             "adsb",
        "opensky_url":      "https://opensky-network.org/",
        "faa_foia_url":     "https://www.faa.gov/foia",
        "note":             "Historical ADS-B requires OpenSky account or FAA FOIA request",
    }
