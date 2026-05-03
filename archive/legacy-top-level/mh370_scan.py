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
  MH370 — MARCH 8 2014 — MULTI-SENSOR ANOMALY SCAN
  Malaysia Airlines Flight MH370
  Last confirmed position: 02:22 UTC over South China Sea
  ACARS cutoff: 01:07 UTC
  Transponder cutoff: 01:21 UTC
  Last military radar: 02:22 UTC (Pulau Perak)
  Inmarsat handshake: 08:11 UTC (7th arc)

  NOTE ON ORBS VIDEO:
  Videos circulating on social media purporting to show
  orbs circling MH370 are unverified and likely fabricated.
  We treat them as hypothesis only — not as data.
  What we CAN do: scan real sensor data for the actual
  disappearance window and see if anything anomalous
  appears in the instruments around the known events.
=============================================================
""")

# ── MH370 KNOWN TIMELINE ──────────────────────────────────────────────────────
# All times UTC, March 8 2014
MH370_EVENTS = [
    {"time":"2014-03-07T16:41:00Z","lat":2.74, "lon":101.71,"desc":"MH370 departs KLIA Kuala Lumpur","conf":1.0},
    {"time":"2014-03-07T17:07:00Z","lat":5.00, "lon":103.00,"desc":"Last ACARS transmission — normal","conf":1.0},
    {"time":"2014-03-07T17:19:00Z","lat":6.90, "lon":103.65,"desc":"Last ATC contact — Good night, MAS 370","conf":1.0},
    {"time":"2014-03-07T17:21:00Z","lat":6.94, "lon":103.59,"desc":"Transponder OFF — primary radar continues","conf":1.0},
    {"time":"2014-03-07T17:30:00Z","lat":7.20, "lon":103.25,"desc":"Military radar — sharp LEFT turn back over peninsula","conf":0.95},
    {"time":"2014-03-07T17:52:00Z","lat":6.50, "lon":99.70, "desc":"Military radar — WMPL waypoint, heading NW","conf":0.92},
    {"time":"2014-03-07T18:02:00Z","lat":6.15, "lon":97.50, "desc":"Military radar — Pulau Perak, last confirmed","conf":0.95},
    {"time":"2014-03-07T18:22:00Z","lat":5.50, "lon":95.30, "desc":"Estimated position from Inmarsat ping arc","conf":0.75},
    {"time":"2014-03-08T00:11:00Z","lat":-38.0,"lon":88.0,  "desc":"7th Inmarsat arc — final handshake before loss","conf":0.80},
]
for e in MH370_EVENTS:
    e["time"]=datetime.datetime.fromisoformat(e["time"].replace("Z","+00:00"))

# Critical anomaly windows
TRANSPONDER_OFF = datetime.datetime(2014,3,7,17,21,tzinfo=datetime.timezone.utc)
LAST_RADAR      = datetime.datetime(2014,3,7,18,2, tzinfo=datetime.timezone.utc)
TURN_BACK       = datetime.datetime(2014,3,7,17,30,tzinfo=datetime.timezone.utc)
FINAL_ARC       = datetime.datetime(2014,3,8,0,11, tzinfo=datetime.timezone.utc)

# Fetch windows — two critical periods
FETCH_START_A = datetime.datetime(2014,3,7,15,0, tzinfo=datetime.timezone.utc)  # Pre-departure to disappearance
FETCH_END_A   = datetime.datetime(2014,3,7,20,0, tzinfo=datetime.timezone.utc)
FETCH_START_B = datetime.datetime(2014,3,7,22,0, tzinfo=datetime.timezone.utc)  # Final arc period
FETCH_END_B   = datetime.datetime(2014,3,8, 2,0, tzinfo=datetime.timezone.utc)

# Stations closest to MH370's known and estimated tracks
# South/Southeast Asian network + Indian Ocean
STATIONS_A = {
    "GUA": {"lat":13.588,"lon":144.867,"name":"Guam",           "color":GRN},
    "HON": {"lat":21.316,"lon":-158.000,"name":"Honolulu HI",   "color":AMB},
    "KAK": {"lat":35.775,"lon":140.186,"name":"Kakioka Japan",  "color":BLU},
    "PHU": {"lat":11.645,"lon":104.989,"name":"Phu Thuy Vietnam","color":RED},
}

T0 = FETCH_START_A

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
    a=np.sin(dlat/2)**2+np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def fetch(sid, start, end):
    params={"id":sid,"starttime":start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime":end.strftime("%Y-%m-%dT%H:%M:%SZ"),"elements":"H,D,Z",
            "sampling_period":60,"format":"json","type":"definitive"}
    try:
        r=requests.get("https://geomag.usgs.gov/ws/data/",params=params,timeout=30)
        r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"    {sid} error: {e}"); return None

def parse(raw):
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
print("[1] Fetching Kp index for March 8 2014...")
kp_records=fetch_kp(2014,3)
event_kp=[r for r in kp_records if
          FETCH_START_A-datetime.timedelta(hours=6)<=r["time"]<=FETCH_END_B+datetime.timedelta(hours=6)]
max_kp=max([r["kp"] for r in event_kp]) if event_kp else None
kp_quiet = max_kp is not None and max_kp < 3
print(f"    Max Kp: {max_kp}  |  Quiet: {kp_quiet}")
if not kp_quiet:
    print(f"    WARNING: Kp={max_kp} — geomagnetic activity present. Solar explanation possible.")
else:
    print(f"    Kp quiet — any magnetometer anomalies would be localized")

# ── FETCH STATIONS ────────────────────────────────────────────────────────────
print("\n[2] Fetching magnetometer stations (disappearance window)...")
all_data={}
for sid,info in STATIONS_A.items():
    print(f"    Fetching {sid} ({info['name']})...")
    raw=fetch(sid, FETCH_START_A, FETCH_END_A)
    data=parse(raw)
    if data:
        all_data[sid]=data
        print(f"    {sid}: {len(data['times'])} minutes")
    else:
        print(f"    {sid}: no data — may not be in USGS network")

# ── ANOMALY SCAN ──────────────────────────────────────────────────────────────
print("\n[3] Scanning for anomalies at key MH370 events...")
key_events=[
    ("Transponder OFF",   TRANSPONDER_OFF),
    ("Sharp turn-back",   TURN_BACK),
    ("Last radar contact",LAST_RADAR),
]

event_anomalies={}
for label,evt_time in key_events:
    window_s=evt_time-datetime.timedelta(minutes=10)
    window_e=evt_time+datetime.timedelta(minutes=10)
    print(f"\n    {label} ({evt_time.strftime('%H:%M UTC')}):")
    event_anomalies[label]=[]
    for sid,data in all_data.items():
        if "D" not in data["fields"]: continue
        sc=rolling_score(data["fields"]["D"])
        idx=[i for i,t in enumerate(data["times"]) if window_s<=t<=window_e]
        if not idx: continue
        peak=float(np.max(sc[idx]))
        peak_t=data["times"][idx[np.argmax(sc[idx])]]
        flag=" *** ANOMALY" if peak>2.0 else ""
        print(f"      {sid}: peak={peak:.3f}s at {peak_t.strftime('%H:%M UTC')}{flag}")
        if peak>2.0:
            event_anomalies[label].append({"station":sid,"sigma":round(peak,3),
                                           "time":peak_t.isoformat()})

# ── CROSS-CORRELATION ─────────────────────────────────────────────────────────
print("\n[4] Cross-correlation during disappearance window...")
disap_s=datetime.datetime(2014,3,7,17,0,tzinfo=datetime.timezone.utc)
disap_e=datetime.datetime(2014,3,7,19,0,tzinfo=datetime.timezone.utc)
sids=list(all_data.keys())
corr_val=0; lag_val=0
if len(sids)>=2:
    s1,s2=sids[0],sids[1]
    d1=all_data[s1]["fields"].get("D",np.array([]))
    d2=all_data[s2]["fields"].get("D",np.array([]))
    t1=all_data[s1]["times"]; t2=all_data[s2]["times"]
    idx1=[i for i,t in enumerate(t1) if disap_s<=t<=disap_e]
    idx2=[i for i,t in enumerate(t2) if disap_s<=t<=disap_e]
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
            print(f"    {s1}-{s2} correlation: {corr_val:.4f}  lag={lag_val}min")

# ── PLOT ──────────────────────────────────────────────────────────────────────
print("\n[5] Generating plots...")
os.makedirs("event_outputs/MH370_2014",exist_ok=True)

fig=plt.figure(figsize=(22,16),facecolor=BG)
gs2=GridSpec(3,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)

# Panel 1: All stations D normalized
ax1=fig.add_subplot(gs2[0,:])
ax1.set_facecolor("#010402"); ax1.tick_params(colors=DIM,labelsize=8)
for sp in ax1.spines.values(): sp.set_color("#0a2211")
for label,evt_time in key_events:
    ax1.axvline(t2min(evt_time),color=RED,linewidth=1.5,alpha=0.8,linestyle="--")
    ax1.text(t2min(evt_time)+0.5,2.5,label,color=RED,fontsize=6,fontfamily=MONO,
            rotation=45,ha="left",path_effects=[pe.withStroke(linewidth=1.5,foreground=BG)])
for sid,data in all_data.items():
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    norm=normalize(data["fields"]["D"])
    ax1.plot(tmin,norm,color=STATIONS_A[sid]["color"],linewidth=1.3,alpha=0.85,
            label=f"{sid} ({STATIONS_A[sid]['name']})")
ax1.set_title("MH370 — ALL STATIONS D-FIELD NORMALIZED\nRed dashed = key MH370 events. Looking for anomalies at transponder-off and turn-back.",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax1.set_xlabel("Minutes from 15:00 UTC 2014-03-07",color=DIM,fontfamily=MONO,fontsize=8)
ax1.set_ylabel("Normalized deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=8,loc="upper left")
ax1.set_xlim(0,300)

# Panel 2: Sigma scores zoomed to disappearance window
ax2=fig.add_subplot(gs2[1,:])
ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=8)
for sp in ax2.spines.values(): sp.set_color("#0a2211")
ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
ax2.axhline(3.0,color=RED,linewidth=0.5,linestyle=":",alpha=0.5,label="3sigma")
for label,evt_time in key_events:
    ax2.axvline(t2min(evt_time),color=RED,linewidth=1.5,alpha=0.8,linestyle="--")
for sid,data in all_data.items():
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax2.plot(tmin,sc,color=STATIONS_A[sid]["color"],linewidth=1.3,alpha=0.85,label=f"{sid} sigma")
ax2.set_title("ANOMALY SCORES — MH370 DISAPPEARANCE WINDOW\nLooking for sigma spikes correlating with transponder-off, turn-back, last radar",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax2.set_xlabel("Minutes from 15:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=8,loc="upper right")
ax2.set_ylim(bottom=0); ax2.set_xlim(0,300)

# Panel 3L: Map
ax3=fig.add_subplot(gs2[2,0])
ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=7)
for sp in ax3.spines.values(): sp.set_color("#0a2211")
for lat in range(-50,25,10):
    ax3.axhline(lat,color=GFNT,linewidth=0.3,linestyle="--")
for lon in range(60,180,20):
    ax3.axvline(lon,color=GFNT,linewidth=0.3,linestyle="--")
ev_lons=[e["lon"] for e in MH370_EVENTS]; ev_lats=[e["lat"] for e in MH370_EVENTS]
ax3.plot(ev_lons[:6],ev_lats[:6],color=AMB,linewidth=2,alpha=0.8,label="Known track")
ax3.plot(ev_lons[0],ev_lats[0],"o",color=GRN,markersize=8,label="KL departure")
ax3.plot(ev_lons[5],ev_lats[5],"^",color=RED,markersize=8,label="Last radar")
ax3.plot(ev_lons[-1],ev_lats[-1],"x",color=RED,markersize=10,label="7th arc")
for e in MH370_EVENTS[:6]:
    ax3.text(e["lon"]+0.5,e["lat"]+0.5,e["time"].strftime("%H:%M"),
            color=AMB,fontsize=5,fontfamily=MONO)
for sid,info in STATIONS_A.items():
    if sid in all_data:
        ax3.plot(info["lon"],info["lat"],"o",color=info["color"],markersize=8,zorder=5)
        ax3.text(info["lon"]+0.5,info["lat"]+0.5,sid,color=info["color"],fontsize=7,fontfamily=MONO)
ax3.set_xlim(60,180); ax3.set_ylim(-50,25)
ax3.set_title("MH370 TRACK + MAGNETOMETER STATIONS",color=GRN,fontfamily=MONO,fontsize=8)
ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=6)

# Panel 3R: Findings
ax4=fig.add_subplot(gs2[2,1])
ax4.set_facecolor("#010402"); ax4.axis("off")
for sp in ax4.spines.values(): sp.set_color(RED if corr_val>0.85 else GDIM)
lines=[
    ("MH370 SENSOR ANALYSIS",GRN,10,True),
    ("2014-03-07/08",WHT,8,False),
    ("",WHT,7,False),
    (f"Kp max: {max_kp}  Quiet: {kp_quiet}",GRN if kp_quiet else AMB,8,True),
    (f"Solar explanation: {'ELIMINATED' if kp_quiet else 'POSSIBLE'}",GRN if kp_quiet else RED,8,True),
    ("",WHT,7,False),
    ("ANOMALIES AT KEY EVENTS:",AMB,9,True),
]
for label,anoms in event_anomalies.items():
    if anoms:
        lines.append((f"{label}:",RED,8,True))
        for a in anoms:
            lines.append((f"  {a['station']}: {a['sigma']:.3f}s",RED,7,False))
    else:
        lines.append((f"{label}: no >2s anomaly",DIM,7,False))
lines+=[
    ("",WHT,7,False),
    (f"Station correlation: {corr_val:.4f}",RED if corr_val>0.85 else WHT,9,True),
    (f"Lag: {lag_val} min",WHT,8,False),
    ("",WHT,7,False),
    ("NOTE ON ORBS VIDEOS:",AMB,8,True),
    ("Viral videos unverified.",WHT,7,False),
    ("Treated as hypothesis only.",WHT,7,False),
    ("Real sensor data is the",WHT,7,False),
    ("only legitimate evidence.",WHT,7,False),
    ("Any anomalies found here",WHT,7,False),
    ("are from gov instruments,",WHT,7,False),
    ("not social media content.",WHT,7,False),
]
y=0.97
for text,color,size,bold in lines:
    ax4.text(0.04,y,text,transform=ax4.transAxes,color=color,fontfamily=MONO,
            fontsize=size,fontweight="bold" if bold else "normal",va="top")
    y-=0.058

fig.suptitle("MH370 — 2014-03-07/08 — MULTI-SENSOR ANOMALY SCAN\nTransponder cutoff / Sharp turn-back / Last radar contact windows",
            color=GRN,fontfamily=MONO,fontsize=11,y=0.97)
out="event_outputs/MH370_2014/MH370_scan.png"
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
plt.close()
print(f"  Plot saved: {out}")

results={
    "event":"MH370","date":"2014-03-07",
    "kp":{"max_kp":max_kp,"quiet":kp_quiet},
    "stations_fetched":list(all_data.keys()),
    "event_anomalies":event_anomalies,
    "correlation":{"value":round(float(corr_val),4),"lag_min":lag_val},
    "note_on_orbs_video":"Viral videos showing orbs circling MH370 are unverified and likely fabricated. This analysis uses only government instrument data.",
}
with open("event_outputs/MH370_2014/MH370_summary.json","w") as f:
    json.dump(results,f,indent=2,default=str)
print("  JSON saved: event_outputs/MH370_2014/MH370_summary.json")

print("\n" + "="*60)
print(f"Kp={max_kp} ({'QUIET' if kp_quiet else 'ACTIVE'})")
print(f"Station correlation: {corr_val:.4f}")
total_anomalies=sum(len(v) for v in event_anomalies.values())
print(f"Anomalies at key events: {total_anomalies}")
print("="*60)
