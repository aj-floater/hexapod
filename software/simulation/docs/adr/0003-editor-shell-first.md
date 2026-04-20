# ADR 0003: Editor Shell First

## Status

Accepted

## Context

The long-term target is a single-joint simulator with future offline replay and live devlink integration, but those features depend on a usable inspection and manipulation shell.

## Decision

Build a viewer-only editor shell first with:

- a dockspace
- dockable viewport
- hierarchy
- inspector
- log
- snapping
- transform gizmo

No replay, devlink, model import, or joint-domain simulation logic is included in the bootstrap milestone.

## Consequences

- The project gets a usable operator-facing shell early.
- Rendering, editor interaction, and persistence can stabilize before simulation data flows are added.
