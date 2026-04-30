"""
lenses/powergrid.py
===================
Power grid frequency deviation analysis.
The US AC grid runs at exactly 60.000 Hz. A large moving electromagnetic
field inductively couples into transmission lines, causing micro-deviations
detectable in grid monitoring logs.

This is the NOVEL LENS nobody has applied to UAP analysis before.
A large EM field transiting populated corridors would leave a frequency
deviation signature in every utility substation it passed over.

Sources:
- NERC (North American Electric Reliability Corporation) frequency data
- GridEye / Frequency Disturbance Recorder network
- EIA (Energy Information Administration) grid data
- Academic FDR networks (FNET/GridEye at UT Knoxville)
"""

import datetime
import requests
import numpy as np
from core.track import haversine_km, heading_deg


# FNET/GridEye — University of Tennessee frequency monitoring
# http://fnetpublic.utk.edu/gradientmap.html
FNET_URL = "http://fnetpublic.utk.edu/data/"

# EIA grid data
EIA_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"

# NERC frequency data (requires membership for raw data)
NERC_URL = "https://www.nerc.com/pa/RAPA/regulatory/Pages/Reliability-Standards.aspx"

# Approximate locations of major grid monitoring points in the Southwest
GRID_MONITORS = {
    "APS_Phoenix":     {"lat": 33.45,  "lon": -112.07, "utility": "Arizona Public Service"},
    "SRP_Mesa":        {"lat": 33.42,  "lon": -111.83, "utility": "Salt River Project"},
    "TEP_Tucson":      {"lat": 32.22,  "lon": -110.97, "utility": "Tucson Electric Power"},
    "NVE_Henderson":   {"lat": 36.04,  "lon": -114.98, "utility": "Nevada Energy"},
    "WPS_Prescott":    {"lat": 34.54,  "lon": -112.47, "utility": "Western Area Power"},
    "SCE_Laughlin":    {"lat": 35.17,  "lon": -114.57, "utility": "Southern California Edison"},
}

# Inductive coupling model parameters
COUPLING_THRESHOLD_NM = 50  # km — significant coupling within this range
EM_FIELD_ESTIMATE_T   = 1e-4  # Tesla — rough estimate for large EM source


def estimate_induced_deviation(field_strength_T: float,
                                dist_km: float,
                                line_length_km: float = 100) -> float:
    """
    Estimate frequency deviation in milliHz from EM induction.
    Very rough model: EMF = B * v * L, converted to frequency effect.
    """
    if dist_km <= 0:
        return 0
    # Field falls off with distance squared
    effective_field = field_strength_T / (dist_km ** 2)
    # EMF in transmission line of length L
    emf = effective_field * 400 * line_length_km * 1000  # 400m/s obj velocity estimate
    # Convert to approximate frequency deviation (mHz)
    # This is very rough — real calculation needs line impedance data
    deviation_mhz = emf * 0.001
    return round(deviation_mhz, 4)


def compute_expected_deviations(track) -> list:
    """
    Compute expected frequency deviations at each grid monitor
    as the formation passes nearby.
    Returns time-series of expected deviations.
    """
    expected = []

    for w in track.witnesses:
        if w.get("conf", 1) < 0:
            continue

        for monitor_id, monitor in GRID_MONITORS.items():
            dist = haversine_km(w["lat"], w["lon"],
                               monitor["lat"], monitor["lon"])

            if dist < COUPLING_THRESHOLD_NM:
                deviation = estimate_induced_deviation(
                    EM_FIELD_ESTIMATE_T, max(dist, 1)
                )
                expected.append({
                    "time":          w["time"],
                    "monitor":       monitor_id,
                    "utility":       monitor["utility"],
                    "dist_km":       round(dist, 1),
                    "est_dev_mhz":   deviation,
                    "source":        w.get("desc", ""),
                    "sigma":         max(0, 3.0 - (dist / 20)),  # Closer = stronger sigma
                    "field":         f"grid_freq_{monitor_id}",
                })

    return sorted(expected, key=lambda x: x["time"])


def fetch_fnet_data(start: datetime.datetime, end: datetime.datetime) -> list:
    """
    Attempt to fetch FNET/GridEye frequency data.
    Coverage starts around 2004 — historical events pre-2004 need utility FOIA requests.
    """
    try:
        r = requests.get(FNET_URL, timeout=10)
        if r.status_code == 200:
            return [{"source": "fnet", "status": "available"}]
    except Exception:
        pass
    return []


def build_foia_template(track) -> str:
    """
    Generate a FOIA request template for utility frequency logs.
    For pre-FNET events, FOIA to utilities is the only way to get data.
    """
    t_start, t_end = track.time_window(60)
    utilities = set(m["utility"] for m in GRID_MONITORS.values())

    return f"""
FREEDOM OF INFORMATION ACT REQUEST

Re: Electric Grid Frequency Monitoring Data
Event Date: {track.date}
Time Window: {t_start.strftime('%H:%M')} – {t_end.strftime('%H:%M')} UTC

Requesting: All available frequency deviation logs, SCADA records,
and power quality monitoring data for the above time window from
substations located in the following corridor:
{track.bounding_box()}

Relevant utilities: {', '.join(utilities)}

Purpose: Scientific research into geophysical correlates of
documented atmospheric phenomena.

Contact NERC for interconnection-wide frequency data:
https://www.nerc.com/pa/RAPA/PA/Pages/FADS.aspx
"""


def run(track, eia_key: str = None, **kwargs) -> dict:
    """Run power grid frequency deviation lens."""
    print(f"    [powergrid] Computing expected EM induction signatures...")

    t_start, t_end = track.time_window(60)

    # Compute expected deviations from track geometry
    expected = compute_expected_deviations(track)
    print(f"    [powergrid] {len(expected)} grid monitors potentially affected")

    for e in expected[:5]:
        print(f"    [powergrid]   {e['time'].strftime('%H:%M')} | {e['monitor']} | "
              f"dist={e['dist_km']}km | est_dev={e['est_dev_mhz']}mHz")

    # Try FNET (post-2004 only)
    fnet = fetch_fnet_data(t_start, t_end)

    # Generate FOIA template for historical data
    foia = build_foia_template(track)

    # Significant deviations as anomalies
    anomalies = [e for e in expected if e["dist_km"] < 30]

    return {
        "expected_deviations": expected,
        "anomalies":           anomalies,
        "fnet_available":      bool(fnet),
        "foia_template":       foia,
        "lens":                "powergrid",
        "note":                "Pre-2004 grid frequency data requires FOIA requests to utilities or NERC",
        "nerc_foia_url":       "https://www.nerc.com/pa/RAPA/PA/Pages/FADS.aspx",
    }
