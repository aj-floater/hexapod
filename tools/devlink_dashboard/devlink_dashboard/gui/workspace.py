from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

LAYOUT_VERSION = 1
PRESET_STORE_VERSION = 1
DEFAULT_X_GROUP = "main"
DEFAULT_PRESET_NAME = "Default"
DEFAULT_TRACE_COLORS = (
    "#0b84f3",
    "#f39c12",
    "#19b36b",
    "#d64550",
    "#8a5cf6",
    "#00a4a6",
)


@dataclass(frozen=True)
class PlotTrace:
    stream: str
    field: str
    color: str
    visible: bool = True
    label: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.stream, self.field)

    @property
    def display_label(self) -> str:
        return self.label or f"{self.stream}.{self.field}"


@dataclass(frozen=True)
class PlotPane:
    id: str
    title: str
    x_group: str = DEFAULT_X_GROUP
    traces: tuple[PlotTrace, ...] = field(default_factory=tuple)
    size: int | None = None
    trace_panel_visible: bool = False
    trace_panel_height: int | None = None


@dataclass(frozen=True)
class PlotWorkspace:
    device: str
    panes: tuple[PlotPane, ...]
    active_pane_id: str | None = None
    version: int = LAYOUT_VERSION


@dataclass(frozen=True)
class WorkspacePreset:
    name: str
    workspace: PlotWorkspace
    visible_param_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspacePresetCollection:
    device: str
    presets: tuple[WorkspacePreset, ...]
    active_preset_name: str
    version: int = PRESET_STORE_VERSION


@dataclass(frozen=True)
class WindowLayout:
    body_splitter_sizes: tuple[int, ...] = ()
    body_splitter_state: str | None = None


def default_trace_color(index: int) -> str:
    return DEFAULT_TRACE_COLORS[index % len(DEFAULT_TRACE_COLORS)]


def blank_workspace(device: str) -> PlotWorkspace:
    return PlotWorkspace(device=device, panes=(), active_pane_id=None)


