"""Parse statistics_year.bin (actually XML despite the extension)."""

from dataclasses import dataclass, field
from datetime import date

import defusedxml.ElementTree as ET


@dataclass
class DayStat:
    """Single statistic entry for a night."""

    stat_id: int
    value: str  # String to support CSV histogram data


@dataclass
class DayRecord:
    """Per-night statistics record with therapy mode and stats."""

    night_date: date
    therapy_mode: int
    # Timestamp pairs: "start-duration,start-duration,..."
    time_segments: str
    stats: list[DayStat] = field(default_factory=list)


def parse_statistics_xml(content: bytes) -> list[DayRecord]:
    """Parse statistics_year.bin XML content."""
    # Handle potential BOM or whitespace
    text = content.decode("utf-8", errors="replace").strip()
    root = ET.fromstring(text)

    days: list[DayRecord] = []

    for day_elem in root.findall("day"):
        date_str = day_elem.get("d", "")
        if not date_str:
            continue

        try:
            night_date = date.fromisoformat(date_str)
        except ValueError:
            continue

        for rec_elem in day_elem.findall("rec"):
            therapy_mode = int(rec_elem.get("m", "0"))
            time_segments = rec_elem.get("t", "")

            stats: list[DayStat] = []
            for s_elem in rec_elem.findall("s"):
                stat_id = int(s_elem.get("i", "0"))
                value = s_elem.get("v", "0")
                stats.append(DayStat(stat_id=stat_id, value=value))

            days.append(
                DayRecord(
                    night_date=night_date,
                    therapy_mode=therapy_mode,
                    time_segments=time_segments,
                    stats=stats,
                ),
            )

    return days


def compute_night_metrics(
    stats: list[DayStat],
) -> dict[str, float | int | None]:
    """Compute derived metrics from raw stat values."""
    stat_map: dict[int, str] = {s.stat_id: s.value for s in stats}

    # Get therapy time in seconds (stat 113)
    therapy_seconds = int(stat_map.get(113, "0"))
    usage_seconds = int(stat_map.get(111, "0"))
    therapy_hours = therapy_seconds / 3600.0 if therapy_seconds > 0 else 0.0

    # Event counts
    ca_count = int(stat_map.get(100, "0"))  # Central Apnea
    oa_count = int(stat_map.get(101, "0"))  # Obstructive Apnea
    rera_count = int(stat_map.get(106, "0"))  # RERA
    ch_count = int(stat_map.get(107, "0"))  # Central Hypopnea
    oh_count = int(stat_map.get(108, "0"))  # Obstructive Hypopnea

    # Pressure stats
    pressure_max = int(stat_map.get(308, "0"))
    pressure_min = int(stat_map.get(309, "0"))

    # Compute indices
    ai_central = round(ca_count / therapy_hours) if therapy_hours > 0 else None
    hi_central = round(ch_count / therapy_hours) if therapy_hours > 0 else None
    rera_index = round(rera_count / therapy_hours) if therapy_hours > 0 else None

    # Compute pressure percentiles from histogram (stat 1005)
    pressure_median = None
    pressure_95 = None
    hist_data = stat_map.get(1005, "")
    if hist_data and "," in hist_data:
        pressure_median = _percentile_from_histogram(hist_data, 50, start=4.0, step=0.5)
        pressure_95 = _percentile_from_histogram(hist_data, 95, start=4.0, step=0.5)

    # Leak 95th percentile from histogram (stat 1016)
    leak_95 = None
    leak_hist = stat_map.get(1016, "")
    if leak_hist and "," in leak_hist:
        leak_95 = _percentile_from_histogram(leak_hist, 95, start=0.0, step=2.5)

    return {
        "usage_seconds": usage_seconds,
        "therapy_seconds": therapy_seconds,
        "obstructive_apneas": oa_count,
        "central_apneas": ca_count,
        "obstructive_hypopneas": oh_count,
        "central_hypopneas": ch_count,
        "reras": rera_count,
        "ai_central": ai_central,
        "hi_central": hi_central,
        "rera_index": rera_index,
        "pressure_max": pressure_max / 100.0 if pressure_max else None,  # Pa -> cmH2O
        "pressure_min": pressure_min / 100.0 if pressure_min else None,
        "pressure_median": pressure_median,
        "pressure_95": pressure_95,
        "leak_95": leak_95,
    }


def _percentile_from_histogram(
    csv_value: str,
    percentile: int,
    start: float,
    step: float,
) -> float | None:
    """Compute a percentile from histogram bin data."""
    try:
        bins = [int(x) for x in csv_value.split(",")]
    except ValueError:
        return None

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
