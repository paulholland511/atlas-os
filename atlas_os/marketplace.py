"""The skills **marketplace** — share, discover, and install community skills.

A skill is a ``SKILL.md`` prompt (plus any sidecar files) living in its own
folder (see :mod:`atlas_os._skills`). The marketplace adds the plumbing to turn
those folders into something shareable:

* a **registry** — a JSON document (``registry.json``) listing skills with
  metadata (name, version, description, author, tags, dependencies, and a
  download URL). Registries live in the repo's ``skills/`` directory, on GitHub
  releases, or anywhere reachable by file path or URL;
* **search** — keyword/tag matching across one or more configured registries;
* **publish** — validate a skill folder against the schema and package it into a
  ``.tar.gz`` with a ``manifest.json``, ready to upload to a registry;
* **dependency resolution** — a skill's manifest may declare dependencies on
  other skills; :meth:`SkillRegistry.resolve_dependencies` returns the full
  install order (dependencies first), detecting missing deps and cycles.

Everything here is pure data + small I/O helpers built on
:mod:`atlas_os.netio` (for URL fetches) so the CLI layer stays thin and the
logic stays testable without a network or a real vault.
"""

from __future__ import annotations

import io
import json
import os
import re
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from atlas_os import netio
from atlas_os._paths import skills_dir
from atlas_os._skills import _parse_frontmatter, find_skill

# The schema version this code reads/writes. Bumped only on a breaking change to
# the registry/manifest layout; readers tolerate a missing field for forward
# compatibility but refuse a registry from a newer major than they understand.
SCHEMA_VERSION = 1

# Required SKILL.md frontmatter fields for a publishable skill.
_REQUIRED_FIELDS: tuple[str, ...] = ("name", "description")

# A skill name is a folder-slug: lowercase letters, digits, and hyphens.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Lenient semver: major.minor.patch with an optional pre-release / build suffix.
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")

# The default registry, shipped in the repo. The literal string ``"builtin"`` is
# a sentinel resolved to this path by :func:`resolve_registry_source`.
DEFAULT_REGISTRY = "builtin"


# ── Errors ──────────────────────────────────────────────────────────────────--
class RegistryError(RuntimeError):
    """A registry document is missing, unreadable, or malformed."""


class SkillValidationError(ValueError):
    """A skill folder failed schema validation. Carries the list of problems."""

    def __init__(self, target: str, problems: list[str]) -> None:
        self.target = target
        self.problems = problems
        joined = "; ".join(problems)
        super().__init__(f"{target}: {joined}")


class DependencyError(RuntimeError):
    """A skill's dependencies are missing from the registry, or form a cycle."""


