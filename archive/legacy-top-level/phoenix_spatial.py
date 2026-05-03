import os, sys, json, subprocess
import numpy as np

def pip(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)
pip("requests"); pip("numpy"); pip("matplotlib")
import requests

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR  = os.path.join(WORK_DIR, "results", "phoenix_1997")
os.makedirs(OUT_DIR, exist_ok=True)

KNOWN = {
    "TUC": {"lat": 32.17, "lon": -110.73, "peak_sigma": 6.333, "in_event": True},
    "BOU": {"lat": 40.13, "lon": -105.24, "peak_sigma": 4.1,   "in_event": True},
}

STATIONS = [
    {"id": "SIT", "lat": 57.06, "lon": -135.33, "desc": "Sitka AK"},
    {"id": "CMO", "lat": 64.87, "lon": -147.86, "desc": "College AK"},
    {"id": "FRD", "lat": 38.20, "lon":  -77.37, "desc": "Fredericksburg VA"},
    {"id": "SJG", "lat": 18.11, "lon":  -66.15, "desc": "San Juan PR"},
    {"id": "HON", "lat": 21.32, "lon": -158.00, "desc": "Honolulu HI"},
    {"id": "BRW", "lat": 71.32, "lon": -156.63, "desc": "Barrow AK"},
    {"id": "TEO", "lat": 19.75, "lon":  -98.97, "desc": "Teoloyucan Mexico"},
]

HAPI_BASE  = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
START      = "1997-03-13T00:00:00Z"
END        = "1997-03-13T06:00:00Z"
PEAK_H     = 3.533
WIN_LO_H   = 3.25
WIN_HI_H   = 3.75
SIGMA_THRESH = 2.0

def fetch_intermagnet(sid):
    cache = os.path.join(WORK_DIR, f"intermagnet_{sid}_19970313.json")
    if os.path.exists(cache):
        try:
            d = json.load(open(cache, encoding="utf-8"))
            if d.get("data") and len(d["data"]) > 10:
                return d
        except: pass

    for data_type in ["definitive", "quasi-definitive", "variation"]:
        params = {
            "id":       f"{sid}/{data_type}/PT1M/xyzf",
            "time.min": START,
            "time.max": END,
            "format":   "json",
        }
        try:
            r = requests.get(HAPI_BASE, params=params, timeout=30)
            if r.status_code == 200:
                d = r.json()
                if d.get("data") and len(d["data"]) > 10:
                    d["_data_type"] = data_type
                    with open(cache, "w", encoding="utf-8") as f:
                        json.dump(d, f)
                    return d
        except: continue
    return None

def extract_y_component(data):
    """
    INTERMAGNET HAPI returns: [timestamp, [x, y, z], f]
    Row structure confirmed by diagnostic:
      row[0] = timestamp string
      row[1] = [X_nT, Y_nT, Z_nT]   (list)
      row[2] = F_nT                  (scalar, often 99999 missing)
    Y = east component = D equivalent
    """
    rows = data.get("data", [])
    times_h, y_vals = [], []
    for row in rows:
        try:
            ts  = str(row[0])
            hr  = int(ts[11:13]); mn = int(ts[14:16])
            t_h = hr + mn / 60.0
            xyz = row[1]
            y   = float(xyz[1])          # Y = east/D component
            if abs(y) < 90000:           # filter IAGA missing
                times_h.append(t_h)
                y_vals.append(y)
        except: continue
    return times_h, y_vals

