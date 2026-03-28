from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..messages import JSONScalar, Message, ParamSpec, SampleMessage, StreamSpec
from ..model import DashboardState, DeviceModel

RESERVED_COMMAND_NAMES = frozenset({"device.describe", "param.list", "param.get", "param.set"})


def is_numeric_value(value: JSONScalar) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def is_numeric_type(type_name: str) -> bool:
    return type_name not in {"bool", "string"}


@dataclass
class NumericSeriesHistory:
    t_us: deque[int] = field(default_factory=deque)
    values: deque[float] = field(default_factory=deque)

    def append(self, t_us: int, value: float, *, max_points: int) -> None:
        self.t_us.append(t_us)
        self.values.append(value)
        while len(self.t_us) > max_points:
            self.t_us.popleft()
            self.values.popleft()


@dataclass
class DashboardRuntime:
    history_limit: int = 2000
    raw_line_limit: int = 2000
    parse_error_limit: int = 200
    dashboard: DashboardState = field(default_factory=DashboardState)
    raw_lines: deque[str] = field(default_factory=lambda: deque(maxlen=2000))
    parse_errors: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    numeric_history: dict[tuple[str, str, str], NumericSeriesHistory] = field(default_factory=dict)
    _next_command_id: int = 1

    def __post_init__(self) -> None:
        self.raw_lines = deque(maxlen=self.raw_line_limit)
        self.parse_errors = deque(maxlen=self.parse_error_limit)

    def reset_session(self) -> None:
        self.dashboard = DashboardState()
        self.raw_lines = deque(maxlen=self.raw_line_limit)
        self.parse_errors = deque(maxlen=self.parse_error_limit)
        self.numeric_history = {}

    def record_raw_line(self, line: str) -> None:
        self.raw_lines.append(line)

    def record_parse_error(self, error: str, line: str | None = None) -> None:
        if line:
            self.parse_errors.append(f"{error} :: {line}")
        else:
            self.parse_errors.append(error)

    def allocate_command_id(self) -> int:
        command_id = self._next_command_id
        self._next_command_id += 1
        return command_id

    def apply_message(self, message: Message) -> DeviceModel:
        device_model = self.dashboard.apply(message)
        if isinstance(message, SampleMessage):
            for field_name, value in message.data.items():
                if not is_numeric_value(value):
                    continue
                key = (message.device, message.stream, field_name)
                history = self.numeric_history.setdefault(key, NumericSeriesHistory())
                history.append(message.t_us, float(value), max_points=self.history_limit)
        return device_model

    def device_names(self) -> list[str]:
        return sorted(self.dashboard.devices.keys())

    def first_device_name(self) -> str | None:
        names = self.device_names()
        if not names:
            return None
        return names[0]

    def get_device(self, device: str | None) -> DeviceModel | None:
        if device is None:
            return None
        return self.dashboard.devices.get(device)

    def param_specs_for_device(self, device: str | None) -> tuple[ParamSpec, ...]:
        model = self.get_device(device)
        if model is None or model.capabilities is None:
            return ()
        return model.capabilities.params

    def stream_specs_for_device(self, device: str | None) -> tuple[StreamSpec, ...]:
        model = self.get_device(device)
        if model is None or model.capabilities is None:
            return ()
        return model.capabilities.streams

    def command_specs_for_device(self, device: str | None, *, include_reserved: bool = False):
        model = self.get_device(device)
        if model is None or model.capabilities is None:
            return ()
        if include_reserved:
            return model.capabilities.commands
        return tuple(
            command for command in model.capabilities.commands if command.name not in RESERVED_COMMAND_NAMES
        )

    def stream_names_for_device(self, device: str | None) -> list[str]:
        model = self.get_device(device)
        if model is None:
            return []
        names = {stream.name for stream in self.stream_specs_for_device(device)}
        names.update(model.streams.keys())
        return sorted(names)

    def get_stream_spec(self, device: str | None, stream_name: str | None) -> StreamSpec | None:
        if device is None or stream_name is None:
            return None
        for stream in self.stream_specs_for_device(device):
            if stream.name == stream_name:
                return stream
        return None

    def numeric_field_names(self, device: str | None, stream_name: str | None) -> list[str]:
        if device is None or stream_name is None:
            return []

        stream_spec = self.get_stream_spec(device, stream_name)
        if stream_spec is not None:
            return [field.name for field in stream_spec.fields if is_numeric_type(field.type)]

        model = self.get_device(device)
        if model is None:
            return []
        stream_state = model.streams.get(stream_name)
        if stream_state is None:
            return []
        return [name for name, value in stream_state.last_data.items() if is_numeric_value(value)]

    def series_for_field(self, device: str | None, stream_name: str | None, field_name: str) -> tuple[list[int], list[float]]:
        if device is None or stream_name is None:
            return ([], [])
        history = self.numeric_history.get((device, stream_name, field_name))
        if history is None:
            return ([], [])
        return (list(history.t_us), list(history.values))

    def latest_stream_values(self, device: str | None, stream_name: str | None) -> dict[str, JSONScalar]:
        model = self.get_device(device)
        if model is None or stream_name is None:
            return {}
        stream_state = model.streams.get(stream_name)
        if stream_state is None:
            return {}
        return dict(stream_state.last_data)
