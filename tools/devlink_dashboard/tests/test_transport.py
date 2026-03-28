from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from devlink_dashboard.transport import SerialPortInfo, list_serial_port_infos, list_serial_ports


class TransportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

