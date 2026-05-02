#!/usr/bin/env python3
"""Helpers for loading plot data from basic-leg CSV and designed-arm JSONL captures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


INPUT_FORMAT_CSV = "csv"
INPUT_FORMAT_JSONL = "jsonl"
SERVO_NAMES = ("A", "B", "C")


@dataclass(frozen=True)
class DesignedArmHoldSample:
    """One normalized hold sample from a Devlink recording."""

    line_no: int
    time_us: float
    target_deg: dict[str, float]
    actual_deg: dict[str, float]


def find_latest_capture(directory: Path) -> Path:
    """Return the newest likely capture file, preferring the current CSV workflow."""
    for pattern in ("telemetry_*.csv", "*.csv", "*.jsonl"):
        candidates = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]
    raise FileNotFoundError("No CSV or JSONL capture files found in the working directory.")


def detect_input_format(path: Path) -> str:
    """Infer whether a capture file is flat CSV telemetry or Devlink JSONL."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return INPUT_FORMAT_CSV
    if suffix == ".jsonl":
        return INPUT_FORMAT_JSONL

    with path.open(encoding="utf-8") as input_file:
        for raw_line in input_file:
            line = raw_line.strip()
            if not line:
                continue
            return INPUT_FORMAT_JSONL if line.startswith("{") else INPUT_FORMAT_CSV

    raise ValueError(f"{path} is empty.")


def require_columns(fieldnames: list[str] | None, required_columns: list[str], capture_path: Path) -> None:
    """Ensure a CSV header contains every required column."""
    if fieldnames is None:
        raise ValueError(f"{capture_path} does not contain a CSV header row.")

    missing = [column for column in required_columns if column not in fieldnames]
    if missing:
        raise ValueError(f"{capture_path} is missing required columns: {', '.join(missing)}")


def _read_float_field(data: dict[str, object], field_name: str, capture_path: Path, line_no: int) -> float:
    if field_name not in data:
        raise ValueError(f"{capture_path}:{line_no} is missing required field {field_name}.")

    try:
        return float(data[field_name])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{capture_path}:{line_no} has a non-numeric value for {field_name}.") from exc


def load_designed_arm_hold_samples(capture_path: Path) -> list[DesignedArmHoldSample]:
    """Return normalized hold samples for the latest successful gait run in a Devlink JSONL capture."""
    hold_samples: list[DesignedArmHoldSample] = []
    command_names_by_id: dict[int, str] = {}
    last_gait_play_response_line: int | None = None

    with capture_path.open(encoding="utf-8") as input_file:
        for line_no, raw_line in enumerate(input_file, start=1):
            line = raw_line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{capture_path}:{line_no} is not valid JSON: {exc.msg}.") from exc

            if not isinstance(message, dict):
                raise ValueError(f"{capture_path}:{line_no} does not contain a JSON object.")

            message_type = message.get("type")
            if message_type == "cmd":
                command_id = message.get("id")
                command_name = message.get("name")
                if isinstance(command_id, int) and isinstance(command_name, str):
                    command_names_by_id[command_id] = command_name
                continue

            if message_type == "resp":
                command_id = message.get("id")
                if isinstance(command_id, int) and command_names_by_id.get(command_id) == "gait.play":
                    if message.get("ok") is True:
                        last_gait_play_response_line = line_no
                continue

            if message_type != "sample" or message.get("stream") != "control_testing.hold":
                continue

            data = message.get("data")
            if not isinstance(data, dict):
                raise ValueError(f"{capture_path}:{line_no} has a malformed control_testing.hold sample.")

            time_us = _read_float_field(message, "t_us", capture_path, line_no)
            target_deg: dict[str, float] = {}
            actual_deg: dict[str, float] = {}
            for servo_name in SERVO_NAMES:
                servo_id = servo_name.lower()
                target_deg[servo_name] = _read_float_field(
                    data,
                    f"hold_{servo_id}_target_deg",
                    capture_path,
                    line_no,
                )
                actual_deg[servo_name] = _read_float_field(
                    data,
                    f"hold_{servo_id}_actual_deg",
                    capture_path,
                    line_no,
                )

            hold_samples.append(
                DesignedArmHoldSample(
                    line_no=line_no,
                    time_us=time_us,
                    target_deg=target_deg,
                    actual_deg=actual_deg,
                )
            )

    if last_gait_play_response_line is None:
        raise ValueError(f"{capture_path} does not contain a successful gait.play response.")

    latest_run_samples = [sample for sample in hold_samples if sample.line_no > last_gait_play_response_line]
    if not latest_run_samples:
        raise ValueError(f"{capture_path} has no control_testing.hold samples after the latest gait.play.")

    return latest_run_samples
