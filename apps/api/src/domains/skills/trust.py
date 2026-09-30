"""What a skill written elsewhere may do (ADR-327).

A THIRD-PARTY skill — one LIA fetched from someone else: an https address, an
Agent Plugins package, a skill library — is read as data, never as orders:

- its catalogue entry is marked, and the catalogue says a marked description is
  a label, never an instruction;
- it never runs a ``plan_template`` and is never ``always_loaded``;
- its instructions run only in the isolated skill runner, which holds its own
  skill's tools and nothing else, and whose answer is neutralised before it is
  shown (no image, no raw HTML — ``markdown_literal.untrusted_markdown``);
- anything of it the main loop reads is handed over as external content;
- it never draws an interactive frame, and its images are ``data:`` only: a
  sandboxed frame may still navigate itself to an address carrying the turn's
  data, which no content policy can forbid.

Whether a skill is third-party is decided HERE, once, from the per-request set
the agent service binds (``third_party_skills_ctx``). A request that bound
nothing is treated as if every user skill were third-party: doubt closes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from src.core.context import isolated_skill_ctx, third_party_skills_ctx
from src.core.prompt_store import parse_prompt_sections, read_prompt_file

#: What ``activate_skill_tool``'s ``request`` means — ONE text for its schema
#: and its catalogue manifest, which the planner and the loop read (ADR-284).
ACTIVATION_REQUEST_DESCRIPTION = (
    "Required for a skill marked third-party, which runs on its own: what it "
    "should do for the person, in their words. Ignored for any other skill."
)


def is_third_party(entry: dict[str, Any] | None) -> bool:
    """Whether a RESOLVED cache entry is a third-party skill for this request.

    Args:
        entry: The skill the person's name resolved to (a ``SkillsCache``
            entry), or None.

    Returns:
        False for a system skill or no skill; for a person's skill, whether its
        name is in the request's third-party set — True when no set was bound.
    """
    if entry is None or entry.get("scope") == "admin":
        return False
    names = third_party_skills_ctx.get()
    return True if names is None else entry.get("name") in names


def is_third_party_name(name: str, user_id: str | None) -> bool:
    """Whether the skill ``name`` resolves to a third-party skill for this person.

    Args:
        name: Skill name.
        user_id: The person (None: system skills only — never third-party).

    Returns:
        See :func:`is_third_party`.
    """
    from src.domains.skills.cache import SkillsCache

    return is_third_party(SkillsCache.get_by_name_for_user(name, user_id))


@contextmanager
def isolated_to(skill_name: str) -> Iterator[None]:
    """Scope the skill tools to ONE skill for the duration of its isolated runner.

    Args:
        skill_name: The third-party skill the runner runs.

    Yields:
        Nothing; on exit the previous scope is restored.
    """
    token = isolated_skill_ctx.set(skill_name)
    try:
        yield
    finally:
        isolated_skill_ctx.reset(token)


def out_of_scope(skill_name: str) -> bool:
    """Whether an isolated runner is asking for a skill other than its own."""
    isolated = isolated_skill_ctx.get()
    return isolated is not None and isolated != skill_name


def reads_as_external(entry: dict[str, Any] | None) -> bool:
    """Whether a skill's content must reach its caller as external content.

    True for a third-party skill read from outside its isolated runner — the
    main loop, the pipeline — where its words would otherwise sit beside the
    person's own and LIA's instructions.

    Args:
        entry: The resolved cache entry, or None.

    Returns:
        True when the caller must wrap what it hands over.
    """
    return isolated_skill_ctx.get() is None and is_third_party(entry)


@lru_cache(maxsize=1)
def trust_lines() -> dict[str, str]:
    """The catalogues' model-facing lines (``skill_catalogue_lines.txt``, ADR-284)."""
    return dict(parse_prompt_sections(read_prompt_file("skill_catalogue_lines"), 2))
