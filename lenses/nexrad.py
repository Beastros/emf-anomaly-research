"""
lenses/nexrad.py — Fixed to accept **kwargs
"""

import datetime
import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.config import Config
from core.anomaly import null_return_score
from core.track import haversine_km


S3_BUCKET = "noaa-nexrad-level2"
RANGE_KM  = 230

NEXRAD_STATIONS = {
    "KFSX": {"lat": 34.574, "lon": -111.198, "name": "Flagstaff AZ"},
    "KIWA": {"lat": 33.289, "lon": -111.670, "name": "Phoenix/Mesa AZ"},
    "KEMX": {"lat": 31.893, "lon": -110.630, "name": "Tucson AZ"},
    "KYUX": {"lat": 32.495, "lon": -114.656, "name": "Yuma AZ"},
}


def stations_in_range(track):
    in_range = {}
    for sid, info in NEXRAD_STATIONS.items():
        for w in track.witnesses:
            d = haversine_km(w["lat"], w["lon"], info["lat"], info["lon"])
            if d < RANGE_KM:
                in_range[sid] = info
                break
    return in_range


def list_files(station, dt):
    try:
        s3  = boto3.client("s3", region_name="us-east-1",
                           config=Config(signature_version=UNSIGNED))
        prefix = f"{dt.year}/{dt.month:02d}/{dt.day:02d}/{station}/"
        keys   = []
        pag    = s3.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
    except Exception as e:
        print(f"    [nexrad] {station} S3 error: {type(e).__name__}")
        return []


def run(track, **kwargs):  # **kwargs absorbs unused args
    t_start, t_end = track.time_window(30)
    stations       = stations_in_range(track)

    print(f"    [nexrad] Stations in range: {list(stations.keys())}")

    anomalies      = []
    station_scores = {}

    for sid, info in stations.items():
        files  = list_files(sid, t_start)
        print(f"    [nexrad] {sid}: {len(files)} archive files found")

        interval = datetime.timedelta(minutes=5)
        t        = t_start
        scores   = []

        while t <= t_end:
            pos = track.interpolate(t)
            if pos:
                score = null_return_score(
                    predicted_pos=pos,
                    sensor_pos=(info["lat"], info["lon"]),
                    sensor_range_km=RANGE_KM,
                    actual_returns=[],
                )
                if score > 0.5:
                    anomalies.append({
                        "time":    t,
                        "station": sid,
                        "sigma":   round(score * 3, 2),
                        "score":   score,
                        "lat":     pos[0],
                        "lon":     pos[1],
                        "field":   f"nexrad_null_{sid}",
                        "dist_to_station": round(
                            haversine_km(pos[0], pos[1], info["lat"], info["lon"]), 1
                        ),
                        "files_found": len(files),
                    })
                scores.append(score)
            t += interval

        station_scores[sid] = {
            "files_found": len(files),
            "mean_score":  round(float(np.mean(scores)), 3) if scores else 0,
            "max_score":   round(float(np.max(scores)), 3) if scores else 0,
            "null_return": len(files) == 0,
        }

    return {
        "station_scores":    station_scores,
        "anomalies":         anomalies,
        "lens":              "nexrad",
        "stations_checked":  list(stations.keys()),
        "all_null":          all(v["null_return"] for v in station_scores.values()),
    }
