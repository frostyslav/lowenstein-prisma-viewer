"""Scan raw SD card directory structure and import therapy data.

Expected layout:
  <mount>/
    <serial_number>/          # e.g. 0040032244
      YYYYMMDD/
        0009/
          event_NNN.xml
          signal_NNN.wmedf
          trendCurves.tc
      log/
        develop.log
        service.log
    config.pscfg              # Device configuration (JSON format)
    statistic.psstat          # Statistics (JSON format)
    Dcm/
      dcm.zip                 # Device config module (ZIP containing device.xml + configuration.xml)
"""

import re
import struct
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Device, DeviceConfig, Night, NightStat, SessionEvent, SignalFile

from .config_parser import parse_configuration_xml, parse_device_xml
from .edf_parser import parse_edf_header
from .event_parser import SessionParseResult, parse_event_xml
from .json_config_parser import parse_pscfg
from .json_statistics_parser import (
    JsonDayStats,
    compute_night_metrics_from_json,
    parse_psstat,
)
from .statistics_parser import DayStat, compute_night_metrics, parse_statistics_xml

# Pattern for serial number directories (numeric, 10 digits)
SERIAL_PATTERN = re.compile(r"^\d{10}$")
# Pattern for date directories
DATE_PATTERN = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
# Pattern for event files
EVENT_PATTERN = re.compile(r"^event_(\d+)\.xml$")

# Minimum therapy duration to consider a session valid (30 minutes in seconds)
MIN_THERAPY_SECONDS = 1800

# Respiratory event IDs for counting
RESP_EVENT_OA = 101
RESP_EVENT_CA = 102
RESP_EVENT_OH = 111
RESP_EVENT_CH = 112
RESP_EVENT_RERA = 121

# Percentage cap for epoch-based metrics
MAX_PERCENT = 100

# Minimum therapy hours to compute AHI
MIN_THERAPY_HOURS = 0.5


@dataclass
class NightImportContext:
    """Bundle of arguments for importing a single night."""

    device: Device
    night_date: date
    event_files: list[Path]
    signal_files: list[Path]
    json_day: JsonDayStats | None
    xml_day_stats: list[DayStat]
    sd_path: Path


@dataclass
class _ScanContext:
    """Bundle of shared state for SD card scanning."""

    json_stats_by_date: dict[date, JsonDayStats]
    xml_stats_by_date: dict[date, list[DayStat]]
    sd_path: Path
    result: dict


def scan_and_import(db: Session, sd_path: Path) -> dict:
    """Scan the SD card mount and import all therapy data."""
    if not sd_path.exists():
        msg = f"SD card path does not exist: {sd_path}"
        raise ValueError(msg)

    result = {
        "devices": [],
        "nights_imported": 0,
        "nights_skipped": 0,
        "errors": [],
    }

    # --- Import device config from config.pscfg or Dcm/dcm.zip ---
    _import_device_config(db, sd_path, result)

    # --- Import statistics from statistic.psstat ---
    json_stats_by_date, xml_stats_by_date = _parse_statistics_file(sd_path, result)

    scan_ctx = _ScanContext(
        json_stats_by_date=json_stats_by_date,
        xml_stats_by_date=xml_stats_by_date,
        sd_path=sd_path,
        result=result,
    )

    # --- Scan serial number directories for nightly data ---
    for entry in sorted(sd_path.iterdir()):
        if not entry.is_dir():
            continue
        if not SERIAL_PATTERN.match(entry.name):
            continue

        _process_device_directory(db, entry, scan_ctx)

    db.commit()
    return result


def _parse_statistics_file(
    sd_path: Path,
    result: dict,
) -> tuple[dict[date, JsonDayStats], dict[date, list[DayStat]]]:
    """Parse statistic.psstat and return JSON and XML stats mappings."""
    json_stats_by_date: dict[date, JsonDayStats] = {}
    xml_stats_by_date: dict[date, list[DayStat]] = {}

    stat_file = sd_path / "statistic.psstat"
    if not stat_file.exists():
        return json_stats_by_date, xml_stats_by_date

    try:
        content = stat_file.read_bytes()
        # Try JSON first (newer firmware)
        if content.strip().startswith(b"{"):
            day_stats = parse_psstat(content)
            for ds in day_stats:
                json_stats_by_date[ds.night_date] = ds
        else:
            # Fall back to XML (older firmware)
            day_records = parse_statistics_xml(content)
            for rec in day_records:
                xml_stats_by_date[rec.night_date] = rec.stats
    except (ValueError, KeyError, OSError) as e:
        result["errors"].append(f"Failed to parse statistic.psstat: {e}")

    return json_stats_by_date, xml_stats_by_date


