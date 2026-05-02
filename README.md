# Hexapod Robot Public Repository

## Introduction

This repository contains the public engineering artifacts for a six-legged robot project. It combines embedded firmware for RP2040-based control experiments, host-side tooling for communicating with and visualizing device state, a C++ simulation/editor shell, hardware design files, and supporting media used during development.

The public repository is organised to let a technically competent reader inspect the control stack, reproduce the host tooling, build the current simulation executable, and review the mechanical and electronics design files. It is intended as the software and hardware workspace for the project rather than a polished end-user product.

## Contextual Overview

The project is split into four main layers:

```text
hardware/ CAD and PCB assets
    ->
firmware/ RP2040 targets implementing control loops and devlink endpoints
    <-UART/devlink->
tools/devlink_dashboard/ Python host tooling for monitor, replay, commands, and GUI

software/simulation/ C++ editor-style sandbox for kinematic and UI experiments
media/ public images and videos used to illustrate development results
```

In practice, the most direct public workflow is to run a firmware target on an RP2040 board, connect it over the current devlink serial path, and inspect or record the device stream with `devlink-dashboard`.

## Repository Layout

- `firmware/`: RP2040 firmware targets, shared support code, and experimental control programs
- `tools/devlink_dashboard/`: Python package for serial monitoring, command dispatch, recording, replay, and the desktop GUI
- `software/simulation/`: Magnum-based C++ simulation/editor shell with vendored third-party dependencies
- `hardware/`: FreeCAD assemblies, KiCad projects, and board-level hardware assets
- `media/`: images and videos that illustrate assembly, calibration, and control behaviour

## Installation Instructions

### 1. Clone the repository

```bash
git clone git@github.com:aj-floater/hexapod.git
cd hexapod
```

### 2. Host tooling prerequisites

Required for `tools/devlink_dashboard/`:

- Python `>=3.11`
- `pip`
- serial support via `pyserial`
- GUI support via `PySide6` and `pyqtgraph` when using the desktop dashboard

Install the package from the repository root:

```bash
python3 -m pip install -e './tools/devlink_dashboard[gui]'
```

If you only need parser, replay, or non-GUI workflows, install the lighter serial extra instead:

```bash
python3 -m pip install -e './tools/devlink_dashboard[serial]'
```

### 3. Simulation prerequisites

Required for `software/simulation/`:

- CMake `>=3.24`
- a C++17 compiler
- a desktop OpenGL-capable environment

The simulation currently vendors its external dependencies under `software/simulation/third_party/`, so no separate package manager is required for Corrade, Magnum, SDL, ImGui, or ImGuizmo in the default workflow.

### 4. Firmware prerequisites

Required for `firmware/` work:

- Raspberry Pi Pico SDK / RP2040 toolchain
- CMake and a C/C++ compiler
- an SWD probe such as Pico Probe or a compatible CMSIS-DAP device for flashing and debugging
- UART wiring when using the current devlink path

Board-specific notes in `firmware/board.md` currently assume:

- `GP4 -> host RX`
- `GP3 -> host TX`
- shared `GND`

### 5. Hardware prerequisites

Required for `hardware/` inspection and editing:

- FreeCAD for `.FCStd` assemblies and parts
- KiCad for PCB and schematic projects

## How to Run the Software

### Host dashboard

Launch the desktop dashboard against a live serial device:

```bash
devlink-dashboard gui --port /dev/ttyACM0 --record session.jsonl
```

Other useful host workflows:

```bash
devlink-dashboard monitor --port /dev/ttyACM0 --record session.jsonl
devlink-dashboard replay session.jsonl
```

### Simulation

Configure, build, and run the current simulation shell:

```bash
cmake -S software/simulation -B software/simulation/build
cmake --build software/simulation/build
./software/simulation/build/bin/hexapod-simulation
```

### Firmware example

One simple public firmware workflow is the RP2040 blink/debug example:

```bash
cd firmware/blink_any_copy
make build
make flash
```

More advanced control targets live under `firmware/control_testing/`, `firmware/basic_control_testing/`, and related subdirectories.

## Technical Details

- The host-device protocol work is centered on `devlink`, with typed messages, NDJSON logging/replay, and capability-driven host state reconstruction in `tools/devlink_dashboard/`.
- Current firmware work targets RP2040 boards and uses a UART-based devlink transport. The public board notes document the active wiring assumptions and shared RX helper usage.
- The simulation executable is an editor-style sandbox rather than a full robot simulator. It currently focuses on a dockable viewport, scene hierarchy, gizmo manipulation, and persistence while replay and joint-domain integration remain future work.
- The simulation build intentionally vendors its major third-party dependencies under `software/simulation/third_party/` and pins them through the local CMake configuration.
- Hardware assets are maintained directly in native design formats so the repository doubles as a source tree for mechanical and PCB iteration, not only as an exported artifact store.

## Known Issues and Future Improvements

- The repository is large because it includes vendored C++ dependencies, CAD files, PCB assets, images, and captured telemetry recordings.
- Some tracked recordings and generated artifacts are large enough to trigger GitHub large-file warnings and may need Git LFS or curation later.
- The simulation scope is still limited to the editor/bootstrap phase; full replay, model import, and complete multi-joint behaviour are not finished.
- Firmware workflows are target-specific and assume local toolchain, probe, and serial environment setup rather than a single turnkey build.
- Hardware and software subsystems are evolving in parallel, so interfaces and assumptions may continue to change as the robot architecture matures.
