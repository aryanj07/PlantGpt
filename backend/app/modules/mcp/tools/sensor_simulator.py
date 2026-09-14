"""Simulated live-sensor tool (Phase 4 plan). No real plant SCADA/historian
exists to connect to yet, and no free public API for private industrial
telemetry exists either (plan decision, this session) - so this is a
deliberately fake data source, not a stand-in meant to look real.

Safety note: every result is explicitly marked simulated=True, and a query
that doesn't name one of the known metrics gets an honest "no live data
source" response rather than a fabricated number - a plant assistant
returning a fake reading that reads as real is a trust problem, not just a
demo shortcut.
"""

import random
from datetime import UTC, datetime

# (low, high, unit) - plausible ranges for a cement/steel/manufacturing
# plant, not tied to any real equipment.
_METRIC_RANGES: dict[str, tuple[float, float, str]] = {
    "temperature": (280.0, 420.0, "C"),
    "vibration": (1.5, 6.0, "mm/s"),
    "pressure": (0.8, 2.4, "bar"),
}


def simulate_reading(query: str) -> dict:
    q = query.lower()
    metric = next((m for m in _METRIC_RANGES if m in q), None)

    if metric is None:
        return {
            "metric": None,
            "value": None,
            "unit": None,
            "as_of": datetime.now(UTC).isoformat(),
            "simulated": True,
            "note": "No live plant system is connected for this request (demo environment).",
        }

    low, high, unit = _METRIC_RANGES[metric]
    return {
        "metric": metric,
        "value": round(random.uniform(low, high), 1),
        "unit": unit,
        "as_of": datetime.now(UTC).isoformat(),
        "simulated": True,
        "note": None,
    }
