# Simulation Architecture

## Current Goal

Bootstrap a Magnum-based editor shell that can host a primitive sandbox today and a single-joint simulation stack later.

## Active Scope

The bootstrap milestone includes:

- Magnum `Platform::Sdl2Application`
- Dear ImGui docking
- a framebuffer-backed viewport panel
- hierarchy, inspector, and log panels
- transform editing with `ImGuizmo`
- translate and rotate snapping
- persistent layout and editor preferences

The bootstrap milestone excludes:

- imported assets or model pipelines
- playback/devlink transport
- joint dynamics or control models
- detached multi-window UI

## Layer Boundaries

- `EditorApplication`
  Owns lifecycle, frame loop, layout, input routing, and persistence.
- `ViewportRenderer`
  Owns scene render passes, framebuffer allocation, and viewport draw state.
- `SceneModel`
  Owns entities, transforms, selection metadata, and editor-facing scene state.
- `EditorPanels`
  Own panel rendering and translate user actions into editor commands.
- `SceneSource`
  Produces frame-oriented scene data for the renderer.

## Invariants

- Render code does not talk directly to future replay/devlink transports.
- Panels do not own authoritative scene state.
- Input capture is explicit: UI and gizmo interaction suppress camera/world controls.
- Runtime layout and preferences live under `.codex/editor/`.

## Planned Extension Path

1. Editor shell bootstrap
2. Single-joint primitive rig scene source
3. Offline playback scene source
4. Live devlink scene source
