"""
lenses/nexrad.py — Level-II archive listing + conditional scoring.

When the S3 archive lists volumes for the UTC day, we emit an informational
tick and **skip** the legacy null-penetration grid for that station.

Anonymous listing: `unidata-nexrad-level2` then fallback `noaa-nexrad-level2`.
"""

import datetime
import boto3
import numpy as np
from botocore import UNSIGNED
from botocore.config import Config

from core.anomaly import null_return_score
from core.track import haversine_km

S3_BUCKETS = ("unidata-nexrad-level2", "noaa-nexrad-level2")
RANGE_KM = 230

NEXRAD_STATIONS = {
    "KFSX": {"lat": 34.574, "lon": -111.198, "name": "Flagstaff AZ"},
    "KIWA": {"lat": 33.289, "lon": -111.670, "name": "Phoenix/Mesa AZ"},
    "KEMX": {"lat": 31.893, "lon": -110.630, "name": "Tucson AZ"},
    "KYUX": {"lat": 32.495, "lon": -114.656, "name": "Yuma AZ"},
    "KLOT": {"lat": 41.6044, "lon": -88.0844, "name": "Chicago/Joliet IL"},
    "KMKX": {"lat": 42.9679, "lon": -88.5506, "name": "Milwaukee WI"},
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
    """Return (keys, bucket_name) — bucket empty string if none."""
    prefix = f"{dt.year}/{dt.month:02d}/{dt.day:02d}/{station}/"
    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )
    for bucket in S3_BUCKETS:
        try:
            keys = []
            pag = s3.get_paginator("list_objects_v2")
            for page in pag.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
            if keys:
                print(f"    [nexrad] {station}: listed from s3://{bucket}/")
            return keys, bucket
        except Exception as e:
            print(f"    [nexrad] {station} bucket={bucket} error: {type(e).__name__}: {e}")
            continue
    return [], ""


def sample_volume_head(bucket: str, keys: list) -> dict:
    """HEAD request on a mid-list key — proves object exists without full download."""
    if not bucket or not keys:
        return {"ok": False, "note": "no bucket or keys"}
    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED),
    )
    key = sorted(keys)[len(keys) // 2]
    try:
        r = s3.head_object(Bucket=bucket, Key=key)
        return {
            "ok": True,
            "sample_key": key,
            "content_length": r.get("ContentLength"),
            "last_modified": str(r.get("LastModified", "")),
        }
    except Exception as e:
        return {"ok": False, "sample_key": key, "error": str(e)}


def run(track, **kwargs):
    t_start, t_end = track.time_window(30)
    stations = stations_in_range(track)

    print(f"    [nexrad] Stations in range: {list(stations.keys())}")

    anomalies = []
    station_scores = {}

    for sid, info in stations.items():
        files, bucket_used = list_files(sid, t_start)
        print(f"    [nexrad] {sid}: {len(files)} archive files found")

        interval = datetime.timedelta(minutes=5)
        t = t_start
        scores = []

        if files:
            mid = t_start + (t_end - t_start) / 2
            pos = track.interpolate(mid)
            head = sample_volume_head(bucket_used, files)
            if head.get("ok"):
                print(f"    [nexrad] {sid}: HEAD ok bytes={head.get('content_length')}")
            else:
                print(f"    [nexrad] {sid}: HEAD stub {head.get('error', head.get('note'))}")

            anomalies.append(
                {
                    "time": mid,
                    "station": sid,
                    "sigma": 1.0,
                    "score": 1.0,
                    "lat": pos[0] if pos else info["lat"],
                    "lon": pos[1] if pos else info["lon"],
                    "field": f"nexrad_archive_ok_{sid}",
                    "dist_to_station": round(
                        haversine_km(pos[0], pos[1], info["lat"], info["lon"]), 1
                    )
                    if pos
                    else 0.0,
                    "files_found": len(files),
                    "s3_bucket": bucket_used,
                    "archive_ok": True,
                    "sample_volume_head": head,
                    "note": "Archive listed — null-return grid skipped for this station",
                }
            )
            station_scores[sid] = {
                "files_found": len(files),
                "s3_bucket": bucket_used,
                "mean_score": 1.0,
                "max_score": 1.0,
                "null_return": False,
                "sample_volume_head": head,
            }
            continue

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
                    anomalies.append(
                        {
                            "time": t,
                            "station": sid,
                            "sigma": round(score * 3, 2),
                            "score": score,
                            "lat": pos[0],
                            "lon": pos[1],
                            "field": f"nexrad_null_{sid}",
                            "dist_to_station": round(
                                haversine_km(pos[0], pos[1], info["lat"], info["lon"]), 1
                            ),
                            "files_found": 0,
                            "archive_ok": False,
                        }
                    )
                scores.append(score)
            t += interval

        station_scores[sid] = {
            "files_found": 0,
            "mean_score": round(float(np.mean(scores)), 3) if scores else 0,
            "max_score": round(float(np.max(scores)), 3) if scores else 0,
            "null_return": True,
        }

    return {
        "station_scores": station_scores,
        "anomalies": anomalies,
        "lens": "nexrad",
        "stations_checked": list(stations.keys()),
        "all_null": all(v.get("null_return") for v in station_scores.values()),
    }
