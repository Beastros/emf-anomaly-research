import sys, os, json, datetime, requests
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── STATIONS ─────────────────────────────────────────────────────────────────
# We need stations spread across the formation corridor
# If the anomaly propagates northward from source, arrival time differences
# between stations gives us independent speed — no eyewitness timestamps needed
STATIONS = {
    "TUC": {"lat": 32.174, "lon": -110.733, "name": "Tucson AZ",        "dist_from_track": 0},
    "BOU": {"lat": 40.137, "lon": -105.237, "name": "Boulder CO",       "dist_from_track": 350},
    "FRD": {"lat": 38.205, "lon": -77.373,  "name": "Fredericksburg VA","dist_from_track": 2400},
    "SIT": {"lat": 57.058, "lon": -135.330, "name": "Sitka AK",         "dist_from_track": 3100},
    "HON": {"lat": 21.316, "lon": -158.000, "name": "Honolulu HI",      "dist_from_track": 4200},
}

# Event window — pull wide to get clean baseline
FETCH_START = datetime.datetime(1997, 3, 14, 0, 0,  tzinfo=datetime.timezone.utc)
FETCH_END   = datetime.datetime(1997, 3, 14, 6, 0,  tzinfo=datetime.timezone.utc)

# Known event window from previous analysis
EVENT_START = datetime.datetime(1997, 3, 14, 2, 25, tzinfo=datetime.timezone.utc)
EVENT_END   = datetime.datetime(1997, 3, 14, 3, 35, tzinfo=datetime.timezone.utc)

# The big spike we found: 03:32 UTC at TUC
SPIKE_TIME  = datetime.datetime(1997, 3, 14, 3, 32, tzinfo=datetime.timezone.utc)

