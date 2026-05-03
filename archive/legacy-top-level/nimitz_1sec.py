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
from scipy.signal import welch, spectrogram
from scipy.fft import fft, fftfreq

WORK_DIR  = r"C:\Users\Mike\uap_sniffer\uap_sniffer"
OUT_DIR   = os.path.join(WORK_DIR, "results", "nimitz_2004")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache", "1sec")
os.makedirs(OUT_DIR,   exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BG="#0c0e0f"; BG2="#131618"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"; PRP="#c47ec4"

USGS_URL = "https://geomag.usgs.gov/ws/data/"

# Nimitz event parameters
EVENT_DATE     = date(2004, 11, 14)
SPIKE_REF_UTC  = "2004-11-14T19:17:00Z"
# Fetch 30 min either side of event for high-res analysis
FETCH_START    = "2004-11-14T18:45:00Z"  # when Fravor scrambled
FETCH_END      = "2004-11-14T19:47:00Z"  # 30 min after relocation
# Wider window for baseline
WIDE_START     = "2004-11-14T17:00:00Z"
WIDE_END       = "2004-11-14T22:00:00Z"

# Spike reference = minute 32 from 18:45 UTC (19:17 - 18:45 = 32 min = 1920 sec)
SPIKE_SEC = 1920

STATIONS = ["BOU", "TUC", "FRN"]  # FRN=Fresno CA -- closest USGS station to event

print()
print("╔══════════════════════════════════════════════════════════════╗")
print("║   USS NIMITZ -- 1-SECOND RESOLUTION MAGNETOMETER           ║")
print("║   Testing for sub-minute ULF/ELF field variations          ║")
print("║   at 60x higher resolution than previous analysis          ║")
print("╚══════════════════════════════════════════════════════════════╝")
print()
print("  Why 1-second matters:")
print("  1-minute data aliases out anything faster than 2-min period")
print("  ULF pulsations (Pc1-Pc5) range from 1s to 600s period")
print("  A sharp 30-second field pulse would be INVISIBLE in 1-min data")
print()

def fetch_1sec(station, start_utc, end_utc, element="D"):
    """Fetch 1-second resolution data from USGS geomag API."""
    cache_key = f"1sec_{station}_{start_utc[:10]}_{start_utc[11:16].replace(':','')}_{end_utc[11:16].replace(':','')}.json"
    cp = os.path.join(CACHE_DIR, cache_key)
    if os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            if d.get("vals") and len(d["vals"]) > 10:
                print(f"    {station}: cached ({len(d['vals'])} pts)")
                return np.array(d["vals"]), d.get("times", [])
        except: pass

    params = {
        "id": station,
        "type": "variation",
        "elements": element,
        "sampling_period": 1,
        "starttime": start_utc,
        "endtime": end_utc,
        "format": "json",
    }
    try:
        r = requests.get(USGS_URL, params=params, timeout=30)
        if r.status_code != 200:
            print(f"    {station}: HTTP {r.status_code} -- trying definitive")
            params["type"] = "definitive"
            r = requests.get(USGS_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"    {station}: failed (HTTP {r.status_code})")
                return None, []

        data = r.json()
        times = data.get("times", [])
        vals_raw = None
        for entry in data.get("values", []):
            if entry.get("id") == element:
                vals_raw = entry.get("values", [])
                break
        if not vals_raw and data.get("values"):
            first = data["values"][0]
            vals_raw = first.get("values", first if isinstance(first, list) else [])

        if not vals_raw:
            print(f"    {station}: no values in response")
            return None, []

        vals = []
        for v in vals_raw:
            try:
                fv = float(v)
                vals.append(np.nan if abs(fv) > 90000 else fv)
            except: vals.append(np.nan)

        n_valid = sum(1 for v in vals if not np.isnan(v))
        print(f"    {station}: {len(vals)} pts, {n_valid} valid")

        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"vals": vals, "times": times}, f)

        return np.array(vals), times

    except Exception as e:
        print(f"    {station}: ERROR {e}")
        return None, []

