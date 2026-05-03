"""
core/anomaly.py
===============
Rolling baseline anomaly detection, null-return scoring,
multi-axis convergence analysis. Dataset-agnostic.
"""

import numpy as np
import datetime
from typing import Callable, List, Dict, Optional, Tuple

# PRE-REGISTERED 2026-04-30 -- do not change between runs
MIN_BASELINE_POINTS = 15   # warmup guard -- prevents artifact spikes from thin windows
BASELINE_WINDOW     = 20   # rolling baseline window in minutes


def _naive_utc(dt: datetime.datetime) -> datetime.datetime:
    """Convergence compares times — force naive UTC for stable ordering."""
    if not isinstance(dt, datetime.datetime):
        return dt
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def rolling_baseline(arr: np.ndarray, window: int = BASELINE_WINDOW) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute rolling mean baseline, deviation, sigma, and anomaly score.
    Past-only window (no future leak).
    Requires MIN_BASELINE_POINTS valid samples before scoring -- prevents
    artifactual high sigmas from near-zero-variance windows at series start.
    Returns (baseline, deviation, sigma, score_in_sigma_units)
    """
    n = len(arr)
    base = np.zeros(n)
    dev  = np.zeros(n)
    sig  = np.zeros(n)

    for i in range(n):
        sl    = arr[max(0, i - window):i]
        valid = sl[~np.isnan(sl)]
        if len(valid) >= MIN_BASELINE_POINTS:
            base[i] = np.mean(valid)
            sig[i]  = np.std(valid)
            dev[i]  = arr[i] - base[i]
        else:
            # Warmup period -- not enough history to score reliably
            base[i] = arr[i] if not np.isnan(arr[i]) else 0
            sig[i]  = 0.001
            dev[i]  = 0

    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(sig > 0.001, np.abs(dev) / sig, 0)

    return base, dev, sig, score


def null_return_score(predicted_pos: Tuple[float, float],
                      sensor_pos: Tuple[float, float],
                      sensor_range_km: float,
                      actual_returns: list,
                      search_radius_km: float = 20.0) -> float:
    from core.track import haversine_km
    dist_to_sensor = haversine_km(
        predicted_pos[0], predicted_pos[1],
        sensor_pos[0], sensor_pos[1]
    )
    if dist_to_sensor > sensor_range_km:
        return 0.0
    nearby = [
        r for r in actual_returns
        if haversine_km(r["lat"], r["lon"], predicted_pos[0], predicted_pos[1]) < search_radius_km
    ]
    if len(nearby) == 0:
        penetration = 1.0 - (dist_to_sensor / sensor_range_km)
        return round(min(0.95, 0.5 + penetration * 0.45), 3)
    else:
        return 0.1


class AnomalyTimeseries:
    def __init__(self, name: str, field: str, times: List[datetime.datetime],
                 values: np.ndarray, units: str = "", window: int = BASELINE_WINDOW):
        self.name   = name
        self.field  = field
        self.times  = times
        self.values = np.array(values, dtype=float)
        self.units  = units
        self.baseline, self.deviation, self.sigma, self.score = rolling_baseline(self.values, window)

    def anomalies(self, threshold: float = 2.0) -> List[dict]:
        hits = []
        for i, (t, s, d, v) in enumerate(zip(self.times, self.score, self.deviation, self.values)):
            if s > threshold and not np.isnan(s):
                hits.append({
                    "time":      t,
                    "field":     self.field,
                    "sigma":     round(float(s), 3),
                    "deviation": round(float(d), 4),
                    "value":     round(float(v), 4),
                    "units":     self.units,
                })
        return hits

    def window_stats(self, t_start: datetime.datetime, t_end: datetime.datetime) -> dict:
        idx = [i for i, t in enumerate(self.times) if t_start <= t <= t_end]
        if not idx:
            return {"count": 0}
        vals   = self.values[idx]
        scores = self.score[idx]
        devs   = self.deviation[idx]
        valid  = vals[~np.isnan(vals)]
        return {
            "count":      len(idx),
            "mean":       round(float(np.mean(valid)), 4) if len(valid) else None,
            "std":        round(float(np.std(valid)), 4) if len(valid) else None,
            "max_sigma":  round(float(np.max(scores)), 3),
            "mean_sigma": round(float(np.mean(scores)), 3),
            "max_dev":    round(float(np.max(np.abs(devs))), 4),
            "anomalies":  int(np.sum(scores > 2.0)),
        }

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "field":            self.field,
            "units":            self.units,
            "anomalies_2sigma": len(self.anomalies(2.0)),
            "anomalies_3sigma": len(self.anomalies(3.0)),
            "peak_sigma":       round(float(np.max(self.score)), 3),
            "peak_time":        self.times[int(np.argmax(self.score))].isoformat(),
        }


class ConvergenceEngine:
    def __init__(self, track, window_minutes: float = 10.0):
        self.track          = track
        self.window_minutes = window_minutes
        self.lens_results   = {}

    def add_lens(self, lens_name: str, anomalies: List[dict]):
        self.lens_results[lens_name] = anomalies

    def find_convergence(
        self,
        min_lenses: int = 2,
        lens_family_fn: Optional[Callable[[str, dict], str]] = None,
    ) -> List[dict]:
        if not self.lens_results:
            return []
        all_times = []
        for lens, anomalies in self.lens_results.items():
            for a in anomalies:
                all_times.append((_naive_utc(a["time"]), lens, a))
        all_times.sort(key=lambda x: x[0])
        convergences = []
        window = datetime.timedelta(minutes=self.window_minutes)
        for i, (t_center, lens_i, anom_i) in enumerate(all_times):
            tc = _naive_utc(t_center)
            nearby = [
                (t, l, a)
                for t, l, a in all_times
                if abs((t - tc).total_seconds()) <= window.total_seconds()
            ]
            raw_lenses = sorted(set(l for _, l, _ in nearby))
            if lens_family_fn:
                families = sorted(
                    set(lens_family_fn(l, a) for _, l, a in nearby)
                )
                fam_count = len(families)
                strength_n = fam_count
            else:
                families = raw_lenses
                fam_count = len(raw_lenses)
                strength_n = fam_count
            if fam_count >= min_lenses:
                already = any(
                    abs((_naive_utc(c["time"]) - tc).total_seconds())
                    < window.total_seconds() / 2
                    for c in convergences
                )
                if not already:
                    pos = self.track.interpolate(t_center)
                    max_sigma = max((a.get("sigma", 0) for _, _, a in nearby), default=0)
                    convergences.append(
                        {
                            "time": t_center,
                            "lenses": raw_lenses,
                            "lens_families": families,
                            "lens_count": fam_count,
                            "max_sigma": round(max_sigma, 3),
                            "position": {"lat": pos[0], "lon": pos[1]} if pos else None,
                            "anomalies": [a for _, _, a in nearby],
                            "strength": round(strength_n * max_sigma, 2),
                        }
                    )
        return sorted(convergences, key=lambda x: x["strength"], reverse=True)

    def summary(self) -> dict:
        convergences = self.find_convergence()
        return {
            "lenses_run":         list(self.lens_results.keys()),
            "total_anomalies":    sum(len(v) for v in self.lens_results.values()),
            "convergence_events": len(convergences),
            "top_convergences":   convergences[:5],
            "per_lens":           {k: len(v) for k, v in self.lens_results.items()},
        }
