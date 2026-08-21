"""Parse event_NNNNNN.xml files from .pdat archives."""

from dataclasses import dataclass

import defusedxml.ElementTree as ET

# Map RespEventID to human-readable type names
RESP_EVENT_NAMES: dict[int, str] = {
    101: "OA",  # Obstructive Apnea
    102: "CA",  # Central Apnea
    103: "LA",  # Leakage Apnea
    105: "HA",  # High Pressure Apnea
    106: "MA",  # Movement Apnea
    111: "OH",  # Obstructive Hypopnea
    112: "CH",  # Central Hypopnea
    113: "LH",  # Leakage Hypopnea
    121: "RERA",
    131: "Snore",
    141: "Artifact",
    151: "FL",  # Flow Limitation
    161: "CL",  # Critical Leak
    171: "PB",  # Periodic Breathing
    181: "CSR",  # Cheyne-Stokes
    221: "TB",  # Timed Breath
    231: "SessionDuration",
    241: "SessionEnd",
    262: "PressureChange",
    306: "MaskOff",
    307: "MaskOn",
    330: "LargeLeak",
    1262: "TherapyPressureChange",
}

# Epoch event IDs (2-minute evaluation windows)
EPOCH_EVENT_IDS = {1, 2, 3, 4, 5, 261}

# Individual epoch event ID constants
EPOCH_SEVERE_OBSTRUCTION = 1
EPOCH_MILD_OBSTRUCTION = 2
EPOCH_FLOW_LIMITATION = 3
EPOCH_SNORE = 4
EPOCH_PERIODIC_BREATHING = 5
EPOCH_DEEP_SLEEP = 261

# Session duration marker
SESSION_DURATION_MARKER = 231

# Clinical events we want to store individually
CLINICAL_EVENT_IDS = {
    101,
    102,
    103,
    105,
    106,
    111,
    112,
    113,
    121,
    131,
    151,
    161,
    171,
    181,
}


@dataclass
class RespEvent:
    """Single respiratory event with timing and severity."""

    resp_event_id: int
    event_type: str
    end_time_ds: int  # Deciseconds from session start
    duration_ds: int  # Deciseconds
    pressure: int  # Pa
    strength: int | None

    @property
    def start_seconds(self) -> float:
        """Event start time in seconds from session start."""
        return (self.end_time_ds - self.duration_ds) / 10.0

    @property
    def duration_seconds(self) -> float:
        """Event duration in seconds."""
        return self.duration_ds / 10.0


@dataclass
class EpochSummary:
    """Summarized epoch data from a single event file."""

    severe_obstruction_ds: int = 0  # ID 1
    mild_obstruction_ds: int = 0  # ID 2
    flow_limitation_ds: int = 0  # ID 3
    snore_ds: int = 0  # ID 4
    periodic_breathing_ds: int = 0  # ID 5
    deep_sleep_ds: int = 0  # ID 261


@dataclass
class SessionParseResult:
    """Result of parsing one event file."""

    events: list[RespEvent]
    epochs: EpochSummary
    session_duration_ds: int  # From RespEventID 231


def _accumulate_epoch(epochs: EpochSummary, event_id: int, duration: int) -> None:
    """Add duration to the appropriate epoch counter."""
    if event_id == EPOCH_SEVERE_OBSTRUCTION:
        epochs.severe_obstruction_ds += duration
    elif event_id == EPOCH_MILD_OBSTRUCTION:
        epochs.mild_obstruction_ds += duration
    elif event_id == EPOCH_FLOW_LIMITATION:
        epochs.flow_limitation_ds += duration
    elif event_id == EPOCH_SNORE:
        epochs.snore_ds += duration
    elif event_id == EPOCH_PERIODIC_BREATHING:
        epochs.periodic_breathing_ds += duration
    elif event_id == EPOCH_DEEP_SLEEP:
        epochs.deep_sleep_ds += duration


def parse_event_xml(content: bytes) -> SessionParseResult:
    """Parse a single event_NNNNNN.xml file."""
    root = ET.fromstring(content)

    events: list[RespEvent] = []
    epochs = EpochSummary()
    session_duration_ds = 0

    for elem in root.findall("RespEvent"):
        event_id = int(elem.get("RespEventID", "0"))
        end_time = int(elem.get("EndTime", "0"))
        duration = int(elem.get("Duration", "0"))
        pressure = int(elem.get("Pressure", "0"))
        strength_str = elem.get("Strength")
        strength = int(strength_str) if strength_str is not None else None

        # Accumulate epoch durations
        if event_id in EPOCH_EVENT_IDS:
            _accumulate_epoch(epochs, event_id, duration)
            continue

        # Session duration marker
        if event_id == SESSION_DURATION_MARKER:
            session_duration_ds = duration
            continue

        # Skip session-end and summary flags
        if event_id in (241, 1230, 1231, 1232, 1233, 1234, 1237, 1238):
            continue

        # Store clinical events
        if event_id in CLINICAL_EVENT_IDS:
            event_type = RESP_EVENT_NAMES.get(event_id, f"Unknown_{event_id}")
            events.append(
                RespEvent(
                    resp_event_id=event_id,
                    event_type=event_type,
                    end_time_ds=end_time,
                    duration_ds=duration,
                    pressure=pressure,
                    strength=strength,
                ),
            )

    return SessionParseResult(
        events=events,
        epochs=epochs,
        session_duration_ds=session_duration_ds,
    )
