from __future__ import annotations

import unittest

from hexapod_dashboard.messages import parse_line
from hexapod_dashboard.model import DashboardState


class ModelTests(unittest.TestCase):
    def test_dashboard_tracks_params_and_samples(self) -> None:
        dashboard = DashboardState()

        dashboard.apply(
            parse_line(
                '{"type":"capabilities","version":1,"device":"leg","commands":[],'
                '"streams":[{"name":"leg.position","fields":[{"name":"setpoint_adc","type":"u16","unit":"adc"}]}],'
                '"params":[{"name":"control.setpoint_adc","type":"u16","access":"rw","default":2600,"min":0,"max":4095}]}'
            )
        )
        dashboard.apply(
            parse_line(
                '{"type":"resp","version":1,"device":"leg","id":2,"ok":true,'
                '"result":{"param":"control.setpoint_adc","value":2450}}'
            )
        )
        dashboard.apply(
            parse_line(
                '{"type":"sample","version":1,"device":"leg","stream":"leg.position","seq":3,"t_us":22,'
                '"data":{"setpoint_adc":2450}}'
            )
        )

        device = dashboard.devices["leg"]
        self.assertEqual(device.params["control.setpoint_adc"], 2450)
        self.assertEqual(device.streams["leg.position"].last_seq, 3)
        self.assertEqual(device.streams["leg.position"].sample_count, 1)

    def test_param_list_response_updates_multiple_values(self) -> None:
        dashboard = DashboardState()
        dashboard.apply(
            parse_line(
                '{"type":"resp","version":1,"device":"leg","id":1,"ok":true,'
                '"result":{"params":[{"name":"a","value":1},{"name":"b","value":2}]}}'
            )
        )
        device = dashboard.devices["leg"]
        self.assertEqual(device.params["a"], 1)
        self.assertEqual(device.params["b"], 2)


if __name__ == "__main__":
    unittest.main()
