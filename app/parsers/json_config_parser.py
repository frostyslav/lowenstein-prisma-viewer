"""Parse JSON-format .pscfg config files (newer Prisma firmware)."""

import json
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    """Device identity from JSON config."""

    serial_number: str
    device_type: str
    firmware_version: str


@dataclass
class ConfigParam:
    """Single configuration parameter from JSON config."""

    section: str  # "cfg" for these files
    param_id: int
    value: str


def parse_pscfg(content: bytes) -> tuple[DeviceInfo, list[ConfigParam]]:
    """Parse a .pscfg JSON file, returning device info and config params."""
    data = json.loads(content)

    dev = data.get("dev", {})
    # Serial number is hex-encoded
    sn_raw = dev.get("sn", "")
    serial = str(int(sn_raw, 16)) if sn_raw.startswith("0x") else sn_raw
    # Pad to 10 digits to match directory naming
    serial = serial.zfill(10)

    device_info = DeviceInfo(
        serial_number=serial,
        device_type=dev.get("devid", data.get("devid", "")),
        firmware_version=dev.get("fwversion", ""),
    )

    params: list[ConfigParam] = []
    cfg = data.get("cfg", {})
    for key, value in cfg.items():
        try:
            param_id = int(key)
        except ValueError:
            continue
        params.append(
            ConfigParam(
                section="cfg",
                param_id=param_id,
                value=str(value),
            ),
        )

    return device_info, params