def _process_device_directory(
    db: Session,
    entry: Path,
    scan_ctx: _ScanContext,
) -> None:
    """Process a single device serial number directory."""
    serial = entry.name
    device = _get_or_create_device(db, serial)

    if serial not in scan_ctx.result["devices"]:
        scan_ctx.result["devices"].append(serial)

    # Scan date directories
    for date_dir in sorted(entry.iterdir()):
        if not date_dir.is_dir():
            continue
        m = DATE_PATTERN.match(date_dir.name)
        if not m:
            continue

        try:
            night_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue

        # Skip if already imported
        existing = (
            db.query(Night)
            .filter_by(device_id=device.id, night_date=night_date)
            .first()
        )
        if existing:
            scan_ctx.result["nights_skipped"] += 1
            continue

        # Find event files (in subdirectory like 0009/)
        event_files = _find_event_files(date_dir)
        if not event_files:
            continue

        # Find signal files
        signal_files = _find_signal_files(date_dir)

        try:
            json_day = scan_ctx.json_stats_by_date.get(night_date)
            xml_day = scan_ctx.xml_stats_by_date.get(night_date, [])

            ctx = NightImportContext(
                device=device,
                night_date=night_date,
                event_files=event_files,
                signal_files=signal_files,
                json_day=json_day,
                xml_day_stats=xml_day,
                sd_path=scan_ctx.sd_path,
            )
            _import_night(db, ctx)

            # Remove if therapy time is too short to be meaningful
            night = (
                db.query(Night)
                .filter_by(device_id=device.id, night_date=night_date)
                .first()
            )
            if night and (night.therapy_seconds or 0) < MIN_THERAPY_SECONDS:
                db.query(SessionEvent).filter_by(night_id=night.id).delete()
                db.query(NightStat).filter_by(night_id=night.id).delete()
                db.query(SignalFile).filter_by(night_id=night.id).delete()
                db.delete(night)
                continue

            scan_ctx.result["nights_imported"] += 1
        except (ValueError, KeyError, OSError, TypeError) as e:
            scan_ctx.result["errors"].append(f"Failed to import {night_date}: {e}")


def _import_device_config(db: Session, sd_path: Path, result: dict) -> str | None:
    """Try to extract device info from config.pscfg (JSON) or Dcm/dcm.zip."""
    serial = None

    # Try config.pscfg first (JSON format, newer firmware)
    pscfg = sd_path / "config.pscfg"
    if pscfg.exists():
        try:
            content = pscfg.read_bytes()
            if content.strip().startswith(b"{"):
                serial = _import_pscfg_json(db, content)
            elif content[:2] == b"PK":
                serial = _import_pscfg_zip(db, pscfg)
            else:
                serial = _import_pscfg_xml(db, content, sd_path)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
            result["errors"].append(f"Failed to parse config.pscfg: {e}")

    # Try Dcm/dcm.zip as fallback
    dcm_zip = sd_path / "Dcm" / "dcm.zip"
    if dcm_zip.exists() and serial is None:
        try:
            serial = _import_dcm_zip(db, dcm_zip)
        except (ValueError, KeyError, OSError, zipfile.BadZipFile) as e:
            result["errors"].append(f"Failed to parse Dcm/dcm.zip: {e}")

    return serial


def _import_pscfg_json(db: Session, content: bytes) -> str | None:
    """Parse JSON config.pscfg and store device info + params."""
    device_info, params = parse_pscfg(content)
    serial = device_info.serial_number
    device = _get_or_create_device(db, serial)
    device.device_type = device_info.device_type
    device.firmware_version = device_info.firmware_version

    # Store config params
    db.query(DeviceConfig).filter_by(device_id=device.id).delete()
    for p in params:
        db.add(
            DeviceConfig(
                device_id=device.id,
                section=p.section,
                param_id=p.param_id,
                value=p.value,
            ),
        )
    return serial


def _import_pscfg_zip(db: Session, pscfg_path: Path) -> str | None:
    """Parse ZIP-format config.pscfg."""
    serial = None
    with zipfile.ZipFile(pscfg_path) as zf:
        for name in zf.namelist():
            if name.endswith("device.xml"):
                info = parse_device_xml(zf.read(name))
                serial = info.serial_number
                break
        for name in zf.namelist():
            if name.endswith("configuration.xml"):
                xml_params = parse_configuration_xml(zf.read(name))
                if serial:
                    device = _get_or_create_device(db, serial)
                    db.query(DeviceConfig).filter_by(device_id=device.id).delete()
                    for p in xml_params:
                        db.add(
                            DeviceConfig(
                                device_id=device.id,
                                section=p.section,
                                param_id=p.param_id,
                                value=p.value,
                            ),
                        )
                break
    return serial


