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
import matplotlib.gridspec as gridspec
from scipy import stats

WORK_DIR  = os.path.dirname(os.path.abspath(__file__))
OUT_DIR   = os.path.join(WORK_DIR, "results", "null_distribution")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache")
os.makedirs(OUT_DIR,   exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BG="#0c0e0f"; BG2="#131618"; BG3="#1a1e21"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"; PRP="#c47ec4"

# ── Events ────────────────────────────────────────────────────────────────────
EVENTS = [
    {"name": "Phoenix Lights", "date": date(1997,  3, 13),
     "sta_a": "TUC", "sta_b": "BOU",
     "start": "01:00", "end": "05:00",
     "r_obs": 0.9704, "lag_obs": -1, "kp": 2.0, "color": RED},
    {"name": "USS Nimitz",     "date": date(2004, 11, 14),
     "sta_a": "TUC", "sta_b": "BOU",
     "start": "01:00", "end": "05:00",
     "r_obs": 0.978,  "lag_obs":  0, "kp": 1.333, "color": ORG},
    {"name": "O'Hare Airport", "date": date(2006, 11,  7),
     "sta_a": "FRD", "sta_b": "BOU",
     "start": "14:00", "end": "20:00",
     "r_obs": 0.9796, "lag_obs": -21, "kp": 0.0, "color": PRP},
]

# Phoenix + Nimitz share TUC-BOU null
NULL_CONFIGS = [
    {"pair": ("TUC","BOU"), "month": 3,  "year_ref": 1997,
     "start": "01:00", "end": "05:00",
     "events": ["Phoenix Lights", "USS Nimitz"]},
    {"pair": ("FRD","BOU"), "month": 11, "year_ref": 2006,
     "start": "14:00", "end": "20:00",
     "events": ["O'Hare Airport"]},
]

N_CONTROL = 80
KP_GATE   = 3.0
HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
KP_URL    = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"

# ── Kp loader ─────────────────────────────────────────────────────────────────
def load_kp():
    cache = os.path.join(CACHE_DIR, "kp_full.json")
    if os.path.exists(cache):
        print("  Kp index: cached")
        return json.load(open(cache, encoding="utf-8"))
    print("  Downloading GFZ Kp archive...")
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
    print(f"  Loaded {len(kp)} days")
    return kp

# ── INTERMAGNET HAPI fetcher ───────────────────────────────────────────────────
def fetch_intermagnet(station, date_obj, start_h, end_h):
    """
    Fetch from INTERMAGNET HAPI -- this is where 1990s data actually lives.
    Row format confirmed: [timestamp, [x, y, z], f]
    Y component (index 1 of the xyz list) = east/D component
    """
    ds  = date_obj.strftime("%Y-%m-%d")
    key = f"hapi_{station}_{ds}_{start_h.replace(':','')}_{end_h.replace(':','')}.json"
    cp  = os.path.join(CACHE_DIR, key)

    if os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            v = d.get("v")
            if v and len(v) > 5:
                return np.array(v)
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
            d = r.json()
            rows = d.get("data", [])
            if not rows: continue

            vals = []
            for row in rows:
                try:
                    xyz = row[1]           # confirmed: row[1] = [x, y, z]
                    y   = float(xyz[1])    # Y = east = D component
                    if abs(y) < 90000:
                        vals.append(y)
                    else:
                        vals.append(np.nan)
                except: vals.append(np.nan)

            valid = [v for v in vals if not np.isnan(v)]
            if len(valid) < 10: continue

            with open(cp, "w", encoding="utf-8") as f:
                json.dump({"v": vals, "source": data_type}, f)
            return np.array(vals)

        except Exception: continue

    return None

# ── r and lag ─────────────────────────────────────────────────────────────────
def compute_r_and_lag(a, b, max_lag=30):
    if a is None or b is None: return None, None
    n = min(len(a), len(b))
    if n < 15: return None, None
    a, b = a[:n], b[:n]
    mask = ~(np.isnan(a) | np.isnan(b))
    if mask.sum() < 15: return None, None
    a, b = a[mask], b[mask]
    a = a - np.mean(a)
    b = b - np.mean(b)

    best_r, best_lag = -2.0, 0
    max_lag = min(max_lag, len(a)//4)
    for lag in range(-max_lag, max_lag+1):
        if lag < 0:   aa, bb = a[-lag:], b[:lag]
        elif lag > 0: aa, bb = a[:-lag], b[lag:]
        else:         aa, bb = a, b
        if len(aa) < 10: continue
        try:
            r, _ = stats.pearsonr(aa, bb)
            if r > best_r:
                best_r, best_lag = r, lag
        except: continue

    return float(best_r), int(best_lag)

# ── Control day candidates ────────────────────────────────────────────────────
def get_candidates(month, year_ref, kp_index, exclude):
    candidates = []
    yr_lo = max(year_ref - 6, 1991)
    yr_hi = min(year_ref + 6, 2023)
    for yr in range(yr_lo, yr_hi+1):
        d = date(yr, month, 1)
        while d.month == month:
            if d not in exclude:
                ds = d.strftime("%Y-%m-%d")
                kp = kp_index.get(ds, 99.0)
                if kp < KP_GATE:
                    candidates.append(d)
            d += timedelta(days=1)
    np.random.seed(42)
    np.random.shuffle(candidates)
    return candidates

# ── Run null for one pair ─────────────────────────────────────────────────────
def run_null(cfg, kp_index, ev_by_name):
    sta_a, sta_b = cfg["pair"]
    start, end   = cfg["start"], cfg["end"]
    ev_names     = cfg["events"]

    print(f"\n  Pair: {sta_a}-{sta_b}  |  Window: {start}-{end} UTC")
    print(f"  Events: {ev_names}")

    exclude = {ev_by_name[n]["date"] for n in ev_names}
    candidates = get_candidates(cfg["month"], cfg["year_ref"], kp_index, exclude)
    print(f"  Candidates: {len(candidates)}")
    print(f"  Downloading via INTERMAGNET HAPI...")

    null_r, null_lag = [], []
    failed = 0
    for cdate in candidates:
        if len(null_r) >= N_CONTROL: break
        a = fetch_intermagnet(sta_a, cdate, start, end)
        b = fetch_intermagnet(sta_b, cdate, start, end)
        r, lag = compute_r_and_lag(a, b)
        if r is not None:
            null_r.append(r)
            null_lag.append(lag)
            if len(null_r) % 20 == 0:
                print(f"  Collected {len(null_r)} control days...")
        else:
            failed += 1

    print(f"  Final: {len(null_r)} control days ({failed} failed)")

    if len(null_r) < 10:
        print(f"  ERROR: Not enough control data. Check INTERMAGNET access.")
        return None

    # Event values
    ev_results = []
    for name in ev_names:
        ev = ev_by_name[name]
        a = fetch_intermagnet(sta_a, ev["date"], start, end)
        b = fetch_intermagnet(sta_b, ev["date"], start, end)
        r, lag = compute_r_and_lag(a, b)
        if r is None:
            r, lag = ev["r_obs"], ev["lag_obs"]
            print(f"  {name}: using reported r={r}, lag={lag} (INTERMAGNET returned no data)")
        else:
            print(f"  {name}: r={r:.4f}, lag={lag} min")

        null_arr = np.array(null_r)
        pct_r = float(stats.percentileofscore(null_arr, r))
        z_r   = (r - np.mean(null_arr)) / np.std(null_arr) if np.std(null_arr) > 0 else 0

        # Joint: fraction of control days with r >= obs AND |lag| <= |obs_lag|
        joint_count = np.sum(
            (null_arr >= r) &
            (np.abs(np.array(null_lag)) <= max(1, abs(lag)))
        )
        joint_pct = 100 - (joint_count / len(null_arr) * 100)

        print(f"    r percentile: {pct_r:.1f}th  z={z_r:.2f}  joint pct: {joint_pct:.1f}th")

        ev_results.append({
            "name": name, "r": r, "lag": lag,
            "pct_r": pct_r, "z_r": z_r,
            "joint_pct": joint_pct,
            "color": ev["color"],
        })

    return {
        "pair": f"{sta_a}-{sta_b}",
        "null_r": null_r, "null_lag": null_lag,
        "ev_results": ev_results,
        "n_control": len(null_r),
    }

# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plot(null_results):
    n = len([nr for nr in null_results if nr])
    if n == 0: return

    fig = plt.figure(figsize=(7*n + 2, 10), facecolor=BG)
    gs  = gridspec.GridSpec(2, n, hspace=0.45, wspace=0.35)

    for col, nr in enumerate([x for x in null_results if x]):
        null_r   = np.array(nr["null_r"])
        null_lag = np.array(nr["null_lag"])
        pair     = nr["pair"]
        evs      = nr["ev_results"]
        p95      = np.percentile(null_r, 95)
        p99      = np.percentile(null_r, 99)

        # TOP: histogram
        ax1 = fig.add_subplot(gs[0, col])
        ax1.set_facecolor(BG2)
        ax1.tick_params(colors=DIM, labelsize=8)
        for sp in ax1.spines.values(): sp.set_color("#252a2e")

        n_bins = min(35, len(null_r)//2)
        ax1.hist(null_r, bins=n_bins, color=BLU, alpha=0.6,
                edgecolor=BG, linewidth=0.4, label=f"Control days (n={len(null_r)})")

        try:
            kde_x = np.linspace(null_r.min()-0.02, 1.01, 300)
            kde_y = stats.gaussian_kde(null_r)(kde_x)
            scale = len(null_r) * (null_r.max()-null_r.min()) / n_bins
            ax1.plot(kde_x, kde_y * scale, color=BLU, lw=1.5, alpha=0.8)
        except: pass

        ax1.axvline(p95, color=ORG, lw=1.0, ls="--", alpha=0.7,
                   label=f"95th pct ({p95:.3f})")
        ax1.axvline(p99, color=GRN, lw=1.0, ls=":",  alpha=0.7,
                   label=f"99th pct ({p99:.3f})")

        for ev in evs:
            ax1.axvline(ev["r"], color=ev["color"], lw=2.5, zorder=6,
                       label=f"{ev['name']}\nr={ev['r']:.4f} ({ev['pct_r']:.0f}th pct)")

        ax1.set_xlabel("Pearson r (D-component, at best lag)", color=TC, fontsize=9)
        ax1.set_ylabel("Count", color=TC, fontsize=9)
        ax1.set_title(
            f"{pair} — r distribution\n"
            f"n={len(null_r)} control days, same month, Kp < 3.0, INTERMAGNET HAPI",
            color=TC, fontsize=9, pad=8)
        ax1.legend(fontsize=6.5, facecolor=BG2, edgecolor="#252a2e",
                  labelcolor=TC, loc="upper left")

        # BOTTOM: joint scatter
        ax2 = fig.add_subplot(gs[1, col])
        ax2.set_facecolor(BG2)
        ax2.tick_params(colors=DIM, labelsize=7)
        for sp in ax2.spines.values(): sp.set_color("#252a2e")

        ax2.scatter(np.abs(null_lag), null_r,
                   c=BLU, s=18, alpha=0.45, edgecolors="none",
                   label="Control days", zorder=2)

        for ev in evs:
            ax2.scatter(abs(ev["lag"]), ev["r"],
                       c=ev["color"], s=200, marker="*", zorder=6,
                       edgecolors="white", linewidths=0.5,
                       label=f"{ev['name']}\nr={ev['r']:.4f}, lag={ev['lag']}min\njoint {ev['joint_pct']:.0f}th pct")

        # Shade extreme zone
        ax2.fill_between([0, 3], [p99, p99], [1.05, 1.05],
                        alpha=0.08, color=RED)
        ax2.text(1.5, (p99 + 1.0) / 2,
                "extreme\nzone", ha="center", va="center",
                fontsize=6, color=RED, alpha=0.6)

        ax2.set_xlabel("|Lag at peak r| (minutes)", color=TC, fontsize=9)
        ax2.set_ylabel("Pearson r at best lag", color=TC, fontsize=9)
        ax2.set_title(
            f"{pair} — Joint test: r vs |lag|\n"
            f"Stars = event days. Upper-left = high r + near-zero lag.",
            color=TC, fontsize=9, pad=8)
        ax2.legend(fontsize=6.5, facecolor=BG2, edgecolor="#252a2e",
                  labelcolor=TC, loc="lower right")

    fig.suptitle(
        "Null Distribution Analysis — Are Event-Day Correlations Statistically Unusual?\n"
        f"Control days: matched month, Kp < 3.0, ±6 years. Source: INTERMAGNET HAPI.\n"
        "Bottom row: joint test — high r AND near-zero lag simultaneously.",
        color=TC, fontsize=10, y=1.02)

    png = os.path.join(OUT_DIR, "null_distribution.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"\n  Plot saved: {png}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=== Null Distribution Analysis v3 ===")
    print("  Using INTERMAGNET HAPI (where 1990s data actually lives)")
    print("  Tests r AND lag jointly against matched control days")
    print()

    kp_index = load_kp()
    if not kp_index:
        print("ERROR: Kp download failed")
        input("Press Enter..."); sys.exit(1)

    ev_by_name = {ev["name"]: ev for ev in EVENTS}
    null_results = []

    for cfg in NULL_CONFIGS:
        nr = run_null(cfg, kp_index, ev_by_name)
        null_results.append(nr)

    print()
    print("=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(f"  {'Event':<22} {'r':>7} {'lag':>6} {'r pct':>7} {'z':>6} {'joint pct':>10}")
    print(f"  {'─'*62}")
    for nr in null_results:
        if not nr: continue
        for ev in nr["ev_results"]:
            print(f"  {ev['name']:<22} {ev['r']:>7.4f} "
                  f"{ev['lag']:>5}m {ev['pct_r']:>7.1f} "
                  f"{ev['z_r']:>6.2f} {ev['joint_pct']:>10.1f}")

    print()
    print("  Interpretation:")
    print("  r pct >= 99     --> event-day r is rare vs matched controls")
    print("  joint pct >= 99 --> high r + near-zero lag TOGETHER is rare")
    print("  Both true       --> finding survives the null distribution test")

    make_plot(null_results)

    # Save JSON
    clean = []
    for nr in null_results:
        if not nr: continue
        clean.append({k:v for k,v in nr.items() if k not in ("null_r","null_lag")})
    jp = os.path.join(OUT_DIR, "null_results.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"  JSON: {jp}")
    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
