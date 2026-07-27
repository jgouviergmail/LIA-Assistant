"""Application of the interest actions an extraction proposes.

This is where an LLM's output becomes user data, so every branch here is a way
to corrupt a profile. Two of them were live defects until 2026-07-27, both
measured on the production database:

* a BLOCKED interest was invisible to deduplication — the user blocked
  "Cycle de l'eau" at 19:14 and the extractor re-created it at 19:39 under a
  near-identical label (cosine 0.9821, far above the 0.89 merge threshold);
* a DORMANT interest was invisible for the same reason, so the reactivation
  branch of ``consolidate_on_mention`` was unreachable from this path.

The tests below pin the repaired semantics per status, plus the ordinary
paths (create / consolidate / rename / delete) that must not regress, plus the
failure isolation that keeps one bad action from taking the batch down.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.interests import helpers as interest_helpers
from src.domains.interests.models import InterestCategory, InterestStatus, UserInterest
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services.action_applier import (
    apply_interest_actions,
    find_similar_interest,
)
from src.infrastructure.llm import local_embeddings

pytestmark = pytest.mark.unit

USER_ID = str(uuid.uuid4())


def _interest(
    topic: str,
    *,
    status: str = InterestStatus.ACTIVE.value,
    similarity: float | None = None,
    user_id: str = USER_ID,
) -> UserInterest:
    """Build a detached interest row.

    Args:
        topic: Topic label.
        status: One of the ``InterestStatus`` values.
        similarity: Cosine similarity the stub should report for this row; the
            value is carried in the embedding so a test reads as the number it
            means. ``None`` means "no embedding" (the string-matching path).
        user_id: Owner, as a string.
    """
    interest = UserInterest(
        user_id=uuid.UUID(user_id),
        topic=topic,
        category="technology",
        positive_signals=1,
        negative_signals=0,
        status=status,
        last_mentioned_at=datetime.now(UTC),
    )
    interest.id = uuid.uuid4()
    interest.embedding = [similarity] if similarity is not None else None
    return interest


def _create(topic: str = "escalade en salle") -> ExtractedInterest:
    return ExtractedInterest(
        action="create", topic=topic, category=InterestCategory.SPORTS, confidence=0.95
    )


def _delete(target: UserInterest) -> ExtractedInterest:
    return ExtractedInterest(action="delete", interest_id=str(target.id))


def _update(target: UserInterest, topic: str | None = None) -> ExtractedInterest:
    return ExtractedInterest(action="update", interest_id=str(target.id), topic=topic)


@pytest.fixture
def repo() -> AsyncMock:
    """Repository double: only the methods the applier is allowed to call."""
    fake = AsyncMock()
    fake.get_by_user_and_topic_ci.return_value = None
    created = _interest("nouveau")
    fake.create.return_value = created
    return fake


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make similarity deterministic and readable.

    ``generate_interest_embedding`` returns a truthy vector, and the cosine
    stub reports whatever similarity the candidate row was built with — so a
    test says "this row is at 0.95" instead of hand-crafting vectors.
    """

    async def _embed(_text: str) -> list[float]:
        return [1.0]

    def _cosine(_a: list[float], b: list[float]) -> float:
        return float(b[0])

    monkeypatch.setattr(interest_helpers, "generate_interest_embedding", _embed)
    monkeypatch.setattr(local_embeddings, "cosine_similarity", _cosine)


def _above() -> float:
    """A similarity that must trigger deduplication."""
    return min(settings.interest_dedup_similarity_threshold + 0.05, 1.0)


def _below() -> float:
    """A similarity that must NOT trigger deduplication."""
    return settings.interest_dedup_similarity_threshold - 0.05


# =============================================================================
# find_similar_interest
# =============================================================================


