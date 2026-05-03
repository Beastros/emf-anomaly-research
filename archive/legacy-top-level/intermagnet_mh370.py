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
  MH370 — INTERMAGNET NETWORK SCAN
  March 8 2014 — Indian Ocean / Asia Pacific stations
  USGS failed — now hitting INTERMAGNET directly
  Kp=1.0 confirmed quiet — any anomalies are localized
=============================================================
""")

# ── MH370 TIMELINE ────────────────────────────────────────────────────────────
MH370 = [
    {"time":"2014-03-07T16:41:00Z","lat":2.74,  "lon":101.71,"desc":"Departs KLIA"},
    {"time":"2014-03-07T17:07:00Z","lat":5.00,  "lon":103.00,"desc":"Last ACARS"},
    {"time":"2014-03-07T17:19:00Z","lat":6.90,  "lon":103.65,"desc":"Last ATC — Good night MAS370"},
    {"time":"2014-03-07T17:21:00Z","lat":6.94,  "lon":103.59,"desc":"TRANSPONDER OFF"},
    {"time":"2014-03-07T17:30:00Z","lat":7.20,  "lon":103.25,"desc":"Sharp LEFT turn — military radar"},
    {"time":"2014-03-07T17:52:00Z","lat":6.50,  "lon":99.70, "desc":"WMPL waypoint — heading NW"},
    {"time":"2014-03-07T18:02:00Z","lat":6.15,  "lon":97.50, "desc":"LAST RADAR — Pulau Perak"},
    {"time":"2014-03-07T18:22:00Z","lat":5.50,  "lon":95.30, "desc":"Inmarsat ping 1"},
    {"time":"2014-03-07T19:41:00Z","lat":1.00,  "lon":93.00, "desc":"Inmarsat ping 2"},
    {"time":"2014-03-07T20:41:00Z","lat":-5.00, "lon":90.00, "desc":"Inmarsat ping 3"},
    {"time":"2014-03-07T21:41:00Z","lat":-13.0, "lon":88.00, "desc":"Inmarsat ping 4"},
    {"time":"2014-03-07T22:41:00Z","lat":-23.0, "lon":87.00, "desc":"Inmarsat ping 5"},
    {"time":"2014-03-07T23:14:00Z","lat":-28.0, "lon":87.00, "desc":"Inmarsat ping 6"},
    {"time":"2014-03-08T00:11:00Z","lat":-38.0, "lon":88.00, "desc":"7TH ARC — final handshake"},
]
for e in MH370:
    e["time"] = datetime.datetime.fromisoformat(e["time"].replace("Z","+00:00"))

TRANSPONDER_OFF = datetime.datetime(2014,3,7,17,21,tzinfo=datetime.timezone.utc)
LAST_RADAR      = datetime.datetime(2014,3,7,18, 2,tzinfo=datetime.timezone.utc)
TURN_BACK       = datetime.datetime(2014,3,7,17,30,tzinfo=datetime.timezone.utc)
FINAL_ARC       = datetime.datetime(2014,3,8, 0,11,tzinfo=datetime.timezone.utc)

FETCH_START = datetime.datetime(2014,3,7,15,0, tzinfo=datetime.timezone.utc)
FETCH_END   = datetime.datetime(2014,3,8, 2,0, tzinfo=datetime.timezone.utc)
T0 = FETCH_START

KEY_EVENTS = [
    ("Transponder OFF", TRANSPONDER_OFF),
    ("Sharp turn-back", TURN_BACK),
    ("Last radar",      LAST_RADAR),
    ("Final arc",       FINAL_ARC),
]

# ── INTERMAGNET STATIONS ──────────────────────────────────────────────────────
# Closest available stations to MH370 track
# INTERMAGNET uses WDC Edinburgh and individual observatory APIs
STATIONS = {
    # Primary sources — INTERMAGNET observatories
    "CNB": {"lat":-35.32,"lon":149.36,"name":"Canberra Australia",   "color":GRN,  "api":"intermagnet"},
    "API": {"lat":-13.81,"lon":-171.77,"name":"Apia Samoa",          "color":AMB,  "api":"intermagnet"},
    "KNY": {"lat":31.424,"lon":130.880,"name":"Kanoya Japan",        "color":RED,  "api":"intermagnet"},
    "IPM": {"lat":7.917, "lon":98.350, "name":"Ip Patong Thailand",  "color":BLU,  "api":"intermagnet"},
    "CTA": {"lat":-20.09,"lon":146.26, "name":"Charters Towers AUS", "color":"#cc44ff","api":"intermagnet"},
    # USGS fallback
    "HON": {"lat":21.316,"lon":-158.000,"name":"Honolulu HI",        "color":"#ff8800","api":"usgs"},
    "GUA": {"lat":13.588,"lon":144.867, "name":"Guam",               "color":"#00ff88","api":"usgs"},
}

USGS_URL        = "https://geomag.usgs.gov/ws/data/"
# INTERMAGNET WDC Edinburgh data service
INTERMAGNET_URL = "https://imag-data.bgs.ac.uk/GIN_V1/GINServices"
# BGS/NERC alternative
BGS_URL         = "https://geomag.bgs.ac.uk/data_service/data/"

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
    a=np.sin(dlat/2)**2+np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def fetch_usgs(sid, start, end):
    params={"id":sid,"starttime":start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"elements":"H,D,Z",
            "sampling_period":60,"format":"json","type":"definitive"}
    try:
        r=requests.get(USGS_URL,params=params,timeout=30)
        r.raise_for_status(); return r.json()
    except Exception as e:
        return None

def fetch_intermagnet_bgs(sid, start, end):
    """
    Fetch from BGS GIN (Geomagnetic Information Node).
    Format: IAGA2002
    """
    # Try BGS data service
    url = f"{BGS_URL}{sid}/minute/definitive/{start.strftime('%Y/%m')}"
    try:
        r=requests.get(url,timeout=20)
        if r.status_code==200:
            return parse_iaga2002(r.text, start, end)
    except: pass

    # Try WDC Edinburgh
    url2 = (f"https://wdc.bgs.ac.uk/catalog/masterfile.do?"
            f"observatoryIagaCode={sid}&"
            f"dataType=minute&"
            f"startDate={start.strftime('%Y-%m-%d')}&"
            f"endDate={end.strftime('%Y-%m-%d')}&"
            f"format=IAGA2002")
    try:
        r=requests.get(url2,timeout=20)
        if r.status_code==200:
            return parse_iaga2002(r.text, start, end)
    except: pass

    # Try direct observatory if known
    obs_urls = {
        "CNB": f"https://www.ga.gov.au/geomagnetic/realtime/data/{sid}_{start.strftime('%Y%m%d')}.min",
        "API": f"https://www.intermagnet.org/data-donnee/minute/{sid}{start.strftime('%Y%m%d')}dmin.min",
    }
    if sid in obs_urls:
        try:
            r=requests.get(obs_urls[sid],timeout=20)
            if r.status_code==200:
                return parse_iaga2002(r.text, start, end)
        except: pass

    return None

def parse_iaga2002(text, start, end):
    """Parse IAGA2002 format magnetometer data."""
    times=[]; H=[]; D=[]; Z=[]
    in_data=False
    for line in text.split("\n"):
        if "DATE" in line and "TIME" in line:
            in_data=True; continue
        if not in_data or not line.strip(): continue
        if line.startswith(" ") or line[0].isdigit():
            parts=line.split()
            if len(parts)<6: continue
            try:
                t=datetime.datetime.fromisoformat(f"{parts[0]}T{parts[1]}+00:00")
                if t<start or t>end: continue
                times.append(t)
                H.append(float(parts[3]) if parts[3]!="99999.00" else np.nan)
                D.append(float(parts[4]) if parts[4]!="99999.00" else np.nan)
                Z.append(float(parts[5]) if parts[5]!="99999.00" else np.nan)
            except: continue
    if not times: return None
    return {"times":times,"fields":{"H":np.array(H),"D":np.array(D),"Z":np.array(Z)}}

def parse_usgs(raw):
    if not raw: return None
    times=[datetime.datetime.fromisoformat(t.replace("Z","+00:00")) for t in raw.get("times",[])]
    fields={}
    for entry in raw.get("values",[]):
        fid=entry["id"]
        vals=np.array([float(v) if v is not None else np.nan for v in entry["values"]])
        if not np.all(np.isnan(vals)): fields[fid]=vals
    return {"times":times,"fields":fields} if fields else None

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

def t2min(t): return (t-T0).total_seconds()/60

# ── FETCH ALL STATIONS ────────────────────────────────────────────────────────
print("[1] Fetching INTERMAGNET + USGS stations...")
all_data={}
for sid,info in STATIONS.items():
    print(f"  {sid} ({info['name']}) via {info['api']}...")
    if info["api"]=="usgs":
        raw=fetch_usgs(sid, FETCH_START, FETCH_END)
        data=parse_usgs(raw)
    else:
        data=fetch_intermagnet_bgs(sid, FETCH_START, FETCH_END)
        if not data:
            # Fallback to USGS even for intermagnet stations
            raw=fetch_usgs(sid, FETCH_START, FETCH_END)
            data=parse_usgs(raw)

    if data:
        all_data[sid]=data
        print(f"    {sid}: {len(data['times'])} minutes, fields={list(data['fields'].keys())}")
    else:
        print(f"    {sid}: no data from any source")

print(f"\n  Stations with data: {list(all_data.keys())}")
print(f"  Stations failed:    {[s for s in STATIONS if s not in all_data]}")

# ── ANOMALY SCAN AT KEY EVENTS ────────────────────────────────────────────────
print("\n[2] Scanning for anomalies at key MH370 timestamps...")
event_hits={}
for label, evt_time in KEY_EVENTS:
    w_s = evt_time - datetime.timedelta(minutes=10)
    w_e = evt_time + datetime.timedelta(minutes=10)
    print(f"\n  {label} ({evt_time.strftime('%H:%M UTC')}):")
    event_hits[label]=[]
    for sid,data in all_data.items():
        for field in ["D","H","Z"]:
            if field not in data["fields"]: continue
            sc=rolling_score(data["fields"][field])
            idx=[i for i,t in enumerate(data["times"]) if w_s<=t<=w_e]
            if not idx: continue
            peak=float(np.max(sc[idx]))
            peak_t=data["times"][idx[np.argmax(sc[idx])]]
            if peak>2.0:
                print(f"    *** {sid} {field}: {peak:.3f}s at {peak_t.strftime('%H:%M UTC')} ***")
                event_hits[label].append({
                    "station":sid,"field":field,
                    "sigma":round(peak,3),
                    "time":peak_t.isoformat()
                })
            elif peak>1.5:
                print(f"    {sid} {field}: {peak:.3f}s at {peak_t.strftime('%H:%M UTC')}")

# ── INMARSAT PING ARC CORRELATION ────────────────────────────────────────────
print("\n[3] Inmarsat ping arc correlation...")
print("  Checking magnetometer anomalies near each ping timestamp...")
ping_events = [(e["time"],e["desc"]) for e in MH370 if "ping" in e["desc"].lower() or "arc" in e["desc"].lower() or "Inmarsat" in e["desc"]]
for pt,desc in ping_events:
    print(f"\n  {pt.strftime('%H:%M UTC')} — {desc}")
    w_s=pt-datetime.timedelta(minutes=15)
    w_e=pt+datetime.timedelta(minutes=15)
    for sid,data in all_data.items():
        if "D" not in data["fields"]: continue
        sc=rolling_score(data["fields"]["D"])
        idx=[i for i,t in enumerate(data["times"]) if w_s<=t<=w_e]
        if not idx: continue
        peak=float(np.max(sc[idx]))
        if peak>1.5:
            peak_t=data["times"][idx[np.argmax(sc[idx])]]
            flag=" ***" if peak>2.0 else ""
            print(f"    {sid}: {peak:.3f}s at {peak_t.strftime('%H:%M UTC')}{flag}")

# ── CROSS-CORRELATION ─────────────────────────────────────────────────────────
print("\n[4] Cross-correlation analysis...")
sids=list(all_data.keys())
corr_val=0; lag_val=0; best_pair=("","")
disap_s=datetime.datetime(2014,3,7,16,30,tzinfo=datetime.timezone.utc)
disap_e=datetime.datetime(2014,3,7,19,0, tzinfo=datetime.timezone.utc)

best_corr=0
for i in range(len(sids)):
    for j in range(i+1,len(sids)):
        s1,s2=sids[i],sids[j]
        d1=all_data[s1]["fields"].get("D",np.array([]))
        d2=all_data[s2]["fields"].get("D",np.array([]))
        t1=all_data[s1]["times"]; t2=all_data[s2]["times"]
        idx1=[i2 for i2,t in enumerate(t1) if disap_s<=t<=disap_e]
        idx2=[i2 for i2,t in enumerate(t2) if disap_s<=t<=disap_e]
        if not idx1 or not idx2: continue
        a=d1[idx1]; b=d2[idx2]; ml=min(len(a),len(b))
        a=a[:ml]; b=b[:ml]; vld=~(np.isnan(a)|np.isnan(b))
        if vld.sum()<5: continue
        c=abs(np.corrcoef(a[vld],b[vld])[0,1])
        if c>best_corr:
            best_corr=c; best_pair=(s1,s2)
            max_lag=30; lags=list(range(-max_lag,max_lag+1)); xcorr=[]
            for lag in lags:
                if lag>=0: aa=a[lag:]; bb=b[:len(aa)]
                else:       aa=a[:lag]; bb=b[-lag:len(aa)-lag]
                ml2=min(len(aa),len(bb))
                if ml2>3:
                    v2=~(np.isnan(aa[:ml2])|np.isnan(bb[:ml2]))
                    xcorr.append(np.corrcoef(aa[:ml2][v2],bb[:ml2][v2])[0,1] if v2.sum()>3 else 0)
                else: xcorr.append(0)
            best_idx=np.argmax(np.abs(xcorr)); lag_val=lags[best_idx]; corr_val=float(np.corrcoef(a[vld],b[vld])[0,1])

if best_pair[0]:
    print(f"  Best pair: {best_pair[0]}-{best_pair[1]}")
    print(f"  Correlation: {corr_val:.4f}  lag={lag_val}min")
else:
    print("  Insufficient data for correlation")

# ── PLOT ──────────────────────────────────────────────────────────────────────
print("\n[5] Generating plots...")
os.makedirs("event_outputs/MH370_2014",exist_ok=True)

fig=plt.figure(figsize=(22,18),facecolor=BG)
gs=GridSpec(4,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)

# Panel 1: D-field normalized all stations
ax1=fig.add_subplot(gs[0,:])
ax1.set_facecolor("#010402"); ax1.tick_params(colors=DIM,labelsize=8)
for sp in ax1.spines.values(): sp.set_color("#0a2211")
colors_list=[RED,GRN,AMB,BLU,"#cc44ff","#ff8800","#00ff88"]
for i,(label,evt_time) in enumerate(KEY_EVENTS):
    ax1.axvline(t2min(evt_time),color=RED,linewidth=1.5,alpha=0.8,linestyle="--")
    ax1.text(t2min(evt_time)+0.5,2.2-i*0.5,label,color=RED,fontsize=6,
            fontfamily=MONO,rotation=45,ha="left",
            path_effects=[pe.withStroke(linewidth=1.5,foreground=BG)])
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    norm=normalize(data["fields"]["D"])
    ax1.plot(tmin,norm,color=colors_list[i%len(colors_list)],
            linewidth=1.3,alpha=0.85,label=f"{sid} ({STATIONS[sid]['name']})")
ax1.set_title("MH370 — ALL STATIONS D-FIELD NORMALIZED (INTERMAGNET+USGS)\nRed dashed = transponder off, turn-back, last radar, final arc",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax1.set_xlabel("Minutes from 15:00 UTC 2014-03-07",color=DIM,fontfamily=MONO,fontsize=8)
ax1.set_ylabel("Normalized deviation",color=DIM,fontfamily=MONO,fontsize=8)
if all_data: ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=3)

# Panel 2: Sigma scores
ax2=fig.add_subplot(gs[1,:])
ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=8)
for sp in ax2.spines.values(): sp.set_color("#0a2211")
ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
ax2.axhline(3.0,color=RED,linewidth=0.5,linestyle=":",alpha=0.5,label="3sigma")
for i,(label,evt_time) in enumerate(KEY_EVENTS):
    ax2.axvline(t2min(evt_time),color=RED,linewidth=1.5,alpha=0.8,linestyle="--")
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax2.plot(tmin,sc,color=colors_list[i%len(colors_list)],linewidth=1.2,alpha=0.85,label=f"{sid}")
ax2.set_title("ANOMALY SCORES — MH370 FULL FLIGHT WINDOW\nLooking for sigma spikes at transponder-off, turn-back, last radar, final arc",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax2.set_xlabel("Minutes from 15:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylim(bottom=0)
if all_data: ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=4)

# Panel 3: Disappearance window zoom
ax3=fig.add_subplot(gs[2,:])
ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=8)
for sp in ax3.spines.values(): sp.set_color("#0a2211")
ax3.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
window_start=t2min(TRANSPONDER_OFF)-20; window_end=t2min(LAST_RADAR)+30
for i,(label,evt_time) in enumerate(KEY_EVENTS[:3]):
    ax3.axvline(t2min(evt_time),color=RED,linewidth=2,alpha=0.9,linestyle="--")
    ax3.text(t2min(evt_time)+0.3,0.2,label,color=RED,fontsize=7,
            fontfamily=MONO,rotation=45,ha="left")
for i,(sid,data) in enumerate(all_data.items()):
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax3.plot(tmin,sc,color=colors_list[i%len(colors_list)],linewidth=1.5,alpha=0.9,label=f"{sid}")
ax3.set_xlim(window_start,window_end)
ax3.set_title("ZOOMED — TRANSPONDER-OFF TO LAST RADAR WINDOW\nThe 41-minute disappearance sequence",
             color=RED,fontfamily=MONO,fontsize=9,pad=8)
ax3.set_xlabel("Minutes from 15:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax3.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax3.set_ylim(bottom=0)
if all_data: ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=4)

# Panel 4L: Map
ax4=fig.add_subplot(gs[3,0])
ax4.set_facecolor("#010402"); ax4.tick_params(colors=DIM,labelsize=7)
for sp in ax4.spines.values(): sp.set_color("#0a2211")
for lat in range(-50,25,10):
    ax4.axhline(lat,color=GFNT,linewidth=0.3,linestyle="--")
for lon in range(60,190,20):
    ax4.axvline(lon,color=GFNT,linewidth=0.3,linestyle="--")
known_lons=[e["lon"] for e in MH370[:8]]
known_lats=[e["lat"] for e in MH370[:8]]
arc_lons=[e["lon"] for e in MH370[7:]]
arc_lats=[e["lat"] for e in MH370[7:]]
ax4.plot(known_lons,known_lats,color=AMB,linewidth=2,alpha=0.9,label="Known track")
ax4.plot(arc_lons,arc_lats,color=RED,linewidth=1,alpha=0.6,linestyle="--",label="Inmarsat arcs")
for e in [MH370[0],MH370[3],MH370[6],MH370[-1]]:
    ax4.plot(e["lon"],e["lat"],"o" if e!=MH370[-1] else "x",
            color=GRN if e==MH370[0] else RED,markersize=8)
    ax4.text(e["lon"]+1,e["lat"]+0.5,e["time"].strftime("%H:%M"),
            color=AMB,fontsize=5,fontfamily=MONO)
for sid,info in STATIONS.items():
    c=colors_list[list(STATIONS.keys()).index(sid)%len(colors_list)]
    has=sid in all_data
    ax4.plot(info["lon"],info["lat"],"o" if has else "x",
            color=c,markersize=8 if has else 6,zorder=5,alpha=1.0 if has else 0.4)
    ax4.text(info["lon"]+1,info["lat"]+0.5,sid,color=c,fontsize=6,fontfamily=MONO)
ax4.set_xlim(60,190); ax4.set_ylim(-50,35)
ax4.set_title("MH370 TRACK + STATION NETWORK",color=GRN,fontfamily=MONO,fontsize=8)
ax4.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=6)

# Panel 4R: Summary
ax5=fig.add_subplot(gs[3,1])
ax5.set_facecolor("#010402"); ax5.axis("off")
for sp in ax5.spines.values(): sp.set_color(RED if any(event_hits.values()) else GDIM)
total_hits=sum(len(v) for v in event_hits.values())
lines=[
    ("MH370 INTERMAGNET ANALYSIS",GRN,10,True),
    ("2014-03-07/08",WHT,8,False),
    ("",WHT,7,False),
    (f"Kp=1.0  CONFIRMED QUIET",GRN,9,True),
    ("Solar explanation: ELIMINATED",GRN,8,True),
    ("",WHT,7,False),
    (f"Stations fetched: {len(all_data)}/{len(STATIONS)}",
     GRN if all_data else RED,8,False),
    ("",WHT,7,False),
    (f"Total anomalies >2s: {total_hits}",
     RED if total_hits>0 else DIM,9,True),
    ("",WHT,7,False),
    ("ANOMALIES AT KEY EVENTS:",AMB,9,True),
]
for label,hits in event_hits.items():
    if hits:
        lines.append((f"{label}:",RED,8,True))
        for h in hits:
            lines.append((f"  {h['station']} {h['field']}: {h['sigma']:.3f}s",RED,7,False))
    else:
        lines.append((f"{label}: none",DIM,7,False))
lines+=[
    ("",WHT,7,False),
    (f"Correlation: {corr_val:.4f}",RED if abs(corr_val)>0.85 else WHT,8,False),
    ("",WHT,7,False),
    ("NOTE: INTERMAGNET coverage",AMB,7,False),
    ("of Indian Ocean is sparse.",AMB,7,False),
    ("CNB/API/KNY are closest.",AMB,7,False),
    ("BGS for direct IAGA2002.",AMB,7,False),
]
y=0.97
for text,color,size,bold in lines:
    ax5.text(0.04,y,text,transform=ax5.transAxes,color=color,fontfamily=MONO,
            fontsize=size,fontweight="bold" if bold else "normal",va="top")
    y-=0.055

fig.suptitle("MH370 — 2014-03-07/08 — INTERMAGNET MULTI-STATION SCAN\nKp=1.0 QUIET | Transponder-off / Turn-back / Last radar / Final arc windows",
            color=GRN,fontfamily=MONO,fontsize=11,y=0.97)
out="event_outputs/MH370_2014/MH370_intermagnet.png"
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
plt.close()
print(f"  Saved: {out}")

results={
    "event":"MH370","date":"2014-03-07",
    "method":"INTERMAGNET + USGS multi-source",
    "kp":{"max_kp":1.0,"quiet":True},
    "stations_fetched":list(all_data.keys()),
    "stations_failed":[s for s in STATIONS if s not in all_data],
    "total_anomalies_at_key_events":sum(len(v) for v in event_hits.values()),
    "event_anomalies":event_hits,
    "correlation":{"value":round(float(corr_val),4),"lag_min":lag_val,"pair":list(best_pair)},
}
with open("event_outputs/MH370_2014/MH370_intermagnet.json","w") as f:
    json.dump(results,f,indent=2,default=str)
print("  Saved: event_outputs/MH370_2014/MH370_intermagnet.json")
print(f"\nKp=1.0 QUIET | Stations={len(all_data)} | Anomalies={sum(len(v) for v in event_hits.values())}")
