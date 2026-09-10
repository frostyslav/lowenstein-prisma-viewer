"""API for summary therapy metrics."""

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Night

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def get_metrics(db: Session = Depends(get_db)) -> dict:
    """Return summary metrics.

    - nights: total number of therapy nights recorded
    - avg_ahi: average AHI over the most recent 30 nights
    - avg_usage_hours: average usage (hours) over the most recent 30 nights
    """
    total_nights = db.query(Night).count()

    recent = db.query(Night).order_by(desc(Night.night_date)).limit(30).all()

    ahi_values = [n.ahi for n in recent if n.ahi is not None]
    usage_values = [n.usage_seconds for n in recent if n.usage_seconds is not None]

    avg_ahi = round(sum(ahi_values) / len(ahi_values), 2) if ahi_values else None
    avg_usage_hours = (
        round(sum(usage_values) / len(usage_values) / 3600, 1) if usage_values else None
    )

    return {
        "nights": total_nights,
        "avg_ahi": avg_ahi,
        "avg_usage_hours": avg_usage_hours,
    }