# ── Registry entries ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RegistryEntry:
    """One skill listed in a registry, with its discovery metadata."""

    name: str
    version: str
    description: str
    author: str
    tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    download_url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryEntry:
        """Build an entry from a registry's JSON object, validating shape."""
        if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise RegistryError(f"skill entry is not an object: {data!r}")
        name = str(data.get("name") or "").strip()
        if not name:
            raise RegistryError("skill entry is missing a 'name'")
        return cls(
            name=name,
            version=str(data.get("version") or "0.0.0").strip(),
            description=str(data.get("description") or "").strip(),
            author=str(data.get("author") or "unknown").strip(),
            tags=_str_tuple(data.get("tags")),
            dependencies=_str_tuple(data.get("dependencies")),
            download_url=str(data.get("download_url") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to a registry JSON object (stable key order)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": list(self.tags),
            "dependencies": list(self.dependencies),
            "download_url": self.download_url,
        }

    def matches(self, query: str) -> bool:
        """True if ``query`` (case-insensitive) hits the name, description, or a tag."""
        q = query.strip().lower()
        if not q:
            return True
        if q in self.name.lower() or q in self.description.lower():
            return True
        return any(q in tag.lower() for tag in self.tags)


# ── Registry ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SkillRegistry:
    """A parsed registry: its name, where it came from, and its skill entries."""

    name: str
    description: str
    source: str
    entries: tuple[RegistryEntry, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str = "") -> SkillRegistry:
        """Parse a registry document, rejecting an unknown future schema major."""
        if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise RegistryError(f"registry is not a JSON object (source: {source})")
        version = data.get("schema_version", SCHEMA_VERSION)
        if not isinstance(version, int) or version > SCHEMA_VERSION:
            raise RegistryError(
                f"unsupported registry schema_version {version!r} "
                f"(this build understands up to {SCHEMA_VERSION})"
            )
        raw_skills = data.get("skills", [])
        if not isinstance(raw_skills, list):
            raise RegistryError("registry 'skills' must be a list")
        entries = tuple(RegistryEntry.from_dict(s) for s in raw_skills)
        return cls(
            name=str(data.get("name") or "unnamed registry").strip(),
            description=str(data.get("description") or "").strip(),
            source=source,
            entries=entries,
        )

    @classmethod
    def from_file(cls, path: Path) -> SkillRegistry:
        """Load a registry from a local JSON file."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RegistryError(f"cannot read registry file {path}: {exc}") from exc
        return cls._from_text(text, source=str(path))

    @classmethod
    def from_url(cls, url: str) -> SkillRegistry:
        """Fetch and parse a registry over HTTP(S)."""
        try:
            data = netio.get_json(url, service="Skill registry")
        except netio.NetworkError as exc:
            raise RegistryError(str(exc)) from exc
        if not isinstance(data, dict):
            raise RegistryError(f"registry at {url} did not return a JSON object")
        return cls.from_dict(data, source=url)

    @classmethod
    def _from_text(cls, text: str, *, source: str) -> SkillRegistry:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RegistryError(f"registry {source} is not valid JSON: {exc}") from exc
        return cls.from_dict(data, source=source)

    def find(self, name: str) -> RegistryEntry | None:
        """Return the entry with this name, or None."""
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def search(self, query: str) -> list[RegistryEntry]:
        """Return matching entries, sorted by name."""
        return sorted(
            (e for e in self.entries if e.matches(query)), key=lambda e: e.name
        )

    def resolve_dependencies(self, name: str) -> list[str]:
        """Return the install order for ``name`` — dependencies first, then itself.

        Raises :class:`DependencyError` if ``name`` (or any transitive
        dependency) is absent from this registry, or if the dependencies form a
        cycle.
        """
        order: list[str] = []
        visiting: set[str] = set()
        done: set[str] = set()

        def visit(target: str, trail: tuple[str, ...]) -> None:
            if target in done:
                return
            if target in visiting:
                cycle = " → ".join((*trail, target))
                raise DependencyError(f"dependency cycle: {cycle}")
            entry = self.find(target)
            if entry is None:
                via = trail[-1] if trail else target
                raise DependencyError(
                    f"unknown skill {target!r}"
                    + (f" (required by {via!r})" if trail else "")
                    + f" — not in registry {self.name!r}"
                )
            visiting.add(target)
            for dep in entry.dependencies:
                visit(dep, (*trail, target))
            visiting.discard(target)
            done.add(target)
            order.append(target)

        visit(name, ())
        return order


# ── Registry sources / configuration ────────────────────────────────────────--
def builtin_registry_path() -> Path:
    """Path to the registry shipped in the repo's ``skills/`` directory."""
    return skills_dir() / "registry.json"


def registries_path(env: dict[str, str] | None = None) -> Path:
    """Resolve the configured-registries file path from the environment.

    Order: ``ATLAS_REGISTRIES_PATH`` → ``$VAULT_PATH/.atlas/registries.json`` →
    ``./.atlas/registries.json`` — mirroring how the audit log is located.
    """
    environ = os.environ if env is None else env
    override = environ.get("ATLAS_REGISTRIES_PATH")
    if override:
        return Path(os.path.expanduser(override))
    vault = environ.get("VAULT_PATH")
    base = Path(os.path.expanduser(vault)) if vault else Path.cwd()
    return base / ".atlas" / "registries.json"


def resolve_registry_source(source: str) -> Path | str:
    """Expand a configured source to a concrete path or URL.

    The :data:`DEFAULT_REGISTRY` sentinel resolves to the bundled registry; a
    ``http://`` / ``https://`` source is returned unchanged; anything else is
    treated as a local file path (``~`` expanded).
    """
    if source == DEFAULT_REGISTRY:
        return builtin_registry_path()
    if urlsplit(source).scheme in ("http", "https"):
        return source
    return Path(os.path.expanduser(source))


def load_registry_sources(env: dict[str, str] | None = None) -> list[str]:
    """Return the configured registry sources, newest last.

    With no config file (the common case), this is just ``[DEFAULT_REGISTRY]``.
    Added registries are appended, and the built-in always comes first so a
    custom registry can shadow nothing it shouldn't.
    """
    path = registries_path(env)
    if not path.is_file():
        return [DEFAULT_REGISTRY]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot read registries config {path}: {exc}") from exc
    extra = data.get("registries", []) if isinstance(data, dict) else []
    sources = [DEFAULT_REGISTRY]
    for src in extra:
        text = str(src).strip()
        if text and text != DEFAULT_REGISTRY and text not in sources:
            sources.append(text)
    return sources


def add_registry(url: str, env: dict[str, str] | None = None) -> list[str]:
    """Add a registry source to the config, returning the updated source list.

    The built-in registry is implicit and never written to the file. A duplicate
    (or the ``builtin`` sentinel) is a no-op. The config file and its parent
    directory are created on first use.
    """
    text = url.strip()
    if not text:
        raise RegistryError("registry URL/path is empty")
    if text == DEFAULT_REGISTRY:
        raise RegistryError("the built-in registry is always present")

    path = registries_path(env)
    existing: list[str] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"cannot read registries config {path}: {exc}") from exc
        if isinstance(data, dict):
            existing = [str(s).strip() for s in data.get("registries", []) if str(s).strip()]

    if text not in existing:
        existing.append(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"registries": existing}, indent=2) + "\n", encoding="utf-8"
    )
    return [DEFAULT_REGISTRY, *existing]