def _import_pscfg_xml(db: Session, content: bytes, sd_path: Path) -> str | None:
    """Parse raw XML config.pscfg."""
    xml_params = parse_configuration_xml(content)
    if not xml_params:
        return None

    serial = None
    for entry in sd_path.iterdir():
        if entry.is_dir() and SERIAL_PATTERN.match(entry.name):
            serial = entry.name
            break

    if serial:
        device = _get_or_create_device(db, serial)
        db.query(DeviceConfig).filter_by(device_id=device.id).delete()
        for p in xml_params:
            db.add(
                DeviceConfig(
                    device_id=device.id,
                    section=p.section,
                    param_id=p.param_id,
                    value=p.value,
                ),
            )
    return serial


def _import_dcm_zip(db: Session, dcm_path: Path) -> str | None:
    """Parse Dcm/dcm.zip for device info and configuration."""
    serial = None
    with zipfile.ZipFile(dcm_path) as zf:
        names = zf.namelist()
        for name in names:
            if name.endswith("device.xml"):
                info = parse_device_xml(zf.read(name))
                serial = info.serial_number
                device = _get_or_create_device(db, serial)
                device.device_type = info.device_type
                device.firmware_version = info.firmware_version
                break

        for name in names:
            if name.endswith("configuration.xml"):
                xml_params = parse_configuration_xml(zf.read(name))
                if serial:
                    device = _get_or_create_device(db, serial)
                    db.query(DeviceConfig).filter_by(device_id=device.id).delete()
                    for p in xml_params:
                        db.add(
                            DeviceConfig(
                                device_id=device.id,
                                section=p.section,
                                param_id=p.param_id,
                                value=p.value,
                            ),
                        )
                break
    return serial


def _find_event_files(date_dir: Path) -> list[Path]:
    """Find all event_*.xml files within a date directory (may be in a subdirectory)."""
    event_files = list(date_dir.glob("event_*.xml"))

    # Check subdirectories (e.g. 0009/)
    for sub in date_dir.iterdir():
        if sub.is_dir():
            event_files.extend(sub.glob("event_*.xml"))

    return sorted(event_files)


def _find_signal_files(date_dir: Path) -> list[Path]:
    """Find all signal_*.wmedf files within a date directory."""
    signal_files = list(date_dir.glob("signal_*.wmedf"))

    for sub in date_dir.iterdir():
        if sub.is_dir():
            signal_files.extend(sub.glob("signal_*.wmedf"))

    return sorted(signal_files)


def _import_night(db: Session, ctx: NightImportContext) -> None:
    """Import a single night from event files and optional stats."""
    night = Night(device_id=ctx.device.id, night_date=ctx.night_date)

    # Populate from JSON statistics (preferred) or XML statistics
    if ctx.json_day:
        _apply_json_stats(night, ctx.json_day)
    elif ctx.xml_day_stats:
        _apply_xml_stats(night, ctx.xml_day_stats)

    db.add(night)
    db.flush()

    # Store raw stats from XML (if available)
    for stat in ctx.xml_day_stats:
        db.add(NightStat(night_id=night.id, stat_id=stat.stat_id, value=stat.value))

    # Process event files
    has_stats = ctx.json_day is not None or len(ctx.xml_day_stats) > 0
    epoch_totals = _process_event_files(db, night, ctx.event_files, has_stats=has_stats)

    # Apply epoch percentages
    _apply_epoch_percentages(night, epoch_totals, has_stats=has_stats)

    # Store signal file references
    _store_signal_files(db, night, ctx.signal_files, ctx.sd_path)


def _apply_json_stats(night: Night, json_day: JsonDayStats) -> None:
    """Apply JSON statistics metrics to a night record."""
    metrics = compute_night_metrics_from_json(json_day)
    night.usage_seconds = metrics["usage_seconds"]
    night.therapy_seconds = metrics["therapy_seconds"]
    night.ahi = metrics["ahi"]
    night.obstructive_apneas = metrics["obstructive_apneas"]
    night.central_apneas = metrics["central_apneas"]
    night.obstructive_hypopneas = metrics["obstructive_hypopneas"]
    night.central_hypopneas = metrics["central_hypopneas"]
    night.reras = metrics["reras"]
    night.ai_central = metrics["ai_central"]
    night.hi_central = metrics["hi_central"]
    night.rera_index = metrics["rera_index"]
    night.pressure_median = metrics["pressure_median"]
    night.pressure_95 = metrics["pressure_95"]


def _apply_xml_stats(night: Night, xml_day_stats: list[DayStat]) -> None:
    """Apply XML statistics metrics to a night record."""
    metrics = compute_night_metrics(xml_day_stats)
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

    therapy_hours = (metrics["therapy_seconds"] or 0) / 3600.0
    if therapy_hours > 0:
        total_events = (
            (metrics["obstructive_apneas"] or 0)
            + (metrics["central_apneas"] or 0)
            + (metrics["obstructive_hypopneas"] or 0)
            + (metrics["central_hypopneas"] or 0)
        )
        night.ahi = round(total_events / therapy_hours, 1)


