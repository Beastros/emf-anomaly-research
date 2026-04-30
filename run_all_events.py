import sys, os, json, datetime, requests
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec

# ── STYLING ───────────────────────────────────────────────────────────────────
BG="#030906"; GRN="#00ff41"; GDIM="#00aa2b"; GFNT="#011a06"
RED="#ff1a44"; AMB="#ffaa00"; BLU="#00aaff"; WHT="#c8ffd4"; DIM="#005c14"; MONO="monospace"

# ── ALL EVENTS ────────────────────────────────────────────────────────────────
EVENTS = [
    {
        "name":        "Stephenville_2008",
        "date":        "2008-01-08",
        "description": "Stephenville Texas — multiple pilot and civilian witnesses, FAA radar anomalies, F-16s scrambled. MUFON radar analysis found returns at 1900 mph.",
        "fetch_start": datetime.datetime(2008,1,8,22,0,  tzinfo=datetime.timezone.utc),
        "fetch_end":   datetime.datetime(2008,1,9, 4,0,  tzinfo=datetime.timezone.utc),
        "event_start": datetime.datetime(2008,1,8,23,0,  tzinfo=datetime.timezone.utc),
        "event_end":   datetime.datetime(2008,1,9, 1,30, tzinfo=datetime.timezone.utc),
        "spike_ref":   datetime.datetime(2008,1,9, 0,0,  tzinfo=datetime.timezone.utc),
        "ref_max_kmh": 1900,
        "ref_aircraft":"F-16 Fighting Falcon",
        "witnesses": [
            {"time":"2008-01-08T23:00:00Z","lat":32.22,"lon":-98.20,"desc":"Stephenville TX — pilot Steve Allen, large silent craft","conf":0.95},
            {"time":"2008-01-08T23:10:00Z","lat":32.18,"lon":-98.10,"desc":"Constable Lee Roy Gaitan — flashing lights, silent","conf":0.90},
            {"time":"2008-01-08T23:15:00Z","lat":32.15,"lon":-97.95,"desc":"Multiple Stephenville witnesses — formation of lights","conf":0.85},
            {"time":"2008-01-08T23:30:00Z","lat":32.38,"lon":-97.73,"desc":"Glen Rose TX — heading toward Crawford Ranch","conf":0.88},
            {"time":"2008-01-08T23:45:00Z","lat":32.54,"lon":-97.45,"desc":"Near Granbury TX — F-16s intercept attempt","conf":0.92},
            {"time":"2008-01-09T00:00:00Z","lat":32.75,"lon":-97.33,"desc":"Fort Worth corridor — radar track continues","conf":0.80},
        ],
        "mag_stations": ["SJG","FRD","BOU","DED"],
        "nexrad_stations": ["KFWS","KGRK","KDYX","KSJT"],
    },
    {
        "name":        "Nimitz_2004",
        "date":        "2004-11-14",
        "description": "USS Nimitz carrier group encounter off San Diego. SPY-1 radar tracked object for 2 weeks. FLIR footage later declassified by DoD. Fire control system reportedly jammed.",
        "fetch_start": datetime.datetime(2004,11,14,17,0, tzinfo=datetime.timezone.utc),
        "fetch_end":   datetime.datetime(2004,11,14,23,0, tzinfo=datetime.timezone.utc),
        "event_start": datetime.datetime(2004,11,14,18,45,tzinfo=datetime.timezone.utc),
        "event_end":   datetime.datetime(2004,11,14,20,0, tzinfo=datetime.timezone.utc),
        "spike_ref":   datetime.datetime(2004,11,14,19,17,tzinfo=datetime.timezone.utc),
        "ref_max_kmh": 1900,
        "ref_aircraft":"F/A-18 Super Hornet",
        "witnesses": [
            {"time":"2004-11-14T18:45:00Z","lat":32.50,"lon":-119.50,"desc":"USS Princeton SPY-1 radar contact initiated","conf":0.99},
            {"time":"2004-11-14T19:00:00Z","lat":32.48,"lon":-119.48,"desc":"Cmdr Fravor scrambled — visual contact","conf":0.98},
            {"time":"2004-11-14T19:10:00Z","lat":32.46,"lon":-119.45,"desc":"Fravor visual — Tic Tac, no wings, no exhaust","conf":0.98},
            {"time":"2004-11-14T19:15:00Z","lat":32.45,"lon":-119.43,"desc":"Object descends 80k ft to sea level — seconds","conf":0.97},
            {"time":"2004-11-14T19:17:00Z","lat":32.60,"lon":-119.00,"desc":"Object relocates 60 miles instantaneously","conf":0.96},
            {"time":"2004-11-14T19:30:00Z","lat":32.60,"lon":-119.00,"desc":"Second intercept — FLIR footage recorded","conf":0.99},
        ],
        "mag_stations": ["TUC","BOU","FRD","HON"],
        "nexrad_stations": ["KNKX","KVTX","KBBX","KESX"],
    },
    {
        "name":        "JAL1628_1986",
        "date":        "1986-11-17",
        "description": "JAL Flight 1628 tracked UFO for 50 minutes over Alaska. FAA formally investigated and confirmed radar returns. Pilot described object size of two aircraft carriers.",
        "fetch_start": datetime.datetime(1986,11,17,5,0,  tzinfo=datetime.timezone.utc),
        "fetch_end":   datetime.datetime(1986,11,17,11,0, tzinfo=datetime.timezone.utc),
        "event_start": datetime.datetime(1986,11,17,6,0,  tzinfo=datetime.timezone.utc),
        "event_end":   datetime.datetime(1986,11,17,7,30, tzinfo=datetime.timezone.utc),
        "spike_ref":   datetime.datetime(1986,11,17,6,30, tzinfo=datetime.timezone.utc),
        "ref_max_kmh": 900,
        "ref_aircraft":"Boeing 747-200",
        "witnesses": [
            {"time":"1986-11-17T06:00:00Z","lat":61.50,"lon":-141.00,"desc":"JAL 1628 first visual contact — two objects","conf":0.95},
            {"time":"1986-11-17T06:15:00Z","lat":62.00,"lon":-143.00,"desc":"Objects pace aircraft — Anchorage ATC confirms radar","conf":0.92},
            {"time":"1986-11-17T06:30:00Z","lat":62.50,"lon":-145.00,"desc":"Large object joins — estimated size 2 aircraft carriers","conf":0.90},
            {"time":"1986-11-17T06:45:00Z","lat":63.00,"lon":-147.00,"desc":"Anchorage requests military intercept — declined","conf":0.88},
            {"time":"1986-11-17T07:00:00Z","lat":63.50,"lon":-149.00,"desc":"Object disappears from radar as UA flight approaches","conf":0.85},
            {"time":"1986-11-17T07:20:00Z","lat":64.50,"lon":-147.00,"desc":"Fairbanks approach — object no longer visible","conf":0.80},
        ],
        "mag_stations": ["CMO","SIT","BRW","VIC"],
        "nexrad_stations": ["PAEC","PAPD","PAKC"],
    },
    {
        "name":        "OHare_2006",
        "date":        "2006-11-07",
        "description": "United Airlines employees and pilots observed metallic disc hovering under clouds at O'Hare. Shot upward through cloud layer leaving circular hole. Multiple aviation-credentialed witnesses.",
        "fetch_start": datetime.datetime(2006,11,7,15,0,  tzinfo=datetime.timezone.utc),
        "fetch_end":   datetime.datetime(2006,11,7,21,0,  tzinfo=datetime.timezone.utc),
        "event_start": datetime.datetime(2006,11,7,16,15, tzinfo=datetime.timezone.utc),
        "event_end":   datetime.datetime(2006,11,7,17,0,  tzinfo=datetime.timezone.utc),
        "spike_ref":   datetime.datetime(2006,11,7,16,30, tzinfo=datetime.timezone.utc),
        "ref_max_kmh": 500,
        "ref_aircraft":"Commercial airliner",
        "witnesses": [
            {"time":"2006-11-07T16:15:00Z","lat":41.978,"lon":-87.904,"desc":"United ramp workers — metallic disc, gate C17","conf":0.92},
            {"time":"2006-11-07T16:20:00Z","lat":41.978,"lon":-87.904,"desc":"United flight crew — disc hovering under 1900ft ceiling","conf":0.95},
            {"time":"2006-11-07T16:25:00Z","lat":41.978,"lon":-87.904,"desc":"Supervisor confirms sighting — multiple witnesses","conf":0.90},
            {"time":"2006-11-07T16:30:00Z","lat":41.980,"lon":-87.900,"desc":"Object shoots upward through clouds — circular hole left","conf":0.93},
        ],
        "mag_stations": ["FRD","BOU","STJ","OTT"],
        "nexrad_stations": ["KLOT","KGRR","KMKX","KDVN"],
    },
    {
        "name":        "Rendlesham_1980",
        "date":        "1980-12-26",
        "description": "RAF Bentwaters UK — USAF personnel witnessed structured craft over 3 nights. Lt Col Halt made live audio recording noting compass and radiation anomalies in real time.",
        "fetch_start": datetime.datetime(1980,12,26,0,0,  tzinfo=datetime.timezone.utc),
        "fetch_end":   datetime.datetime(1980,12,26,6,0,  tzinfo=datetime.timezone.utc),
        "event_start": datetime.datetime(1980,12,26,2,0,  tzinfo=datetime.timezone.utc),
        "event_end":   datetime.datetime(1980,12,26,4,0,  tzinfo=datetime.timezone.utc),
        "spike_ref":   datetime.datetime(1980,12,26,3,0,  tzinfo=datetime.timezone.utc),
        "ref_max_kmh": 500,
        "ref_aircraft":"Known aircraft",
        "witnesses": [
            {"time":"1980-12-26T02:00:00Z","lat":52.09,"lon":1.45,"desc":"Airman Burroughs — lights in Rendlesham Forest","conf":0.92},
            {"time":"1980-12-26T02:30:00Z","lat":52.09,"lon":1.44,"desc":"Penniston touches craft — geometric symbols noted","conf":0.88},
            {"time":"1980-12-26T03:00:00Z","lat":52.09,"lon":1.43,"desc":"Lt Col Halt — compass malfunction, radiation readings","conf":0.95},
            {"time":"1980-12-26T03:30:00Z","lat":52.09,"lon":1.42,"desc":"Halt audio recording — three starlike objects","conf":0.95},
        ],
        "mag_stations": ["HAD","ESK","LER","NGK"],
        "nexrad_stations": [],
    },
]

