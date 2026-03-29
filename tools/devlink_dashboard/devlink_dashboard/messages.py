from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping, TypeAlias

PROTOCOL_NAME = "devlink"
PROTOCOL_VERSION = 1

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ProtocolError(ValueError):
    pass


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _ensure_json_value(value: object, path: str) -> JSONValue:
    if _is_scalar(value):
        return value
    if isinstance(value, list):
        return [_ensure_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, dict):
        converted: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolError(f"{path} keys must be strings")
            converted[key] = _ensure_json_value(item, f"{path}.{key}")
        return converted
    raise ProtocolError(f"{path} is not JSON-compatible")


def _require_mapping(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{key} must be an object")
    return value


def _require_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ProtocolError(f"{key} must be a string")
    return value


def _require_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{key} must be an integer")
    return value


def _require_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ProtocolError(f"{key} must be a boolean")
    return value


def _require_list(data: Mapping[str, object], key: str) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ProtocolError(f"{key} must be a list")
    return value


def _optional_mapping(data: Mapping[str, object], key: str) -> Mapping[str, JSONValue] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{key} must be an object")
    return {str(k): _ensure_json_value(v, f"{key}.{k}") for k, v in value.items()}


@dataclass(frozen=True)
class CommandArgSpec:
    name: str
    type: str
    required: bool


@dataclass(frozen=True)
class CommandSpec:
    name: str
    args: tuple[CommandArgSpec, ...]


@dataclass(frozen=True)
class StreamFieldSpec:
    name: str
    type: str
    unit: str


@dataclass(frozen=True)
class StreamSpec:
    name: str
    fields: tuple[StreamFieldSpec, ...]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    access: str
    default: JSONScalar
    min: int | float | None = None
    max: int | float | None = None


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str


@dataclass(frozen=True)
class HelloMessage:
    version: int
    device: str
    protocol: str
    firmware: str
    type: str = field(init=False, default="hello")


@dataclass(frozen=True)
class CapabilitiesMessage:
    version: int
    device: str
    commands: tuple[CommandSpec, ...]
    streams: tuple[StreamSpec, ...]
    params: tuple[ParamSpec, ...]
    type: str = field(init=False, default="capabilities")


@dataclass(frozen=True)
class CmdMessage:
    version: int
    device: str
    id: int
    name: str
    args: Mapping[str, JSONValue]
    type: str = field(init=False, default="cmd")


@dataclass(frozen=True)
class RespMessage:
    version: int
    device: str
    id: int
    ok: bool
    result: Mapping[str, JSONValue] | None = None
    error: ErrorInfo | None = None
    type: str = field(init=False, default="resp")


@dataclass(frozen=True)
class EventMessage:
    version: int
    device: str
    name: str
    severity: str
    data: Mapping[str, JSONValue] | None = None
    type: str = field(init=False, default="event")


@dataclass(frozen=True)
class SampleMessage:
    version: int
    device: str
    stream: str
    seq: int
    t_us: int
    data: Mapping[str, JSONScalar]
    type: str = field(init=False, default="sample")


@dataclass(frozen=True)
class LogMessage:
    version: int
    device: str
    level: str
    msg: str
    type: str = field(init=False, default="log")


Message: TypeAlias = (
    HelloMessage
    | CapabilitiesMessage
    | CmdMessage
    | RespMessage
    | EventMessage
    | SampleMessage
    | LogMessage
)


def parse_line_resilient(line: str | bytes) -> Message:
    if isinstance(line, bytes):
        text = line.decode("utf-8", errors="replace")
    else:
        text = line

    try:
        return parse_line(text)
    except ProtocolError as original_error:
        cleaned = text.replace("\x00", "").strip()
        if cleaned and cleaned != text.strip():
            try:
                return parse_line(cleaned)
            except ProtocolError:
                pass

        search_start = 0
        while True:
            candidate_index = cleaned.find('{"type"', search_start)
            if candidate_index < 0:
                break
            if candidate_index > 0:
                candidate = cleaned[candidate_index:]
                try:
                    return parse_line(candidate)
                except ProtocolError:
                    pass
            search_start = candidate_index + 1

        raise original_error


def _parse_command_arg_spec(raw: object) -> CommandArgSpec:
    if not isinstance(raw, Mapping):
        raise ProtocolError("command arg spec must be an object")
    return CommandArgSpec(
        name=_require_str(raw, "name"),
        type=_require_str(raw, "type"),
        required=_require_bool(raw, "required"),
    )


def _parse_command_spec(raw: object) -> CommandSpec:
    if not isinstance(raw, Mapping):
        raise ProtocolError("command spec must be an object")
    return CommandSpec(
        name=_require_str(raw, "name"),
        args=tuple(_parse_command_arg_spec(item) for item in _require_list(raw, "args")),
    )


def _parse_stream_field_spec(raw: object) -> StreamFieldSpec:
    if not isinstance(raw, Mapping):
        raise ProtocolError("stream field spec must be an object")
    return StreamFieldSpec(
        name=_require_str(raw, "name"),
        type=_require_str(raw, "type"),
        unit=_require_str(raw, "unit"),
    )


def _parse_stream_spec(raw: object) -> StreamSpec:
    if not isinstance(raw, Mapping):
        raise ProtocolError("stream spec must be an object")
    return StreamSpec(
        name=_require_str(raw, "name"),
        fields=tuple(_parse_stream_field_spec(item) for item in _require_list(raw, "fields")),
    )


def _parse_param_spec(raw: object) -> ParamSpec:
    if not isinstance(raw, Mapping):
        raise ProtocolError("param spec must be an object")
    default = raw.get("default")
    if not _is_scalar(default):
        raise ProtocolError("param default must be a scalar")
    min_value = raw.get("min")
    max_value = raw.get("max")
    if min_value is not None and (isinstance(min_value, bool) or not isinstance(min_value, (int, float))):
        raise ProtocolError("param min must be numeric")
    if max_value is not None and (isinstance(max_value, bool) or not isinstance(max_value, (int, float))):
        raise ProtocolError("param max must be numeric")
    return ParamSpec(
        name=_require_str(raw, "name"),
        type=_require_str(raw, "type"),
        access=_require_str(raw, "access"),
        default=default,
        min=min_value,
        max=max_value,
    )


def build_cmd_message(device: str, command_id: int, name: str, args: Mapping[str, JSONValue] | None = None) -> CmdMessage:
    normalized_args = {} if args is None else {key: _ensure_json_value(value, f"args.{key}") for key, value in args.items()}
    return CmdMessage(
        version=PROTOCOL_VERSION,
        device=device,
        id=command_id,
        name=name,
        args=normalized_args,
    )


def parse_line(line: str | bytes) -> Message:
    if isinstance(line, bytes):
        line = line.decode("utf-8")

    text = line.strip()
    if not text:
        raise ProtocolError("empty line")

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(str(exc)) from exc
    if not isinstance(raw, Mapping):
        raise ProtocolError("message must be a JSON object")

    message_type = _require_str(raw, "type")
    version = _require_int(raw, "version")
    device = _require_str(raw, "device")

    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version {version}")

    if message_type == "hello":
        protocol = _require_str(raw, "protocol")
        firmware = _require_str(raw, "firmware")
        if protocol != PROTOCOL_NAME:
            raise ProtocolError(f"unexpected protocol {protocol}")
        return HelloMessage(version=version, device=device, protocol=protocol, firmware=firmware)

    if message_type == "capabilities":
        return CapabilitiesMessage(
            version=version,
            device=device,
            commands=tuple(_parse_command_spec(item) for item in _require_list(raw, "commands")),
            streams=tuple(_parse_stream_spec(item) for item in _require_list(raw, "streams")),
            params=tuple(_parse_param_spec(item) for item in _require_list(raw, "params")),
        )

    if message_type == "cmd":
        args = _require_mapping(raw, "args")
        normalized_args = {str(k): _ensure_json_value(v, f"args.{k}") for k, v in args.items()}
        return CmdMessage(
            version=version,
            device=device,
            id=_require_int(raw, "id"),
            name=_require_str(raw, "name"),
            args=normalized_args,
        )

    if message_type == "resp":
        ok = _require_bool(raw, "ok")
        result = _optional_mapping(raw, "result")
        error = None
        if "error" in raw and raw["error"] is not None:
            error_mapping = _require_mapping(raw, "error")
            error = ErrorInfo(
                code=_require_str(error_mapping, "code"),
                message=_require_str(error_mapping, "message"),
            )
        if not ok and error is None:
            raise ProtocolError("resp.error is required when ok is false")
        return RespMessage(
            version=version,
            device=device,
            id=_require_int(raw, "id"),
            ok=ok,
            result=result,
            error=error,
        )

    if message_type == "event":
        return EventMessage(
            version=version,
            device=device,
            name=_require_str(raw, "name"),
            severity=_require_str(raw, "severity"),
            data=_optional_mapping(raw, "data"),
        )

    if message_type == "sample":
        data = _require_mapping(raw, "data")
        sample_data: dict[str, JSONScalar] = {}
        for key, value in data.items():
            if not _is_scalar(value):
                raise ProtocolError(f"sample.data.{key} must be a scalar")
            sample_data[str(key)] = value
        return SampleMessage(
            version=version,
            device=device,
            stream=_require_str(raw, "stream"),
            seq=_require_int(raw, "seq"),
            t_us=_require_int(raw, "t_us"),
            data=sample_data,
        )

    if message_type == "log":
        return LogMessage(
            version=version,
            device=device,
            level=_require_str(raw, "level"),
            msg=_require_str(raw, "msg"),
        )

    raise ProtocolError(f"unknown message type {message_type}")


def _command_arg_to_dict(spec: CommandArgSpec) -> dict[str, JSONValue]:
    return {"name": spec.name, "type": spec.type, "required": spec.required}


def _command_spec_to_dict(spec: CommandSpec) -> dict[str, JSONValue]:
    return {"name": spec.name, "args": [_command_arg_to_dict(arg) for arg in spec.args]}


def _stream_field_to_dict(field_spec: StreamFieldSpec) -> dict[str, JSONValue]:
    return {"name": field_spec.name, "type": field_spec.type, "unit": field_spec.unit}


def _stream_spec_to_dict(spec: StreamSpec) -> dict[str, JSONValue]:
    return {"name": spec.name, "fields": [_stream_field_to_dict(field) for field in spec.fields]}


def _param_spec_to_dict(spec: ParamSpec) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "name": spec.name,
        "type": spec.type,
        "access": spec.access,
        "default": spec.default,
    }
    if spec.min is not None:
        payload["min"] = spec.min
    if spec.max is not None:
        payload["max"] = spec.max
    return payload


