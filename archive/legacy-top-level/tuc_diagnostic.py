import os, sys, json, subprocess
import numpy as np

def pip(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)
pip("requests"); pip("numpy"); pip("matplotlib")

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WORK_DIR  = r"C:\Users\Mike\uap_sniffer\uap_sniffer"
OUT_DIR   = os.path.join(WORK_DIR, "results", "phoenix_1997")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache")
os.makedirs(OUT_DIR, exist_ok=True)

HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
USGS_URL  = "https://geomag.usgs.gov/ws/data/"
DATE      = "1997-03-13"
START     = "01:00"
END       = "05:00"

BG="#0c0e0f"; BG2="#131618"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"

print()
print("=== TUC Data Source Diagnostic ===")
print(f"  Date: {DATE}  Window: {START}-{END} UTC")
print(f"  Comparing USGS API vs INTERMAGNET HAPI")
print(f"  Comparing D vs Y vs H components")
print()

# ── Fetch USGS -- tries D, H, X, Y components ─────────────────────────────────
def fetch_usgs(station, element):
    params = {
        "id": station, "type": "variation", "elements": element,
        "sampling_period": 60,
        "starttime": f"{DATE}T{START}:00Z",
        "endtime":   f"{DATE}T{END}:00Z",
        "format": "json",
    }
    try:
        r = requests.get(USGS_URL, params=params, timeout=20)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        data = r.json()
        vraw = None
        if "values" in data and data["values"]:
            first = data["values"][0]
            vraw = first.get("values") if isinstance(first, dict) else first
        if not vraw:
            return None, "no values key"
        vals = []
        for v in vraw:
            try:
                fv = float(v)
                vals.append(np.nan if abs(fv) > 90000 else fv)
            except:
                vals.append(np.nan)
        n_valid = sum(1 for v in vals if not np.isnan(v))
        return np.array(vals), f"{n_valid} valid pts"
    except Exception as e:
        return None, str(e)

# ── Fetch INTERMAGNET -- all components from xyzf ─────────────────────────────
def fetch_hapi_all(station):
    """Returns dict of component arrays: X, Y, Z, F"""
    key = f"hapi_{station}_{DATE}_{START.replace(':','')}_{END.replace(':','')}.json"
    cp  = os.path.join(CACHE_DIR, key)
    rows = None
    if os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            # old cache format only stores Y -- need full data
        except: pass

    for data_type in ["definitive", "quasi-definitive", "variation"]:
        params = {
            "id":       f"{station}/{data_type}/PT1M/xyzf",
            "time.min": f"{DATE}T{START}:00Z",
            "time.max": f"{DATE}T{END}:00Z",
            "format":   "json",
        }
        try:
            r = requests.get(HAPI_BASE, params=params, timeout=25)
            if r.status_code != 200: continue
            data = r.json()
            rows = data.get("data", [])
            if len(rows) < 10: continue
            print(f"  HAPI: {len(rows)} rows ({data_type})")
            break
        except Exception as e:
            print(f"  HAPI error ({data_type}): {e}")
            continue

    if not rows:
        return None

    X, Y, Z, F = [], [], [], []
    for row in rows:
        try:
            xyz = row[1]  # [x, y, z]
            f   = row[2]  # scalar F
            X.append(float(xyz[0]) if abs(float(xyz[0])) < 90000 else np.nan)
            Y.append(float(xyz[1]) if abs(float(xyz[1])) < 90000 else np.nan)
            Z.append(float(xyz[2]) if abs(float(xyz[2])) < 90000 else np.nan)
            F.append(float(f)      if abs(float(f))      < 90000 else np.nan)
        except:
            X.append(np.nan); Y.append(np.nan)
            Z.append(np.nan); F.append(np.nan)

    return {
        "X": np.array(X), "Y": np.array(Y),
        "Z": np.array(Z), "F": np.array(F)
    }

# ── Rolling sigma (past-only, warmup-guarded) ─────────────────────────────────
def rolling_sigma(vals, window=20, min_pts=15):
    arr = np.array(vals, dtype=float)
    out = np.zeros(len(arr))
    for i in range(len(arr)):
        w = arr[max(0, i-window):i]
        w = w[~np.isnan(w)]
        if len(w) < min_pts: continue
        s = np.std(w)
        if s < 1e-6: continue
        if not np.isnan(arr[i]):
            out[i] = abs(arr[i] - np.mean(w)) / s
    return out

def rolling_sigma_no_warmup_guard(vals, window=20):
    """Original pipeline behavior -- no minimum points requirement"""
    arr = np.array(vals, dtype=float)
    out = np.zeros(len(arr))
    for i in range(len(arr)):
        w = arr[max(0, i-window):i]
        w = w[~np.isnan(w)]
        if len(w) < 2: continue
        s = np.std(w)
        if s < 1e-6: continue
        if not np.isnan(arr[i]):
            out[i] = abs(arr[i] - np.mean(w)) / s
    return out

