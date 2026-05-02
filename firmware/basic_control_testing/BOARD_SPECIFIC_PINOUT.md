# Board-Specific Pico Pinout

This note reflects the wiring used on this specific board and test setup. It does not use the shared/common pin header.

- `GP2`, `GP3`, `GP5`, `GP6`: external LEDs
- `GP9`, `GP10`: buttons, with the other side tied to `GND` so they are active-low when configured with pull-ups
- `GP16`, `GP17`, `GP18`: servo signal pins
- `GP25`: onboard Pico LED
- `GP26`, `GP27`, `GP28`: analog inputs (`ADC0`, `ADC1`, `ADC2`)

Wiring notes:

- The external LEDs are connected to ground through series resistors.
- The servo entries above are signal pins only.
- The analog inputs above are the three measured analog signals.
- For the previously tested "360 degree" servos on this board, the empirically usable pulse range was about `1250-1750 us`.
- On that setup, the usable positional range was about `0-50 degrees`, with `25 degrees` used as a midpoint hold test.

Measured servo/ADC mapping from captured sweep:

- Servo `A` on `GP16` maps to `ADCA` on `GP26`
- Servo `B` on `GP17` maps to `ADCB` on `GP27`
- Servo `C` on `GP18` maps to `ADCC` on `GP28`

Measured angle-to-ADC calibration points:

| Driven angle | Servo A / ADCA | Servo B / ADCB | Servo C / ADCC |
|---|---:|---:|---:|
| `0 deg` | `2575` | `2569` | `2584` |
| `10 deg` | `2413` | `2397` | `2420` |
| `20 deg` | `2207` | `2196` | `2216` |
| `30 deg` | `1999` | `1988` | `2012` |
| `40 deg` | `1803` | `1785` | `1813` |
| `50 deg` | `1592` | `1581` | `1609` |

Approximate inverse mappings from ADC reading to measured angle:

- Servo `A`: `angle_deg ~= clamp((2595 - ADCA) / 19.87, 0, 50)`
- Servo `B`: `angle_deg ~= clamp((2585 - ADCB) / 19.95, 0, 50)`
- Servo `C`: `angle_deg ~= clamp((2602 - ADCC) / 19.71, 0, 50)`

For better accuracy, use the calibration table above with linear interpolation between adjacent points instead of relying only on the simple formulas.
