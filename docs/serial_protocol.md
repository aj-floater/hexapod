# Hexapod Serial Protocol v1

`hexapod.serial` is the canonical UART-first protocol for firmware targets in this repository.

Version `1` uses UTF-8 newline-delimited JSON (`NDJSON`):

- Each message is exactly one JSON object.
- Each message ends with `\n` or `\r\n`.
- Messages must fit inside the target's fixed-size receive buffer.
- Human-readable logs may be emitted, but host correctness must not depend on them.

## Transport Model

- One device per serial port.
- Every message still includes a `device` field so recordings remain unambiguous.
- Target-local Markdown is not protocol source of truth; this document is.

## Common Envelope

Every message must include:

- `type`: message family
- `version`: protocol version, fixed to integer `1`
- `device`: stable device identifier, for example `leg`

## Message Families

### `hello`

Emitted once on boot or reconnect.

```json
{"type":"hello","version":1,"device":"leg","protocol":"hexapod.serial","firmware":"0.1.0"}
```

Fields:

- `protocol`: fixed string `hexapod.serial`
- `firmware`: firmware identifier or version string

### `capabilities`

Emitted after `hello`. Declares commands, telemetry streams, and parameters so a generic host can inspect the device.

```json
{
  "type":"capabilities",
  "version":1,
  "device":"leg",
  "commands":[
    {"name":"demo.start","args":[]},
    {"name":"demo.stop","args":[]},
    {"name":"param.list","args":[]},
    {"name":"param.get","args":[{"name":"param","type":"string","required":true}]},
    {"name":"param.set","args":[
      {"name":"param","type":"string","required":true},
      {"name":"value","type":"integer","required":true}
    ]}
  ],
  "streams":[
    {
      "name":"leg.position",
      "fields":[
        {"name":"setpoint_adc","type":"u16","unit":"adc"},
        {"name":"measured_adc","type":"u16","unit":"adc"},
        {"name":"control_output_pct","type":"i16","unit":"pct"}
      ]
    }
  ],
  "params":[
    {"name":"control.setpoint_adc","type":"u16","access":"rw","default":2600,"min":0,"max":4095},
    {"name":"control.deadband_adc","type":"u16","access":"rw","default":60,"min":0,"max":4095},
    {"name":"control.min_output_pct","type":"u8","access":"rw","default":20,"min":0,"max":100},
    {"name":"control.max_output_pct","type":"u8","access":"rw","default":60,"min":0,"max":100},
    {"name":"control.error_to_output_divisor","type":"u16","access":"rw","default":16,"min":1,"max":4095}
  ]
}
```

### `cmd`

Host-to-device command. Every `cmd` must produce exactly one `resp`.

```json
{"type":"cmd","version":1,"device":"leg","id":7,"name":"demo.start","args":{}}
{"type":"cmd","version":1,"device":"leg","id":8,"name":"param.get","args":{"param":"control.setpoint_adc"}}
{"type":"cmd","version":1,"device":"leg","id":9,"name":"param.set","args":{"param":"control.setpoint_adc","value":2450}}
```

Fields:

- `id`: integer request identifier
- `name`: stable dotted command name
- `args`: JSON object, empty if no arguments

### `resp`

Reply to exactly one `cmd`.

```json
{"type":"resp","version":1,"device":"leg","id":7,"ok":true}
{"type":"resp","version":1,"device":"leg","id":8,"ok":true,"result":{"param":"control.setpoint_adc","value":2600}}
{"type":"resp","version":1,"device":"leg","id":9,"ok":false,"error":{"code":"value_out_of_range","message":"param value outside allowed range"}}
```

Fields:

- `id`: request identifier from `cmd`
- `ok`: boolean success flag
- `result`: optional JSON object on success
- `error`: optional JSON object on failure with:
  - `code`: machine-readable error code
  - `message`: short operator-readable text

### `event`

Asynchronous state or fault notification.

```json
{"type":"event","version":1,"device":"leg","name":"device.ready","severity":"info"}
{"type":"event","version":1,"device":"leg","name":"demo.started","severity":"info"}
{"type":"event","version":1,"device":"leg","name":"demo.done","severity":"info"}
{"type":"event","version":1,"device":"leg","name":"protocol.invalid_json","severity":"error"}
```

Fields:

- `name`: dotted event name
- `severity`: `debug`, `info`, `warn`, or `error`
- `data`: optional JSON object with additional details

### `sample`

Telemetry sample for a named stream.

```json
{"type":"sample","version":1,"device":"leg","stream":"leg.position","seq":42,"t_us":1876543,"data":{"setpoint_adc":2600,"measured_adc":2412,"control_output_pct":34}}
```

Fields:

- `stream`: stable stream name
- `seq`: per-stream or per-session monotonically increasing integer
- `t_us`: device timestamp in microseconds
- `data`: JSON object containing the fields declared in `capabilities.streams`

### `log`

Human-readable text. Hosts may display or record these lines, but must not depend on them for behavior.

```json
{"type":"log","version":1,"device":"leg","level":"info","msg":"pio rx initialized"}
```

Fields:

- `level`: `debug`, `info`, `warn`, or `error`
- `msg`: short human-readable text

## Naming Rules

- Commands use dotted verbs, for example `demo.start`, `param.get`, `param.set`.
- Streams use dotted nouns, for example `leg.position`.
- Params use dotted names, for example `control.deadband_adc`.
- Event names use dotted names, for example `device.ready`, `demo.done`.

## Error Handling

- Unknown command names return `resp.ok=false` with `error.code="unknown_command"`.
- Missing required arguments return `error.code="invalid_args"`.
- Unknown parameters return `error.code="unknown_param"`.
- Rejected values return `error.code="value_out_of_range"`.
- Malformed or oversized lines may not have a usable command `id`; they should be surfaced as `event` or `log` messages such as `protocol.invalid_json` or `protocol.line_too_long`.

## Host Guidance

- Hosts should record raw NDJSON lines verbatim and parse them later.
- Hosts should auto-build generic plots from `capabilities.streams` and numeric `sample.data` fields.
- Hosts should treat `capabilities` as the schema source and `resp` messages as the mutable state source for parameters.

## v1 Reference Target

`firmware/leg` is the first v1 adopter:

- `demo.start` and `demo.stop` control the existing position-hold demo.
- `leg.position` exposes `setpoint_adc`, `measured_adc`, and `control_output_pct`.
- Parameter support covers the current control tuning values:
  - `control.setpoint_adc`
  - `control.deadband_adc`
  - `control.min_output_pct`
  - `control.max_output_pct`
  - `control.error_to_output_divisor`
