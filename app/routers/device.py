"""API for device info and configuration."""

import contextlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, DeviceConfig

router = APIRouter(prefix="/api/device", tags=["device"])

# Human-readable parameter names (subset of the most useful ones)
PARAM_NAMES: dict[int, str] = {
    1003: "Therapy Mode",
    1005: "Autostart",
    1011: "Humidifier Level",
    1012: "Heated Tube Temp",
    1014: "Ramp Enabled",
    1015: "Ramp Time (min)",
    1018: "CPAP Fixed Pressure",
    1023: "Mask Type",
    1083: "Comfort Level",
    1123: "EPAP Mode",
    1125: "EPAP Pressure",
    1126: "IPAP Pressure",
    1127: "PS Min",
    1128: "PS Max",
    1138: "Min Pressure",
    1139: "Max Pressure",
    1199: "Max Therapy Pressure",
    1200: "Start Pressure",
}

THERAPY_MODES: dict[str, str] = {
    "0": "CPAP",
    "1": "APAP",
    "2": "APAP+",
    "3": "BiLevel",
    "4": "ASV",
    "5": "iVAPS",
}

# Params that are pressures in Pa
PRESSURE_PARAMS = {1018, 1125, 1126, 1127, 1128, 1138, 1139, 1199, 1200, 1201}

# Therapy mode parameter ID
PARAM_THERAPY_MODE = 1003


@router.get("")
def get_device(db: Session = Depends(get_db)) -> dict:
    """Get device info and configuration."""
    device = db.query(Device).first()
    if not device:
        raise HTTPException(status_code=404, detail="No device imported yet")

    configs = db.query(DeviceConfig).filter_by(device_id=device.id).all()

    config_list = []
    for c in configs:
        name = PARAM_NAMES.get(c.param_id, f"Param_{c.param_id}")
        display_value = c.value

        # Convert pressure Pa to cmH2O
        if c.param_id in PRESSURE_PARAMS:
            with contextlib.suppress(ValueError):
                display_value = f"{int(c.value) / 100:.1f} cmH2O"

        # Decode therapy mode
        if c.param_id == PARAM_THERAPY_MODE:
            display_value = THERAPY_MODES.get(c.value, c.value)

        config_list.append(
            {
                "section": c.section,
                "param_id": c.param_id,
                "name": name,
                "raw_value": c.value,
                "display_value": display_value,
            },
        )

    return {
        "serial_number": device.serial_number,
        "device_type": device.device_type,
        "firmware_version": device.firmware_version,
        "config": config_list,
    }
