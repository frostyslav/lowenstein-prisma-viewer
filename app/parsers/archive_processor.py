"""Top-level processor that handles .pcfg and .pdat ZIP archives."""

import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from io import BytesIO

from sqlalchemy.orm import Session

from app.models import Device, DeviceConfig, Import, Night, NightStat, SessionEvent

from .config_parser import DeviceInfo, parse_configuration_xml, parse_device_xml
from .event_parser import parse_event_xml
from .statistics_parser import DayStat, compute_night_metrics, parse_statistics_xml


def process_pcfg(db: Session, file_content: bytes, filename: str) -> dict:
    """Process a .pcfg archive: device info + configuration."""
    zf = zipfile.ZipFile(BytesIO(file_content))
    names = zf.namelist()

    # Find device.xml
    device_info = None
    for name in names:
        if name.endswith("device.xml"):
            device_info = parse_device_xml(zf.read(name))
            break

    if device_info is None:
        msg = "No device.xml found in archive"
        raise ValueError(msg)

    # Upsert device
    device = db.query(Device).filter_by(serial_number=device_info.serial_number).first()
    if not device:
        device = Device(
            serial_number=device_info.serial_number,
            device_type=device_info.device_type,
            firmware_version=device_info.firmware_version,
        )
        db.add(device)
        db.flush()
    else:
        device.firmware_version = device_info.firmware_version
        device.device_type = device_info.device_type

    # Parse configuration
    config_params = []
    for name in names:
        if name.endswith("configuration.xml"):
            config_params = parse_configuration_xml(zf.read(name))
            break

    # Replace existing config for this device
    db.query(DeviceConfig).filter_by(device_id=device.id).delete()
    for param in config_params:
        db.add(
            DeviceConfig(
                device_id=device.id,
                section=param.section,
                param_id=param.param_id,
                value=param.value,
            ),
        )

    # Record import
    imp = Import(filename=filename, file_type="pcfg", nights_imported=0)
    db.add(imp)
    db.commit()

    return {
        "device_serial": device_info.serial_number,
        "config_params": len(config_params),
    }


def _extract_device_from_zip(zf: zipfile.ZipFile) -> DeviceInfo:
    """Find and parse device.xml from a ZIP archive."""
    for name in zf.namelist():
        if name.endswith("device.xml"):
            return parse_device_xml(zf.read(name))
    msg = "No device.xml found in archive"
    raise ValueError(msg)


def _collect_statistics(
    zf: zipfile.ZipFile,
    names: list[str],
) -> dict[date, list[DayStat]]:
    """Parse statistics_year.bin from the archive if present."""
    stat_file = None
    for name in names:
        if "statistics_year.bin" in name:
            stat_file = name
            break

    if not stat_file:
        return {}

    nights_from_stats: dict[date, list[DayStat]] = {}
    day_records = parse_statistics_xml(zf.read(stat_file))
    for day_rec in day_records:
        nights_from_stats[day_rec.night_date] = day_rec.stats
    return nights_from_stats


def _collect_event_files(names: list[str]) -> dict[str, list[str]]:
    """Group event file paths by date directory."""
    event_files: dict[str, list[str]] = {}
    event_pattern = re.compile(r"events/(\d{8})/event_(\d+)\.xml$")

    for name in names:
        m = event_pattern.search(name)
        if m:
            date_str = m.group(1)
            event_files.setdefault(date_str, []).append(name)
    return event_files


def _apply_stats_to_night(night: Night, metrics: dict) -> None:
    """Set night attributes from a computed metrics dictionary."""
    night.usage_seconds = metrics["usage_seconds"]
    night.therapy_seconds = metrics["therapy_seconds"]
    night.obstructive_apneas = metrics["obstructive_apneas"]
    night.central_apneas = metrics["central_apneas"]
    night.obstructive_hypopneas = metrics["obstructive_hypopneas"]
    night.central_hypopneas = metrics["central_hypopneas"]
    night.reras = metrics["reras"]
    night.ai_central = metrics["ai_central"]
    night.hi_central = metrics["hi_central"]
    night.rera_index = metrics["rera_index"]
    night.pressure_max = metrics["pressure_max"]
    night.pressure_min = metrics["pressure_min"]
    night.pressure_median = metrics["pressure_median"]
    night.pressure_95 = metrics["pressure_95"]
    night.leak_95 = metrics["leak_95"]


