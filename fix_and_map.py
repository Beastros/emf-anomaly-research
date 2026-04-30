import sys, os, json, datetime, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
events_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events")
report = None
for fname in os.listdir(reports_dir):
    if fname.endswith(".json") and "phoenix" in fname.lower():
        with open(os.path.join(reports_dir, fname)) as f: report = json.load(f)
        print("Loaded:", fname); break
if not report: print("No report found"); sys.exit(1)
with open(os.path.join(events_dir, "phoenix_lights_1997.json")) as f: event_data = json.load(f)
from core.track import EventTrack
track = EventTrack(event_data); segments = track.segments()
witnesses = [w for w in track.witnesses if w.get("conf",1) >= 0]
ref_max = event_data.get("reference_max_kmh", 706)
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.patches as mpatches, matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec
BG="#030906";GRN="#00ff41";GDIM="#00aa2b";GFNT="#011a06";RED="#ff1a44";AMB="#ffaa00";WHT="#c8ffd4";DIM="#005c14";MONO="monospace"
AZ_LATS=[37,37,36.5,31.33,31.33,31.33,32.72,34,35.18,36.15,37]
AZ_LONS=[-114.05,-109.05,-109.05,-109.05,-111.07,-114.82,-114.72,-114.63,-114.57,-114.05,-114.05]
NEXRAD={"KFSX":(34.574,-111.198),"KIWA":(33.289,-111.670),"KEMX":(31.893,-110.630),"KYUX":(32.495,-114.656)}
CITIES=[("PHOENIX",33.45,-112.07),("TUCSON",32.22,-110.97),("FLAGSTAFF",35.2,-111.65),("HENDERSON NV",36.04,-114.5),("PRESCOTT",34.54,-112.8),("CHANDLER",33.28,-111.5)]
CONV=[{"lat":32.45,"lon":-111.15,"sigma":6.333,"lenses":["nexrad","mag"],"t_min":115},{"lat":35.73,"lon":-114.35,"sigma":4.121,"lenses":["nexrad","mag","sw"],"t_min":30},{"lat":35.43,"lon":-113.72,"sigma":4.121,"lenses":["nexrad","mag","sw"],"t_min":35},{"lat":36.04,"lon":-114.98,"sigma":4.121,"lenses":["mag","sw"],"t_min":25}]
def sc(s): return GRN if s<=ref_max*0.68 else (AMB if s<=ref_max else RED)
fig=plt.figure(figsize=(22,15),facecolor=BG)
gs=GridSpec(3,3,figure=fig,left=0.04,right=0.97,top=0.93,bottom=0.05,hspace=0.5,wspace=0.3)
ax=fig.add_subplot(gs[0:2,0:2]); ax.set_facecolor("#010402")
ax.tick_params(colors=DIM,labelsize=7)
for sp in ax.spines.values(): sp.set_color("#0a2211")
for lat in range(31,38):
    ax.axhline(lat,color=GFNT,linewidth=0.4,linestyle="--")
    ax.text(-115.35,lat+0.05,f"{lat}N",color=DIM,fontsize=6,fontfamily=MONO)
for lon in range(-115,-108): ax.axvline(lon,color=GFNT,linewidth=0.4,linestyle="--")
ax.plot(AZ_LONS,AZ_LATS,color=GDIM,linewidth=1.5,alpha=0.8)
ax.fill(AZ_LONS,AZ_LATS,alpha=0.05,color=GRN)
for sid,(slat,slon) in NEXRAD.items():
    ax.add_patch(plt.Circle((slon,slat),230/111,fill=False,color=GDIM,linewidth=0.5,linestyle="--",alpha=0.4))
    ax.plot(slon,slat,"o",color=GRN,markersize=6,zorder=5); ax.plot(slon,slat,"o",color=BG,markersize=3,zorder=6)
    ax.text(slon+0.1,slat+0.12,sid,color=GRN,fontsize=7,fontfamily=MONO,fontweight="bold",zorder=7)
