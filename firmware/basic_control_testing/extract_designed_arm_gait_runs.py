#!/usr/bin/env python3
"""Extract successful designed-arm gait runs from a DevLink JSONL recording."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys


SERVO_NAMES = ("A", "B", "C")


@dataclass(frozen=True)
class ParsedMessage:
    line_no: int
    payload: dict[str, object]


@dataclass(frozen=True)
class GaitRun:
    run_index: int
    command_id: int
    response_line_no: int
    speed_mode: int
    cycle_time_ms: int | None
    start_line_no: int
    end_line_no: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path, help="DevLink JSONL recording to inspect.")
    parser.add_argument(
        "--speed-mode",
        dest="speed_modes",
        type=int,
        action="append",
        help="Only extract matching gait speed modes. Repeat to keep multiple modes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for extracted JSON files. Defaults to the input file's directory.",
    )
    return parser.parse_args()


def load_messages(input_path: Path) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    with input_path.open(encoding="utf-8") as input_file:
        for line_no, raw_line in enumerate(input_file, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{input_path}:{line_no} is not valid JSON: {exc.msg}.") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{input_path}:{line_no} does not contain a JSON object.")
            messages.append(ParsedMessage(line_no=line_no, payload=payload))
    if not messages:
        raise ValueError(f"{input_path} is empty.")
    return messages


def discover_gait_runs(messages: list[ParsedMessage], input_path: Path) -> list[GaitRun]:
    command_names_by_id: dict[int, str] = {}
    raw_runs: list[tuple[int, int, int, int | None]] = []

    for message in messages:
        payload = message.payload
        message_type = payload.get("type")
        if message_type == "cmd":
            command_id = payload.get("id")
            command_name = payload.get("name")
            if isinstance(command_id, int) and isinstance(command_name, str):
                command_names_by_id[command_id] = command_name
            continue

        if message_type != "resp":
            continue

        command_id = payload.get("id")
        if not isinstance(command_id, int) or command_names_by_id.get(command_id) != "gait.play":
            continue
        if payload.get("ok") is not True:
            continue

        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError(f"{input_path}:{message.line_no} has a malformed gait.play result.")

        speed_mode = result.get("speed_mode")
        if not isinstance(speed_mode, int):
            raise ValueError(f"{input_path}:{message.line_no} is missing integer result.speed_mode.")

        cycle_time_ms = result.get("cycle_time_ms")
        if cycle_time_ms is not None and not isinstance(cycle_time_ms, int):
            raise ValueError(f"{input_path}:{message.line_no} has a non-integer result.cycle_time_ms.")

        raw_runs.append((command_id, message.line_no, speed_mode, cycle_time_ms))

    if not raw_runs:
        raise ValueError(f"{input_path} does not contain a successful gait.play response.")

    runs: list[GaitRun] = []
    final_line_no = messages[-1].line_no
    for run_index, (command_id, response_line_no, speed_mode, cycle_time_ms) in enumerate(raw_runs, start=1):
        start_line_no = response_line_no + 1
        next_response_line_no = raw_runs[run_index][1] if run_index < len(raw_runs) else None
        end_line_no = final_line_no if next_response_line_no is None else next_response_line_no - 1
        runs.append(
            GaitRun(
                run_index=run_index,
                command_id=command_id,
                response_line_no=response_line_no,
                speed_mode=speed_mode,
                cycle_time_ms=cycle_time_ms,
                start_line_no=start_line_no,
                end_line_no=end_line_no,
            )
        )
    return runs


def _float_field(data: dict[str, object], key: str, input_path: Path, line_no: int) -> float:
    value = data.get(key)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{input_path}:{line_no} has a non-numeric {key}.") from exc


def extract_run_payload(input_path: Path, messages: list[ParsedMessage], run: GaitRun) -> dict[str, object]:
    run_messages = [
        message.payload
        for message in messages
        if run.start_line_no <= message.line_no <= run.end_line_no
    ]

    hold_samples: list[dict[str, object]] = []
    start_time_us: float | None = None
    end_time_us: float | None = None

    for message in messages:
        if message.line_no < run.start_line_no or message.line_no > run.end_line_no:
            continue
        payload = message.payload
        if payload.get("type") != "sample" or payload.get("stream") != "control_testing.hold":
            continue

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"{input_path}:{message.line_no} has a malformed control_testing.hold payload.")

        time_us = _float_field(payload, "t_us", input_path, message.line_no)
        if start_time_us is None:
            start_time_us = time_us
        end_time_us = time_us

        sample = {
            "line_no": message.line_no,
            "seq": payload.get("seq"),
            "time_us": time_us,
            "elapsed_s": (time_us - start_time_us) / 1_000_000.0,
            "target_deg": {},
            "actual_deg": {},
            "error_deg": {},
            "output_pct": {},
        }

        for servo_name in SERVO_NAMES:
            servo_id = servo_name.lower()
            sample["target_deg"][servo_name] = _float_field(
                data, f"hold_{servo_id}_target_deg", input_path, message.line_no
            )
            sample["actual_deg"][servo_name] = _float_field(
                data, f"hold_{servo_id}_actual_deg", input_path, message.line_no
            )
            sample["error_deg"][servo_name] = _float_field(
                data, f"hold_{servo_id}_error_deg", input_path, message.line_no
            )
            sample["output_pct"][servo_name] = int(round(_float_field(
                data, f"hold_{servo_id}_output_pct", input_path, message.line_no
            )))

        hold_samples.append(sample)

    if not hold_samples or start_time_us is None or end_time_us is None:
        raise ValueError(
            f"{input_path} run {run.run_index} (speed {run.speed_mode}) has no control_testing.hold samples."
        )

    return {
        "source_recording": str(input_path),
        "run_index": run.run_index,
        "speed_mode": run.speed_mode,
        "cycle_time_ms": run.cycle_time_ms,
        "command_id": run.command_id,
        "response_line_no": run.response_line_no,
        "start_line_no": run.start_line_no,
        "end_line_no": run.end_line_no,
        "message_count": len(run_messages),
        "hold_sample_count": len(hold_samples),
        "start_time_us": start_time_us,
        "end_time_us": end_time_us,
        "duration_s": (end_time_us - start_time_us) / 1_000_000.0,
        "hold_samples": hold_samples,
    }


def output_path_for_run(
    output_dir: Path,
    input_path: Path,
    run: GaitRun,
    speed_counts: dict[int, int],
) -> Path:
    base_name = f"{input_path.stem}_speed{run.speed_mode}"
    if speed_counts[run.speed_mode] > 1:
        base_name = f"{base_name}_run{run.run_index}"
    return output_dir / f"{base_name}.json"


def main() -> int:
    args = parse_args()
    input_path = args.input_path.resolve()
    output_dir = (args.output_dir or input_path.parent).resolve()

    try:
        messages = load_messages(input_path)
        runs = discover_gait_runs(messages, input_path)
        if args.speed_modes:
            requested = set(args.speed_modes)
            runs = [run for run in runs if run.speed_mode in requested]
            if not runs:
                raise ValueError(
                    f"{input_path} does not contain successful gait.play runs for speed modes: "
                    f"{', '.join(str(mode) for mode in sorted(requested))}."
                )

        speed_counts: dict[int, int] = defaultdict(int)
        for run in runs:
            speed_counts[run.speed_mode] += 1

        output_dir.mkdir(parents=True, exist_ok=True)
        for run in runs:
            payload = extract_run_payload(input_path, messages, run)
            output_path = output_path_for_run(output_dir, input_path, run, speed_counts)
            with output_path.open("w", encoding="utf-8") as output_file:
                json.dump(payload, output_file, indent=2)
                output_file.write("\n")
            print(
                f"Saved {output_path} "
                f"(speed {run.speed_mode}, {payload['hold_sample_count']} hold samples, {payload['duration_s']:.3f} s)"
            )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
