# Hexapod Dashboard Core

This package provides the host-side foundation for `hexapod.serial`:

- NDJSON message parsing and validation
- a generic device/state model driven by `hello` and `capabilities`
- raw line recording and replay
- a small CLI for monitoring, sending commands, and replaying captures

It is intentionally GUI-free in v1. The future dashboard UI should consume this package rather than reimplementing serial parsing.

## Install

From the repository root:

```bash
python3 -m pip install -e './tools/hexapod_dashboard[serial]'
```

If you only want replay and parser tests, the optional `serial` extra is not required.

## CLI

Monitor a live device:

```bash
hexapod-dashboard monitor --port /dev/ttyUSB0 --record session.jsonl
```

Send a command:

```bash
hexapod-dashboard send --port /dev/ttyUSB0 --device leg --id 1 --name demo.stop
hexapod-dashboard send --port /dev/ttyUSB0 --device leg --id 2 --name param.set --args '{"param":"control.setpoint_adc","value":2450}'
```

Replay a recorded session:

```bash
hexapod-dashboard replay session.jsonl
```

## Package Layout

- `hexapod_dashboard.messages`: typed message schema and NDJSON parsing
- `hexapod_dashboard.model`: generic device state for hosts and future GUIs
- `hexapod_dashboard.session`: JSONL record and replay helpers
- `hexapod_dashboard.transport`: optional `pyserial` transport
- `hexapod_dashboard.cli`: reference command-line workflow
