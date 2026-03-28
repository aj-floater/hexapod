# Devlink Dashboard

This package provides the host-side foundation for `devlink`:

- NDJSON message parsing and validation
- a generic device/state model driven by `hello` and `capabilities`
- raw line recording and replay
- a small CLI for monitoring, sending commands, replaying captures, and launching the GUI

The desktop GUI consumes the same parser, model, transport, and session modules as the CLI.

## Install

From the repository root:

```bash
python3 -m pip install -e './tools/devlink_dashboard[serial]'
```

If you only want replay and parser tests, the optional `serial` extra is not required.

To use the desktop GUI:

```bash
python3 -m pip install -e './tools/devlink_dashboard[gui]'
```

## CLI

Monitor a live device:

```bash
devlink-dashboard monitor --port /dev/ttyUSB0 --record session.jsonl
```

Send a command:

```bash
devlink-dashboard send --port /dev/ttyUSB0 --device leg --id 1 --name demo.stop
devlink-dashboard send --port /dev/ttyUSB0 --device leg --id 2 --name param.set --args '{"param":"control.setpoint_adc","value":2450}'
```

Replay a recorded session:

```bash
devlink-dashboard replay session.jsonl
```

Launch the desktop dashboard:

```bash
devlink-dashboard gui
devlink-dashboard gui --port /dev/ttyACM0 --record session.jsonl
```

The GUI now sends a bootstrap `device.describe` command on connect so it can recover `hello` and `capabilities` even if the board was already running before the host attached.

## Package Layout

- `devlink_dashboard.messages`: typed message schema and NDJSON parsing
- `devlink_dashboard.model`: generic device state for hosts and future GUIs
- `devlink_dashboard.session`: JSONL record and replay helpers
- `devlink_dashboard.transport`: optional `pyserial` transport
- `devlink_dashboard.gui`: Qt controller, runtime, and widgets for the desktop app
- `devlink_dashboard.cli`: reference command-line workflow
