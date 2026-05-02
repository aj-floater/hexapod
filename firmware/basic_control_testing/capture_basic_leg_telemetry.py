#!/usr/bin/env python3
"""Capture basic leg telemetry from the Pico USB CDC serial port into a CSV file."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Iterable

import serial
from serial.tools import list_ports


EXPECTED_HEADER_FIELDS = [
    "state",
    "speed_mode",
    "cycle_time_ms",
    "time_us",
    "sample_index",
    "phase_u",
    "cmd_x_mm",
    "cmd_y_mm",
    "cmd_z_mm",
    "cmd_q_a_deg",
    "cmd_q_b_deg",
    "cmd_q_c_deg",
    "cmd_a_abs_deg",
    "cmd_b_abs_deg",
    "cmd_c_abs_deg",
    "adc_a_raw",
    "adc_b_raw",
    "adc_c_raw",
    "meas_q_a_deg",
    "meas_q_b_deg",
    "meas_q_c_deg",
    "meas_a_abs_deg",
    "meas_b_abs_deg",
    "meas_c_abs_deg",
    "meas_x_mm",
    "meas_y_mm",
    "meas_z_mm",
]
EXPECTED_HEADER_LINE = ",".join(EXPECTED_HEADER_FIELDS)
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 0.5
COMMON_USB_SERIAL_PREFIXES = (
    "/dev/ttyACM",
    "/dev/ttyUSB",
    "/dev/cu.usbmodem",
    "/dev/cu.usbserial",
    "COM",
)


class AutoDetectError(RuntimeError):
    """Raised when automatic port selection cannot pick a unique device."""


@dataclass(frozen=True)
class PortCandidate:
    """A serial port candidate with a detection score."""

    device: str
    description: str
    manufacturer: str
    product: str
    hwid: str
    score: int

    def display_name(self) -> str:
        parts = [self.device]
        if self.description:
            parts.append(self.description)
        if self.manufacturer:
            parts.append(self.manufacturer)
        if self.product and self.product != self.description:
            parts.append(self.product)
        if self.hwid:
            parts.append(self.hwid)
        return " | ".join(parts)


@dataclass
class CaptureStats:
    """Mutable capture state used for the final shutdown summary."""

    row_count: int = 0
    saw_header: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        help="Serial device path. If omitted, the script auto-detects a likely Pico USB CDC port.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="CSV output path. Defaults to telemetry_YYYYMMDD_HHMMSS.csv in the current directory.",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help="Serial baud rate to pass to pyserial. Pico USB CDC ignores this in practice.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Serial read timeout in seconds.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print ignored status and malformed lines to stderr.",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / f"telemetry_{timestamp}.csv"


def parse_csv_line(line: str) -> list[str]:
    return next(csv.reader([line], skipinitialspace=False))


def score_port(port: list_ports.ListPortInfo) -> int:
    text_parts = [
        port.device,
        port.description or "",
        getattr(port, "manufacturer", "") or "",
        getattr(port, "product", "") or "",
        getattr(port, "interface", "") or "",
        port.hwid or "",
    ]
    port_text = " ".join(text_parts).lower()
    score = 0

    if getattr(port, "vid", None) == 0x2E8A:
        score += 100
    if "raspberry pi" in port_text:
        score += 50
    if "pico" in port_text:
        score += 40
    if port.device.startswith("/dev/ttyACM") or port.device.startswith("/dev/cu.usbmodem"):
        score += 10
    elif port.device.startswith("/dev/ttyUSB") or port.device.startswith("/dev/cu.usbserial"):
        score += 5
    elif port.device.startswith("COM"):
        score += 5

    return score


def build_candidate(port: list_ports.ListPortInfo) -> PortCandidate:
    return PortCandidate(
        device=port.device,
        description=port.description or "",
        manufacturer=getattr(port, "manufacturer", "") or "",
        product=getattr(port, "product", "") or "",
        hwid=port.hwid or "",
        score=score_port(port),
    )


def format_candidate_list(candidates: Iterable[PortCandidate]) -> str:
    return "\n".join(f"  - {candidate.display_name()}" for candidate in candidates)


def looks_like_usb_serial(device: str) -> bool:
    return device.startswith(COMMON_USB_SERIAL_PREFIXES)


def autodetect_port() -> str:
    ports = [build_candidate(port) for port in list_ports.comports()]
    scored = [candidate for candidate in ports if candidate.score > 0]

    if len(scored) == 1:
        return scored[0].device
    if len(scored) > 1:
        raise AutoDetectError(
            "Multiple Pico-like serial ports found. Re-run with --port.\n"
            f"{format_candidate_list(scored)}"
        )

    fallback = [candidate for candidate in ports if looks_like_usb_serial(candidate.device)]
    if len(fallback) == 1:
        return fallback[0].device
    if len(fallback) > 1:
        raise AutoDetectError(
            "Multiple USB serial ports found and none were uniquely Pico-like. Re-run with --port.\n"
            f"{format_candidate_list(fallback)}"
        )

    if ports:
        raise AutoDetectError(
            "No likely Pico serial port found. Available serial ports:\n"
            f"{format_candidate_list(ports)}\n"
            "Re-run with --port if the correct device is listed above."
        )

    raise AutoDetectError(
        "No serial ports found. Connect the Pico and re-run, or pass --port explicitly."
    )


def open_output_file(path: Path) -> tuple[object, csv.writer]:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_obj = path.open("x", newline="", encoding="utf-8")
    return file_obj, csv.writer(file_obj)


def emit_verbose(message: str, enabled: bool) -> None:
    if enabled:
        print(message, file=sys.stderr)


def capture_rows(
    serial_port: serial.Serial,
    writer: csv.writer,
    output_file: object,
    stats: CaptureStats,
    verbose: bool,
) -> None:

    while True:
        raw_line = serial_port.readline()
        if not raw_line:
            continue

        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue

        if line == EXPECTED_HEADER_LINE:
            if not stats.saw_header:
                writer.writerow(EXPECTED_HEADER_FIELDS)
                output_file.flush()
                stats.saw_header = True
                emit_verbose("Telemetry header detected.", verbose)
            else:
                emit_verbose("Repeated telemetry header ignored.", verbose)
            continue

        if not stats.saw_header:
            emit_verbose(f"Ignored pre-header line: {line}", verbose)
            continue

        try:
            fields = parse_csv_line(line)
        except csv.Error as exc:
            emit_verbose(f"Ignored unparsable line: {line} ({exc})", verbose)
            continue

        if len(fields) != len(EXPECTED_HEADER_FIELDS):
            emit_verbose(f"Ignored non-telemetry line: {line}", verbose)
            continue

        writer.writerow(fields)
        output_file.flush()
        stats.row_count += 1


def main() -> int:
    args = parse_args()
    output_path = args.output if args.output is not None else default_output_path()

    try:
        port = args.port if args.port else autodetect_port()
    except AutoDetectError as exc:
        print(exc, file=sys.stderr)
        return 2

    stats = CaptureStats()

    try:
        with serial.Serial(port=port, baudrate=args.baud, timeout=args.timeout) as serial_port:
            print(f"Listening on {port}", file=sys.stderr)
            serial_port.reset_input_buffer()
            try:
                output_file, writer = open_output_file(output_path)
            except FileExistsError:
                print(f"Output file already exists: {output_path}", file=sys.stderr)
                return 2
            except OSError as exc:
                print(f"Unable to open output file {output_path}: {exc}", file=sys.stderr)
                return 2

            with output_file:
                print(f"Writing telemetry to {output_path}", file=sys.stderr)
                capture_rows(serial_port, writer, output_file, stats, args.verbose)
    except serial.SerialException as exc:
        print(f"Unable to open serial port {port}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCapture interrupted by user.", file=sys.stderr)
    finally:
        print(
            f"Summary: port={port} output={output_path} rows={stats.row_count} "
            f"header_seen={'yes' if stats.saw_header else 'no'}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
