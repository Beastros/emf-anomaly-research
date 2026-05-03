"""
core/lens_tiers.py
==================
Which lenses are backed by external measurements vs model/prior placeholders.
"""

from __future__ import annotations

from typing import Callable, Dict, List

# Archive/API-backed (or will be empty if no credentials — still "instrument" intent)
INSTRUMENT_LENSES = frozenset(
    {
        "magnetometer",
        "spaceweather",
        "omni",
        "asos",
        "nexrad",
        "infrasound",
        "lightning",
        "adsb",
    }
)

MODEL_PRIOR_LENSES = frozenset(
    {
        "powergrid",
        "ionosphere",
    }
)


def is_instrument_lens(name: str) -> bool:
    return name in INSTRUMENT_LENSES


def collapse_magnetometer_family(lens_name: str, _anom: Dict) -> str:
    """Treat all XYZ components as one independent family."""
    if lens_name == "magnetometer":
        return "magnetometer"
    return lens_name


def default_family(lens_name: str, _anom: Dict) -> str:
    return lens_name


def instrument_anomalies_for_convergence(lens_name: str, anomalies: List[dict]) -> List[dict]:
    """
    Rows excluded from *instrument-only* coincidence (still kept in full timeline).

    Nexrad `archive_ok` ticks are informational (archive listed); they are not treated
    as independent measurement anomalies for strict bundles.
    """
    if lens_name == "nexrad":
        return [a for a in anomalies if not a.get("archive_ok")]
    return list(anomalies)