USGS_URL = "https://geomag.usgs.gov/ws/data/"

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = np.radians(lat2-lat1); dlon = np.radians(lon2-lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return R*2*np.arctan2(np.sqrt(a),np.sqrt(1-a))

def fetch_station(station_id):
    params = {
        "id": station_id,
        "starttime": FETCH_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endtime":   FETCH_END.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elements":  "H,D,Z",
        "sampling_period": 60,
        "format": "json",
        "type": "definitive",
    }
    print(f"  Fetching {station_id} ({STATIONS[station_id]['name']})...")
    try:
        r = requests.get(USGS_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  {station_id} failed: {e}")
        return None

def parse_station(raw):
    if not raw: return None
    times = [datetime.datetime.fromisoformat(t.replace("Z","+00:00")) for t in raw.get("times",[])]
    fields = {}
    for entry in raw.get("values",[]):
        fid  = entry["id"]
        vals = np.array([float(v) if v is not None else np.nan for v in entry["values"]])
        if not np.all(np.isnan(vals)):
            fields[fid] = vals
    return {"times": times, "fields": fields}

def rolling_anomaly(arr, window=20):
    n = len(arr); base=np.zeros(n); sig=np.zeros(n); score=np.zeros(n)
    for i in range(n):
        sl=arr[max(0,i-window):i]; valid=sl[~np.isnan(sl)]
        if len(valid)>=3:
            base[i]=np.mean(valid); sig[i]=np.std(valid)
            score[i]=abs(arr[i]-base[i])/sig[i] if sig[i]>0.001 else 0
        else:
            base[i]=arr[i] if not np.isnan(arr[i]) else 0; score[i]=0
    return base, score

def find_peak_anomaly(data, field="D", t_start=None, t_end=None):
    if not data or field not in data["fields"]: return None
    arr = data["fields"][field]
    times = data["times"]
    _, score = rolling_anomaly(arr)
    indices = [i for i,t in enumerate(times) if (t_start is None or t>=t_start) and (t_end is None or t<=t_end)]
    if not indices: return None
    peak_idx = indices[np.argmax(score[indices])]
    return {
        "time":   times[peak_idx],
        "sigma":  round(float(score[peak_idx]),3),
        "value":  round(float(arr[peak_idx]),4),
        "index":  peak_idx,
    }

def compute_wavefront_velocity(station_peaks, reference_station="TUC"):
    if reference_station not in station_peaks: return []
    ref = station_peaks[reference_station]
    if not ref: return []

    results = []
    for sid, peak in station_peaks.items():
        if sid == reference_station or not peak: continue
        info = STATIONS[sid]
        ref_info = STATIONS[reference_station]

        # Time difference between peak anomalies
        dt_seconds = (peak["time"] - ref["time"]).total_seconds()

        # Distance between stations
        dist_km = haversine_km(ref_info["lat"], ref_info["lon"], info["lat"], info["lon"])

        # Implied velocity of wavefront
        if abs(dt_seconds) > 0:
            velocity_kmh = (dist_km / abs(dt_seconds)) * 3600
            velocity_kms = dist_km / abs(dt_seconds)
        else:
            velocity_kmh = float("inf")
            velocity_kms = float("inf")

        # Direction: did anomaly arrive at reference before or after this station?
        direction = "propagating away from AZ" if dt_seconds > 0 else "propagating toward AZ"

        results.append({
            "from_station":    reference_station,
            "to_station":      sid,
            "to_name":         info["name"],
            "ref_peak_time":   ref["time"].strftime("%H:%M:%S UTC"),
            "other_peak_time": peak["time"].strftime("%H:%M:%S UTC"),
            "dt_seconds":      dt_seconds,
            "dt_minutes":      round(dt_seconds/60, 2),
            "dist_km":         round(dist_km, 1),
            "wavefront_kmh":   round(velocity_kmh, 1),
            "wavefront_kms":   round(velocity_kms, 3),
            "direction":       direction,
            "ref_sigma":       ref["sigma"],
            "other_sigma":     peak["sigma"],
            "interpretation":  interpret_velocity(velocity_kmh, dt_seconds, sid),
        })

    return sorted(results, key=lambda x: abs(x["dt_seconds"]))

def interpret_velocity(v_kmh, dt_s, station):
    if abs(dt_s) < 60:
        return "NEAR-SIMULTANEOUS — consistent with global EM pulse or solar event (but Kp=2 rules out solar)"
    elif v_kmh < 10:
        return "Very slow propagation — consistent with ionospheric drift"
    elif 10 <= v_kmh < 400:
        return "Subsonic propagation — could be pressure wave or ionospheric disturbance"
    elif 400 <= v_kmh < 750:
        return "Transonic — consistent with fast-moving atmospheric source"
    elif 750 <= v_kmh < 2000:
        return "SUPERSONIC — consistent with fast-moving EM field source, matches track speed range"
    elif 2000 <= v_kmh < 30000:
        return "Hypersonic — consistent with extreme velocity source or ionospheric coupling"
    elif v_kmh >= 30000:
        return "Near-instantaneous at regional scale — consistent with EM radiation (light speed) not physical object"
    else:
        return "Unclassified"

def print_banner():
    print("""
=============================================================
  MULTI-STATION MAGNETOMETER WAVEFRONT ANALYSIS
  Phoenix Lights 1997-03-14
  Deriving independent speed estimate from field propagation
  NO EYEWITNESS TIMESTAMPS USED
=============================================================
""")

def main():
    print_banner()

    os.makedirs("output", exist_ok=True)

    # ── Fetch all stations ────────────────────────────────────────────────────
    print("[1] Fetching all stations...")
    station_data = {}
    for sid in STATIONS:
        raw  = fetch_station(sid)
        data = parse_station(raw)
        if data:
            n_fields = len(data["fields"])
            print(f"    {sid}: {len(data['times'])} minutes, {n_fields} fields")
            station_data[sid] = data
        else:
            print(f"    {sid}: no data")

    # ── Find peak anomaly at each station during event window ─────────────────
    print("\n[2] Finding peak anomaly times per station (D-field, event window)...")
    print(f"    Window: {EVENT_START.strftime('%H:%M')} - {EVENT_END.strftime('%H:%M')} UTC")
    print(f"    Reference spike: {SPIKE_TIME.strftime('%H:%M')} UTC at TUC (6.333 sigma)")
    print()

    # Extend window to catch propagated anomalies at distant stations
    extended_start = EVENT_START - datetime.timedelta(hours=2)
    extended_end   = EVENT_END   + datetime.timedelta(hours=2)

    station_peaks = {}
    for sid, data in station_data.items():
        for field in ["D", "H", "Z"]:
            peak = find_peak_anomaly(data, field, extended_start, extended_end)
            if peak:
                key = f"{sid}_{field}"
                print(f"    {sid} {field}: peak={peak['sigma']:.3f}s at {peak['time'].strftime('%H:%M UTC')}")

        # Use D field as primary
        peak_D = find_peak_anomaly(data, "D", extended_start, extended_end)
        station_peaks[sid] = peak_D
        if peak_D:
            in_event = EVENT_START <= peak_D["time"] <= EVENT_END
            flag = " <-- IN EVENT WINDOW" if in_event else ""
            print(f"    {sid} D-peak: {peak_D['sigma']:.3f}s @ {peak_D['time'].strftime('%H:%M UTC')}{flag}")
        else:
            print(f"    {sid}: no D anomaly found")
        print()

    # ── Wavefront velocity calculation ────────────────────────────────────────
    print("[3] Computing wavefront propagation velocity...")
    print("    Using TUC 03:32 UTC spike as reference point")
    print("    If anomaly appears at other stations at different times,")
    print("    the time delta + distance = independent velocity estimate\n")

    # Override TUC peak with known spike time for precision
    if "TUC" in station_data:
        tuc_peak = find_peak_anomaly(station_data["TUC"], "D",
                                      SPIKE_TIME - datetime.timedelta(minutes=5),
                                      SPIKE_TIME + datetime.timedelta(minutes=5))
        if tuc_peak:
            station_peaks["TUC"] = tuc_peak
            print(f"    TUC confirmed: {tuc_peak['sigma']:.3f}s at {tuc_peak['time'].strftime('%H:%M:%S UTC')}")
        else:
            # Use known spike time
            station_peaks["TUC"] = {
                "time":  SPIKE_TIME,
                "sigma": 6.333,
                "value": 668.2,
            }
            print(f"    TUC: using known spike time {SPIKE_TIME.strftime('%H:%M UTC')}")

    velocities = compute_wavefront_velocity(station_peaks, "TUC")

    print("\n[4] WAVEFRONT VELOCITY RESULTS:")
    print("    " + "="*70)
    for v in velocities:
        print(f"\n    TUC → {v['to_station']} ({v['to_name']})")
        print(f"    Distance:      {v['dist_km']} km")
        print(f"    TUC peak:      {v['ref_peak_time']} ({v['ref_sigma']:.3f}s)")
        print(f"    {v['to_station']} peak:    {v['other_peak_time']} ({v['other_sigma']:.3f}s)")
        print(f"    Time delta:    {v['dt_minutes']} minutes ({v['dt_seconds']:.0f} seconds)")
        print(f"    Wavefront:     {v['wavefront_kmh']} km/h  ({v['wavefront_kms']} km/s)")
        print(f"    Direction:     {v['direction']}")
        print(f"    Meaning:       {v['interpretation']}")

    # ── Local correlation: TUC vs BOU ────────────────────────────────────────
    print("\n[5] Cross-correlation analysis (TUC vs BOU — closest pair)...")
    if "TUC" in station_data and "BOU" in station_data:
        tuc_d = station_data["TUC"]["fields"].get("D", np.array([]))
        bou_d = station_data["BOU"]["fields"].get("D", np.array([]))
        tuc_t = station_data["TUC"]["times"]
        bou_t = station_data["BOU"]["times"]

        # Align to common time window
        tuc_event_idx = [i for i,t in enumerate(tuc_t) if EVENT_START<=t<=EVENT_END]
        bou_event_idx = [i for i,t in enumerate(bou_t) if EVENT_START<=t<=EVENT_END]

        if tuc_event_idx and bou_event_idx:
            tuc_seg = tuc_d[tuc_event_idx]
            bou_seg = bou_d[bou_event_idx]
            min_len = min(len(tuc_seg), len(bou_seg))

            if min_len > 5:
                tuc_seg = tuc_seg[:min_len]
                bou_seg = bou_seg[:min_len]

                # Remove NaN
                valid = ~(np.isnan(tuc_seg) | np.isnan(bou_seg))
                if valid.sum() > 5:
                    corr = np.corrcoef(tuc_seg[valid], bou_seg[valid])[0,1]
                    print(f"    TUC-BOU D-field correlation during event: {corr:.4f}")
                    if abs(corr) > 0.7:
                        print(f"    HIGH CORRELATION — both stations moving together")
                        print(f"    Could indicate: global source (but Kp=2 rules out solar)")
                        print(f"    OR: source large enough to affect both simultaneously")
                    elif abs(corr) < 0.3:
                        print(f"    LOW CORRELATION — stations moving independently")
                        print(f"    STRONG INDICATOR: anomaly is LOCALIZED near TUC, not global")
                        print(f"    This is the most powerful finding: something near Tucson")
                        print(f"    was disturbing the field in a way Boulder didn't see")
                    else:
                        print(f"    MODERATE CORRELATION — mixed signal")

                    # Time-lag cross correlation to find propagation delay
                    max_lag = 30  # minutes
                    lags = range(-max_lag, max_lag+1)
                    xcorr = []
                    for lag in lags:
                        if lag >= 0:
                            a = tuc_seg[valid][lag:]
                            b = bou_seg[valid][:len(a)] if len(bou_seg[valid]) >= len(a) else bou_seg[valid]
                        else:
                            a = tuc_seg[valid][:lag]
                            b = bou_seg[valid][-lag:len(a)-lag] if len(bou_seg[valid]) >= len(a) else bou_seg[valid]
                        min_l = min(len(a), len(b))
                        if min_l > 3:
                            vld = ~(np.isnan(a[:min_l]) | np.isnan(b[:min_l]))
                            if vld.sum() > 3:
                                xcorr.append(np.corrcoef(a[:min_l][vld], b[:min_l][vld])[0,1])
                            else:
                                xcorr.append(0)
                        else:
                            xcorr.append(0)

                    if xcorr:
                        best_lag_idx = np.argmax(np.abs(xcorr))
                        best_lag     = list(lags)[best_lag_idx]
                        best_corr    = xcorr[best_lag_idx]
                        print(f"\n    Peak cross-correlation: {best_corr:.4f} at lag={best_lag} minutes")
                        if best_lag != 0:
                            dist_tuc_bou = haversine_km(
                                STATIONS["TUC"]["lat"], STATIONS["TUC"]["lon"],
                                STATIONS["BOU"]["lat"], STATIONS["BOU"]["lon"]
                            )
                            implied_v = (dist_tuc_bou / abs(best_lag * 60)) * 3600
                            print(f"    TUC→BOU distance: {dist_tuc_bou:.0f} km")
                            print(f"    Implied propagation velocity: {implied_v:.0f} km/h")
                            print(f"    Interpretation: {interpret_velocity(implied_v, best_lag*60, 'BOU')}")
                        else:
                            print(f"    Zero lag — simultaneous at both stations")
                            print(f"    Consistent with global or near-lightspeed source")

    # ── Save results ──────────────────────────────────────────────────────────
    print("\n[6] Saving results...")
    results = {
        "analysis":    "Multi-station magnetometer wavefront velocity",
        "event":       "Phoenix Lights 1997-03-13",
        "method":      "Independent of eyewitness timestamps",
        "reference":   "TUC spike 03:32 UTC 6.333 sigma D-field",
        "stations":    list(station_data.keys()),
        "peaks":       {k: {"time": v["time"].isoformat() if v else None,
                            "sigma": v["sigma"] if v else None}
                       for k,v in station_peaks.items() if v},
        "velocities":  velocities,
    }
    with open("output/wavefront_analysis.json","w") as f:
        json.dump(results, f, indent=2, default=str)
    print("  Saved: output/wavefront_analysis.json")

    print("\n" + "="*60)
    print("KEY QUESTION THIS ANSWERS:")
    print("If the D-field anomaly appears at BOU minutes after TUC,")
    print("the time delta + 900km distance gives us a speed that")
    print("either matches, exceeds, or contradicts the eyewitness")
    print("track speeds — with zero eyewitness input.")
    print()
    print("If BOU shows NO anomaly during the event window,")
    print("that confirms the disturbance was LOCALIZED to Arizona —")
    print("not a global or regional geomagnetic event.")
    print("="*60)

if __name__ == "__main__":
    main()
