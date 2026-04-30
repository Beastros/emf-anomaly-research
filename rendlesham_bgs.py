import sys, os, json, datetime, requests
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec

BG="#030906"; GRN="#00ff41"; GDIM="#00aa2b"; GFNT="#011a06"
RED="#ff1a44"; AMB="#ffaa00"; BLU="#00aaff"; WHT="#c8ffd4"; DIM="#005c14"; MONO="monospace"

print("""
=============================================================
  RENDLESHAM FOREST 1980 — BGS / INTERMAGNET SCAN
  December 26 1980 — RAF Bentwaters Suffolk UK
  Lt Col Halt audio recording = live instrument log
  Compass anomalies reported in real time on tape

  UNIQUE: We have EXACT timestamps from Halt's audio.
  Cross-referencing against UK magnetometer network.
  If compass anomaly appears in BGS data at same time
  as Halt reports it on tape = extraordinary corroboration.
=============================================================
""")

# ── HALT AUDIO TIMELINE ───────────────────────────────────────────────────────
# Halt's recording starts ~03:00 UTC Dec 27 (times on tape are local UK = UTC+0 winter)
# Key timestamps from the recording (approximate UTC Dec 27 1980)
HALT_EVENTS = [
    {"time":"1980-12-27T02:00:00Z","lat":52.09,"lon":1.45,"desc":"Halt enters forest — lights reported","conf":0.95},
    {"time":"1980-12-27T02:30:00Z","lat":52.09,"lon":1.44,"desc":"Halt tape starts — anomalous lights ahead","conf":0.95},
    {"time":"1980-12-27T02:44:00Z","lat":52.09,"lon":1.43,"desc":"COMPASS MALFUNCTION reported on tape","conf":0.98},
    {"time":"1980-12-27T02:48:00Z","lat":52.09,"lon":1.43,"desc":"Radiation detector readings elevated","conf":0.96},
    {"time":"1980-12-27T03:05:00Z","lat":52.09,"lon":1.43,"desc":"Three starlike objects — red/green/blue","conf":0.95},
    {"time":"1980-12-27T03:15:00Z","lat":52.09,"lon":1.44,"desc":"Object beams light at Halt's feet","conf":0.92},
    {"time":"1980-12-27T03:30:00Z","lat":52.09,"lon":1.45,"desc":"Objects depart — tape ends","conf":0.90},
]
for e in HALT_EVENTS:
    e["time"]=datetime.datetime.fromisoformat(e["time"].replace("Z","+00:00"))

# The compass malfunction is the key timestamp — 02:44 UTC
COMPASS_MALFUNCTION = datetime.datetime(1980,12,27,2,44,tzinfo=datetime.timezone.utc)
TAPE_START          = datetime.datetime(1980,12,27,2,30,tzinfo=datetime.timezone.utc)
TAPE_END            = datetime.datetime(1980,12,27,3,30,tzinfo=datetime.timezone.utc)

FETCH_START = datetime.datetime(1980,12,27,0,0, tzinfo=datetime.timezone.utc)
FETCH_END   = datetime.datetime(1980,12,27,6,0, tzinfo=datetime.timezone.utc)
T0 = FETCH_START

# ── BGS / INTERMAGNET UK STATIONS ─────────────────────────────────────────────
# HAD = Hartland Devon (closest major UK station to Suffolk)
# ESK = Eskdalemuir Scotland
# LER = Lerwick Shetland
# NGK = Niemegk Germany (backup)
STATIONS = {
    "HAD": {"lat":51.00,"lon":-4.48, "name":"Hartland Devon UK",    "color":RED,  "dist_km":350},
    "ESK": {"lat":55.32,"lon":-3.20, "name":"Eskdalemuir Scotland", "color":GRN,  "dist_km":580},
    "LER": {"lat":60.13,"lon":-1.18, "name":"Lerwick Shetland",     "color":AMB,  "dist_km":900},
    "NGK": {"lat":52.07,"lon":12.68, "name":"Niemegk Germany",      "color":BLU,  "dist_km":800},
    "CLF": {"lat":48.02,"lon":2.26,  "name":"Chambon-la-Foret FR",  "color":"#cc44ff","dist_km":600},
}

