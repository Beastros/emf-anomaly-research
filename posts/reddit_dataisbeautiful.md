# r/dataisbeautiful Post

**TITLE:**
[OC] Cross-correlating government magnetometer stations 1,013km apart against the Phoenix Lights 1997 timeline — correlation 0.9704 with no solar activity. Same algorithm on MH370 found zero-minute hits at the transponder cutoff.

---

**BODY:**

Built an open-source multi-sensor forensic framework that queries public government APIs — USGS geomagnetic network, GFZ Potsdam Kp index, NOAA NEXRAD, INTERMAGNET — and cross-references them against documented anomalous events.

**The Phoenix Lights visualization (lead image):**

- Top panel: All 5 stations D-field normalized. TUC (red) and BOU (green) move in near-perfect unison during the event window despite being 1,013km apart.
- Middle panel: TUC vs BOU zoomed to event window. Correlation: **0.9704**. Lag: -1 minute. Implied propagation velocity: >60,000 km/h.
- Bottom: Anomaly sigma scores. TUC alone spikes to 6.333σ at the moment of last sighting.

**What this is:**

Two independent USGS magnetometer stations in different states, with their own atomic clocks, running since the 1960s, showing near-identical D-field behavior during a specific 70-minute window on March 13-14 1997. Kp was 2.0 — geomagnetically quiet. Solar explanation eliminated by independent dataset.

**MH370 finding:**

Same algorithm on INTERMAGNET data (Canberra + Kakioka + Kanoya) for March 7 2014:

At 17:21 UTC — exact transponder cutoff minute:
- Kakioka X: 2.481σ, dt = 0 minutes
- Kakioka Y: 3.813σ, dt = 0 minutes  
- Kanoya X: 2.765σ, dt = 0 minutes

**Tools:** Python, matplotlib, requests, numpy. Data: USGS, GFZ Potsdam, INTERMAGNET HAPI.

**Full repo with all code and methodology:**
`https://github.com/emfproj/emf-anomaly-research`

All findings reproducible by running the scripts. Data fetches live from public APIs.

Happy to answer questions about methodology in comments.