USGS_URL = "https://geomag.usgs.gov/ws/data/"

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
    a=np.sin(dlat/2)**2+np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def fetch_mag(station, start, end):
    params={"id":station,"starttime":start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"elements":"H,D,Z",
            "sampling_period":60,"format":"json","type":"definitive"}
    try:
        r=requests.get(USGS_URL,params=params,timeout=30)
        r.raise_for_status(); return r.json()
    except Exception as e:
        return None

def parse_mag(raw):
    if not raw: return None
    times=[datetime.datetime.fromisoformat(t.replace("Z","+00:00")) for t in raw.get("times",[])]
    fields={}
    for entry in raw.get("values",[]):
        fid=entry["id"]
        vals=np.array([float(v) if v is not None else np.nan for v in entry["values"]])
        if not np.all(np.isnan(vals)): fields[fid]=vals
    return {"times":times,"fields":fields} if fields else None

def rolling_score(arr, window=20):
    n=len(arr); score=np.zeros(n)
    for i in range(n):
        sl=arr[max(0,i-window):i]; valid=sl[~np.isnan(sl)]
        if len(valid)>=3:
            s=np.std(valid)
            score[i]=abs(arr[i]-np.mean(valid))/s if s>0.001 else 0
    return score

def normalize(arr):
    v=arr[~np.isnan(arr)]
    if len(v)==0: return arr
    mn=np.nanmean(v); sd=np.nanstd(v)
    return (arr-mn)/sd if sd>0.001 else arr-mn