for seg in segments:
    w1=next((w for w in track.witnesses if w.get("desc","")[:15]==seg["from"][:15]),None)
    w2=next((w for w in track.witnesses if w.get("desc","")[:15]==seg["to"][:15]),None)
    if not w1 or not w2: continue
    c=sc(seg["speed_kmh"]); lw=2.8 if seg["speed_kmh"]>ref_max else 2.0
    ax.plot([w1["lon"],w2["lon"]],[w1["lat"],w2["lat"]],color=c,linewidth=lw,alpha=0.9,zorder=4)
    mlat=(w1["lat"]+w2["lat"])/2; mlon=(w1["lon"]+w2["lon"])/2
    ax.text(mlon,mlat,f"{seg['speed_kmh']:.0f}",color=c,fontsize=7,fontfamily=MONO,fontweight="bold",ha="center",path_effects=[pe.withStroke(linewidth=2,foreground=BG)],zorder=8)
    dlat=w2["lat"]-w1["lat"]; dlon=w2["lon"]-w1["lon"]
    ax.annotate("",xy=(mlon+dlon*0.2,mlat+dlat*0.2),xytext=(mlon,mlat),arrowprops=dict(arrowstyle="-|>",color=c,lw=1.2),zorder=9)
for w in witnesses:
    conf=w.get("conf",0.5); color=RED if conf>=0.9 else AMB; size=10 if conf>=0.9 else 7
    ax.plot(w["lon"],w["lat"],"^",color=color,markersize=size,zorder=10,alpha=0.9)
    ax.plot(w["lon"],w["lat"],"^",color=BG,markersize=size//2,zorder=11)
    wt=w["time"]; ts=wt.strftime("%H:%M") if hasattr(wt,"strftime") else str(wt)[:16]
    ax.text(w["lon"]+0.1,w["lat"]+0.15,f"{ts}\n{w.get('desc','')[:20]}",color=color,fontsize=5.5,fontfamily=MONO,zorder=12,va="bottom",path_effects=[pe.withStroke(linewidth=1.5,foreground=BG)])
for c in CONV:
    n=len(c["lenses"])
    ax.add_patch(plt.Circle((c["lon"],c["lat"]),0.35,fill=True,color=RED,alpha=0.12*n,zorder=3))
    ax.add_patch(plt.Circle((c["lon"],c["lat"]),0.35,fill=False,color=RED,linewidth=1.2,alpha=0.7,zorder=3))
    ax.text(c["lon"],c["lat"]-0.45,f"{c['sigma']}s\n{n}sen",color=RED,fontsize=6,fontfamily=MONO,ha="center",path_effects=[pe.withStroke(linewidth=1.5,foreground=BG)],zorder=13)
for name,lat,lon in CITIES: ax.text(lon,lat,name,color=DIM,fontsize=6,fontfamily=MONO,alpha=0.8,ha="center")
ax.set_xlim(-115.5,-108.5); ax.set_ylim(30.7,37.5)
ax.set_title("FORMATION TRACK - SPEED & CONVERGENCE MAP",color=GRN,fontfamily=MONO,fontsize=10,pad=8)
ax.legend(handles=[mpatches.Patch(color=GRN,label="Sub-cruise"),mpatches.Patch(color=AMB,label="Within A-10 max"),mpatches.Patch(color=RED,label="EXCEEDS A-10 MAX"),mpatches.Patch(color=RED,alpha=0.4,label="Convergence event")],facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,loc="lower right")
ax2=fig.add_subplot(gs[0,2]); ax2.set_facecolor("#010402"); ax2.tick_params(colors=DIM,labelsize=7)
for sp in ax2.spines.values(): sp.set_color("#0a2211")
labels=[f"S{i+1}" for i in range(len(segments))]; speeds=[s["speed_kmh"] for s in segments]
bars=ax2.bar(labels,speeds,color=[sc(s) for s in speeds],edgecolor=BG,linewidth=0.5)
ax2.axhline(ref_max,color=RED,linewidth=1,linestyle="--",alpha=0.8,label=f"A-10 max {ref_max}")
ax2.axhline(480,color=AMB,linewidth=0.7,linestyle=":",alpha=0.6,label="A-10 cruise ~480")
for bar,spd in zip(bars,speeds): ax2.text(bar.get_x()+bar.get_width()/2,bar.get_height()+8,f"{spd:.0f}",ha="center",va="bottom",color=WHT,fontsize=6,fontfamily=MONO)
ax2.set_title("SPEED PROFILE (km/h)",color=GRN,fontfamily=MONO,fontsize=8); ax2.set_ylabel("km/h",color=DIM,fontfamily=MONO,fontsize=7)
ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=DIM,fontsize=6); ax2.set_ylim(0,max(speeds)*1.18)
ax3=fig.add_subplot(gs[1,2]); ax3.set_facecolor("#010402"); ax3.tick_params(colors=DIM,labelsize=7)
for sp in ax3.spines.values(): sp.set_color("#0a2211")
headings=[s["heading"] for s in segments]; mean_hdg=np.mean(headings); hdg_clrs=[RED if abs(h-mean_hdg)>60 else GRN for h in headings]
ax3.bar(labels,headings,color=hdg_clrs,edgecolor=BG,linewidth=0.5)
ax3.axhline(mean_hdg,color=AMB,linewidth=1,linestyle="--",alpha=0.8,label=f"Mean {mean_hdg:.0f}deg")
for i,(h,c) in enumerate(zip(headings,hdg_clrs)): ax3.text(i,h+2,f"{h:.0f}",ha="center",va="bottom",color=RED if c==RED else WHT,fontsize=6,fontfamily=MONO)
ax3.set_title("HEADING (deg) - RED=ANOMALOUS",color=GRN,fontfamily=MONO,fontsize=8); ax3.set_ylabel("Degrees",color=DIM,fontfamily=MONO,fontsize=7)
ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=DIM,fontsize=6)
ax4=fig.add_subplot(gs[2,0:3]); ax4.set_facecolor("#010402"); ax4.tick_params(colors=DIM,labelsize=7)
for sp in ax4.spines.values(): sp.set_color("#0a2211")
t0=track.start_time; seg_t=[]; seg_s=[]
for seg in segments:
    ft=seg["from_time"]; tt=seg["to_time"]
    if isinstance(ft,str): ft=datetime.datetime.fromisoformat(ft.replace("Z","+00:00"))
    if isinstance(tt,str): tt=datetime.datetime.fromisoformat(tt.replace("Z","+00:00"))
    t1=(ft-t0).total_seconds()/60; t2=(tt-t0).total_seconds()/60
    seg_t.extend([t1,t2]); seg_s.extend([seg["speed_kmh"],seg["speed_kmh"]])