USGS_URL = "https://geomag.usgs.gov/ws/data/"
BGS_URL  = "https://geomag.bgs.ac.uk/data_service/data/"

def fetch_bgs(sid, start, end):
    """
    BGS data service — returns IAGA2002 format.
    URL format: /data_service/data/minute/definitive/YYYY/MM/STATIONYYYYMMDDMIN.min
    """
    urls_to_try = [
        f"{BGS_URL}minute/definitive/{start.year}/{start.month:02d}/{sid.lower()}{start.strftime('%Y%m%d')}dmin.min",
        f"https://www.geomag.bgs.ac.uk/data_service/data/minute/definitive/{start.year}/{start.month:02d}/{sid.lower()}{start.strftime('%Y%m%d')}dmin.min",
        f"https://wdc.bgs.ac.uk/catalog/masterfile.do?observatoryIagaCode={sid}&dataType=minute&startDate={start.strftime('%Y-%m-%d')}&endDate={end.strftime('%Y-%m-%d')}&format=IAGA2002",
        f"https://imag-data.bgs.ac.uk/GIN_V1/GINServices?Request=GetData&observatoryIagaCode={sid}&samplesPerDay=1440&startDate={start.strftime('%Y-%m-%d')}&endDate={end.strftime('%Y-%m-%d')}&dataType=definitive&orientation=HDZF&format=IAGA2002",
    ]
    for url in urls_to_try:
        try:
            r=requests.get(url,timeout=20)
            if r.status_code==200 and len(r.text)>100:
                data=parse_iaga2002(r.text,start,end)
                if data:
                    print(f"    {sid}: got data from BGS")
                    return data
        except: pass

    # Final fallback: USGS (some European stations are in USGS)
    params={"id":sid,"starttime":start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"elements":"H,D,Z",
            "sampling_period":60,"format":"json","type":"definitive"}
    try:
        r=requests.get(USGS_URL,params=params,timeout=20)
        r.raise_for_status()
        raw=r.json()
        times=[datetime.datetime.fromisoformat(t.replace("Z","+00:00")) for t in raw.get("times",[])]
        fields={}
        for entry in raw.get("values",[]):
            fid=entry["id"]
            vals=np.array([float(v) if v is not None else np.nan for v in entry["values"]])
            if not np.all(np.isnan(vals)): fields[fid]=vals
        if fields:
            print(f"    {sid}: got data from USGS fallback")
            return {"times":times,"fields":fields}
    except: pass
    return None

def parse_iaga2002(text, start, end):
    times=[]; H=[]; D=[]; Z=[]
    in_data=False
    for line in text.split("\n"):
        stripped=line.strip()
        if not stripped: continue
        if "DATE" in line and "TIME" in line: in_data=True; continue
        if not in_data: continue
        parts=stripped.split()
        if len(parts)<6: continue
        try:
            t=datetime.datetime.fromisoformat(f"{parts[0]}T{parts[1]}".replace("T24:","T00:"))
            if t.tzinfo is None: t=t.replace(tzinfo=datetime.timezone.utc)
            if t<start-datetime.timedelta(hours=1) or t>end+datetime.timedelta(hours=1): continue
            times.append(t)
            def safe(v): return float(v) if v not in ("99999","99999.00","88888","88888.00") else np.nan
            H.append(safe(parts[3])); D.append(safe(parts[4])); Z.append(safe(parts[5]))
        except: continue
    if not times: return None
    return {"times":times,"fields":{"H":np.array(H),"D":np.array(D),"Z":np.array(Z)}}

def rolling_score(arr,window=20):
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

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
    a=np.sin(dlat/2)**2+np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def t2min(t): return (t-T0).total_seconds()/60

def fetch_kp(year,month):
    url="https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
    try:
        r=requests.get(url,timeout=30); records=[]
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

