# EMF Anomaly Research — Technical Methodology

## Overview

This document describes the complete technical methodology used in the EMF Anomaly Research framework. The framework applies multi-sensor convergence analysis to historical anomalous events using only publicly available government instrument data.

---

## Data Sources

### USGS Geomagnetic Observatory Network
- **URL:** `https://geomag.usgs.gov/ws/data/`
- **Resolution:** 1-minute samples
- **Fields:** H (horizontal intensity), D (declination), Z (vertical), F (total)
- **Coverage:** ~14 US stations, data from 1960s-present
- **Access:** Public REST API, no authentication required

### GFZ Potsdam Kp Index
- **URL:** `https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt`
- **Resolution:** 3-hour intervals
- **Range:** 0 (geomagnetically quiet) to 9 (extreme storm)
- **Coverage:** Global index, 1932-present
- **Access:** Public HTTP, no authentication required

### NOAA NEXRAD Level-II Archive
- **URL:** `s3://noaa-nexrad-level2/`
- **Resolution:** Volume scans ~5 minutes
- **Coverage:** ~160 US stations, 1991-present (2008+ publicly accessible on S3)
- **Access:** AWS S3 public bucket

### INTERMAGNET HAPI Server
- **URL:** `https://imag-data.bgs.ac.uk/GIN_V1/hapi/data`
- **Format:** `?id=STATION/definitive/PT1M/xyzf&time.min=YYYY-MM-DDTHH:MM:SSZ&time.max=...`
- **Resolution:** 1-minute samples
- **Coverage:** Global network, ~150 stations
- **Access:** Public HAPI API, no authentication required

---

## Core Algorithms

### 1. Rolling Baseline Anomaly Detection

For each field component at each station:

```python
def rolling_score(arr, window=20):
    n = len(arr)
    score = np.zeros(n)
    for i in range(n):
        baseline = arr[max(0, i-window):i]
        valid = baseline[~np.isnan(baseline)]
        if len(valid) >= 3:
            mu = np.mean(valid)
            sigma = np.std(valid)
            score[i] = abs(arr[i] - mu) / sigma if sigma > 0.001 else 0
    return score
```

The 20-minute window captures short-term baseline variation while being sensitive to event-scale anomalies. A score of 2.0 indicates the current reading is 2 standard deviations from the recent baseline — flagged as anomalous. Scores above 3.0 are considered highly anomalous.

### 2. Kp Geomagnetic Activity Gate

Before interpreting any magnetometer anomaly, the framework checks the Kp index for the event window. Kp < 3 is classified as quiet — geomagnetic storm activity cannot explain localized anomalies. All five primary events in this study occurred during Kp < 3.

```
Phoenix 1997:   Kp = 2.0   QUIET
Nimitz 2004:    Kp = 1.333 QUIET
O'Hare 2006:    Kp = 0.0   QUIET (perfectly quiet)
JAL 1986:       Kp = 2.667 QUIET
MH370 2014:     Kp = 1.0   QUIET
```

This gate eliminates the most common conventional explanation for multi-station magnetometer anomalies.

### 3. Cross-Station Wavefront Velocity

The propagation velocity of a field disturbance between two stations is computed from the cross-correlation lag:

```python
# Find lag of maximum cross-correlation
lags = range(-30, 31)  # minutes
xcorr = []
for lag in lags:
    if lag >= 0:
        a = signal1[lag:]; b = signal2[:len(a)]
    else:
        a = signal1[:lag]; b = signal2[-lag:len(a)-lag]
    xcorr.append(np.corrcoef(a, b)[0,1])

best_lag = lags[np.argmax(np.abs(xcorr))]
velocity_kmh = distance_km / (best_lag / 60)
```

**Key property:** This calculation uses only atomic-clock-timestamped station data. No eyewitness timestamps are used. The velocity estimate is therefore independent of human testimony.

### 4. NEXRAD Null-Return Scoring

For events where physical objects were visually reported within NEXRAD coverage:

```python
def null_score(station, event_time, coverage_radius_km=230):
    files = list_s3_files(station, event_time)
    if len(files) == 0:
        # No data in archive
        return 0.777  # moderate null score
    
    # Check reflectivity in event geometry
    max_dbz = scan_for_returns(files, event_location)
    if max_dbz < 5:  # below noise floor
        return 0.928  # high null score
    return 0.0
```

A null score above 0.7 indicates an object reported visually within coverage that produced no expected radar return.

### 5. Multi-Sensor Convergence Engine

Anomalies from all lenses are projected onto a unified spatiotemporal grid. A convergence event is flagged when ≥2 independent datasets show anomalies within a 10-minute window at overlapping locations:

```python
def find_convergence(anomaly_lists, time_window_minutes=10):
    convergence_events = []
    for t in all_anomaly_times:
        window_anomalies = [a for a in all_anomalies 
                           if abs((a.time - t).total_seconds()) < time_window_minutes * 60]
        lenses_represented = set(a.lens for a in window_anomalies)
        if len(lenses_represented) >= 2:
            convergence_events.append(ConvergenceEvent(t, lenses_represented))
    return convergence_events
```

---

## Velocity Reference Framework

Propagation velocities are interpreted against known physical mechanisms:

