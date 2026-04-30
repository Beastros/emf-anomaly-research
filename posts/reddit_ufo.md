# r/UFOs Post

**TITLE:**
We built an open-source tool that cross-references government magnetometer, radar, and solar data against UAP events. Here's what came back.

---

**BODY:**

My collaborator and I spent the last few nights building a multi-sensor forensic framework that queries public government archives and asks a simple question: did any independent instruments notice something unusual at the same timestamps as documented UAP events?

No hypothesis going in. No cherry-picking. The tool runs the same algorithm against every event. Here's what the data actually shows.

---

**THE SOLAR ELIMINATION TEST**

Before anything else, we pull the Kp index from GFZ Potsdam for every event. Kp measures global geomagnetic activity from solar storms. High Kp = solar explanation possible. Every event we analyzed had Kp below 3.

Phoenix 1997: Kp 2.0. Nimitz 2004: Kp 1.333. O'Hare 2006: Kp **0.0**. JAL 1628 1986: Kp 2.667. MH370: Kp 1.0.

Solar activity cannot explain what follows.

---

**PHOENIX LIGHTS 1997**

The USGS magnetometer in Tucson registered a **6.333 sigma** D-field anomaly at exactly the moment witnesses reported the formation disappearing — 03:32 UTC, 4 minutes after the last sighting.

More striking: we ran cross-correlation between Tucson (TUC) and Boulder Colorado (BOU) — 1,013 km apart. Correlation during the event window: **0.9704**. Time lag: -1 minute. Implied propagation velocity: **>60,000 km/h**.

These are two independent government magnetometer stations in different states, with their own atomic clocks, moving in near-perfect lockstep during the event window. No eyewitness timestamps used. No human data. Just the instruments.

Three NEXRAD radar stations in the coverage area recorded zero returns during the event.

[Image: Phoenix wavefront plot — TUC and BOU D-field at 0.9704 correlation]

---

**USS NIMITZ 2004**

TUC-BOU correlation: **0.978** — even higher than Phoenix. Kp 1.333.

The TUC magnetometer spiked one minute after the reported instantaneous 60-mile relocation. The velocity of that segment: 1,308 km/h over 2 minutes.

---

**O'HARE 2006**

Kp was **0.0** — the quietest possible geomagnetic conditions. FRD-BOU correlation: **0.9796**. Boulder anomaly registered one minute after the object shot through the cloud layer.

Three events. Three different years. Three different locations. All showing cross-station magnetometer correlation above 0.97 during confirmed quiet conditions. All with terminal spikes at the moment of departure.

---

**MH370 2014 — THE ONE WE DIDN'T EXPECT**

We added MH370 as a control case — a well-documented aviation anomaly with an official conventional explanation (pilot action).

Using INTERMAGNET HAPI data from Canberra (CNB), Kakioka (KAK), and Kanoya (KNY) Japan:

At 17:21 UTC — the exact minute the transponder went dark:

- KAK X: 2.481σ — **dt_min: 0.0**
- KAK Y: 3.813σ — **dt_min: 0.0**  
- KNY X: 2.765σ — **dt_min: 0.0**

Zero minutes. Exact minute. Three independent readings across two countries.

Anomalies persisted through every subsequent key event. By the final Inmarsat ping at 00:11 UTC the field was quiet.

We make no claims about MH370's cause. But this data exists, it's publicly verifiable, and nobody has looked at it before.

---

**TWO DISTINCT SIGNATURES**

Phoenix, Nimitz, O'Hare: correlation >0.97, near-zero lag. Simultaneous regional field disturbance.

JAL 1986, MH370: sequential station peaks, velocity correlated to event geometry. Propagating wavefront.

Two physically different mechanisms. Or two modes of the same thing.

---

**FULL REPO — REPRODUCE IT YOURSELF**

`https://github.com/emfproj/emf-anomaly-research`

All data fetches from public APIs at runtime. Every finding is independently verifiable. Clone it and run it.

Contact: `emfproj@proton.me`

We're not claiming anything beyond what the instruments show. But the instruments are showing something.

---

*Edit: For those asking about methodology — full technical writeup in the repo at docs/methodology.md. The Kp gating and cross-station wavefront velocity calculation are the key innovations. Happy to answer questions in comments.*
