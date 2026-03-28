from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .messages import (
    CmdMessage,
    EventMessage,
    LogMessage,
    Message,
    ProtocolError,
    RespMessage,
    SampleMessage,
    build_cmd_message,
    parse_line,
)
from .model import DashboardState
from .session import JsonlRecorder, iter_recorded_messages
from .transport import SerialPump, SerialTransport, SerialUnavailableError


def _format_message(message: Message) -> str:
    if isinstance(message, SampleMessage):
        return f"[sample] {message.device} {message.stream} seq={message.seq} data={dict(message.data)}"
    if isinstance(message, RespMessage):
        if message.ok:
            suffix = "" if message.result is None else f" result={dict(message.result)}"
            return f"[resp] {message.device} id={message.id} ok{suffix}"
        return f"[resp] {message.device} id={message.id} error={message.error.code if message.error else 'unknown'}"
    if isinstance(message, EventMessage):
        return f"[event] {message.device} {message.severity} {message.name}"
    if isinstance(message, LogMessage):
        return f"[log] {message.device} {message.level} {message.msg}"
    return f"[{message.type}] {message.device}"


def _parse_args_json(raw_args: str | None) -> dict[str, object]:
    if raw_args is None:
        return {}
    data = json.loads(raw_args)
    if not isinstance(data, dict):
        raise ProtocolError("--args must decode to a JSON object")
    return data


def _run_monitor(args: argparse.Namespace) -> int:
    dashboard = DashboardState()
    recorder = JsonlRecorder(args.record) if args.record else None
    try:
        with SerialTransport(args.port, baud=args.baud, timeout=args.timeout) as transport:
            pump = SerialPump(transport=transport, recorder=recorder)
            while True:
                try:
                    message = pump.pump_once()
                except ProtocolError as exc:
                    print(f"[parse-error] {exc}")
                    continue
                if message is None:
                    continue
                dashboard.apply(message)
                print(_format_message(message))
        return 0
    except SerialUnavailableError as exc:
        print(exc)
        return 2
    except KeyboardInterrupt:
        return 0
    finally:
        if recorder is not None:
            recorder.close()


def _run_send(args: argparse.Namespace) -> int:
    try:
        payload = _parse_args_json(args.args)
    except (json.JSONDecodeError, ProtocolError) as exc:
        print(f"invalid args payload: {exc}")
        return 2

    message: CmdMessage = build_cmd_message(
        device=args.device,
        command_id=args.id,
        name=args.name,
        args=payload,
    )

    try:
        with SerialTransport(args.port, baud=args.baud, timeout=args.timeout) as transport:
            transport.send_message(message)
            if args.wait <= 0:
                return 0

            deadline = time.monotonic() + args.wait
            while time.monotonic() < deadline:
                line = transport.readline()
                if line is None or line == "":
                    continue
                try:
                    parsed = parse_line(line)
                except ProtocolError as exc:
                    print(f"[parse-error] {exc}")
                    continue
                print(_format_message(parsed))
                if isinstance(parsed, RespMessage) and parsed.id == args.id:
                    return 0 if parsed.ok else 1
            print("timeout waiting for response")
            return 1
    except SerialUnavailableError as exc:
        print(exc)
        return 2


def _run_replay(args: argparse.Namespace) -> int:
    dashboard = DashboardState()
    for message in iter_recorded_messages(Path(args.path)):
        dashboard.apply(message)
        if not args.summary_only:
            print(_format_message(message))

    if args.summary_only:
        for device, model in dashboard.devices.items():
            print(
                f"{device}: samples={sum(stream.sample_count for stream in model.streams.values())} "
                f"params={len(model.params)} events={len(model.events)} logs={len(model.logs)}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hexapod-dashboard")
    subparsers = parser.add_subparsers(dest="command", required=True)

    monitor = subparsers.add_parser("monitor", help="monitor a live serial device")
    monitor.add_argument("--port", required=True)
    monitor.add_argument("--baud", type=int, default=115200)
    monitor.add_argument("--timeout", type=float, default=0.1)
    monitor.add_argument("--record")
    monitor.set_defaults(func=_run_monitor)

    send = subparsers.add_parser("send", help="send a command to a live serial device")
    send.add_argument("--port", required=True)
    send.add_argument("--baud", type=int, default=115200)
    send.add_argument("--timeout", type=float, default=0.1)
    send.add_argument("--device", required=True)
    send.add_argument("--id", required=True, type=int)
    send.add_argument("--name", required=True)
    send.add_argument("--args")
    send.add_argument("--wait", type=float, default=1.0)
    send.set_defaults(func=_run_send)

    replay = subparsers.add_parser("replay", help="replay a recorded JSONL session")
    replay.add_argument("path")
    replay.add_argument("--summary-only", action="store_true")
    replay.set_defaults(func=_run_replay)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
