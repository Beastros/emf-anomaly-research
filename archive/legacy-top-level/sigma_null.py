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

WORK_DIR  = r"C:\Users\Mike\uap_sniffer\uap_sniffer"
OUT_DIR   = os.path.join(WORK_DIR, "results", "null_distribution")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BG="#0c0e0f"; BG2="#131618"; BG3="#1a1e21"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"; PRP="#c47ec4"

HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
KP_URL    = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"

# ═══════════════════════════════════════════════════════════════════════
# PRE-REGISTERED PARAMETERS v2 -- frozen 2026-04-30
# Change from v1: added MIN_BASELINE_POINTS to fix warmup artifact
# ═══════════════════════════════════════════════════════════════════════
SIGMA_BASELINE_WINDOW = 20    # minutes, past-only
MIN_BASELINE_POINTS   = 15    # don't score until this many points behind us
                               # FIX: v1 was scoring at minute 5 with 5 pts,
                               # producing artifactual 43-sigma spikes
SIGMA_THRESHOLD       = 2.0
COEXCEED_LAG_WINDOW   = 10
KP_GATE               = 3.0
N_CONTROL             = 80
YEAR_RANGE            = 6

EVENTS = [
    {
        "name": "Phoenix Lights", "role": "DEVELOPMENT",
        "date": date(1997, 3, 13),
        "sta_a": "TUC", "sta_b": "BOU",
        "start": "01:00", "end": "05:00",
        "kp": 2.0, "color": RED,
        "sighting_minute": 148,
    },
    {
        "name": "USS Nimitz", "role": "SECONDARY",
        "date": date(2004, 11, 14),
        "sta_a": "TUC", "sta_b": "BOU",
        "start": "01:00", "end": "05:00",
        "kp": 1.333, "color": ORG,
        "sighting_minute": None,
    },
    {
        "name": "O'Hare Airport", "role": "HELD-OUT BLIND TEST",
        "date": date(2006, 11, 7),
        "sta_a": "FRD", "sta_b": "BOU",
        "start": "14:00", "end": "20:00",
        "kp": 0.0, "color": PRP,
        "sighting_minute": 210,
    },
]

# ── Kp ────────────────────────────────────────────────────────────────────────
def load_kp():
    cache = os.path.join(CACHE_DIR, "kp_full.json")
    if os.path.exists(cache):
        print("  Kp: cached"); return json.load(open(cache, encoding="utf-8"))
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
    print(f"  Kp: {len(kp)} days"); return kp

# ── INTERMAGNET fetcher ───────────────────────────────────────────────────────
def fetch_intermagnet(station, date_obj, start_h, end_h):
    ds  = date_obj.strftime("%Y-%m-%d")
    key = f"hapi_{station}_{ds}_{start_h.replace(':','')}_{end_h.replace(':','')}.json"
    cp  = os.path.join(CACHE_DIR, key)
    if os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            v = d.get("v")
            if v and len(v) > 5: return np.array(v)
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
            vals = []
            for row in rows:
                try:
                    y = float(row[1][1])
                    vals.append(np.nan if abs(y) > 90000 else y)
                except: vals.append(np.nan)
            if sum(1 for v in vals if not np.isnan(v)) < 10: continue
            with open(cp,"w",encoding="utf-8") as f:
                json.dump({"v": vals, "src": data_type}, f)
            return np.array(vals)
        except: continue
    return None

# ── Rolling sigma (past-only, with warmup guard) ──────────────────────────────
def rolling_sigma(vals):
    """
    Scores each point against the past SIGMA_BASELINE_WINDOW points.
    Returns 0 for the first MIN_BASELINE_POINTS minutes -- warmup period.
    This prevents artifactual high sigmas when the window has only 2-3 points.
    """
    arr = np.array(vals, dtype=float)
    out = np.zeros(len(arr))
    for i in range(len(arr)):
        window = arr[max(0, i - SIGMA_BASELINE_WINDOW):i]
        window = window[~np.isnan(window)]
        # Warmup guard -- require minimum points before scoring
        if len(window) < MIN_BASELINE_POINTS:
            out[i] = 0.0
            continue
        s = np.std(window)
        if s < 1e-6: continue
        if not np.isnan(arr[i]):
            out[i] = abs(arr[i] - np.mean(window)) / s
    return out

