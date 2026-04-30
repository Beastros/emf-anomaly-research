"""
lenses/ionosphere.py
====================
Total Electron Content (TEC) and ionospheric anomaly detection.
A plasma-generating or high-energy object in the atmosphere leaves
a TEC enhancement trail detectable in GPS network data.

Sources:
- JPL IONEX maps: https://cddis.nasa.gov/archive/gnss/products/ionex/
- NOAA Space Weather ionospheric data
- IGS (International GNSS Service) TEC maps
"""

import datetime
import requests
import numpy as np
import os
from core.track import haversine_km


# NASA CDDIS IONEX archive (requires Earthdata login for some products)
CDDIS_URL = "https://cddis.nasa.gov/archive/gnss/products/ionex/"

# NOAA Space Weather ionospheric endpoint
NOAA_IONO_URL = "https://services.swpc.noaa.gov/text/wwv.txt"

# IGS analysis centers (some have open access)
IGS_SOURCES = [
    "https://cddis.nasa.gov/archive/gnss/products/ionex/{year}/{doy}/jplg{doy}0.{yy}i.Z",
    "https://cddis.nasa.gov/archive/gnss/products/ionex/{year}/{doy}/codg{doy}0.{yy}i.Z",
]


def day_of_year(dt: datetime.datetime) -> int:
    return dt.timetuple().tm_yday


def ionex_url(dt: datetime.datetime, center: str = "jpl") -> str:
    doy = day_of_year(dt)
    yy  = str(dt.year)[2:]
    return (f"https://cddis.nasa.gov/archive/gnss/products/ionex/"
            f"{dt.year}/{doy:03d}/{center}g{doy:03d}0.{yy}i.Z")


def fetch_noaa_wwv(start: datetime.datetime, end: datetime.datetime) -> list:
    """
    Fetch NOAA WWV ionospheric propagation data.
    WWV broadcasts ionospheric conditions every 18 minutes.
    Anomalous propagation = ionospheric disturbance.
    """
    try:
        r = requests.get(NOAA_IONO_URL, timeout=15)
        if r.status_code == 200:
            lines = r.text.split("\n")
            records = []
            for line in lines:
                if line.startswith("#") or not line.strip():
                    continue
                records.append({"raw": line.strip()})
            return records
    except Exception as e:
        print(f"    [ionosphere] WWV fetch error: {e}")
    return []


def estimate_tec_anomaly(track) -> list:
    """
    Estimate where TEC anomalies should appear given the track.
    A plasma trail moves with the object and persists for minutes.
    Returns list of expected anomaly windows and locations.
    """
    anomalies = []
    for w in track.witnesses:
        if w.get("conf", 1) >= 0.7:
            # Plasma trail lingers for ~5-15 minutes
            for offset_min in [0, 5, 10]:
                t = w["time"] + datetime.timedelta(minutes=offset_min)
                anomalies.append({
                    "time":          t,
                    "field":         "TEC_estimated",
                    "sigma":         2.0 * (1 - offset_min/15),
                    "lat":           w["lat"],
                    "lon":           w["lon"],
                    "source":        w.get("desc", "witness"),
                    "note":          f"Estimated TEC enhancement +{offset_min}min after sighting",
                    "confidence":    w.get("conf", 0.5),
                })
    return anomalies


def check_ionex_availability(dt: datetime.datetime) -> dict:
    """Check if IONEX TEC maps are available for a given date."""
    for center in ["jpl", "cod", "esa", "igs"]:
        url = ionex_url(dt, center)
        try:
            r = requests.head(url, timeout=10)
            if r.status_code in (200, 302):
                return {"available": True, "url": url, "center": center}
        except Exception:
            continue
    return {
        "available": False,
        "note": "IONEX maps require NASA Earthdata login for 1990s data",
        "register": "https://urs.earthdata.nasa.gov/users/new",
    }


def run(track, earthdata_token: str = None, **kwargs) -> dict:
    """Run ionospheric TEC lens."""
    print(f"    [ionosphere] Checking TEC data availability...")
    t_start, t_end = track.time_window(30)

    # Check IONEX availability
    ionex_status = check_ionex_availability(t_start)
    print(f"    [ionosphere] IONEX available: {ionex_status['available']}")

    # Estimated anomalies based on track geometry
    estimated = estimate_tec_anomaly(track)
    print(f"    [ionosphere] {len(estimated)} estimated TEC enhancement windows")

    # Try to fetch any available current ionospheric data
    wwv_data = fetch_noaa_wwv(t_start, t_end)

    anomalies = estimated  # Use estimates until real data is pulled

    return {
        "ionex_status":     ionex_status,
        "estimated_windows": len(estimated),
        "anomalies":        anomalies,
        "lens":             "ionosphere",
        "earthdata_url":    "https://urs.earthdata.nasa.gov/users/new",
        "note":             "Full TEC maps require NASA Earthdata credentials for historical data",
    }
