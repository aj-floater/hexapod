from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from devlink_dashboard.gui.controller import ConnectionConfig, ConnectionWorker
from devlink_dashboard.messages import build_cmd_message
from devlink_dashboard.transport import SerialPortInfo, SerialTransport, list_serial_port_infos, list_serial_ports


class _ChunkedSerial:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    @property
    def in_waiting(self) -> int:
        if not self._chunks:
            return 0
        return len(self._chunks[0])

    def reset_output_buffer(self) -> None:
        return None

    def read(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    def close(self) -> None:
        return None


class TransportTests(unittest.TestCase):
    @mock.patch("serial.Serial")
    def test_open_resynchronizes_serial_input(self, mock_serial_ctor: mock.Mock) -> None:
        serial_instance = mock.Mock()
        mock_serial_ctor.return_value = serial_instance

        transport = SerialTransport("/dev/ttyACM0", baud=115200, timeout=0.05)
        transport.open()

        serial_instance.reset_output_buffer.assert_called_once_with()
        serial_instance.reset_input_buffer.assert_not_called()
        serial_instance.read_until.assert_not_called()
        transport.close()

    def test_readline_preserves_partial_line_across_quiet_gaps(self) -> None:
        capabilities_line = (
            b'{"type":"capabilities","version":1,"device":"control_testing","commands":[],"streams":[],'
            b'"params":[]}\r\n'
        )
        transport = SerialTransport("/dev/ttyACM0", baud=921600, timeout=0.0)
        transport._serial = _ChunkedSerial(
            [
                capabilities_line[:35],
                b"",
                capabilities_line[35:72],
                b"",
                capabilities_line[72:],
            ]
        )

        self.assertIsNone(transport.readline())
        self.assertGreater(transport.pending_input_bytes(), 0)
        self.assertIsNone(transport.readline())
        self.assertGreater(transport.pending_input_bytes(), 0)
        self.assertEqual(transport.readline(), capabilities_line[:-2])
        self.assertEqual(transport.pending_input_bytes(), 0)

    def test_pending_input_bytes_includes_buffered_bytes(self) -> None:
        transport = SerialTransport("/dev/ttyACM0", baud=921600, timeout=0.05)
        transport._serial = SimpleNamespace(in_waiting=4)
        transport._rx_buffer.extend(b"abc")

        self.assertEqual(transport.pending_input_bytes(), 7)

    @mock.patch("serial.tools.list_ports.comports")
    def test_list_serial_port_infos_includes_description(self, mock_comports: mock.Mock) -> None:
        mock_comports.return_value = [
            SimpleNamespace(device="/dev/ttyACM0", description="Raspberry Pi Debug Probe"),
            SimpleNamespace(device="/dev/ttyUSB0", description="USB UART"),
        ]

        ports = list_serial_port_infos()

        self.assertEqual(
            ports,
            [
                SerialPortInfo(device="/dev/ttyACM0", description="Raspberry Pi Debug Probe"),
                SerialPortInfo(device="/dev/ttyUSB0", description="USB UART"),
            ],
        )
        self.assertEqual(list_serial_ports(), ["/dev/ttyACM0", "/dev/ttyUSB0"])

    def test_connection_worker_drains_multiple_lines_per_poll(self) -> None:
        class FakeTransport:
            def __init__(self) -> None:
                self.lines = [
                    '{"type":"hello","version":1,"device":"status_led","protocol":"devlink","firmware":"test"}',
                    '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":1,"t_us":1,'
                    '"data":{"blink_period_ms":250}}',
                ]

            def readline(self) -> str | None:
                if not self.lines:
                    return None
                return self.lines.pop(0)

            def pending_input_bytes(self) -> int:
                return 1 if self.lines else 0

        worker = ConnectionWorker(ConnectionConfig(port="/dev/null"))
        worker._transport = FakeTransport()  # type: ignore[assignment]

        messages: list[object] = []
        worker.message_received.connect(messages.append)
        worker._poll()

        self.assertEqual(len(messages), 2)

    def test_connection_worker_sends_without_waiting_for_input_drain(self) -> None:
        class FakeTransport:
            def __init__(self) -> None:
                self.pending = 4
                self.sent: list[str] = []

            def pending_input_bytes(self) -> int:
                return self.pending

            def send_message(self, message) -> None:
                self.sent.append(message.name)

        worker = ConnectionWorker(ConnectionConfig(port="/dev/null"))
        worker._transport = FakeTransport()  # type: ignore[assignment]

        worker.send_message(
            SimpleNamespace(name="param.set", type="cmd")  # ignored because not a CmdMessage
        )
        self.assertEqual(worker._transport.sent, [])  # type: ignore[union-attr]

        from devlink_dashboard.messages import build_cmd_message

        message = build_cmd_message(
            device="status_led",
            command_id=7,
            name="param.set",
            args={"param": "blink.period_ms", "value": 123},
        )
        worker.send_message(message)
        self.assertEqual(worker._transport.sent, ["param.set"])  # type: ignore[union-attr]

    def test_connection_worker_flushes_outbox_before_draining_input(self) -> None:
        class FakeTransport:
            def __init__(self) -> None:
                self.lines = [
                    b'{"type":"hello","version":1,"device":"status_led","protocol":"devlink","firmware":"test"}',
                ]
                self.sent: list[str] = []

            def readline(self) -> bytes | None:
                if not self.lines:
                    return None
                return self.lines.pop(0)

            def pending_input_bytes(self) -> int:
                return 1 if self.lines else 0

            def send_message(self, message) -> None:
                self.sent.append(message.name)

        worker = ConnectionWorker(ConnectionConfig(port="/dev/null"))
        worker._transport = FakeTransport()  # type: ignore[assignment]
        worker._outbox.append(
            build_cmd_message(
                device="status_led",
                command_id=8,
                name="param.set",
                args={"param": "blink.period_ms", "value": 123},
            )
        )

        messages: list[object] = []
        worker.message_received.connect(messages.append)
        worker._poll()

        self.assertEqual(worker._transport.sent, ["param.set"])  # type: ignore[union-attr]
        self.assertEqual(len(messages), 1)

    def test_connection_worker_can_toggle_recording_without_reconnecting(self) -> None:
        worker = ConnectionWorker(ConnectionConfig(port="/dev/null"))
        worker._transport = object()  # type: ignore[assignment]

        states: list[tuple[bool, str]] = []
        worker.recording_state_changed.connect(lambda active, path: states.append((active, path)))

        with TemporaryDirectory() as tmpdir:
            record_path = Path(tmpdir) / "session.jsonl"
            worker.start_recording(str(record_path))
            worker._handle_line(
                '{"type":"hello","version":1,"device":"status_led","protocol":"devlink","firmware":"test"}'
            )
            worker.stop_recording()

            self.assertTrue(record_path.exists())
            lines = record_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn('"type":"hello"', lines[0])

        self.assertEqual(states, [(True, str(record_path)), (False, "")])

    def test_controller_reports_last_record_path_when_recording_stops(self) -> None:
        from devlink_dashboard.gui.controller import GuiController

        controller = GuiController()
        messages: list[str] = []
        controller.status_message.connect(messages.append)

        controller._on_recording_state_changed(True, "/tmp/devlink/session.jsonl")
        controller._on_recording_state_changed(False, "")

        self.assertEqual(
            messages,
            [
                "recording to /tmp/devlink/session.jsonl",
                "recording stopped: saved to /tmp/devlink/session.jsonl",
            ],
        )


if __name__ == "__main__":
    unittest.main()
