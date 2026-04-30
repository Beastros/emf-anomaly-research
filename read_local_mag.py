import sys,os,json,datetime,glob,numpy as np
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import matplotlib;matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
BG="#030906";GRN="#00ff41";RED="#ff1a44";AMB="#ffaa00";BLU="#00aaff";WHT="#c8ffd4";DIM="#005c14";MONO="monospace"
print("LOCAL MAG READER v3")
def parse_hapi(fp,td):
    times=[];X=[];Y=[];Z=[]
    sid=os.path.basename(fp)[:3].upper()
    with open(fp,"r",errors="ignore") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#"):continue
            p=line.split(",")
            if len(p)<4:continue
            try:
                ts=p[0].replace("Z","")
                if "T" not in ts:ts+="T00:00"
                t=datetime.datetime.fromisoformat(ts+"+00:00")
                if t.date()!=td:continue
                def s(v):fv=float(v);return np.nan if abs(fv)>90000 else fv
                X.append(s(p[1]));Y.append(s(p[2]));Z.append(s(p[3]));times.append(t)
            except:continue
    if not times:return None
    return {"sid":sid,"times":times,"fields":{"X":np.array(X),"Y":np.array(Y),"Z":np.array(Z)}}
def rscore(arr,w=20):
    n=len(arr);sc=np.zeros(n)
    for i in range(n):
        sl=arr[max(0,i-w):i];v=sl[~np.isnan(sl)]
        if len(v)>=3:
            s=np.std(v);sc[i]=abs(arr[i]-np.mean(v))/s if s>0.001 else 0
    return sc
def norm(arr):
    v=arr[~np.isnan(arr)]
    if not len(v):return arr
    mn=np.nanmean(v);sd=np.nanstd(v)
    return (arr-mn)/sd if sd>0.001 else arr-mn
td=datetime.date(2014,3,7)
T0=datetime.datetime(2014,3,7,0,0,0,tzinfo=datetime.timezone.utc)
def t2m(t):return (t-T0).total_seconds()/60
KEY=[
    ("Last ACARS",datetime.datetime(2014,3,7,17,7,tzinfo=datetime.timezone.utc)),
    ("Last ATC",datetime.datetime(2014,3,7,17,19,tzinfo=datetime.timezone.utc)),
    ("TRANSPONDER OFF",datetime.datetime(2014,3,7,17,21,tzinfo=datetime.timezone.utc)),
    ("LEFT TURN",datetime.datetime(2014,3,7,17,30,tzinfo=datetime.timezone.utc)),
    ("Last radar",datetime.datetime(2014,3,7,18,2,tzinfo=datetime.timezone.utc)),
    ("Final arc",datetime.datetime(2014,3,8,0,11,tzinfo=datetime.timezone.utc)),
]
PRIMARY=datetime.datetime(2014,3,7,17,21,tzinfo=datetime.timezone.utc)
out_dir="event_outputs/MH370_2014"
files=glob.glob(os.path.join(out_dir,"*.min"))
print(f"Files found: {len(files)}")
station_data={}
for fp in files:
    d=parse_hapi(fp,td)
    if d:
        sid=d["sid"]
        if sid in station_data:sid+="b"
        station_data[sid]=d
        print(f"  {sid}: {len(d['times'])} minutes")
    else:
        print(f"  Could not parse {os.path.basename(fp)}")
if not station_data:
    print("NO DATA PARSED")
    sys.exit(1)
print(f"\nScanning anomalies...")
hits=[]
for label,evt in KEY:
    ws=evt-datetime.timedelta(minutes=10);we=evt+datetime.timedelta(minutes=10)
    for sid,d in station_data.items():
        for fn,arr in d["fields"].items():
            sc=rscore(arr)
            idx=[i for i,t in enumerate(d["times"]) if ws<=t<=we]
            if not idx:continue
            pk=float(np.max(sc[idx]));pt=d["times"][idx[np.argmax(sc[idx])]]
            if pk>2.0:
                dt=(pt-evt).total_seconds()/60
                print(f"  *** {label}: {sid} {fn} {pk:.3f}s @ {pt.strftime('%H:%M')} ({dt:+.0f}min)")
                hits.append({"label":label,"sid":sid,"fn":fn,"sigma":pk,"time":pt.isoformat(),"dt":dt})
            elif pk>1.5:
                print(f"  {label}: {sid} {fn} {pk:.3f}s")
print(f"\nTotal >2s hits: {len(hits)}")
corr=0;lag=0;bp=("","")
sids=list(station_data.keys())
if len(sids)>=2:
    s1,s2=sids[0],sids[1]
    f1="Y";f2="Y"
    d1=station_data[s1]["fields"][f1];d2=station_data[s2]["fields"][f2]
    t1=station_data[s1]["times"];t2=station_data[s2]["times"]
    ws=PRIMARY-datetime.timedelta(hours=2);we=PRIMARY+datetime.timedelta(hours=2)
    i1=[i for i,t in enumerate(t1) if ws<=t<=we]
    i2=[i for i,t in enumerate(t2) if ws<=t<=we]
    if i1 and i2:
        a=d1[i1];b=d2[i2];ml=min(len(a),len(b));a=a[:ml];b=b[:ml]
        vld=~(np.isnan(a)|np.isnan(b))
        if vld.sum()>5:
            corr=float(np.corrcoef(a[vld],b[vld])[0,1]);bp=(s1,s2)
            print(f"Correlation {s1}-{s2}: {corr:.4f}")
