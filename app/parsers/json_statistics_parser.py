"""Parse JSON-format .psstat statistics files (newer Prisma firmware).

The .psstat file contains:
- version, date, hash, crc: metadata
- dev: device info (same as .pscfg)
- use: total usage counters
- days: array of daily records

Each day record has:
- 5: unix timestamp (session start)
- 6: therapy time in minutes
- 7: usage time in minutes
- 9: some counter
- 10: pressure histogram (array of 20 bins)
- 15: packed value (possibly bitfield)
- 16-20: event counts (OA, CA, OH, CH, RERA likely)
- 21: another histogram (array of 33 bins)
- 37, 38: additional event counts
- 41, 42, 44: percentages or counts
- 46: some counter
- 47-51: cumulative counters
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime

# Filter out invalid timestamps (before ~2001)
MIN_UNIX_TIMESTAMP = 1_000_000_000
# Skip sessions shorter than 30 minutes
MIN_THERAPY_MINUTES = 30


@dataclass
class JsonDayStats:
    """Parsed stats for a single night from .psstat JSON."""

    night_date: date
    timestamp: int
    therapy_minutes: int
    usage_minutes: int
    # Event counts — field mappings determined by cross-referencing with event files
    field_9: int  # Likely central apneas or similar
    field_16: int
    field_17: int
    field_18: int
    field_19: int
    field_20: int
    field_37: int
    field_38: int
    field_41: int
    field_42: int
    field_44: int
    field_46: int
    pressure_histogram: list[int]  # Field 10
    field_21_histogram: list[int]  # Field 21


def parse_psstat(content: bytes) -> list[JsonDayStats]:
    """Parse .psstat JSON content into daily stats."""
    data = json.loads(content)
    days_raw = data.get("days", [])

    results: list[JsonDayStats] = []

    for entry in days_raw:
        day = entry.get("day", {})

        ts = day.get("5", 0)
        if ts < MIN_UNIX_TIMESTAMP:
            continue

        dt = datetime.fromtimestamp(ts, tz=UTC)
        night_date = dt.date()

        therapy_min = day.get("6", 0)
        usage_min = day.get("7", 0)

        # Skip days with negligible therapy time (< 30 min = not a real session)
        if therapy_min < MIN_THERAPY_MINUTES:
            continue

        results.append(
            JsonDayStats(
                night_date=night_date,
                timestamp=ts,
                therapy_minutes=therapy_min,
                usage_minutes=usage_min,
                field_9=day.get("9", 0),
                field_16=day.get("16", 0),
                field_17=day.get("17", 0),
                field_18=day.get("18", 0),
                field_19=day.get("19", 0),
                field_20=day.get("20", 0),
                field_37=day.get("37", 0),
                field_38=day.get("38", 0),
                field_41=day.get("41", 0),
                field_42=day.get("42", 0),
                field_44=day.get("44", 0),
                field_46=day.get("46", 0),
                pressure_histogram=day.get("10", []),
                field_21_histogram=day.get("21", []),
            ),
        )

    return results


def compute_night_metrics_from_json(stats: JsonDayStats) -> dict:
    """Compute derived metrics from JSON statistics.

    Note: The exact mapping of field numbers to clinical metrics is inferred.
    Based on typical Prisma data patterns:
    - field_16 + field_17: appear to be apnea/hypopnea counts (sums match AHI * hours)
    - field_18, field_19: additional event counts
    - field_38: likely RERA count
    - field_42: likely snore-related
    - field_44: likely flow limitation related
    """
    therapy_seconds = stats.therapy_minutes * 60
    usage_seconds = stats.usage_minutes * 60
    therapy_hours = therapy_seconds / 3600.0

    # Total respiratory event counts
    # Based on patterns: 16=OA, 17=OH, 18=CA, 19=CH, 38=RERA (tentative)
    oa_count = stats.field_16
    oh_count = stats.field_17
    ca_count = stats.field_18
    ch_count = stats.field_19
    rera_count = stats.field_38

    # Compute indices
    ai_central = round(ca_count / therapy_hours) if therapy_hours > 0 else None
    hi_central = round(ch_count / therapy_hours) if therapy_hours > 0 else None
    rera_index = round(rera_count / therapy_hours) if therapy_hours > 0 else None

    total_events = oa_count + ca_count + oh_count + ch_count
    ahi = round(total_events / therapy_hours, 1) if therapy_hours > 0 else None

    # Pressure percentile from histogram (field 10)
    # Assume bins start at some base pressure and step by a fixed amount
    pressure_median = None
    pressure_95 = None
    if stats.pressure_histogram and sum(stats.pressure_histogram) > 0:
        # Bins likely represent pressure in 0.5 cmH2O steps starting around 4-5 cmH2O
        # Need to confirm with cross-reference, using conservative estimate
        pressure_median = _percentile_from_histogram(
            stats.pressure_histogram,
            50,
            start=4.0,
            step=0.5,
        )
        pressure_95 = _percentile_from_histogram(
            stats.pressure_histogram,
            95,
            start=4.0,
            step=0.5,
        )

    return {
        "usage_seconds": usage_seconds,
        "therapy_seconds": therapy_seconds,
        "ahi": ahi,
        "obstructive_apneas": oa_count,
        "central_apneas": ca_count,
        "obstructive_hypopneas": oh_count,
        "central_hypopneas": ch_count,
        "reras": rera_count,
        "ai_central": ai_central,
        "hi_central": hi_central,
        "rera_index": rera_index,
        "pressure_median": pressure_median,
        "pressure_95": pressure_95,
    }


def _percentile_from_histogram(
    bins: list[int],
    percentile: int,
    start: float,
    step: float,
) -> float | None:
    """Compute a percentile from histogram bin data."""
    total = sum(bins)
    if total == 0:
        return None

    target = total * (percentile / 100.0)
    cumulative = 0
    for i, count in enumerate(bins):
        cumulative += count
        if cumulative >= target:
            return start + i * step

    return start + (len(bins) - 1) * step
