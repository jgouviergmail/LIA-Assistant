"""Typed fictional corpus and quality gates; no provider calls in this module."""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from src.core.content_classification import (
    ContentClassification,
    EmailCategory,
    EmailClassification,
    EmailPriority,
    EvidenceScope,
)
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.infrastructure.llm.decision_types import DecisionCharge
from src.infrastructure.llm.typesafe_client import ChoiceAnswer


class Gate(BaseModel):
    maximum_wrong_accepted_labels: int
    minimum_positive_coverage: float
    minimum_phishing_coverage: float


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    language: Literal["en", "fr", "de", "es", "it", "zh"]
    kind: Literal["email", "event"]
    evidence_scope: EvidenceScope
    evidence: dict[str, JsonValue]
    expected_category: EmailCategory
    expected_priority: EmailPriority | None

    @model_validator(mode="after")
    def coherent_kind(self) -> Case:
        if self.kind == "event" and (
            self.expected_priority is not None
            or self.expected_category not in {"unknown", "professional", "personal"}
        ):
            raise ValueError("Event cases have no email-only label")
        return self

    def observation(self) -> ClassificationObservation:
        return ClassificationObservation(
            identity=self.id,
            kind=self.kind,
            container_id="fictional",
            item_id=self.id,
            occurrence="",
            revision="1",
            evidence_scope=self.evidence_scope,
            evidence=self.evidence,
        )


class Corpus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    reference_time: AwareDatetime
    timezone: str
    source: str
    quality_gate: Gate
    items: list[Case]

    @classmethod
    def read(cls, path: Path) -> Corpus:
        return cls.model_validate_json(path.read_bytes())


class ClassScore(BaseModel):
    support: int = 0
    accepted: int = 0
    correct: int = 0
    false_positives: int = 0

    @property
    def coverage(self) -> float:
        return self.correct / self.support if self.support else 0.0


class QualityReport(BaseModel):
    passed: bool
    cases: int
    wrong_accepted: int
    abstentions: int
    positive_coverage: float
    per_class: dict[str, ClassScore]
    failures: list[str]


class ReplayCall(BaseModel):
    kind: str
    outcome: str
    latency_ms: float
    charge: DecisionCharge | None
    members: list[str]
    answers: dict[str, ChoiceAnswer]


class ReplayReport(BaseModel):
    split: str
    live: bool
    policy_sha256: str
    corpus_sha256: str
    native_calls_planned: int
    request_bytes: int
    estimated_input_tokens: int
    budget_eur: Decimal
    prior_cost_eur: Decimal
    total_cost_eur: Decimal
    models: dict[str, str]
    calls: list[ReplayCall] = Field(default_factory=list)
    quality: QualityReport | None = None
    run_id: str | None = None
    stop_reason: str | None = None
    predictions: dict[str, ContentClassification] = Field(default_factory=dict)
    settings_unchanged: bool | None = None


def score(corpus: Corpus, predictions: dict[str, ContentClassification]) -> QualityReport:
    per_class: dict[str, ClassScore] = defaultdict(ClassScore)
    wrong = abstentions = positives = covered = 0
    for case in corpus.items:
        prediction = predictions.get(case.id)
        decisions: list[tuple[str, str, str]] = [
            (
                f"{case.kind}.category",
                case.expected_category,
                prediction.category if prediction else "unknown",
            )
        ]
        if case.expected_priority is not None:
            priority = (
                prediction.priority if isinstance(prediction, EmailClassification) else "unknown"
            )
            decisions.append(("email.priority", case.expected_priority, priority))
        for dimension, expected, actual in decisions:
            target = per_class[f"{dimension}.{expected}"]
            target.support += 1
            if expected != "unknown":
                positives += 1
                covered += actual == expected
            if actual == "unknown":
                abstentions += 1
                continue
            result = per_class[f"{dimension}.{actual}"]
            result.accepted += 1
            if actual == expected:
                result.correct += 1
            else:
                wrong += 1
                result.false_positives += 1
    failures = _failures(corpus, per_class, wrong)
    return QualityReport(
        passed=not failures,
        cases=len(corpus.items),
        wrong_accepted=wrong,
        abstentions=abstentions,
        positive_coverage=covered / positives if positives else 0.0,
        per_class=dict(per_class),
        failures=failures,
    )


def _failures(corpus: Corpus, scores: dict[str, ClassScore], wrong: int) -> list[str]:
    failures: list[str] = []
    if wrong > corpus.quality_gate.maximum_wrong_accepted_labels:
        failures.append("wrong_accepted_labels")
    for key, value in scores.items():
        if key.endswith(".unknown") or not value.support:
            continue
        minimum = (
            corpus.quality_gate.minimum_phishing_coverage
            if key.endswith(".phishing_scam")
            else corpus.quality_gate.minimum_positive_coverage
        )
        if value.coverage < minimum:
            failures.append(f"coverage:{key}")
    return failures
