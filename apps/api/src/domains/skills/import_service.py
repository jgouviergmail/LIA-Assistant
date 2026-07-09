"""Skill import service — single hardened pipeline for all import paths.

Every way a skill enters LIA converges here:

- HTTP upload of a ``SKILL.md`` or ``.zip`` (user + admin endpoints)
- Direct import from chat via the ``import_user_skill`` tool (skill-generator)

Centralizing the pipeline closes a class of bugs that the previous
router-local logic carried (audited 2026-07-09):

- **S1 — path traversal**: the frontmatter ``name`` was concatenated into the
  destination path and ``mkdir``-ed without validation, so ``name: ../../system/x``
  let any authenticated user overwrite a *system* skill. Names are now validated
  against the agentskills.io pattern **before** any filesystem write.
- **S2 — cross-scope collision**: ``skills.name`` is globally unique, so a user
  importing a name owned by a system skill or another user silently rewrote the
  other's DB row (and skipped state creation). User imports that would shadow a
  system skill or collide with another user are now rejected (409).
- **S3 — zip expansion**: no decompressed-size / member-count guard (zip-bomb)
  and ``extractall`` wrote the *whole* archive even though only one skill root
  was validated. Extraction is now bounded and scoped to the SKILL.md subtree.
- **S4 — validation divergence**: the importer was lenient while the generator's
  ``validate_skill.py`` was strict. Both now enforce the same name contract.

The pipeline stages into a temp directory, validates fully, and only then
atomically swaps into the live skills tree — a failed import never damages an
existing skill.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import yaml

from src.core.constants import (
    SKILLS_DESCRIPTION_MAX_LENGTH,
    SKILLS_IMPORT_TEXT_EXTENSIONS,
    SKILLS_MAX_FILE_SIZE_KB,
    SKILLS_NAME_MAX_LENGTH,
)
from src.domains.skills.exceptions import (
    raise_skill_file_too_large,
    raise_skill_invalid_format,
    raise_skill_name_conflict,
    raise_skill_quota_exceeded,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# agentskills.io name contract (mirrors loader.SKILL_NAME_PATTERN and the
# generator's validate_skill.py — the three MUST agree; a parity test pins it).
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_CONSECUTIVE_HYPHENS = re.compile(r"--")
_RESERVED_PREFIXES = ("claude", "anthropic")


def validate_skill_name(name: str) -> None:
    """Validate a skill name against the agentskills.io contract.

    This is the S1 traversal guard: the pattern admits only ``[a-z0-9-]``, so
    any path separator (``/``, ``\\``) or ``..`` segment fails here — long
    before the name reaches a filesystem path.

    Args:
        name: Candidate skill name (from SKILL.md frontmatter).

    Raises:
        ValidationError: 400 when the name violates the contract.
    """
    if not name or not isinstance(name, str):
        raise_skill_invalid_format("Skill 'name' is required in frontmatter")
    if len(name) < 2 or len(name) > SKILLS_NAME_MAX_LENGTH:
        raise_skill_invalid_format(
            f"Skill name must be 2-{SKILLS_NAME_MAX_LENGTH} characters (got {len(name)})"
        )
    if not _SKILL_NAME_PATTERN.match(name):
        raise_skill_invalid_format(
            f"Skill name '{name}' is invalid — use lowercase letters, digits and "
            "single hyphens only (pattern [a-z0-9][a-z0-9-]*[a-z0-9])"
        )
    if _CONSECUTIVE_HYPHENS.search(name):
        raise_skill_invalid_format(f"Skill name '{name}' contains consecutive hyphens")
    for prefix in _RESERVED_PREFIXES:
        if name.startswith(prefix):
            raise_skill_invalid_format(f"Skill name '{name}' uses reserved prefix '{prefix}'")


def _parse_frontmatter_name(text: str) -> str:
    """Extract and return the ``name`` from raw SKILL.md text.

    Args:
        text: Full SKILL.md content (frontmatter + body).

    Returns:
        The frontmatter ``name`` value.

    Raises:
        ValidationError: 400 when the frontmatter is missing or malformed.
    """
    if not text.startswith("---"):
        raise_skill_invalid_format("SKILL.md must start with YAML frontmatter (---)")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise_skill_invalid_format("Invalid YAML frontmatter (missing closing ---)")
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise_skill_invalid_format(f"Invalid YAML in frontmatter: {exc}")
    if not isinstance(meta, dict):
        raise_skill_invalid_format("YAML frontmatter must be a mapping (key: value pairs)")
    name = meta.get("name")
    if not isinstance(name, str) or not name:
        raise_skill_invalid_format("SKILL.md frontmatter must declare a non-empty 'name'")
    return name


class SkillImportService:
    """Hardened, transactional import pipeline shared by every import path.

    Instantiated per request/tool-call with the current ``AsyncSession``.
    Filesystem writes are confined to a temp staging area until validation
    passes, then atomically swapped into the live tree.
    """

    def __init__(self, db: AsyncSession) -> None:
        from src.domains.skills.repository import SkillRepository

        self.db = db
        self.skill_repo = SkillRepository(db)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def import_upload(
        self,
        content: bytes,
        filename: str,
        *,
        owner_id: UUID | None,
        is_system: bool,
    ) -> dict[str, Any]:
        """Import from an uploaded ``SKILL.md`` or ``.zip`` archive.

        Args:
            content: Raw uploaded bytes.
            filename: Original filename (only its ``.zip`` suffix is used).
            owner_id: Importing user's id (``None`` for system/admin imports).
            is_system: True for admin (system) imports, False for user imports.

        Returns:
            The parsed skill dict (safe subset) for the API response.

        Raises:
            BaseAPIException / ValidationError: on any size, format, name,
                conflict or quota violation.
        """
        from src.core.config import get_settings

        settings = get_settings()
        if len(content) > SKILLS_MAX_FILE_SIZE_KB * 1024:
            raise_skill_file_too_large(len(content), SKILLS_MAX_FILE_SIZE_KB)

        with tempfile.TemporaryDirectory(prefix="skill_import_") as staging_root:
            staging = Path(staging_root)
            # Offload the blocking extraction / file writes off the event loop (CA-4).
            if filename.endswith(".zip"):
                name = await asyncio.to_thread(self._stage_zip, content, staging, settings)
            else:
                name = await asyncio.to_thread(self._stage_single_md, content, staging)
            return await self._finalize(
                staging / name, name, owner_id=owner_id, is_system=is_system, settings=settings
            )

    async def import_files(
        self,
        files: dict[str, str],
        *,
        owner_id: UUID,
    ) -> dict[str, Any]:
        """Import from an in-memory map of relative path → text content.

        This is the chat-driven path (``import_user_skill`` tool). Only text
        files are accepted — binary assets cannot transit as tool-call string
        arguments. Always a user (non-system) import.

        Args:
            files: Mapping of POSIX-relative path to UTF-8 text content. Must
                include a top-level ``SKILL.md``.
            owner_id: Importing user's id.

        Returns:
            The parsed skill dict (safe subset).

        Raises:
            BaseAPIException / ValidationError: on any format, name, conflict,
                size or quota violation.
        """
        from src.core.config import get_settings

        settings = get_settings()
        skill_md = files.get("SKILL.md")
        if not skill_md:
            raise_skill_invalid_format("import must include a top-level 'SKILL.md' file")

        name = _parse_frontmatter_name(skill_md)
        validate_skill_name(name)

        with tempfile.TemporaryDirectory(prefix="skill_import_") as staging_root:
            skill_dir = Path(staging_root) / name
            # Offload the blocking file writes off the event loop (CA-4).
            await asyncio.to_thread(self._write_text_files, files, skill_dir, settings)
            return await self._finalize(
                skill_dir, name, owner_id=owner_id, is_system=False, settings=settings
            )

    # ------------------------------------------------------------------
    # Staging (S1 + S3): lay a validated skill out under a temp directory
    # ------------------------------------------------------------------

    def _stage_single_md(self, content: bytes, staging: Path) -> str:
        """Stage a bare SKILL.md upload. Returns the validated skill name."""
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise_skill_invalid_format("SKILL.md must be a valid UTF-8 text file")

        name = _parse_frontmatter_name(text)
        validate_skill_name(name)

        skill_dir = staging / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
        return name

    def _stage_zip(self, content: bytes, staging: Path, settings: Any) -> str:
        """Stage a .zip package with expansion + traversal guards (S3).

        Only the subtree rooted at the SKILL.md's parent is extracted, keyed
        under the *validated frontmatter name* (not the archive's folder name).
        Returns the validated skill name.
        """
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]

                # Guard: member count + total decompressed size (zip bomb).
                if len(infos) > settings.skills_zip_max_files:
                    raise_skill_invalid_format(
                        f"Package has too many files (max {settings.skills_zip_max_files})"
                    )
                total = sum(i.file_size for i in infos)
                if total > settings.skills_zip_max_decompressed_kb * 1024:
                    raise_skill_invalid_format(
                        "Package decompressed size exceeds "
                        f"{settings.skills_zip_max_decompressed_kb}KB"
                    )

                skill_md = next((i for i in infos if i.filename.endswith("SKILL.md")), None)
                if skill_md is None:
                    raise_skill_invalid_format("No SKILL.md found in zip")

                # Root prefix inside the archive (empty for a flat zip).
                prefix = str(Path(skill_md.filename).parent)
                prefix = "" if prefix in (".", "") else prefix + "/"

                # Read + validate the name before writing anything to disk.
                raw = zf.read(skill_md.filename)
                if raw.startswith(b"\xef\xbb\xbf"):
                    raw = raw[3:]
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise_skill_invalid_format("SKILL.md must be a valid UTF-8 text file")
                name = _parse_frontmatter_name(text)
                validate_skill_name(name)

                skill_dir = (staging / name).resolve()
                skill_dir.mkdir(parents=True)

                # Extract only the members under the skill root, re-anchored to
                # skill_dir, with a per-member zip-slip check. Members outside
                # the root (multi-root archives) are deliberately dropped — the
                # warning below keeps that visible instead of silent.
                skipped: list[str] = []
                for info in infos:
                    if prefix and not info.filename.startswith(prefix):
                        skipped.append(info.filename)
                        continue
                    rel = info.filename[len(prefix) :] if prefix else info.filename
                    if not rel:
                        continue
                    dest = (skill_dir / rel).resolve()
                    try:
                        dest.relative_to(skill_dir)
                    except ValueError:
                        raise_skill_invalid_format("Zip contains path traversal entries")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                if skipped:
                    logger.warning(
                        "skill_zip_members_outside_root_skipped",
                        skill_name=name,
                        skipped_count=len(skipped),
                        sample=skipped[:5],
                    )
        except zipfile.BadZipFile:
            raise_skill_invalid_format("Invalid zip file")
        return name

    def _write_text_files(self, files: dict[str, str], skill_dir: Path, settings: Any) -> None:
        """Write a text-only file map into the staging skill dir (chat path).

        Enforces relative paths, allowed text extensions, and the same
        decompressed-size budget as zip imports.
        """
        allowed = SKILLS_IMPORT_TEXT_EXTENSIONS
        budget = settings.skills_zip_max_decompressed_kb * 1024
        if len(files) > settings.skills_zip_max_files:
            raise_skill_invalid_format(f"Too many files (max {settings.skills_zip_max_files})")
        skill_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        skill_dir_resolved = skill_dir.resolve()
        for rel_path, text in files.items():
            rel = Path(rel_path)
            if rel.is_absolute() or ".." in rel.parts:
                raise_skill_invalid_format(f"Invalid file path '{rel_path}'")
            if rel.suffix.lower() not in allowed:
                raise_skill_invalid_format(
                    f"File type '{rel.suffix}' not allowed for chat import "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
            total += len(text.encode("utf-8"))
            if total > budget:
                raise_skill_invalid_format(
                    f"Total content exceeds {settings.skills_zip_max_decompressed_kb}KB"
                )
            dest = (skill_dir / rel).resolve()
            try:
                dest.relative_to(skill_dir_resolved)
            except ValueError:
                raise_skill_invalid_format(f"Invalid file path '{rel_path}'")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")

    # ------------------------------------------------------------------
    # Finalize (S2 + S4): conflict check, content validation, commit, register
    # ------------------------------------------------------------------

    async def _finalize(
        self,
        staged_skill_dir: Path,
        name: str,
        *,
        owner_id: UUID | None,
        is_system: bool,
        settings: Any,
    ) -> dict[str, Any]:
        """Validate the staged skill, then commit it to the live tree + DB."""
        from src.domains.skills.cache import SkillsCache
        from src.domains.skills.loader import parse_skill_file
        from src.domains.skills.preference_service import SkillPreferenceService

        # S4 — content validation (description present, no XML, parseable).
        # Blocking read → offload off the event loop (CA-4).
        skill = await asyncio.to_thread(parse_skill_file, staged_skill_dir / "SKILL.md")
        if not skill:
            raise_skill_invalid_format(
                "SKILL.md validation failed (missing description or invalid format)"
            )
        desc = skill.get("description", "")
        if len(desc) > SKILLS_DESCRIPTION_MAX_LENGTH:
            raise_skill_invalid_format(
                f"Description exceeds {SKILLS_DESCRIPTION_MAX_LENGTH} characters"
            )

        # S2 — conflict + quota. Admin import is trusted and intentionally
        # overwrites system skills, but must not capture a USER-owned name
        # (the DB row would silently flip scope).
        if is_system:
            await self._check_admin_conflict(name)
        else:
            await self._check_user_conflict(name, owner_id)
            await self._check_quota(owner_id, name, settings)

        # Disk swap: the previous version (if any) is parked in the staging
        # root — outside the scanned skills tree, auto-cleaned with it — so a
        # failure at ANY later step can restore it byte-for-byte.
        base_dir = (
            Path(settings.skills_system_path)
            if is_system
            else Path(settings.skills_users_path) / str(owner_id)
        )
        base_dir.mkdir(parents=True, exist_ok=True)
        target_dir = base_dir / name
        backup_dir = staged_skill_dir.parent / "__previous__"
        # Blocking disk swap → offload off the event loop (CA-4).
        await asyncio.to_thread(self._swap_in, staged_skill_dir, target_dir, backup_dir)

        # Rebase source_path onto the live location for the response.
        skill["source_path"] = str(target_dir / "SKILL.md")

        # DB register + commit. On failure the disk is rolled back to the
        # previous version (or removed for a fresh import) — the live tree and
        # the DB never diverge on an error path.
        try:
            svc = SkillPreferenceService(self.db)
            await svc.create_skill_for_import(
                name=name,
                description=desc or name,
                is_system=is_system,
                owner_id=owner_id,
                descriptions=skill.get("descriptions"),
            )
            await self.db.commit()
        except ValueError:
            # Identity guard in create_skill_for_import: a concurrent import
            # won the name between our conflict check and the flush. Restore
            # the disk and answer the same 409 as the up-front check.
            await asyncio.to_thread(self._roll_back_disk, target_dir, backup_dir)
            raise_skill_name_conflict(name)
        except Exception:
            await asyncio.to_thread(self._roll_back_disk, target_dir, backup_dir)
            raise

        await SkillsCache.invalidate_and_reload()

        logger.info(
            "skill_import_committed",
            skill_name=name,
            is_system=is_system,
            owner_id=str(owner_id) if owner_id else None,
        )
        return skill

    @staticmethod
    def _swap_in(staged_skill_dir: Path, target_dir: Path, backup_dir: Path) -> None:
        """Replace ``target_dir`` with the staged directory, keeping a backup.

        The previous version is MOVED to ``backup_dir`` (inside the staging
        temp root) instead of being deleted: if the incoming move fails, it is
        restored, so a failed re-import can never destroy the existing skill.
        Called via ``asyncio.to_thread``.
        """
        if target_dir.exists():
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            shutil.move(str(target_dir), str(backup_dir))
        try:
            shutil.move(str(staged_skill_dir), str(target_dir))
        except Exception:
            if backup_dir.exists():
                shutil.move(str(backup_dir), str(target_dir))
            raise

    @staticmethod
    def _roll_back_disk(target_dir: Path, backup_dir: Path) -> None:
        """Undo :meth:`_swap_in` after a post-swap failure (DB register/commit).

        Removes the newly placed directory and restores the backup when one
        exists (re-import case). Called via ``asyncio.to_thread``.
        """
        shutil.rmtree(target_dir, ignore_errors=True)
        if backup_dir.exists():
            shutil.move(str(backup_dir), str(target_dir))

    async def _check_admin_conflict(self, name: str) -> None:
        """Reject an admin import whose name is already owned by a user skill.

        ``skills.name`` is globally unique: registering a system skill under a
        user-owned name would silently flip the existing row's scope.
        Re-importing an existing system skill is allowed (upsert). The DB is
        the registration authority; the cache adds the disk view.
        """
        from src.domains.skills.cache import SkillsCache

        row = await self.skill_repo.get_by_name(name)
        if row and not row.is_system:
            raise_skill_name_conflict(name)
        for s in SkillsCache.get_all():
            if s["name"] == name and s["scope"] == "user":
                raise_skill_name_conflict(name)

    async def _check_user_conflict(self, name: str, owner_id: UUID | None) -> None:
        """Reject a user import that shadows a system skill or another user (S2).

        A user re-importing their *own* skill of the same name is allowed
        (upsert). The existence of another user's skill is not disclosed — the
        same 409 is raised for system-shadow and cross-user collision. The DB
        row is the registration authority; the cache adds the disk view.
        """
        from src.domains.skills.cache import SkillsCache

        row = await self.skill_repo.get_by_name(name)
        if row and (row.is_system or row.owner_id != owner_id):
            raise_skill_name_conflict(name)

        owner_str = str(owner_id) if owner_id else None
        for s in SkillsCache.get_all():
            if s["name"] != name:
                continue
            if s["scope"] == "admin":
                raise_skill_name_conflict(name)
            if s.get("owner_id") not in (None, owner_str):
                raise_skill_name_conflict(name)

    async def _check_quota(self, owner_id: UUID | None, name: str, settings: Any) -> None:
        """Reject when the user is at their imported-skill cap.

        Re-importing an existing own skill (``name`` already counted) is
        always allowed — it does not create a new skill. The count is the
        union of the DB registration view and the disk (cache) view.
        """
        from src.domains.skills.cache import SkillsCache

        owner_str = str(owner_id) if owner_id else None
        owned: set[str] = {
            s["name"] for s in SkillsCache.get_all() if s.get("owner_id") == owner_str
        }
        if owner_id is not None:
            owned |= {row.name for row in await self.skill_repo.get_user_skills(owner_id)}
        if name in owned:
            return
        if len(owned) >= settings.skills_max_per_user:
            raise_skill_quota_exceeded(owner_str or "unknown", settings.skills_max_per_user)