def message_to_dict(message: Message) -> dict[str, JSONValue]:
    if isinstance(message, HelloMessage):
        return {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "protocol": message.protocol,
            "firmware": message.firmware,
        }

    if isinstance(message, CapabilitiesMessage):
        return {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "commands": [_command_spec_to_dict(spec) for spec in message.commands],
            "streams": [_stream_spec_to_dict(spec) for spec in message.streams],
            "params": [_param_spec_to_dict(spec) for spec in message.params],
        }

    if isinstance(message, CmdMessage):
        return {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "id": message.id,
            "name": message.name,
            "args": dict(message.args),
        }

    if isinstance(message, RespMessage):
        payload: dict[str, JSONValue] = {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "id": message.id,
            "ok": message.ok,
        }
        if message.result is not None:
            payload["result"] = dict(message.result)
        if message.error is not None:
            payload["error"] = {"code": message.error.code, "message": message.error.message}
        return payload

    if isinstance(message, EventMessage):
        payload = {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "name": message.name,
            "severity": message.severity,
        }
        if message.data is not None:
            payload["data"] = dict(message.data)
        return payload

    if isinstance(message, SampleMessage):
        return {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "stream": message.stream,
            "seq": message.seq,
            "t_us": message.t_us,
            "data": dict(message.data),
        }

    if isinstance(message, LogMessage):
        return {
            "type": message.type,
            "version": message.version,
            "device": message.device,
            "level": message.level,
            "msg": message.msg,
        }

    raise TypeError(f"unsupported message {type(message)!r}")


def serialize_message(message: Message) -> str:
    return json.dumps(message_to_dict(message), separators=(",", ":"), sort_keys=False)
