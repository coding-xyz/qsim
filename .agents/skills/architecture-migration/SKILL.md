---
name: architecture-migration
description: Guides architecture migrations that change schemas, ownership boundaries, public APIs, persistence formats, or test contracts. Use when moving a codebase from one structural model to another and you must keep every layer synchronized.
---

# Architecture Migration

## Overview

This skill is for migrations where the shape of the system is changing:

- old container -> new container
- old ownership -> new ownership
- old API names -> new API names
- old persistence layout -> new persistence layout
- old tests -> new requirements

These migrations are dangerous because they often "mostly work" while leaving
the codebase internally inconsistent. The common failure mode is changing the
core schema in one place, then forgetting to update exports, consumers,
persistence, helper utilities, and tests.

This skill exists to prevent that half-migrated state.

## When to Use

Use this skill when any of the following is true:

- a core class is renamed, moved, or split
- ownership changes from one layer to another
- a field name or field meaning changes
- a public API export changes
- persistence layout or manifest structure changes
- tests should now reflect a new architecture rather than old implementation
- you are replacing an old object model with a new one

Examples:

- `model.results` -> `model.runs`
- run-scoped analyses -> model-level analyses
- `AnalysisResult` -> `ModelAnalysis`
- `input_result_ids` -> `input_run_ids`
- raw dict config -> typed config classes
- top-level fields -> `config/state/registry/runs/analyses`

## Core Principles

### 1. Migration Is a Whole-System Change

If a core architectural concept changes, you must assume every layer is affected.

The migration is not complete until all of these are checked:

- schema layer
- workflow/orchestration layer
- public exports
- persistence save path
- persistence load path
- UI/consumer code
- helper utilities
- tests
- compatibility shims

### 2. One New Truth, Zero Ambiguity

At the end of the migration, each concept must have:

- one canonical name
- one canonical home
- one canonical dependency direction

Do not leave two active peer models unless there is a deliberate compatibility
phase with explicit deprecation comments.

### 3. Tests Follow Requirements, Not Legacy Shape

If the architecture target is known, tests should be rewritten to that target.

Do not preserve old tests just because the old implementation still exists.
Legacy-structure tests are liabilities during migration.

### 4. Export Layers Are Part of the Architecture

Changing a schema without changing the package exports is not a complete
migration.

If a symbol moves or is renamed, check:

- `__init__.py`
- public re-exports
- user-facing import paths
- internal imports

### 5. Save/Load Is Part of the Contract

If a model changes in memory, persistence must be reevaluated immediately.

The migration is incomplete if:

- save writes the new structure but load returns old objects
- load returns dicts where runtime expects typed objects
- IDs or scopes mean different things before and after save/load

## The Migration Procedure

### Step 1: Write the Structural Delta

Before editing code, explicitly state:

```text
OLD:
- where the concept lived
- what it was called
- who depended on it

NEW:
- where the concept will live
- what it will be called
- who will depend on it
```

Minimum required questions:

1. What is changing?
2. What is the new canonical home?
3. What old name or home becomes invalid?
4. Which modules produce it?
5. Which modules consume it?
6. Which tests must change to the new requirement?

### Step 2: Identify Every Impacted Layer

Do not start patching until you enumerate every affected layer.

Use this checklist:

```text
[ ] Schema classes/dataclasses
[ ] Workflow/orchestration code
[ ] Public API exports
[ ] Persistence save path
[ ] Persistence load path
[ ] UI / notebook / summary consumers
[ ] Utility helpers
[ ] Tests
[ ] Compatibility layer or deprecation path
```

If any box is skipped, assume the migration is incomplete.

### Step 3: Update Producers First

Producers are the modules that create or write the new structure.

Examples:

- schema definitions
- workflow execution code
- model assembly code
- persistence save logic

Goal:

- new objects are produced consistently
- old structure is no longer written as primary output

### Step 4: Update Consumers Second

Consumers are modules that read or depend on the structure.

Examples:

- UI helpers
- notebook helpers
- result summaries
- persistence load logic
- helper utilities
- downstream workflow helpers

Goal:

- consumers read the new canonical structure directly
- consumers do not keep reading old field names or old homes

### Step 5: Update Public API Surface

Search for:

- package re-exports
- import aliases
- public names used by tests or examples

If a type changes from `AnalysisResult` to `ModelAnalysis`, resolve one of:

1. full rename everywhere
2. temporary compatibility alias with explicit deprecation

Never leave a broken export.

### Step 6: Update Persistence as a Pair

Save and load must be migrated together.

Required checks:

- save path writes the new hierarchy
- load path reconstructs the new hierarchy
- typed objects remain typed after reload
- IDs, scopes, and dependencies survive roundtrip

### Step 7: Rewrite Tests to the New Architecture

When architecture changes, test updates are not optional.

Classify tests into:

1. Keep as-is
Pure algorithm or isolated utility tests unaffected by structure

2. Rewrite
Tests that describe old structure but should now validate the new structure

