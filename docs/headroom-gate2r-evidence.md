# Headroom Gate 2R Real-Package Evidence

Date: 2026-07-12
Host: CT106 / `Atlas`
Branch: `feature/headroom-integration-v1`

## Boundaries

- Synthetic non-secret input only.
- No provider API call.
- No live configuration change.
- No service restart, deployment, commit, or push.
- Live Headroom state before and after: `enabled=false`, `mode=off`.

## Runtime evidence

- Subprocess executable: `/home/hermes/services/headroom/venv/bin/python`.
- Headroom Python: 3.11.15.
- Distribution: `headroom-ai==0.25.0`.
- Package location: `/home/hermes/services/headroom/venv/lib/python3.11/site-packages`.
- Environment: `HEADROOM_TELEMETRY=off`, `HEADROOM_TELEMETRY_WARN=off`.
- `is_telemetry_enabled()`: `False`.
- API invoked by adapter worker: `headroom.transforms.log_compressor.LogCompressor.compress()`.

## Result

- Real-package subprocess invoked: yes.
- Subprocess completed: yes.
- Timeout: no.
- Exception: none.
- Duration: 232.53 ms.
- Input: 16,800 bytes.
- Headroom output: valid and non-empty, 16,800 bytes.
- Savings: 0 bytes; candidate rejected as `insufficient_savings`.
- Adapter sent/returned original context: yes.
- Original and final SHA-256 hashes matched: `043b6037ea22327395e9c391fee406ecdbbcb409ecbfacc366f3e3f5bf6a6990`.
- Optimized segments accepted: 0.
- Raw secret logging: none. Fixture contained only the repeated string `INFO synthetic repeated diagnostic line synthetic=true`; evidence stores only counts, status, paths and hashes.

## Disposition

The installed real package and documented API are executable within the 5-second adapter timeout. The package returned structurally valid non-empty output. Because the fixture did not benefit from compression, the minimum-savings validator correctly failed open with the original request. This closes the Gate 2 compatibility and fail-open evidence gap without enabling production compression.
