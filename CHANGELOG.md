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
- Hardened `guide` and `add --explain/--schema` with provenance/defaulting guidance for authoring guardrails from source material
- Tightened `active` guardrail validation: active records now require an authoritative reference, at least one evidence-bearing `excerpt`, and a non-placeholder owner
- Documented the neutral placeholder workflow (`unassigned`) for draft records when accountable ownership is not stated by the source
- Expanded `README.md` with practical taxonomy guidance covering free-form vs controlled `scope`, bootstrap examples, validation behavior, and recommended team workflow