colors=[RED,GRN,AMB,BLU]
fig=plt.figure(figsize=(22,14),facecolor=BG)
gs=GridSpec(3,2,figure=fig,left=0.06,right=0.97,top=0.92,bottom=0.04,hspace=0.55,wspace=0.3)
ax1=fig.add_subplot(gs[0,:]);ax1.set_facecolor("#010402");ax1.tick_params(colors=DIM,labelsize=8)
for sp in ax1.spines.values():sp.set_color("#0a2211")
ax1.axvline(t2m(PRIMARY),color=RED,linewidth=2.5,alpha=0.9,label="TRANSPONDER OFF 17:21 UTC")
for label,evt in KEY:
    if evt!=PRIMARY:ax1.axvline(t2m(evt),color=AMB,linewidth=0.8,alpha=0.5,linestyle="--")
for i,(sid,d) in enumerate(station_data.items()):
    tmin=[t2m(t) for t in d["times"]]
    ax1.plot(tmin,norm(d["fields"]["Y"]),color=colors[i%4],linewidth=1.3,alpha=0.85,label=f"{sid} Y-field")
ax1.set_xlim(0,1440);ax1.set_title("MH370 2014-03-07 Y-FIELD NORMALIZED — Red=Transponder OFF",color=GRN,fontfamily=MONO,fontsize=9)
ax1.set_xlabel("Minutes from 00:00 UTC",color=DIM,fontfamily=MONO,fontsize=8)
ax1.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=4)
ax2=fig.add_subplot(gs[1,:]);ax2.set_facecolor("#010402");ax2.tick_params(colors=DIM,labelsize=8)
for sp in ax2.spines.values():sp.set_color("#0a2211")
ax2.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7,label="2sigma")
ax2.axvline(t2m(PRIMARY),color=RED,linewidth=2.5,alpha=0.9)
for label,evt in KEY:ax2.axvline(t2m(evt),color=AMB,linewidth=0.8,alpha=0.5,linestyle="--")
for i,(sid,d) in enumerate(station_data.items()):
    tmin=[t2m(t) for t in d["times"]]
    ax2.plot(tmin,rscore(d["fields"]["Y"]),color=colors[i%4],linewidth=1.3,alpha=0.85,label=f"{sid}")
ax2.set_xlim(0,1440);ax2.set_ylim(bottom=0)
ax2.set_title("ANOMALY SCORES — Spike at red=corroboration",color=GRN,fontfamily=MONO,fontsize=9)
ax2.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7,ncol=4)
ax3=fig.add_subplot(gs[2,0]);ax3.set_facecolor("#010402");ax3.tick_params(colors=DIM,labelsize=8)
for sp in ax3.spines.values():sp.set_color("#0a2211")
ax3.axhline(2.0,color=RED,linewidth=0.8,linestyle="--",alpha=0.7)
ax3.axvline(t2m(PRIMARY),color=RED,linewidth=2.5,alpha=0.9,label="Transponder OFF")
for label,evt in KEY:ax3.axvline(t2m(evt),color=AMB,linewidth=1,alpha=0.7,linestyle="--")
for i,(sid,d) in enumerate(station_data.items()):
    tmin=[t2m(t) for t in d["times"]]
    ax3.plot(tmin,rscore(d["fields"]["Y"]),color=colors[i%4],linewidth=1.8,alpha=0.9,label=f"{sid}")
ax3.set_xlim(t2m(PRIMARY)-60,t2m(PRIMARY)+120);ax3.set_ylim(bottom=0)
ax3.set_title("ZOOMED — Transponder OFF window",color=RED,fontfamily=MONO,fontsize=8)
ax3.legend(facecolor=BG,edgecolor="#0a2211",labelcolor=WHT,fontsize=7)
ax4=fig.add_subplot(gs[2,1]);ax4.set_facecolor("#010402");ax4.axis("off")
lines=[("MH370 2014-03-07",GRN,10,True),(f"Stations: {list(station_data.keys())}",WHT,7,False),
       ("",WHT,6,False),(f"Total >2s anomalies: {len(hits)}",RED if hits else DIM,9,True),
       ("",WHT,6,False),("PRIMARY: Transponder OFF 17:21 UTC",AMB,9,True),("",WHT,6,False)]
if hits:
    lines+=[("*** CORROBORATION FOUND ***",RED,10,True)]
    for h in hits[:4]:lines+=[(f"{h['sid']} {h['fn']}: {h['sigma']:.3f}s",RED,8,True),(f"  {h['dt']:+.0f}min",AMB,7,False)]
else:
    lines+=[("No anomaly at transponder cutoff",DIM,8,False),("Field quiet at these stations",DIM,7,False)]
lines+=[(f"Correlation: {corr:.4f}",RED if abs(corr)>0.85 else WHT,8,False),("",WHT,6,False),
        ("Phoenix: 0.9704 Nimitz: 0.9780",DIM,7,False),("OHare:   0.9796",DIM,7,False)]
y=0.97
for txt,col,sz,bold in lines:
    ax4.text(0.04,y,txt,transform=ax4.transAxes,color=col,fontfamily=MONO,fontsize=sz,fontweight="bold" if bold else "normal",va="top")
    y-=0.062
fig.suptitle("MH370 2014-03-07 — INTERMAGNET CNB/KAK/KNY\nTransponder OFF 17:21 UTC = primary corroboration target",color=GRN,fontfamily=MONO,fontsize=10,y=0.97)
out=os.path.join(out_dir,"MH370_local_mag.png")
plt.savefig(out,dpi=150,bbox_inches="tight",facecolor=BG);plt.close()
print(f"Plot: {out}")
import subprocess;subprocess.Popen(["start",out],shell=True)
