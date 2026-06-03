# Publishing to PyPI

How to cut an Atlas OS release and publish it to [PyPI](https://pypi.org). This
is a maintainer runbook — end users just `pip install atlas-os` (or, in future,
`pipx install atlas-os`).

Atlas OS builds with [hatchling](https://hatch.pypa.io/). The package metadata
lives in [`pyproject.toml`](../pyproject.toml) and the version is single-sourced
from `__version__` in [`atlas_os/__init__.py`](../atlas_os/__init__.py).

## Prerequisites

```bash
pip install --upgrade build twine
```

You'll also need a [PyPI account](https://pypi.org/account/register/) and an
[API token](https://pypi.org/manage/account/token/) (scope it to the
`atlas-os` project once it exists; use an account-wide token for the very first
upload). Tokens are used as the password with username `__token__`.

## 1. Bump the version

Edit the single source of truth — `__version__` in `atlas_os/__init__.py`:

```python
__version__ = "0.4.0"   # was 0.3.0
```

`pyproject.toml` reads this automatically (`[tool.hatch.version]`), so the
package, the `atlas --version` output, and the published metadata all stay in
lockstep. Follow [SemVer](https://semver.org/): patch for fixes, minor for
backwards-compatible features, major for breaking changes.

Then move the `[Unreleased]` section of [`CHANGELOG.md`](../CHANGELOG.md) under a
new `## [0.4.0] — YYYY-MM-DD` heading.

## 2. Pre-flight checks

Run the same gates CI does, so a release never ships broken:

```bash
ruff check scripts tests atlas_os
pytest
pip-audit -r requirements.txt
```

## 3. Build the distributions

```bash
rm -rf dist/
python -m build
```

This produces two artefacts in `dist/`:

- `atlas_os-<version>.tar.gz` — the source distribution (sdist)
- `atlas_os-<version>-py3-none-any.whl` — the built wheel

The wheel force-includes the operational data dirs (`scripts/`, `schemas/`,
`templates/`, `skills/`) into a top-level `atlas_os_data/` package so an
installed `atlas` command works without the source checkout (see
[`atlas_os/_paths.py`](../atlas_os/_paths.py)). Sanity-check that the skills made
it in:

```bash
unzip -l dist/atlas_os-*.whl | grep 'atlas_os_data/skills'
tar tzf dist/atlas_os-*.tar.gz | grep 'skills/.*SKILL.md'
```

## 4. Validate the metadata

```bash
twine check dist/*
```

Both files should report `PASSED`. This catches a malformed long description
(rendered from `README.md`) before PyPI rejects it.

## 5. Upload to TestPyPI first (recommended)

Dry-run the whole flow against [TestPyPI](https://test.pypi.org/) so a typo
doesn't burn a real version number (PyPI never lets you re-upload a version):

```bash
twine upload --repository testpypi dist/*
# then, in a throwaway venv:
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ atlas-os
atlas --version
```

## 6. Upload to PyPI

```bash
twine upload dist/*
# username: __token__
# password: pypi-…    (your API token)
```

Prefer a non-interactive token via environment variables in CI:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-your-token-here
twine upload dist/*
```

## 7. Tag the release

```bash
git tag -a v0.4.0 -m "Atlas OS 0.4.0"
git push origin v0.4.0
```

Then create a GitHub Release from the tag, pasting the relevant CHANGELOG
section.

## Verify the published package

```bash
pip install --upgrade atlas-os
atlas --version          # should print the new version
atlas skills list        # operational data dirs are bundled and discoverable
```

---

> **Automating it.** Once you're comfortable, move steps 3–6 into a GitHub
> Actions workflow triggered on `v*` tags, using
> [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) so
> no token is stored in the repo.
