# Domain Concepts

## Guardrail

A named, scoped architectural constraint. Says: "When making an architectural decision in *this context*, *this rule* applies."

Guardrails have three severity levels following RFC 2119:
- **must** -- Mandatory. Violation requires formal exception process.
- **should** -- Strongly recommended. Deviation requires documented rationale.
- **may** -- Advisory. Recommended practice, not enforced.

## Reference

An external citation linking a guardrail to its authoritative source: ADR, policy, standard, regulation, pattern, or document.

## Link

A typed relationship between two guardrails:
- **supports** -- Guardrail A reinforces guardrail B
- **conflicts** -- Guardrail A and B are in tension
- **refines** -- Guardrail A is a more specific version of B
- **implements** -- Guardrail A is a concrete implementation of B

## Scope

The architectural domain a guardrail applies to. Values come from `taxonomy.json`:
`channels`, `relationships`, `business-support`, `products-services`, `business-control`, `risk-management`, `organisational-support`, `it-platform`, `data-platform`

## Lifecycle

Guardrails have a status lifecycle: `draft` -> `active` -> `deprecated` / `superseded`

No delete. The governance audit trail matters.

## Structured validation

A "check" takes a proposed decision (with scope, applies_to, lifecycle_stage) and surfaces all matching guardrails grouped by severity. The CLI does not judge compliance -- it surfaces what is relevant.
