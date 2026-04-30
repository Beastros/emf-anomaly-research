"""
lenses/magnetometer.py — Fixed to accept **kwargs
"""

import datetime
import numpy as np
import requests
from core.anomaly import AnomalyTimeseries


USGS_URL = "https://geomag.usgs.gov/ws/data/"

STATIONS = {
    "TUC": {"lat": 32.174, "lon": -110.733, "name": "Tucson AZ"},
    "BOU": {"lat": 40.137, "lon": -105.237, "name": "Boulder CO"},
    "FRD": {"lat": 38.205, "lon": -77.373,  "name": "Fredericksburg VA"},
}


def fetch(station, start, end, sampling=60):
    params = {
        "id":              station,
        "starttime":       start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endtime":         end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elements":        "H,D,Z,F",
        "sampling_period": sampling,
        "format":          "json",
        "type":            "definitive",
    }
    print(f"    [magnetometer] Fetching {station} {start.strftime('%Y-%m-%d %H:%M')} UTC...")
    r = requests.get(USGS_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def parse(raw):
    times = [
        datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
        for t in raw.get("times", [])
    ]
    result = {}
    for entry in raw.get("values", []):
        fid  = entry["id"]
        vals = np.array([float(v) if v is not None else np.nan for v in entry["values"]])
        if not np.all(np.isnan(vals)):
            units = "nT" if fid in ("H","Z","F") else "arcmin"
            result[fid] = AnomalyTimeseries(
                name=f"USGS-{fid}", field=fid,
                times=times, values=vals, units=units
            )
    return result


def run(track, **kwargs):  # **kwargs absorbs unused args from other lenses
    t_start, t_end = track.time_window(60)
    bbox = track.bounding_box(pad_deg=3.0)

    nearby = {
        sid: info for sid, info in STATIONS.items()
        if bbox["min_lat"] <= info["lat"] <= bbox["max_lat"]
        and bbox["min_lon"] <= info["lon"] <= bbox["max_lon"]
    }
    if not nearby:
        nearby = {"TUC": STATIONS["TUC"]}

    print(f"    [magnetometer] Stations in range: {list(nearby.keys())}")

    all_results   = {}
    all_anomalies = []

    for station in nearby:
        try:
            raw    = fetch(station, t_start, t_end)
            fields = parse(raw)
            all_results[station] = fields

            for fid, ts in fields.items():
                for anom in ts.anomalies(2.0):
                    anom["station"] = station
                    anom["field"]   = f"{station}_{fid}"
                    all_anomalies.append(anom)

            total = sum(len(f.anomalies()) for f in fields.values())
            print(f"    [magnetometer] {station}: {total} anomalies >2σ")
            for fid, ts in fields.items():
                peak = float(ts.score.max())
                n    = len(ts.anomalies(2.0))
                if peak > 2.0:
                    print(f"      {fid}: peak={peak:.3f}σ  n={n}")
        except Exception as e:
            print(f"    [magnetometer] {station} error: {e}")

    return {
        "station_data": all_results,
        "anomalies":    all_anomalies,
        "lens":         "magnetometer",
    }
