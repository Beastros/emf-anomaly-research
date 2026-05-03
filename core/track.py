"""
core/track.py
=============
Event geometry: interpolation, velocity, heading, coverage analysis.
All events are defined as a sequence of {time, lat, lon, desc, conf} points.
"""

import datetime
import math
import numpy as np
from typing import List, Optional, Tuple, Dict


def naive_utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def heading_deg(lat1, lon1, lat2, lon2) -> float:
    """Bearing in degrees from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(math.radians(lat2))
    y = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


class EventTrack:
    """
    Represents a UAP event as a sequence of geolocated, timestamped witness reports.
    Provides interpolation, velocity computation, and segment analysis.
    """

    def __init__(self, event: dict):
        self.name        = event["name"]
        self.date        = event["date"]
        self.description = event.get("description", "")
        self.witnesses   = sorted(event["witnesses"], key=lambda w: w["time"])
        self._parse_times()

    def _parse_times(self):
        for w in self.witnesses:
            if isinstance(w["time"], str):
                w["time"] = datetime.datetime.fromisoformat(
                    w["time"].replace("Z", "+00:00")
                )

    @property
    def start_time(self) -> datetime.datetime:
        return self.witnesses[0]["time"]

    @property
    def end_time(self) -> datetime.datetime:
        return self.witnesses[-1]["time"]

    def duration_minutes(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 60

    def segments(self) -> List[dict]:
        """Compute velocity and heading for each witness-to-witness segment."""
        segs = []
        for i in range(len(self.witnesses) - 1):
            w1, w2 = self.witnesses[i], self.witnesses[i+1]
            dt_h   = (w2["time"] - w1["time"]).total_seconds() / 3600
            dist   = haversine_km(w1["lat"], w1["lon"], w2["lat"], w2["lon"])
            speed  = dist / dt_h if dt_h > 0 else 0
            hdg    = heading_deg(w1["lat"], w1["lon"], w2["lat"], w2["lon"])
            segs.append({
                "from":       w1.get("desc", f"W{i}"),
                "to":         w2.get("desc", f"W{i+1}"),
                "from_time":  w1["time"],
                "to_time":    w2["time"],
                "dist_km":    round(dist, 2),
                "speed_kmh":  round(speed, 1),
                "speed_kts":  round(speed * 0.539957, 1),
                "heading":    round(hdg, 1),
                "dt_min":     round(dt_h * 60, 1),
            })
        return segs

    def interpolate(self, t: datetime.datetime) -> Optional[Tuple[float, float]]:
        """Return (lat, lon) at time t via linear interpolation."""
        ws = [w for w in self.witnesses if w.get("conf", 1) >= 0]
        if not ws:
            return None
        t = naive_utc(t)
        t_min, t_max = naive_utc(ws[0]["time"]), naive_utc(ws[-1]["time"])
        if t < t_min or t > t_max:
            return None
        for i in range(len(ws) - 1):
            t0, t1 = naive_utc(ws[i]["time"]), naive_utc(ws[i + 1]["time"])
            if t0 <= t <= t1:
                f = (t - t0).total_seconds() / (t1 - t0).total_seconds()
                lat = ws[i]["lat"] + (ws[i+1]["lat"] - ws[i]["lat"]) * f
                lon = ws[i]["lon"] + (ws[i+1]["lon"] - ws[i]["lon"]) * f
                return (lat, lon)
        return None

    def velocity_summary(self, known_max_kmh: float = None) -> dict:
        segs    = self.segments()
        speeds  = [s["speed_kmh"] for s in segs if s["speed_kmh"] > 0]
        avg_spd = round(float(np.mean(speeds)), 1) if speeds else 0
        max_spd = round(float(np.max(speeds)), 1) if speeds else 0
        headings = [s["heading"] for s in segs]
        hdg_std  = round(float(np.std(headings)), 1) if headings else 0

        result = {
            "avg_speed_kmh":       avg_spd,
            "max_speed_kmh":       max_spd,
            "avg_speed_kts":       round(avg_spd * 0.539957, 1),
            "heading_std_deg":     hdg_std,
            "anomalous_headings":  [s for s in segs if abs(s["heading"] - np.mean(headings)) > 60],
            "segments":            segs,
        }
        if known_max_kmh:
            result["reference_max_kmh"]      = known_max_kmh
            result["segments_exceeding_max"] = [s for s in segs if s["speed_kmh"] > known_max_kmh]
            result["consistent_with_ref"]    = len(result["segments_exceeding_max"]) == 0

        return result

    def bounding_box(self, pad_deg=0.5) -> dict:
        lats = [w["lat"] for w in self.witnesses]
        lons = [w["lon"] for w in self.witnesses]
        return {
            "min_lat": min(lats) - pad_deg,
            "max_lat": max(lats) + pad_deg,
            "min_lon": min(lons) - pad_deg,
            "max_lon": max(lons) + pad_deg,
        }

    def time_window(self, pad_minutes=30) -> Tuple[datetime.datetime, datetime.datetime]:
        pad = datetime.timedelta(minutes=pad_minutes)
        return (self.start_time - pad, self.end_time + pad)

    def summary(self) -> dict:
        return {
            "name":             self.name,
            "date":             self.date,
            "witnesses":        len(self.witnesses),
            "duration_min":     self.duration_minutes(),
            "total_dist_km":    sum(s["dist_km"] for s in self.segments()),
            "bounding_box":     self.bounding_box(),
        }
