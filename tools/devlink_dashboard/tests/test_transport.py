from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from devlink_dashboard.gui.controller import ConnectionConfig, ConnectionWorker
from devlink_dashboard.transport import SerialPortInfo, SerialTransport, list_serial_port_infos, list_serial_ports


class TransportTests(unittest.TestCase):
    @mock.patch("serial.Serial")
    def test_open_resynchronizes_serial_input(self, mock_serial_ctor: mock.Mock) -> None:
        serial_instance = mock.Mock()
        mock_serial_ctor.return_value = serial_instance

        transport = SerialTransport("/dev/ttyACM0", baud=115200, timeout=0.05)
        transport.open()

        serial_instance.reset_input_buffer.assert_called_once_with()
        serial_instance.reset_output_buffer.assert_called_once_with()
        serial_instance.read_until.assert_called_once_with(b"\n")
        transport.close()

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


if __name__ == "__main__":
    unittest.main()
