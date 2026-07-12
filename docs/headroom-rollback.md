# Headroom Rollback

1. Set `headroom.enabled: false` and `headroom.mode: off` in the existing Hermes config.
2. Verify the loaded policy reports off and `HEADROOM_TELEMETRY=off` remains enforced.
3. Restore the timestamped pre-change config backup and verify its checksum, if configuration was changed. Gate 2 did not change live config.
4. Revert the isolated integration commit on `feature/headroom-integration-v1`, or remove the adapter call and files using Git.
5. Restart only the verified Hermes gateway user service, and only with explicit approval. Gate 2 performs no restart.
6. Run the synthetic full-conversation provider test and confirm the original request reaches the same mocked transport.
7. Run provider-routing and fallback regression tests and confirm no provider/model/fallback changes.
8. Make the Headroom environment unavailable in a test and verify Atlas continues with the original request.

## Gate 2 rehearsal

Rollback was rehearsed without modifying services: off-mode tests prove byte-identical passthrough; exception and timeout tests prove original-context fail-open; routing-field tests prove provider and fallback fields remain unchanged. No live configuration restoration or service restart was required or authorized.
