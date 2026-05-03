import os, sys, json, subprocess
from datetime import date, timedelta
import numpy as np

def pip(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)
pip("requests"); pip("numpy"); pip("matplotlib"); pip("scipy")

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

WORK_DIR  = r"C:\Users\Mike\uap_sniffer\uap_sniffer"
OUT_DIR   = os.path.join(WORK_DIR, "results", "null_distribution")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BG="#0c0e0f"; BG2="#131618"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"

HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
KP_URL    = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"

# ═══════════════════════════════════════════════════════════════════════
# PRE-REGISTERED PARAMETERS v3 -- frozen 2026-04-30
# Changes from v2:
#   - Window: 02:00-04:00 UTC (covers where TUC spike actually lands)
#   - Isolation metric: corridor_peak / MEAN_external (not max)
#   - Also test: fraction of external stations exceeding threshold
# ═══════════════════════════════════════════════════════════════════════
SIGMA_WINDOW     = 20
MIN_BASELINE_PTS = 15
SIGMA_THRESHOLD  = 2.0
KP_GATE          = 3.0
N_CONTROL        = 80
YEAR_RANGE       = 6

CORRIDOR     = ["TUC", "BOU"]
EXTERNAL     = ["SIT", "CMO", "FRD", "SJG", "HON", "BRW"]

EVENT_DATE   = date(1997, 3, 13)
EVENT_MONTH  = 3
EVENT_YEAR   = 1997

# Window covers 02:00-04:00 UTC with warmup from 01:30
# TUC spike falls at ~03:32 UTC -- fully inside window
FETCH_START  = "01:30"   # 30 min warmup before score window
SCORE_START  = "02:00"   # start scoring here
SCORE_END    = "04:00"   # stop scoring here

def load_kp():
    cache = os.path.join(CACHE_DIR, "kp_full.json")
    if os.path.exists(cache):
        print("  Kp: cached")
        return json.load(open(cache, encoding="utf-8"))
    print("  Downloading Kp...")
    r = requests.get(KP_URL, timeout=60)
    kp = {}
    for line in r.text.splitlines():
        if line.startswith("#") or len(line) < 20: continue
        p = line.split()
        if len(p) < 15: continue
        try:
            yr,mo,dy = int(p[0]),int(p[1]),int(p[2])
            vals = [float(p[i])/10.0 for i in range(7,15) if i<len(p)]
            kp[f"{yr:04d}-{mo:02d}-{dy:02d}"] = float(np.mean(vals))
        except: continue
    with open(cache,"w",encoding="utf-8") as f: json.dump(kp,f)
    return kp

def fetch_intermagnet(station, date_obj, start_h, end_h):
    ds  = date_obj.strftime("%Y-%m-%d")
    key = f"hapi_{station}_{ds}_{start_h.replace(':','')}_{end_h.replace(':','')}.json"
    cp  = os.path.join(CACHE_DIR, key)
    if os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            v = d.get("v"); ts = d.get("times_str", [])
            if v and len(v) > 5: return np.array(v), ts
        except: pass
    for data_type in ["definitive", "quasi-definitive", "variation"]:
        params = {
            "id":       f"{station}/{data_type}/PT1M/xyzf",
            "time.min": f"{ds}T{start_h}:00Z",
            "time.max": f"{ds}T{end_h}:00Z",
            "format":   "json",
        }
        try:
            r = requests.get(HAPI_BASE, params=params, timeout=25)
            if r.status_code != 200: continue
            rows = r.json().get("data", [])
            if not rows: continue
            vals = []; tstr = []
            for row in rows:
                try:
                    y = float(row[1][1])
                    vals.append(np.nan if abs(y) > 90000 else y)
                    tstr.append(str(row[0]))
                except:
                    vals.append(np.nan); tstr.append("")
            if sum(1 for v in vals if not np.isnan(v)) < 5: continue
            with open(cp,"w",encoding="utf-8") as f:
                json.dump({"v": vals, "times_str": tstr}, f)
            return np.array(vals), tstr
        except: continue
    return None, []