3. Delete
Tests whose only purpose was to defend an architecture that is now obsolete

4. Add
New tests that assert the new architecture explicitly

## Mandatory Search Patterns

When performing an architecture migration, search for all of the following:

### Naming Search

- old class name
- new class name
- old field name
- new field name
- old container path
- new container path

### Ownership Search

Search for any old structural assumptions, such as:

- `model.results`
- `results.trajectories`
- `results.analyses`
- `ensure_solver`
- `trajectory_id`
- old top-level convenience fields

### Export Search

Search:

- `__init__.py`
- `__all__`
- package-level imports

### Consumer Search

Search all code that reads:

- analysis dependencies
- runtime metadata
- persistence payloads
- summary/report helpers
- UI/notebook entrypoints

### Test Search

Search tests for:

- old containers
- old field names
- old IDs
- old persistence layout
- old import paths

## Required Migration Invariants

At the end of the migration, all of these must be true:

### Invariant 1: Canonical Home

Each migrated concept has exactly one primary home.

Example:

- `ModelSpec` is primarily under `run.artifacts.model_spec`
- not also treated as an equal peer in `runtime_metadata`

### Invariant 2: Canonical Dependency Expression

Dependencies are expressed consistently.

Example:

- if analyses depend on runs, use `input_run_ids` everywhere
- do not leave some code reading `input_result_ids`

### Invariant 3: Canonical Export

Public modules export the current type names.

Example:

- package exports must not reference deleted or renamed symbols

### Invariant 4: Canonical Persistence

Saved structure and loaded structure represent the same architecture.

### Invariant 5: Canonical Tests

Tests validate the new architecture, not the old one.

## Architecture Migration Checklist

Use this checklist in every migration.

### A. Schema Layer

- [ ] Old types renamed or deprecated intentionally
- [ ] New types defined in canonical module
- [ ] Field names reflect new ownership semantics
- [ ] Comments/docstrings describe the new model, not the old one

### B. Workflow Layer

- [ ] Producers write only the new canonical structure
- [ ] Old duplicate writes are removed or marked compatibility-only
- [ ] IDs and scopes match the new design

### C. Export Layer

- [ ] `__init__.py` imports updated
- [ ] `__all__` updated
- [ ] no broken re-export remains

### D. Persistence Layer

- [ ] save path matches the new hierarchy
- [ ] load path reconstructs the new hierarchy
- [ ] no silent type degradation where it matters

### E. Consumer Layer

- [ ] notebook helpers updated
- [ ] UI/result summary helpers updated
- [ ] utility functions updated

### F. Test Layer

- [ ] obsolete structure tests removed or rewritten
- [ ] architecture tests validate the new hierarchy
- [ ] roundtrip tests validate new persistence shape
- [ ] no tests remain that require the old structure as primary truth

## Common Failure Modes

### Failure Mode 1: Renamed Type, Old Export

Example:

- schema now defines `ModelAnalysis`
- `workflow.__init__` still exports `AnalysisResult`

Result:

- import-time failures
- test collection failures
- confused public API

### Failure Mode 2: New Producer, Old Consumer

Example:

- producer writes `input_run_ids`
- UI still reads `input_result_ids`

Result:

- data exists but appears missing to consumers

### Failure Mode 3: New Save, Old Load

Example:

- save writes a hierarchical structure
- load returns legacy containers or raw dicts

Result:

- roundtrip breaks typed architecture

### Failure Mode 4: New Tests, Old Helpers

Example:

- tests assert `model.runs`
- helper utilities still assume `model.results`

Result:

- tests expose real migration incompleteness

This is a good failure. Fix the code, not the test, unless the requirement is wrong.

### Failure Mode 5: Compatibility Without Boundaries

Example:

- old and new field names both exist
- no comment marks which one is deprecated

Result:

- codebase drifts into permanent ambiguity

## What to Do When You Find a Conflict

When you discover old and new structures conflicting:

1. Stop adding new edits.
2. Name the specific conflict.
3. Decide the canonical structure.
4. Update producers, consumers, exports, and tests to that canonical structure.
5. Remove or quarantine the old shape.

Do not paper over the conflict by adding another adapter unless the adapter is
an explicit deprecation tool.

## Verification

Before declaring an architecture migration complete, verify:

- [ ] package imports succeed
- [ ] public exports point to real symbols
- [ ] tests describe the new structure
- [ ] save/load preserves the new structure
- [ ] no old primary container remains in active use
- [ ] UI/helpers consume the new field names
- [ ] exactly one canonical home exists for each migrated concept

## Short Prompt Version

Use this concise prompt when invoking the skill:

```text
Perform this as a full architecture migration, not a local patch.

1. State the old structure and new structure.
2. Identify every impacted layer: schema, workflow, exports, persistence, UI/helpers, tests.
3. Update producers first, then consumers.
4. Rewrite tests to the new requirement rather than preserving legacy structure.
5. Verify imports, exports, save/load, and consumer code all agree on the same model.
6. Do not leave old and new field names or containers as co-equal truths.
```
