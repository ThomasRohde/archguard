# Prompt: Scaffold a Project from `PRD.md`

Use the prompt below with a coding agent to read a `PRD.md` file and scaffold a project repository, including the recommended files and built-in guidance for how humans should complete any missing details.

---

## Recommended use

Give the agent this prompt in a repository that contains a `PRD.md` at the root.  
The agent should then inspect `PRD.md`, choose a reasonable project structure, create the starter files, and place clear fill-in guidance where the PRD does not yet specify enough.

---

## The prompt

```text
You are a senior software architect and staff engineer. Your job is to scaffold a new project from a single source document: `PRD.md`.

Your goal is not just to create code folders. Your goal is to create a repo that is easy for humans and AI coding agents to steer correctly.

Read `PRD.md` carefully and treat it as the primary source of truth.

## Core behavior

1. Infer the project type, likely stack, repo layout, and delivery shape from `PRD.md`.
2. Scaffold the repository accordingly.
3. Create the recommended operating files listed below.
4. Where `PRD.md` is incomplete or ambiguous, do **not** invent high-confidence details.
5. Instead, create sensible placeholders and add short, concrete guidance in the files explaining exactly what should be filled in.
6. Prefer a lean, practical scaffold over an over-engineered one.
7. Reuse conventions that fit the project type.
8. Make the repo immediately usable by both humans and coding agents.

## Non-negotiable rules

- Do not hallucinate product decisions that are not supported by `PRD.md`.
- If something is missing, mark it clearly as `TODO:` or `TBD:`.
- Every placeholder must include guidance, examples, or decision criteria.
- Keep guidance short and actionable.
- If the PRD implies a specific stack, use it.
- If the PRD does not specify a stack, choose the simplest credible stack and document why in `ARCHITECTURE.md`.
- Prefer convention over novelty.
- Optimize for maintainability, testability, and agent-readability.
- Do not create empty files unless they contain useful guidance.

## Deliverables

Create or update the following where appropriate for the project type.

### 1) Repository structure
Scaffold a sensible top-level layout, for example:
- `src/` or language-appropriate source folders
- `tests/`
- `docs/`
- `.github/`
- config files for the chosen stack
- package/build files
- developer environment files where relevant

Choose the simplest professional structure that fits the PRD.

### 2) Core human-readable project files

Create these files with useful starter content:

- `README.md`
- `PROJECT.md`
- `ARCHITECTURE.md`
- `TESTING.md`
- `CONTRIBUTING.md`
- `SECURITY.md` if relevant
- `CHANGELOG.md`
- `DECISIONS/ADR-0001-initial-architecture.md`
- `docs/DOMAIN.md` if the project contains significant domain concepts
- `docs/GLOSSARY.md` if the PRD uses specialized terminology
- `docs/ROADMAP.md`

### 3) Agent-readable guidance files

Create these files with concrete instructions for coding agents:

- `AGENTS.md`
- `.github/copilot-instructions.md`
- `.github/instructions/backend.instructions.md` if backend exists
- `.github/instructions/frontend.instructions.md` if frontend exists
- `.github/instructions/testing.instructions.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- issue templates if appropriate

### 4) Development and quality files

Create the quality and workflow baseline for the chosen stack, such as:

- formatter config
- linter config
- test runner config
- type checker config if applicable
- `.editorconfig`
- `.gitignore`
- CI workflow in `.github/workflows/ci.yml`

Only create what is appropriate for the inferred stack.

## Required content guidance per file

### `README.md`
Include:
- what the project is
- who it is for
- current status
- quick start
- repo structure summary
- how to run tests
- how to contribute

If missing from the PRD, add `TODO:` markers with short guidance.

### `PROJECT.md`
Include:
- problem statement
- target users
- goals
- non-goals
- scope boundaries
- constraints
- assumptions
- success criteria
- open questions

Use crisp bullets. If the PRD is weak on scope, make that visible.