# ── Metrics ───────────────────────────────────────────────────────────────────
def compute_metrics(vals_a, vals_b):
    if vals_a is None or vals_b is None: return None
    n = min(len(vals_a), len(vals_b))
    if n < 30: return None
    a, b = vals_a[:n], vals_b[:n]
    if np.sum(~np.isnan(a)) < 20 or np.sum(~np.isnan(b)) < 20: return None

    sig_a = rolling_sigma(a)
    sig_b = rolling_sigma(b)

    m1 = float(np.max(sig_a))
    m2 = float(np.max(sig_b))

    lag = COEXCEED_LAG_WINDOW
    thresh = SIGMA_THRESHOLD
    coexceed = 0
    for i in range(n):
        if sig_a[i] >= thresh:
            lo = max(0, i - lag); hi = min(n, i + lag + 1)
            if np.any(sig_b[lo:hi] >= thresh):
                coexceed += 1

    return {"peak_sigma_a": m1, "peak_sigma_b": m2,
            "coexceed_count": coexceed, "sig_a": sig_a, "sig_b": sig_b}

def spike_timing_metric(sig_a, sighting_minute):
    if sighting_minute is None: return None
    spikes = np.where(sig_a >= SIGMA_THRESHOLD)[0]
    if len(spikes) == 0: return None
    return int(np.min(np.abs(spikes - sighting_minute)))

# ── Control days ──────────────────────────────────────────────────────────────
def get_candidates(month, year_ref, kp_index, exclude):
    candidates = []
    yr_lo = max(year_ref - YEAR_RANGE, 1991)
    yr_hi = min(year_ref + YEAR_RANGE, 2023)
    for yr in range(yr_lo, yr_hi+1):
        d = date(yr, month, 1)
        while d.month == month:
            if d not in exclude:
                ds = d.strftime("%Y-%m-%d")
                if kp_index.get(ds, 99.0) < KP_GATE:
                    candidates.append(d)
            d += timedelta(days=1)
    np.random.seed(42)
    np.random.shuffle(candidates)
    return candidates