def _process_night_events(
    db: Session,
    night: Night,
    event_file_list: list[str],
    zf: zipfile.ZipFile,
) -> None:
    """Parse event files and store events + epoch-derived percentages on night."""
    for idx, event_file_path in enumerate(sorted(event_file_list)):
        try:
            result = parse_event_xml(zf.read(event_file_path))
        except (ET.ParseError, KeyError, ValueError, zipfile.BadZipFile):
            continue

        # Update epoch percentages from events if not from stats
        if result.session_duration_ds > 0:
            session_secs = result.session_duration_ds / 10.0
            if result.epochs.deep_sleep_ds > 0 and night.deep_sleep_pct is None:
                night.deep_sleep_pct = round(
                    result.epochs.deep_sleep_ds / 10.0 / session_secs * 100,
                )
            if result.epochs.snore_ds > 0 and night.snore_pct is None:
                night.snore_pct = round(
                    result.epochs.snore_ds / 10.0 / session_secs * 100,
                )
            if (
                result.epochs.flow_limitation_ds > 0
                and night.flow_limitation_pct is None
            ):
                night.flow_limitation_pct = round(
                    result.epochs.flow_limitation_ds / 10.0 / session_secs * 100,
                )

        # Store individual events
        for event in result.events:
            db.add(
                SessionEvent(
                    night_id=night.id,
                    session_index=idx,
                    event_type=event.event_type,
                    resp_event_id=event.resp_event_id,
                    start_seconds=event.start_seconds,
                    duration_seconds=event.duration_seconds,
                    strength=event.strength,
                    pressure_pa=event.pressure,
                ),
            )


def process_pdat(db: Session, file_content: bytes, filename: str) -> dict:
    """Process a .pdat archive: events, statistics, sessions."""
    zf = zipfile.ZipFile(BytesIO(file_content))
    names = zf.namelist()

    device_info = _extract_device_from_zip(zf)

    device = db.query(Device).filter_by(serial_number=device_info.serial_number).first()
    if not device:
        device = Device(
            serial_number=device_info.serial_number,
            device_type=device_info.device_type,
            firmware_version=device_info.firmware_version,
        )
        db.add(device)
        db.flush()

    nights_imported = 0

    nights_from_stats = _collect_statistics(zf, names)
    event_files = _collect_event_files(names)

    # Get all dates to process (union of stats + events)
    all_dates: set[date] = set(nights_from_stats.keys())
    for date_str in event_files:
        try:
            d = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            all_dates.add(d)
        except ValueError:
            pass

    for night_date in sorted(all_dates):
        # Skip if already imported
        existing = (
            db.query(Night)
            .filter_by(device_id=device.id, night_date=night_date)
            .first()
        )
        if existing:
            continue

        # Create night record
        night = Night(device_id=device.id, night_date=night_date)

        # Populate from statistics if available
        day_stats = nights_from_stats.get(night_date, [])
        if day_stats:
            metrics = compute_night_metrics(day_stats)
            _apply_stats_to_night(night, metrics)

            # Compute AHI: (OA + CA + OH + CH) / therapy_hours
            therapy_hours = (metrics["therapy_seconds"] or 0) / 3600.0
            if therapy_hours > 0:
                total_events = (
                    (metrics["obstructive_apneas"] or 0)
                    + (metrics["central_apneas"] or 0)
                    + (metrics["obstructive_hypopneas"] or 0)
                    + (metrics["central_hypopneas"] or 0)
                )
                night.ahi = round(total_events / therapy_hours, 1)

        db.add(night)
        db.flush()

        # Store raw stats
        for stat in day_stats:
            db.add(
                NightStat(
                    night_id=night.id,
                    stat_id=stat.stat_id,
                    value=stat.value,
                ),
            )

        # Process event files for this night
        date_str = night_date.strftime("%Y%m%d")
        event_file_list = event_files.get(date_str, [])
        _process_night_events(db, night, event_file_list, zf)

        nights_imported += 1

    # Record import
    imp = Import(filename=filename, file_type="pdat", nights_imported=nights_imported)
    db.add(imp)
    db.commit()

    return {
        "device_serial": device_info.serial_number,
        "nights_imported": nights_imported,
        "total_nights": len(all_dates),
    }
