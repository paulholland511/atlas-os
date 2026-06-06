# atlas-os (deprecated → eidetic-os)

**`atlas-os` has been renamed to [`eidetic-os`](https://pypi.org/project/eidetic-os/).**

This package on PyPI is now a deprecation stub. It contains no code of its own —
it simply depends on `eidetic-os` and emits a `DeprecationWarning` when imported,
so existing installs keep working while you migrate.

## What you should do

```bash
pip uninstall atlas-os
pip install eidetic-os
```

Then use the new name everywhere:

- **CLI:** `eidetic …` (was `atlas …`)
- **Package import:** `import eidetic_os` (was `import atlas_os`)
- **Environment variables:** `EIDETIC_*` (was `ATLAS_*`)
- **State directory:** `.eidetic/` (was `.atlas/`)

Eidetic OS migrates legacy state for you on first run: it copies an existing
`.atlas/` directory to `.eidetic/` and maps any `ATLAS_*` environment variables
to their `EIDETIC_*` equivalents, printing a deprecation notice for each.

## Why the rename?

The project was renamed Atlas OS → Eidetic OS in the v4.0 cycle. See the
[main project README](https://github.com/paulholland511/atlas-os#why-we-renamed)
for the full story.

## This stub

Installing `atlas-os` pulls in `eidetic-os` as a dependency and nothing else.
Importing `atlas_os` raises:

```
DeprecationWarning: The 'atlas-os' package has been renamed to 'eidetic-os'.
Please run 'pip install eidetic-os' as this legacy package is deprecated.
```

Build and publish this stub from this directory (`legacy-pypi-stub/`), which has
its own `pyproject.toml` independent of the main package.