def rolling_sigma(times_h, vals, window_min=20):
    arr = np.array(vals)
    out = np.zeros(len(arr))
    for i in range(len(arr)):
        lo = max(0, i - window_min // 2)
        hi = min(len(arr), i + window_min // 2)
        w  = arr[lo:hi]
        s  = np.std(w)
        if s > 0:
            out[i] = abs(arr[i] - np.mean(w)) / s
    return out

def analyze(stn):
    sid = stn["id"]
    print(f"  {sid} ({stn['desc']})")
    data = fetch_intermagnet(sid)
    if data is None:
        print(f"    No data from INTERMAGNET")
        return {"station": sid, "lat": stn["lat"], "lon": stn["lon"],
                "desc": stn["desc"], "status": "no_data"}

    n = len(data.get("data", []))
    print(f"    {n} rows ({data.get('_data_type','?')})")

    times_h, y_vals = extract_y_component(data)
    if len(y_vals) < 10:
        print(f"    Only {len(y_vals)} valid Y readings")
        return {"station": sid, "lat": stn["lat"], "lon": stn["lon"],
                "desc": stn["desc"], "status": "parse_failed",
                "n_valid": len(y_vals)}

    print(f"    {len(y_vals)} valid Y (east) readings")

    sigmas = rolling_sigma(times_h, y_vals)

    window_sigs = [sigmas[i] for i, t in enumerate(times_h)
                   if WIN_LO_H <= t <= WIN_HI_H]
    peak_w = max(window_sigs) if window_sigs else 0.0
    peak_g = float(np.max(sigmas))
    in_ev  = peak_w >= SIGMA_THRESH

    flag = "<<< IN EVENT" if in_ev else "-- quiet"
    print(f"    Window sigma: {peak_w:.3f}  {flag}")
    print(f"    Global peak:  {peak_g:.3f}")

    return {
        "station": sid, "lat": stn["lat"], "lon": stn["lon"],
        "desc": stn["desc"], "data_type": data.get("_data_type"),
        "n_valid": len(y_vals),
        "peak_sigma_window": round(peak_w, 3),
        "peak_sigma_global": round(peak_g, 3),
        "in_event": in_ev,
        "times_h": times_h,
        "y_vals": y_vals,
        "sigmas": sigmas.tolist(),
        "status": "ok"
    }

def make_plot(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    BG="#0c0e0f"; BG2="#131618"; TC="#cac6bc"; DIM="#6a6760"
    GRN="#6fa87a"; RED="#e05c5c"; ORG="#b89555"; BLU="#5a91c0"

    ok = [r for r in results if r.get("status") == "ok"]
    if not ok:
        print("  No data to plot")
        return

    all_stns = ok + [
        {"station":"TUC","lat":32.17,"lon":-110.73,"in_event":True,
         "peak_sigma_window":6.333,"desc":"Tucson AZ (known)"},
        {"station":"BOU","lat":40.13,"lon":-105.24,"in_event":True,
         "peak_sigma_window":4.1,  "desc":"Boulder CO (known)"},
    ]

    fig = plt.figure(figsize=(16, 8), facecolor=BG)
    gs  = gridspec.GridSpec(1, 2, width_ratios=[1, 1.8], wspace=0.08)

    # MAP
    ax_map = fig.add_subplot(gs[0])
    ax_map.set_facecolor(BG2)
    ax_map.tick_params(colors=DIM, labelsize=7)
    for sp in ax_map.spines.values(): sp.set_color("#252a2e")

    for stn in all_stns:
        col  = RED   if stn.get("in_event") else GRN
        mk   = "*"   if stn.get("in_event") else "o"
        sz   = 180   if stn.get("in_event") else 80
        ax_map.scatter(stn["lon"], stn["lat"], c=col, s=sz,
                      marker=mk, zorder=5, alpha=0.9, edgecolors="none")
        sig = stn.get("peak_sigma_window", 0)
        ax_map.annotate(
            f"  {stn['station']}\n  {sig:.1f}s",
            xy=(stn["lon"], stn["lat"]),
            fontsize=6, color=TC, va="center")

    # No-data stations
    for stn in results:
        if stn.get("status") != "ok":
            ax_map.scatter(stn["lon"], stn["lat"], c=DIM, s=50,
                          marker="x", zorder=4, alpha=0.7)
            ax_map.annotate(f"  {stn['station']}\n  no data",
                           xy=(stn["lon"], stn["lat"]),
                           fontsize=5, color=DIM)

    # Corridor shading
    ax_map.fill_between([-115, -100], [30, 30], [43, 43],
                        alpha=0.07, color=ORG)
    ax_map.set_xlim(-175, -60); ax_map.set_ylim(10, 75)
    ax_map.set_xlabel("Longitude", color=TC, fontsize=8)
    ax_map.set_ylabel("Latitude",  color=TC, fontsize=8)
    ax_map.set_title("Station Map\nRed star=anomalous | Green=quiet | X=no data",
                    color=TC, fontsize=8, pad=6)

    # TIME SERIES
    ax_ts = fig.add_subplot(gs[1])
    ax_ts.set_facecolor(BG2)
    ax_ts.tick_params(colors=DIM, labelsize=7)
    for sp in ax_ts.spines.values(): sp.set_color("#252a2e")
    ax_ts.axvspan(WIN_LO_H, WIN_HI_H, alpha=0.12, color=ORG, label="Event window")
    ax_ts.axvline(PEAK_H, color=ORG, lw=0.8, ls="--", alpha=0.8)
    ax_ts.axhline(SIGMA_THRESH, color=RED, lw=0.7, ls="--", alpha=0.6,
                 label="2.0s threshold")

    palette = [BLU,"#c47ec4","#e0a060","#60c0e0","#a0e060","#e06080","#80e0c0"]
    for j, r in enumerate(ok):
        col = palette[j % len(palette)]
        lw  = 1.6 if r.get("in_event") else 0.9
        ax_ts.plot(r["times_h"], r["sigmas"], color=col, lw=lw, alpha=0.85,
                  label=f"{r['station']} {r['peak_sigma_window']:.2f}s")

    ax_ts.set_xlim(0, 6)
    ax_ts.set_xlabel("UTC hours", color=TC, fontsize=8)
    ax_ts.set_ylabel("Sigma (20-min rolling baseline)", color=TC, fontsize=8)
    ax_ts.set_title(
        "Y-component (east) Sigma -- All Stations -- 1997-03-13\n"
        "Shaded=event window | Dashed=mag peak 03:32 UTC",
        color=TC, fontsize=8, pad=6)
    ax_ts.legend(fontsize=6, facecolor=BG2, edgecolor="#252a2e",
                labelcolor=TC, loc="upper right", ncol=2)

    fig.suptitle(
        "Phoenix Lights 1997 -- Spatial Extent of Magnetometer Anomaly\n"
        "Working question: localized AZ-CO corridor or broad regional event?",
        color=TC, fontsize=9, y=1.01)

    png = os.path.join(OUT_DIR, "phoenix_spatial_extent.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"\n  Plot: {png}")

def main():
    print()
    print("=== Phoenix Lights 1997 -- Spatial Extent v2 ===")
    print()

    results = []
    for stn in STATIONS:
        r = analyze(stn)
        results.append(r)

    ok    = [r for r in results if r.get("status") == "ok"]
    in_ev = [r for r in ok if r.get("in_event")]
    quiet = [r for r in ok if not r.get("in_event")]
    nd    = [r for r in results if r.get("status") != "ok"]

    print()
    print("=" * 62)
    print("  SPATIAL EXTENT RESULTS")
    print("=" * 62)
    print(f"  {'Stn':<5} {'Location':<25} {'Win sigma':>10} {'Result':>12}")
    print(f"  {'-'*56}")
    print(f"  {'TUC':<5} {'Tucson AZ (known)':<25} {'6.333':>10} {'IN EVENT':>12}")
    print(f"  {'BOU':<5} {'Boulder CO (known)':<25} {'4.100':>10} {'IN EVENT':>12}")
    for r in ok:
        flag = "IN EVENT" if r.get("in_event") else "quiet"
        print(f"  {r['station']:<5} {r['desc']:<25} "
              f"{r['peak_sigma_window']:>10.3f} {flag:>12}")
    for r in nd:
        print(f"  {r['station']:<5} {r['desc']:<25} "
              f"{'--':>10} {'no data':>12}")

    print()
    print("  VERDICT")
    print(f"  {'-'*56}")
    if not ok:
        print("  No new station data available.")
    elif in_ev:
        ids = [r["station"] for r in in_ev]
        print(f"  ADDITIONAL STATIONS IN EVENT: {ids}")
        print(f"  --> Anomaly extends beyond AZ-CO corridor")
        print(f"  --> Check geometry -- could still be corridor-aligned")
        print(f"  --> Or indicates broader regional field disturbance")
    else:
        ids = [r["station"] for r in quiet]
        print(f"  ALL NEW STATIONS QUIET: {ids}")
        print(f"  --> Anomaly is SPATIALLY LOCALIZED")
        print(f"  --> Consistent with a source physically present")
        print(f"      in the AZ-CO corridor during the event window")
        print(f"  --> Rules out global geomagnetic storm explanation")

    if ok:
        make_plot(results)

    clean = [{k:v for k,v in r.items()
              if k not in ("times_h","y_vals","sigmas")}
             for r in results]
    jp = os.path.join(OUT_DIR, "phoenix_spatial_extent.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump({"results": clean, "known": KNOWN}, f, indent=2)
    print(f"\n  JSON: {jp}")
    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
