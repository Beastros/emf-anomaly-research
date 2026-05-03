"""
lenses/omni.py
==============
NASA OMNI2 1-hour merged solar-wind / IMF (lagged to near-Earth), via CDAWeb HAPI.

Treasure-hunt context: quiet vs elevated V_sw, Bz(GSM) vs rolling baseline — not causality.
Dataset: OMNI2_H0_MRG1HR (hourly cadence, timestamps at half-hour midpoints).
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

import numpy as np
import requests

from core.anomaly import AnomalyTimeseries, BASELINE_WINDOW, MIN_BASELINE_POINTS

HAPI_DATA = "https://cdaweb.gsfc.nasa.gov/hapi/data"
DATASET_ID = "OMNI2_H0_MRG1HR"
# Parameter order must match HAPI catalog order (Time first).
PARAMS = "Time,BZ_GSM1800,V1800"
BZ_FILL = 999.9
V_FILL = 9999.0


def _parse_time(s: str) -> datetime.datetime:
    dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return dt.replace(tzinfo=None)


def run(track, pad_minutes: int = 720, **kwargs: Any) -> dict:
    """
    Pull OMNI2 hourly V and Bz for the padded witness window; rolling σ on each series.
    """
    t_start, t_end = track.time_window(pad_minutes)
    tmin = t_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    tmax = t_end.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    print(f"    [omni] CDAWeb HAPI {DATASET_ID} {tmin} → {tmax}")

    params = {
        "id": DATASET_ID,
        "parameters": PARAMS,
        "time.min": tmin,
        "time.max": tmax,
        "format": "json",
    }
    try:
        r = requests.get(HAPI_DATA, params=params, timeout=90)
        j = r.json()
    except Exception as e:
        print(f"    [omni] Request failed: {e}")
        return {"anomalies": [], "lens": "omni", "error": str(e)}

    if j.get("status", {}).get("code") != 1200:
        print(f"    [omni] HAPI error: {j.get('status')}")
        return {"anomalies": [], "lens": "omni", "hapi_status": j.get("status")}

    rows = j.get("data") or []
    if len(rows) < MIN_BASELINE_POINTS + BASELINE_WINDOW:
        print(f"    [omni] Too few samples: {len(rows)}")
        return {"anomalies": [], "lens": "omni", "note": "short_series"}

    times: List[datetime.datetime] = []
    bz: List[float] = []
    vv: List[float] = []
    for row in rows:
        if len(row) < 3:
            continue
        try:
            t = _parse_time(row[0])
            b = float(row[1])
            v = float(row[2])
        except (ValueError, TypeError):
            continue
        if abs(b) >= BZ_FILL - 1 or abs(v) >= V_FILL - 1:
            continue
        times.append(t)
        bz.append(b)
        vv.append(v)

    if len(times) < MIN_BASELINE_POINTS + BASELINE_WINDOW:
        print(f"    [omni] Too few valid rows after fill strip: {len(times)}")
        return {"anomalies": [], "lens": "omni", "note": "mostly_fill"}

    bz_a = np.array(bz, dtype=float)
    v_a = np.array(vv, dtype=float)

    ts_bz = AnomalyTimeseries(
        "OMNI-Bz_GSM",
        "BZ_GSM1800",
        times,
        bz_a,
        units="nT",
        window=min(BASELINE_WINDOW, max(5, len(times) // 4)),
    )
    ts_v = AnomalyTimeseries(
        "OMNI-V_sw",
        "V1800",
        times,
        v_a,
        units="km/s",
        window=min(BASELINE_WINDOW, max(5, len(times) // 4)),
    )

    anomalies: List[dict] = []
    for an in ts_bz.anomalies(2.0):
        an["station"] = "OMNI2_1AU"
        an["lens_detail"] = "omni_imf"
        anomalies.append(an)
    for an in ts_v.anomalies(2.0):
        an["station"] = "OMNI2_1AU"
        an["lens_detail"] = "omni_plasma"
        anomalies.append(an)

    print(
        f"    [omni] Valid hourly rows={len(times)}  "
        f"Bz_peak_σ={float(ts_bz.score.max()):.2f}  "
        f"V_peak_σ={float(ts_v.score.max()):.2f}  "
        f"hits>{2}σ={len(anomalies)}"
    )

    return {
        "anomalies": anomalies,
        "lens": "omni",
        "series_summary": {
            "n_points": len(times),
            "bz_peak_sigma": round(float(ts_bz.score.max()), 3),
            "v_peak_sigma": round(float(ts_v.score.max()), 3),
            "bz_mean": round(float(np.mean(bz_a)), 2),
            "v_mean": round(float(np.mean(v_a)), 1),
            "window_start_utc": times[0].isoformat(),
            "window_end_utc": times[-1].isoformat(),
        },
        "source": HAPI_DATA,
        "dataset": DATASET_ID,
    }
