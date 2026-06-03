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

## Automated publishing (GitHub Actions + Trusted Publishing)

The manual runbook above is the fallback. The normal path is automated:
**push a `v*` tag and GitHub Actions builds, tests, and publishes to PyPI** —
no stored token, no `twine upload` from your laptop.

This uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC). Instead of a long-lived API token sitting in the repo, GitHub mints a
short-lived identity token for each run; PyPI trusts it because of a one-time
trusted-publisher config you add on pypi.org tying the project to this exact
repo + workflow + environment. Nothing secret is stored anywhere.

The workflows live in [`.github/workflows/`](../.github/workflows):

- **`publish.yml`** — triggers on `v*` tags (e.g. `v0.4.0`). Runs `test` →
  `build` → `publish`. The publish job uses the `pypi` environment and
  `id-token: write`, and only runs for a real tag push (not manual dispatch).
- **`test-publish.yml`** — triggers on pre-release tags (`v*rc*`, `v*dev*`,
  e.g. `v0.4.0rc1`). Identical, but publishes to **TestPyPI** using the
  `testpypi` environment. Use it to rehearse the whole flow safely.

### One-time PyPI setup (Paul — do this before the first release)

Trusted publishing must be configured **before** the first upload. You have two
options:

**Option A — pending publisher (recommended; no manual upload needed).**
PyPI lets you pre-register a trusted publisher for a project that *doesn't exist
yet*. The first time the workflow runs, PyPI creates the project and binds it.

1. Sign in to <https://pypi.org> → your account → **Publishing** (or go directly
   to <https://pypi.org/manage/account/publishing/>).
2. Under **Add a new pending publisher**, fill in:
   - **PyPI Project Name:** `atlas-os`
   - **Owner:** `paulholland511`
   - **Repository name:** `atlas-os`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. Save. The first `v*` tag push will create and publish the project.

**Option B — manual first upload, then configure.**
If you'd rather claim the name immediately:

1. Do one manual `twine upload dist/*` (steps 1–6 above) to create the
   `atlas-os` project on PyPI.
2. Then on the project: **Manage → Publishing → Add a new publisher**, with the
   same values as Option A (Owner `paulholland511`, Repo `atlas-os`, Workflow
   `publish.yml`, Environment `pypi`).
3. From then on, tags publish automatically; you never need a token again.

**For TestPyPI** (to use `test-publish.yml`): repeat the same on
<https://test.pypi.org/manage/account/publishing/>, but set the **Environment
name** to `testpypi`.

> **GitHub environments.** The `pypi` (and `testpypi`) environment names in the
> workflows don't need to pre-exist — GitHub creates them on first use. If you
> want a manual approval gate before a release goes out, create the `pypi`
> environment under the repo's **Settings → Environments** and add yourself as a
> required reviewer.

### The release flow, end to end

```bash
# 1. Bump the single source of truth
#    edit atlas_os/__init__.py:  __version__ = "0.4.0"

# 2. Move CHANGELOG [Unreleased] under ## [0.4.0] — YYYY-MM-DD, then commit
git add atlas_os/__init__.py CHANGELOG.md
git commit -m "Release 0.4.0"
git push origin main

# 3. Tag and push — this is what triggers the publish
git tag -a v0.4.0 -m "Atlas OS 0.4.0"
git push origin v0.4.0
```

GitHub Actions takes it from there: lint + tests run, the sdist and wheel are
built and `twine check`ed, and the publish job uploads to PyPI via OIDC. Watch
it under the repo's **Actions** tab. To rehearse first, tag `v0.4.0rc1` and push
— that routes to TestPyPI via `test-publish.yml`.

After it's green, create a GitHub Release from the tag and paste the CHANGELOG
section, then verify:

```bash
pip install --upgrade atlas-os
atlas --version          # should print the new version
```