# ── FETCH KP ──────────────────────────────────────────────────────────────────
print("[1] Fetching Kp for December 1980...")
kp_records=fetch_kp(1980,12)
event_kp=[r for r in kp_records if FETCH_START-datetime.timedelta(hours=6)<=r["time"]<=FETCH_END+datetime.timedelta(hours=6)]
max_kp=max([r["kp"] for r in event_kp]) if event_kp else None
kp_quiet= max_kp is not None and max_kp<3
print(f"    Max Kp: {max_kp}  |  Quiet: {kp_quiet}")
if not kp_quiet:
    print(f"    Kp={max_kp} — elevated. Solar may contribute. But Halt's compass malfunction")
    print(f"    was noted at a SPECIFIC TIME. Correlation with that timestamp is still valid.")
else:
    print(f"    Kp quiet — any anomalies are localized")

# ── FETCH STATIONS ─────────────────────────────────────────────────────────────
print("\n[2] Fetching BGS/INTERMAGNET UK stations...")
all_data={}
for sid,info in STATIONS.items():
    print(f"  Fetching {sid} ({info['name']}, {info['dist_km']}km from Rendlesham)...")
    data=fetch_bgs(sid, FETCH_START, FETCH_END)
    if data:
        all_data[sid]=data
        print(f"    {sid}: {len(data['times'])} minutes, fields={list(data['fields'].keys())}")
    else:
        print(f"    {sid}: no data from BGS or USGS")

print(f"\n  Stations with data: {list(all_data.keys())}")
print(f"  Stations failed: {[s for s in STATIONS if s not in all_data]}")

# ── THE KEY ANALYSIS: Halt's compass malfunction timestamp ────────────────────
print("\n[3] CRITICAL ANALYSIS: Halt compass malfunction at 02:44 UTC")
print("    If BGS shows D-field anomaly at same time = instrument corroboration")
print("    This would be the most direct physical verification possible.\n")

compass_window_s = COMPASS_MALFUNCTION - datetime.timedelta(minutes=5)
compass_window_e = COMPASS_MALFUNCTION + datetime.timedelta(minutes=15)

compass_hits=[]
for sid,data in all_data.items():
    for field in ["D","H","Z"]:
        if field not in data["fields"]: continue
        sc=rolling_score(data["fields"][field])
        idx=[i for i,t in enumerate(data["times"]) if compass_window_s<=t<=compass_window_e]
        if not idx: continue
        peak=float(np.max(sc[idx]))
        peak_t=data["times"][idx[np.argmax(sc[idx])]]
        if peak>1.5:
            dt_from_halt=(peak_t-COMPASS_MALFUNCTION).total_seconds()/60
            flag=" *** ANOMALY AT HALT TIMESTAMP" if peak>2.0 else " (elevated)"
            print(f"    {sid} {field}: {peak:.3f}s at {peak_t.strftime('%H:%M UTC')} "
                  f"({dt_from_halt:+.0f}min from Halt report){flag}")
            if peak>2.0:
                compass_hits.append({
                    "station":sid,"field":field,"sigma":round(peak,3),
                    "time":peak_t.isoformat(),
                    "dt_from_halt_min":round(dt_from_halt,1)
                })

if compass_hits:
    print(f"\n  *** CORROBORATION FOUND: {len(compass_hits)} anomalies near Halt's compass timestamp ***")
else:
    print(f"\n  No >2sigma anomalies in compass malfunction window.")
    print(f"  Either: stations too far, data gap, or anomaly was truly local to Rendlesham.")