def in_score_window(t_str):
    try:
        h = int(t_str[11:13]); m = int(t_str[14:16])
        sh, sm = int(SCORE_START[:2]), int(SCORE_START[3:])
        eh, em = int(SCORE_END[:2]),   int(SCORE_END[3:])
        t_min = h*60+m; s_min = sh*60+sm; e_min = eh*60+em
        return s_min <= t_min <= e_min
    except: return False

def rolling_sigma_scored(vals, tstr):
    arr = np.array(vals, dtype=float)
    n   = len(arr)
    out = np.zeros(n)
    for i in range(n):
        w = arr[max(0, i-SIGMA_WINDOW):i]
        w = w[~np.isnan(w)]
        if len(w) < MIN_BASELINE_PTS: continue
        s = np.std(w)
        if s < 1e-6: continue
        if not np.isnan(arr[i]):
            out[i] = abs(arr[i] - np.mean(w)) / s
    # Zero outside score window
    return np.array([out[i] if in_score_window(tstr[i]) else 0.0
                     for i in range(n)])

def score_station(sid, date_obj):
    v, ts = fetch_intermagnet(sid, date_obj, FETCH_START, SCORE_END)
    if v is None or len(v) < 5: return None
    sig = rolling_sigma_scored(v, ts)
    # Extract only score-window values
    window_sigs = [sig[i] for i in range(len(ts)) if in_score_window(ts[i])]
    if not window_sigs: return None
    return np.array(window_sigs)

def corridor_metrics(date_obj):
    # Corridor
    csigs = {}
    for sid in CORRIDOR:
        s = score_station(sid, date_obj)
        if s is not None: csigs[sid] = s
    if len(csigs) < len(CORRIDOR): return None

    n = min(len(s) for s in csigs.values())

    # Minutes both corridor stations exceed threshold
    corridor_minutes = sum(
        1 for i in range(n)
        if all(csigs[sid][i] >= SIGMA_THRESHOLD for sid in csigs)
    )
    corridor_peak = max(float(np.max(s)) for s in csigs.values())
    corridor_mean = float(np.mean([np.mean(s) for s in csigs.values()]))

    # External
    ext_peaks = []; ext_means = []; ext_exceed_count = 0
    for sid in EXTERNAL:
        s = score_station(sid, date_obj)
        if s is None: continue
        ext_peaks.append(float(np.max(s)))
        ext_means.append(float(np.mean(s)))
        if np.max(s) >= SIGMA_THRESHOLD:
            ext_exceed_count += 1

    if len(ext_peaks) < 3: return None

    max_external  = max(ext_peaks)
    mean_external = float(np.mean(ext_means))   # KEY FIX: mean of means
    n_ext_exceed  = ext_exceed_count
    n_ext_total   = len(ext_peaks)

    # Isolation metrics
    # 1. Ratio using MEAN external (robust to single-station outliers)
    ratio_mean = (corridor_peak / mean_external
                  if mean_external > 0.01 else corridor_peak * 10)

    # 2. Fraction of external stations exceeding threshold
    frac_ext_exceed = n_ext_exceed / n_ext_total

    # 3. Classic isolation: corridor active AND all externals below threshold
    isolation_strict = corridor_minutes > 0 and max_external < SIGMA_THRESHOLD

    # 4. Soft isolation: corridor active AND mean external below threshold
    isolation_soft = corridor_minutes > 0 and mean_external < SIGMA_THRESHOLD

    return {
        "corridor_minutes":   corridor_minutes,
        "corridor_peak":      corridor_peak,
        "corridor_mean":      corridor_mean,
        "max_external":       max_external,
        "mean_external":      mean_external,
        "n_ext_exceed":       n_ext_exceed,
        "n_ext_total":        n_ext_total,
        "frac_ext_exceed":    frac_ext_exceed,
        "ratio_mean":         ratio_mean,
        "isolation_strict":   isolation_strict,
        "isolation_soft":     isolation_soft,
    }