class TestFindSimilarInterest:
    async def test_no_candidate_means_no_match(self) -> None:
        assert await find_similar_interest("escalade", []) == (False, None)

    async def test_a_candidate_above_the_threshold_matches(self) -> None:
        candidate = _interest("escalade", similarity=_above())

        assert await find_similar_interest("escalade en salle", [candidate]) == (True, candidate)

    async def test_a_candidate_below_the_threshold_does_not_match(self) -> None:
        candidate = _interest("ornithologie", similarity=_below())

        assert await find_similar_interest("escalade", [candidate]) == (False, None)

    async def test_the_threshold_is_inclusive(self) -> None:
        candidate = _interest("escalade", similarity=settings.interest_dedup_similarity_threshold)

        is_similar, _ = await find_similar_interest("escalade", [candidate])

        assert is_similar is True

    async def test_the_best_candidate_wins(self) -> None:
        good = _interest("escalade", similarity=_above())
        better = _interest("escalade en salle", similarity=min(_above() + 0.02, 1.0))

        _, match = await find_similar_interest("escalade en salle", [good, better])

        assert match is better

    async def test_a_blocked_candidate_is_returned_like_any_other(self) -> None:
        # The status decision belongs to the caller: this function must SEE
        # blocked rows, which is exactly what it could not do before.
        blocked = _interest(
            "cycle de l'eau", status=InterestStatus.BLOCKED.value, similarity=_above()
        )

        assert await find_similar_interest("cycle de l'eau (schémas)", [blocked]) == (True, blocked)

    async def test_a_missing_embedding_falls_back_to_substring_matching(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Embedding generation is best-effort; its failure must not disable
        # dedup entirely (ADR-131: the "Anthropic"/"anthropic" prod duplicate).
        async def _no_embedding(_text: str) -> None:
            return None

        monkeypatch.setattr(interest_helpers, "generate_interest_embedding", _no_embedding)
        candidate = _interest("Anthropic", similarity=None)

        assert await find_similar_interest("anthropic", [candidate]) == (True, candidate)

    async def test_substring_matching_works_in_both_directions(self) -> None:
        candidate = _interest("escalade en salle de bloc", similarity=None)

        assert await find_similar_interest("escalade", [candidate]) == (True, candidate)

    async def test_unrelated_topics_without_embeddings_do_not_match(self) -> None:
        candidate = _interest("ornithologie", similarity=None)

        assert await find_similar_interest("escalade", [candidate]) == (False, None)


# =============================================================================
# Status semantics — the repaired defects
# =============================================================================


class TestBlockedIsNeverResurrected:
    async def test_a_creation_matching_a_blocked_interest_applies_nothing(
        self, repo: AsyncMock
    ) -> None:
        blocked = _interest(
            "Cycle de l'eau (schémas et explications)",
            status=InterestStatus.BLOCKED.value,
            similarity=_above(),
        )

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_create("Cycle de l'eau (hydrologie, schémas explicatifs)")],
            existing_interests=[blocked],
        )

        assert applied == 0
        repo.create.assert_not_awaited()
        repo.consolidate_on_mention.assert_not_awaited()

    async def test_an_update_targeting_a_blocked_interest_is_refused(self, repo: AsyncMock) -> None:
        blocked = _interest("jeux de stratégie", status=InterestStatus.BLOCKED.value)
        repo.get_by_id.return_value = blocked

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_update(blocked, topic="jeux de plateau")],
            existing_interests=[blocked],
        )

        assert applied == 0
        assert blocked.topic == "jeux de stratégie"
        repo.consolidate_on_mention.assert_not_awaited()

    async def test_a_deletion_targeting_a_blocked_interest_is_refused(
        self, repo: AsyncMock
    ) -> None:
        # Deleting the row would DESTROY the block: the topic could then be
        # re-created freely. The block must outlive the extraction.
        blocked = _interest("météo capteurs", status=InterestStatus.BLOCKED.value)
        repo.get_by_id.return_value = blocked

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_delete(blocked)],
            existing_interests=[blocked],
        )

        assert applied == 0
        repo.delete.assert_not_awaited()

    async def test_a_rename_colliding_with_a_blocked_interest_is_refused(
        self, repo: AsyncMock
    ) -> None:
        target = _interest("horloges")
        blocked = _interest("tic-tac-toe", status=InterestStatus.BLOCKED.value)
        repo.get_by_id.return_value = target
        repo.get_by_user_and_topic_ci.return_value = blocked

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_update(target, topic="tic-tac-toe")],
            existing_interests=[target],
        )

        assert applied == 0
        repo.consolidate_on_mention.assert_not_awaited()


class TestDormantIsRevivedNotDuplicated:
    async def test_a_creation_matching_a_dormant_interest_consolidates_it(
        self, repo: AsyncMock
    ) -> None:
        dormant = _interest(
            "botanique urbaine", status=InterestStatus.DORMANT.value, similarity=_above()
        )

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_create("botanique urbaine et défilés")],
            existing_interests=[dormant],
        )

        assert applied == 1
        repo.consolidate_on_mention.assert_awaited_once_with(dormant)
        repo.create.assert_not_awaited()