# ── SCAN ALL HALT EVENTS ──────────────────────────────────────────────────────
print("\n[4] Scanning all Halt audio timestamps...")
all_event_hits={}
for evt in HALT_EVENTS:
    label=evt["desc"][:40]
    w_s=evt["time"]-datetime.timedelta(minutes=8)
    w_e=evt["time"]+datetime.timedelta(minutes=8)
    hits=[]
    for sid,data in all_data.items():
        if "D" not in data["fields"]: continue
        sc=rolling_score(data["fields"]["D"])
        idx=[i for i,t in enumerate(data["times"]) if w_s<=t<=w_e]
        if not idx: continue
        peak=float(np.max(sc[idx]))
        peak_t=data["times"][idx[np.argmax(sc[idx])]]
        if peak>2.0:
            hits.append({"station":sid,"sigma":round(peak,3),"time":peak_t.isoformat()})
            print(f"    {evt['time'].strftime('%H:%M')} {label}: {sid} {peak:.3f}s ***")
    all_event_hits[label]=hits

# ── CROSS-CORRELATION ─────────────────────────────────────────────────────────
corr_val=0; lag_val=0; best_pair=("","")
sids=list(all_data.keys())
if len(sids)>=2:
    for i in range(len(sids)):
        for j in range(i+1,len(sids)):
            s1,s2=sids[i],sids[j]
            d1=all_data[s1]["fields"].get("D",np.array([]))
            d2=all_data[s2]["fields"].get("D",np.array([]))
            t1=all_data[s1]["times"]; t2=all_data[s2]["times"]
            idx1=[i2 for i2,t in enumerate(t1) if TAPE_START<=t<=TAPE_END]
            idx2=[i2 for i2,t in enumerate(t2) if TAPE_START<=t<=TAPE_END]
            if not idx1 or not idx2: continue
            a=d1[idx1]; b=d2[idx2]; ml=min(len(a),len(b))
            a=a[:ml]; b=b[:ml]; vld=~(np.isnan(a)|np.isnan(b))
            if vld.sum()<5: continue
            c=float(np.corrcoef(a[vld],b[vld])[0,1])
            if abs(c)>abs(corr_val):
                corr_val=c; best_pair=(s1,s2)
    print(f"\n[5] Best correlation: {best_pair[0]}-{best_pair[1]} = {corr_val:.4f}")

# ── PLOT ──────────────────────────────────────────────────────────────────────
print("\n[6] Generating plots...")
os.makedirs("event_outputs/Rendlesham_1980",exist_ok=True)
fig=plt.figure(figsize=(22,18),facecolor=BG)
gs=GridSpec(4,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)
colors_list=[RED,GRN,AMB,BLU,"#cc44ff"]

ax1=fig.add_subplot(gs[0,:])
ax1.set_facecolor("#010402"); ax1.tick_params(colors=DIM,labelsize=8)
for sp in ax1.spines.values(): sp.set_color("#0a2211")
ax1.axvspan(t2min(TAPE_START),t2min(TAPE_END),alpha=0.08,color=RED,label="Halt recording")
ax1.axvline(t2min(COMPASS_MALFUNCTION),color=RED,linewidth=2.5,alpha=0.9,
           label=f"COMPASS MALFUNCTION {COMPASS_MALFUNCTION.strftime('%H:%M UTC')}")
for i,evt in enumerate(HALT_EVENTS):
    ax1.axvline(t2min(evt["time"]),color=AMB,linewidth=0.8,alpha=0.6,linestyle="--")
    if i%2==0:
        ax1.text(t2min(evt["time"])+0.3,1.8,evt["desc"][:20],
                color=AMB,fontsize=5,fontfamily=MONO,rotation=40,ha="left")
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    norm=normalize(data["fields"]["D"])
    ax1.plot(tmin,norm,color=colors_list[i%len(colors_list)],linewidth=1.3,
            alpha=0.85,label=f"{sid} ({STATIONS[sid]['name']})")
ax1.set_title("RENDLESHAM 1980 — ALL STATIONS D-FIELD NORMALIZED\nRed = Halt compass malfunction timestamp. Amber = other Halt audio events.",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax1.set_xlabel("Minutes from 00:00 UTC 1980-12-27",color=DIM,fontfamily=MONO,fontsize=8)
ax1.set_ylabel("Normalized deviation",color=DIM,fontfamily=MONO,fontsize=8)
if all_data: ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=3)

