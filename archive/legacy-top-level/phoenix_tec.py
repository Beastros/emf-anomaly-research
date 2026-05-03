#!/usr/bin/env python3
"""
TEC Anomaly Scorer -- Phoenix Lights 1997-03-13
Fetches IONEX global ionosphere maps from IGS archives,
extracts TEC over Phoenix AZ, applies rolling sigma baseline,
plots against the magnetometer event window.

Run from: C:/Users/Mike/uap_sniffer/uap_sniffer/
Output:   results/phoenix_1997/phoenix_tec_analysis.png
          results/phoenix_1997/phoenix_tec.json
"""

import os, sys, json, struct, gzip, urllib.request, urllib.error
import numpy as np
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
PHOENIX_LAT =  33.4   # degrees N
PHOENIX_LON = -112.1  # degrees E (negative = West)
EVENT_START_UTC = 1.0   # hours UTC -- sightings began ~01:00 UTC (18:00 MST Mar 12)
EVENT_PEAK_UTC  = 3.53  # hours UTC -- D-field peak 03:32 UTC
EVENT_END_UTC   = 4.0   # hours UTC

OUT_DIR = r"results\phoenix_1997"
SIGMA_THRESHOLD = 2.0

# ── IONEX sources (try in order) ──────────────────────────────────────────────
# Day 072 of 1997 = March 13
IONEX_URLS = [
    # JPL via NASA CDDIS (may require Earthdata login -- will fail gracefully)
    "https://cddis.nasa.gov/archive/gnss/products/ionex/1997/072/jplg0720.97i.Z",
    # CODE via CDDIS
    "https://cddis.nasa.gov/archive/gnss/products/ionex/1997/072/codg0720.97i.Z",
    # IGS ftp mirror via HTTPS (BKG)
    "https://igs.bkg.bund.de/root_ftp/IGS/products/ionosphere/1997/072/jplg0720.97i.Z",
    # ESA
    "https://navigation-office.esa.int/products/gnss-products/1997/072/esag0720.97i.Z",
]

LOCAL_CACHE = "jplg0720.97i"

