# EMF Anomaly Research — UAP Sniffer

A multi-sensor anomaly detection framework that cross-correlates independent public government sensor archives against dates and locations of documented anomalous aerial events. Built on the same rolling-baseline sigma architecture as the GPS Tsunami Detection project.

**Independent research project.** All data sourced from free public APIs. All results reproducible from source code.

📡 **Live Report**: [beastros.github.io/emf-anomaly-research](https://beastros.github.io/emf-anomaly-research/)

---

## What This Does

Each event is treated as a multi-instrument measurement problem. For a given date and location, the framework retrieves data from every available public sensor archive, scores each stream independently against a rolling baseline, and asks: did independent instruments — with no connection to each other — flag the same window?

When two magnetometer stations 1,013 km apart on separate data acquisition systems produce a Pearson correlation of 0.9704 during a 90-minute event window, under quiet solar conditions, while six other stations across the continent show nothing — that convergence is the finding.

The framework does not interpret what caused the signal. It reports what the instruments recorded, eliminates known confounders, and presents the result.

---

## Sensor Stack

| Sensor | Source | Role |
|---|---|---|
| USGS fluxgate magnetometers | geomag.usgs.gov | Primary anomaly detector — D/H/Z components, 1-min resolution |
| GFZ Potsdam Kp index | kp.gfz-potsdam.de | Solar activity gate — eliminates geomagnetic storm explanations |
| INTERMAGNET global network | imag-data.bgs.ac.uk/GIN_V1/hapi | Spatial extent mapping — additional stations continent-wide |
| IONEX global TEC maps | NASA CDDIS / JPL JPLG | Ionospheric check — rules out electron density disturbance |
| NOAA NEXRAD S3 | s3://noaa-nexrad-level2/ | Radar (2008+ only — pre-2008 archive not publicly released) |

---

## Core Algorithm

```
ACS(t) = Σ [ wₙ × σₙ(t) × G(Kp) × N(s,t) ]

σₙ(t)  = |x - mean(20-min window)| / std(20-min window)
G(Kp)  = 1.0 if Kp < 3.0   ←  solar ELIMINATED
          0.2 if Kp ≥ 3.0   ←  solar POSSIBLE
Weights: magnetometer 1.0 | NEXRAD 0.8 | Kp 0.6
Flag threshold: σ > 2.0
```

Cross-station correlation uses Pearson r with time-lag sweep. Propagation velocity is estimated as station separation / lag at peak r. Spatial extent is assessed by pulling additional INTERMAGNET stations and checking each against the 2.0σ threshold during the event window.

---

## Events Analyzed

| Event | Date | Kp | Solar | Stations | r | Peak σ | Result |
|---|---|---|---|---|---|---|---|
| Phoenix Lights | 1997-03-13 | 2.0 | QUIET | TUC, BOU | 0.9704 | 6.33 | HIGH ANOMALY |
| USS Nimitz | 2004-11-14 | 1.333 | QUIET | TUC, BOU | 0.978 | — | HIGH ANOMALY |
| O'Hare Airport | 2006-11-07 | 0.0 | QUIET | FRD, BOU | 0.9796 | — | HIGH ANOMALY |
| JAL Flight 1628 | 1986-11-17 | 2.667 | QUIET | SIT, BOU | — | — | HIGH ANOMALY |
| Stephenville TX | 2008-01-08 | 3.333 | ACTIVE | ABN, BOU | 0.9711 | — | INCONCLUSIVE |
| MH370 | 2014-03-07 | 1.0 | QUIET | CNB, KAK, KNY | 0.4452 | 4.42 | ANOMALY (control)* |

\* MH370 was added expecting a null result. It was not null.

---

## Primary Case: Phoenix Lights — 1997-03-13

### Magnetometer Correlation

Two USGS fluxgate magnetometers — Tucson AZ (TUC) and Boulder CO (BOU) — produced the following during the Phoenix Lights event window:

| Metric | Value |
|---|---|
| Pearson r, D-component | **0.9704** |
| Lag at peak correlation | −1 min (BOU leads TUC) |
| Station separation | 1,013 km |
| Implied propagation velocity | >60,787 km/h at 1-min resolution |
| Peak D-field deviation (TUC) | **6.333σ** at 03:32 UTC |
| Lag from final reported sighting | +4 min |
| Kp index | **2.0 — solar ELIMINATED** |
| Total flagged anomalies | 201 (178 magnetometer, 14 convergence events) |

These are independent instruments operated by separate USGS field offices with independent timing systems. They have no data connection to each other.

### Spatial Extent Analysis

Following the TUC-BOU result, data was pulled from six additional INTERMAGNET stations spanning the continent. The question: was the anomaly regional or confined to the AZ-CO corridor?

| Station | Location | Distance | Window σ | Result |
|---|---|---|---|---|
| TUC | Tucson AZ | 0 km (in corridor) | **6.333** | IN EVENT |
| BOU | Boulder CO | 0 km (in corridor) | **4.100** | IN EVENT |
| SIT | Sitka AK | ~2,800 km NW | 1.554 | quiet |
| CMO | College AK | ~3,500 km NW | 1.649 | quiet |
| FRD | Fredericksburg VA | ~2,500 km E | 1.195 | quiet |
| SJG | San Juan PR | ~4,000 km SE | 1.010 | quiet |
| HON | Honolulu HI | ~4,100 km W | 0.889 | quiet |
| BRW | Barrow AK | ~4,200 km NW | 1.797 | quiet |

**All six stations outside the corridor were below threshold.** The anomaly did not propagate to Alaska, Hawaii, Virginia, Puerto Rico, or the Arctic.

### Ionospheric TEC Check

IONEX global TEC maps (JPLG, 2-hour resolution) were pulled for the four events with archive coverage (post-1998). TEC was interpolated to each event location and scored against daily baseline.

| Event | Max window σ | Result |
|---|---|---|
| USS Nimitz (2004) | 1.617 | no anomaly |
| O'Hare Airport (2006) | 1.587 | no anomaly |
| MH370 (2014) | 1.882 | no anomaly |
| Stephenville (2008) | 1.923 | no anomaly |

No TEC anomaly exceeded 2.0σ during any event window. The ionosphere was undisturbed.

---

## Key Findings

**1. The Phoenix Lights magnetometer correlation is statistically unlikely under known atmospheric or solar mechanisms.**
TUC-BOU r = 0.9704 at 1,013 km separation, −1 minute lag, Kp = 2.0. A correlation this high between independent instruments this far apart during quiet solar conditions does not have a routine explanation. The same pattern appeared independently on the Nimitz date (r = 0.978) and the O'Hare date (r = 0.9796).

**2. The anomaly was spatially localized to the Arizona-Colorado corridor.**
Six magnetometer stations from Alaska to Puerto Rico were flat during the event window. This rules out a global geomagnetic storm, a continental-scale solar effect, and any mechanism expected to affect instruments broadly across North America. Whatever produced the TUC-BOU signal was confined to the region where the event was reported.

**3. The ionosphere was undisturbed across all four testable events.**
TEC stayed below 2.0σ at every event location and time window tested. This rules out broad ionospheric disturbance as the signal source and distinguishes the signature from space weather phenomena, which would perturb electron density.

**4. The signal reproduced across three independent events spanning nine years.**
Phoenix (1997), Nimitz (2004), and O'Hare (2006) all produced r > 0.97 at near-zero lag between independent station pairs, under quiet solar conditions, on unrelated dates. The consistency of the pattern across different locations, different station pairs, and a nine-year span is the strongest argument that it reflects a real repeating phenomenon rather than a coincidental measurement artifact.

**5. Two distinct signal types exist in the dataset.**
Type 1 (Phoenix, Nimitz, O'Hare): simultaneous regional field response, r > 0.97, near-zero lag, spatially bounded.
Type 2 (JAL 1628, MH370): propagating wavefront, sequential station peaks, velocity tracks event geometry. These are physically distinct signatures.

**6. What the data does not establish.**
The magnetometer records a perturbation in Earth's ambient magnetic field. It does not identify the source. These findings establish that something produced a spatially localized, geomagnetically quiet, ionospherically invisible, simultaneous field perturbation across 1,013 km on three separate occasions. The cause is not identified.

---

## Two Signal Types

| Type | Pattern | Events | r | Lag |
|---|---|---|---|---|
| **Type 1 — Simultaneous regional** | Independent stations respond together. Near-zero lag. High r. Spatially confined to corridor. | Phoenix, Nimitz, O'Hare | >0.97 | 0–1 min |
| **Type 2 — Propagating wavefront** | Sequential station peaks. Velocity consistent with event geometry. Lower r. | JAL 1628, MH370 | 0.44–var | minutes to hours |

---

## Repository Structure

```
sniffer.py                    # Main CLI — run analysis for any event
run_all_events.py             # Batch runner for all configured events
wavefront.py                  # Cross-station wavefront velocity estimator
read_local_mag.py             # INTERMAGNET HAPI CSV reader

core/
  anomaly.py                  # ACS algorithm + rolling baseline scorer
  report.py                   # Result formatter
  track.py                    # Witness track segment speed estimator

lenses/
  magnetometer.py             # USGS geomag API + INTERMAGNET HAPI
  nexrad.py                   # NOAA NEXRAD S3 (2008+ only)
  spaceweather.py             # GFZ Potsdam Kp index

events/
  phoenix_lights_1997.json    # Event config — coordinates, window, stations
  nimitz_2004.json
  ohare_2006.json
  jal_1628_1986.json
  mh370_2014.json

results/
  phoenix_1997/               # Output plots and JSON for each event
  nimitz_2004/
  ohare_2006/
  jal_1986/
  mh370_2014/

docs/
  index.html                  # Public report — hosted on GitHub Pages

# Analysis scripts (session work)
phoenix_tec.py                # IONEX TEC downloader + scorer
phoenix_spatial.py            # Spatial extent — 8-station continental check
phoenix_corroborate.py        # Multi-dataset cross-reference
fetch_ionex_data.py           # TEC downloader for post-1998 events
```

---

## Data Sources

| Source | Data | URL |
|---|---|---|
| USGS Geomagnetism | Magnetometer D/H/Z, 1-min | geomag.usgs.gov/ws/data/ |
| INTERMAGNET / BGS | Global magnetometer network, 1-min | imag-data.bgs.ac.uk/GIN_V1/hapi |
| GFZ Potsdam | Kp index since 1932 | kp.gfz-potsdam.de |
| NASA CDDIS | IONEX global TEC maps (1998+) | cddis.nasa.gov/archive/gnss/products/ionex/ |
| NOAA NEXRAD | Weather radar archive (2008+) | s3://noaa-nexrad-level2/ |

CDDIS access requires a free NASA Earthdata account. All other sources are open with no authentication.

---

## Requirements

```
python >= 3.10
numpy scipy matplotlib requests unlzw3
```

```
pip install numpy scipy matplotlib requests unlzw3
```

---

## Pending Work

- [ ] Stephenville 2008 — NEXRAD radar cross-reference (archive accessible)
- [ ] Belgian UAP Wave 1989–90 — magnetometer analysis not yet started
- [ ] Rendlesham Forest 1980 — BGS physical records, contact initiated
- [ ] MH370 — add as formal event in run_all_events.py
- [ ] Superconducting gravimeter — GGP Tucson 1997, contact requested
- [ ] Ionosonde data (pre-1998) — NOAA NGDC for Phoenix 1997 window
- [ ] Galileo Project submission
- [ ] AARO submission

---

## Status

- [x] Core magnetometer cross-correlation validated (Phoenix, Nimitz, O'Hare)
- [x] Solar gate (GFZ Kp) — eliminates solar wind explanations
- [x] Spatial extent analysis — 8-station continental check (6 quiet, 2 in event)
- [x] Ionospheric TEC check — IONEX JPLG, 4 events, no anomaly detected
- [x] Two signal type taxonomy (simultaneous regional vs propagating wavefront)
- [x] MH370 control case — unexpected result, preliminary
- [x] Public report with full methodology and limitations
- [ ] Independent replication
- [ ] Peer review
- [ ] Pre-1998 ionosonde data for Phoenix 1997

---

*All results reproducible from publicly available data. This is an independent research project. Findings are preliminary pending independent replication.*