def compute_1sec_metrics(vals, times, spike_sec):
    """
    Compute metrics specific to 1-second data:
    1. Rolling sigma at 60-sec window (same as before)
    2. Rolling sigma at 5-sec window (catches fast pulses)
    3. Power spectral density -- look for unusual frequency content
    4. Spectrogram -- time-frequency view around event
    5. Peak timing relative to spike reference
    """
    arr = np.array(vals, dtype=float)
    n   = len(arr)

    # Detrend -- remove slow baseline drift
    valid_mask = ~np.isnan(arr)
    if valid_mask.sum() < 60:
        return None

    # Fill NaN with linear interpolation for spectral analysis
    x = np.arange(n)
    arr_filled = arr.copy()
    arr_filled[~valid_mask] = np.interp(x[~valid_mask], x[valid_mask], arr[valid_mask])

    # Rolling sigma at multiple windows
    def rsig(a, w, minpts=None):
        if minpts is None: minpts = w//2
        out = np.zeros(len(a))
        for i in range(len(a)):
            sl = a[max(0,i-w):i]
            sl = sl[~np.isnan(sl)]
            if len(sl) < minpts: continue
            s = np.std(sl)
            if s < 1e-6: continue
            if not np.isnan(a[i]):
                out[i] = abs(a[i] - np.mean(sl)) / s
        return out

    sig_60  = rsig(arr, 60,  minpts=30)   # 60-sec window (matches 1-min analysis)
    sig_5   = rsig(arr, 5,   minpts=3)    # 5-sec window  (fast pulses)
    sig_300 = rsig(arr, 300, minpts=150)  # 5-min window  (slower variations)

    # PSD using Welch method
    fs = 1.0  # 1 Hz sampling
    f_psd, psd = welch(arr_filled - np.nanmean(arr_filled),
                       fs=fs, nperseg=min(512, n//4))

    # Spectrogram around event
    f_spec, t_spec, Sxx = spectrogram(arr_filled - np.nanmean(arr_filled),
                                       fs=fs, nperseg=min(256, n//8),
                                       noverlap=min(200, n//10))

    # Peak analysis around spike reference
    window_30 = 30 * 60  # 30 min = 1800 sec either side
    lo = max(0, spike_sec - window_30)
    hi = min(n, spike_sec + window_30)

    peak_5sec_near   = float(np.max(sig_5[lo:hi]))   if hi > lo else 0
    peak_60sec_near  = float(np.max(sig_60[lo:hi]))  if hi > lo else 0

    # Find closest spike to event
    # Look within ±10 minutes of event
    tight_lo = max(0, spike_sec - 600)
    tight_hi = min(n, spike_sec + 600)
    peak_tight = float(np.max(sig_5[tight_lo:tight_hi])) if tight_hi > tight_lo else 0
    peak_tight_t = int(np.argmax(sig_5[tight_lo:tight_hi])) + tight_lo if tight_hi > tight_lo else -1
    gap_to_spike  = abs(peak_tight_t - spike_sec) if peak_tight_t >= 0 else -1

    return {
        "sig_5":   sig_5,
        "sig_60":  sig_60,
        "sig_300": sig_300,
        "f_psd":   f_psd,
        "psd":     psd,
        "f_spec":  f_spec,
        "t_spec":  t_spec,
        "Sxx":     Sxx,
        "peak_5sec_near":  peak_5sec_near,
        "peak_60sec_near": peak_60sec_near,
        "peak_tight":      peak_tight,
        "gap_to_spike":    gap_to_spike,
        "n":               n,
    }

def main():
    print("─"*60)
    print("FETCHING 1-SECOND DATA")
    print("─"*60)
    print(f"  Window: {FETCH_START} to {FETCH_END}")
    print(f"  Spike reference: {SPIKE_REF_UTC} (sec {SPIKE_SEC} from window start)")
    print()

    station_data = {}
    for sid in STATIONS:
        print(f"  {sid}:")
        vals, times = fetch_1sec(sid, FETCH_START, FETCH_END)
        if vals is not None and len(vals) > 60:
            m = compute_1sec_metrics(vals, times, SPIKE_SEC)
            if m:
                station_data[sid] = {"vals": vals, "times": times, **m}
                print(f"    5-sec peak near event:   {m['peak_5sec_near']:.3f}s")
                print(f"    60-sec peak near event:  {m['peak_60sec_near']:.3f}s")
                print(f"    Peak in ±10min window:   {m['peak_tight']:.3f}s")
                print(f"    Gap to spike reference:  {m['gap_to_spike']} sec "
                      f"({m['gap_to_spike']/60:.1f} min)" if m['gap_to_spike']>=0 else "")
        print()

    if not station_data:
        print("  No 1-second data retrieved.")
        print("  The USGS API may be blocking requests from this IP.")
        print()
        print("  ALTERNATIVE: Download raw files from USGS ScienceBase:")
        print("  BOU: https://doi.org/10.5066/P91S9DIF")
        print("  TUC: https://doi.org/10.5066/P9KZQB9P")
        print("  FRN: https://doi.org/10.5066/P9PS5V16")
        print()
        print("  File naming: BOU20041114.raw (IAGA 2002 format)")
        print("  One file per day, header then data at 1-second intervals")
        print()
        input("Press Enter to close...")
        return

    # Plot
    print("─"*60)
    print("PLOTTING")
    print("─"*60)

    n_sta = len(station_data)
    fig = plt.figure(figsize=(18, 5*n_sta + 2), facecolor=BG)
    gs  = gridspec.GridSpec(n_sta, 3, figure=fig, hspace=0.5, wspace=0.35,
                            left=0.06, right=0.97, top=0.93, bottom=0.04)

    for row, (sid, sd) in enumerate(station_data.items()):
        secs = np.arange(len(sd["vals"]))
        spike = SPIKE_SEC

        # Panel 1: Sigma time series at multiple resolutions
        ax1 = fig.add_subplot(gs[row, 0])
        ax1.set_facecolor(BG2)
        ax1.tick_params(colors=DIM, labelsize=7)
        for sp in ax1.spines.values(): sp.set_color("#252a2e")

        ax1.plot(secs, sd["sig_5"],   color=RED,  lw=0.6, alpha=0.8, label="5-sec window")
        ax1.plot(secs, sd["sig_60"],  color=BLU,  lw=0.9, alpha=0.8, label="60-sec window")
        ax1.plot(secs, sd["sig_300"], color=ORG,  lw=1.1, alpha=0.6, label="5-min window")
        ax1.axhline(2.0, color=RED, lw=0.7, ls="--", alpha=0.5)
        ax1.axvline(spike, color=GRN, lw=2.0, ls="--", alpha=0.9, label="19:17 UTC")
        ax1.axvspan(spike-600, spike+600, alpha=0.05, color=GRN)

        ax1.set_title(f"{sid} Rolling Sigma (1-sec data)\n"
                     f"Peak 5s: {sd['peak_tight']:.2f}s  "
                     f"Gap: {sd['gap_to_spike']/60:.1f}min",
                     color=TC, fontsize=8, pad=5)
        ax1.set_xlabel("Seconds from 18:45 UTC", color=TC, fontsize=7)
        ax1.set_ylabel("Sigma", color=TC, fontsize=7)
        ax1.legend(fontsize=6, facecolor=BG2, edgecolor="#252a2e",
                  labelcolor=TC, loc="upper right")

        # Panel 2: PSD
        ax2 = fig.add_subplot(gs[row, 1])
        ax2.set_facecolor(BG2)
        ax2.tick_params(colors=DIM, labelsize=7)
        for sp in ax2.spines.values(): sp.set_color("#252a2e")

        f = sd["f_psd"][1:]  # skip DC
        p = sd["psd"][1:]
        ax2.semilogy(f, p, color=BLU, lw=1.0)

        # Mark Schumann resonances (1Hz data can only see up to 0.5Hz so Schumann not visible)
        # Mark ULF bands instead
        for freq, label in [(1/600, "Pc5\n600s"), (1/150, "Pc4\n150s"),
                            (1/45,  "Pc3\n45s"),  (1/10,  "Pc2\n10s"),
                            (1/3,   "Pc1\n3s")]:
            if freq < 0.49:
                ax2.axvline(freq, color=ORG, lw=0.7, ls=":", alpha=0.6)
                ax2.text(freq, p.max()*0.5, label, color=ORG,
                        fontsize=5, ha="center", va="top")

        ax2.set_title(f"{sid} Power Spectral Density\nULF pulsation bands marked",
                     color=TC, fontsize=8, pad=5)
        ax2.set_xlabel("Frequency (Hz)", color=TC, fontsize=7)
        ax2.set_ylabel("Power", color=TC, fontsize=7)
        ax2.set_xlim(0, 0.5)

        # Panel 3: Zoomed sigma around event ±10 min
        ax3 = fig.add_subplot(gs[row, 2])
        ax3.set_facecolor(BG2)
        ax3.tick_params(colors=DIM, labelsize=7)
        for sp in ax3.spines.values(): sp.set_color("#252a2e")

        lo = max(0, spike - 600); hi = min(len(secs), spike + 600)
        ax3.plot(secs[lo:hi], sd["sig_5"][lo:hi],
                color=RED, lw=0.7, alpha=0.9, label="5-sec sigma")
        ax3.plot(secs[lo:hi], sd["sig_60"][lo:hi],
                color=BLU, lw=1.0, alpha=0.8, label="60-sec sigma")
        ax3.axhline(2.0, color=RED, lw=0.7, ls="--", alpha=0.5)
        ax3.axvline(spike, color=GRN, lw=2.0, ls="--", alpha=0.9, label="19:17 UTC")

        ax3.set_title(f"{sid} ZOOMED ±10min around 19:17 UTC",
                     color=TC, fontsize=8, pad=5)
        ax3.set_xlabel("Seconds from 18:45 UTC", color=TC, fontsize=7)
        ax3.set_ylabel("Sigma", color=TC, fontsize=7)
        ax3.legend(fontsize=6, facecolor=BG2, edgecolor="#252a2e",
                  labelcolor=TC, loc="upper right")

    fig.suptitle(
        "USS NIMITZ 2004-11-14 -- 1-Second Resolution Magnetometer\n"
        "60x finer than previous analysis | ULF pulsation analysis | "
        "Green line = 19:17 UTC (instantaneous relocation)",
        color=TC, fontsize=10, y=0.97)

    png = os.path.join(OUT_DIR, "nimitz_1sec.png")
    plt.savefig(png, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()
    print(f"  Plot: {png}")

    # Summary
    print()
    print("="*60)
    print("  1-SECOND ANALYSIS SUMMARY")
    print("="*60)
    for sid, sd in station_data.items():
        print(f"  {sid}:")
        print(f"    5-sec peak in ±10min window: {sd['peak_tight']:.3f}s")
        print(f"    Gap to 19:17 UTC:            {sd['gap_to_spike']} sec "
              f"({sd['gap_to_spike']/60:.1f} min)")
        print(f"    5-sec peak in ±30min window: {sd['peak_5sec_near']:.3f}s")

    jp = os.path.join(OUT_DIR, "nimitz_1sec.json")
    clean = {sid: {k: float(v) if isinstance(v, (np.floating, np.integer)) else v
                   for k, v in {
                       "peak_tight": sd["peak_tight"],
                       "gap_to_spike_sec": sd["gap_to_spike"],
                       "peak_5sec_near": sd["peak_5sec_near"],
                       "peak_60sec_near": sd["peak_60sec_near"],
                   }.items()}
             for sid, sd in station_data.items()}
    with open(jp,"w",encoding="utf-8") as f:
        json.dump(clean, f, indent=2)
    print(f"  JSON: {jp}")
    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