def load_registry(source: str) -> SkillRegistry:
    """Load a single registry by source string (sentinel, path, or URL)."""
    resolved = resolve_registry_source(source)
    if isinstance(resolved, Path):
        return SkillRegistry.from_file(resolved)
    return SkillRegistry.from_url(resolved)


@dataclass(frozen=True)
class RegistryLoad:
    """The outcome of loading one configured registry — its data, or its error."""

    source: str
    registry: SkillRegistry | None
    error: str | None = None


def load_all_registries(env: dict[str, str] | None = None) -> list[RegistryLoad]:
    """Load every configured registry, capturing per-source errors.

    One unreachable or malformed registry never aborts the others — its failure
    is recorded in :class:`RegistryLoad.error` so the CLI can report it and carry
    on with the registries that did load.
    """
    loads: list[RegistryLoad] = []
    for source in load_registry_sources(env):
        try:
            loads.append(RegistryLoad(source=source, registry=load_registry(source)))
        except RegistryError as exc:
            loads.append(RegistryLoad(source=source, registry=None, error=str(exc)))
    return loads


@dataclass(frozen=True)
class SearchHit:
    """A search match, paired with the registry it came from."""

    entry: RegistryEntry
    registry_name: str
    source: str


def search_registries(
    query: str, env: dict[str, str] | None = None
) -> tuple[list[SearchHit], list[RegistryLoad]]:
    """Search every configured registry for ``query``.

    Returns the matching hits (de-duplicated by skill name, first registry wins)
    sorted by name, and the list of registry loads so the caller can surface any
    that failed.
    """
    loads = load_all_registries(env)
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for load in loads:
        if load.registry is None:
            continue
        for entry in load.registry.search(query):
            if entry.name in seen:
                continue
            seen.add(entry.name)
            hits.append(
                SearchHit(
                    entry=entry,
                    registry_name=load.registry.name,
                    source=load.source,
                )
            )
    hits.sort(key=lambda h: h.entry.name)
    return hits, loads


# ── Manifest ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SkillManifest:
    """The manifest packaged alongside a skill — its schema-validated metadata."""

    name: str
    version: str
    description: str
    author: str
    tags: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the ``manifest.json`` object (stable key order)."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": list(self.tags),
            "dependencies": list(self.dependencies),
        }

    def to_registry_entry(self, download_url: str = "") -> RegistryEntry:
        """Project this manifest into a registry entry."""
        return RegistryEntry(
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            tags=self.tags,
            dependencies=self.dependencies,
            download_url=download_url,
        )


# ── Validation & packaging ────────────────────────────────────────────────────
def _str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce a JSON list-of-strings into a tuple, dropping blanks."""
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value if str(v).strip())


def _frontmatter_problems(meta: dict[str, object]) -> list[str]:
    """Collect schema problems in a SKILL.md's parsed frontmatter."""
    problems: list[str] = []
    for required in _REQUIRED_FIELDS:
        value = meta.get(required)
        if not (isinstance(value, str) and value.strip()):
            problems.append(f"missing or empty required field {required!r}")

    name = meta.get("name")
    if isinstance(name, str) and name.strip() and not _NAME_RE.match(name.strip()):
        problems.append(
            f"name {name!r} is not a valid slug (lowercase letters, digits, hyphens)"
        )

    version = meta.get("version")
    if version is not None and not (
        isinstance(version, str) and _VERSION_RE.match(version.strip())
    ):
        problems.append(f"version {version!r} is not semver (e.g. 1.0.0)")

    for list_field in ("tags", "dependencies"):
        value = meta.get(list_field)
        if value is not None and not (
            isinstance(value, list) and all(isinstance(v, str) for v in value)  # pyright: ignore[reportUnknownVariableType]
        ):
            problems.append(f"{list_field!r} must be a list of strings")

    return problems


