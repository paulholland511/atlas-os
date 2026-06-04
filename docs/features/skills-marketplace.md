# Feature: Skills Marketplace / Community Registry

**Source:** [`atlas_os/marketplace.py`](../../atlas_os/marketplace.py),
[`skills/registry.json`](../../skills/registry.json) ·
**CLI:** `atlas skills search` · `atlas skills publish` · `atlas skills registry`

The marketplace turns Atlas OS skills from *files in this repo* into something
**shareable across installs** — search a registry, package a skill to share, and
add community registries to discover skills others have published. It builds on
the [skills framework](../SKILLS-FRAMEWORK.md): a skill is still a `SKILL.md`
folder; the marketplace adds the registry, validation, packaging, and dependency
plumbing around it.

---

## Concepts

- **Registry** — a JSON document (`registry.json`) listing skills with discovery
  metadata. The built-in registry ships in `skills/registry.json` and is always
  searched. Add more with `atlas skills registry add <url>`.
- **Entry** — one skill in a registry: `name`, `version`, `description`,
  `author`, `tags`, `dependencies`, `download_url`.
- **Manifest** — the schema-validated metadata generated into a skill's package
  (`manifest.json`) when you publish it.
- **Package** — a `<name>-<version>.tar.gz` containing the `manifest.json` plus
  the skill's files, rooted under a top-level `<name>/` directory.

---

## The registry format

```json
{
  "schema_version": 1,
  "name": "Atlas OS Built-in Skills",
  "description": "The skills that ship with Atlas OS …",
  "skills": [
    {
      "name": "vault-lint-report",
      "version": "1.0.0",
      "description": "Vault health check — orphans, dead links, stale claims.",
      "author": "Atlas OS",
      "tags": ["vault", "lint", "maintenance", "health"],
      "dependencies": [],
      "download_url": "https://github.com/paulholland511/atlas-os/tree/main/skills/vault-lint-report"
    }
  ]
}
```

- `schema_version` — readers refuse a registry from a newer major than they
  understand, and tolerate a missing field for forward compatibility.
- `name` (in each entry) must be a folder-slug: lowercase letters, digits, and
  hyphens.
- `version` is lenient semver (`MAJOR.MINOR.PATCH`, optional `-pre`/`+build`).
- `tags` and `dependencies` are lists of strings.

---

## Search

```bash
atlas skills search trading        # match name / description / tags
atlas skills search vault
atlas skills search                # empty query → list everything
```

Search runs across **every** configured registry (the built-in one is always
included), de-duplicated by skill name (first registry wins). A registry that's
unreachable or malformed is reported as a warning and skipped — it never aborts
the search of the registries that did load.

---

## Registries

Configured registries live in `$VAULT_PATH/.atlas/registries.json` (override the
path with `ATLAS_REGISTRIES_PATH`; falls back to `./.atlas/registries.json`). The
built-in registry is implicit and never written to the file.

```bash
atlas skills registry add https://example.com/skills/registry.json
atlas skills registry add ./team-registry.json     # a local path works too
atlas skills registry list                          # show configured registries + counts
```

---

## Publishing a skill

`publish` validates a skill folder against the schema and packages it for
sharing. Point it at a folder containing a `SKILL.md`:

```bash
atlas skills publish ./my-skill                     # → dist/skills/my-skill-1.0.0.tar.gz
atlas skills publish ./my-skill --output ~/share    # custom output directory
```

Validation reports **every** problem at once:

- the folder exists and contains a `SKILL.md` with a YAML frontmatter block;
- `name` and `description` are present and non-empty;
- `name` is a valid slug;
- any `version` is semver; any `tags` / `dependencies` are lists of strings.

On success it writes `<name>-<version>.tar.gz` with a generated `manifest.json`
plus the skill's files (VCS/OS cruft and prior `.tar.gz` builds are excluded).
Upload that archive somewhere durable and point a registry entry's
`download_url` at it.

A publishable `SKILL.md` can carry the extra marketplace frontmatter:

```yaml
---
name: my-skill
version: 1.2.0
description: What this skill does, in one line.
author: Your Name
tags: [research, email]
dependencies: [topic-research-brief]
---
```

---

## Dependencies

A skill may declare `dependencies` on other skills.
`SkillRegistry.resolve_dependencies(name)` returns the full install order —
dependencies first, the target last — and raises `DependencyError` on a missing
dependency or a cycle. This lets a registry express "install *these* skills
before this one" without the CLI having to special-case it.

---

## Invariants & tests

- Every entry in the built-in `registry.json` must resolve to a real skill folder
  under `skills/` — `marketplace.validate_builtin_registry()` enforces this and
  the test-suite (`tests/test_marketplace.py`) asserts it, so a stale or typo'd
  entry fails CI rather than at install time.
- All registry/packaging logic is pure data + small I/O helpers, so the test
  suite exercises it with no network and no real vault.

See the [CLI reference](../CLI-REFERENCE.md#atlas-skills) for the exact flags and
exit codes, and the [Skills Framework](../SKILLS-FRAMEWORK.md#the-skills-marketplace)
for how the marketplace fits the broader skill lifecycle.