def get_candidates(kp_index):
    candidates = []
    yr_lo = max(EVENT_YEAR - YEAR_RANGE, 1991)
    yr_hi = min(EVENT_YEAR + YEAR_RANGE, 2023)
    for yr in range(yr_lo, yr_hi+1):
        d = date(yr, EVENT_MONTH, 1)
        while d.month == EVENT_MONTH:
            if d != EVENT_DATE:
                ds = d.strftime("%Y-%m-%d")
                if kp_index.get(ds, 99.0) < KP_GATE:
                    candidates.append(d)
            d += timedelta(days=1)
    import random; random.seed(42); random.shuffle(candidates)
    return candidates

def main():
    print()
    print("=== Corridor Isolation Test v3 ===")
    print(f"  Score window:  {SCORE_START}-{SCORE_END} UTC")
    print(f"  Fetch window:  {FETCH_START}-{SCORE_END} UTC (warmup)")
    print(f"  Isolation metric: corridor_peak / MEAN_external (not max)")
    print(f"  Also testing: fraction of external stations exceeding 2s")
    print()

    kp_index = load_kp()

    print("  EVENT DAY metrics...")
    ev = corridor_metrics(EVENT_DATE)
    if ev is None:
        print("  ERROR"); input("Press Enter..."); return

    print(f"    Corridor minutes (both >= 2s):  {ev['corridor_minutes']}")
    print(f"    Corridor peak sigma:            {ev['corridor_peak']:.3f}")
    print(f"    Max external sigma:             {ev['max_external']:.3f}")
    print(f"    Mean external sigma:            {ev['mean_external']:.3f}")
    print(f"    External stations exceeding 2s: {ev['n_ext_exceed']}/{ev['n_ext_total']}")
    print(f"    Ratio (corridor/mean_ext):      {ev['ratio_mean']:.3f}")
    print(f"    Isolation strict:               {ev['isolation_strict']}")
    print(f"    Isolation soft:                 {ev['isolation_soft']}")

    print()
    print(f"  Building null ({N_CONTROL} controls)...")
    candidates = get_candidates(kp_index)

    null = {k: [] for k in ["corridor_minutes","corridor_peak","max_external",
                              "mean_external","frac_ext_exceed","ratio_mean",
                              "isolation_strict","isolation_soft"]}
    failed = 0
    for cdate in candidates:
        if len(null["corridor_minutes"]) >= N_CONTROL: break
        m = corridor_metrics(cdate)
        if m is None: failed += 1; continue
        for k in null: null[k].append(m[k])
        if len(null["corridor_minutes"]) % 20 == 0:
            print(f"  {len(null['corridor_minutes'])} controls...")

    n_ctrl = len(null["corridor_minutes"])
    print(f"  Final: {n_ctrl} controls ({failed} failed)")
    if n_ctrl < 10:
        print("  Not enough data"); input("Press Enter..."); return

    def pct(nd, obs): return float(stats.percentileofscore(np.array(nd), obs))
    def zs(nd, obs):
        a = np.array(nd)
        return float((obs-np.mean(a))/np.std(a)) if np.std(a)>0 else 0.0

    print()
    print("=" * 72)
    print("  RESULTS -- ALL METRICS")
    print("=" * 72)
    print(f"  {'Metric':<28} {'Obs':>7} {'Mean':>7} {'p95':>7} {'Pct':>7} {'z':>6}")
    print(f"  {'─'*66}")

    continuous = [
        ("corridor_minutes",  ev["corridor_minutes"]),
        ("corridor_peak",     ev["corridor_peak"]),
        ("max_external",      ev["max_external"]),
        ("mean_external",     ev["mean_external"]),
        ("frac_ext_exceed",   ev["frac_ext_exceed"]),
        ("ratio_mean",        ev["ratio_mean"]),
    ]
    for mname, obs in continuous:
        nd  = null[mname]
        p   = pct(nd, obs)
        z   = zs(nd, obs)
        p95 = np.percentile(nd, 95)
        flag = " ***" if p >= 95 or p <= 5 else ""
        print(f"  {mname:<28} {obs:>7.3f} {np.mean(nd):>7.3f} "
              f"{p95:>7.3f} {p:>7.1f} {z:>6.2f}{flag}")

    print()
    strict_rate = float(np.mean(null["isolation_strict"])) * 100
    soft_rate   = float(np.mean(null["isolation_soft"]))   * 100
    print(f"  Strict isolation in controls: "
          f"{int(np.sum(null['isolation_strict']))}/{n_ctrl} ({strict_rate:.1f}%)")
    print(f"  Soft isolation in controls:   "
          f"{int(np.sum(null['isolation_soft']))}/{n_ctrl} ({soft_rate:.1f}%)")
    print(f"  Phoenix strict isolation: {ev['isolation_strict']}")
    print(f"  Phoenix soft isolation:   {ev['isolation_soft']}")

    # Plot -- 6 panels
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), facecolor=BG)
    fig.subplots_adjust(hspace=0.45, wspace=0.35)
    axes = axes.flatten()

    plot_items = [
        ("Corridor minutes\n(both TUC+BOU >= 2s)",
         null["corridor_minutes"], ev["corridor_minutes"]),
        ("Corridor peak sigma",
         null["corridor_peak"], ev["corridor_peak"]),
        ("Mean external sigma\n(mean across 6 stations)",
         null["mean_external"], ev["mean_external"]),
        ("Max external sigma",
         null["max_external"], ev["max_external"]),
        ("Frac external stations\nexceeding 2s threshold",
         null["frac_ext_exceed"], ev["frac_ext_exceed"]),
        ("Isolation ratio\n(corridor peak / mean ext)",
         null["ratio_mean"], ev["ratio_mean"]),
    ]
    for ax, (title, nd, obs) in zip(axes, plot_items):
        ax.set_facecolor(BG2)
        ax.tick_params(colors=DIM, labelsize=7)
        for sp in ax.spines.values(): sp.set_color("#252a2e")
        nd_arr = np.array(nd)
        n_bins = min(25, len(nd_arr)//2)
        ax.hist(nd_arr, bins=n_bins, color=BLU, alpha=0.65,
               edgecolor=BG, lw=0.3, label=f"n={len(nd_arr)}")
        p95 = np.percentile(nd_arr, 95)
        ax.axvline(p95, color=ORG, lw=0.9, ls="--", alpha=0.7,
                  label=f"95th ({p95:.2f})")
        p = pct(nd, obs)
        flag = " ***" if p >= 95 or p <= 5 else ""
        ax.axvline(obs, color=RED, lw=2.5, zorder=6,
                  label=f"Phoenix: {obs:.2f} ({p:.0f}th){flag}")
        ax.set_title(title, color=TC, fontsize=8, pad=5)
        ax.set_xlabel("Value", color=TC, fontsize=7)
        ax.set_ylabel("Count", color=TC, fontsize=7)
        ax.legend(fontsize=6, facecolor=BG2, edgecolor="#252a2e",
                 labelcolor=TC, loc="upper right")

    fig.suptitle(
        f"Corridor Isolation v3 — {SCORE_START}-{SCORE_END} UTC | "
        f"n={n_ctrl} controls | Kp<{KP_GATE}\n"
        "Metric: corridor_peak / MEAN_external | *** = beyond 95th/5th pct",
        color=TC, fontsize=9, y=1.02)

    png = os.path.join(OUT_DIR, "corridor_isolation_v3.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"\n  Plot: {png}")

    result = {
        "version": "v3",
        "window": f"{SCORE_START}-{SCORE_END} UTC",
        "event_metrics": ev,
        "null_n": n_ctrl,
        "percentiles": {m[0]: pct(null[m[0]], m[1]) for m in continuous},
        "isolation_strict_rate_pct": strict_rate,
        "isolation_soft_rate_pct":   soft_rate,
    }
    jp = os.path.join(OUT_DIR, "corridor_isolation_v3.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  JSON: {jp}")
    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
