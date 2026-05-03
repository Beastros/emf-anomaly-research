"""
lenses/magnetometer.py
Fetches from INTERMAGNET HAPI (has 1990s data).
Falls back to USGS for post-2000 events where USGS has coverage.
"""
import datetime
import numpy as np
import requests
from core.anomaly import AnomalyTimeseries

HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
USGS_URL  = "https://geomag.usgs.gov/ws/data/"

STATIONS = {
    "TUC": {"lat": 32.174, "lon": -110.733, "name": "Tucson AZ"},
    "BOU": {"lat": 40.137, "lon": -105.237, "name": "Boulder CO"},
    "FRD": {"lat": 38.205, "lon": -77.373,  "name": "Fredericksburg VA"},
    "SIT": {"lat": 57.058, "lon": -135.325, "name": "Sitka AK"},
    "CMO": {"lat": 64.874, "lon": -147.860, "name": "College AK"},
    "HON": {"lat": 21.316, "lon": -158.000, "name": "Honolulu HI"},
}

# Always attempt these INTERMAGNET observatories for regional context (treasure-hunt mesh).
NETWORK_ANCHORS = ("TUC", "BOU", "FRD", "SIT")


def fetch_hapi(station, start, end):
    """
    Fetch from INTERMAGNET HAPI -- has 1990s data.
    Row format: [timestamp, [x, y, z], f]
    Returns dict of component arrays or None.
    """
    ds = start.strftime("%Y-%m-%d")
    for data_type in ["definitive", "quasi-definitive", "variation"]:
        params = {
            "id":       f"{station}/{data_type}/PT1M/xyzf",
            "time.min": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time.max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "format":   "json",
        }
        try:
            r = requests.get(HAPI_BASE, params=params, timeout=30)
            if r.status_code != 200:
                continue
            rows = r.json().get("data", [])
            if len(rows) < 10:
                continue
            times = []
            X, Y, Z = [], [], []
            for row in rows:
                try:
                    t   = datetime.datetime.fromisoformat(
                        str(row[0]).replace("Z", "+00:00"))
                    xyz = row[1]
                    x   = float(xyz[0]); y = float(xyz[1]); z = float(xyz[2])
                    times.append(t)
                    X.append(np.nan if abs(x) > 90000 else x)
                    Y.append(np.nan if abs(y) > 90000 else y)
                    Z.append(np.nan if abs(z) > 90000 else z)
                except:
                    continue
            if len(times) < 10:
                continue
            print(f"      HAPI {data_type}: {len(times)} rows")
            return {
                "times": times,
                "X": np.array(X),
                "Y": np.array(Y),   # Y = east = D equivalent
                "Z": np.array(Z),
            }
        except Exception as e:
            continue
    return None


def hapi_to_timeseries(station, hapi_data):
    """Convert HAPI dict to AnomalyTimeseries objects keyed by component."""
    result = {}
    times  = hapi_data["times"]
    for comp in ["X", "Y", "Z"]:
        vals = hapi_data[comp]
        if np.sum(~np.isnan(vals)) < 10:
            continue
        result[comp] = AnomalyTimeseries(
            name=f"HAPI-{comp}", field=comp,
            times=times, values=vals, units="nT"
        )
    return result


def run(track, **kwargs):
    t_start, t_end = track.time_window(60)
    bbox = track.bounding_box(pad_deg=3.0)

    nearby = {
        sid: info
        for sid, info in STATIONS.items()
        if bbox["min_lat"] <= info["lat"] <= bbox["max_lat"]
        and bbox["min_lon"] <= info["lon"] <= bbox["max_lon"]
    }
    if not nearby:
        nearby = {"TUC": STATIONS["TUC"]}

    stations_to_fetch = sorted(set(nearby.keys()) | set(NETWORK_ANCHORS))

    print(f"    [magnetometer] Bbox hits: {list(nearby.keys())}")
    print(f"    [magnetometer] Fetching mesh: {stations_to_fetch}")
    print(f"    [magnetometer] Source: INTERMAGNET HAPI (has 1990s data)")

    all_results   = {}
    all_anomalies = []

    for station in stations_to_fetch:
        print(f"    Fetching {station}...")
        hapi = fetch_hapi(station, t_start, t_end)
        if hapi is None:
            print(f"      {station}: no data from INTERMAGNET HAPI")
            continue

        fields = hapi_to_timeseries(station, hapi)
        all_results[station] = fields

        for comp, ts in fields.items():
            for anom in ts.anomalies(2.0):
                anom["station"] = station
                anom["field"]   = f"{station}_{comp}"
                all_anomalies.append(anom)

        total = sum(len(f.anomalies()) for f in fields.values())
        print(f"      {station}: {total} anomalies >2sigma")
        for comp, ts in fields.items():
            peak = float(ts.score.max())
            n    = len(ts.anomalies(2.0))
            if peak > 2.0:
                peak_t = ts.times[int(np.argmax(ts.score))]
                print(f"        {comp}: peak={peak:.3f}s  n={n}  at {peak_t.strftime('%H:%M UTC')}")

    return {
        "station_data": all_results,
        "anomalies":    all_anomalies,
        "lens":         "magnetometer",
    }
