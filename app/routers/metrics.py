"""Prometheus-compatible metrics endpoint (backed by prometheus-client)."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    generate_latest,
)
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Night

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> Response:
    """Expose therapy metrics in Prometheus text exposition format.

    A fresh registry is built on each scrape so the gauges reflect the
    current database state rather than accumulating across requests.

    Metrics:
    - cpap_nights_total: total number of therapy nights recorded
    - cpap_ahi_avg_last_30: average AHI over the most recent 30 nights
    - cpap_usage_hours_avg_last_30: average usage (hours) over the last 30 nights
    """
    total_nights = db.query(Night).count()

    recent = db.query(Night).order_by(desc(Night.night_date)).limit(30).all()

    ahi_values = [n.ahi for n in recent if n.ahi is not None]
    usage_values = [n.usage_seconds for n in recent if n.usage_seconds is not None]

    avg_ahi = sum(ahi_values) / len(ahi_values) if ahi_values else 0.0
    avg_usage_hours = (
        sum(usage_values) / len(usage_values) / 3600 if usage_values else 0.0
    )

    registry = CollectorRegistry()

    nights_gauge = Gauge(
        "cpap_nights_total",
        "Total number of therapy nights recorded.",
        registry=registry,
    )
    ahi_gauge = Gauge(
        "cpap_ahi_avg_last_30",
        "Average AHI over the most recent 30 nights.",
        registry=registry,
    )
    usage_gauge = Gauge(
        "cpap_usage_hours_avg_last_30",
        "Average usage in hours over the most recent 30 nights.",
        registry=registry,
    )

    nights_gauge.set(total_nights)
    ahi_gauge.set(avg_ahi)
    usage_gauge.set(avg_usage_hours)

    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
