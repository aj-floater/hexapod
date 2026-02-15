# blink_any_copy

RP2040 blink example configured for Pico Probe development flow.

## Pico Probe wiring

- Probe `SWCLK` -> target `SWCLK`
- Probe `SWDIO` -> target `SWDIO`
- Probe `GND` -> target `GND`
- Optional serial (for UART logs): probe `TX` -> target UART `RX`, and probe `RX` -> target UART `TX`.

## Build / flash / debug

From this directory:

```sh
make check
make build
make flash
make debug
```

or with `just`:

```sh
just check
just build
just flash
just debug
```

## Neovim debugging (nvim-dap)

This folder now includes project-local DAP config:

- `.nvim.lua`
- `.nvim/dap-rp2040.lua`

Prerequisites:

- `nvim-dap` plugin installed.
- Enable local config loading in Neovim:
  - add `set exrc` to your init file.

Workflow:

1. In terminal A, from this folder run `make openocd`.
2. In terminal B, from this folder run `make build`.
3. Open Neovim in this folder.
4. Start debug with `<F5>`.

Keymaps provided:

- `<F5>` continue/start
- `<F10>` step over
- `<F11>` step into
- `<F12>` step out
- `<Leader>db` toggle breakpoint
- `<Leader>dr` open DAP REPL
- `<Leader>dt` terminate session

## Notes

- Defaults assume the Raspberry Pi Pico VS Code toolchain layout in `~/.pico-sdk`.
- If your tools are elsewhere, override variables like `OPENOCD_BIN`, `OPENOCD_SCRIPTS`, `GDB_BIN`, `CMAKE_BIN`.
- OpenOCD interface defaults to `interface/cmsis-dap.cfg` for Pico Probe firmware.
- SWD clock defaults to `OPENOCD_ADAPTER_SPEED=5000` (kHz). Override if needed, for example:
  `make flash OPENOCD_ADAPTER_SPEED=2000`.

## If flash fails with `libusb initialization failed`

- That error means OpenOCD cannot access USB from the current environment.
- On this machine, udev is already configured in `/etc/udev/rules.d/99-raspberrypi-debugprobe.rules`.
- Run `make flash` from your normal host terminal (not a restricted sandbox/container session).
