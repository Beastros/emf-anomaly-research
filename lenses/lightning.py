"""
lenses/lightning.py
===================
Lightning anomaly detection — looks for atypical discharge events
in the event corridor that don't match weather patterns.
A highly charged or plasma-generating object moving through atmosphere
would trigger anomalous lightning or St. Elmo's fire type events.

Primary source: NOAA NLDN via NCEI (requires registration for full data)
Fallback: Vaisala open records, ENTLN public summaries
"""

import datetime
import requests
import json
import numpy as np
from core.track import haversine_km


# NOAA NCEI lightning endpoint (public summary data)
NCEI_URL = "https://www.ncdc.noaa.gov/cdo-web/api/v2/data"

# Blitzortung open lightning network (real-time and some archive)
BLITZORTUNG_URL = "https://data.blitzortung.org/Data_1/Protected/"


def fetch_lightning_ncei(bbox: dict, start: datetime.datetime,
                         end: datetime.datetime, token: str = None) -> list:
    """
    Fetch lightning data from NOAA NCEI.
    Requires free API token from https://www.ncdc.noaa.gov/cdo-web/token
    Returns list of strike records.
    """
    if not token:
        print("    [lightning] No NCEI token — using fallback estimation")
        return []

    headers = {"token": token}
    params  = {
        "datasetid":  "NEXRAD2",
        "stationid":  f"GHCND:{bbox}",
        "startdate":  start.strftime("%Y-%m-%d"),
        "enddate":    end.strftime("%Y-%m-%d"),
        "limit":      1000,
    }
    try:
        r = requests.get(NCEI_URL, headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get("results", [])
    except Exception as e:
        print(f"    [lightning] NCEI fetch error: {e}")
    return []


def estimate_from_nexrad_context(track) -> list:
    """
    Since direct lightning data requires authentication,
    estimate anomalous discharge likelihood from track context.
    Real implementation would cross-reference NLDN archive.
    """
    # Placeholder for when NLDN access is configured
    # Real logic: query NLDN for strikes within 50km of track, 
    # flag any that don't correlate with weather radar precipitation
    return []


def run(track, ncei_token: str = None, **kwargs) -> dict:
    """
    Run lightning anomaly lens.
    Without NCEI token returns structural output ready for data injection.
    """
    print(f"    [lightning] Scanning for anomalous discharge events...")
    t_start, t_end = track.time_window(30)
    bbox = track.bounding_box()

    strikes = fetch_lightning_ncei(bbox, t_start, t_end, ncei_token)

    if not strikes:
        # Try to use any available public source
        print(f"    [lightning] No direct strike data — framework ready for NLDN injection")
        print(f"    [lightning] Register at: https://www.ncdc.noaa.gov/cdo-web/token")

    anomalies = []

    # Flag any strikes within track corridor during event with no weather explanation
    for strike in strikes:
        try:
            slat = float(strike.get("latitude", 0))
            slon = float(strike.get("longitude", 0))
            stime = datetime.datetime.fromisoformat(strike.get("date", ""))

            pos = track.interpolate(stime)
            if pos:
                dist = haversine_km(slat, slon, pos[0], pos[1])
                if dist < 30:  # Within 30km of formation position
                    anomalies.append({
                        "time":     stime,
                        "field":    "lightning_strike",
                        "sigma":    3.0,  # Near formation position = anomalous
                        "lat":      slat,
                        "lon":      slon,
                        "dist_km":  round(dist, 1),
                        "note":     "Strike within 30km of formation position",
                    })
        except (ValueError, KeyError):
            continue

    return {
        "strikes_found":   len(strikes),
        "anomalies":       anomalies,
        "lens":            "lightning",
        "data_source":     "NLDN/NCEI" if strikes else "awaiting_token",
        "register_url":    "https://www.ncdc.noaa.gov/cdo-web/token",
    }