def fetch_kp(year, month):
    url="https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
    try:
        r=requests.get(url,timeout=30)
        records=[]
        for line in r.text.split("\n"):
            if not line.strip() or line.startswith("#"): continue
            parts=line.split()
            if len(parts)<12: continue
            try:
                y,m,d=int(parts[0]),int(parts[1]),int(parts[2])
                if y!=year or m!=month: continue
                for h in range(8):
                    col=7+h
                    if col<len(parts):
                        kp=float(parts[col])
                        t=datetime.datetime(y,m,d,h*3,0,0,tzinfo=datetime.timezone.utc)
                        records.append({"time":t,"kp":kp})
            except: continue
        return records
    except: return []

def run_event(event):
    name = event["name"]
    print(f"\n{'='*60}")
    print(f"EVENT: {name}")
    print(f"Date:  {event['date']}")
    print(f"{'='*60}")

    out_dir = os.path.join("event_outputs", name)
    os.makedirs(out_dir, exist_ok=True)

    T0          = event["fetch_start"]
    event_start = event["event_start"]
    event_end   = event["event_end"]
    spike_ref   = event["spike_ref"]
    witnesses   = event["witnesses"]

    def t2min(t): return (t-T0).total_seconds()/60

    # ── Parse witness times ───────────────────────────────────────────────────
    for w in witnesses:
        if isinstance(w["time"],str):
            w["time"]=datetime.datetime.fromisoformat(w["time"].replace("Z","+00:00"))

    # ── Velocity profile ──────────────────────────────────────────────────────
    print(f"\n[1] Velocity profile...")
    segs=[]
    ref_max=event["ref_max_kmh"]
    valid_w=[w for w in witnesses if w.get("conf",1)>=0]
    for i in range(len(valid_w)-1):
        w1,w2=valid_w[i],valid_w[i+1]
        dt_h=(w2["time"]-w1["time"]).total_seconds()/3600
        dist=haversine_km(w1["lat"],w1["lon"],w2["lat"],w2["lon"])
        spd=dist/dt_h if dt_h>0 else 0
        segs.append({"from":w1["desc"][:30],"to":w2["desc"][:30],
                     "speed_kmh":round(spd,1),"dist_km":round(dist,1),"dt_min":round(dt_h*60,1)})
        flag=" *** EXCEEDS REF MAX" if spd>ref_max else ""
        print(f"    S{i+1}: {spd:.0f} km/h  ({dist:.0f}km in {dt_h*60:.0f}min){flag}")

    exceed=[s for s in segs if s["speed_kmh"]>ref_max]
    avg_spd=np.mean([s["speed_kmh"] for s in segs]) if segs else 0
    print(f"    Avg: {avg_spd:.0f} km/h  |  Exceeding {ref_max}: {len(exceed)}/{len(segs)}")

    # ── Fetch Kp ──────────────────────────────────────────────────────────────
    print(f"\n[2] Kp index...")
    kp_records=fetch_kp(T0.year, T0.month)
    pad=datetime.timedelta(hours=6)
    event_kp=[r for r in kp_records if event_start-pad<=r["time"]<=event_end+pad]
    max_kp=max([r["kp"] for r in event_kp]) if event_kp else None
    kp_quiet = max_kp is not None and max_kp < 3
    print(f"    Max Kp: {max_kp}  |  Quiet: {kp_quiet}  |  Solar explanation possible: {not kp_quiet}")

    # ── Fetch magnetometer stations ───────────────────────────────────────────
    print(f"\n[3] Magnetometer stations: {event['mag_stations']}")
    station_data={}
    COLORS=[RED,GRN,AMB,BLU,"#cc44ff","#ff8800"]
    station_colors={sid:COLORS[i%len(COLORS)] for i,sid in enumerate(event["mag_stations"])}

    for sid in event["mag_stations"]:
        print(f"    Fetching {sid}...")
        raw=fetch_mag(sid, event["fetch_start"], event["fetch_end"])
        data=parse_mag(raw)
        if data:
            station_data[sid]=data
            print(f"    {sid}: {len(data['times'])} minutes, fields={list(data['fields'].keys())}")
        else:
            print(f"    {sid}: no data")

    # ── Cross-correlation (first two stations) ────────────────────────────────
    corr_val=0; lag_val=0
    sids=list(station_data.keys())
    if len(sids)>=2:
        s1,s2=sids[0],sids[1]
        d1=station_data[s1]["fields"].get("D",np.array([]))
        d2=station_data[s2]["fields"].get("D",np.array([]))
        t1=station_data[s1]["times"]
        t2=station_data[s2]["times"]
        idx1=[i for i,t in enumerate(t1) if event_start<=t<=event_end]
        idx2=[i for i,t in enumerate(t2) if event_start<=t<=event_end]
        if idx1 and idx2:
            a=d1[idx1]; b=d2[idx2]; ml=min(len(a),len(b))
            a=a[:ml]; b=b[:ml]; vld=~(np.isnan(a)|np.isnan(b))
            if vld.sum()>5:
                corr_val=np.corrcoef(a[vld],b[vld])[0,1]
                max_lag=30; lags=list(range(-max_lag,max_lag+1)); xcorr=[]
                for lag in lags:
                    if lag>=0: aa=a[lag:]; bb=b[:len(aa)]
                    else:       aa=a[:lag]; bb=b[-lag:len(aa)-lag]
                    ml2=min(len(aa),len(bb))
                    if ml2>3:
                        v2=~(np.isnan(aa[:ml2])|np.isnan(bb[:ml2]))
                        xcorr.append(np.corrcoef(aa[:ml2][v2],bb[:ml2][v2])[0,1] if v2.sum()>3 else 0)
                    else: xcorr.append(0)
                best=np.argmax(np.abs(xcorr)); lag_val=lags[best]
                dist_s12=haversine_km(0,0,0,0)
                print(f"\n    {s1}-{s2} correlation: {corr_val:.4f}  lag={lag_val}min")

    # ── Generate plots ────────────────────────────────────────────────────────
    print(f"\n[4] Generating plots...")
    fig=plt.figure(figsize=(22,16),facecolor=BG)
    gs2=GridSpec(3,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)

    # Panel 1: All stations D-field normalized
    ax1=fig.add_subplot(gs2[0,:])
    ax1.set_facecolor("#010402"); ax1.tick_params(colors=DIM,labelsize=8)
    for sp in ax1.spines.values(): sp.set_color("#0a2211")
    ax1.axvspan(t2min(event_start),t2min(event_end),alpha=0.08,color=RED,label="Event window")
    ax1.axvline(t2min(spike_ref),color=RED,linewidth=2,alpha=0.9,label=f"Reference time {spike_ref.strftime('%H:%M UTC')}")
    for sid,data in station_data.items():
        if "D" not in data["fields"]: continue
        tmin=[t2min(t) for t in data["times"]]
        norm=normalize(data["fields"]["D"])
        ax1.plot(tmin,norm,color=station_colors[sid],linewidth=1.3,alpha=0.85,label=f"{sid} D-field")
    for w in valid_w:
        ax1.axvline(t2min(w["time"]),color=AMB,linewidth=0.5,alpha=0.4,linestyle="--")
    ax1.set_title(f"ALL STATIONS — D-FIELD NORMALIZED\n{name} — {event['description'][:80]}",
                 color=GRN,fontfamily=MONO,fontsize=8,pad=6)
    ax1.set_xlabel("Minutes from fetch start (UTC)",color=DIM,fontfamily=MONO,fontsize=7)
    ax1.set_ylabel("Normalized deviation",color=DIM,fontfamily=MONO,fontsize=7)
    ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=4,loc="upper left")

    # Panel 2: Sigma scores
    ax2=fig.add_subplot(gs2[1,:])
    ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=8)
    for sp in ax2.spines.values(): sp.set_color("#0a2211")
    ax2.axvspan(t2min(event_start),t2min(event_end),alpha=0.08,color=RED)
    ax2.axvline(t2min(spike_ref),color=RED,linewidth=2,alpha=0.8)
    ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
    ax2.axhline(3.0,color=RED,linewidth=0.5,linestyle=":",alpha=0.5,label="3sigma")
    for sid,data in station_data.items():
        if "D" not in data["fields"]: continue
        tmin=[t2min(t) for t in data["times"]]
        sc=rolling_score(data["fields"]["D"])
        ax2.plot(tmin,sc,color=station_colors[sid],linewidth=1.2,alpha=0.85,label=f"{sid} sigma")
    for w in valid_w:
        ax2.axvline(t2min(w["time"]),color=AMB,linewidth=0.5,alpha=0.4,linestyle="--")
    ax2.set_title("ANOMALY SCORE (sigma) — D-FIELD ALL STATIONS",color=GRN,fontfamily=MONO,fontsize=8,pad=6)
    ax2.set_xlabel("Minutes from fetch start",color=DIM,fontfamily=MONO,fontsize=7)
    ax2.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=7)
    ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=3,loc="upper right")
    ax2.set_ylim(bottom=0)

    # Panel 3: Speed profile
    ax3=fig.add_subplot(gs2[2,0])
    ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=8)
    for sp in ax3.spines.values(): sp.set_color("#0a2211")
    if segs:
        labels=[f"S{i+1}" for i in range(len(segs))]
        speeds=[s["speed_kmh"] for s in segs]
        colors2=[RED if s>ref_max else AMB if s>ref_max*0.7 else GRN for s in speeds]
        bars=ax3.bar(labels,speeds,color=colors2,edgecolor=BG,linewidth=0.5)
        ax3.axhline(ref_max,color=RED,linewidth=1,linestyle="--",alpha=0.8,label=f"Ref max {ref_max}")
        for bar,spd in zip(bars,speeds):
            ax3.text(bar.get_x()+bar.get_width()/2,bar.get_height()+10,f"{spd:.0f}",
                    ha="center",va="bottom",color=WHT,fontsize=7,fontfamily=MONO)
    ax3.set_title(f"SPEED PROFILE\n{event['ref_aircraft']} max={ref_max} km/h",color=GRN,fontfamily=MONO,fontsize=8)
    ax3.set_ylabel("km/h",color=DIM,fontfamily=MONO,fontsize=7)
    ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=DIM,fontsize=7)
    if segs: ax3.set_ylim(0,max(speeds)*1.2)

    # Panel 4: Findings summary
    ax4=fig.add_subplot(gs2[2,1])
    ax4.set_facecolor("#010402"); ax4.axis("off")
    for sp in ax4.spines.values(): sp.set_color(RED if corr_val>0.85 else GDIM)
    lines=[
        (f"EVENT: {name}", GRN, 9, True),
        (f"Date: {event['date']}", WHT, 8, False),
        ("", WHT, 7, False),
        (f"Stations fetched: {len(station_data)}/{len(event['mag_stations'])}", GRN if station_data else RED, 8, False),
        (f"Kp max: {max_kp}  Quiet: {kp_quiet}", GRN if kp_quiet else RED, 8, True),
        (f"Solar explanation: {'ELIMINATED' if kp_quiet else 'POSSIBLE'}", GRN if kp_quiet else AMB, 8, True),
        ("", WHT, 7, False),
        (f"Velocity avg: {avg_spd:.0f} km/h", WHT, 8, False),
        (f"Segments > ref max: {len(exceed)}/{len(segs)}", RED if exceed else GRN, 8, True),
        ("", WHT, 7, False),
        (f"Station correlation: {corr_val:.4f}", RED if corr_val>0.85 else AMB if corr_val>0.6 else WHT, 9, True),
        (f"Lag: {lag_val} min", WHT, 8, False),
        ("", WHT, 7, False),
        ("VERDICT:", AMB, 9, True),
    ]
    if corr_val>0.85 and kp_quiet:
        lines.append(("HIGH CORRELATION + QUIET Kp", RED, 9, True))
        lines.append(("= LOCALIZED NON-SOLAR SOURCE", RED, 8, True))
        lines.append(("Consistent with Phoenix pattern", AMB, 8, False))
    elif corr_val>0.6:
        lines.append(("MODERATE CORRELATION", AMB, 8, True))
        lines.append(("Warrants further investigation", AMB, 8, False))
    else:
        lines.append(("LOW CORRELATION", GRN, 8, False))
        lines.append(("Disturbance may be localized", GRN, 8, False))
        lines.append(("or stations too far apart", GRN, 8, False))

    y=0.97
    for text,color,size,bold in lines:
        ax4.text(0.05,y,text,transform=ax4.transAxes,color=color,fontfamily=MONO,
                fontsize=size,fontweight="bold" if bold else "normal",va="top")
        y-=0.055

    fig.suptitle(f"UAP SNIFFER — {name.upper().replace('_',' ')} — {event['date']}\n{event['description'][:100]}",
                color=GRN,fontfamily=MONO,fontsize=10,y=0.97)

    plot_path=os.path.join(out_dir,f"{name}_analysis.png")
    plt.savefig(plot_path,dpi=150,bbox_inches="tight",facecolor=BG)
    plt.close()
    print(f"    Plot saved: {plot_path}")

    # ── Save JSON summary ─────────────────────────────────────────────────────
    summary={
        "event":       name,
        "date":        event["date"],
        "description": event["description"],
        "velocity": {
            "avg_kmh":      round(avg_spd,1),
            "ref_max_kmh":  ref_max,
            "ref_aircraft": event["ref_aircraft"],
            "segments_exceeding": len(exceed),
            "total_segments":     len(segs),
            "segments":           segs,
        },
        "kp": {
            "max_kp":           max_kp,
            "quiet":            kp_quiet,
            "solar_possible":   not kp_quiet,
        },
        "magnetometer": {
            "stations_fetched":  list(station_data.keys()),
            "stations_failed":   [s for s in event["mag_stations"] if s not in station_data],
            "primary_correlation": round(float(corr_val),4),
            "primary_lag_min":     lag_val,
            "peak_sigmas":         {},
        },
        "verdict": "",
    }

    for sid,data in station_data.items():
        if "D" in data["fields"]:
            sc=rolling_score(data["fields"]["D"])
            idx=[i for i,t in enumerate(data["times"]) if event_start<=t<=event_end]
            if idx:
                peak=float(np.max(sc[idx]))
                peak_t=data["times"][idx[np.argmax(sc[idx])]]
                summary["magnetometer"]["peak_sigmas"][sid]={
                    "peak_sigma": round(peak,3),
                    "peak_time":  peak_t.isoformat(),
                }

    if corr_val>0.85 and kp_quiet:
        summary["verdict"]="HIGH ANOMALY — High cross-station correlation during quiet Kp. Pattern consistent with Phoenix Lights. Non-solar localized EM disturbance."
    elif corr_val>0.6 or (exceed and kp_quiet):
        summary["verdict"]="MODERATE ANOMALY — Warrants deeper analysis. Some indicators present."
    else:
        summary["verdict"]="LOW ANOMALY — No strong multi-sensor convergence detected. May require different station selection."

    json_path=os.path.join(out_dir,f"{name}_summary.json")
    with open(json_path,"w") as f:
        json.dump(summary,f,indent=2,default=str)
    print(f"    Summary saved: {json_path}")

    print(f"\n    VERDICT: {summary['verdict']}")
    return summary

