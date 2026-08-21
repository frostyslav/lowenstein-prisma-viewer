"""API endpoint to trigger SD card scan/import."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.parsers.sd_scanner import scan_and_import

router = APIRouter(prefix="/api/scan", tags=["scan"])

SDCARD_PATH = Path("/app/sdcard")


@router.post("")
def trigger_scan(db: Session = Depends(get_db)) -> dict:
    """Scan the mounted SD card directory and import new therapy data."""
    if not SDCARD_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="SD card directory not found. Mount your CPAP data to /app/sdcard.",
        )

    # Check if there's any content
    contents = list(SDCARD_PATH.iterdir())
    if not contents:
        raise HTTPException(
            status_code=404,
            detail="SD card directory is empty. Copy your CPAP data to the sdcard/ folder.",
        )

    try:
        result = scan_and_import(db, SDCARD_PATH)
    except (ValueError, OSError, TypeError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}") from e

    return {
        "status": "ok",
        "devices": result["devices"],
        "nights_imported": result["nights_imported"],
        "nights_skipped": result["nights_skipped"],
        "errors": result["errors"],
    }


@router.get("/status")
def scan_status() -> dict:
    """Check if SD card is mounted and what's available."""
    mounted = (
        SDCARD_PATH.exists() and any(SDCARD_PATH.iterdir())
        if SDCARD_PATH.exists()
        else False
    )

    return {
        "mounted": mounted,
        "path": str(SDCARD_PATH),
    }
