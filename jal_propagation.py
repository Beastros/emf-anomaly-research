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
  JAL 1628 ALASKA 1986 — WAVEFRONT PROPAGATION ANALYSIS
  3 Alaskan magnetometer stations
  Computing independent velocity from peak arrival times
  NO EYEWITNESS TIMESTAMPS USED
=============================================================
""")

# ── ALASKAN STATIONS ──────────────────────────────────────────────────────────
# BRW = Barrow (northernmost), SIT = Sitka (southeast), CMO = College/Fairbanks
STATIONS = {
    "BRW": {"lat":71.322,"lon":-156.648,"name":"Barrow AK",        "color":RED},
    "CMO": {"lat":64.872,"lon":-147.861,"name":"College/Fairbanks","color":GRN},
    "SIT": {"lat":57.058,"lon":-135.330,"name":"Sitka AK",         "color":AMB},
    "BOU": {"lat":40.137,"lon":-105.237,"name":"Boulder CO",        "color":BLU},
}

# JAL 1628 event window UTC
FETCH_START = datetime.datetime(1986,11,17,3,0,  tzinfo=datetime.timezone.utc)
FETCH_END   = datetime.datetime(1986,11,17,11,0, tzinfo=datetime.timezone.utc)
EVENT_START = datetime.datetime(1986,11,17,6,0,  tzinfo=datetime.timezone.utc)
EVENT_END   = datetime.datetime(1986,11,17,7,30, tzinfo=datetime.timezone.utc)
T0 = FETCH_START

# JAL 1628 flight path (approximate UTC positions)
JAL_TRACK = [
    {"time":"1986-11-17T06:00:00Z","lat":61.50,"lon":-141.00,"desc":"First contact — two objects ahead"},
    {"time":"1986-11-17T06:15:00Z","lat":62.00,"lon":-143.00,"desc":"Anchorage ATC radar confirms"},
    {"time":"1986-11-17T06:30:00Z","lat":62.50,"lon":-145.00,"desc":"Large object — carrier-size"},
    {"time":"1986-11-17T06:45:00Z","lat":63.00,"lon":-147.00,"desc":"Military intercept requested"},
    {"time":"1986-11-17T07:00:00Z","lat":63.50,"lon":-149.00,"desc":"Object disappears as UA approaches"},
    {"time":"1986-11-17T07:20:00Z","lat":64.50,"lon":-147.00,"desc":"Fairbanks — object gone"},
]
for w in JAL_TRACK:
    w["time"] = datetime.datetime.fromisoformat(w["time"].replace("Z","+00:00"))

# Known peak times from batch run
KNOWN_PEAKS = {
    "BRW": datetime.datetime(1986,11,17,6,24,tzinfo=datetime.timezone.utc),
    "SIT": datetime.datetime(1986,11,17,6,25,tzinfo=datetime.timezone.utc),
    "CMO": datetime.datetime(1986,11,17,6,38,tzinfo=datetime.timezone.utc),
}

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
    a=np.sin(dlat/2)**2+np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def fetch(sid):
    params={"id":sid,"starttime":FETCH_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endtime":FETCH_END.strftime("%Y-%m-%dT%H:%M:%SZ"),"elements":"H,D,Z",
            "sampling_period":60,"format":"json","type":"definitive"}
    print(f"  Fetching {sid} ({STATIONS[sid]['name']})...")
    try:
        r=requests.get("https://geomag.usgs.gov/ws/data/",params=params,timeout=30)
        r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"  {sid} error: {e}"); return None

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

def interpret_v(v_kmh):
    if v_kmh<10:     return "Very slow — ionospheric drift"
    elif v_kmh<340:  return "Subsonic — pressure wave"
    elif v_kmh<1200: return "Transonic/supersonic — fast atmospheric"
    elif v_kmh<5000: return "HYPERSONIC — fast EM source or Alfven wave"
    elif v_kmh<50000:return "EXTREME — magnetospheric coupling"
    else:            return "Near-instantaneous — EM radiation / field collapse"

# ── FETCH ─────────────────────────────────────────────────────────────────────
print("[1] Fetching stations...")
all_data={}
for sid in STATIONS:
    raw=fetch(sid)
    data=parse(raw)
    if data:
        all_data[sid]=data
        print(f"    {sid}: {len(data['times'])} minutes")
    else:
        print(f"    {sid}: no data")

# ── FIND PEAKS ────────────────────────────────────────────────────────────────
print("\n[2] Finding peak anomaly times in event window...")
extended_s = EVENT_START - datetime.timedelta(hours=1)
extended_e = EVENT_END   + datetime.timedelta(hours=1)

actual_peaks={}
for sid,data in all_data.items():
    if "D" not in data["fields"]: continue
    sc=rolling_score(data["fields"]["D"])
    idx=[i for i,t in enumerate(data["times"]) if extended_s<=t<=extended_e]
    if not idx: continue
    peak_idx=idx[np.argmax(sc[idx])]
    peak_t=data["times"][peak_idx]
    peak_s=sc[peak_idx]
    actual_peaks[sid]={"time":peak_t,"sigma":round(float(peak_s),3)}
    in_ev = "IN EVENT WINDOW" if EVENT_START<=peak_t<=EVENT_END else "outside window"
    print(f"    {sid}: peak={peak_s:.3f}s at {peak_t.strftime('%H:%M:%S UTC')} ({in_ev})")

# Use known peaks from batch run if actual peaks are close
print("\n[3] Cross-referencing with known batch peaks...")
for sid,known_t in KNOWN_PEAKS.items():
    if sid in actual_peaks:
        diff=(actual_peaks[sid]["time"]-known_t).total_seconds()/60
        print(f"    {sid}: batch={known_t.strftime('%H:%M')} actual={actual_peaks[sid]['time'].strftime('%H:%M')} diff={diff:.0f}min")

# Use actual peaks for calculation
peaks_to_use = actual_peaks if actual_peaks else {
    sid: {"time":t,"sigma":3.0} for sid,t in KNOWN_PEAKS.items()
}

# ── WAVEFRONT VELOCITY ────────────────────────────────────────────────────────
print("\n[4] WAVEFRONT PROPAGATION VELOCITY CALCULATION")
print("="*60)
print("Logic: Peak anomaly time difference between stations")
print("       + known distance = propagation velocity")
print("       Zero eyewitness data used.\n")

# All pairs
pairs=[]
sids=list(peaks_to_use.keys())
for i in range(len(sids)):
    for j in range(i+1,len(sids)):
        s1,s2=sids[i],sids[j]
        if s1 not in STATIONS or s2 not in STATIONS: continue
        p1,p2=peaks_to_use[s1],peaks_to_use[s2]
        dt=(p2["time"]-p1["time"]).total_seconds()
        dist=haversine_km(STATIONS[s1]["lat"],STATIONS[s1]["lon"],
                         STATIONS[s2]["lat"],STATIONS[s2]["lon"])
        v=abs(dist/dt)*3600 if dt!=0 else float("inf")
        direction="S1 then S2" if dt>0 else "S2 then S1"
        pairs.append({
            "s1":s1,"s2":s2,
            "s1_name":STATIONS[s1]["name"],"s2_name":STATIONS[s2]["name"],
            "s1_peak":p1["time"].strftime("%H:%M:%S UTC"),
            "s2_peak":p2["time"].strftime("%H:%M:%S UTC"),
            "dt_seconds":dt,"dt_minutes":round(dt/60,1),
            "dist_km":round(dist,1),"velocity_kmh":round(v,1),
            "direction":direction,
            "interpretation":interpret_v(v),
            "s1_sigma":p1["sigma"],"s2_sigma":p2["sigma"],
        })
        print(f"  {s1} ({STATIONS[s1]['name']}) → {s2} ({STATIONS[s2]['name']})")
        print(f"    Distance:  {dist:.0f} km")
        print(f"    {s1} peak: {p1['time'].strftime('%H:%M:%S')} ({p1['sigma']:.3f}s)")
        print(f"    {s2} peak: {p2['time'].strftime('%H:%M:%S')} ({p2['sigma']:.3f}s)")
        print(f"    Dt:        {dt/60:.1f} minutes ({dt:.0f} seconds)")
        print(f"    Velocity:  {v:.0f} km/h")
        print(f"    Order:     {direction}")
        print(f"    Meaning:   {interpret_v(v)}")
        print()

# ── JAL POSITION AT PEAK TIMES ───────────────────────────────────────────────
print("[5] JAL 1628 position at time of each station peak...")
for sid,peak in peaks_to_use.items():
    pt=peak["time"]
    closest=min(JAL_TRACK,key=lambda w:abs((w["time"]-pt).total_seconds()))
    dist_to_jal=haversine_km(STATIONS[sid]["lat"],STATIONS[sid]["lon"],
                             closest["lat"],closest["lon"])
    print(f"    {sid} peak {pt.strftime('%H:%M UTC')}: nearest JAL pos = {closest['desc'][:40]}")
    print(f"       Distance station→JAL: {dist_to_jal:.0f} km")

# ── COMPARE TO EYEWITNESS VELOCITY ────────────────────────────────────────────
print("\n[6] Cross-check against JAL 747 speed...")
print("    Boeing 747-200 cruise: ~900 km/h")
print("    JAL was pacing the object — object speed ≈ aircraft speed")
print("    If wavefront velocity >> 900 km/h → object was faster than aircraft")
print("    If wavefront velocity ≈ 900 km/h → consistent with pacing object")
if pairs:
    alaska_pairs=[p for p in pairs if p["s1"] in ["BRW","SIT","CMO"] and p["s2"] in ["BRW","SIT","CMO"]]
    if alaska_pairs:
        avg_v=np.mean([p["velocity_kmh"] for p in alaska_pairs if p["velocity_kmh"]<1e8])
        print(f"\n    Average Alaska station wavefront: {avg_v:.0f} km/h")
        print(f"    vs 747 cruise: 900 km/h")
        if avg_v > 1500:
            print(f"    RESULT: Wavefront {avg_v/900:.1f}x faster than 747 → object faster than pacing aircraft")
        elif 600 < avg_v < 1200:
            print(f"    RESULT: Wavefront consistent with ~aircraft speed → supports pacing object")
        else:
            print(f"    RESULT: Wavefront speed doesn't match aircraft model — different physics")

# ── GENERATE PLOT ─────────────────────────────────────────────────────────────
print("\n[7] Generating plots...")
os.makedirs("event_outputs/JAL1628_1986",exist_ok=True)

fig=plt.figure(figsize=(22,16),facecolor=BG)
gs=GridSpec(3,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)

# Panel 1: All stations D normalized full window
ax1=fig.add_subplot(gs[0,:])
ax1.set_facecolor("#010402"); ax1.tick_params(colors=DIM,labelsize=8)
for sp in ax1.spines.values(): sp.set_color("#0a2211")
ax1.axvspan(t2min(EVENT_START),t2min(EVENT_END),alpha=0.08,color=RED,label="Event window")
for sid,data in all_data.items():
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    norm=normalize(data["fields"]["D"])
    ax1.plot(tmin,norm,color=STATIONS[sid]["color"],linewidth=1.5,alpha=0.85,label=f"{sid} ({STATIONS[sid]['name']})")
    if sid in peaks_to_use:
        pt=peaks_to_use[sid]["time"]
        ax1.axvline(t2min(pt),color=STATIONS[sid]["color"],linewidth=1.5,linestyle="--",alpha=0.7)
for w in JAL_TRACK:
    ax1.axvline(t2min(w["time"]),color=AMB,linewidth=0.5,alpha=0.4,linestyle=":")
ax1.set_title("JAL 1628 — ALL STATIONS D-FIELD NORMALIZED\nDashed lines = peak anomaly times. Dotted = JAL position reports.",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax1.set_xlabel("Minutes from 03:00 UTC 1986-11-17",color=DIM,fontfamily=MONO,fontsize=8)
ax1.set_ylabel("Normalized deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=8,loc="upper left")

# Panel 2: Sigma scores
ax2=fig.add_subplot(gs[1,:])
ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=8)
for sp in ax2.spines.values(): sp.set_color("#0a2211")
ax2.axvspan(t2min(EVENT_START),t2min(EVENT_END),alpha=0.08,color=RED)
ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
ax2.axhline(3.0,color=RED,linewidth=0.5,linestyle=":",alpha=0.5,label="3sigma")
for sid,data in all_data.items():
    if "D" not in data["fields"]: continue
    tmin=[t2min(t) for t in data["times"]]
    sc=rolling_score(data["fields"]["D"])
    ax2.plot(tmin,sc,color=STATIONS[sid]["color"],linewidth=1.3,alpha=0.85,label=f"{sid} sigma")
    if sid in peaks_to_use:
        pt=peaks_to_use[sid]["time"]
        ps=peaks_to_use[sid]["sigma"]
        ax2.annotate(f"{sid}\n{pt.strftime('%H:%M')}\n{ps:.2f}s",
                    xy=(t2min(pt),ps),xytext=(t2min(pt)+3,ps+0.3),
                    color=STATIONS[sid]["color"],fontsize=6,fontfamily=MONO,
                    arrowprops=dict(arrowstyle="->",color=STATIONS[sid]["color"],lw=0.8))
for w in JAL_TRACK:
    ax2.axvline(t2min(w["time"]),color=AMB,linewidth=0.5,alpha=0.4,linestyle=":")
ax2.set_title("ANOMALY SCORES — ANNOTATED WITH PEAK TIMES\nSequence of peaks reveals propagation direction and velocity",
             color=GRN,fontfamily=MONO,fontsize=9,pad=8)
ax2.set_xlabel("Minutes from 03:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax2.set_ylabel("Sigma deviation",color=DIM,fontfamily=MONO,fontsize=8)
ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=8,loc="upper right")
ax2.set_ylim(bottom=0)

# Panel 3L: Alaska map with propagation arrows
ax3=fig.add_subplot(gs[2,0])
ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=7)
for sp in ax3.spines.values(): sp.set_color("#0a2211")
for lat in range(55,75,5):
    ax3.axhline(lat,color=GFNT,linewidth=0.3,linestyle="--")
for lon in range(-165,-125,10):
    ax3.axvline(lon,color=GFNT,linewidth=0.3,linestyle="--")
# JAL track
jal_lons=[w["lon"] for w in JAL_TRACK]; jal_lats=[w["lat"] for w in JAL_TRACK]
ax3.plot(jal_lons,jal_lats,color=AMB,linewidth=2,alpha=0.8,label="JAL 1628 track")
ax3.plot(jal_lons[0],jal_lats[0],"o",color=AMB,markersize=8)
for w in JAL_TRACK[::2]:
    ax3.text(w["lon"]+0.3,w["lat"]+0.3,w["time"].strftime("%H:%M"),
            color=AMB,fontsize=6,fontfamily=MONO)
# Stations with peak time labels
sorder=sorted([s for s in peaks_to_use if s in STATIONS],key=lambda s:peaks_to_use[s]["time"])
for rank,sid in enumerate(sorder):
    info=STATIONS[sid]; peak=peaks_to_use[sid]
    ax3.plot(info["lon"],info["lat"],"o",color=info["color"],markersize=10,zorder=5)
    ax3.plot(info["lon"],info["lat"],"o",color=BG,markersize=5,zorder=6)
    ax3.text(info["lon"]+0.5,info["lat"]+0.5,
            f"{sid}\n{peak['time'].strftime('%H:%M')}\n#{rank+1}",
            color=info["color"],fontsize=7,fontfamily=MONO,fontweight="bold")
# Draw propagation sequence arrows
for i in range(len(sorder)-1):
    s1,s2=sorder[i],sorder[i+1]
    if s1 in STATIONS and s2 in STATIONS:
        ax3.annotate("",
            xy=(STATIONS[s2]["lon"],STATIONS[s2]["lat"]),
            xytext=(STATIONS[s1]["lon"],STATIONS[s1]["lat"]),
            arrowprops=dict(arrowstyle="-|>",color=WHT,lw=1.5,alpha=0.7))
ax3.set_xlim(-170,-120); ax3.set_ylim(53,75)
ax3.set_title("PROPAGATION SEQUENCE MAP\n#1→#2→#3 = order of peak anomaly arrival",
             color=GRN,fontfamily=MONO,fontsize=8)
ax3.set_xlabel("Longitude",color=DIM,fontfamily=MONO,fontsize=7)
ax3.set_ylabel("Latitude",color=DIM,fontfamily=MONO,fontsize=7)
ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7)

# Panel 3R: Velocity results table
ax4=fig.add_subplot(gs[2,1])
ax4.set_facecolor("#010402"); ax4.axis("off")
for sp in ax4.spines.values(): sp.set_color(RED)
lines=[
    ("JAL 1628 WAVEFRONT VELOCITIES",GRN,10,True),
    ("1986-11-17 Alaska",WHT,8,False),
    ("No eyewitness timestamps used.",WHT,8,False),
    ("",WHT,7,False),
]
for p in pairs:
    v=p["velocity_kmh"]
    c=RED if v>1500 else AMB if v>800 else GRN
    lines.append((f"{p['s1']}→{p['s2']}: {v:.0f} km/h",c,8,True))
    lines.append((f"  dt={p['dt_minutes']:.0f}min dist={p['dist_km']:.0f}km",WHT,7,False))
    lines.append((f"  {p['interpretation'][:45]}",c,7,False))
    lines.append(("",WHT,6,False))
alaska_pairs2=[p for p in pairs if p["s1"] in ["BRW","SIT","CMO"] and p["s2"] in ["BRW","SIT","CMO"]]
if alaska_pairs2:
    valid_v=[p["velocity_kmh"] for p in alaska_pairs2 if p["velocity_kmh"]<1e8]
    if valid_v:
        avg=np.mean(valid_v)
        lines.append(("",WHT,7,False))
        lines.append(("ALASKA AVERAGE WAVEFRONT:",AMB,9,True))
        lines.append((f"{avg:.0f} km/h",RED if avg>1500 else AMB,10,True))
        lines.append(("vs 747 cruise: 900 km/h",WHT,8,False))
        ratio=avg/900
        lines.append((f"= {ratio:.1f}x faster than 747",RED if ratio>1.5 else GRN,9,True))
y=0.97
for text,color,size,bold in lines:
    ax4.text(0.04,y,text,transform=ax4.transAxes,color=color,fontfamily=MONO,
            fontsize=size,fontweight="bold" if bold else "normal",va="top")
    y-=0.055

fig.suptitle("JAL FLIGHT 1628 — 1986-11-17 ALASKA\nMULTI-STATION MAGNETOMETER WAVEFRONT PROPAGATION ANALYSIS",
            color=GRN,fontfamily=MONO,fontsize=11,y=0.97)
out="event_outputs/JAL1628_1986/JAL1628_wavefront.png"
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG)
plt.close()
print(f"  Plot saved: {out}")

results={"event":"JAL1628_1986","date":"1986-11-17","pairs":pairs,
         "known_peaks":{k:v.isoformat() for k,v in KNOWN_PEAKS.items()},
         "actual_peaks":{k:{"time":v["time"].isoformat(),"sigma":v["sigma"]} for k,v in actual_peaks.items()}}
with open("event_outputs/JAL1628_1986/JAL1628_wavefront.json","w") as f:
    json.dump(results,f,indent=2,default=str)
print("  JSON saved: event_outputs/JAL1628_1986/JAL1628_wavefront.json")
print("\nDone.")
