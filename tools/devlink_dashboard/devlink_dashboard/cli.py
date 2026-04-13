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
    parse_line_resilient,
)
from .model import DashboardState
from .session import JsonlRecorder, iter_recorded_messages
from .transport import SerialPump, SerialTransport, SerialUnavailableError


def _is_ignorable_parse_error(error_text: str) -> bool:
    return (
        error_text.startswith("unknown binary stream id")
        or error_text == "binary sample frame too short"
    )


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
                if line is None or line == b"":
                    continue
                try:
                    parsed = parse_line_resilient(line)
                except ProtocolError as exc:
                    error_text = str(exc)
                    if _is_ignorable_parse_error(error_text):
                        continue
                    print(f"[parse-error] {error_text}")
                    continue
                print(_format_message(parsed))
                if isinstance(parsed, RespMessage) and parsed.id == args.id:
                    return 0 if parsed.ok else 1
            print("timeout waiting for response")
            return 1
    except SerialUnavailableError as exc:
        print(exc)
        return 2


def _run_diag(args: argparse.Namespace) -> int:
    describe_command_id = args.id_base
    next_command_id = describe_command_id + 1
    latencies_ms: list[float] = []
    timeout_count = 0
    command_error_count = 0
    parse_error_count = 0
    sample_count = 0
    seen_hello = False
    seen_capabilities = False
    describe_ok = False

    def pump_until(deadline: float) -> tuple[Message | None, bool]:
        nonlocal parse_error_count
        nonlocal sample_count

        while time.monotonic() < deadline:
            line = transport.readline()
            if line is None or line == b"":
                continue
            try:
                parsed = parse_line_resilient(line)
            except ProtocolError as exc:
                error_text = str(exc)
                if _is_ignorable_parse_error(error_text):
                    continue
                parse_error_count += 1
                print(f"[parse-error] {error_text}")
                continue
            if isinstance(parsed, SampleMessage):
                sample_count += 1
            return parsed, True
        return None, False

    try:
        with SerialTransport(args.port, baud=args.baud, timeout=args.timeout) as transport:
            describe_message: CmdMessage = build_cmd_message(
                device="*",
                command_id=describe_command_id,
                name="device.describe",
                args={},
            )
            transport.send_message(describe_message)

            describe_deadline = time.monotonic() + args.describe_wait
            while True:
                parsed, have_message = pump_until(describe_deadline)
                if not have_message:
                    break
                print(_format_message(parsed))
                if parsed.type == "hello":
                    seen_hello = True
                elif parsed.type == "capabilities":
                    seen_capabilities = True
                elif isinstance(parsed, RespMessage) and parsed.id == describe_command_id:
                    describe_ok = parsed.ok

                if seen_hello and seen_capabilities and describe_ok:
                    break

            print(
                "[diag] describe "
                f"hello={seen_hello} capabilities={seen_capabilities} ok={describe_ok}"
            )

            for _ in range(args.iterations):
                command_id = next_command_id
                next_command_id += 1
                command_message: CmdMessage = build_cmd_message(
                    device=args.device,
                    command_id=command_id,
                    name="param.get",
                    args={"param": args.param},
                )
                send_started = time.monotonic()
                transport.send_message(command_message)
                command_deadline = send_started + args.wait
                matched = False

                while True:
                    parsed, have_message = pump_until(command_deadline)
                    if not have_message:
                        break
                    if isinstance(parsed, RespMessage) and parsed.id == command_id:
                        matched = True
                        if parsed.ok:
                            latencies_ms.append((time.monotonic() - send_started) * 1000.0)
                        else:
                            command_error_count += 1
                        break

                if not matched:
                    timeout_count += 1

    except SerialUnavailableError as exc:
        print(exc)
        return 2

    success_count = len(latencies_ms)
    latency_avg_ms = (sum(latencies_ms) / success_count) if success_count > 0 else 0.0
    latency_min_ms = min(latencies_ms) if success_count > 0 else 0.0
    latency_max_ms = max(latencies_ms) if success_count > 0 else 0.0

    print(
        "[diag] summary "
        f"describe_ok={seen_hello and seen_capabilities and describe_ok} "
        f"param_get_success={success_count}/{args.iterations} "
        f"timeouts={timeout_count} errors={command_error_count} "
        f"parse_errors={parse_error_count} samples_seen={sample_count}"
    )
    if success_count > 0:
        print(
            "[diag] latency_ms "
            f"min={latency_min_ms:.1f} avg={latency_avg_ms:.1f} max={latency_max_ms:.1f}"
        )

    if seen_hello and seen_capabilities and describe_ok and timeout_count == 0 and command_error_count == 0:
        return 0
    return 1


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


def _run_gui(args: argparse.Namespace) -> int:
    from .gui.app import run_gui

    return run_gui(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devlink-dashboard")
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

    diag = subparsers.add_parser("diag", help="run command/parameter reliability diagnostics")
    diag.add_argument("--port", required=True)
    diag.add_argument("--baud", type=int, default=115200)
    diag.add_argument("--timeout", type=float, default=0.1)
    diag.add_argument("--device", default="control_testing")
    diag.add_argument("--param", default="servo.a.hold.target_deg")
    diag.add_argument("--iterations", type=int, default=20)
    diag.add_argument("--wait", type=float, default=1.0)
    diag.add_argument("--describe-wait", type=float, default=2.0)
    diag.add_argument("--id-base", type=int, default=1000)
    diag.set_defaults(func=_run_diag)

    replay = subparsers.add_parser("replay", help="replay a recorded JSONL session")
    replay.add_argument("path")
    replay.add_argument("--summary-only", action="store_true")
    replay.set_defaults(func=_run_replay)

    gui = subparsers.add_parser("gui", help="launch the desktop dashboard")
    gui.add_argument("--port")
    gui.add_argument("--baud", type=int, default=115200)
    gui.add_argument("--timeout", type=float, default=0.05)
    gui.add_argument("--record")
    gui.set_defaults(func=_run_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
