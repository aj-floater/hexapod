# ADR 0002: Vendored Pinned Dependencies

## Status

Accepted

## Context

System packages for Magnum and related libraries are not available in the local environment, and reproducibility matters for AI-assisted iteration.

## Decision

Vendor all external dependencies into `third_party/` and pin them by commit SHA in `cmake/ThirdPartyVersions.cmake`.

## Consequences

- Builds are reproducible from repo state.
- AI agents can inspect dependency layout locally without hidden package-manager state.
- The repository size increases.
