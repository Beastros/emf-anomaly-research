# AARO Submission

**TO:** aaro.mil (public reporting mechanism)
**SUBJECT:** Independent multi-sensor analysis of documented UAP events — reproducible findings using public government data

---

To the All-domain Anomaly Resolution Office,

I am submitting findings from an independent analysis of documented UAP events using publicly available government sensor archives. The methodology and all findings are fully reproducible.

**Methodology Summary:**

An open-source framework was developed that cross-correlates USGS geomagnetic observatory data, GFZ Potsdam Kp index, NOAA NEXRAD radar archives, and INTERMAGNET global magnetometer data against documented UAP event timestamps. The core innovation is eyewitness-independent velocity estimation via cross-station magnetometer wavefront analysis, combined with automatic solar activity gating via the Kp index.

**Findings Summary:**

Three events with strong multi-sensor convergence, all during confirmed quiet geomagnetic conditions:

**Phoenix Lights, 1997-03-13:**
- Kp 2.0 (quiet)
- TUC-BOU cross-station correlation: 0.9704 at -1 minute lag
- Implied wavefront velocity: >60,000 km/h across 1,013km baseline
- D-field peak: 6.333σ at documented last sighting time
- NEXRAD null returns: 3 stations, scores 0.777-0.928
- 14 multi-sensor convergence events

**USS Nimitz, 2004-11-14:**
- Kp 1.333 (quiet)
- TUC-BOU correlation: 0.978
- Magnetometer spike 1 minute after documented instantaneous relocation event

**O'Hare Airport, 2006-11-07:**
- Kp 0.0 (perfectly quiet)
- FRD-BOU correlation: 0.9796
- Boulder anomaly 1 minute after documented vertical departure

**Additional finding — MH370, 2014-03-07:**
INTERMAGNET data from Canberra (CNB), Kakioka (KAK), and Kanoya (KNY) shows 9 anomalies across all three field axes at zero-minute offset from the MH370 transponder cutoff (17:21 UTC), during Kp 1.0 conditions. This finding was incidental to the UAP analysis and may be relevant to ongoing MH370 investigation.

**Repository for independent verification:**

`https://github.com/emfproj/emf-anomaly-research`

All source code is open. All data fetches from public government APIs at runtime. All findings can be independently reproduced.

`emfproj@proton.me`
