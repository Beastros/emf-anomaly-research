# Email — Galileo Project

**TO:** https://projects.iq.harvard.edu/galileo/contact
**SUBJECT:** Open-source multi-sensor historical UAP analysis framework — reproducible findings across 5 events

---

Dear Galileo Project Team,

I've developed an open-source framework that applies multi-sensor convergence analysis to historical anomalous events using publicly archived government data. Given your project's focus on scientific instrumentation and reproducible methodology, I thought this work might be of interest.

**What it does:**

The framework queries USGS geomagnetic observatories, GFZ Potsdam Kp index, NOAA NEXRAD, and INTERMAGNET simultaneously against documented event timestamps and applies cross-station wavefront velocity analysis, rolling baseline anomaly detection, and solar activity gating to produce reproducible findings independent of eyewitness data.

**Key findings:**

Phoenix Lights (1997), USS Nimitz (2004), and O'Hare Airport (2006) all show cross-station magnetometer correlations above 0.97 during confirmed quiet geomagnetic conditions (Kp < 2), with terminal anomalies at the documented departure timestamps. The wavefront analysis produces velocity estimates using only atomic-clock-timestamped instrument data — no eyewitness timestamps used.

An unexpected result emerged from MH370 (2014): INTERMAGNET stations at Canberra, Kakioka, and Kanoya show multi-axis anomalies at zero-minute offset from the transponder cutoff (17:21 UTC), during Kp 1.0 conditions. This appears to be previously unreported.

Two physically distinct signatures have been identified across events — simultaneous regional field disturbance (Phoenix/Nimitz/O'Hare) and propagating wavefront (JAL 1628/MH370) — suggesting the methodology may be capable of anomaly taxonomy, not just detection.

**Repository:**

`https://github.com/emfproj/emf-anomaly-research`

All code is open source. All data fetches from public APIs at runtime. Every finding is independently reproducible. Full methodology documentation is in the repository.

I recognize this work would benefit from rigorous peer review and I'd welcome any critique of the methodology. If this is relevant to the Galileo Project's historical analysis efforts or useful as a validation dataset for your forward-looking sensor work, I'm happy to discuss further.

`emfproj@proton.me`