def _sanitize_device_name(device: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", device).strip("._")
    return sanitized or "device"


def default_workspace_root() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not root:
        return Path.home() / ".config" / "devlink_dashboard" / "workspaces"
    path = Path(root)
    if path.name == ".config":
        path = path / "devlink_dashboard"
    return path / "workspaces"


def default_layout_root() -> Path:
    return default_workspace_root().parent


def workspace_to_dict(workspace: PlotWorkspace) -> dict[str, object]:
    return {
        "version": workspace.version,
        "device": workspace.device,
        "active_pane_id": workspace.active_pane_id,
        "panes": [
            {
                "id": pane.id,
                "title": pane.title,
                "x_group": pane.x_group,
                "size": pane.size,
                "trace_panel_visible": pane.trace_panel_visible,
                "trace_panel_height": pane.trace_panel_height,
                "traces": [
                    {
                        "stream": trace.stream,
                        "field": trace.field,
                        "color": trace.color,
                        "visible": trace.visible,
                        "label": trace.label,
                    }
                    for trace in pane.traces
                ],
            }
            for pane in workspace.panes
        ],
    }


def workspace_from_dict(raw: object, *, device: str | None = None) -> PlotWorkspace:
    if not isinstance(raw, dict):
        raise ValueError("workspace payload must be an object")

    version = raw.get("version", LAYOUT_VERSION)
    if not isinstance(version, int):
        raise ValueError("workspace version must be an integer")
    if version != LAYOUT_VERSION:
        raise ValueError(f"unsupported workspace version {version}")

    resolved_device = device or raw.get("device")
    if not isinstance(resolved_device, str) or not resolved_device:
        raise ValueError("workspace device must be a string")

    active_pane_id = raw.get("active_pane_id")
    if active_pane_id is not None and not isinstance(active_pane_id, str):
        raise ValueError("active_pane_id must be a string or null")

    panes_raw = raw.get("panes")
    if not isinstance(panes_raw, list):
        raise ValueError("panes must be a list")

    panes: list[PlotPane] = []
    for pane_raw in panes_raw:
        if not isinstance(pane_raw, dict):
            raise ValueError("pane must be an object")
        pane_id = pane_raw.get("id")
        title = pane_raw.get("title")
        x_group = pane_raw.get("x_group", DEFAULT_X_GROUP)
        size = pane_raw.get("size")
        trace_panel_visible = pane_raw.get("trace_panel_visible", False)
        trace_panel_height = pane_raw.get("trace_panel_height")
        traces_raw = pane_raw.get("traces", [])
        if not isinstance(pane_id, str) or not pane_id:
            raise ValueError("pane id must be a string")
        if not isinstance(title, str):
            raise ValueError("pane title must be a string")
        if not isinstance(x_group, str) or not x_group:
            raise ValueError("pane x_group must be a string")
        if size is not None and (not isinstance(size, int) or size <= 0):
            raise ValueError("pane size must be a positive integer or null")
        if not isinstance(trace_panel_visible, bool):
            raise ValueError("pane trace_panel_visible must be a boolean")
        if trace_panel_height is not None and (not isinstance(trace_panel_height, int) or trace_panel_height <= 0):
            raise ValueError("pane trace_panel_height must be a positive integer or null")
        if not isinstance(traces_raw, list):
            raise ValueError("pane traces must be a list")

        traces: list[PlotTrace] = []
        for trace_raw in traces_raw:
            if not isinstance(trace_raw, dict):
                raise ValueError("trace must be an object")
            stream = trace_raw.get("stream")
            field = trace_raw.get("field")
            color = trace_raw.get("color")
            visible = trace_raw.get("visible", True)
            label = trace_raw.get("label")
            if not isinstance(stream, str) or not stream:
                raise ValueError("trace stream must be a string")
            if not isinstance(field, str) or not field:
                raise ValueError("trace field must be a string")
            if not isinstance(color, str) or not color:
                raise ValueError("trace color must be a string")
            if not isinstance(visible, bool):
                raise ValueError("trace visible must be a boolean")
            if label is not None and not isinstance(label, str):
                raise ValueError("trace label must be a string or null")
            traces.append(
                PlotTrace(
                    stream=stream,
                    field=field,
                    color=color,
                    visible=visible,
                    label=label,
                )
            )

        panes.append(
            PlotPane(
                id=pane_id,
                title=title,
                x_group=x_group,
                traces=tuple(traces),
                size=size,
                trace_panel_visible=trace_panel_visible,
                trace_panel_height=trace_panel_height,
            )
        )

    return PlotWorkspace(
        version=version,
        device=resolved_device,
        panes=tuple(panes),
        active_pane_id=active_pane_id,
    )


def workspace_presets_to_dict(collection: WorkspacePresetCollection) -> dict[str, object]:
    return {
        "version": collection.version,
        "device": collection.device,
        "active_preset_name": collection.active_preset_name,
        "presets": [
            {
                "name": preset.name,
                "workspace": workspace_to_dict(preset.workspace),
                "visible_param_names": list(preset.visible_param_names),
            }
            for preset in collection.presets
        ],
    }


def workspace_presets_from_dict(raw: object, *, device: str | None = None) -> WorkspacePresetCollection:
    if not isinstance(raw, dict):
        raise ValueError("workspace preset payload must be an object")

    if "presets" not in raw:
        legacy_workspace = workspace_from_dict(raw, device=device)
        return WorkspacePresetCollection(
            device=legacy_workspace.device,
            presets=(WorkspacePreset(name=DEFAULT_PRESET_NAME, workspace=legacy_workspace),),
            active_preset_name=DEFAULT_PRESET_NAME,
        )

    version = raw.get("version", PRESET_STORE_VERSION)
    if not isinstance(version, int):
        raise ValueError("workspace preset version must be an integer")
    if version != PRESET_STORE_VERSION:
        raise ValueError(f"unsupported workspace preset version {version}")

    resolved_device = device or raw.get("device")
    if not isinstance(resolved_device, str) or not resolved_device:
        raise ValueError("workspace preset device must be a string")

    active_preset_name = raw.get("active_preset_name")
    if not isinstance(active_preset_name, str) or not active_preset_name:
        raise ValueError("active_preset_name must be a string")

    presets_raw = raw.get("presets")
    if not isinstance(presets_raw, list) or not presets_raw:
        raise ValueError("presets must be a non-empty list")

    presets: list[WorkspacePreset] = []
    preset_names: set[str] = set()
    for preset_raw in presets_raw:
        if not isinstance(preset_raw, dict):
            raise ValueError("preset must be an object")
        name = preset_raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("preset name must be a non-empty string")
        if name in preset_names:
            raise ValueError(f"duplicate preset name {name}")
        visible_param_names_raw = preset_raw.get("visible_param_names", [])
        if not isinstance(visible_param_names_raw, list):
            raise ValueError("visible_param_names must be a list")
        visible_param_names: list[str] = []
        seen_param_names: set[str] = set()
        for param_name in visible_param_names_raw:
            if not isinstance(param_name, str) or not param_name:
                raise ValueError("visible_param_names entries must be non-empty strings")
            if param_name in seen_param_names:
                raise ValueError(f"duplicate visible_param_name {param_name}")
            visible_param_names.append(param_name)
            seen_param_names.add(param_name)
        workspace = workspace_from_dict(preset_raw.get("workspace"), device=resolved_device)
        presets.append(
            WorkspacePreset(
                name=name,
                workspace=workspace,
                visible_param_names=tuple(visible_param_names),
            )
        )
        preset_names.add(name)

    if active_preset_name not in preset_names:
        raise ValueError("active_preset_name must match a preset")

    return WorkspacePresetCollection(
        version=version,
        device=resolved_device,
        presets=tuple(presets),
        active_preset_name=active_preset_name,
    )


class WorkspaceStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or default_workspace_root()

    def path_for_device(self, device: str) -> Path:
        return self._root_dir / f"{_sanitize_device_name(device)}.json"

    def load(self, device: str) -> WorkspacePresetCollection | None:
        path = self.path_for_device(device)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return workspace_presets_from_dict(raw, device=device)

    def save(self, collection: WorkspacePresetCollection) -> None:
        path = self.path_for_device(collection.device)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = workspace_presets_to_dict(collection)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class WindowLayoutStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir = root_dir or default_layout_root()

    @property
    def _path(self) -> Path:
        return self._root_dir / "window_layout.json"

    def load(self) -> WindowLayout | None:
        path = self._path
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("window layout payload must be an object")
        sizes = raw.get("body_splitter_sizes", [])
        state = raw.get("body_splitter_state")
        if not isinstance(sizes, list) or any(not isinstance(size, int) or size <= 0 for size in sizes):
            raise ValueError("body_splitter_sizes must be a list of positive integers")
        if state is not None and not isinstance(state, str):
            raise ValueError("body_splitter_state must be a string or null")
        return WindowLayout(body_splitter_sizes=tuple(sizes), body_splitter_state=state)

    def save(self, layout: WindowLayout) -> None:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "body_splitter_sizes": list(layout.body_splitter_sizes),
            "body_splitter_state": layout.body_splitter_state,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
