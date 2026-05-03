import os, sys, json, subprocess

def pip(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)

pip("requests"); pip("unlzw3"); pip("numpy"); pip("matplotlib")

import requests
import numpy as np
try:
    from unlzw3 import unlzw
    HAS_UNLZW = True
except ImportError:
    HAS_UNLZW = False

WORK_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    candidates = [
        os.path.join(WORK_DIR, ".env"),
        os.path.join(WORK_DIR, "_env"),
        os.path.join(os.environ.get("USERPROFILE",""), "Desktop",
                     "Earthquake Feed Listener Engine", ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            raw = open(path, "rb").read().lstrip(b"\xef\xbb\xbf").decode("utf-8")
            for line in raw.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            print(f"Credentials from: {path}")
            return True
    return False

class EarthdataSession(requests.Session):
    def rebuild_auth(self, prepared_request, response):
        if self.auth:
            prepared_request.prepare_auth(self.auth, prepared_request.url)

EVENTS = [
    {
        "name": "Nimitz",       "date": "2004-11-14",
        "year": 2004, "doy": 319, "yr2": "04",
        "lat": 32.0,  "lon": -117.0,
        "label": "USS Nimitz -- off San Diego CA",
        "out_dir": "nimitz_2004",
        "event_utc": [0.0, 24.0], "peak_utc": None,
    },
    {
        "name": "OHare",        "date": "2006-11-07",
        "year": 2006, "doy": 311, "yr2": "06",
        "lat": 41.98, "lon": -87.9,
        "label": "O'Hare Airport -- Chicago IL",
        "out_dir": "ohare_2006",
        "event_utc": [15.0, 19.0], "peak_utc": 17.5,
    },
    {
        "name": "MH370",        "date": "2014-03-07",
        "year": 2014, "doy": 66,  "yr2": "14",
        "lat": 6.9,   "lon": 103.6,
        "label": "MH370 -- transponder-off position",
        "out_dir": "mh370_2014",
        "event_utc": [16.0, 18.5], "peak_utc": 17.35,
    },
    {
        "name": "Stephenville", "date": "2008-01-08",
        "year": 2008, "doy": 8,   "yr2": "08",
        "lat": 32.22, "lon": -98.2,
        "label": "Stephenville TX",
        "out_dir": "stephenville_2008",
        "event_utc": [0.0, 6.0], "peak_utc": 2.0,
    },
]

def download_ionex(year, doy, yr2, user, passwd):
    fname = f"jplg{doy:03d}0.{yr2}i.Z"
    url   = f"https://cddis.nasa.gov/archive/gnss/products/ionex/{year}/{doy:03d}/{fname}"
    cache = os.path.join(WORK_DIR, fname.replace(".Z", ""))

    if os.path.exists(cache) and os.path.getsize(cache) > 50000:
        print(f"  Cached: {cache}")
        return open(cache, "r", encoding="ascii", errors="replace").read()

    print(f"  Downloading: {url}")
    sess = EarthdataSession()
    sess.auth = (user, passwd)
    try:
        r = sess.get(url, timeout=60)
    except Exception as e:
        print(f"  Error: {e}"); return None

    if "text/html" in r.headers.get("Content-Type","") or r.content[:1] == b"<":
        print(f"  Auth failed"); return None
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}"); return None

    raw = r.content
    print(f"  Downloaded {len(raw):,} bytes")
    if HAS_UNLZW:
        try:
            text = unlzw(raw).decode("ascii", errors="replace")
        except Exception as e:
            print(f"  Decompress error: {e}"); return None
    else:
        import gzip
        try:
            text = gzip.decompress(raw).decode("ascii", errors="replace")
        except Exception:
            text = raw.decode("ascii", errors="replace")

    print(f"  Decompressed: {len(text):,} chars")
    with open(cache, "w", encoding="utf-8") as f:
        f.write(text)
    return text

def parse_ionex(text):
    """
    Parse IONEX format.
    KEY FIXES:
    - Use fixed-width columns for LAT/LON header (lat+lon1 merge when no space between)
    - Break data reading only when col-60 label contains LETTERS (not just any content)
    """
    maps = []
    lines = text.splitlines()
    i = 0
    exp = -1
    in_map = False
    cur_map = None
    cur_rows = []

    while i < len(lines):
        line = lines[i]
        label = line[60:].strip() if len(line) > 60 else ""

        if "EXPONENT" in label:
            try: exp = int(line[:60].strip())
            except: pass

        if "START OF TEC MAP" in label:
            in_map = True
            cur_rows = []
            cur_map = {"epoch_utc": None, "rows": []}

        if in_map and "EPOCH OF CURRENT MAP" in label:
            parts = line[:60].split()
            try:
                yr,mo,dy,hr,mn,sc = [int(x) for x in parts[:6]]
                cur_map["epoch_utc"] = hr + mn/60.0 + sc/3600.0
            except: pass

        if in_map and "LAT/LON1/LON2/DLON/H" in label:
            # FIX 1: Use fixed-width columns -- lat and lon1 often touch with no space
            # IONEX spec: 8X, 5F6.1  (8 spaces padding, then 5 floats of width 6)
            try:
                lat  = float(line[2:8].strip())
                lon1 = float(line[8:14].strip())
                lon2 = float(line[14:20].strip())
                dlon = float(line[20:26].strip())
                n_lon = int(round((lon2 - lon1) / dlon)) + 1

                vals = []
                i += 1
                while len(vals) < n_lon and i < len(lines):
                    dl = lines[i]
                    # FIX 2: break only when col-60+ label contains LETTERS
                    # Data lines have numbers past col 60 -- that's fine, keep reading
                    lbl60 = dl[60:].strip() if len(dl) > 60 else ""
                    if lbl60 and any(c.isalpha() for c in lbl60):
                        break
                    for tok in dl.split():
                        if tok.lstrip("-").isdigit():
                            vals.append(int(tok))
                    if len(vals) < n_lon:
                        i += 1

                scale = 10 ** exp
                tec_row = [v * scale for v in vals[:n_lon]]
                cur_rows.append({
                    "lat": lat, "lon1": lon1, "lon2": lon2,
                    "dlon": dlon, "tec": tec_row, "n_lon": n_lon,
                    "got": len(vals)
                })
                continue
            except Exception as e:
                pass

        if in_map and "END OF TEC MAP" in label:
            in_map = False
            if cur_map and cur_map["epoch_utc"] is not None:
                cur_map["rows"] = cur_rows
                maps.append(cur_map)

        i += 1

    return maps

def interp_tec(map_data, tlat, tlon):
    rows = map_data["rows"]
    if not rows: return None

    lats = sorted(set(r["lat"] for r in rows), reverse=True)
    la = next((l for l in lats if l >= tlat), lats[0])
    lb = next((l for l in reversed(lats) if l <= tlat), lats[-1])

    def row_at(lv):
        return next((r for r in rows if abs(r["lat"] - lv) < 0.01), None)

    def lon_interp(row):
        if not row or not row["tec"]: return None
        tl = max(row["lon1"], min(tlon, row["lon2"]))
        idx_f = (tl - row["lon1"]) / row["dlon"]
        i0 = max(0, min(int(idx_f), len(row["tec"]) - 2))
        frac = idx_f - int(idx_f)
        return row["tec"][i0] * (1-frac) + row["tec"][i0+1] * frac

    va = lon_interp(row_at(la))
    vb = lon_interp(row_at(lb))
    if va is None: return vb
    if vb is None: return va
    if abs(la - lb) < 0.001: return va
    f = (tlat - lb) / (la - lb)
    return vb*(1-f) + va*f

def sigma_score(vals):
    arr = np.array(vals, dtype=float)
    if len(arr) < 3: return np.zeros(len(arr))
    m, s = np.mean(arr), np.std(arr)
    if s < 1e-9: return np.zeros(len(arr))
    return np.abs(arr - m) / s

def make_plot(ev, epochs, tec_vals, sigmas, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BG="#0c0e0f"; BG2="#131618"; TC="#cac6bc"; DIM="#6a6760"
    BLU="#5a91c0"; GRN="#6fa87a"; ORG="#b89555"; RED="#e05c5c"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), facecolor=BG, sharex=True)
    fig.subplots_adjust(hspace=0.06)
    for ax in [ax1, ax2]:
        ax.set_facecolor(BG2)
        ax.tick_params(colors=DIM, labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#252a2e")
        es, ee = ev["event_utc"]
        ax.axvspan(es, ee, alpha=0.12, color=ORG)
        if ev["peak_utc"]:
            ax.axvline(ev["peak_utc"], color=ORG, lw=0.8, ls="--", alpha=0.8)

    ax1.plot(epochs, tec_vals, color=BLU, lw=1.5, marker="o", ms=4)
    ax1.set_ylabel("VTEC (TECU)", color=TC, fontsize=9)
    lon_lbl = f"{abs(ev['lon'])}deg {'W' if ev['lon']<0 else 'E'}"
    ax1.set_title(
        f"Ionospheric TEC -- {ev['label']} -- {ev['date']}\n"
        f"IONEX JPLG interpolated at {ev['lat']}N {lon_lbl}",
        color=TC, fontsize=9, pad=8)

    ax2.bar(epochs, sigmas, width=0.15, color=GRN, alpha=0.8)
    ax2.axhline(2.0, color=RED, lw=0.8, ls="--")
    for ep, sg in zip(epochs, sigmas):
        if sg >= 2.0:
            ax2.annotate(f"{sg:.1f}s", xy=(ep, sg),
                        xytext=(ep, sg+0.05), fontsize=7, color=RED, ha="center")
    ax2.set_ylabel("Sigma", color=TC, fontsize=9)
    ax2.set_xlabel("Time (UTC hours)", color=TC, fontsize=9)
    fig.text(0.01, 0.005,
             "Shaded = event window | Dashed = event peak | Red = 2.0s threshold",
             fontsize=7, color=DIM, va="bottom")

    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close()

def main():
    print()
    print("=== IONEX TEC Analyzer v3 ===")
    print()

    if not load_env():
        print("ERROR: no .env found")
        input("Press Enter..."); sys.exit(1)

    user   = os.environ.get("EARTHDATA_USER","")
    passwd = os.environ.get("EARTHDATA_PASS","")
    if not user:
        print("ERROR: no credentials"); input("Press Enter..."); sys.exit(1)
    print(f"User: {user}\n")

    summary = []

    for ev in EVENTS:
        print(f"--- {ev['name']} ({ev['date']}) ---")
        out_dir = os.path.join(WORK_DIR, "results", ev["out_dir"])
        os.makedirs(out_dir, exist_ok=True)

        text = download_ionex(ev["year"], ev["doy"], ev["yr2"], user, passwd)
        if not text:
            summary.append({"event": ev["name"], "status": "download_failed"})
            print(); continue

        maps = parse_ionex(text)
        print(f"  Parsed {len(maps)} maps")

        if maps:
            r0 = maps[0]["rows"][0] if maps[0]["rows"] else None
            if r0:
                print(f"  Grid: lat={r0['lat']} lon1={r0['lon1']} "
                      f"lon2={r0['lon2']} dlon={r0['dlon']} "
                      f"n_expected={r0['n_lon']} n_got={r0['got']}")

        epochs, tec_vals = [], []
        for m in maps:
            tec = interp_tec(m, ev["lat"], ev["lon"])
            if tec is not None and tec > 0:
                epochs.append(m["epoch_utc"])
                tec_vals.append(tec)

        if len(tec_vals) < 3:
            print(f"  Only {len(tec_vals)} valid TEC points")
            summary.append({"event": ev["name"], "status": "insufficient_data",
                            "points": len(tec_vals)})
            print(); continue

        sigmas = sigma_score(tec_vals)
        hits = []
        es, ee = ev["event_utc"]

        print(f"\n  {'UTC':>8}  {'TEC (TECU)':>12}  {'Sigma':>8}  Flag")
        print(f"  {'-'*46}")
        for ep, tv, sg in zip(epochs, tec_vals, sigmas):
            flag = " <<< ANOMALY" if sg >= 2.0 else ""
            h = int(ep); mn2 = int((ep-h)*60)
            print(f"  {h:02d}:{mn2:02d}      {tv:10.3f}  {sg:8.3f}{flag}")
            if es <= ep <= ee and sg >= 2.0:
                hits.append({"epoch_utc": ep, "tec": tv, "sigma": float(sg)})

        png = os.path.join(out_dir, f"{ev['out_dir']}_tec_analysis.png")
        try:
            make_plot(ev, epochs, tec_vals, sigmas, png)
            print(f"\n  Plot: {png}")
        except Exception as e:
            print(f"\n  Plot error: {e}")

        result = {
            "event": ev["name"], "date": ev["date"],
            "lat": ev["lat"], "lon": ev["lon"],
            "epochs_utc": epochs, "tec_tecu": tec_vals,
            "sigma_scores": [float(s) for s in sigmas],
            "event_window_utc": ev["event_utc"],
            "event_hits": hits,
        }
        jp = os.path.join(out_dir, f"{ev['out_dir']}_tec.json")
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"  JSON: {jp}")

        summary.append({
            "event": ev["name"], "date": ev["date"],
            "hits": len(hits), "max_sigma": float(max(sigmas)), "status": "ok"
        })
        print()

    print("\n=== SUMMARY ===")
    print(f"  {'Event':<15} {'Status':<18} {'Window hits':>12} {'Max sigma':>10}")
    print(f"  {'-'*58}")
    for r in summary:
        hits = str(r.get("hits","-"))
        sig  = f"{r.get('max_sigma',0):.3f}" if r.get("max_sigma") else "-"
        print(f"  {r['event']:<15} {r['status']:<18} {hits:>12} {sig:>10}")

    print()
    input("Press Enter to close...")

if __name__ == "__main__":
    main()
