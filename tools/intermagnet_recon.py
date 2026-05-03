"""
tools/intermagnet_recon.py
==========================
Inventory INTERMAGNET HAPI stations (definitive PT1M xyzf) and rank by distance
from an event centroid. Probes HAPI for row counts in a short test window.

Usage:
  python tools/intermagnet_recon.py
  python tools/intermagnet_recon.py --lat 33.45 --lon -112.07 --start 1997-03-14T02:00:00Z --end 1997-03-14T04:00:00Z
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

HAPI_CATALOG = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/catalog"
HAPI_DATA = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"

# Approximate observatory coordinates (WGS84) for US INTERMAGNET sites — for distance ranking only.
# Pulled from published observatory metadata / IAGA; refine if you need arc-second precision.
STATION_COORDS: dict[str, tuple[float, float, str]] = {
    "TUC": (32.174, -110.733, "Tucson AZ"),
    "FRN": (37.091, -119.717, "Fresno CA"),
    "DLR": (29.484, -100.915, "Del Rio TX"),
    "BOU": (40.137, -105.237, "Boulder CO"),
    "FRD": (38.205, -77.373, "Fredericksburg VA"),
    "SIT": (57.058, -135.325, "Sitka AK"),
    "CMO": (64.874, -147.860, "College AK"),
    "HON": (21.316, -158.000, "Honolulu HI"),
    "BRW": (71.322, -156.615, "Barrow AK"),
    "BSL": (30.350, -89.638, "Stennis MS"),
    "DED": (70.178, -148.451, "Deadhorse AK"),
    "GUA": (13.589, 144.868, "Guam"),
    "JCO": (64.874, -147.861, "College variant"),
    "MID": (28.208, -177.381, "Midway"),
    "NEW": (45.265, -124.065, "Newport OR"),
    "SHU": (55.349, -160.502, "Shumagin AK"),
    "SJG": (18.109, -66.150, "San Juan PR"),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_catalog() -> list[dict]:
    r = urllib.request.urlopen(HAPI_CATALOG, timeout=60)
    return json.loads(r.read().decode())["catalog"]


def us_definitive_xyzf_stations(catalog: list[dict]) -> dict[str, str]:
    """station_code -> title for */definitive/PT1M/xyzf datasets."""
    out: dict[str, str] = {}
    for e in catalog:
        if not e["id"].endswith("/definitive/PT1M/xyzf"):
            continue
        if "USA" not in e["title"] and "United States" not in e["title"]:
            continue
        code = e["id"].split("/")[0].upper()
        out[code] = e["title"]
    return out


def hapi_row_count(station: str, tmin: str, tmax: str) -> tuple[int, str | None]:
    params = {
        "id": f"{station.lower()}/definitive/PT1M/xyzf",
        "time.min": tmin,
        "time.max": tmax,
        "format": "json",
    }
    q = urllib.parse.urlencode(params)
    url = f"{HAPI_DATA}?{q}"
    try:
        r = urllib.request.urlopen(url, timeout=45)
        data = json.loads(r.read().decode())
        rows = data.get("data") or []
        return len(rows), None
    except Exception as e:
        return 0, str(e)


def main() -> None:
    p = argparse.ArgumentParser(description="INTERMAGNET distance + HAPI probe")
    p.add_argument("--lat", type=float, default=33.45)
    p.add_argument("--lon", type=float, default=-112.07)
    p.add_argument("--start", default="1997-03-14T02:00:00Z")
    p.add_argument("--end", default="1997-03-14T04:00:00Z")
    p.add_argument("--out", default="", help="Write JSON path (default: outputs/intermagnet_recon.json)")
    args = p.parse_args()

    cat = load_catalog()
    us_st = us_definitive_xyzf_stations(cat)

    ranked: list[dict] = []
    for code, title in sorted(us_st.items()):
        meta = STATION_COORDS.get(code)
        if not meta:
            continue
        lat_s, lon_s, label = meta
        d = haversine_km(args.lat, args.lon, lat_s, lon_s)
        ranked.append(
            {
                "code": code,
                "label": label,
                "lat": lat_s,
                "lon": lon_s,
                "distance_km": round(d, 1),
                "catalog_title_snip": title[:80] + "…",
            }
        )
    ranked.sort(key=lambda x: x["distance_km"])

    # Probe top 8 nearest for HAPI rows (2h window)
    probe: list[dict] = []
    for row in ranked[:8]:
        n, err = hapi_row_count(row["code"], args.start, args.end)
        probe.append({**row, "hapi_rows_in_window": n, "hapi_error": err})

    summary = {
        "centroid": {"lat": args.lat, "lon": args.lon},
        "test_window": {"start": args.start, "end": args.end},
        "nearest_intermagnet_definitive_xyzf_usa": ranked[:15],
        "hapi_probe_nearest_8": probe,
        "note": (
            "Distances use fixed STATION_COORDS in this script; only stations with known coords are ranked. "
            "Closest station to centroid is the best available *geomag* anchor — still hundreds of km for "
            "most US interiors; does not localize city-scale phenomena."
        ),
    }

    out_path = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs",
        "intermagnet_recon.json",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
