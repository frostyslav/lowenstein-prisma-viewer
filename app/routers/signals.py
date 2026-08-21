"""API for waveform signal data from .wmedf files."""

import struct
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SignalFile
from app.parsers.edf_parser import get_signal_summary, read_signal_data

router = APIRouter(prefix="/api/signals", tags=["signals"])

SDCARD_PATH = Path("/app/sdcard")

# Default channels to display (most clinically relevant)
DEFAULT_CHANNELS = ["RespFlow", "Pressure", "LeakFlowBreath", "FlowFull"]

# Maximum seconds to return in one request (to avoid huge payloads)
MAX_WINDOW_SECONDS = 600  # 10 minutes


@router.get("/night/{night_id}")
def get_night_signals(night_id: int, db: Session = Depends(get_db)) -> dict:
    """List available signal files for a given night."""
    files = (
        db.query(SignalFile)
        .filter_by(night_id=night_id)
        .order_by(SignalFile.session_index)
        .all()
    )

    if not files:
        raise HTTPException(
            status_code=404,
            detail="No signal files found for this night",
        )

    results = []
    for sf in files:
        file_path = SDCARD_PATH / sf.file_path
        if not file_path.exists():
            continue

        try:
            summary = get_signal_summary(file_path)
            results.append(
                {
                    "id": sf.id,
                    "session_index": sf.session_index,
                    "duration_seconds": summary["duration_seconds"],
                    "channels": summary["channels"],
                },
            )
        except (OSError, ValueError, struct.error):
            results.append(
                {
                    "id": sf.id,
                    "session_index": sf.session_index,
                    "duration_seconds": sf.duration_seconds,
                    "channels": [],
                },
            )

    return {"night_id": night_id, "signal_files": results}


@router.get("/data/{signal_file_id}")
def get_signal_data(
    signal_file_id: int,
    start: int = Query(0, description="Start time in seconds"),
    duration: int = Query(300, description="Duration in seconds (max 600)"),
    channels: str = Query(
        "",
        description="Comma-separated channel labels (empty = defaults)",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Read signal data for a specific time window.

    Returns downsampled data suitable for charting.
    """
    sf = db.query(SignalFile).filter_by(id=signal_file_id).first()
    if not sf:
        raise HTTPException(status_code=404, detail="Signal file not found")

    file_path = SDCARD_PATH / sf.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Signal file not available on disk")

    # Clamp duration
    duration = min(duration, MAX_WINDOW_SECONDS)

    # Parse channel selection
    if channels:
        channel_list = [c.strip() for c in channels.split(",")]
    else:
        channel_list = DEFAULT_CHANNELS

    try:
        data = read_signal_data(
            file_path,
            channel_labels=channel_list,
            start_record=start,
            num_records=duration,
        )
    except (OSError, ValueError, struct.error) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read signal: {e}",
        ) from e

    # Downsample for frontend if too many points
    # Target: ~1000 points per channel for smooth rendering
    max_points = 1500
    downsampled: dict[str, list[float]] = {}
    for label, values in data.items():
        if len(values) > max_points:
            step = len(values) / max_points
            downsampled[label] = [values[int(i * step)] for i in range(max_points)]
        else:
            downsampled[label] = values

    return {
        "start_seconds": start,
        "duration_seconds": duration,
        "channels": {
            label: {
                "values": vals,
                "sample_count": len(vals),
            }
            for label, vals in downsampled.items()
        },
    }
