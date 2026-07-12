# Headroom Gate 3R Evidence

Date: 2026-07-12
Result: PARTIAL

- Live config was not modified; checksum remained `61f70f21f26bdd210981961f5c80b06c5bb317bbeac767c12cb5ed2d5908e806`, `enabled=false`, `mode=off`.
- Temporary purpose-built agent config explicitly used `enabled=true`, `mode=observe`, telemetry disabled, fail-open enabled and raw logging disabled.
- Mock transport was reached; no real provider API was contacted.
- Headroom metrics were captured with `mode=observe`, `original_context_used=true`, `bypass_reason=no_eligible_content`, original/optimized token estimates 2843/2843, zero optimized segments and sub-millisecond adapter duration.
- Metrics contained only structured fields and no synthetic context body.
- Attempt 1 failed before conversation because the test agent has no direct `messages` attribute.
- Attempt 2 completed the conversation and mock transport, but the test assertion expected flat `content`; Codex Responses uses nested content, so exact payload equality was not mechanically proven.
- The temporary test was removed. No service restart, active mode, infrastructure change, commit or push occurred.