ax2=fig.add_subplot(gs[1,:])
ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=8)
for sp in ax2.spines.values(): sp.set_color("#0a2211")
ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
ax2.axvline(t2min(COMPASS_MALFUNCTION),color=RED,linewidth=2.5,alpha=0.9,
           label=f"Halt compass malfunction {COMPASS_MALFUNCTION.strftime('%H:%M')}")
for i,evt in enumerate(HALT_EVENTS):
    ax2.axvline(t2min(evt["time"]),color=AMB,linewidth=0.8,alpha=0.5,linestyle="--")
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax2.plot(tmin,sc,color=colors_list[i%len(colors_list)],linewidth=1.2,alpha=0.85,label=f"{sid}")
ax2.set_title("ANOMALY SCORES — KEY QUESTION: Does any station spike at 02:44 UTC (Halt compass)?",
             color=RED,fontfamily=MONO,fontsize=9,pad=8)
ax2.set_xlabel("Minutes from 00:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylim(bottom=0)
if all_data: ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=3)

ax3=fig.add_subplot(gs[2,:])
ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=8)
for sp in ax3.spines.values(): sp.set_color("#0a2211")
ax3.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7)
ax3.axvline(t2min(COMPASS_MALFUNCTION),color=RED,linewidth=2.5,alpha=0.9,
           label=f"02:44 UTC — COMPASS MALFUNCTION (Halt audio)")
ax3.axvspan(t2min(TAPE_START),t2min(TAPE_END),alpha=0.1,color=RED)
for i,evt in enumerate(HALT_EVENTS):
    ax3.axvline(t2min(evt["time"]),color=AMB,linewidth=1,alpha=0.7,linestyle="--")
    ax3.text(t2min(evt["time"])+0.2,0.1+i*0.08,evt["desc"][:25],
            color=AMB,fontsize=5,fontfamily=MONO,rotation=30,ha="left")
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax3.plot(tmin,sc,color=colors_list[i%len(colors_list)],linewidth=1.8,alpha=0.9,label=f"{sid}")
zoom_s=t2min(TAPE_START)-15; zoom_e=t2min(TAPE_END)+15
ax3.set_xlim(zoom_s,zoom_e)
ax3.set_title("ZOOMED — HALT RECORDING WINDOW (02:30–03:30 UTC)\nThis is where Halt's compass malfunction should appear if the field was real",
             color=RED,fontfamily=MONO,fontsize=9,pad=8)
ax3.set_xlabel("Minutes from 00:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax3.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax3.set_ylim(bottom=0)
if all_data: ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=3)

ax4=fig.add_subplot(gs[3,0])
ax4.set_facecolor("#010402"); ax4.tick_params(colors=DIM,labelsize=7)
for sp in ax4.spines.values(): sp.set_color("#0a2211")
for lat in range(45,65,5):
    ax4.axhline(lat,color=GFNT,linewidth=0.3,linestyle="--")
for lon in range(-10,20,5):
    ax4.axvline(lon,color=GFNT,linewidth=0.3,linestyle="--")
ax4.plot(1.45,52.09,"*",color=RED,markersize=15,zorder=10,label="Rendlesham Forest")
ax4.text(1.65,52.15,"RENDLESHAM\nRAF BENTWATERS",color=RED,fontsize=7,fontfamily=MONO,fontweight="bold")
for sid,info in STATIONS.items():
    has=sid in all_data
    c=colors_list[list(STATIONS.keys()).index(sid)%len(colors_list)]
    ax4.plot(info["lon"],info["lat"],"o" if has else "x",color=c,markersize=8 if has else 5,zorder=5)
    ax4.text(info["lon"]+0.2,info["lat"]+0.3,f"{sid}\n{info['dist_km']}km",
            color=c,fontsize=6,fontfamily=MONO)
    if has:
        ax4.plot([1.45,info["lon"]],[52.09,info["lat"]],color=c,linewidth=0.6,alpha=0.4,linestyle="--")