@dataclass
class _EpochTotals:
    """Accumulated epoch totals from all event files in a night."""

    total_session_duration_ds: int = 0
    total_deep_sleep_ds: int = 0
    total_snore_ds: int = 0
    total_flow_limitation_ds: int = 0


def _process_event_files(
    db: Session,
    night: Night,
    event_files: list[Path],
    *,
    has_stats: bool,
) -> _EpochTotals:
    """Parse event files, store events, and accumulate epoch totals."""
    totals = _EpochTotals()

    for idx, event_file in enumerate(event_files):
        try:
            content = event_file.read_bytes()
            parsed = parse_event_xml(content)
        except (OSError, ValueError, KeyError):
            continue

        totals.total_session_duration_ds += parsed.session_duration_ds
        totals.total_deep_sleep_ds += parsed.epochs.deep_sleep_ds
        totals.total_snore_ds += parsed.epochs.snore_ds
        totals.total_flow_limitation_ds += parsed.epochs.flow_limitation_ds

        # Store individual events
        for event in parsed.events:
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

        # If no stats, compute event counts from event files
        if not has_stats:
            _accumulate_event_counts(night, parsed)

    return totals


def _accumulate_event_counts(night: Night, parsed: SessionParseResult) -> None:
    """Accumulate respiratory event counts on the night from a parsed session."""
    for event in parsed.events:
        if event.resp_event_id == RESP_EVENT_OA:
            night.obstructive_apneas = (night.obstructive_apneas or 0) + 1
        elif event.resp_event_id == RESP_EVENT_CA:
            night.central_apneas = (night.central_apneas or 0) + 1
        elif event.resp_event_id == RESP_EVENT_OH:
            night.obstructive_hypopneas = (night.obstructive_hypopneas or 0) + 1
        elif event.resp_event_id == RESP_EVENT_CH:
            night.central_hypopneas = (night.central_hypopneas or 0) + 1
        elif event.resp_event_id == RESP_EVENT_RERA:
            night.reras = (night.reras or 0) + 1


def _apply_epoch_percentages(
    night: Night,
    totals: _EpochTotals,
    *,
    has_stats: bool,
) -> None:
    """Compute and apply epoch-based percentages to a night record."""
    if totals.total_session_duration_ds <= 0:
        return

    session_secs = totals.total_session_duration_ds / 10.0

    if totals.total_deep_sleep_ds > 0:
        deep_pct = totals.total_deep_sleep_ds / 10.0 / session_secs * MAX_PERCENT
        if 0 < deep_pct <= MAX_PERCENT:
            night.deep_sleep_pct = round(deep_pct)

    if totals.total_snore_ds > 0:
        snore_pct = totals.total_snore_ds / 10.0 / session_secs * MAX_PERCENT
        if 0 < snore_pct <= MAX_PERCENT:
            night.snore_pct = round(snore_pct)

    if totals.total_flow_limitation_ds > 0:
        fl_pct = totals.total_flow_limitation_ds / 10.0 / session_secs * MAX_PERCENT
        if 0 < fl_pct <= MAX_PERCENT:
            night.flow_limitation_pct = round(fl_pct)

    # If no stats, compute therapy time and AHI from events
    if not has_stats:
        night.therapy_seconds = int(session_secs)
        therapy_hours = session_secs / 3600.0
        if therapy_hours >= MIN_THERAPY_HOURS:
            total_events = (
                (night.obstructive_apneas or 0)
                + (night.central_apneas or 0)
                + (night.obstructive_hypopneas or 0)
                + (night.central_hypopneas or 0)
            )
            night.ahi = round(total_events / therapy_hours, 1)


def _store_signal_files(
    db: Session,
    night: Night,
    signal_files: list[Path],
    sd_path: Path,
) -> None:
    """Store signal file references for waveform viewing."""
    for idx, sig_path in enumerate(signal_files):
        # Store path relative to sd_path
        rel_path = str(sig_path.relative_to(sd_path))
        duration = None
        num_channels = None
        try:
            hdr = parse_edf_header(sig_path)
            duration = hdr.duration_seconds
            num_channels = len(hdr.channels)
        except (OSError, ValueError, struct.error):
            pass

        db.add(
            SignalFile(
                night_id=night.id,
                session_index=idx,
                file_path=rel_path,
                duration_seconds=duration,
                num_channels=num_channels,
            ),
        )


def _get_or_create_device(db: Session, serial: str) -> Device:
    """Get existing device or create a new one."""
    device = db.query(Device).filter_by(serial_number=serial).first()
    if not device:
        device = Device(serial_number=serial)
        db.add(device)
        db.flush()
    return device
