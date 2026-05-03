import os, sys, json, subprocess, urllib.request, gzip, netrc, ssl
from datetime import date, datetime, timedelta, timezone
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
OUT_DIR   = os.path.join(WORK_DIR, "results", "nimitz_2004")
CACHE_DIR = os.path.join(WORK_DIR, "null_cache")
os.makedirs(OUT_DIR,   exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BG="#0c0e0f"; BG2="#131618"; BG3="#1a1e21"; TC="#cac6bc"; DIM="#6a6760"
RED="#e05c5c"; GRN="#6fa87a"; ORG="#b89555"; BLU="#5a91c0"; PRP="#c47ec4"
MONO="monospace"

HAPI_BASE = "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data"
KP_URL    = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
IONEX_URL = "https://cddis.nasa.gov/archive/gnss/products/ionex"

EVENT = {
    "name": "USS Nimitz", "date": date(2004, 11, 14),
    "lat": 32.5, "lon": -119.5, "kp_obs": 1.333,
}

SIGMA_WINDOW     = 20
MIN_BASELINE_PTS = 15
SIGMA_THRESHOLD  = 2.0
KP_GATE          = 3.0
N_CONTROL        = 80
YEAR_RANGE       = 6

CORRIDOR  = ["TUC", "BOU"]
EXTERNAL  = ["SIT", "CMO", "FRD", "SJG", "HON", "BRW"]
ALL_STATIONS = CORRIDOR + EXTERNAL

FETCH_START  = "16:30"
SCORE_START  = "17:00"
SCORE_END    = "22:00"
DATE_STR     = "2004-11-14"
EVENT_MONTH  = 11
EVENT_YEAR   = 2004
EVENT_DATE   = date(2004, 11, 14)
SPIKE_REF_MIN = 137   # 19:17 UTC - 17:00 = 137 min

STATION_LOCS = {
    "TUC": (32.17, -110.73), "BOU": (40.14, -105.24),
    "FRD": (38.21, -77.37),  "SIT": (57.06, -135.33),
    "CMO": (64.87, -147.86), "SJG": (18.11, -66.15),
    "HON": (21.32, -158.0),  "BRW": (71.32, -156.6),
}

print()
print("╔══════════════════════════════════════════════════════════════╗")
print("║   USS NIMITZ 2004-11-14 -- COMPREHENSIVE ANALYSIS v2       ║")
print("╚══════════════════════════════════════════════════════════════╝")
print()

def load_kp():
    cache = os.path.join(CACHE_DIR, "kp_full.json")
    if os.path.exists(cache):
        print("  Kp: cached")
        return json.load(open(cache, encoding="utf-8"))
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
            if sum(1 for v in vals if not np.isnan(v)) < 10: continue
            with open(cp,"w",encoding="utf-8") as f:
                json.dump({"v": vals, "times_str": tstr}, f)
            return np.array(vals), tstr
        except: continue
    return None, []

def in_score_window(t_str):
    try:
        h = int(t_str[11:13]); m = int(t_str[14:16])
        sh,sm = int(SCORE_START[:2]), int(SCORE_START[3:])
        eh,em = int(SCORE_END[:2]),   int(SCORE_END[3:])
        return (sh*60+sm) <= (h*60+m) <= (eh*60+em)
    except: return False

def rolling_sigma_scored(vals, tstr):
    arr = np.array(vals, dtype=float)
    out = np.zeros(len(arr))
    for i in range(len(arr)):
        w = arr[max(0, i-SIGMA_WINDOW):i]
        w = w[~np.isnan(w)]
        if len(w) < MIN_BASELINE_PTS: continue
        s = np.std(w)
        if s < 1e-6: continue
        if not np.isnan(arr[i]):
            out[i] = abs(arr[i] - np.mean(w)) / s
    return np.array([out[i] if in_score_window(tstr[i]) else 0.0
                     for i in range(len(arr))])

def get_window(vals, tstr, sig):
    wv=[]; ws=[]; wm=[]
    sh,sm = int(SCORE_START[:2]), int(SCORE_START[3:])
    for i, ts in enumerate(tstr):
        if not in_score_window(ts): continue
        try:
            h=int(ts[11:13]); m=int(ts[14:16])
            wv.append(vals[i]); ws.append(sig[i])
            wm.append((h*60+m)-(sh*60+sm))
        except: pass
    return np.array(wv), np.array(ws), np.array(wm)

def fetch_ionex_tec(date_obj, lat, lon):
    ds = date_obj.strftime("%Y-%m-%d")
    cache_key = f"tec_{ds}_{lat:.1f}_{lon:.1f}.json"
    cp = os.path.join(CACHE_DIR, cache_key)
    if os.path.exists(cp):
        try: return json.load(open(cp, encoding="utf-8"))
        except: pass

    year = date_obj.year
    doy  = date_obj.timetuple().tm_yday
    url  = f"{IONEX_URL}/{year}/{doy:03d}/jplg{doy:03d}0.{str(year)[2:]}i.Z"

    print(f"  Fetching IONEX: {url}")

    # Load Earthdata credentials
    login = os.environ.get("EARTHDATA_USER", "")
    pw    = os.environ.get("EARTHDATA_PASS", "")
    if not login:
        env_candidates = [
            os.path.join(WORK_DIR, ".env"),
            os.path.join(os.environ.get("USERPROFILE",""), "Desktop",
                         "Earthquake Feed Listener Engine", ".env"),
        ]
        for ep in env_candidates:
            if os.path.exists(ep):
                raw = open(ep,"rb").read().lstrip(b"\xef\xbb\xbf").decode("utf-8")
                for line in raw.splitlines():
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k,v = line.split("=",1)
                        if k.strip() == "EARTHDATA_USER": login = v.strip()
                        if k.strip() == "EARTHDATA_PASS": pw    = v.strip()
                break
    if not login:
        try:
            n = netrc.netrc()
            login, _, pw = n.authenticators("urs.earthdata.nasa.gov")
        except: pass

    if not login:
        print("  IONEX: No Earthdata credentials found -- skipping TEC")
        return None

    class EarthdataSession(requests.Session):
        def rebuild_auth(self, p, r):
            if self.auth: p.prepare_auth(self.auth, p.url)

    sess = EarthdataSession()
    sess.auth = (login, pw)

    try:
        r = sess.get(url, timeout=60, verify=False)
        if r.status_code != 200 or b"<html" in r.content[:200]:
            print(f"  IONEX fetch failed: HTTP {r.status_code}")
            return None
        raw = gzip.decompress(r.content).decode("ascii", errors="ignore")
    except Exception as e:
        print(f"  IONEX error: {e}")
        return None

    # Parse IONEX
    tec_maps = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "START OF TEC MAP" in line:
            epoch_hour = None; tec_grid = {}
            i += 1
            while i < len(lines) and "END OF TEC MAP" not in lines[i]:
                l = lines[i]
                if "EPOCH OF CURRENT MAP" in l:
                    parts = l.split()
                    try: epoch_hour = int(parts[3])
                    except: pass
                elif "LAT/LON1/LON2/DLON/H" in l:
                    try:
                        lat_map = float(l[2:8].strip())
                        lon1    = float(l[8:14].strip())
                        lon2    = float(l[14:20].strip())
                        dlon    = float(l[20:26].strip())
                        i += 1
                        row_vals = []
                        while i < len(lines) and "LAT/LON" not in lines[i] and "END" not in lines[i]:
                            row_vals.extend([int(x) for x in lines[i].split()
                                             if x.lstrip("-").isdigit()])
                            i += 1
                        lons = np.arange(lon1, lon2+dlon*0.5, dlon)
                        for j, lo in enumerate(lons[:len(row_vals)]):
                            if row_vals[j] != 9999:
                                tec_grid[(lat_map, lo)] = row_vals[j] / 10.0
                        continue
                    except: pass
                i += 1
            if epoch_hour is not None and tec_grid:
                tec_val = interp_tec(tec_grid, lat, lon)
                if tec_val is not None:
                    tec_maps.append([epoch_hour, tec_val])
        i += 1

    if tec_maps:
        with open(cp,"w",encoding="utf-8") as f: json.dump(tec_maps,f)
        print(f"  IONEX: {len(tec_maps)} maps parsed")
    return tec_maps if tec_maps else None

def interp_tec(grid, lat, lon):
    if not grid: return None
    lats = sorted(set(k[0] for k in grid))
    lons = sorted(set(k[1] for k in grid))
    try:
        lat1 = max(l for l in lats if l<=lat); lat2 = min(l for l in lats if l>=lat)
        lon1 = max(l for l in lons if l<=lon); lon2 = min(l for l in lons if l>=lon)
        vals = [grid.get((la,lo)) for la in [lat1,lat2] for lo in [lon1,lon2]]
        if any(v is None for v in vals): return None
        dlat=lat2-lat1; dlon=lon2-lon1
        if dlat<0.01 and dlon<0.01: return vals[0]
        if dlat<0.01:
            t=(lon-lon1)/dlon if dlon>0.01 else 0; return vals[0]*(1-t)+vals[1]*t
        if dlon<0.01:
            t=(lat-lat1)/dlat if dlat>0.01 else 0; return vals[0]*(1-t)+vals[2]*t
        t=(lat-lat1)/dlat; u=(lon-lon1)/dlon
        return vals[0]*(1-t)*(1-u)+vals[1]*(1-t)*u+vals[2]*t*(1-u)+vals[3]*t*u
    except: return None

def get_candidates(kp_index):
    candidates = []
    yr_lo = max(EVENT_YEAR-YEAR_RANGE, 1998)
    yr_hi = min(EVENT_YEAR+YEAR_RANGE, 2023)
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
    kp_index = load_kp()

    # STEP 1
    print("─"*60)
    print("STEP 1: SOLAR GATE")
    print("─"*60)
    event_kp = kp_index.get(DATE_STR, 99.0)
    print(f"  Kp: {event_kp:.3f} -- {'ELIMINATED' if event_kp<KP_GATE else 'POSSIBLE'}")

    # STEP 2
    print(); print("─"*60)
    print("STEP 2: MAGNETOMETER")
    print("─"*60)
    station_data = {}
    for sid in ALL_STATIONS:
        print(f"  Fetching {sid}...")
        v, ts = fetch_intermagnet(sid, EVENT_DATE, FETCH_START, SCORE_END)
        if v is not None:
            sig = rolling_sigma_scored(v, ts)
            wv, ws, wm = get_window(v, ts, sig)
            peak = float(np.max(ws)) if len(ws)>0 else 0
            exceed = int(np.sum(ws >= SIGMA_THRESHOLD))
            station_data[sid] = {"v":v,"ts":ts,"sig":sig,"wv":wv,"ws":ws,"wm":wm,
                                 "peak":peak,"exceed":exceed}
            print(f"    {sid}: peak={peak:.3f}s  exceed={exceed}")
            if len(ws)>0:
                peak_idx = np.argmax(ws)
                peak_min = wm[peak_idx] if len(wm)>peak_idx else -1
                ph = 17 + int(peak_min)//60; pm = int(peak_min)%60
                gap = abs(int(peak_min)-SPIKE_REF_MIN)
                print(f"    {sid}: peak at {ph:02d}:{pm:02d} UTC  gap from 19:17 = {gap} min")
        else:
            print(f"    {sid}: no data")

    # Corridor assessment
    print()
    cp_vals = [station_data[s]["peak"] for s in CORRIDOR if s in station_data]
    ex_vals = [station_data[s]["peak"] for s in EXTERNAL if s in station_data]
    if cp_vals and ex_vals:
        ratio = np.mean(cp_vals)/np.mean(ex_vals) if np.mean(ex_vals)>0.01 else 0
        print(f"  Corridor mean sigma: {np.mean(cp_vals):.3f}")
        print(f"  External mean sigma: {np.mean(ex_vals):.3f}")
        print(f"  Isolation ratio:     {ratio:.3f}")
        if ratio > 2.0:
            print("  --> Corridor significantly elevated vs external")
        else:
            print("  --> Corridor NOT isolated from external (ratio near 1.0)")

    # STEP 3
    print(); print("─"*60)
    print("STEP 3: IONEX TEC")
    print("─"*60)
    tec_data = fetch_ionex_tec(EVENT_DATE, EVENT["lat"], EVENT["lon"])
    tec_max_sigma = None
    if tec_data and len(tec_data) > 1:
        tec_arr = [t[1] for t in tec_data]
        tec_mean = np.mean(tec_arr); tec_std = np.std(tec_arr)
        print(f"  TEC at {EVENT['lat']}N, {EVENT['lon']}W:")
        for hour, tec in tec_data:
            sigma = (tec-tec_mean)/tec_std if tec_std>0 else 0
            flag = " <-- EVENT" if 17<=hour<=21 else ""
            print(f"    {hour:02d}:00 UTC: {tec:.1f} TECU  ({sigma:+.2f}s){flag}")
        event_sigmas = [abs((t[1]-tec_mean)/tec_std)
                        for t in tec_data if 17<=t[0]<=21]
        tec_max_sigma = max(event_sigmas) if event_sigmas else 0
        print(f"  Max TEC sigma in event window: {tec_max_sigma:.3f}")
        verdict = "ANOMALY" if tec_max_sigma>=2.0 else "no anomaly"
        print(f"  TEC verdict: {verdict}")
    else:
        print("  TEC: skipped or no data")

    # STEP 4
    print(); print("─"*60)
    print("STEP 4: NULL DISTRIBUTION")
    print("─"*60)
    print(f"  Building {N_CONTROL} control days...")
    candidates = get_candidates(kp_index)

    null_tuc=[]; null_bou=[]; null_coex=[]
    failed=0
    for cdate in candidates:
        if len(null_tuc) >= N_CONTROL: break
        t_res = None; b_res = None
        vt,tt = fetch_intermagnet("TUC",cdate,FETCH_START,SCORE_END)
        vb,tb = fetch_intermagnet("BOU",cdate,FETCH_START,SCORE_END)
        if vt is None or vb is None: failed+=1; continue
        st = rolling_sigma_scored(vt,tt)
        sb = rolling_sigma_scored(vb,tb)
        _,wst,_ = get_window(vt,tt,st)
        _,wsb,_ = get_window(vb,tb,sb)
        if len(wst)<5 or len(wsb)<5: failed+=1; continue
        null_tuc.append(float(np.max(wst)))
        null_bou.append(float(np.max(wsb)))
        n = min(len(wst),len(wsb))
        coex = sum(1 for i in range(n)
                   if wst[i]>=SIGMA_THRESHOLD and
                   any(wsb[max(0,i-10):min(n,i+11)]>=SIGMA_THRESHOLD))
        null_coex.append(coex)
        if len(null_tuc)%20==0: print(f"  {len(null_tuc)} controls...")

    n_ctrl = len(null_tuc)
    print(f"  Final: {n_ctrl} controls ({failed} failed)")

    ev_tuc = station_data.get("TUC",{}).get("peak",0)
    ev_bou = station_data.get("BOU",{}).get("peak",0)
    wst = station_data.get("TUC",{}).get("ws",np.array([]))
    wsb = station_data.get("BOU",{}).get("ws",np.array([]))
    n = min(len(wst),len(wsb))
    ev_coex = sum(1 for i in range(n)
                  if wst[i]>=SIGMA_THRESHOLD and
                  any(wsb[max(0,i-10):min(n,i+11)]>=SIGMA_THRESHOLD)) if n>0 else 0

    def pct(nd,obs): return float(stats.percentileofscore(np.array(nd),obs)) if nd else 0
    def zs(nd,obs):
        a=np.array(nd)
        return float((obs-np.mean(a))/np.std(a)) if len(a)>1 and np.std(a)>0 else 0

    print()
    print("="*68)
    print("  RESULTS -- ALL METRICS")
    print("="*68)
    print(f"  {'Metric':<28} {'Obs':>7} {'Mean':>7} {'p95':>7} {'Pct':>7} {'z':>6}")
    print(f"  {'─'*64}")

    metric_results=[]
    for mname,obs,nd in [
        ("TUC peak sigma",  ev_tuc,  null_tuc),
        ("BOU peak sigma",  ev_bou,  null_bou),
        ("Co-exceedances",  ev_coex, null_coex),
    ]:
        if not nd: continue
        p=pct(nd,obs); z=zs(nd,obs); p95=np.percentile(nd,95)
        flag=" ***" if p>=95 or p<=5 else ""
        print(f"  {mname:<28} {obs:>7.2f} {np.mean(nd):>7.2f} "
              f"{p95:>7.2f} {p:>7.1f} {z:>6.2f}{flag}")
        metric_results.append({"metric":mname,"obs":obs,"null":nd,"pct":p,"z":z,"p95":p95})

    # STEP 5: Plot
    print(); print("─"*60); print("STEP 5: PLOTTING"); print("─"*60)

    fig = plt.figure(figsize=(20,15), facecolor=BG)
    gs  = gridspec.GridSpec(3,3,figure=fig,hspace=0.5,wspace=0.35,
                            left=0.06,right=0.97,top=0.92,bottom=0.05)

    # Sigma time series per corridor station
    colors_corr=[RED,ORG]
    for col,(sid,col_c) in enumerate(zip(CORRIDOR,colors_corr)):
        ax = fig.add_subplot(gs[0,col])
        ax.set_facecolor(BG2)
        ax.tick_params(colors=DIM,labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#252a2e")
        if sid in station_data:
            ws=station_data[sid]["ws"]; wm=station_data[sid]["wm"]
            ax.plot(wm,ws,color=col_c,lw=1.3,label=f"{sid} sigma")
            ax.axhline(SIGMA_THRESHOLD,color=RED,lw=0.8,ls="--",alpha=0.7)
            ax.axvline(SPIKE_REF_MIN,color=GRN,lw=1.5,ls="--",alpha=0.9,
                      label="19:17 UTC")
            ax.axvspan(0,MIN_BASELINE_PTS,alpha=0.1,color=DIM)
        ax.set_title(f"{sid} Sigma\nNimitz 2004-11-14",color=TC,fontsize=8,pad=5)
        ax.set_xlabel("Min from 17:00 UTC",color=TC,fontsize=8)
        ax.set_ylabel("Sigma",color=TC,fontsize=8)
        ax.legend(fontsize=6.5,facecolor=BG2,edgecolor="#252a2e",labelcolor=TC)

    # External stations
    ax3=fig.add_subplot(gs[0,2])
    ax3.set_facecolor(BG2); ax3.tick_params(colors=DIM,labelsize=8)
    for sp in ax3.spines.values(): sp.set_color("#252a2e")
    ext_colors=[BLU,ORG,GRN,PRP,"#ff8844","#44ffcc"]
    for i,sid in enumerate(EXTERNAL):
        if sid not in station_data: continue
        ax3.plot(station_data[sid]["wm"],station_data[sid]["ws"],
                color=ext_colors[i%6],lw=0.9,alpha=0.75,label=sid)
    ax3.axhline(SIGMA_THRESHOLD,color=RED,lw=0.8,ls="--",alpha=0.7)
    ax3.axvline(SPIKE_REF_MIN,color=GRN,lw=1.5,ls="--",alpha=0.9)
    ax3.set_title("External Stations\n(flat = localized signal)",color=TC,fontsize=8,pad=5)
    ax3.set_xlabel("Min from 17:00 UTC",color=TC,fontsize=8)
    ax3.legend(fontsize=6,facecolor=BG2,edgecolor="#252a2e",labelcolor=TC,ncol=2)

    # Null histograms
    for col,res in enumerate(metric_results[:3]):
        ax=fig.add_subplot(gs[1,col])
        ax.set_facecolor(BG2); ax.tick_params(colors=DIM,labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#252a2e")
        nd=np.array(res["null"]); obs=res["obs"]
        n_bins=min(25,len(nd)//2)
        ax.hist(nd,bins=n_bins,color=BLU,alpha=0.65,edgecolor=BG,lw=0.3,
               label=f"Controls (n={len(nd)})")
        ax.axvline(res["p95"],color=ORG,lw=0.9,ls="--",alpha=0.7,
                  label=f"95th ({res['p95']:.2f})")
        flag=" ***" if res["pct"]>=95 or res["pct"]<=5 else ""
        ax.axvline(obs,color=RED,lw=2.5,zorder=6,
                  label=f"Nimitz: {obs:.2f} ({res['pct']:.0f}th){flag}")
        ax.set_title(f"Null: {res['metric']}",color=TC,fontsize=8,pad=5)
        ax.set_xlabel("Value",color=TC,fontsize=8); ax.set_ylabel("Count",color=TC,fontsize=8)
        ax.legend(fontsize=6.5,facecolor=BG2,edgecolor="#252a2e",labelcolor=TC)

    # Summary text
    ax7=fig.add_subplot(gs[2,:2])
    ax7.set_facecolor(BG2); ax7.axis("off")
    lines=[
        ("USS NIMITZ 2004-11-14 -- FINDINGS",TC,10,True),("",TC,7,False),
        (f"Kp={event_kp:.3f}  Solar: {'ELIMINATED' if event_kp<KP_GATE else 'POSSIBLE'}",
         GRN if event_kp<KP_GATE else RED,9,True),
        ("",TC,7,False),("MAGNETOMETER:",TC,9,True),
    ]
    for sid in ALL_STATIONS:
        if sid not in station_data: continue
        sd=station_data[sid]
        wm=sd["wm"]; ws=sd["ws"]
        if len(ws)==0: continue
        peak_min=wm[np.argmax(ws)] if len(wm)>0 else 0
        gap=abs(int(peak_min)-SPIKE_REF_MIN)
        ph=17+int(peak_min)//60; pm=int(peak_min)%60
        label="[CORRIDOR]" if sid in CORRIDOR else "[external]"
        lines.append((f"  {sid} {label}: peak={sd['peak']:.2f}s @ {ph:02d}:{pm:02d} UTC  "
                      f"gap={gap}min",TC,7.5,False))
    lines+=[("",TC,7,False),
            (f"Corridor mean: {np.mean(cp_vals):.3f}s  External mean: {np.mean(ex_vals):.3f}s  "
             f"Ratio: {np.mean(cp_vals)/np.mean(ex_vals):.3f}",TC,8,False),
            ("",TC,7,False),
            (f"TEC max sigma in event window: {tec_max_sigma:.3f}s" if tec_max_sigma is not None
             else "TEC: not fetched",
             GRN if (tec_max_sigma or 0)<2.0 else RED,8,False),
            ("",TC,7,False),("NULL TEST RESULTS:",TC,9,True)]
    for res in metric_results:
        flag=" ***" if res["pct"]>=95 or res["pct"]<=5 else ""
        lines.append((f"  {res['metric']}: {res['pct']:.0f}th pct  z={res['z']:.2f}{flag}",
                      RED if "***" in flag else TC,8,False))

    y=0.97
    for text,color,size,bold in lines:
        ax7.text(0.02,y,text,transform=ax7.transAxes,color=color,
                fontfamily=MONO,fontsize=size,fontweight="bold" if bold else "normal",va="top")
        y-=0.065

    # Station map
    ax8=fig.add_subplot(gs[2,2])
    ax8.set_facecolor(BG2); ax8.tick_params(colors=DIM,labelsize=7)
    for sp in ax8.spines.values(): sp.set_color("#252a2e")
    for sid,(slat,slon) in STATION_LOCS.items():
        pk=station_data.get(sid,{}).get("peak",0)
        color=RED if sid in CORRIDOR else BLU
        ax8.scatter(slon,slat,c=color,s=min(60+pk*25,350),zorder=5,
                   edgecolors="white",linewidths=0.5)
        ax8.text(slon+1.5,slat+0.5,f"{sid}\n{pk:.2f}s",color=TC,fontsize=5,ha="left")
    ax8.scatter(EVENT["lon"],EVENT["lat"],c=GRN,s=200,marker="*",zorder=6,
               edgecolors="white",linewidths=0.5)
    ax8.text(EVENT["lon"]+1,EVENT["lat"]-2,"Nimitz",color=GRN,fontsize=6)
    ax8.set_xlim(-180,-60); ax8.set_ylim(10,80)
    ax8.set_title("Station Map (dot size = peak sigma)",color=TC,fontsize=7,pad=5)

    fig.suptitle("USS NIMITZ 2004-11-14 -- Multi-Sensor Analysis\n"
                "Pre-registered metrics | INTERMAGNET HAPI | Warmup guard | Null-tested",
                color=TC,fontsize=10,y=0.96)

    png=os.path.join(OUT_DIR,"nimitz_comprehensive.png")
    plt.savefig(png,dpi=150,bbox_inches="tight",facecolor=BG,edgecolor="none")
    plt.close()
    print(f"  Plot: {png}")

    jp=os.path.join(OUT_DIR,"nimitz_comprehensive.json")
    out={"event":"USS Nimitz","date":DATE_STR,"kp":event_kp,
         "solar_eliminated":event_kp<KP_GATE,
         "corridor_mean":float(np.mean(cp_vals)) if cp_vals else None,
         "external_mean":float(np.mean(ex_vals)) if ex_vals else None,
         "isolation_ratio":float(np.mean(cp_vals)/np.mean(ex_vals)) if cp_vals and ex_vals and np.mean(ex_vals)>0 else None,
         "tec_max_event_sigma":tec_max_sigma,
         "null_results":[{k:v for k,v in r.items() if k!="null"} for r in metric_results],
         "station_peaks":{s:station_data[s]["peak"] for s in station_data}}
    with open(jp,"w",encoding="utf-8") as f:
        json.dump(out,f,indent=2,default=str)
    print(f"  JSON: {jp}")
    print(); print("  Done."); print()
    input("Press Enter to close...")

if __name__=="__main__":
    main()