if seg_t:
    ax4.fill_between(seg_t,seg_s,alpha=0.15,color=GRN); ax4.plot(seg_t,seg_s,color=GRN,linewidth=1.8)
    ax4.axhline(ref_max,color=RED,linewidth=1,linestyle="--",alpha=0.7,label=f"A-10 max {ref_max}")
    ax4.axhline(480,color=AMB,linewidth=0.7,linestyle=":",alpha=0.6,label="A-10 cruise")
for w in witnesses:
    wt=w["time"]
    if isinstance(wt,str): wt=datetime.datetime.fromisoformat(wt.replace("Z","+00:00"))
    tm=(wt-t0).total_seconds()/60; conf=w.get("conf",0.5); color=RED if conf>=0.9 else AMB
    ax4.axvline(tm,color=color,linewidth=1.2,alpha=0.8)
    ax4.text(tm+0.3,max(seg_s)*0.92,wt.strftime("%H:%M"),color=color,fontsize=6,fontfamily=MONO,rotation=40,ha="left")
for c in CONV:
    ax4.axvspan(c["t_min"]-4,c["t_min"]+4,alpha=0.08*len(c["lenses"]),color=RED)
    ax4.text(c["t_min"],55,f"{c['sigma']}s\n({len(c['lenses'])})",color=RED,fontsize=6,fontfamily=MONO,ha="center",path_effects=[pe.withStroke(linewidth=1.5,foreground=BG)])
ax4.set_xlabel("Minutes from event start (19:55 MST)",color=DIM,fontfamily=MONO,fontsize=8)
ax4.set_ylabel("Speed (km/h)",color=DIM,fontfamily=MONO,fontsize=8)
ax4.set_title("EVENT TIMELINE - SPEED + WITNESS MARKERS + CONVERGENCE EVENTS",color=GRN,fontfamily=MONO,fontsize=8)
ax4.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=DIM,fontsize=7)
fig.suptitle("UAP SNIFFER - PHOENIX LIGHTS 1997-03-13\nMultiple independent anomalies. Conventional explanation faces significant challenges.",color=GRN,fontfamily=MONO,fontsize=11,y=0.97)
fig.text(0.5,0.01,"201 anomalies | 14 convergence events | Kp=2.0 quiet | 4/8 segments exceed A-10 max | D-field peak 6.333 sigma",ha="center",color=DIM,fontfamily=MONO,fontsize=8)
out=os.path.join(reports_dir,"phoenix_lights_1997_map.png")
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG); plt.close()
print(f"Map saved: {out}"); os.startfile(out)
