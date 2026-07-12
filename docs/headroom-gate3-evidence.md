# Headroom Gate 3 Observe Pilot Evidence

Date: 2026-07-12
Result: PARTIAL — no qualifying observe-mode sample

## Pre-change

- Config SHA-256: `61f70f21f26bdd210981961f5c80b06c5bb317bbeac767c12cb5ed2d5908e806`.
- Headroom: `enabled=false`, `mode=off`.
- Hermes gateway and MCP wrapper processes were running.
- `hermes-dashboard.service` was inactive and unrelated to the running gateway.
- Working tree contained only the approved uncommitted Gate 2/2R changes.

Backup: `/home/hermes/.hermes/config.yaml.headroom-gate3-20260712T135908-0400.bak`.

## Temporary configuration

The config was temporarily set to enabled/observe, telemetry disabled, fail-open enabled, raw logging disabled, 5000 ms timeout. No service was restarted. No production provider API was contacted.

## Attempts

1. Existing synthetic full-conversation test passed and reached mocked provider transport, but its fixture forced Headroom mode off. It was not counted.
2. Corrected temporary test instrumentation failed before mocked transport with a fixture-scope `NameError`; the helper still reported off mode. It was not counted.

Per the two-attempt limit, no further pilot attempt was made. The temporary test file was removed.

## Restoration

- The original config was restored byte-for-byte from the backup.
- Restored SHA-256: `61f70f21f26bdd210981961f5c80b06c5bb317bbeac767c12cb5ed2d5908e806` (match).
- Restored Headroom: `enabled=false`, `mode=off`.
- Baseline synthetic provider-transport test: 1 passed.
- Hermes gateway and MCP wrapper remained running.
- No service restart, deployment, commit, push, active mode, infrastructure change, or production provider call occurred.
