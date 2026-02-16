# PIO UART RX (GPIO3) for Command Input

## Why this exists

This board routes command RX to `GPIO3`. RP2040 hardware UART RX is not available on that pin, so command input is implemented with PIO.

TX output (logs/telemetry) still uses stdio UART on `GPIO4`.

## Files

- `uart_rx.pio`
  - PIO program that samples 8N1 UART frames.
- `pio_uart_rx.h` / `pio_uart_rx.c`
  - Small driver wrapper for init and non-blocking byte reads.
- `leg.c`
  - Uses PIO RX bytes to build command lines and run open-loop test commands.
- `CMakeLists.txt`
  - Generates PIO header and links `hardware_pio`.

## Runtime path

1. `pio_uart_rx_init(...)` starts a PIO state machine on `GPIO3` at `115200`.
2. Main loop calls `pio_uart_rx_try_getc(...)` (non-blocking).
3. Received bytes feed the existing command-line parser.
4. Valid commands trigger open-loop test execution.

## Wiring expectations

- Probe `TX` -> target `GPIO3` (PIO RX input)
- Probe `RX` -> target `GPIO4` (stdio UART TX output)
- Probe `GND` -> target `GND`
- Baud: `115200`

## Commands

- `S`
  - Runs default test (`60%`, `2000 ms`, forward)
- `START,40,1500,F`
  - Comma-separated format
- `START 40 1500 F`
  - Space-separated format

## Expected serial sequence

1. `READY: ...`
2. `RX: ...`
3. `ACK: ...`
4. Plot lines: `ref_step_adc`, `adc_c_raw`, `ref_pwm_pct`, `t_ms`
5. `DONE`
