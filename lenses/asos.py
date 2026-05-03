"""
lenses/asos.py
==============
Localized surface weather from aviation ASOS/METAR via Iowa Environmental Mesonet archive.

Granular visibility, wind, altimeter — complements coarse Nexrad archive checks.
"""

from __future__ import annotations

import csv
import datetime
import io
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests

from core.anomaly import AnomalyTimeseries
from core.track import EventTrack, naive_utc

IEM_ASOS_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
REQUEST_TIMEOUT = 120

# Phoenix metro + nearby valley reference points (ICAO as used by IEM)
DEFAULT_STATIONS = ("KPHX", "KDVT", "KIWA", "KSDL")
CHICAGO_ASOS = ("KORD", "KMDW", "KPWK", "KUGN")


def stations_for_event_track(track: EventTrack) -> Tuple[str, ...]:
    bb = track.bounding_box(0.0)
    lat_c = (bb["min_lat"] + bb["max_lat"]) / 2
    lon_c = (bb["min_lon"] + bb["max_lon"]) / 2
    if 41.2 <= lat_c <= 42.9 and -88.9 <= lon_c <= -87.3:
        return CHICAGO_ASOS
    if 32.4 <= lat_c <= 34.6 and -113.3 <= lon_c <= -111.2:
        return DEFAULT_STATIONS
    return DEFAULT_STATIONS

_SIGNIFICANT_WX = frozenset(
    {"TS", "TSRA", "VCTS", "LTG", "FG", "BR", "HZ", "FU", "DU", "BLDU", "BLSN", "SQ", "FC", "+RA", "RA", "SN", "SHRA", "SHSN"}
)


def _norm_station(raw: str) -> str:
    s = (raw or "").strip().upper()
    if len(s) == 3 and s.isalpha():
        return "K" + s
    return s


def _parse_float(x: Any) -> float:
    if x is None:
        return float("nan")
    t = str(x).strip()
    if t in ("", "M", "m", "T"):
        return float("nan")
    try:
        return float(t)
    except ValueError:
        return float("nan")


