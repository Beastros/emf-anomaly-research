"""
lenses/infrasound.py
====================
IMS Infrasound Network + IRIS seismic archive.
A fast-moving dense object generates infrasound (<20Hz pressure waves).
Sensitive enough to detect meteors, large aircraft, volcanic eruptions.
Cross-referencing infrasound with event track gives speed/altitude estimates.

IMS data: https://www.ctbto.org/specials/vdec/ (requires registration)
IRIS data: https://service.iris.edu/irisws/timeseries/1/
"""

import datetime
import requests
import numpy as np
from core.track import haversine_km


# IRIS web services
IRIS_TIMESERIES = "https://service.iris.edu/irisws/timeseries/1/query"
IRIS_STATION    = "https://service.iris.edu/fdsnws/station/1/query"

# Known infrasound-capable seismic stations
INFRASOUND_STATIONS = {
    "BK.CMB":  {"lat": 38.034, "lon": -120.386, "name": "Columbia CA",       "network": "BK"},
    "IU.ANMO": {"lat": 34.946, "lon": -106.457, "name": "Albuquerque NM",    "network": "IU"},
    "IU.TUC":  {"lat": 32.310, "lon": -110.785, "name": "Tucson AZ",         "network": "IU"},
    "IM.I57US":{"lat": 33.606, "lon": -116.453, "name": "Pinon Flat CA",     "network": "IM"},
    "IU.CCM":  {"lat": 38.056, "lon": -91.245,  "name": "Cathedral Cave MO", "network": "IU"},
    "US.TZTN": {"lat": 36.623, "lon": -83.447,  "name": "Tazewell TN",       "network": "US"},
}

# Speed of sound at altitude (approximate)
SOUND_SPEED_MS = 340  # m/s at sea level


def fetch_iris_waveform(network: str, station: str, channel: str,
                        start: datetime.datetime, end: datetime.datetime) -> dict:
    """Fetch waveform data from IRIS web services."""
    params = {
        "net":     network,
        "sta":     station,
        "cha":     channel,
        "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime":   end.strftime("%Y-%m-%dT%H:%M:%S"),
        "output":  "ascii",
        "nodata":  "404",
    }
    try:
        r = requests.get(IRIS_TIMESERIES, params=params, timeout=20)
        if r.status_code == 200:
            return {"data": r.text, "status": "ok"}
        else:
            return {"status": "no_data", "code": r.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def estimate_travel_time(source_lat, source_lon,
                         station_lat, station_lon, alt_m=1000) -> float:
    """Estimate infrasound travel time from source to station in seconds."""
    dist_km = haversine_km(source_lat, source_lon, station_lat, station_lon)
    # Account for altitude path
    path_m  = np.sqrt((dist_km * 1000)**2 + alt_m**2)
    return path_m / SOUND_SPEED_MS


def run(track, pad_minutes: int = 60, **kwargs) -> dict:
    """
    Run infrasound/seismic lens.
    Estimates expected arrival times at stations and flags anomalies.
    """
    print(f"    [infrasound] Scanning IRIS network for infrasound signatures...")
    t_start, t_end = track.time_window(pad_minutes)
    bbox = track.bounding_box(pad_deg=5.0)

    # Find nearby stations
    nearby = {
        sid: info for sid, info in INFRASOUND_STATIONS.items()
        if bbox["min_lat"] - 5 <= info["lat"] <= bbox["max_lat"] + 5
        and bbox["min_lon"] - 5 <= info["lon"] <= bbox["max_lon"] + 5
    }

    print(f"    [infrasound] Stations in range: {list(nearby.keys())}")

    anomalies = []
    station_results = {}

    for sid, info in nearby.items():
        net, sta = sid.split(".")
        # Try BHZ (broadband seismic) and LDO (infrasound) channels
        for channel in ["BHZ", "LDO", "HDF"]:
            result = fetch_iris_waveform(net, sta, channel, t_start, t_end)
            if result["status"] == "ok":
                print(f"    [infrasound] {sid} {channel}: data retrieved")
                station_results[f"{sid}.{channel}"] = result

                # Estimate expected infrasound from each witness position
                for w in track.witnesses:
                    travel_s = estimate_travel_time(
                        w["lat"], w["lon"],
                        info["lat"], info["lon"]
                    )
                    expected_arrival = w["time"] + datetime.timedelta(seconds=travel_s)
                    if t_start <= expected_arrival <= t_end:
                        anomalies.append({
                            "time":           expected_arrival,
                            "field":          f"infrasound_{sid}",
                            "sigma":          2.0,  # Placeholder
                            "source_witness": w.get("desc", ""),
                            "travel_time_s":  round(travel_s, 1),
                            "dist_km":        round(haversine_km(w["lat"], w["lon"], info["lat"], info["lon"]), 1),
                            "station":        sid,
                            "note":           f"Expected infrasound arrival from {w.get('desc', 'witness')}",
                        })
            else:
                print(f"    [infrasound] {sid} {channel}: {result.get('status')} {result.get('code','')}")

    if not station_results:
        print(f"    [infrasound] No waveform data retrieved — IMS archive may require CTBTO credentials")
        print(f"    [infrasound] Apply at: https://www.ctbto.org/specials/vdec/")

    return {
        "stations_checked": list(nearby.keys()),
        "data_retrieved":   list(station_results.keys()),
        "anomalies":        anomalies,
        "lens":             "infrasound",
        "ctbto_url":        "https://www.ctbto.org/specials/vdec/",
    }
