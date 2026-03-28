from __future__ import annotations

import unittest

from devlink_dashboard.messages import (
    CapabilitiesMessage,
    CmdMessage,
    HelloMessage,
    ProtocolError,
    SampleMessage,
    build_cmd_message,
    parse_line,
    serialize_message,
)


class MessageTests(unittest.TestCase):
    def test_parse_hello(self) -> None:
        message = parse_line(
            '{"type":"hello","version":1,"device":"leg","protocol":"devlink","firmware":"0.1.0"}'
        )
        self.assertIsInstance(message, HelloMessage)
        self.assertEqual(message.device, "leg")

    def test_parse_capabilities(self) -> None:
        message = parse_line(
            '{"type":"capabilities","version":1,"device":"leg","commands":[{"name":"demo.start","args":[]}],'
            '"streams":[{"name":"leg.position","fields":[{"name":"setpoint_adc","type":"u16","unit":"adc"}]}],'
            '"params":[{"name":"control.setpoint_adc","type":"u16","access":"rw","default":2600,"min":0,"max":4095}]}'
        )
        self.assertIsInstance(message, CapabilitiesMessage)
        self.assertEqual(message.commands[0].name, "demo.start")
        self.assertEqual(message.streams[0].fields[0].name, "setpoint_adc")
        self.assertEqual(message.params[0].default, 2600)

    def test_cmd_round_trip(self) -> None:
        original = build_cmd_message(
            device="leg",
            command_id=7,
            name="param.set",
            args={"param": "control.setpoint_adc", "value": 2500},
        )
        encoded = serialize_message(original)
        parsed = parse_line(encoded)
        self.assertIsInstance(parsed, CmdMessage)
        self.assertEqual(parsed.id, 7)
        self.assertEqual(parsed.args["value"], 2500)

    def test_sample_requires_scalar_fields(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_line(
                '{"type":"sample","version":1,"device":"leg","stream":"leg.position","seq":1,"t_us":10,'
                '"data":{"nested":{"bad":true}}}'
            )

    def test_parse_bool_param_and_bool_sample(self) -> None:
        message = parse_line(
            '{"type":"capabilities","version":1,"device":"status_led","commands":[],"streams":['
            '{"name":"status_led.state","fields":['
            '{"name":"led_enabled","type":"bool","unit":"state"},'
            '{"name":"blink_period_ms","type":"u32","unit":"ms"}]}],'
            '"params":[{"name":"blink.enabled","type":"bool","access":"rw","default":true},'
            '{"name":"blink.period_ms","type":"u32","access":"rw","default":250,"min":10,"max":2000}]}'
        )
        self.assertIsInstance(message, CapabilitiesMessage)
        self.assertEqual(message.params[0].default, True)
        self.assertEqual(message.params[1].default, 250)

        sample = parse_line(
            '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":2,"t_us":50,'
            '"data":{"led_enabled":true,"blink_period_ms":500}}'
        )
        self.assertIsInstance(sample, SampleMessage)
        self.assertEqual(sample.data["led_enabled"], True)
        self.assertEqual(sample.data["blink_period_ms"], 500)

    def test_unknown_type_rejected(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_line('{"type":"nope","version":1,"device":"leg"}')


if __name__ == "__main__":
    unittest.main()
