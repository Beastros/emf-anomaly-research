"""
tools/nevada_swarm_gw_em_probe.py
=================================
News-anchored Nevada swarm (Apr 2026) + USGS origin times + GWOSC overlap check
+ INTERMAGNET minute-field excursion stats (EM proxy).

Not physics claims — lab notebook for your stack.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

import numpy as np

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
GWOSC_GWTC4 = "https://gwosc.org/eventapi/json/GWTC-4.0"
GWOSC_GWTC3 = "https://gwosc.org/eventapi/json/GWTC-3-confident"

# News anchors (headlines): M4.4 ~3pm PDT Apr 29 2026; USGS NN00916724 is authoritative origin below.
GPS_EPOCH = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)

MAG_STATIONS = (
    ("FRN", "Fresno CA — nearest definitive INTERMAGNET to southern NV cluster"),
    ("TUC", "Tucson AZ"),
    ("BOU", "Boulder CO"),
)


def utc_to_gps(t: dt.datetime) -> float:
    t = t.astimezone(dt.timezone.utc)
    return (t - GPS_EPOCH).total_seconds()


def gps_to_utc(gps: float) -> dt.datetime:
    return GPS_EPOCH + dt.timedelta(seconds=gps)


def fetch_json(url: str, params: Dict[str, Any] | None = None) -> Any:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    r = urllib.request.urlopen(url, timeout=60)
    return json.loads(r.read().decode())


def usgs_swarm_events() -> List[dict]:
    params = {
        "format": "geojson",
        "starttime": "2026-04-28",
        "endtime": "2026-05-01",
        "minlatitude": 36.4,
        "maxlatitude": 37.9,
        "minlongitude": -116.2,
        "maxlongitude": -114.4,
        "minmagnitude": "1.5",
        "orderby": "time-asc",
    }
    data = fetch_json(USGS_URL, params)
    out = []
    for f in data.get("features", []):
        p = f["properties"]
        geom = f["geometry"]["coordinates"]
        lon, lat, depth_km = geom[0], geom[1], geom[2]
        t_ms = p.get("time")
        if t_ms is None:
            continue
        t_utc = dt.datetime.fromtimestamp(t_ms / 1000.0, tz=dt.timezone.utc)
        out.append(
            {
                "time_utc": t_utc.isoformat(),
                "gps": utc_to_gps(t_utc),
                "mag": p.get("mag"),
                "magType": p.get("magType"),
                "place": p.get("place"),
                "depth_km": depth_km,
                "url": p.get("url"),
                "id": f.get("id"),
            }
        )
    return out


def hapi_xyzf(station: str, t0: dt.datetime, t1: dt.datetime) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]]:
    times: List[dt.datetime] = []
    X, Y, Z = [], [], []
    errs: List[str] = []
    # Recent months: definitive often 400 until processing; adjusted/best-avail works.
    for dtype in ("definitive", "adjusted", "quasi-definitive", "variation"):
        params = {
            "id": f"{station.lower()}/{dtype}/PT1M/xyzf",
            "time.min": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "time.max": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "format": "json",
        }
        q = urllib.parse.urlencode(params)
        try:
            r = urllib.request.urlopen(f"{HAPI_BASE}?{q}", timeout=45)
            rows = json.loads(r.read().decode()).get("data", [])
        except Exception as e:
            errs.append(f"{station}/{dtype}: {e}")
            continue
        if len(rows) < 5:
            errs.append(f"{station}/{dtype}: sparse {len(rows)}")
            continue
        times.clear()
        X.clear()
        Y.clear()
        Z.clear()
        for row in rows:
            try:
                t = dt.datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                xyz = row[1]
                x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
                if abs(x) > 90000 or abs(y) > 90000 or abs(z) > 90000:
                    continue
                times.append(t)
                X.append(x)
                Y.append(y)
                Z.append(z)
            except (ValueError, TypeError, IndexError):
                continue
        if len(times) >= 10:
            return (
                np.array(X, dtype=float),
                np.array(Y, dtype=float),
                np.array(Z, dtype=float),
                np.array([utc_to_gps(t.astimezone(dt.timezone.utc)) for t in times]),
                [f"ok:{dtype} n={len(times)}"],
            )
    return np.array([]), np.array([]), np.array([]), np.array([]), errs or ["no_data"]


def em_stats(Z: np.ndarray) -> Dict[str, Any]:
    if Z.size < 5:
        return {"status": "insufficient"}
    med = np.nanmedian(Z)
    resid = np.abs(Z - med)
    d1 = np.abs(np.diff(Z))
    return {
        "status": "ok",
        "median_Z_nT": round(float(med), 2),
        "max_abs_residual_nT": round(float(np.nanmax(resid)), 3),
        "p95_abs_residual_nT": round(float(np.nanpercentile(resid, 95)), 3),
        "max_abs_minute_delta_nT": round(float(np.nanmax(d1)), 3),
        "p95_abs_minute_delta_nT": round(float(np.nanpercentile(d1, 95)), 3),
    }


def gwosc_in_window(catalog_url: str, gps0: float, gps1: float) -> Tuple[str, List[dict]]:
    try:
        data = fetch_json(catalog_url)
    except Exception as e:
        return str(e), []
    events = data.get("events", data)
    if not isinstance(events, dict):
        return "unexpected_shape", []
    hits = []
    for eid, meta in events.items():
        if not isinstance(meta, dict):
            continue
        g = meta.get("GPS")
        if g is None:
            continue
        try:
            g = float(g)
        except (TypeError, ValueError):
            continue
        if gps0 <= g <= gps1:
            hits.append(
                {
                    "id": eid,
                    "GPS": g,
                    "time_utc": gps_to_utc(g).isoformat(),
                    "commonName": meta.get("commonName"),
                }
            )
    return "ok", sorted(hits, key=lambda x: x["GPS"])


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(root, "outputs", "nevada_swarm_gw_em_probe.json")

    news_anchor = {
        "headline_claims": [
            "M4.4 near Area 51 / southern NV, Apr 29 2026 ~3pm local (PDT) per Independent, Newsweek, etc.",
            "Shallow depth ~2.5–4 km reported in press; USGS authoritative below.",
        ],
        "headline_vs_usgs_time_note": (
            "Press often cites ~3pm Pacific; USGS origin for nn00916724 is **15:06 UTC** "
            "(08:06 Pacific) in this pull — same cluster/day, not same clock minute. "
            "Use USGS `time` for alignment, not headline paraphrases."
        ),
        "usgs_mainshock_id_hint": "nn00916724 / us7000sh0q",
    }

    events = usgs_swarm_events()
    main = max(events, key=lambda e: e["mag"] or 0) if events else None

    em_block: Dict[str, Any] = {}
    gw_block: Dict[str, Any] = {}

    if main:
        t0 = dt.datetime.fromisoformat(main["time_utc"].replace("Z", "+00:00"))
        win0, win1 = t0 - dt.timedelta(hours=3), t0 + dt.timedelta(hours=3)
        gps_win0, gps_win1 = utc_to_gps(win0), utc_to_gps(win1)

        for code, note in MAG_STATIONS:
            X, Y, Z, _gps_arr, msg = hapi_xyzf(code, win0, win1)
            em_block[code] = {
                "note": note,
                "hapi": msg,
                "stats_Z": em_stats(Z),
            }

        gw_block["window_gps"] = [gps_win0, gps_win1]
        gw_block["window_utc"] = [win0.isoformat(), win1.isoformat()]

        for name, url in [("GWTC-4.0", GWOSC_GWTC4), ("GWTC-3-confident", GWOSC_GWTC3)]:
            err, hits = gwosc_in_window(url, gps_win0, gps_win1)
            gw_block[name] = {"catalog_error_or_ok": err, "mergers_in_window": hits}

    report = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "news_anchor": news_anchor,
        "usgs_events_in_box": events,
        "usgs_mainshock_pick": main,
        "emf_proxy_intermagnet_Z": em_block,
        "gravitational_wave_catalog_overlap": gw_block,
        "interpretation_lab_note": (
            "GW: LVK catalogs list compact-binary mergers, not terrestrial quakes. "
            "Empty overlap is expected. EM: minute variometer residuals/deltas summarize "
            "geomagnetic noise level during the USGS window — not localized 'Area 51 EM beam'."
        ),
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
