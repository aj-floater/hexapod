# Board Quirks

- `devlink` currently uses UART, not USB CDC. The board transmits on `GP4`, receives commands on `GP3`, and needs a shared `GND`.
- For the current firmware targets, wire `GP4 -> host RX` and `GP3 -> host TX`. `leg` and `status_led_demo` now use the same mapping.
- Command RX should use the shared PIO UART helper in `firmware/common/pio_uart_rx.*`. Plain stdio RX via `getchar_timeout_us()` was unreliable once the device was continuously streaming samples.
- A fresh target that wants `devlink` command RX should enable both helpers in CMake:
  - `devlink_serial_enable_for_target(<target>)`
  - `devlink_pio_uart_rx_enable_for_target(<target>)`
- `devlink-dashboard send` may print one parse error when it opens a streaming port mid-line. If RX wiring is correct, the real `resp` should still arrive immediately after.
