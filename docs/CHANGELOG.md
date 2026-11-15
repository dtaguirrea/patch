# Changelog

## 2026-11-15 · English interface and emergency pathways

- Translated interface, validation messages, built-in prompts, scenario descriptions, new report text and documentation to English.
- Required both explicit responsiveness and normal-breathing answers before every interview entry point.
- Added immediate guidance previews for NO answers without treating unconfirmed selections as recorded evidence.
- Added deterministic, sourced adult emergency branches for the three NO combinations and urgent clarification of unknown findings.
- Added emergency reassessment that updates instructions while preserving CRITICAL and the interview block.
- Included guidance provenance in immutable outbound snapshots; older or superseded checks require reassessment.
- Kept the one-button simulation clock, recorded cases, original scenarios and delayed transport.
- Preserved historical records rather than translating or rewriting evidence.
- No tests added or test suites executed.

## 2026-11-15 · Recorded cases and guided interface

- Imported C01/C02 from supplied JSON recordings, with ten/eight response turns respectively; Case 3 contained no files.
- Added case_data with source identifiers and hashes, without running the notebooks.
- Added persisted workflow phases and backend ordering guards.
- Replaced multiple simulation controls with one time-advance button and adjustable increment.
- Kept recorded values as crew_reported with unknown observation time; did not fabricate demographic or telemetry history.

## 2026-11-14 · Initial MVP

- Completed the application scaffold, two-state HSM, N02/N04/N06 scenarios, SQLite persistence and one-way packet transport.
- Added deterministic interview mock, observations with provenance, SBAR handoffs and JSON export.
- Added Windows/Unix launchers and documentation.