# =============================================================================
# Ordinary paths — must not regress
# =============================================================================


class TestCreate:
    async def test_a_new_subject_is_created(self, repo: AsyncMock) -> None:
        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_create()], existing_interests=[]
        )

        assert applied == 1
        repo.create.assert_awaited_once()
        assert repo.create.await_args.kwargs["topic"] == "escalade en salle"
        assert repo.create.await_args.kwargs["category"] == InterestCategory.SPORTS.value

    async def test_a_known_active_subject_is_consolidated_not_duplicated(
        self, repo: AsyncMock
    ) -> None:
        existing = _interest("escalade", similarity=_above())

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_create()], existing_interests=[existing]
        )

        assert applied == 1
        repo.consolidate_on_mention.assert_awaited_once_with(existing)
        repo.create.assert_not_awaited()

    async def test_a_distant_subject_is_created_alongside(self, repo: AsyncMock) -> None:
        existing = _interest("ornithologie", similarity=_below())

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_create()], existing_interests=[existing]
        )

        assert applied == 1
        repo.create.assert_awaited_once()

    @pytest.mark.parametrize(
        "payload",
        [
            {"action": "create", "category": "sports", "confidence": 0.9},
            {"action": "create", "topic": "escalade", "confidence": 0.9},
        ],
        ids=["no_topic", "no_category"],
    )
    async def test_an_incomplete_creation_is_dropped(
        self, repo: AsyncMock, payload: dict[str, Any]
    ) -> None:
        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[ExtractedInterest(**payload)],
            existing_interests=[],
        )

        assert applied == 0
        repo.create.assert_not_awaited()

    async def test_an_action_without_an_explicit_kind_defaults_to_create(
        self, repo: AsyncMock
    ) -> None:
        action = ExtractedInterest(
            topic="escalade", category=InterestCategory.SPORTS, confidence=0.9
        )

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[action], existing_interests=[]
        )

        assert applied == 1
        repo.create.assert_awaited_once()


class TestUpdate:
    async def test_a_rename_rewrites_the_topic_and_invalidates_derived_state(
        self, repo: AsyncMock
    ) -> None:
        target = _interest("langgraph")
        target.subject = "IA"
        repo.get_by_id.return_value = target

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_update(target, topic="LangGraph, agents et checkpointing")],
            existing_interests=[target],
        )

        assert applied == 1
        assert target.topic == "LangGraph, agents et checkpointing"
        # Subject is derived from the topic: it must be recomputed (ADR-131).
        assert target.subject is None
        # And the embedding must follow the new label, or dedup drifts.
        assert target.embedding == [1.0]
        repo.consolidate_on_mention.assert_awaited_once_with(target)

    async def test_a_rename_onto_an_existing_topic_consolidates_the_target(
        self, repo: AsyncMock
    ) -> None:
        target = _interest("langgraph")
        collision = _interest("LangGraph")
        repo.get_by_id.return_value = target
        repo.get_by_user_and_topic_ci.return_value = collision

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_update(target, topic="LangGraph")],
            existing_interests=[target],
        )

        assert applied == 1
        repo.consolidate_on_mention.assert_awaited_once_with(collision)
        assert target.topic == "langgraph"

    async def test_an_update_without_a_rename_only_counts_the_mention(
        self, repo: AsyncMock
    ) -> None:
        target = _interest("langgraph")
        target.subject = "IA"
        repo.get_by_id.return_value = target

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_update(target)], existing_interests=[target]
        )

        assert applied == 1
        assert target.subject == "IA"
        repo.consolidate_on_mention.assert_awaited_once_with(target)

    async def test_a_category_change_is_applied(self, repo: AsyncMock) -> None:
        target = _interest("escalade")
        repo.get_by_id.return_value = target
        action = ExtractedInterest(
            action="update", interest_id=str(target.id), category=InterestCategory.SPORTS
        )

        await apply_interest_actions(
            repo, user_id=USER_ID, actions=[action], existing_interests=[target]
        )

        assert target.category == InterestCategory.SPORTS.value


class TestDelete:
    async def test_a_known_interest_is_deleted(self, repo: AsyncMock) -> None:
        target = _interest("cinéma muet")
        repo.get_by_id.return_value = target

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_delete(target)], existing_interests=[target]
        )

        assert applied == 1
        repo.delete.assert_awaited_once_with(target)