### `ARCHITECTURE.md`
Include:
- chosen stack and rationale
- major components/modules
- boundaries and responsibilities
- key data flows
- external dependencies
- architectural constraints
- quality attributes
- trade-offs
- known unknowns

Where choices are inferred, label them as provisional.

### `TESTING.md`
Include:
- testing strategy
- test pyramid or equivalent approach
- required commands
- coverage expectations if appropriate
- what must be tested for each PR
- how AI agents should validate their changes before completion

### `CONTRIBUTING.md`
Include:
- branch/PR workflow
- code style expectations
- commit expectations
- review checklist
- how to propose architectural changes
- instructions for updating docs and tests with code changes

### `AGENTS.md`
This is critical. Include:
- project overview in agent-friendly terms
- where to look first
- what files are authoritative
- coding rules
- architectural invariants
- what not to change casually
- how to run validation
- how to handle ambiguity
- when to stop and leave a `TODO:` instead of guessing
- expected output style for code, docs, and PRs

### `.github/copilot-instructions.md`
Include:
- repo-wide implementation guidance
- naming conventions
- preferred patterns
- testing expectations
- documentation expectations
- “follow existing patterns before introducing new abstractions”

### Path-specific `.instructions.md` files
Include rules tailored to the relevant area, for example:
- backend conventions
- frontend conventions
- testing conventions
- API conventions
- persistence conventions

### `ADR-0001-initial-architecture.md`
Write the first ADR that records:
- the initial project shape
- the inferred stack
- why this shape was chosen from the PRD
- what remains provisional

### `docs/ROADMAP.md`
Include:
- suggested milestone breakdown
- likely workstreams
- risks and dependencies
- a note distinguishing confirmed items from inferred items

## Guidance style requirements

Whenever you create placeholders, use this pattern:

- `TODO: <what is missing>`
- `Why it matters: <one sentence>`
- `How to fill this in: <one or two concrete instructions>`
- `Example: <optional short example>`

Keep placeholders genuinely useful. Do not write vague filler.

## Scaffolding strategy

1. Read `PRD.md`.
2. Summarize the implied project type in 5–10 bullets.
3. Choose the minimal credible stack.
4. Scaffold the repo.
5. Create the recommended files.
6. Populate each file with the best available content from the PRD.
7. Add guided placeholders where information is missing.
8. Create a short final report in `docs/SCAFFOLDING-NOTES.md` containing:
   - what was inferred from the PRD
   - what was scaffolded
   - what still needs human input
   - the highest-risk ambiguities

## If code generation is appropriate

If the PRD is strong enough to justify starter code, create only a thin vertical skeleton:
- app entry point
- config
- one sample feature/module
- basic tests
- build/run scripts

Do not generate lots of speculative business logic.

## Output expectations

At the end, provide:
1. the created file tree
2. a concise summary of architectural choices
3. a list of assumptions
4. a list of `TODO`s requiring human review

Be disciplined, practical, and explicit about uncertainty.
```

---

## What this prompt is designed to produce

This prompt is designed to make the agent create a repo that is:

- usable immediately
- steerable by humans
- readable by other agents
- explicit about ambiguity
- light on hallucinated decisions
- strong on scaffolding and operating guidance

It is intentionally opinionated in one way: when the PRD is incomplete, the agent should create **guided blanks**, not fake certainty.

---

## Suggested companion input

For best results, place these at repo root before running the prompt:

- `PRD.md`
- optional `stack-preferences.md`
- optional `constraints.md`
- optional `domain-notes.md`

That will materially improve the scaffold quality.

---

## Suggested extension

A useful follow-up prompt after the scaffold is:

> Read `PRD.md`, `PROJECT.md`, `ARCHITECTURE.md`, `AGENTS.md`, and `docs/SCAFFOLDING-NOTES.md`.  
> Now turn the scaffold into an implementation plan by creating epics, thin slices, and issue-ready tasks with acceptance criteria.
