from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from devlink_dashboard.gui.runtime import DashboardRuntime
from devlink_dashboard.gui.workspace import (
    DEFAULT_PRESET_NAME,
    PlotPane,
    PlotTrace,
    PlotWorkspace,
    WorkspacePreset,
    WorkspacePresetCollection,
    WorkspaceStore,
    workspace_from_dict,
    workspace_presets_from_dict,
    workspace_presets_to_dict,
    workspace_to_dict,
)
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

    def test_workspace_preset_round_trip_and_store_are_per_device(self) -> None:
        workspace = PlotWorkspace(
            device="status_led",
            active_pane_id="pane-1",
            panes=(
                PlotPane(
                    id="pane-1",
                    title="State",
                    size=320,
                    trace_panel_visible=True,
                    trace_panel_height=188,
                    traces=(
                        PlotTrace(stream="status_led.state", field="blink_period_ms", color="#0b84f3"),
                    ),
                ),
            ),
        )
        collection = WorkspacePresetCollection(
            device="status_led",
            active_preset_name="Preset 2",
            presets=(
                WorkspacePreset(
                    name=DEFAULT_PRESET_NAME,
                    workspace=workspace,
                    visible_param_names=("blink.period_ms",),
                ),
                WorkspacePreset(
                    name="Preset 2",
                    workspace=PlotWorkspace(device="status_led", panes=()),
                    visible_param_names=("status_led.enabled", "telemetry.rate_hz"),
                ),
            ),
        )

        payload = workspace_presets_to_dict(collection)
        restored = workspace_presets_from_dict(payload)
        self.assertEqual(restored, collection)

        with tempfile.TemporaryDirectory() as tmp_dir:
            store = WorkspaceStore(Path(tmp_dir))
            store.save(collection)
            loaded = store.load("status_led")
            self.assertEqual(loaded, collection)
            self.assertIsNone(store.load("leg"))

    def test_legacy_workspace_payload_migrates_to_default_preset(self) -> None:
        workspace = PlotWorkspace(
            device="status_led",
            active_pane_id="pane-1",
            panes=(
                PlotPane(
                    id="pane-1",
                    title="State",
                    trace_panel_visible=True,
                    traces=(PlotTrace(stream="status_led.state", field="blink_period_ms", color="#0b84f3"),),
                ),
            ),
        )

        payload = workspace_to_dict(workspace)
        restored_workspace = workspace_from_dict(payload)
        self.assertEqual(restored_workspace, workspace)

        restored_presets = workspace_presets_from_dict(payload)
        self.assertEqual(restored_presets.device, "status_led")
        self.assertEqual(restored_presets.active_preset_name, DEFAULT_PRESET_NAME)
        self.assertEqual(len(restored_presets.presets), 1)
        self.assertEqual(restored_presets.presets[0].name, DEFAULT_PRESET_NAME)
        self.assertEqual(restored_presets.presets[0].workspace, workspace)
        self.assertEqual(restored_presets.presets[0].visible_param_names, ())

    def test_workspace_payload_without_trace_panel_visible_defaults_to_false(self) -> None:
        payload = {
            "version": 1,
            "device": "status_led",
            "active_pane_id": "pane-1",
            "panes": [
                {
                    "id": "pane-1",
                    "title": "State",
                    "x_group": "main",
                    "traces": [
                        {
                            "stream": "status_led.state",
                            "field": "blink_period_ms",
                            "color": "#0b84f3",
                            "visible": True,
                            "label": None,
                        }
                    ],
                }
            ],
        }

        restored = workspace_from_dict(payload)

        self.assertFalse(restored.panes[0].trace_panel_visible)
        self.assertIsNone(restored.panes[0].trace_panel_height)

    def test_preset_payload_without_visible_param_names_defaults_to_empty(self) -> None:
        payload = {
            "version": 1,
            "device": "status_led",
            "active_preset_name": DEFAULT_PRESET_NAME,
            "presets": [
                {
                    "name": DEFAULT_PRESET_NAME,
                    "workspace": {
                        "version": 1,
                        "device": "status_led",
                        "active_pane_id": None,
                        "panes": [],
                    },
                }
            ],
        }

        restored = workspace_presets_from_dict(payload)

        self.assertEqual(restored.device, "status_led")
        self.assertEqual(restored.presets[0].visible_param_names, ())


if __name__ == "__main__":
    unittest.main()
