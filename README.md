# Lowenstein Prisma CPAP Viewer

[![CI](https://github.com/frostyslav/lowenstein-prisma-viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/frostyslav/lowenstein-prisma-viewer/actions/workflows/ci.yml)
[![Publish Docker Image](https://github.com/frostyslav/lowenstein-prisma-viewer/actions/workflows/publish.yml/badge.svg)](https://github.com/frostyslav/lowenstein-prisma-viewer/actions/workflows/publish.yml)
[![Docker Hub](https://img.shields.io/docker/v/frostyslav/lowenstein-prisma-viewer?logo=docker&label=Docker%20Hub&sort=semver)](https://hub.docker.com/r/frostyslav/lowenstein-prisma-viewer)
[![License](https://img.shields.io/github/license/frostyslav/lowenstein-prisma-viewer)](LICENSE)

A self-hosted web application for viewing therapy data from Lowenstein (formerly Weinmann) Prisma series CPAP (Continuous Positive Airway Pressure) machines. Single-user, runs in Docker, stores data in SQLite.

## Quick Start

```bash
# 1. Copy your SD card contents
cp -r /path/to/sdcard/* sdcard/

# 2. Start the app
docker compose up --build

# 3. Open http://localhost:3000
# 4. Go to Import → click "Scan & Import"
```

## Architecture

```text
lowenstein-viewer/
  app/                      # Python backend (FastAPI)
    parsers/
      edf_parser.py         # WMEDF (Weinmann Modified European Data Format) signal file reader
      event_parser.py       # event_*.xml parser (respiratory events)
      json_config_parser.py # .pscfg (Prisma Smart Configuration) parser (JSON format)
      json_statistics_parser.py # .psstat (Prisma Smart Statistics) parser (JSON format)
      sd_scanner.py         # SD (Secure Digital) card directory scanner & importer
      config_parser.py      # Legacy XML config parser
      statistics_parser.py  # Legacy XML statistics parser
    routers/
      scan.py               # POST /api/scan — trigger import
      nights.py             # GET /api/nights — list/detail
      signals.py            # GET /api/signals — waveform data
      device.py             # GET /api/device — config display
      upload.py             # POST /api/upload — file upload (legacy)
    models.py               # SQLAlchemy ORM (Object-Relational Mapping) models (SQLite)
    database.py             # DB (database) connection
    main.py                 # FastAPI app + static file serving
  frontend/                 # React + Vite + Tailwind CSS + Recharts
    src/components/
      Dashboard.tsx         # AHI (Apnea-Hypopnea Index) trend, pressure, leak, event breakdown charts
      NightDetail.tsx       # Per-night metrics, event timeline, waveforms
      SignalViewer.tsx       # Interactive signal waveform viewer
      DeviceConfig.tsx      # Device info and therapy parameters
      Upload.tsx            # SD card scan UI (User Interface)
      Layout.tsx            # Navigation shell
  data/                     # SQLite database (volume-mounted, persists)
  sdcard/                   # SD card contents (volume-mounted, read-only)
  Dockerfile                # Multi-stage: Node (frontend) + Python (backend)
  docker-compose.yml        # Single container, two volumes
```

## How It Works

1. You copy your Prisma SD card contents to `sdcard/`
2. The app scans the directory structure: `<serial>/YYYYMMDD/0009/event_*.xml`
3. Events are parsed and stored in SQLite along with stats from `statistic.psstat`
4. Signal files (`signal_*.wmedf`) are indexed by path for on-demand waveform reading
5. The React frontend queries the API (Application Programming Interface) and renders charts

Data flow:

- **Statistics** come from `statistic.psstat` (JSON, JavaScript Object Notation) — provides therapy time, event counts, pressure histograms per night
- **Events** come from `event_*.xml` — individual apneas, hypopneas, RERAs (Respiratory Effort-Related Arousals) with timestamps
- **Waveforms** come from `signal_*.wmedf` — EDF (European Data Format)-format recordings read on demand (not stored in DB)
- **Config** comes from `config.pscfg` (JSON) — device settings and therapy parameters

## SD Card Structure

The app expects this layout in `sdcard/`:

```text
sdcard/
  <serial_number>/        # e.g. 0040012345
    YYYYMMDD/
      0009/
        event_NNN.xml     # Therapy events (apneas, hypopneas, etc.)
        signal_NNN.wmedf  # Waveform data (EDF format)
        trendCurves.tc    # Trend summary (not parsed yet)
  config.pscfg            # Device configuration (JSON)
  statistic.psstat        # Per-night statistics (JSON)
  Dcm/
    dcm.zip               # DCM (Device Configuration Module) archive (optional, legacy)
```

## Known Caveats

### Statistics field mapping is approximate

The `.psstat` JSON format uses numeric field keys without documentation. The mapping of fields to clinical metrics (which field is OA count vs CA count, etc.) is inferred by cross-referencing with event file data. It appears correct for the tested firmware but may differ on other Prisma models.

Current mapping:

- Field 6: therapy time (minutes)
- Field 7: usage time (minutes)
- Field 16: OA (Obstructive Apnea) count
- Field 17: OH (Obstructive Hypopnea) count
- Field 18: CA (Central Apnea) count
- Field 19: CH (Central Hypopnea) count
- Field 38: RERA count

### Epoch percentages are unreliable

The newer firmware's epoch events (flow limitation %, deep sleep %, snore %) use a different encoding than the older XML-based format. The computed percentages often exceed 100%, indicating the duration units have changed. These metrics are suppressed when they produce impossible values.

### Waveform Y-axis units are uncalibrated

The EDF headers for `RespFlow` and `FlowFull` channels declare `l/min` but use a 1:1 digital-to-physical mapping ([-32768, 32767] → [-32768, 32767]). The actual scale factor is unknown — the waveform shapes are correct but the Y-axis values are arbitrary. Pressure channels (hPa, hectopascals) are correctly scaled.

### AHI computation

AHI is computed as `(OA + CA + OH + CH) / therapy_hours`. This matches the standard definition but may differ slightly from the device display, which likely uses additional internal logic (time-windowed calculations, minimum duration thresholds, or epoch-based scoring).

Where:

- OA = Obstructive Apnea count
- CA = Central Apnea count
- OH = Obstructive Hypopnea count
- CH = Central Hypopnea count

### Short sessions are filtered

Sessions under 30 minutes are excluded from the dashboard. These are typically brief mask-on/off events that produce meaningless indices.

### Only the tested firmware format is supported

This app was developed against Prisma firmware `3.17.0008` with `.pscfg`/`.psstat` JSON format. Older devices that export `.pcfg`/`.pdat` ZIP archives (XML-based) have parser support but haven't been tested.

## Development

### Running locally without Docker

Backend:

```bash
cd lowenstein-viewer
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd lowenstein-viewer/frontend
npm install
npm run dev   # Proxies /api to localhost:8000
```

### Re-importing data

Delete `data/cpap.db` and re-scan to start fresh. The scanner skips nights already in the database, so you can also just add new SD card data and scan again.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (ORM), SQLite
- **Frontend:** React 19, Vite, Tailwind CSS, Recharts, React Router
- **Deployment:** Docker (single container), ~150MB image
- **Linting:** Ruff (Python), markdownlint (Markdown), hadolint (Dockerfile), commitlint (Conventional Commits)
