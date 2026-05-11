---
paths:
  - "docs/**"
  - "**/*.md"
  - "**/*.mdx"
  - "README*"
  - "mkdocs.yml"
  - "pyproject.toml"
  - "src/**"
  - "packages/**"
---

# Documentation rule

Use this rule when creating, updating, reviewing, or generating project documentation. The target result is a browsable documentation site, not only a README.

## Documentation goal

- Write documentation as a Wiki-style operation guide that a new user can open in a browser and follow step by step.
- Cover all major features, workflows, configuration files, modules, command-line entry points, and examples.
- Maintain a complete API reference for every public function, class, type, enum, dataclass, Pydantic model, TypedDict, protocol, exception, constant, and module entry point.
- Keep API documentation synchronized with source docstrings. If code has no docstring, add one before documenting the API.
- Do not invent behavior. Read the implementation, tests, examples, and existing docs before writing descriptions.
- If existing documentation tooling already exists, extend it instead of replacing it.

## Preferred documentation system

- If the project already uses MkDocs, Sphinx, Docusaurus, VitePress, TypeDoc, or another documentation system, keep using the existing system.
- If no documentation system exists and this is a Python project, prefer MkDocs + Material + mkdocstrings.
- The documentation must build into static HTML and be viewable locally in a browser.
- Add or update build commands in the docs, such as `mkdocs build`, `mkdocs serve`, `sphinx-build`, `npm run docs:build`, or the existing project-specific command.

## Required navigation structure

Create or maintain a navigation structure equivalent to this:

```yaml
nav:
  - Project overview:
      - Introduction: index.md
      - Design goals: overview/design-goals.md
      - Architecture: overview/architecture.md
  - Getting started:
      - Installation: getting-started/installation.md
      - Quickstart: getting-started/quickstart.md
      - Basic workflow: getting-started/workflow.md
  - User guide:
      - Configuration: guide/configuration.md
      - Common tasks: guide/tasks.md
      - Input and output: guide/io.md
      - Running and debugging: guide/running-and-debugging.md
  - Modules:
      - Module overview: modules/index.md
      - Module pages: modules/<module-name>.md
  - API reference:
      - API overview: api/index.md
      - Module API pages: api/<module-name>.md
  - Developer guide:
      - Code structure: developer/code-structure.md
      - Extending the project: developer/extending.md
      - Testing: developer/testing.md
```

Use the project’s actual module names and directory layout. For small projects, the tree may be shorter, but it must still contain project overview, basic workflow, module documentation, and API reference.

## Writing style

- Write documentation as practical instructions, not marketing copy.
- For every feature or module, explain:
  - what problem it solves;
  - when the user should use it;
  - the minimal working example;
  - required inputs and generated outputs;
  - important parameters and defaults;
  - common errors and debugging steps;
  - links to related modules and API reference.
- Prefer concrete statements over vague claims.
- Keep headings descriptive and scannable.
- Keep examples aligned with the current codebase.
- Mark pseudo-code explicitly. Do not present pseudo-code as runnable code.

## API reference requirements

The API reference must be complete. Do not document only the most common interfaces.

For every public function, document:

- purpose;
- full signature;
- parameter names, types, default values, units, and meaning;
- return type and return value meaning;
- raised exceptions;
- side effects, file I/O, network I/O, mutation, or global state changes;
- minimal usage example;
- related functions or classes.

For every public class or type, document:

- purpose and lifecycle;
- constructor parameters;
- attributes and properties;
- methods;
- invariants and validation rules;
- typical usage example;
- extension points, if any.

For every configuration object, document:

- field name;
- field type;
- whether it is required;
- default value;
- unit;
- allowed range or allowed values;
- example value;
- how it affects runtime behavior.

## Docstring requirements

- Treat docstrings as the source of truth for generated API documentation.
- Before generating API reference pages, inspect public functions, classes, and types for missing or stale docstrings.
- If a public API has no docstring, add one.
- If the docstring conflicts with implementation, tests, or examples, update the docstring and documentation to match the implementation.
- Preserve the project’s existing docstring style. If no style exists, use Google-style docstrings for Python.
- Docstrings should describe behavior, parameters, returns, exceptions, and important side effects. Do not paste large implementation details into docstrings.

Recommended Python docstring shape:

```python
def run_workflow(config_path: str) -> WorkflowResult:
    """Run a workflow from a configuration file.

    Args:
        config_path: Path to the workflow configuration file.

    Returns:
        The workflow result, including outputs, metadata, and generated artifacts.

    Raises:
        ConfigValidationError: If the configuration file is invalid.
        RuntimeError: If execution fails after validation.
    """
```

## Documentation workflow

When asked to write or update documentation:

1. Inspect the project structure before writing.
2. Identify source directories, public modules, CLI entry points, examples, tests, configuration files, and existing documentation tooling.
3. Build a module map that explains each module’s responsibility.
4. Check docstrings for all public APIs touched by the documentation task.
5. Add or fix missing docstrings before generating API reference pages.
6. Create or update user-facing guide pages.
7. Create or update module overview pages.
8. Create or update generated API reference pages.
9. Update the documentation navigation file.
10. Run the documentation build command.
11. Fix broken links, missing imports, invalid Markdown, and API rendering errors.
12. Report what changed and whether the documentation build passed.

## MkDocs + mkdocstrings convention

For Python projects using MkDocs, prefer API pages that use mkdocstrings instead of manually copying code signatures:

```markdown
# `package.module`

::: package.module
    options:
      show_source: true
      show_root_heading: true
      show_signature_annotations: true
      members_order: source
```

Create one API page per important module. Use `api/index.md` as the API reference landing page.

## Quality checklist

Before finishing a documentation task, verify:

- [ ] The documentation builds as a static site.
- [ ] The navigation contains project overview, getting started, basic workflow, modules, and API reference.
- [ ] All major features have operation-guide pages.
- [ ] Every public function is documented.
- [ ] Every public class and type is documented.
- [ ] Every configuration structure is documented.
- [ ] Missing public docstrings were added.
- [ ] API reference matches docstrings and implementation.
- [ ] Examples use real project names, paths, and parameters.
- [ ] Links are not broken.
- [ ] There are no unexplained TODO placeholders.
- [ ] The final response states the build command and whether it passed.

## Do not do this

- Do not only update `README.md` when the task requires full documentation.
- Do not write API reference from memory.
- Do not omit functions or types because they seem minor.
- Do not leave public APIs undocumented.
- Do not create documentation for functions, parameters, or config fields that do not exist.
- Do not replace an existing documentation framework without a clear reason.
- Do not claim the docs build passed unless the build command was actually run successfully.

## Final response format

When the documentation task is complete, summarize in this format:

```text
Completed documentation update:

- Updated: <files>
- Added: <files>
- Added or fixed docstrings: <files or symbols>
- API reference coverage: <modules covered>
- Local preview command: <command>
- Build result: <passed / failed, with reason>
- Remaining questions: <only if code behavior is genuinely unclear>
```
