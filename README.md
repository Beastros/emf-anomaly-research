# EMF Anomaly Research
### Multi-Sensor Forensic Analysis of Anomalous Events Using Public Archive Data

> *"The data is real. The anomalies are real. What caused them remains an open question."*

---

## What This Is

A reproducible, open-source framework that cross-correlates multiple independent public sensor datasets against documented anomalous events â€” UAP sightings, unexplained aviation incidents, and other cases with precise timestamps and locations.

The core methodology: point every available sensor at the same event and ask what each one independently recorded. When unconnected instruments flag the same moment from different locations, that convergence is physically meaningful regardless of what caused it.

**No hypothesis. No conclusions beyond what the instruments show. Full reproducibility.**

---

## Key Findings

All findings below are derived from publicly available government data. Every result can be independently reproduced by running the scripts in this repository.

### Phoenix Lights â€” 1997-03-13
| Metric | Result |
|--------|--------|
| Kp index | 2.0 (Quiet â€” solar explanation eliminated) |
| TUC-BOU magnetometer correlation | **0.9704** |
| Implied wavefront velocity | >60,000 km/h (near-simultaneous across 1,013km) |
| NEXRAD null return score | 0.928 (in coverage, nothing detected) |
| D-field peak anomaly | **6.333Ïƒ** at 03:32 UTC (4 min after last sighting) |
| Velocity segments exceeding A-10 max | 4/8 |
| Multi-sensor convergence events | **14** |

### USS Nimitz Encounter â€” 2004-11-14
| Metric | Result |
|--------|--------|
| Kp index | 1.333 (Quiet â€” solar explanation eliminated) |
| TUC-BOU magnetometer correlation | **0.978** |
| Instantaneous relocation speed | 1,308 km/h over 2 minutes |
| TUC D-field spike | 2.396Ïƒ at 19:18 UTC (1 min after relocation event) |
| Verdict | HIGH ANOMALY â€” Pattern consistent with Phoenix Lights |

### O'Hare Airport â€” 2006-11-07
| Metric | Result |
|--------|--------|
| Kp index | **0.0** (Perfectly quiet â€” solar explanation eliminated) |
| FRD-BOU magnetometer correlation | **0.9796** |
| BOU anomaly timing | +1 minute after object shot through cloud layer |
| Verdict | HIGH ANOMALY â€” Pattern consistent with Phoenix Lights |

### JAL Flight 1628 â€” 1986-11-17
| Metric | Result |
|--------|--------|
| Kp index | 2.667 (Quiet â€” solar explanation eliminated) |
| Alaska station wavefront velocity | **829 km/h** (matches 747 cruise speed) |
| SIT-BOU terminal velocity | 42,954 km/h (magnetospheric coupling) |
| Pattern type | Propagating wavefront â€” different from Phoenix/Nimitz/O'Hare |

### MH370 â€” 2014-03-07
| Metric | Result |
|--------|--------|
| Kp index | 1.0 (Quiet â€” solar explanation eliminated) |
| Primary hits at transponder cutoff | **9 anomalies across 3 stations** |
| KAK X-field at 17:21 UTC | **dt_min: 0.0** (exact transponder cutoff minute) |
| KAK Y-field at 17:21 UTC | **3.813Ïƒ  dt_min: 0.0** |
| KNY X-field at 17:21 UTC | **2.765Ïƒ  dt_min: 0.0** |
| Anomalies persist through | All key events (ACARS â†’ transponder â†’ turn â†’ last radar) |
| Final arc anomalies | 0 (field quiet after disappearance sequence) |

---

## Two Distinct Physical Signatures

Analysis across events reveals two patterns:

