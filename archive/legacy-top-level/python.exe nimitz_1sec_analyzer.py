import json
import shutil
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── 1. Move files to project data folder ──────────────────────────────────────
SRC_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer\data\geomag_2004-11-14_FRN_TUC_1sec_definitive"
DST_DIR = r"C:\Users\Mike\uap_sniffer\uap_sniffer\data\nimitz_1sec"
os.makedirs(DST_DIR, exist_ok=True)

for fname in ["FRN_2004-11-14_1sec_definitive_HDZ.json",
              "TUC_2004-11-14_1sec_definitive_HDZ.json"]:
    src = os.path.join(SRC_DIR, fname)
    dst = os.path.join(DST_DIR, fname)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f"Copied {fname}")
    else:
        print(f"Skipped {fname} (already exists or source missing)")

# ── 2. Parse JSON format ───────────────────────────────────────────────────────
def load_json_station(filepath):
    with open(filepath) as f:
        d = json.load(f)
    times = pd.to_datetime(d["times"])
    channels = {ch["id"]: ch["values"] for ch in d["values"]}
    df = pd.DataFrame({"timestamp": times})
    for ch_name, vals in channels.items():
        df[ch_name] = pd.array(vals, dtype="Float64")
    df.set_index("timestamp", inplace=True)
    return df

# ── 3. Rolling sigma (past-only, 20-min window = 1200 samples) ────────────────
def rolling_sigma(series, window=1200, min_periods=15):
    roll = series.rolling(window=window, min_periods=min_periods)
    mu = roll.mean()
    sd = roll.std()
    return (series - mu) / sd

# ── 4. Load stations ───────────────────────────────────────────────────────────
stations = {
    "FRN": os.path.join(DST_DIR, "FRN_2004-11-14_1sec_definitive_HDZ.json"),
    "TUC": os.path.join(DST_DIR, "TUC_2004-11-14_1sec_definitive_HDZ.json"),
}

results = {}
for name, path in stations.items():
    df = load_json_station(path)
    if "H" not in df.columns:
        print(f"{name}: no H channel found, skipping")
        continue
    df["sigma"] = rolling_sigma(df["H"].astype(float))
    results[name] = df
    peak = df["sigma"].abs().max()
    peak_time = df["sigma"].abs().idxmax()
    print(f"{name} | peak |sigma| = {peak:.3f} at {peak_time}")

# ── 5. Plot ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5))

colors = {"FRN": "steelblue", "TUC": "darkorange"}
for name, df in results.items():
    ax.plot(df.index, df["sigma"], label=name, color=colors[name], lw=0.6, alpha=0.8)

# Nimitz UAP window 18:00-19:00 UTC
ax.axvspan(pd.Timestamp("2004-11-14 18:00:00"),
           pd.Timestamp("2004-11-14 19:00:00"),
           color="red", alpha=0.15, label="UAP window (18-19 UTC)")

ax.axhline(3,  color="red", lw=0.8, ls="--", label="+3σ")
ax.axhline(-3, color="red", lw=0.8, ls="--")

ax.set_title("Nimitz 2004-11-14 | 1-second rolling sigma (H component, 20-min window)")
ax.set_xlabel("UTC")
ax.set_ylabel("sigma")
ax.legend()
ax.grid(True, alpha=0.3)

OUT = r"C:\Users\Mike\uap_sniffer\uap_sniffer\outputs\nimitz_1sec_sigma.png"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
plt.tight_layout()
plt.savefig(OUT, dpi=150)
print(f"Saved → {OUT}")
plt.show()