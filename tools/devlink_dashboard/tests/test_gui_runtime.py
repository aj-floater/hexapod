from __future__ import annotations

import unittest

from devlink_dashboard.gui.runtime import DashboardRuntime
from devlink_dashboard.messages import parse_line


class GuiRuntimeTests(unittest.TestCase):
    def test_runtime_tracks_numeric_series_and_ignores_bool(self) -> None:
        runtime = DashboardRuntime(history_limit=3)
        runtime.apply_message(
            parse_line(
                '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":1,"t_us":10,'
                '"data":{"led_enabled":true,"blink_period_ms":250}}'
            )
        )
        runtime.apply_message(
            parse_line(
                '{"type":"sample","version":1,"device":"status_led","stream":"status_led.state","seq":2,"t_us":20,'
                '"data":{"led_enabled":false,"blink_period_ms":300}}'
            )
        )

        self.assertEqual(
            runtime.series_for_field("status_led", "status_led.state", "blink_period_ms"),
            ([10, 20], [250.0, 300.0]),
        )
        self.assertEqual(runtime.series_for_field("status_led", "status_led.state", "led_enabled"), ([], []))

    def test_runtime_filters_reserved_commands_and_allocates_ids(self) -> None:
        runtime = DashboardRuntime()
        runtime.apply_message(
            parse_line(
                '{"type":"capabilities","version":1,"device":"leg","commands":['
                '{"name":"device.describe","args":[]},'
                '{"name":"demo.start","args":[]},'
                '{"name":"param.list","args":[]},'
                '{"name":"param.set","args":[{"name":"param","type":"string","required":true}]}],'
                '"streams":[],"params":[]}'
            )
        )

        commands = runtime.command_specs_for_device("leg")
        self.assertEqual([command.name for command in commands], ["demo.start"])
        self.assertEqual(runtime.allocate_command_id(), 1)
        self.assertEqual(runtime.allocate_command_id(), 2)


if __name__ == "__main__":
    unittest.main()