# ── MAIN ──────────────────────────────────────────────────────────────────────
print("""
╔══════════════════════════════════════════════════════════════╗
║         UAP SNIFFER — MULTI-EVENT BATCH ANALYSIS            ║
║         Running all events — outputs per folder             ║
╚══════════════════════════════════════════════════════════════╝
""")
print(f"Events to run: {len(EVENTS)}")
for e in EVENTS: print(f"  - {e['name']} ({e['date']})")

os.makedirs("event_outputs", exist_ok=True)
all_summaries=[]

for event in EVENTS:
    try:
        summary=run_event(event)
        all_summaries.append(summary)
    except Exception as ex:
        import traceback
        print(f"\nERROR on {event['name']}: {ex}")
        traceback.print_exc()

# ── Master comparison report ──────────────────────────────────────────────────
print(f"\n{'='*60}")
print("MASTER COMPARISON REPORT")
print(f"{'='*60}")
for s in all_summaries:
    mag=s.get("magnetometer",{})
    kp=s.get("kp",{})
    vel=s.get("velocity",{})
    print(f"\n{s['event']}")
    print(f"  Kp={kp.get('max_kp')}  quiet={kp.get('quiet')}")
    print(f"  Correlation={mag.get('primary_correlation')}  lag={mag.get('primary_lag_min')}min")
    print(f"  Speed exceed ref: {vel.get('segments_exceeding')}/{vel.get('total_segments')}")
    print(f"  VERDICT: {s.get('verdict','')[:80]}")

with open("event_outputs/master_comparison.json","w") as f:
    json.dump(all_summaries,f,indent=2,default=str)
print(f"\nMaster comparison saved: event_outputs/master_comparison.json")
print("\nDone. Paste the contents of each event_outputs/[event]/ folder back for analysis.")
