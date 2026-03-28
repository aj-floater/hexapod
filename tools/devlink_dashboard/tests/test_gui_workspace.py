from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from devlink_dashboard.gui.runtime import DashboardRuntime
from devlink_dashboard.gui.workspace import PlotPane, PlotTrace, PlotWorkspace, WorkspaceStore, workspace_from_dict, workspace_to_dict
from devlink_dashboard.messages import parse_line


class WorkspaceTests(unittest.TestCase):
    def test_runtime_builds_default_workspace_from_numeric_streams(self) -> None:
        runtime = DashboardRuntime()
        runtime.apply_message(
            parse_line(
                '{"type":"capabilities","version":1,"device":"leg","commands":[],"streams":['
                '{"name":"leg.position","fields":['
                '{"name":"setpoint_adc","type":"u16","unit":"adc"},'
                '{"name":"enabled","type":"bool","unit":"state"}]},'
                '{"name":"leg.control","fields":[{"name":"control_output_pct","type":"i16","unit":"percent"}]}],'
                '"params":[]}'
            )
        )

        workspace = runtime.build_default_workspace("leg")

        self.assertEqual(workspace.device, "leg")
        self.assertEqual([pane.id for pane in workspace.panes], ["pane-1", "pane-2"])
        self.assertEqual([trace.field for trace in workspace.panes[0].traces], ["setpoint_adc"])
        self.assertEqual([trace.field for trace in workspace.panes[1].traces], ["control_output_pct"])

    def test_workspace_round_trip_and_store_are_per_device(self) -> None:
        workspace = PlotWorkspace(
            device="status_led",
            active_pane_id="pane-1",
            panes=(
                PlotPane(
                    id="pane-1",
                    title="State",
                    traces=(
                        PlotTrace(stream="status_led.state", field="blink_period_ms", color="#0b84f3"),
                    ),
                ),
            ),
        )

        payload = workspace_to_dict(workspace)
        restored = workspace_from_dict(payload)
        self.assertEqual(restored, workspace)

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = WorkspaceStore(Path(tmp_dir))
            store.save(workspace)
            loaded = store.load("status_led")
            self.assertEqual(loaded, workspace)
            self.assertIsNone(store.load("leg"))


if __name__ == "__main__":
    unittest.main()
