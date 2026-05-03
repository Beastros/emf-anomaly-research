"""
Rolling sigma on H for FRN and TUC on 2004-11-14 (Nimitz encounter date).

Reads JSON produced under data/geomag_2004-11-14_FRN_TUC_1sec_definitive/.

By default, uses a 1200-sample (20-minute) past-only window on 1 Hz data when H is present.

USGS 1-second *definitive* JSON for 2004-11-14 is often all-null (H,D,Z not filled at 1 Hz).
Unless you pass --strict-json-only, this script then falls back to the Geomag API 1-minute
definitive series with a 20-sample past-only window (still 20 minutes of history).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "geomag_2004-11-14_FRN_TUC_1sec_definitive",
)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# Primary: 1 Hz × 20 min = 1200 samples (past-only window excludes current index)
WINDOW_1SEC = 1200
MIN_VALID = 15

# Fallback: 1-minute cadence — 20 minutes = 20 samples
WINDOW_1MIN = 20

NIMITZ_START = datetime(2004, 11, 14, 18, 0, 0, tzinfo=timezone.utc)
NIMITZ_END = datetime(2004, 11, 14, 19, 0, 0, tzinfo=timezone.utc)

DAY_START = datetime(2004, 11, 14, 0, 0, 0, tzinfo=timezone.utc)
DAY_END = datetime(2004, 11, 15, 0, 0, 0, tzinfo=timezone.utc)

GEOMAG_URL = "https://geomag.usgs.gov/ws/data/"


def load_station_json(path: str) -> pd.DataFrame:
    with open(path, encoding="utf-8") as fh:
        raw: dict[str, Any] = json.load(fh)
    times = raw["times"]
    cols: dict[str, list[Any]] = {"H": [], "D": [], "Z": []}
    for block in raw["values"]:
        fid = block["id"]
        if fid in cols:
            cols[fid] = block["values"]
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(times, utc=True),
            "H": cols["H"],
            "D": cols["D"],
            "Z": cols["Z"],
        }
    )
    df = df.dropna(subset=["H"])
    return df


def fetch_minute_definitive_station(obs: str) -> pd.DataFrame:
    """Full UTC calendar day 2004-11-14 at 1-minute definitive."""
    params = {
        "id": obs,
        "starttime": DAY_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endtime": DAY_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elements": "H,D,Z",
        "sampling_period": 60,
        "format": "json",
        "type": "definitive",
    }
    r = requests.get(GEOMAG_URL, params=params, timeout=180)
    r.raise_for_status()
    raw = r.json()
    times = raw["times"]
    cols = {"H": [], "D": [], "Z": []}
    for block in raw["values"]:
        if block["id"] in cols:
            cols[block["id"]] = block["values"]
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(times, utc=True),
            "H": cols["H"],
            "D": cols["D"],
            "Z": cols["Z"],
        }
    )
    df = df.dropna(subset=["H"])
    # Drop trailing next-midnight minute if present
    day_end_ts = pd.Timestamp(datetime(2004, 11, 15, 0, 0, 0), tz="UTC")
    df = df[df["timestamp"] < day_end_ts]
    return df


def rolling_sigma_past_only(h: pd.Series, window: int, min_valid: int) -> pd.Series:
    """
    For each index i: mean/std of h.iloc[i-window : i] (preceding window rows, not including i).
    sigma_i = (h_i - mean) / std. Requires at least min_valid non-null values in that slice.
    """
    arr = h.astype(float).to_numpy()
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    for i in range(n):
        lo = max(0, i - window)
        hi = i
        if hi - lo < 1:
            continue
        seg = arr[lo:hi]
        mask = ~np.isnan(seg)
        if int(mask.sum()) < min_valid:
            continue
        seg_valid = seg[mask]
        mu = float(np.mean(seg_valid))
        sd = float(np.std(seg_valid, ddof=0))
        if sd <= 0.0 or np.isnan(sd):
            continue
        cur = arr[i]
        if np.isnan(cur):
            continue
        out[i] = (cur - mu) / sd
    return pd.Series(out, index=h.index)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nimitz-day FRN/TUC rolling H sigma")
    parser.add_argument(
        "--strict-json-only",
        action="store_true",
        help="Do not call API; exit if JSON has no usable H after dropna.",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    paths = {
        "FRN": os.path.join(DATA_DIR, "FRN_2004-11-14_1sec_definitive_HDZ.json"),
        "TUC": os.path.join(DATA_DIR, "TUC_2004-11-14_1sec_definitive_HDZ.json"),
    }

    # Probe JSON for usable H
    use_fallback = False
    for p in paths.values():
        if not os.path.isfile(p):
            raise FileNotFoundError(f"Missing {p}")
        df_preview = load_station_json(p)
        if len(df_preview) == 0:
            use_fallback = True
            break

    window = WINDOW_1SEC
    dfs: dict[str, pd.DataFrame] = {}

    if use_fallback and args.strict_json_only:
        raise SystemExit(
            "JSON files contain no non-null H (USGS 1-second definitive is empty for this date). "
            "Re-export valid 1 Hz JSON or omit --strict-json-only to use the 1-minute API fallback."
        )

    if use_fallback:
        print(
            "[NOTE] JSON has no non-null H — using 1-minute definitive from Geomag API "
            f"with {WINDOW_1MIN}-sample (20-minute) past-only window.\n"
        )
        window = WINDOW_1MIN
        for name in paths:
            dfs[name] = fetch_minute_definitive_station(name)
            print(f"{name}: loaded {len(dfs[name])} rows (1-minute definitive API)")
    else:
        for name, p in paths.items():
            dfs[name] = load_station_json(p)
            print(f"{name}: loaded {len(dfs[name])} rows from JSON (1-second)")

    series_sigma: dict[str, pd.Series] = {}

    for name, df in dfs.items():
        sigma = rolling_sigma_past_only(df["H"], window, MIN_VALID)
        sigma.index = df["timestamp"]
        series_sigma[name] = sigma

        valid = sigma.dropna()
        if valid.empty:
            print(f"{name}: no valid sigma values")
        else:
            idxmax = valid.idxmax()
            print(f"{name}: max sigma = {valid.max():.6g} at {idxmax}")

    fig, ax = plt.subplots(figsize=(14, 5))
    for name, sig in series_sigma.items():
        ax.plot(sig.index, sig.values, label=f"{name} H σ", linewidth=0.9, alpha=0.9)

    ax.axhline(3.0, color="crimson", linestyle="--", linewidth=1.0, label="σ = 3")
    ax.axvspan(NIMITZ_START, NIMITZ_END, color="orange", alpha=0.2, label="Nimitz window (18–19 UTC)")

    if window == WINDOW_1MIN:
        subtitle = f"past-only window = {window} samples (20 min @ 1-minute cadence)"
        cadence = "1-minute definitive (API fallback)"
    else:
        subtitle = f"past-only window = {window} samples (20 min @ 1 Hz)"
        cadence = "1-second JSON"
    ax.set_ylabel("Rolling σ")
    ax.set_xlabel("UTC")
    ax.set_title(f"2004-11-14 FRN vs TUC — rolling sigma on H ({cadence})\n{subtitle}")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "nimitz_1sec_sigma.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