def _parse_time(valid_raw: str) -> datetime.datetime:
    valid_raw = valid_raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(valid_raw, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError(f"unparsed valid time: {valid_raw!r}")


def fetch_asos_csv(
    stations: Tuple[str, ...],
    t0: datetime.datetime,
    t1: datetime.datetime,
) -> str:
    params: Dict[str, Any] = {
        "data": "all",
        "year1": t0.year,
        "month1": t0.month,
        "day1": t0.day,
        "hour1": t0.hour,
        "minute1": t0.minute,
        "year2": t1.year,
        "month2": t1.month,
        "day2": t1.day,
        "hour2": t1.hour,
        "minute2": t1.minute,
        "tz": "UTC",
        "format": "onlycomma",
        "latlon": "yes",
        "direct": "yes",
        "missing": "M",
        "trace": "T",
    }
    for s in stations:
        params.setdefault("station", []).append(s)

    r = requests.get(IEM_ASOS_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def _wx_tokens(wx: str) -> List[str]:
    if not wx or str(wx).strip() in ("M", "m"):
        return []
    return str(wx).strip().split()


def run(track, **kwargs):
    pad_minutes = float(kwargs.get("asos_pad_minutes", 720))
    if kwargs.get("asos_stations"):
        stations = tuple(str(x).strip().upper() for x in kwargs["asos_stations"])
    else:
        stations = stations_for_event_track(track)
    tw0, tw1 = track.time_window(pad_minutes)
    t0 = naive_utc(tw0)
    t1 = naive_utc(tw1)

    print(
        f"    [asos] IEM ASOS/METAR {t0.isoformat()}Z → {t1.isoformat()}Z  "
        f"stations={list(stations)}"
    )

    try:
        raw_csv = fetch_asos_csv(stations, t0, t1)
    except Exception as e:
        print(f"    [asos] fetch failed: {e}")
        return {
            "lens": "asos",
            "anomalies": [],
            "series_summary": {"status": "error", "error": str(e)},
            "note": "IEM ASOS archive unreachable — try again or narrow window",
        }

    reader = csv.DictReader(io.StringIO(raw_csv))
    rows: List[dict] = []
    for row in reader:
        try:
            sid = _norm_station(row.get("station", ""))
            lat = _parse_float(row.get("lat"))
            lon = _parse_float(row.get("lon"))
            vt = _parse_time(row.get("valid", ""))
        except (ValueError, TypeError):
            continue
        rows.append(
            {
                "station": sid,
                "valid": vt,
                "lat": lat,
                "lon": lon,
                "tmpf": _parse_float(row.get("tmpf")),
                "dwpf": _parse_float(row.get("dwpf")),
                "sknt": _parse_float(row.get("sknt")),
                "vsby": _parse_float(row.get("vsby")),
                "alti": _parse_float(row.get("alti")),
                "gust": _parse_float(row.get("gust")),
                "wxcodes": row.get("wxcodes") or "",
                "metar": (row.get("metar") or "")[:500],
            }
        )

    if len(rows) < 8:
        print(f"    [asos] Too few rows: {len(rows)}")
        return {
            "lens": "asos",
            "anomalies": [],
            "series_summary": {"status": "sparse", "row_count": len(rows)},
            "note": "Sparse ASOS archive return — widen asos_pad_minutes or check station IDs",
        }

    w_start = naive_utc(track.start_time)
    w_end = naive_utc(track.end_time)

    per_station: Dict[str, List[dict]] = {}
    for r in rows:
        per_station.setdefault(r["station"], []).append(r)

    anomalies: List[dict] = []
    station_summaries: Dict[str, Any] = {}

    for sid in sorted(per_station.keys()):
        obs = sorted(per_station[sid], key=lambda x: x["valid"])
        in_win = [o for o in obs if w_start <= o["valid"] <= w_end]

        wx_all: List[str] = []
        for o in obs:
            wx_all.extend(_wx_tokens(o["wxcodes"]))
        sig_hits = sorted({w for w in wx_all if w in _SIGNIFICANT_WX})

        def series_for(field: str) -> Tuple[List[datetime.datetime], np.ndarray]:
            ts_l: List[datetime.datetime] = []
            vals: List[float] = []
            for o in obs:
                v = float(o[field])
                if np.isnan(v):
                    continue
                ts_l.append(o["valid"])
                vals.append(v)
            return ts_l, np.array(vals, dtype=float)

        st_summary: Dict[str, Any] = {
            "obs_count": len(obs),
            "event_window_obs": len(in_win),
            "wxcodes_flagged": sig_hits,
        }
        if in_win:
            vs = [o["vsby"] for o in in_win if not np.isnan(o["vsby"])]
            sk = [o["sknt"] for o in in_win if not np.isnan(o["sknt"])]
            st_summary["event_min_vsby_mi"] = round(float(min(vs)), 2) if vs else None
            st_summary["event_max_vsby_mi"] = round(float(max(vs)), 2) if vs else None
            st_summary["event_max_sknt"] = round(float(max(sk)), 1) if sk else None
        station_summaries[sid] = st_summary

        lat0 = next((o["lat"] for o in obs if not np.isnan(o["lat"])), float("nan"))
        lon0 = next((o["lon"] for o in obs if not np.isnan(o["lon"])), float("nan"))

        for field, units in (("sknt", "kt"), ("alti", "inHg")):
            times, arr = series_for(field)
            if len(arr) < 20:
                continue
            if np.nanstd(arr) < 1e-6:
                continue
            ts_obj = AnomalyTimeseries(sid, field, times, arr, units=units)
            for hit in ts_obj.anomalies(2.0):
                hit = dict(hit)
                hit["station"] = sid
                if not np.isnan(lat0):
                    hit["lat"] = round(float(lat0), 4)
                if not np.isnan(lon0):
                    hit["lon"] = round(float(lon0), 4)
                hit["lens_detail"] = "asos"
                anomalies.append(hit)

        times_v, arr_v = series_for("vsby")
        if len(arr_v) >= 20 and np.nanstd(arr_v) > 1e-4:
            ts_v = AnomalyTimeseries(sid, "vsby_mi", times_v, arr_v, units="mi")
            for hit in ts_v.anomalies(2.0):
                hit = dict(hit)
                hit["station"] = sid
                if not np.isnan(lat0):
                    hit["lat"] = round(float(lat0), 4)
                if not np.isnan(lon0):
                    hit["lon"] = round(float(lon0), 4)
                hit["lens_detail"] = "asos"
                anomalies.append(hit)

    anomalies.sort(key=lambda a: a["time"])

    print(f"    [asos] Parsed {len(rows)} METAR rows → {len(anomalies)} σ-hits (wind/pressure/vis)")

    series_summary = {
        "status": "ok",
        "source": "IEM ASOS archive (https://mesonet.agron.iastate.edu)",
        "stations": station_summaries,
        "station_list": list(stations),
        "window_utc": [t0.isoformat() + "Z", t1.isoformat() + "Z"],
        "event_span_utc": [w_start.isoformat() + "Z", w_end.isoformat() + "Z"],
    }

    return {
        "lens": "asos",
        "anomalies": anomalies,
        "series_summary": series_summary,
        "note": "Localized aviation wx — visibility/wind/altimeter vs rolling baseline on each station",
    }