class TestIdentityGuards:
    @pytest.mark.parametrize("action", ["update", "delete"])
    async def test_an_unknown_identifier_is_refused(self, repo: AsyncMock, action: str) -> None:
        # Hallucinated UUIDs must never reach the database.
        known = _interest("escalade")
        stranger = ExtractedInterest(action=action, interest_id=str(uuid.uuid4()))

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[stranger], existing_interests=[known]
        )

        assert applied == 0
        repo.get_by_id.assert_not_awaited()
        repo.delete.assert_not_awaited()

    @pytest.mark.parametrize("action", ["update", "delete"])
    async def test_an_action_without_an_identifier_is_refused(
        self, repo: AsyncMock, action: str
    ) -> None:
        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[ExtractedInterest(action=action)],
            existing_interests=[_interest("escalade")],
        )

        assert applied == 0
        repo.delete.assert_not_awaited()

    async def test_another_users_interest_is_refused(self, repo: AsyncMock) -> None:
        # Cross-tenant write: the id is known to the batch but the row belongs
        # to someone else.
        foreign = _interest("escalade", user_id=str(uuid.uuid4()))
        repo.get_by_id.return_value = foreign

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_delete(foreign)], existing_interests=[foreign]
        )

        assert applied == 0
        repo.delete.assert_not_awaited()

    async def test_a_vanished_row_is_refused(self, repo: AsyncMock) -> None:
        target = _interest("escalade")
        repo.get_by_id.return_value = None

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_delete(target)], existing_interests=[target]
        )

        assert applied == 0
        repo.delete.assert_not_awaited()


# =============================================================================
# Batch behaviour
# =============================================================================


class TestBatch:
    async def test_the_delete_cap_is_enforced_and_the_rest_survives(self, repo: AsyncMock) -> None:
        # Threshold read from settings, never hardcoded: the cap can move.
        targets = [
            _interest(f"sujet {index}")
            for index in range(settings.extraction_max_deletes_per_run + 1)
        ]
        repo.get_by_id.side_effect = targets
        actions: list[ExtractedInterest] = [_delete(t) for t in targets]
        actions.append(_create())

        applied = await apply_interest_actions(
            repo, user_id=USER_ID, actions=actions, existing_interests=targets
        )

        repo.delete.assert_not_awaited()
        repo.create.assert_awaited_once()
        assert applied == 1

    async def test_deletions_within_the_cap_are_applied(self, repo: AsyncMock) -> None:
        targets = [
            _interest(f"sujet {index}") for index in range(settings.extraction_max_deletes_per_run)
        ]
        repo.get_by_id.side_effect = targets

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_delete(t) for t in targets],
            existing_interests=targets,
        )

        assert applied == len(targets)
        assert repo.delete.await_count == len(targets)

    async def test_two_near_identical_creations_do_not_both_land(self, repo: AsyncMock) -> None:
        # The candidate list is snapshotted before the loop, so a creation must
        # join it — otherwise one answer proposing the same subject twice
        # inserts two rows that the dedup would have merged on the next turn.
        created = _interest("escalade en salle", similarity=_above())
        repo.create.return_value = created

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_create("escalade en salle"), _create("escalade en salle de bloc")],
            existing_interests=[],
        )

        repo.create.assert_awaited_once()
        repo.consolidate_on_mention.assert_awaited_once_with(created)
        assert applied == 2

    async def test_one_failing_action_never_takes_the_others_down(self, repo: AsyncMock) -> None:
        # Unrelated topic, below the threshold: the surviving create must go
        # all the way to an insert, not be absorbed by a lookalike.
        target = _interest("ornithologie", similarity=_below())
        repo.get_by_id.side_effect = RuntimeError("database went away")

        applied = await apply_interest_actions(
            repo,
            user_id=USER_ID,
            actions=[_delete(target), _create()],
            existing_interests=[target],
        )

        assert applied == 1
        repo.create.assert_awaited_once()

    async def test_an_empty_batch_applies_nothing(self, repo: AsyncMock) -> None:
        assert (
            await apply_interest_actions(repo, user_id=USER_ID, actions=[], existing_interests=[])
            == 0
        )

    async def test_nothing_is_committed_by_the_applier(self, repo: AsyncMock) -> None:
        # Transaction ownership belongs to the caller; committing here would
        # break the caller's ability to roll the batch back.
        await apply_interest_actions(
            repo, user_id=USER_ID, actions=[_create()], existing_interests=[]
        )

        repo.commit.assert_not_awaited()
