# Changelog

All notable changes to Tilt UI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-28

### Added
- Real-time Tilt hydrometer monitoring dashboard
- BLE scanning using Bleak library for Tilt device detection
- WebSocket-based live updates to frontend
- SG and temperature calibration with linear interpolation
- Calibration point management (add, view, clear)
- Historical readings storage with SQLite/SQLAlchemy async
- CSV export of all readings
- Automatic data cleanup (30-day retention)
- Multi-mode scanner support:
  - BLE mode (production): Direct Bluetooth scanning
  - Mock mode: Simulated readings for development
  - File mode: Read from TiltPi JSON files
  - Relay mode: Fetch from remote TiltPi
- Systemd service for Raspberry Pi deployment
- Svelte frontend with responsive design
- REST API for tilts, readings, calibration, and system info

### Technical
- FastAPI backend with async SQLAlchemy 2.1
- Bleak BLE library with beacontools for iBeacon parsing
- SQLite database with automatic migrations
- WebSocket manager for real-time client updates
