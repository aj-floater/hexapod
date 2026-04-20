# ADR 0001: Magnum Editor Stack

## Status

Accepted

## Context

The simulator needs a native C++ rendering shell that stays simple enough for a small sandbox, while remaining extensible toward a richer leg or robot editor later.

## Decision

Use:

- Corrade
- Magnum
- Magnum Integration
- SDL2
- Dear ImGui docking branch
- ImGuizmo

The application shell will be `Magnum::Platform::Sdl2Application` using Magnum's OpenGL renderer path.

## Consequences

- The first milestone can focus on editor behavior instead of low-level rendering setup.
- The stack stays portable and CMake-friendly.
- OpenGL remains the initial backend, which is acceptable for the current tooling-first milestone.
