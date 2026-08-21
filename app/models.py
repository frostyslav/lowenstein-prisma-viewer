"""SQLAlchemy ORM models for CPAP therapy data."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Device(Base):
    """CPAP device identity and firmware info."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    device_type: Mapped[str | None] = mapped_column(String, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeviceConfig(Base):
    """Therapy configuration parameters from configuration.xml."""

    __tablename__ = "device_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, index=True)
    section: Mapped[str] = mapped_column(String)  # OBL or OPT
    param_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(String)


class Night(Base):
    """One therapy night (noon-to-noon)."""

    __tablename__ = "nights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, index=True)
    night_date: Mapped[date] = mapped_column(Date, index=True)
    usage_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    therapy_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ahi: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_central: Mapped[float | None] = mapped_column(Float, nullable=True)
    hi_central: Mapped[float | None] = mapped_column(Float, nullable=True)
    rera_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    obstructive_apneas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    central_apneas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    obstructive_hypopneas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    central_hypopneas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reras: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deep_sleep_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    snore_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    flow_limitation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    leak_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_95: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_min: Mapped[float | None] = mapped_column(Float, nullable=True)


class SessionEvent(Base):
    """Individual respiratory events within a therapy session."""

    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    night_id: Mapped[int] = mapped_column(Integer, index=True)
    session_index: Mapped[int] = mapped_column(Integer)  # Which event file (sequence #)
    event_type: Mapped[str] = mapped_column(
        String,
    )  # e.g. "OA", "CA", "OH", "CH", "RERA"
    resp_event_id: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column(Float)  # Seconds from session start
    duration_seconds: Mapped[float] = mapped_column(Float)
    strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pressure_pa: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NightStat(Base):
    """Raw statistics from statistics_year.bin, per night."""

    __tablename__ = "night_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    night_id: Mapped[int] = mapped_column(Integer, index=True)
    stat_id: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(Text)  # String to support CSV histogram data


class Import(Base):
    """Track imported archives to avoid duplicates."""

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)  # "pcfg" or "pdat"
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    nights_imported: Mapped[int] = mapped_column(Integer, default=0)


class SignalFile(Base):
    """Track signal file paths for waveform viewing."""

    __tablename__ = "signal_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    night_id: Mapped[int] = mapped_column(Integer, index=True)
    session_index: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String)  # Relative path within sdcard mount
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    num_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
