# Hexapod Simulation

`software/simulation` hosts the Magnum-based editor shell for the single-joint sandbox and future replay/devlink integration work.

## Status

The current milestone is an editor-style primitive sandbox:

- single native window
- ImGui docking layout
- dockable 3D viewport
- hierarchy, inspector, and log panels
- translate/rotate gizmo and snapping
- persistent layout and editor preferences

Replay, devlink, model import, and joint-domain simulation are intentionally out of scope for the bootstrap.

## Dependency Strategy

Third-party sources are vendored under `third_party/` and pinned by commit in [cmake/ThirdPartyVersions.cmake](/home/arjames/Coding/hexapod/software/simulation/cmake/ThirdPartyVersions.cmake).

## Runtime State

Local editor state is written under `.codex/editor/` when `.codex` is a directory. If `.codex` already exists as a plain file, the app falls back to `.simulation-state/editor/`.

- `imgui.ini`
- `prefs.json`
- `log.txt`

These files are runtime artifacts, not source-of-truth project data.
