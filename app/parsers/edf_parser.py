"""Parse Weinmann Modified EDF (.wmedf) signal files.

EDF format: 256-byte main header + ns*256 bytes signal headers + binary data.
Each data record = 1 second. Samples are 16-bit signed integers (little-endian)
or 8-bit unsigned depending on the digital range.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

# Max value for 8-bit unsigned samples
UINT8_MAX = 255


@dataclass
class SignalChannel:
    """EDF signal channel metadata and calibration."""

    label: str
    physical_dimension: str
    physical_min: float
    physical_max: float
    digital_min: int
    digital_max: int
    samples_per_record: int

    @property
    def gain(self) -> float:
        """Scale factor: physical units per digital unit."""
        dig_range = self.digital_max - self.digital_min
        if dig_range == 0:
            return 1.0
        return (self.physical_max - self.physical_min) / dig_range

    @property
    def offset(self) -> float:
        """Offset for digital-to-physical conversion."""
        return self.physical_min - self.gain * self.digital_min

    @property
    def is_8bit(self) -> bool:
        """Whether this channel uses 8-bit samples (0-255 range)."""
        return self.digital_min == 0 and self.digital_max == UINT8_MAX


@dataclass
class EdfHeader:
    """Parsed EDF file header with channel definitions."""

    start_date: str
    start_time: str
    header_bytes: int
    num_records: int
    record_duration: float
    channels: list[SignalChannel]

    @property
    def duration_seconds(self) -> int:
        """Total recording duration in seconds."""
        return int(self.num_records * self.record_duration)


def parse_edf_header(path: Path) -> EdfHeader:
    """Parse only the header of an EDF file (no signal data)."""
    with path.open("rb") as f:
        header = f.read(256)

        start_date = header[168:176].decode().strip()
        start_time = header[176:184].decode().strip()
        header_bytes = int(header[184:192].decode().strip())
        num_records_str = header[236:244].decode().strip()
        record_duration = float(header[244:252].decode().strip())
        num_signals = int(header[252:256].decode().strip())

        # Handle -1 (streaming/unknown) by calculating from file size
        if num_records_str == "-1":
            f.seek(0, 2)
            file_size = f.tell()
            # We need samples_per_record to calculate, so parse headers first
            num_records = -1
        else:
            num_records = int(num_records_str)
            file_size = None

        ns = num_signals
        f.seek(256)

        labels = [f.read(16).decode().strip() for _ in range(ns)]
        _transducers = [f.read(80).decode().strip() for _ in range(ns)]
        phys_dims = [f.read(8).decode().strip() for _ in range(ns)]
        phys_mins = [float(f.read(8).decode().strip()) for _ in range(ns)]
        phys_maxs = [float(f.read(8).decode().strip()) for _ in range(ns)]
        dig_mins = [int(f.read(8).decode().strip()) for _ in range(ns)]
        dig_maxs = [int(f.read(8).decode().strip()) for _ in range(ns)]
        _prefilters = [f.read(80).decode().strip() for _ in range(ns)]
        samples_per_record = [int(f.read(8).decode().strip()) for _ in range(ns)]
        _reserved = [f.read(32).decode().strip() for _ in range(ns)]

        channels = [
            SignalChannel(
                label=labels[i],
                physical_dimension=phys_dims[i],
                physical_min=phys_mins[i],
                physical_max=phys_maxs[i],
                digital_min=dig_mins[i],
                digital_max=dig_maxs[i],
                samples_per_record=samples_per_record[i],
            )
            for i in range(ns)
        ]

        # Calculate num_records if it was -1
        if num_records == -1 and file_size is not None:
            # Determine bytes per sample based on channels
            bytes_per_record = sum(
                ch.samples_per_record * (1 if ch.is_8bit else 2) for ch in channels
            )
            data_bytes = file_size - header_bytes
            num_records = data_bytes // bytes_per_record

    return EdfHeader(
        start_date=start_date,
        start_time=start_time,
        header_bytes=header_bytes,
        num_records=num_records,
        record_duration=record_duration,
        channels=channels,
    )


def read_signal_data(
    path: Path,
    channel_labels: list[str] | None = None,
    start_record: int = 0,
    num_records: int | None = None,
) -> dict[str, list[float]]:
    """Read signal data from an EDF file.

    Args:
        path: Path to the .wmedf file
        channel_labels: Which channels to read (None = all)
        start_record: First record to read (0-indexed)
        num_records: How many records to read (None = all remaining)

    Returns:
        Dict mapping channel label -> list of physical values

    """
    header = parse_edf_header(path)
    channels = header.channels

    # Determine which channels to read
    if channel_labels:
        channel_indices = [
            i for i, ch in enumerate(channels) if ch.label in channel_labels
        ]
    else:
        channel_indices = list(range(len(channels)))

    # Clamp record range
    if num_records is None:
        num_records = header.num_records - start_record
    num_records = min(num_records, header.num_records - start_record)
    if num_records <= 0:
        return {channels[i].label: [] for i in channel_indices}

    # Calculate byte layout per record
    # Each channel's samples are stored sequentially within a record
    # For this device: 8-bit channels use 1 byte/sample, 16-bit use 2 bytes/sample
    channel_byte_offsets: list[int] = []
    channel_byte_sizes: list[int] = []
    offset = 0
    for ch in channels:
        channel_byte_offsets.append(offset)
        byte_size = ch.samples_per_record * (1 if ch.is_8bit else 2)
        channel_byte_sizes.append(byte_size)
        offset += byte_size
    bytes_per_record = offset

    # Initialize output
    result: dict[str, list[float]] = {channels[i].label: [] for i in channel_indices}

    with path.open("rb") as f:
        f.seek(header.header_bytes + start_record * bytes_per_record)

        for _ in range(num_records):
            record_data = f.read(bytes_per_record)
            if len(record_data) < bytes_per_record:
                break

            for idx in channel_indices:
                ch = channels[idx]
                ch_offset = channel_byte_offsets[idx]
                ch_bytes = record_data[ch_offset : ch_offset + channel_byte_sizes[idx]]

                if ch.is_8bit:
                    # 8-bit unsigned samples
                    samples = struct.unpack(f"<{ch.samples_per_record}B", ch_bytes)
                else:
                    # 16-bit signed samples
                    samples = struct.unpack(f"<{ch.samples_per_record}h", ch_bytes)

                # Convert to physical units
                gain = ch.gain
                off = ch.offset
                physical = [s * gain + off for s in samples]
                result[ch.label].extend(physical)

    return result


def get_signal_summary(path: Path) -> dict:
    """Get a summary of signal file contents without reading all data."""
    header = parse_edf_header(path)
    return {
        "start_date": header.start_date,
        "start_time": header.start_time,
        "duration_seconds": header.duration_seconds,
        "channels": [
            {
                "label": ch.label,
                "unit": ch.physical_dimension,
                "samples_per_second": ch.samples_per_record / header.record_duration,
                "physical_min": ch.physical_min,
                "physical_max": ch.physical_max,
            }
            for ch in header.channels
        ],
    }