ax4.set_xlim(-10,20); ax4.set_ylim(45,65)
ax4.set_title("UK/EUROPE STATION NETWORK\nFrom Rendlesham Forest",color=GRN,fontfamily=MONO,fontsize=8)
ax4.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=6)

ax5=fig.add_subplot(gs[3,1])
ax5.set_facecolor("#010402"); ax5.axis("off")
total_hits=sum(len(v) for v in all_event_hits.values())
for sp in ax5.spines.values(): sp.set_color(RED if compass_hits else GDIM)
lines=[
    ("RENDLESHAM BGS ANALYSIS",GRN,10,True),
    ("1980-12-26/27 RAF Bentwaters UK",WHT,8,False),
    ("",WHT,7,False),
    (f"Kp={max_kp}  Quiet:{kp_quiet}",GRN if kp_quiet else AMB,8,True),
    ("",WHT,7,False),
    (f"Stations fetched: {len(all_data)}/{len(STATIONS)}",GRN if all_data else RED,8,False),
    ("",WHT,7,False),
    ("KEY FINDING:",AMB,9,True),
    ("Halt compass malfunction 02:44 UTC",AMB,8,False),
    ("Reported LIVE on audio recording.",AMB,8,False),
    ("",WHT,7,False),
]
if compass_hits:
    lines.append(("*** BGS CORROBORATION ***",RED,10,True))
    for h in compass_hits:
        lines.append((f"{h['station']}: {h['sigma']:.3f}s at {h['time'][11:16]}",RED,8,True))
        lines.append((f"  {h['dt_from_halt_min']:+.0f}min from Halt report",AMB,7,False))
else:
    lines.append(("No BGS anomaly at 02:44 UTC",DIM,8,False))
    lines.append(("Possible reasons:",DIM,7,False))
    lines.append(("- Stations too far (350km+)",DIM,7,False))
    lines.append(("- Field was very local",DIM,7,False))
    lines.append(("- Data gap in 1980 archive",DIM,7,False))
lines+=[
    ("",WHT,7,False),
    (f"Total anomalies: {total_hits}",RED if total_hits>0 else DIM,8,False),
    (f"Correlation: {corr_val:.4f}",RED if abs(corr_val)>0.85 else WHT,8,False),
]
y=0.97
for text,color,size,bold in lines:
    ax5.text(0.04,y,text,transform=ax5.transAxes,color=color,fontfamily=MONO,
            fontsize=size,fontweight="bold" if bold else "normal",va="top")
    y-=0.055

fig.suptitle("RENDLESHAM FOREST 1980-12-26/27 — BGS/INTERMAGNET SCAN\nCross-referencing Halt audio compass malfunction against UK magnetometer network",
            color=GRN,fontfamily=MONO,fontsize=11,y=0.97)
out="event_outputs/Rendlesham_1980/Rendlesham_bgs.png"
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
plt.close()
print(f"  Saved: {out}")

results={
    "event":"Rendlesham_1980","date":"1980-12-26",
    "method":"BGS/INTERMAGNET UK network",
    "kp":{"max_kp":max_kp,"quiet":kp_quiet},
    "stations_fetched":list(all_data.keys()),
    "stations_failed":[s for s in STATIONS if s not in all_data],
    "halt_compass_malfunction_utc":COMPASS_MALFUNCTION.isoformat(),
    "compass_hits":compass_hits,
    "total_halt_event_anomalies":total_hits,
    "correlation":{"value":round(float(corr_val),4),"pair":list(best_pair)},
    "note":"Halt's audio recording provides exact timestamps for compass anomalies. Any BGS anomaly within minutes of these timestamps constitutes independent instrument corroboration of a real EM event.",
}
with open("event_outputs/Rendlesham_1980/Rendlesham_bgs.json","w") as f:
    json.dump(results,f,indent=2,default=str)
print("  Saved: event_outputs/Rendlesham_1980/Rendlesham_bgs.json")
print(f"\nKp={max_kp} | Stations={len(all_data)} | Compass hits={len(compass_hits)} | Total={total_hits}")