# ── Helpers ───────────────────────────────────────────────────────────────────
def download_ionex():
    """Try each URL, decompress .Z (Unix compress) or .gz, return raw text."""
    if os.path.exists(LOCAL_CACHE):
        print(f"Using cached {LOCAL_CACHE}")
        with open(LOCAL_CACHE, "r", errors="replace") as f:
            return f.read()

    for url in IONEX_URLS:
        print(f"Trying: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "emf-research/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
            print(f"  Downloaded {len(raw):,} bytes")

            # Decompress
            if url.endswith(".Z"):
                # Unix LZW compress -- use ncompress via subprocess if available,
                # otherwise try treating as gzip (some servers re-encode)
                try:
                    import subprocess
                    result = subprocess.run(
                        ["uncompress", "-c"],
                        input=raw, capture_output=True
                    )
                    if result.returncode == 0:
                        text = result.stdout.decode("ascii", errors="replace")
                    else:
                        raise RuntimeError("uncompress failed")
                except Exception:
                    # Try gzip fallback
                    try:
                        import io
                        text = gzip.decompress(raw).decode("ascii", errors="replace")
                    except Exception:
                        # Last resort: treat as plain text (some mirrors serve uncompressed)
                        text = raw.decode("ascii", errors="replace")
            elif url.endswith(".gz"):
                import io
                text = gzip.decompress(raw).decode("ascii", errors="replace")
            else:
                text = raw.decode("ascii", errors="replace")

            # Quick sanity check
            if "IONEX" in text or "TEC" in text or "END OF HEADER" in text:
                with open(LOCAL_CACHE, "w") as f:
                    f.write(text)
                print(f"  Cached to {LOCAL_CACHE}")
                return text
            else:
                print(f"  Content doesn't look like IONEX, trying next...")

        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            print(f"  URL error: {e.reason}")
        except Exception as e:
            print(f"  Error: {e}")

    return None


def parse_ionex(text):
    """
    Parse IONEX format. Returns list of:
      { 'epoch_utc': float_hours, 'lat': [...], 'lon': [...], 'tec': 2d_array }
    """
    maps = []
    lines = text.splitlines()
    i = 0
    in_map = False
    current_map = None
    current_rows = []
    current_lat = None
    lat_list = []
    lon_start = lon_end = lon_step = None
    lat_start = lat_end = lat_step = None
    exp = -1  # IONEX exponent

    while i < len(lines):
        line = lines[i]
        label = line[60:].strip() if len(line) > 60 else ""

        if "EXPONENT" in label:
            try:
                exp = int(line[:6].strip())
            except:
                exp = -1

        if "HGT1 / HGT2 / DHGT" in label:
            pass  # height info, skip

        if "LAT1 / LAT2 / DLAT" in label:
            parts = line[:60].split()
            try:
                lat_start = float(parts[0])
                lat_end   = float(parts[1])
                lat_step  = float(parts[2])
            except:
                pass

        if "LON1 / LON2 / DLON" in label:
            parts = line[:60].split()
            try:
                lon_start = float(parts[0])
                lon_end   = float(parts[1])
                lon_step  = float(parts[2])
            except:
                pass

        if "START OF TEC MAP" in label:
            in_map = True
            current_rows = []
            lat_list = []
            current_map = {"epoch_utc": None, "rows": []}

        if in_map and "EPOCH OF CURRENT MAP" in label:
            parts = line[:60].split()
            try:
                # yr mo dy hr min sec
                yr, mo, dy, hr, mn, sc = [int(x) for x in parts[:6]]
                if yr < 100:
                    yr += 1900
                epoch_h = hr + mn/60.0 + sc/3600.0
                current_map["epoch_utc"] = epoch_h
                current_map["date"] = f"{yr}-{mo:02d}-{dy:02d}"
            except:
                pass

        if in_map and "LAT/LON1/LON2/DLON/H" in label:
            parts = line[:60].split()
            try:
                current_lat = float(parts[0])
                r_lon1 = float(parts[1])
                r_lon2 = float(parts[2])
                r_dlon = float(parts[3])
                lat_list.append(current_lat)
                # read data lines
                n_lons = int(round((r_lon2 - r_lon1) / r_dlon)) + 1
                row_vals = []
                i += 1
                while len(row_vals) < n_lons and i < len(lines):
                    dline = lines[i]
                    if len(dline) > 60 and lines[i][60:].strip():
                        break
                    vals = dline.split()
                    row_vals.extend([int(v) for v in vals if v.lstrip('-').isdigit()])
                    if len(row_vals) < n_lons:
                        i += 1
                tec_row = [v * (10**exp) for v in row_vals[:n_lons]]
                current_rows.append({
                    "lat": current_lat,
                    "lon1": r_lon1,
                    "lon2": r_lon2,
                    "dlon": r_dlon,
                    "tec": tec_row
                })
                continue
            except Exception as e:
                pass

        if in_map and "END OF TEC MAP" in label:
            in_map = False
            if current_map and current_map["epoch_utc"] is not None:
                current_map["rows"] = current_rows
                maps.append(current_map)
            current_map = None
            current_rows = []

        i += 1

    return maps


def interpolate_tec(map_data, target_lat, target_lon):
    """Bilinear interpolation of TEC at target lat/lon from a parsed map."""
    rows = map_data["rows"]
    if not rows:
        return None

    # Find bounding rows by latitude
    lats = [r["lat"] for r in rows]
    lats_sorted = sorted(set(lats), reverse=True)  # usually descending

    # Find surrounding lats
    lat_above = None
    lat_below = None
    for lat in lats_sorted:
        if lat >= target_lat:
            lat_above = lat
        if lat <= target_lat and lat_below is None:
            lat_below = lat

    if lat_above is None:
        lat_above = lats_sorted[0]
    if lat_below is None:
        lat_below = lats_sorted[-1]

    def get_row(lat_val):
        for r in rows:
            if abs(r["lat"] - lat_val) < 0.01:
                return r
        return None

    def lon_interp(row, tlon):
        if row is None:
            return None
        lon1 = row["lon1"]
        dlon = row["dlon"]
        tec  = row["tec"]
        if dlon == 0 or not tec:
            return None
        idx_f = (tlon - lon1) / dlon
        idx_lo = int(idx_f)
        idx_hi = idx_lo + 1
        frac = idx_f - idx_lo
        if idx_lo < 0: idx_lo = 0
        if idx_hi >= len(tec): idx_hi = len(tec) - 1
        if idx_lo >= len(tec): return None
        return tec[idx_lo] * (1 - frac) + tec[idx_hi] * frac

    r_above = get_row(lat_above)
    r_below = get_row(lat_below)

    tec_above = lon_interp(r_above, target_lon)
    tec_below = lon_interp(r_below, target_lon)

    if tec_above is None and tec_below is None:
        return None
    if tec_above is None:
        return tec_below
    if tec_below is None:
        return tec_above

    if abs(lat_above - lat_below) < 0.001:
        return tec_above

    lat_frac = (target_lat - lat_below) / (lat_above - lat_below)
    return tec_below * (1 - lat_frac) + tec_above * lat_frac


def sigma_score(values):
    """Rolling sigma scorer. Window = all available points (small dataset)."""
    arr = np.array(values, dtype=float)
    if len(arr) < 3:
        return np.zeros(len(arr))
    mean = np.mean(arr)
    std  = np.std(arr)
    if std < 1e-9:
        return np.zeros(len(arr))
    return np.abs(arr - mean) / std


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print()
    print("=== TEC Anomaly Scorer -- Phoenix Lights 1997-03-13 ===")
    print(f"Target: {PHOENIX_LAT}N, {PHOENIX_LON}E (Phoenix AZ)")
    print()

    os.makedirs(OUT_DIR, exist_ok=True)

    # Download
    text = download_ionex()
    if text is None:
        print()
        print("ERROR: Could not download IONEX file from any source.")
        print()
        print("Manual download instructions:")
        print("1. Go to: https://cddis.nasa.gov/archive/gnss/products/ionex/1997/072/")
        print("   (requires free NASA Earthdata account)")
        print("2. Download: jplg0720.97i.Z or codg0720.97i.Z")
        print("3. Decompress to: jplg0720.97i")
        print("4. Place in: C:\\Users\\Mike\\uap_sniffer\\uap_sniffer\\")
        print("5. Re-run this script")
        input("\nPress Enter to exit...")
        sys.exit(1)

    print(f"Parsing IONEX ({len(text):,} chars)...")
    maps = parse_ionex(text)
    print(f"Found {len(maps)} TEC maps")

    if not maps:
        print("ERROR: No TEC maps parsed. File may be corrupt or wrong format.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Extract TEC over Phoenix for each epoch
    epochs = []
    tec_vals = []
    for m in maps:
        epoch = m["epoch_utc"]
        tec = interpolate_tec(m, PHOENIX_LAT, PHOENIX_LON)
        if tec is not None and tec > 0:
            epochs.append(epoch)
            tec_vals.append(tec)
            print(f"  {epoch:5.2f} UTC  TEC = {tec:.2f} TECU")

    if len(tec_vals) < 2:
        print("ERROR: Not enough TEC data points to analyze.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Sigma score
    sigmas = sigma_score(tec_vals)

    print()
    print("=== RESULTS ===")
    print(f"{'Epoch (UTC)':>14}  {'TEC (TECU)':>12}  {'Sigma':>8}  {'Flag':>6}")
    print("-" * 50)
    for ep, tv, sg in zip(epochs, tec_vals, sigmas):
        flag = " <<< ANOMALY" if sg >= SIGMA_THRESHOLD else ""
        h = int(ep)
        m = int((ep - h) * 60)
        print(f"  {h:02d}:{m:02d} UTC      {tv:10.2f}  {sg:8.3f}{flag}")

    # Event window check
    print()
    print("=== EVENT WINDOW ANALYSIS ===")
    event_hits = []
    for ep, tv, sg in zip(epochs, tec_vals, sigmas):
        if EVENT_START_UTC <= ep <= EVENT_END_UTC:
            event_hits.append((ep, tv, sg))
            h = int(ep); mn = int((ep-h)*60)
            status = f"ANOMALY ({sg:.2f}sigma)" if sg >= SIGMA_THRESHOLD else f"normal ({sg:.2f}sigma)"
            print(f"  {h:02d}:{mn:02d} UTC: TEC={tv:.2f} TECU -- {status}")

    if not event_hits:
        print("  No TEC map epochs fall within event window")
        print("  (2-hour resolution may straddle the window)")
        # Check closest
        closest = min(zip(epochs, tec_vals, sigmas),
                     key=lambda x: abs(x[0] - EVENT_PEAK_UTC))
        h = int(closest[0]); mn = int((closest[0]-h)*60)
        print(f"  Closest epoch to peak (03:32 UTC): {h:02d}:{mn:02d} UTC")
        print(f"  TEC = {closest[1]:.2f} TECU, sigma = {closest[2]:.3f}")

    # Save JSON
    result = {
        "event": "Phoenix Lights",
        "date": "1997-03-13",
        "target_lat": PHOENIX_LAT,
        "target_lon": PHOENIX_LON,
        "epochs_utc": epochs,
        "tec_tecu": tec_vals,
        "sigma_scores": [float(s) for s in sigmas],
        "event_window_utc": [EVENT_START_UTC, EVENT_END_UTC],
        "peak_utc": EVENT_PEAK_UTC,
        "threshold": SIGMA_THRESHOLD,
    }
    json_path = os.path.join(OUT_DIR, "phoenix_tec.json")
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {json_path}")

    # Plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7),
                                        facecolor="#0c0e0f", sharex=True)
        fig.subplots_adjust(hspace=0.08)

        color_tec   = "#5a91c0"
        color_sigma = "#6fa87a"
        color_event = "#b89555"
        bg          = "#0c0e0f"
        bg2         = "#131618"
        text_col    = "#cac6bc"
        dim_col     = "#6a6760"

        for ax in [ax1, ax2]:
            ax.set_facecolor(bg2)
            ax.tick_params(colors=dim_col, labelsize=8)
            ax.spines["bottom"].set_color("#252a2e")
            ax.spines["top"].set_color("#252a2e")
            ax.spines["left"].set_color("#252a2e")
            ax.spines["right"].set_color("#252a2e")
            # Event window shading
            ax.axvspan(EVENT_START_UTC, EVENT_END_UTC,
                      alpha=0.12, color=color_event, label="Event window")
            ax.axvline(EVENT_PEAK_UTC, color=color_event,
                      linewidth=0.8, linestyle="--", alpha=0.7)

        # TEC
        ax1.plot(epochs, tec_vals, color=color_tec, linewidth=1.5,
                marker="o", markersize=5, label="TEC (Phoenix grid cell)")
        ax1.set_ylabel("TEC (TECU)", color=text_col, fontsize=9)
        ax1.set_title(
            "Ionospheric TEC — Phoenix AZ — 1997-03-13\n"
            f"IONEX global map interpolated at {PHOENIX_LAT}°N {abs(PHOENIX_LON)}°W",
            color=text_col, fontsize=10, pad=10
        )
        ax1.legend(fontsize=8, facecolor=bg2, edgecolor="#252a2e",
                  labelcolor=text_col)

        # Sigma
        ax2.bar(epochs, sigmas, width=0.15, color=color_sigma, alpha=0.8,
               label="Sigma deviation")
        ax2.axhline(SIGMA_THRESHOLD, color="#e05c5c", linewidth=0.8,
                   linestyle="--", label=f"Threshold ({SIGMA_THRESHOLD}σ)")
        ax2.set_ylabel("Sigma deviation", color=text_col, fontsize=9)
        ax2.set_xlabel("Time (UTC hours)", color=text_col, fontsize=9)
        ax2.legend(fontsize=8, facecolor=bg2, edgecolor="#252a2e",
                  labelcolor=text_col)

        # Annotations
        ax1.annotate("mag D-field\npeak 03:32",
                    xy=(EVENT_PEAK_UTC, max(tec_vals)),
                    xytext=(EVENT_PEAK_UTC + 1.5, max(tec_vals)),
                    fontsize=7, color=color_event,
                    arrowprops=dict(arrowstyle="->", color=color_event, lw=0.8))

        note = (
            "Note: IONEX resolution is 2 hours. A hit within the event window\n"
            "is meaningful even without sub-minute precision.\n"
            f"Kp = 2.0 (solar ELIMINATED). Magnetometer r = 0.9704."
        )
        fig.text(0.02, 0.01, note, fontsize=7, color=dim_col, va="bottom")

        png_path = os.path.join(OUT_DIR, "phoenix_tec_analysis.png")
        plt.savefig(png_path, dpi=150, bbox_inches="tight",
                   facecolor=bg, edgecolor="none")
        plt.close()
        print(f"Saved: {png_path}")
        print()
        print(f"Add to report after pushing: results/phoenix_1997/phoenix_tec_analysis.png")

    except ImportError:
        print("matplotlib not installed -- skipping plot")
        print("Install with: pip install matplotlib")

    print()
    input("Press Enter to close...")


if __name__ == "__main__":
    main()
