"""Real rounded Choice evidence must survive without manufacturing confidence."""

import json
from decimal import Decimal
from pathlib import Path
from typing import get_args

import httpx
import pytest

from src.core.content_classification import EmailCategory, EmailPriority
from src.domains.agents.services.qualification.policy import accepted_choice
from src.infrastructure.llm.typesafe_client import (
    ChoiceAnswer,
    ChoiceQuestion,
    TypeSafeClient,
    TypeSafeError,
)

pytestmark = pytest.mark.unit


async def test_recorded_cent_rounded_batch_preserves_other_answers_and_its_single_charge() -> None:
    path = Path(__file__).parents[3] / "fixtures/jev_choice_rounded_batch.json"
    body = json.loads(path.read_bytes())
    questions = {
        key: ChoiceQuestion(
            instructions="Classify the indicated fictional email dimension.",
            criteria={
                option: option
                for option in get_args(
                    EmailPriority if key.endswith("_priority") else EmailCategory
                )
            },
        )
        for key in body["answers"]
    }
    assert sum(
        Decimal(str(p)) for p in body["answers"]["i0_category"]["probabilities"].values()
    ) == Decimal(".99")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        result = await TypeSafeClient(http, "test-only").choose_many(
            model=body["model"], state="Fictional batch", questions=questions, timeout_seconds=1
        )
    assert set(result.answers) == set(questions)
    assert result.usage.model_dump() == body["usage"]
    for key, answer in result.answers.items():
        assert answer.probabilities == body["answers"][key]["probabilities"]
        assert answer.confidence <= body["answers"][key]["confidence"]
    assert accepted_choice(result.answers["i0_category"], get_args(EmailCategory)) == "unknown"
    assert accepted_choice(result.answers["i0_priority"], get_args(EmailPriority)) == "normal"
    assert accepted_choice(result.answers["i2_category"], get_args(EmailCategory)) == "professional"
    assert accepted_choice(result.answers["i3_category"], get_args(EmailCategory)) == "unknown"
    assert (
        accepted_choice(result.answers["i4_category"], get_args(EmailCategory)) == "phishing_scam"
    )


@pytest.mark.parametrize(
    "probabilities,valid",
    [
        ({"winner": 0.93, "a": 0.05, "b": 0.01, "c": 0.0, "d": 0.0}, True),
        ({"winner": 0.99, "a": 0.01, "b": 0.01}, True),
        ({"winner": 0.9299999999999999, "a": 0.05, "b": 0.01, "c": 0.0, "d": 0.0}, True),
        ({"winner": 0.99, "a": 0.01, "b": 0.01, "c": 0.01, "d": 0.0}, True),
        ({"winner": 0.998, "other": 0.0}, False),
        ({"winner": 0.93, "a": 0.049, "b": 0.01, "c": 0.0, "d": 0.0}, False),
        ({"winner": 0.96, "other": 0.02}, False),
        ({"winner": 1.0, "a": 0.01, "b": 0.01, "c": 0.0}, False),
        ({"winner": 0.8, "other": 0.8}, False),
        ({"winner": 0.0, "other": 0.0}, False),
        pytest.param(
            {"winner": 0.0, **{f"other_{i}": 0.0 for i in range(254)}},
            False,
            id="zero-mass-maximum-options",
        ),
    ],
)
async def test_probability_mass_must_be_feasible_at_the_received_precision(
    probabilities: dict[str, float], valid: bool
) -> None:
    body = {
        "model": "jev-1.13.0",
        "answers": {
            "selection": {
                "type": "choice",
                "choice": "winner",
                "confidence": 1.0,
                "probabilities": probabilities,
            }
        },
        "usage": {"input_tokens": 6244, "output_tokens": 506},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    ) as http:
        call = TypeSafeClient(http, "test-only").choose(
            model=body["model"],
            state="Fictional",
            timeout_seconds=1,
            question=ChoiceQuestion(
                instructions="Choose.", criteria={key: key for key in probabilities}
            ),
        )
        if valid:
            assert (await call).answer.probabilities == probabilities
        else:
            with pytest.raises(TypeSafeError) as caught:
                await call
            assert caught.value.reason == "probability_sum"
            assert caught.value.usage is not None
            assert caught.value.usage.input_tokens == 6244


@pytest.mark.parametrize("deficit", [0.0, 1e-12])
def test_classification_uses_the_same_exact_concentration_boundary(deficit: float) -> None:
    answer = ChoiceAnswer(
        type="choice",
        choice="professional",
        confidence=0.95,
        probabilities={
            "unknown": 0.04 + deficit,
            "professional": 0.96 - deficit,
            "personal": 0.0,
            "spam": 0.0,
            "phishing_scam": 0.0,
        },
    )
    assert accepted_choice(answer, get_args(EmailCategory)) == (
        "professional" if deficit == 0.0 else "unknown"
    )


def test_overfull_rounded_distribution_cannot_promote_a_phishing_alert() -> None:
    answer = ChoiceAnswer(
        type="choice",
        choice="phishing_scam",
        confidence=1.0,
        probabilities={
            "unknown": 0.01,
            "professional": 0.0,
            "personal": 0.0,
            "spam": 0.0,
            "phishing_scam": 1.0,
        },
    )
    assert accepted_choice(answer, get_args(EmailCategory)) == "unknown"


@pytest.mark.parametrize(
    "choice,probabilities,expected",
    [
        (
            "spam",
            {
                "unknown": 0.0,
                "professional": 0.0,
                "personal": 0.0,
                "spam": 0.99,
                "phishing_scam": 0.0,
            },
            "spam",
        ),
        (
            "professional",
            {
                "unknown": 0.03,
                "professional": 0.98,
                "personal": 0.0,
                "spam": 0.0,
                "phishing_scam": 0.0,
            },
            "professional",
        ),
        (
            "professional",
            {
                "unknown": 0.05,
                "professional": 0.96,
                "personal": 0.0,
                "spam": 0.0,
                "phishing_scam": 0.0,
            },
            "unknown",
        ),
    ],
)
def test_rounded_mass_is_consistent_between_transport_and_classification(
    choice: str, probabilities: dict[str, float], expected: str
) -> None:
    answer = ChoiceAnswer(
        type="choice", choice=choice, confidence=0.99, probabilities=probabilities
    )
    assert accepted_choice(answer, get_args(EmailCategory)) == expected


def test_accepted_rounded_tie_stays_uncertain() -> None:
    answer = ChoiceAnswer(
        type="choice", choice="a", confidence=1.0, probabilities={"a": 0.33, "b": 0.33, "c": 0.33}
    )
    assert accepted_choice(answer, ("a", "b", "c")) == "unknown"


def test_probability_contract_changes_invalidate_previous_classification_cache(monkeypatch) -> None:
    from src.domains.agents.services.qualification import service

    before = service.policy_fingerprint()
    monkeypatch.setattr(service, "CHOICE_PROBABILITY_CONTRACT", "next-contract", raising=False)
    assert service.policy_fingerprint() != before
