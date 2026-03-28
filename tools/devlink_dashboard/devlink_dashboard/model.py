from __future__ import annotations

from dataclasses import dataclass, field

from .messages import (
    CapabilitiesMessage,
    EventMessage,
    HelloMessage,
    JSONScalar,
    LogMessage,
    Message,
    RespMessage,
    SampleMessage,
)


@dataclass
class StreamState:
    name: str
    last_seq: int | None = None
    last_t_us: int | None = None
    last_data: dict[str, JSONScalar] = field(default_factory=dict)
    sample_count: int = 0


@dataclass
class DeviceModel:
    device: str
    hello: HelloMessage | None = None
    capabilities: CapabilitiesMessage | None = None
    params: dict[str, JSONScalar] = field(default_factory=dict)
    streams: dict[str, StreamState] = field(default_factory=dict)
    events: list[EventMessage] = field(default_factory=list)
    logs: list[LogMessage] = field(default_factory=list)
    responses: list[RespMessage] = field(default_factory=list)
    last_message: Message | None = None

    def apply(self, message: Message) -> None:
        self.last_message = message

        if isinstance(message, HelloMessage):
            self.hello = message
            return

        if isinstance(message, CapabilitiesMessage):
            self.capabilities = message
            for param in message.params:
                self.params.setdefault(param.name, param.default)
            return

        if isinstance(message, RespMessage):
            self.responses.append(message)
            self._apply_response(message)
            return

        if isinstance(message, SampleMessage):
            stream_state = self.streams.setdefault(message.stream, StreamState(name=message.stream))
            stream_state.last_seq = message.seq
            stream_state.last_t_us = message.t_us
            stream_state.last_data = dict(message.data)
            stream_state.sample_count += 1
            return

        if isinstance(message, EventMessage):
            self.events.append(message)
            return

        if isinstance(message, LogMessage):
            self.logs.append(message)
            return

    def _apply_response(self, response: RespMessage) -> None:
        if not response.ok or response.result is None:
            return

        result = response.result
        if isinstance(result.get("param"), str) and "value" in result:
            self.params[result["param"]] = result["value"]
            return

        params = result.get("params")
        if not isinstance(params, list):
            return

        for item in params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and "value" in item:
                self.params[name] = item["value"]


@dataclass
class DashboardState:
    devices: dict[str, DeviceModel] = field(default_factory=dict)

    def apply(self, message: Message) -> DeviceModel:
        device_model = self.devices.setdefault(message.device, DeviceModel(device=message.device))
        device_model.apply(message)
        return device_model