def manifest_from_frontmatter(meta: dict[str, object]) -> SkillManifest:
    """Build a :class:`SkillManifest` from validated frontmatter (no checks here)."""
    return SkillManifest(
        name=str(meta["name"]).strip(),
        version=str(meta.get("version") or "0.1.0").strip(),
        description=str(meta["description"]).strip(),
        author=str(meta.get("author") or "unknown").strip(),
        tags=_str_tuple(meta.get("tags")),
        dependencies=_str_tuple(meta.get("dependencies")),
    )


def validate_skill(skill_dir: Path) -> SkillManifest:
    """Validate a skill folder against the schema, returning its manifest.

    Checks that the folder exists, contains a ``SKILL.md`` with parseable
    frontmatter, and that the frontmatter carries the required fields with valid
    shapes. Raises :class:`SkillValidationError` listing *every* problem found,
    so a publisher can fix them in one pass rather than one at a time.
    """
    target = str(skill_dir)
    if not skill_dir.is_dir():
        raise SkillValidationError(target, ["not a directory"])

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SkillValidationError(target, ["no SKILL.md in skill folder"])

    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SkillValidationError(target, ["SKILL.md has no YAML frontmatter block"])
    meta = _parse_frontmatter(text)
    if not meta:
        raise SkillValidationError(
            target, ["SKILL.md frontmatter is empty or not valid YAML"]
        )

    problems = _frontmatter_problems(meta)
    if problems:
        raise SkillValidationError(target, problems)

    return manifest_from_frontmatter(meta)


@dataclass(frozen=True)
class PublishResult:
    """The outcome of packaging a skill — its manifest and the archive path."""

    manifest: SkillManifest
    archive: Path
    files: tuple[str, ...] = field(default=())


# Files never shipped in a skill package (VCS/OS cruft, prior builds).
_PACKAGE_EXCLUDE: frozenset[str] = frozenset(
    {".git", ".DS_Store", "__pycache__", "manifest.json"}
)


def _package_members(skill_dir: Path) -> list[Path]:
    """Every file to include in the archive, sorted, excluding cruft."""
    members: list[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(skill_dir).parts)
        if parts & _PACKAGE_EXCLUDE or path.name.endswith(".tar.gz"):
            continue
        members.append(path)
    return members


def package_skill(skill_dir: Path, output_dir: Path) -> PublishResult:
    """Validate and package a skill folder into ``<name>-<version>.tar.gz``.

    The archive contains a generated ``manifest.json`` plus the skill's files,
    all rooted under a top-level ``<name>/`` directory so it unpacks cleanly.
    Raises :class:`SkillValidationError` if the skill doesn't pass validation.
    """
    manifest = validate_skill(skill_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive = output_dir / f"{manifest.name}-{manifest.version}.tar.gz"
    manifest_bytes = (
        json.dumps(manifest.to_dict(), indent=2) + "\n"
    ).encode("utf-8")

    included: list[str] = [f"{manifest.name}/manifest.json"]
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(f"{manifest.name}/manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for member in _package_members(skill_dir):
            arcname = f"{manifest.name}/{member.relative_to(skill_dir).as_posix()}"
            tar.add(member, arcname=arcname)
            included.append(arcname)

    return PublishResult(
        manifest=manifest, archive=archive, files=tuple(included)
    )


# ── Built-in registry validation ──────────────────────────────────────────────
def validate_builtin_registry() -> list[str]:
    """Return registry entry names that don't resolve to a real shipped skill.

    An empty list means every entry in the bundled ``registry.json`` names a
    skill folder that exists under ``skills/`` — the invariant the test-suite
    asserts so a typo'd or stale entry fails CI rather than at install time.
    """
    registry = SkillRegistry.from_file(builtin_registry_path())
    return [e.name for e in registry.entries if find_skill(e.name) is None]
