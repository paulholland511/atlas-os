"""Pre-built **skill packs** — curated bundles of related skills.

A *pack* groups skills that together set up a complete workflow, so you can
install an entire workflow with one command (``atlas skills install-pack
<name>``) instead of installing each skill one at a time. Packs reference skills
by their folder slug; :func:`install_pack` simply runs the per-skill installer
(:func:`atlas_os._skills.install_skill`) for every member, with the same
``{{PLACEHOLDER}}`` substitution.

The registry below is the single source of truth. Each pack's ``skills`` must
name real skills under ``skills/`` — :func:`validate_packs` checks this and the
test-suite asserts it, so a typo'd slug fails CI rather than at install time.
"""

from __future__ import annotations

from dataclasses import dataclass

from atlas_os._skills import (
    InstallResult,
    SkillInstallError,
    SkillNotFoundError,
    find_skill,
    install_skill,
    skills_install_root,
)


@dataclass(frozen=True)
class Pack:
    """One installable bundle of related skills."""

    name: str
    description: str
    skills: tuple[str, ...]  # skill folder slugs, install order


# ── Registry ──────────────────────────────────────────────────────────────────
# Pack name → Pack. Skill slugs must match folders under skills/ (validated).
PACKS: dict[str, Pack] = {
    "knowledge": Pack(
        name="knowledge",
        description=(
            "Vault management — nightly commit & index, incremental and full RAG "
            "re-embedding, twice-daily Cowork session capture (morning + "
            "afternoon), lint reports, and the weekly knowledge digest."
        ),
        skills=(
            "nightly-obsidian-index",
            "nightly-rag-incremental",
            "weekly-rag-full-reembed",
            "morning-session-capture",
            "afternoon-session-capture",
            "vault-lint-report",
            "weekly-digest-report",
        ),
    ),
    "communication": Pack(
        name="communication",
        description=(
            "Email & reporting — the daily morning report email, inbox-triage "
            "digest, and on-demand vault report documents."
        ),
        skills=(
            "atlas-daily-report-email",
            "inbox-triage-digest",
            "generate-vault-report-doc",
        ),
    ),
    "trading": Pack(
        name="trading",
        description=(
            "Trading intelligence — the daily trading report and on-demand "
            "topic research briefs."
        ),
        skills=(
            "daily-trading-report",
            "topic-research-brief",
        ),
    ),
}


class PackNotFoundError(LookupError):
    """Raised when a pack name is not in the registry."""


def find_pack(name: str) -> Pack | None:
    """Return the pack with this name, or None."""
    return PACKS.get(name)


def load_packs() -> list[Pack]:
    """Return every pack, sorted by name."""
    return [PACKS[name] for name in sorted(PACKS)]


def validate_packs() -> list[tuple[str, str]]:
    """Return ``(pack, slug)`` pairs that reference a skill that doesn't exist.

    An empty list means every pack member resolves to a real skill.
    """
    missing: list[tuple[str, str]] = []
    for pack in load_packs():
        for slug in pack.skills:
            if find_skill(slug) is None:
                missing.append((pack.name, slug))
    return missing


@dataclass(frozen=True)
class PackInstallResult:
    """Outcome of installing a pack — what landed and what was skipped."""

    pack: str
    installed: list[InstallResult]
    skipped: list[tuple[str, str]]  # (slug, reason)


def install_pack(
    name: str, *, env: dict[str, str] | None = None, force: bool = False
) -> PackInstallResult:
    """Install every skill in a pack, filling placeholders from the environment.

    Raises :class:`PackNotFoundError` for an unknown pack and
    :class:`atlas_os._skills.SkillInstallError` when there's no install target at
    all. Per-skill problems (an unknown slug, or an already-installed skill when
    ``force`` is False) are collected into ``skipped`` so one bad member never
    aborts the whole pack.
    """
    pack = find_pack(name)
    if pack is None:
        raise PackNotFoundError(name)

    # Fail fast on a pack-wide problem (no target) rather than skipping every
    # skill with the same error.
    if skills_install_root(env) is None:
        raise SkillInstallError(
            "no install target — set ATLAS_SKILLS_DIR or VAULT_PATH (run `atlas init`)"
        )

    installed: list[InstallResult] = []
    skipped: list[tuple[str, str]] = []
    for slug in pack.skills:
        try:
            installed.append(install_skill(slug, env=env, force=force))
        except SkillNotFoundError:
            skipped.append((slug, "unknown skill — not in this Atlas OS install"))
        except SkillInstallError as exc:
            skipped.append((slug, str(exc)))

    return PackInstallResult(pack=pack.name, installed=installed, skipped=skipped)
