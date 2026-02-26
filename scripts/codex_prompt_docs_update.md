# Codex Prompt: Update Docstring + Wiki + API Reference

Use this prompt in Codex whenever code changes require synchronized documentation updates.

```
Task: Update documentation consistently after code changes.

Scope:
1) Review and improve docstrings in:
   - src/qsim/analysis/*.py
   - src/qsim/qec/*.py
2) Update wiki pages in docs/wiki and docs/WIKI.md to reflect current behavior.
3) Update API reference entry pages in docs/api.
4) Ensure mkdocs nav includes wiki and api links for qec/analysis.
5) Keep wording concise and technical; do not invent unimplemented behavior.

Acceptance checklist:
- [ ] Docstrings are complete for public functions/classes (args/returns/behavior).
- [ ] docs/wiki/overview.md reflects current pipeline outputs.
- [ ] docs/wiki/qec_analysis.md exists and is up to date.
- [ ] docs/api/analysis.md and docs/api/qec.md exist and are up to date.
- [ ] docs/api/index.md links analysis and qec pages.
- [ ] mkdocs.yml nav contains wiki/qec_analysis and api/qec entries.
- [ ] mkdocs build --clean succeeds.

After editing:
1) Run:
   - $env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; pytest -q -p no:cacheprovider
   - $env:PYTHONDONTWRITEBYTECODE='1'; mkdocs build --clean
2) Provide a short report:
   - changed files
   - test result
   - docs build result
   - remaining risks
```
