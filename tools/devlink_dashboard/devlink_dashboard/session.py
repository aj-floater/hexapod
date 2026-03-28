from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .messages import Message, parse_line, serialize_message


class JsonlRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def record_line(self, line: str) -> None:
        payload = line.rstrip("\r\n")
        self._handle.write(payload)
        self._handle.write("\n")
        self._handle.flush()

    def record_message(self, message: Message) -> None:
        self.record_line(serialize_message(message))

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "JsonlRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def iter_recorded_lines(path: str | Path) -> Iterator[str]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield line


def iter_recorded_messages(path: str | Path) -> Iterator[Message]:
    for line in iter_recorded_lines(path):
        yield parse_line(line)