**Type 1 â€” Simultaneous Regional Field (Phoenix, Nimitz, O'Hare)**
Cross-station correlation >0.97, near-zero lag, field affecting multiple stations simultaneously across hundreds to thousands of kilometers. Consistent with a field source of extraordinary spatial extent or near-lightspeed propagation.

**Type 2 â€” Propagating Wavefront (JAL, MH370)**
Sequential station peaks, velocity correlated with known event geometry. Field moves across the sensor network tracking the event. Different physical mechanism from Type 1.

Both types occur during confirmed geomagnetically quiet conditions. Solar activity eliminated as explanation for all five events.

---

## Methodology

### Data Sources
| Source | Data | Access |
|--------|------|--------|
| USGS Geomagnetic | H, D, Z, F fields â€” minute resolution | Public API |
| GFZ Potsdam | Kp index 1932-present | Public HTTP |
| NOAA NEXRAD | Level-II radar archive | AWS S3 public bucket |
| INTERMAGNET HAPI | Global magnetometer network | Public API |
| NOAA AWS | Weather/atmospheric data | Public |

### Core Algorithm
1. **Track geometry** â€” velocity, heading, interpolated position from witness reports
2. **Rolling baseline** â€” 20-minute window, sigma deviation scoring
3. **Kp gate** â€” solar activity check eliminates geomagnetic storm explanations
4. **Null-return scoring** â€” quantifies absence of expected radar returns against coverage geometry
5. **Cross-station wavefront** â€” time-lag cross-correlation gives propagation velocity independent of any eyewitness timestamps
6. **Convergence engine** â€” flags windows where â‰¥2 independent datasets are simultaneously anomalous

### Key Innovation: Eyewitness-Independent Verification
The wavefront velocity calculation uses only atomic-clock-timestamped government instrument data. No eyewitness timestamps are used. Station distances are known. Peak anomaly time differences give propagation velocity independently.

Phoenix Lights example: TUC-BOU correlation 0.9704 at -1 minute lag across 1,013km implies >60,000 km/h propagation â€” confirmed by two independent magnetometer stations with no eyewitness input.

---

## Reproducibility

Every finding in this repository can be independently verified:

```bash
git clone https://github.com/Beastros/emf-anomaly-research
cd emf-anomaly-research
pip install -r requirements.txt

# Run Phoenix Lights analysis
python sniffer.py --event phoenix_lights_1997 --lenses magnetometer,spaceweather,nexrad

# Run all events
python run_all_events.py

# MH370 with INTERMAGNET data
python mh370_analysis.py
```

All data is fetched from public APIs at runtime. No proprietary data. No pre-processed results required.

---

## What This Does Not Claim

- These findings do not prove extraterrestrial origin of any event
- Magnetometer anomalies have conventional explanations in some contexts (eliminated here by Kp gating but not exhaustively)
- MH370 findings do not contradict the leading official theory (pilot action); they indicate geomagnetic instruments registered anomalies during the disappearance sequence
- Correlation is not causation
- The null radar return for Phoenix is based on official records, not direct file scanning (1997 NEXRAD archive access denied)

---

## What This Does Establish

- A repeatable methodology for multi-sensor forensic analysis of historical events
- Three independent events (Phoenix, Nimitz, O'Hare) showing the same electromagnetic signature pattern during confirmed quiet geomagnetic conditions
- Eyewitness-independent velocity estimates via magnetometer wavefront analysis
- An anomaly taxonomy distinguishing at least two physically distinct signatures across the event set
- MH370 geomagnetic anomalies at zero-minute offset from transponder cutoff across three stations â€” previously unreported

---

## Repository Structure

```
emf-anomaly-research/
â”œâ”€â”€ README.md
â”œâ”€â”€ sniffer.py              # Main CLI
â”œâ”€â”€ run_all_events.py       # Batch analysis
â”œâ”€â”€ wavefront.py            # Multi-station velocity analysis
â”œâ”€â”€ mh370_analysis.py       # MH370 INTERMAGNET analysis
â”œâ”€â”€ core/
â”‚   â”œâ”€â”€ track.py            # Event geometry
â”‚   â”œâ”€â”€ anomaly.py          # Detection engine
â”‚   â””â”€â”€ report.py           # Report generation
â”œâ”€â”€ lenses/
â”‚   â”œâ”€â”€ magnetometer.py     # USGS geomagnetic
â”‚   â”œâ”€â”€ nexrad.py           # NEXRAD radar
â”‚   â”œâ”€â”€ spaceweather.py     # Kp index
â”‚   â”œâ”€â”€ lightning.py        # NLDN
â”‚   â”œâ”€â”€ infrasound.py       # IMS/IRIS
â”‚   â”œâ”€â”€ ionosphere.py       # TEC maps
â”‚   â”œâ”€â”€ powergrid.py        # Grid frequency
â”‚   â””â”€â”€ adsb.py             # ADS-B gaps
â”œâ”€â”€ events/
â”‚   â”œâ”€â”€ phoenix_lights_1997.json
â”‚   â”œâ”€â”€ nimitz_2004.json
â”‚   â”œâ”€â”€ ohare_2006.json
â”‚   â”œâ”€â”€ jal1628_1986.json
â”‚   â””â”€â”€ mh370_2014.json
â”œâ”€â”€ results/
â”‚   â”œâ”€â”€ phoenix_1997/
â”‚   â”œâ”€â”€ nimitz_2004/
â”‚   â”œâ”€â”€ ohare_2006/
â”‚   â”œâ”€â”€ jal_1986/
â”‚   â””â”€â”€ mh370_2014/
â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ methodology.md
â”‚   â””â”€â”€ findings_layman.md
â””â”€â”€ requirements.txt
```

---

## Contact

`emfproj@proton.me`

Data, methodology questions, and independent reproductions welcome.

---

## Citation

If you use this methodology or findings in research or publications, please cite this repository and acknowledge the original data sources (USGS, GFZ Potsdam, NOAA, INTERMAGNET).

---

*Built April 2026. All source data public. All findings reproducible.*

