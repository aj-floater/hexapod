from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .messages import Message

Subscriber = Callable[[Message], None]


class MessageBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, callback: Subscriber, message_type: str | None = None) -> None:
        key = "*" if message_type is None else message_type
        self._subscribers[key].append(callback)

    def publish(self, message: Message) -> None:
        for callback in self._subscribers["*"]:
            callback(message)
        for callback in self._subscribers[message.type]:
            callback(message)