# ── Main ──────────────────────────────────────────────────────────────────────
print("Fetching USGS TUC:")
usgs_results = {}
for element in ["D", "H", "X", "Y"]:
    vals, status = fetch_usgs("TUC", element)
    n_valid = sum(1 for v in (vals if vals is not None else []) if not np.isnan(v))
    print(f"  TUC {element}: {status}  |  n_valid={n_valid}")
    if vals is not None and n_valid > 10:
        usgs_results[element] = vals

print()
print("Fetching INTERMAGNET TUC:")
hapi = fetch_hapi_all("TUC")

if hapi is None:
    print("  INTERMAGNET fetch failed")
else:
    for comp, arr in hapi.items():
        n_valid = sum(1 for v in arr if not np.isnan(v))
        print(f"  TUC {comp}: n_valid={n_valid}  "
              f"range=[{np.nanmin(arr):.2f}, {np.nanmax(arr):.2f}]")

print()
print("Computing sigma scores -- comparing methods:")
print()

results = []

# For each available component, compute sigma both ways
components_to_test = []
for el, vals in usgs_results.items():
    components_to_test.append(("USGS", el, vals))
if hapi:
    for comp, arr in hapi.items():
        if sum(1 for v in arr if not np.isnan(v)) > 10:
            components_to_test.append(("HAPI", comp, arr))

print(f"  {'Source':<8} {'Comp':<5} {'No guard peak':>14} "
      f"{'Guarded peak':>14} {'Peak minute':>12}")
print(f"  {'─'*58}")

for source, comp, vals in components_to_test:
    sig_ng = rolling_sigma_no_warmup_guard(vals, window=20)
    sig_g  = rolling_sigma(vals, window=20, min_pts=15)

    peak_ng     = float(np.max(sig_ng))
    peak_ng_min = int(np.argmax(sig_ng))
    peak_g      = float(np.max(sig_g))
    peak_g_min  = int(np.argmax(sig_g))

    print(f"  {source:<8} {comp:<5} {peak_ng:>14.3f} (min {peak_ng_min:3d})"
          f"  {peak_g:>14.3f} (min {peak_g_min:3d})")

    results.append({
        "source": source, "component": comp,
        "peak_no_guard": peak_ng, "peak_no_guard_min": peak_ng_min,
        "peak_guarded": peak_g,   "peak_guarded_min": peak_g_min,
        "vals": vals, "sig_ng": sig_ng, "sig_g": sig_g,
    })

# ── Plot ──────────────────────────────────────────────────────────────────────
print()
print("Plotting...")

# Plot all sigma time series side by side
n = len(results)
if n > 0:
    fig, axes = plt.subplots(n, 2, figsize=(14, 3*n), facecolor=BG)
    if n == 1: axes = axes.reshape(1, 2)
    fig.subplots_adjust(hspace=0.5, wspace=0.3)

    for row, res in enumerate(results):
        mins = np.arange(len(res["vals"]))

        for col, (sig, label, guard_label) in enumerate([
            (res["sig_ng"], "No warmup guard (original behavior)",
             f"Peak={res['peak_no_guard']:.2f} at min {res['peak_no_guard_min']}"),
            (res["sig_g"],  f"Warmup guard (min 15 pts)",
             f"Peak={res['peak_guarded']:.2f} at min {res['peak_guarded_min']}"),
        ]):
            ax = axes[row][col]
            ax.set_facecolor(BG2)
            ax.tick_params(colors=DIM, labelsize=7)
            for sp in ax.spines.values(): sp.set_color("#252a2e")

            color = BLU if res["source"] == "HAPI" else GRN
            ax.plot(mins, sig, color=color, lw=1.0)
            ax.axhline(2.0, color=RED, lw=0.7, ls="--", alpha=0.6)
            ax.axvline(148, color=ORG, lw=0.8, ls="--", alpha=0.7,
                      label="Last sighting (min 148)")

            # Warmup zone
            if col == 1:
                ax.axvspan(0, 15, alpha=0.15, color=DIM, label="Warmup zone")

            ax.set_title(
                f"{res['source']} {res['component']} | {label}\n{guard_label}",
                color=TC, fontsize=7, pad=4)
            ax.set_xlabel("Minutes from 01:00 UTC", color=TC, fontsize=7)
            ax.set_ylabel("Sigma", color=TC, fontsize=7)

    fig.suptitle(
        "TUC 1997-03-13 -- Data Source & Sigma Method Comparison\n"
        "Left: no warmup guard (original pipeline behavior)\n"
        "Right: warmup guard (null test behavior, min 15 pts)",
        color=TC, fontsize=9, y=1.01)

    png = os.path.join(OUT_DIR, "tuc_diagnostic.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"  Plot: {png}")

# Save results
clean = [{k:v for k,v in r.items()
          if k not in ("vals","sig_ng","sig_g")}
         for r in results]
jp = os.path.join(OUT_DIR, "tuc_diagnostic.json")
with open(jp, "w", encoding="utf-8") as f:
    json.dump(clean, f, indent=2)
print(f"  JSON: {jp}")

print()
print("=== KEY QUESTION ===")
print("Does any source/component/method reproduce the original 6.33 sigma?")
print("If yes: we know what the original pipeline was computing.")
print("If no: the 6.33 number needs to be traced in run_all_events.py directly.")
print()
input("Press Enter to close...")
