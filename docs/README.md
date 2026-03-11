# Documentation Maintenance

This project keeps documentation in two directories with different roles:

- `docs/src`: source of truth (Markdown and generation scripts)
- `docs/site`: build output (generated static site)

## Rules

1. Edit only `docs/src` (and `mkdocs.yml` when needed).
2. Do not manually edit files under `docs/site`.
3. After any doc change, rebuild site output:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; mkdocs build --clean
```

4. Commit `docs/src` and the regenerated `docs/site` together so they stay in sync.
