"""
lenses/infrasound.py
====================
IRIS broadband vertical (BHZ): minute RMS + rolling σ (same spirit as seismic lens).

Also records geometry-based **expected arrival** rows separately (`geometry_priors`)
— not fed as measurement anomalies.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Tuple

import numpy as np
import requests

from core.anomaly import (
    AnomalyTimeseries,
    BASELINE_WINDOW,
    MIN_BASELINE_POINTS,
)
from core.track import haversine_km

IRIS_TIMESERIES = "https://service.iris.edu/irisws/timeseries/1/query"

INFRASOUND_STATIONS = {
    "BK.CMB": {"lat": 38.034, "lon": -120.386, "name": "Columbia CA", "network": "BK"},
    "IU.ANMO": {"lat": 34.946, "lon": -106.457, "name": "Albuquerque NM", "network": "IU"},
    "IU.TUC": {"lat": 32.310, "lon": -110.785, "name": "Tucson AZ", "network": "IU"},
    "IM.I57US": {"lat": 33.606, "lon": -116.453, "name": "Pinon Flat CA", "network": "IM"},
    "IU.CCM": {"lat": 38.056, "lon": -91.245, "name": "Cathedral Cave MO", "network": "IU"},
    "US.TZTN": {"lat": 36.623, "lon": -83.447, "name": "Tazewell TN", "network": "US"},
}

SOUND_SPEED_MS = 340
MAX_FETCH_HOURS = 6.0
REQUEST_TIMEOUT = 120


def cap_window(
    t0: datetime.datetime,
    t1: datetime.datetime,
    max_hours: float = MAX_FETCH_HOURS,
) -> Tuple[datetime.datetime, datetime.datetime]:
    span_s = (t1 - t0).total_seconds()
    cap_s = max_hours * 3600.0
    if span_s <= cap_s:
        return t0, t1
    mid = t0 + datetime.timedelta(seconds=span_s / 2.0)
    half = datetime.timedelta(seconds=cap_s / 2.0)
    return mid - half, mid + half


def fetch_iris_waveform(
    network: str,
    station: str,
    channel: str,
    start: datetime.datetime,
    end: datetime.datetime,
    loc_candidates: Tuple[str, ...] = ("00", "--"),
) -> Dict[str, Any]:
    for loc in loc_candidates:
        params = {
            "net": network,
            "sta": station,
            "loc": loc,
            "cha": channel,
            "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "output": "ascii",
        }
        try:
            r = requests.get(IRIS_TIMESERIES, params=params, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return {"data": r.text, "status": "ok", "loc_used": loc}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "no_data", "code": 404}


def parse_tspair_ascii(text: str) -> Tuple[np.ndarray, np.ndarray]:
    lines = text.strip().splitlines()
    if not lines:
        return np.array([], dtype="datetime64[ns]"), np.array([], dtype=float)
    ts_list: List[np.datetime64] = []
    vals: List[float] = []
    for ln in lines[1:]:
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split(None, 1)
        if len(parts) < 2:
            continue
        ts_raw = parts[0]
        try:
            v = float(parts[1].split()[0])
        except (ValueError, IndexError):
            continue
        try:
            ts_list.append(np.datetime64(ts_raw.replace("Z", "")))
        except Exception:
            continue
        vals.append(v)
    return np.array(ts_list, dtype="datetime64[ns]"), np.array(vals, dtype=float)


def minute_floor_series(
    timestamps: np.ndarray, values: np.ndarray
) -> Tuple[List[datetime.datetime], np.ndarray]:
    if len(timestamps) == 0:
        return [], np.array([], dtype=float)
    t_ns = timestamps.astype("datetime64[ns]").astype(np.int64)
    minute_ns = 60_000_000_000
    bucket = (t_ns // minute_ns).astype(np.int64)
    order = np.argsort(bucket)
    b = bucket[order]
    v = values[order].astype(float)
    uniq: List[int] = []
    rms_vals: List[float] = []
    i, n = 0, len(b)
    while i < n:
        j = i
        while j < n and b[j] == b[i]:
            j += 1
        chunk = v[i:j]
        rms_vals.append(float(np.sqrt(np.mean(chunk * chunk))))
        uniq.append(int(b[i]))
        i = j
    times_out: List[datetime.datetime] = []
    for ub in uniq:
        ns = ub * minute_ns
        dt64 = np.datetime64(ns, "ns")
        t_py = datetime.datetime.utcfromtimestamp(dt64.astype(np.int64) / 1e9)
        times_out.append(t_py)
    return times_out, np.array(rms_vals, dtype=float)


def estimate_travel_time(source_lat, source_lon, station_lat, station_lon, alt_m=1000) -> float:
    dist_km = haversine_km(source_lat, source_lon, station_lat, station_lon)
    path_m = np.sqrt((dist_km * 1000) ** 2 + alt_m**2)
    return path_m / SOUND_SPEED_MS


def run(track, pad_minutes: int = 60, **kwargs) -> dict:
    print(f"    [infrasound] IRIS BHZ minute-RMS + σ (cap {MAX_FETCH_HOURS}h)...")
    t_start, t_end = track.time_window(pad_minutes)
    ft0, ft1 = cap_window(t_start, t_end)
    if (ft0, ft1) != (t_start, t_end):
        print(
            f"    [infrasound] Time window capped to {MAX_FETCH_HOURS}h centered on event"
        )

    bbox = track.bounding_box(pad_deg=5.0)
    nearby = {
        sid: info
        for sid, info in INFRASOUND_STATIONS.items()
        if bbox["min_lat"] - 5 <= info["lat"] <= bbox["max_lat"] + 5
        and bbox["min_lon"] - 5 <= info["lon"] <= bbox["max_lon"] + 5
    }

    print(f"    [infrasound] Stations in range: {list(nearby.keys())}")

    measurement_anomalies: List[dict] = []
    geometry_priors: List[dict] = []
    station_results: Dict[str, Any] = {}
    min_minutes = BASELINE_WINDOW + MIN_BASELINE_POINTS

    for sid, info in nearby.items():
        net, sta = sid.split(".")
        channel = "BHZ"
        result = fetch_iris_waveform(net, sta, channel, ft0, ft1)
        if result["status"] != "ok":
            print(f"    [infrasound] {sid} {channel}: {result.get('status')} {result.get('code', '')}")
            continue

        print(f"    [infrasound] {sid} {channel}: waveform retrieved loc={result.get('loc_used')}")
        station_results[f"{sid}.{channel}"] = {"loc": result.get("loc_used")}

        ts_np, vals = parse_tspair_ascii(result["data"])
        if len(vals) < BASELINE_WINDOW * 10:
            print(f"      → skip RMS: only {len(vals)} samples")
        else:
            minutes, rms = minute_floor_series(ts_np, vals)
            if len(rms) >= min_minutes:
                ats = AnomalyTimeseries(
                    name=f"INFRA-{sid}-BHZ-RMS",
                    field=f"infrasound_rms_{sid}",
                    times=minutes,
                    values=rms,
                    units="counts_rms_1min",
                    window=BASELINE_WINDOW,
                )
                for anom in ats.anomalies(2.0):
                    anom["station"] = sid
                    anom["channel"] = channel
                    anom["kind"] = "bhz_minute_rms"
                    measurement_anomalies.append(anom)
                pk = float(ats.score.max())
                print(f"      → {len(minutes)} min bins  peak_σ={pk:.2f}  hits>{2}σ={len(ats.anomalies(2.0))}")
            else:
                print(f"      → skip σ: only {len(rms)} minute bins (need {min_minutes})")

        for w in track.witnesses:
            travel_s = estimate_travel_time(
                w["lat"], w["lon"], info["lat"], info["lon"]
            )
            expected_arrival = w["time"] + datetime.timedelta(seconds=travel_s)
            if t_start <= expected_arrival <= t_end:
                geometry_priors.append(
                    {
                        "time": expected_arrival,
                        "field": f"infrasound_prior_{sid}",
                        "sigma": 2.0,
                        "kind": "geometry_prior",
                        "source_witness": w.get("desc", ""),
                        "travel_time_s": round(travel_s, 1),
                        "dist_km": round(
                            haversine_km(
                                w["lat"], w["lon"], info["lat"], info["lon"]
                            ),
                            1,
                        ),
                        "station": sid,
                        "note": "Expected arrival (not waveform σ)",
                    }
                )

    if not station_results:
        print(f"    [infrasound] No BHZ waveforms — check IRIS availability")

    return {
        "stations_checked": list(nearby.keys()),
        "data_retrieved": list(station_results.keys()),
        "anomalies": measurement_anomalies,
        "geometry_priors": geometry_priors,
        "lens": "infrasound",
        "ctbto_url": "https://www.ctbto.org/specials/vdec/",
    }
