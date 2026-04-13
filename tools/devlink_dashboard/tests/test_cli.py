from __future__ import annotations

import argparse
import importlib
import json
import unittest
from unittest import mock

cli = importlib.import_module("devlink_dashboard.cli")


class _FakeDiagTransport:
    def __init__(self, scenario: str) -> None:
        self._scenario = scenario
        self._queue: list[bytes] = []

    def __enter__(self) -> "_FakeDiagTransport":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def send_message(self, message) -> None:
        if message.name == "device.describe":
            self._queue.extend(
                [
                    b'{"type":"hello","version":1,"device":"control_testing","protocol":"devlink","firmware":"test"}',
                    (
                        b'{"type":"capabilities","version":1,"device":"control_testing",'
                        b'"commands":[],"streams":[{"name":"control_testing.adc","id":0,'
                        b'"sample_format":"binary","fields":[{"name":"adc_a_raw","type":"u16","unit":"adc"}]}],'
                        b'"params":[{"name":"servo.a.hold.target_deg","type":"f32","access":"rw","default":90.0}]}'
                    ),
                    json.dumps(
                        {
                            "type": "resp",
                            "version": 1,
                            "device": "control_testing",
                            "id": message.id,
                            "ok": True,
                        }
                    ).encode("utf-8"),
                ]
            )
            return

        if message.name == "param.get" and self._scenario == "success":
            self._queue.append(
                json.dumps(
                    {
                        "type": "resp",
                        "version": 1,
                        "device": "control_testing",
                        "id": message.id,
                        "ok": True,
                        "result": {
                            "param": "servo.a.hold.target_deg",
                            "value": 90.0,
                        },
                    }
                ).encode("utf-8")
            )

    def readline(self) -> bytes | None:
        if self._queue:
            return self._queue.pop(0)
        return None


class CliTests(unittest.TestCase):
    def test_parser_includes_diag_subcommand(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["diag", "--port", "/dev/ttyACM0"])
        self.assertEqual(args.command, "diag")
        self.assertTrue(callable(args.func))

    @mock.patch("devlink_dashboard.cli.SerialTransport")
    def test_run_diag_success(self, mock_transport_ctor: mock.Mock) -> None:
        mock_transport_ctor.side_effect = lambda *a, **k: _FakeDiagTransport("success")
        args = argparse.Namespace(
            port="/dev/ttyACM0",
            baud=921600,
            timeout=0.01,
            device="control_testing",
            param="servo.a.hold.target_deg",
            iterations=3,
            wait=0.1,
            describe_wait=0.2,
            id_base=1000,
        )

        result = cli._run_diag(args)
        self.assertEqual(result, 0)

    @mock.patch("devlink_dashboard.cli.SerialTransport")
    def test_run_diag_times_out_when_param_response_missing(self, mock_transport_ctor: mock.Mock) -> None:
        mock_transport_ctor.side_effect = lambda *a, **k: _FakeDiagTransport("timeout")
        args = argparse.Namespace(
            port="/dev/ttyACM0",
            baud=921600,
            timeout=0.01,
            device="control_testing",
            param="servo.a.hold.target_deg",
            iterations=2,
            wait=0.02,
            describe_wait=0.2,
            id_base=1100,
        )

        result = cli._run_diag(args)
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