# ── Analyze one event ─────────────────────────────────────────────────────────
def analyze_event(ev, kp_index, all_events):
    name = ev["name"]; role = ev["role"]
    sta_a = ev["sta_a"]; sta_b = ev["sta_b"]
    start = ev["start"]; end = ev["end"]

    print(f"\n{'='*62}")
    print(f"  {name} [{role}]")
    print(f"  {sta_a}-{sta_b}  |  {start}-{end} UTC  |  Kp={ev['kp']}")
    print(f"  Warmup guard: first {MIN_BASELINE_POINTS} minutes not scored")
    print(f"{'='*62}")

    a_ev = fetch_intermagnet(sta_a, ev["date"], start, end)
    b_ev = fetch_intermagnet(sta_b, ev["date"], start, end)
    ev_m = compute_metrics(a_ev, b_ev)
    if ev_m is None:
        print("  No event data"); return None

    ev_timing = spike_timing_metric(ev_m["sig_a"], ev["sighting_minute"])

    print(f"\n  EVENT DAY:")
    print(f"    peak sigma {sta_a}: {ev_m['peak_sigma_a']:.3f}")
    print(f"    peak sigma {sta_b}: {ev_m['peak_sigma_b']:.3f}")
    print(f"    co-exceedances:     {ev_m['coexceed_count']}")
    if ev_timing is not None:
        print(f"    spike timing gap:   {ev_timing} min from sighting")

    exclude = {e["date"] for e in all_events if e["sta_a"] == sta_a}
    candidates = get_candidates(ev["date"].month, ev["date"].year,
                                kp_index, exclude)
    print(f"\n  Building null ({len(candidates)} candidates)...")

    null = {"peak_a": [], "peak_b": [], "coexceed": [], "timing": []}
    failed = 0
    for cdate in candidates:
        if len(null["peak_a"]) >= N_CONTROL: break
        a = fetch_intermagnet(sta_a, cdate, start, end)
        b = fetch_intermagnet(sta_b, cdate, start, end)
        m = compute_metrics(a, b)
        if m is None: failed += 1; continue
        null["peak_a"].append(m["peak_sigma_a"])
        null["peak_b"].append(m["peak_sigma_b"])
        null["coexceed"].append(m["coexceed_count"])
        t = spike_timing_metric(m["sig_a"], ev["sighting_minute"])
        if t is not None: null["timing"].append(t)
        if len(null["peak_a"]) % 20 == 0:
            print(f"  {len(null['peak_a'])} control days...")

    n_ctrl = len(null["peak_a"])
    print(f"  Final: {n_ctrl} control days ({failed} failed)")
    if n_ctrl < 10: return None

    def pct(nd, obs): return float(stats.percentileofscore(np.array(nd), obs))
    def zs(nd, obs):
        a = np.array(nd)
        return float((obs - np.mean(a))/np.std(a)) if np.std(a) > 0 else 0.0

    metrics = {
        "peak_sigma_a": {
            "observed": ev_m["peak_sigma_a"],
            "null_mean": float(np.mean(null["peak_a"])),
            "null_p95":  float(np.percentile(null["peak_a"], 95)),
            "null_p99":  float(np.percentile(null["peak_a"], 99)),
            "percentile": pct(null["peak_a"], ev_m["peak_sigma_a"]),
            "z": zs(null["peak_a"], ev_m["peak_sigma_a"]),
            "null_dist": null["peak_a"],
        },
        "peak_sigma_b": {
            "observed": ev_m["peak_sigma_b"],
            "null_mean": float(np.mean(null["peak_b"])),
            "null_p95":  float(np.percentile(null["peak_b"], 95)),
            "null_p99":  float(np.percentile(null["peak_b"], 99)),
            "percentile": pct(null["peak_b"], ev_m["peak_sigma_b"]),
            "z": zs(null["peak_b"], ev_m["peak_sigma_b"]),
            "null_dist": null["peak_b"],
        },
        "coexceed_count": {
            "observed": ev_m["coexceed_count"],
            "null_mean": float(np.mean(null["coexceed"])),
            "null_p95":  float(np.percentile(null["coexceed"], 95)),
            "null_p99":  float(np.percentile(null["coexceed"], 99)),
            "percentile": pct(null["coexceed"], ev_m["coexceed_count"]),
            "z": zs(null["coexceed"], ev_m["coexceed_count"]),
            "null_dist": null["coexceed"],
        },
    }
    if ev_timing is not None and null["timing"]:
        metrics["spike_timing"] = {
            "observed": ev_timing,
            "null_mean": float(np.mean(null["timing"])),
            "null_p05":  float(np.percentile(null["timing"], 5)),
            "percentile": 100 - pct(null["timing"], ev_timing),
            "z": -zs(null["timing"], ev_timing),
            "null_dist": null["timing"],
        }

    print(f"\n  RESULTS (*** = beyond 95th/5th pct):")
    print(f"  {'Metric':<22} {'Obs':>8} {'Mean':>8} {'p95':>8} {'Pct':>8} {'z':>6}")
    print(f"  {'─'*64}")
    for mname, mv in metrics.items():
        p95 = mv.get("null_p95", mv.get("null_p05", 0))
        flag = " ***" if mv["percentile"] >= 95 or mv["percentile"] <= 5 else ""
        print(f"  {mname:<22} {mv['observed']:>8.2f} {mv['null_mean']:>8.2f} "
              f"{p95:>8.2f} {mv['percentile']:>8.1f} {mv['z']:>6.2f}{flag}")

    return {
        "event": name, "role": role,
        "sta_a": sta_a, "sta_b": sta_b,
        "n_control": n_ctrl, "metrics": metrics,
        "ev_sig_a": ev_m["sig_a"].tolist(),
        "ev_sig_b": ev_m["sig_b"].tolist(),
    }