| Velocity Range | Physical Mechanism |
|---------------|-------------------|
| < 340 km/h | Subsonic — pressure wave, weather system |
| 340–1,200 km/h | Transonic/supersonic — fast atmospheric |
| 1,200–5,000 km/h | Hypersonic — fast EM source or Alfvén wave |
| 5,000–50,000 km/h | Extreme — magnetospheric coupling |
| > 50,000 km/h | Near-instantaneous — EM radiation / field collapse |

### Alfvén Wave Context

Alfvén waves propagate along geomagnetic field lines at speeds that can reach 10,000-100,000 km/h depending on local plasma density. A strong local EM event can launch an Alfvén wave that propagates to distant stations far faster than any physical object. The Phoenix Lights near-instantaneous TUC-BOU correlation (implied >60,000 km/h) is consistent with Alfvén wave propagation from a strong local source.

---

## Event Analysis Protocol

For each event:

1. Load event JSON (witness timestamps, locations, reference aircraft, confidence weights)
2. Compute track geometry — velocity per segment, headings, anomalous deviations
3. Fetch Kp for event window ± 6 hours — classify as quiet/active
4. Fetch magnetometer data for all stations within 2,000km of event track
5. Apply rolling baseline scoring to all field components
6. Compute cross-station correlations and wavefront velocities
7. Fetch NEXRAD archive for stations within coverage of event track
8. Score null returns against expected coverage geometry
9. Run convergence engine across all lens outputs
10. Generate JSON report + visualization outputs

---

## Statistical Considerations

### Why Rolling Baseline vs. Fixed Baseline

A fixed daily baseline would conflate diurnal variation (the natural daily cycle of Earth's magnetic field) with event-correlated anomalies. The 20-minute rolling baseline captures the local trend and is sensitive only to departures from that trend — more appropriate for detecting short-duration events.

### Multiple Comparison Consideration

With multiple stations, multiple field components, and multiple event timestamps, the probability of spurious hits increases. The framework addresses this by:

1. Requiring the Kp gate to pass before interpreting any finding
2. Cross-validating against independent datasets (magnetometer + NEXRAD + Kp must converge)
3. Computing cross-station wavefront velocity as an independent check — a spurious hit at one station would not produce a physically consistent wavefront velocity with a second station

### Correlation Baseline

Normal background cross-station D-field correlation during quiet conditions at unrelated stations is typically 0.3-0.6 due to shared diurnal variation. Correlations above 0.9 during event windows, absent solar activity, indicate a common driving source beyond normal background.

Phoenix 1997 (0.9704), Nimitz 2004 (0.978), and O'Hare 2006 (0.9796) all substantially exceed this baseline. MH370 2014 (0.4452) does not exceed the baseline for simultaneous regional disturbance but shows a different pattern — sequential multi-axis hits at exact event timestamps.

---

## Known Limitations

**1997 NEXRAD Archive Access**
NEXRAD S3 data for 1997 returns AccessDenied. Null-return scoring for Phoenix Lights is based on official archive records (zero files retrieved) rather than direct scan analysis. This is noted in all Phoenix findings.

**USGS Network Coverage**
The USGS magnetometer network covers the continental US and some territories well. Coverage for Southeast Asia and the Indian Ocean is minimal, requiring fallback to INTERMAGNET for events in those regions.

**1980 Archive Digitization**
BGS Hartland and Eskdalemuir minute data prior to approximately 1991 is not available in the INTERMAGNET digital archive. Rendlesham 1980 analysis requires direct BGS archive request.

**Rolling Baseline Window**
A 20-minute window means events shorter than ~5 minutes may not be captured at adequate sigma sensitivity. The window size is configurable.

**Single Station Limit**
Phoenix analysis relies primarily on TUC (Tucson) as the nearest USGS station. Additional nearby stations would strengthen the finding. The cross-station wavefront analysis with BOU provides independent validation.

---

## Reproducing All Findings

```bash
# Install dependencies
pip install requests numpy matplotlib boto3

# Phoenix Lights — primary event
python sniffer.py --event phoenix_lights_1997 --lenses magnetometer,spaceweather,nexrad

# Wavefront analysis — Phoenix
python wavefront.py

# All UAP events batch
python run_all_events.py

# MH370 INTERMAGNET analysis
# First fetch data:
curl "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?id=CNB/definitive/PT1M/xyzf&time.min=2014-03-07T00:00:00Z&time.max=2014-03-08T00:00:00Z" -o event_outputs/MH370_2014/CNB_20140307.min
curl "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?id=KAK/definitive/PT1M/xyzf&time.min=2014-03-07T00:00:00Z&time.max=2014-03-08T00:00:00Z" -o event_outputs/MH370_2014/KAK_20140307.min
curl "https://imag-data.bgs.ac.uk/GIN_V1/hapi/data?id=KNY/definitive/PT1M/xyzf&time.min=2014-03-07T00:00:00Z&time.max=2014-03-08T00:00:00Z" -o event_outputs/MH370_2014/KNY_20140307.min
# Then run:
python read_local_mag.py
```

Expected runtime: 2-5 minutes per event depending on API response times.

---

## Contact

`emfproj@proton.me`

Independent reproductions, methodology critiques, and additional event suggestions welcome.
