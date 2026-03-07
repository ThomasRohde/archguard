# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Project scaffold with full CLI command surface (stubbed)
- Pydantic data models for guardrails, references, links
- JSONL read/write/rewrite operations
- SQLite index schema with FTS5
- RRF scoring for hybrid search
- `init` command (functional)
- Test suite: models, store, index, search, CLI, property-based
- Documentation: README, PROJECT, ARCHITECTURE, TESTING, CONTRIBUTING, AGENTS

### Changed
- Aligned CLI process exit codes with `PRD.md` Section 12 and updated `guide`/README documentation to advertise the same contract
- Tuned `deduplicate` for short normative guardrails by lowering the default threshold to `0.65` and normalizing camelCase terms such as `apiVersion` consistently
- Reduced false-positive severity consistency warnings when RFC 2119 terms are being discussed as wording rather than used normatively
- Hardened `guide` and `add --explain/--schema` with provenance/defaulting guidance for authoring guardrails from source material
- Tightened `active` guardrail validation: active records now require an authoritative reference, at least one evidence-bearing `excerpt`, and a non-placeholder owner
- Documented the neutral placeholder workflow (`unassigned`) for draft records when accountable ownership is not stated by the source
- Expanded `README.md` with practical taxonomy guidance covering free-form vs controlled `scope`, bootstrap examples, validation behavior, and recommended team workflow