# ── Plot ──────────────────────────────────────────────────────────────────────
def make_plots(all_results):
    ok = [r for r in all_results if r]
    if not ok: return

    metric_names  = ["peak_sigma_a", "peak_sigma_b", "coexceed_count"]
    metric_labels = ["Peak sigma (sta A)", "Peak sigma (sta B)", "Co-exceedances"]

    fig, axes = plt.subplots(len(metric_names), len(ok),
                             figsize=(6*len(ok), 4*len(metric_names)),
                             facecolor=BG)
    if len(ok) == 1: axes = axes.reshape(-1,1)
    fig.subplots_adjust(hspace=0.5, wspace=0.35)

    for col, res in enumerate(ok):
        ev_color = next(e["color"] for e in EVENTS if e["name"]==res["event"])
        for row, (mn, ml) in enumerate(zip(metric_names, metric_labels)):
            if mn not in res["metrics"]: continue
            mv = res["metrics"][mn]
            ax = axes[row][col]
            ax.set_facecolor(BG2)
            ax.tick_params(colors=DIM, labelsize=8)
            for sp in ax.spines.values(): sp.set_color("#252a2e")

            nd  = np.array(mv["null_dist"])
            obs = mv["observed"]
            pct_r = mv["percentile"]
            p95 = mv.get("null_p95", mv.get("null_p05", 0))
            p99 = mv.get("null_p99", 0)

            n_bins = min(25, len(nd)//2)
            ax.hist(nd, bins=n_bins, color=BLU, alpha=0.65, edgecolor=BG, lw=0.3,
                   label=f"Controls (n={len(nd)})")
            if p95: ax.axvline(p95, color=ORG, lw=0.9, ls="--", alpha=0.7,
                               label=f"95th ({p95:.2f})")
            if p99: ax.axvline(p99, color=GRN, lw=0.9, ls=":", alpha=0.7,
                               label=f"99th ({p99:.2f})")
            ax.axvline(obs, color=ev_color, lw=2.5, zorder=6,
                      label=f"Obs: {obs:.2f} ({pct_r:.0f}th)")

            flag = " ***" if pct_r >= 95 or pct_r <= 5 else ""
            ax.set_title(f"{res['event']} [{res['role']}]\n"
                        f"{res['sta_a']}-{res['sta_b']} | {ml}\n"
                        f"{pct_r:.0f}th pct{flag}",
                        color=TC, fontsize=8, pad=6)
            ax.set_xlabel(ml, color=TC, fontsize=8)
            ax.set_ylabel("Count", color=TC, fontsize=8)
            ax.legend(fontsize=6, facecolor=BG2, edgecolor="#252a2e",
                     labelcolor=TC, loc="upper right")

    fig.suptitle(
        f"Sigma Null Distribution v2 (warmup fix: min {MIN_BASELINE_POINTS} pts)\n"
        f"baseline={SIGMA_BASELINE_WINDOW}min | threshold={SIGMA_THRESHOLD}s | "
        f"lag=±{COEXCEED_LAG_WINDOW}min | Kp<{KP_GATE} | n={N_CONTROL}\n"
        "*** = beyond 95th/5th percentile",
        color=TC, fontsize=9, y=1.01)

    png = os.path.join(OUT_DIR, "sigma_null_v2.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"\n  Histogram plot: {png}")

    # Time series plot
    fig2, axes2 = plt.subplots(len(ok), 1, figsize=(14, 4*len(ok)), facecolor=BG)
    if len(ok) == 1: axes2 = [axes2]
    fig2.subplots_adjust(hspace=0.5)

    for ax, res in zip(axes2, ok):
        ev = next(e for e in EVENTS if e["name"]==res["event"])
        ax.set_facecolor(BG2)
        ax.tick_params(colors=DIM, labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#252a2e")

        sig_a = np.array(res["ev_sig_a"])
        sig_b = np.array(res["ev_sig_b"])
        mins  = np.arange(len(sig_a))

        # Shade warmup period
        ax.axvspan(0, MIN_BASELINE_POINTS, alpha=0.15, color=DIM,
                  label=f"Warmup (not scored, <{MIN_BASELINE_POINTS} pts)")
        ax.plot(mins, sig_a, color=ev["color"], lw=1.2, label=f"{res['sta_a']} sigma")
        ax.plot(mins, sig_b, color=BLU, lw=1.2, alpha=0.7, label=f"{res['sta_b']} sigma")
        ax.axhline(SIGMA_THRESHOLD, color=RED, lw=0.8, ls="--", alpha=0.6,
                  label=f"{SIGMA_THRESHOLD}s threshold")
        if ev["sighting_minute"] is not None:
            ax.axvline(ev["sighting_minute"], color=ORG, lw=1.0, ls="--",
                      alpha=0.8, label="Last sighting")

        pka = res["metrics"]["peak_sigma_a"]
        cex = res["metrics"]["coexceed_count"]
        ax.set_title(
            f"{res['event']} [{res['role']}] — Rolling sigma (warmup-corrected)\n"
            f"Peak {res['sta_a']}: {pka['observed']:.2f}s ({pka['percentile']:.0f}th pct)  |  "
            f"Co-exceedances: {cex['observed']} ({cex['percentile']:.0f}th pct)",
            color=TC, fontsize=8, pad=6)
        ax.set_xlabel("Minutes from window start", color=TC, fontsize=8)
        ax.set_ylabel("Rolling sigma", color=TC, fontsize=8)
        ax.legend(fontsize=7, facecolor=BG2, edgecolor="#252a2e",
                 labelcolor=TC, loc="upper right", ncol=2)

    fig2.suptitle("Rolling Sigma Time Series v2 (warmup-corrected)",
                 color=TC, fontsize=9, y=1.01)
    png2 = os.path.join(OUT_DIR, "sigma_timeseries_v2.png")
    plt.savefig(png2, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"  Time series plot: {png2}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=== Sigma Null Analysis v2 (warmup fix) ===")
    print(f"  Fix: scores zeroed for first {MIN_BASELINE_POINTS} minutes")
    print(f"  Eliminates artifactual spikes from thin baseline windows")
    print()
    print("  RETIRED: Pearson cross-correlation (fails null test)")
    print("  TESTING: peak sigma, co-exceedances, spike timing")
    print()

    kp_index = load_kp()
    all_results = []
    for ev in EVENTS:
        r = analyze_event(ev, kp_index, EVENTS)
        all_results.append(r)

    print()
    print("=" * 72)
    print("  SUMMARY -- ALL METRICS, ALL EVENTS (including non-significant)")
    print("=" * 72)
    print(f"  {'Event':<22} {'Role':<20} {'Metric':<22} {'Pct':>6} {'z':>6}")
    print(f"  {'─'*72}")
    for res in all_results:
        if not res: continue
        for mn, mv in res["metrics"].items():
            flag = " ***" if mv["percentile"] >= 95 or mv["percentile"] <= 5 else ""
            print(f"  {res['event']:<22} {res['role']:<20} {mn:<22} "
                  f"{mv['percentile']:>6.1f} {mv['z']:>6.2f}{flag}")

    make_plots(all_results)

    clean = []
    for res in all_results:
        if not res: continue
        rc = {k:v for k,v in res.items() if k not in ("ev_sig_a","ev_sig_b")}
        for mn in rc.get("metrics",{}):
            rc["metrics"][mn] = {k:v for k,v in rc["metrics"][mn].items()
                                 if k != "null_dist"}
        clean.append(rc)

    jp = os.path.join(OUT_DIR, "sigma_null_v2_results.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"  JSON: {jp}")
    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
