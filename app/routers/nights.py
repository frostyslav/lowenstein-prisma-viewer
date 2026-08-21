"""API for querying night/session data."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Night, NightStat, SessionEvent

router = APIRouter(prefix="/api/nights", tags=["nights"])


@router.get("")
def list_nights(
    limit: int = 90,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    """List therapy nights, most recent first."""
    nights = (
        db.query(Night)
        .order_by(desc(Night.night_date))
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(Night).count()

    return {
        "total": total,
        "nights": [
            {
                "id": n.id,
                "date": n.night_date.isoformat(),
                "usage_hours": round(n.usage_seconds / 3600, 1)
                if n.usage_seconds
                else None,
                "therapy_hours": round(n.therapy_seconds / 3600, 1)
                if n.therapy_seconds
                else None,
                "ahi": n.ahi,
                "ai_central": n.ai_central,
                "hi_central": n.hi_central,
                "rera_index": n.rera_index,
                "obstructive_apneas": n.obstructive_apneas,
                "central_apneas": n.central_apneas,
                "obstructive_hypopneas": n.obstructive_hypopneas,
                "central_hypopneas": n.central_hypopneas,
                "reras": n.reras,
                "deep_sleep_pct": n.deep_sleep_pct,
                "snore_pct": n.snore_pct,
                "flow_limitation_pct": n.flow_limitation_pct,
                "leak_95": n.leak_95,
                "pressure_median": n.pressure_median,
                "pressure_95": n.pressure_95,
                "pressure_max": n.pressure_max,
                "pressure_min": n.pressure_min,
            }
            for n in nights
        ],
    }


@router.get("/{night_id}")
def get_night_detail(night_id: int, db: Session = Depends(get_db)) -> dict:
    """Get detailed data for a specific night."""
    night = db.query(Night).filter_by(id=night_id).first()
    if not night:
        raise HTTPException(status_code=404, detail="Night not found")

    events = (
        db.query(SessionEvent)
        .filter_by(night_id=night_id)
        .order_by(SessionEvent.start_seconds)
        .all()
    )

    stats = db.query(NightStat).filter_by(night_id=night_id).all()

    return {
        "id": night.id,
        "date": night.night_date.isoformat(),
        "usage_hours": round(night.usage_seconds / 3600, 1)
        if night.usage_seconds
        else None,
        "therapy_hours": round(night.therapy_seconds / 3600, 1)
        if night.therapy_seconds
        else None,
        "ahi": night.ahi,
        "ai_central": night.ai_central,
        "hi_central": night.hi_central,
        "rera_index": night.rera_index,
        "obstructive_apneas": night.obstructive_apneas,
        "central_apneas": night.central_apneas,
        "obstructive_hypopneas": night.obstructive_hypopneas,
        "central_hypopneas": night.central_hypopneas,
        "reras": night.reras,
        "deep_sleep_pct": night.deep_sleep_pct,
        "snore_pct": night.snore_pct,
        "flow_limitation_pct": night.flow_limitation_pct,
        "leak_95": night.leak_95,
        "pressure_median": night.pressure_median,
        "pressure_95": night.pressure_95,
        "pressure_max": night.pressure_max,
        "pressure_min": night.pressure_min,
        "events": [
            {
                "type": e.event_type,
                "start_seconds": e.start_seconds,
                "duration_seconds": e.duration_seconds,
                "strength": e.strength,
                "session_index": e.session_index,
            }
            for e in events
        ],
        "raw_stats": [{"stat_id": s.stat_id, "value": s.value} for s in stats],
    }
