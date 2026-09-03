"""Built-in templates — categories ``personal`` and ``learning`` (ADR-259)."""

from __future__ import annotations

from src.domains.meetings.schemas import TemplateCategory
from src.domains.meetings.template_catalogue._shared import (
    DECISIONS,
    DOCUMENTS,
    NEXT_STEPS,
    RISKS,
    A,
    B,
    BuiltinSection,
    BuiltinTemplate,
    P,
    T,
)

_PERS = TemplateCategory.PERSONAL
_LEARN = TemplateCategory.LEARNING

TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        "medical_appointment",
        _PERS,
        True,
        (
            BuiltinSection(
                "reason_for_visit",
                P,
                "Why the appointment took place and the symptoms or concerns described, "
                "in two to four sentences.",
            ),
            BuiltinSection(
                "findings",
                B,
                "What the practitioner observed, measured or explained, one per bullet, "
                "figures exactly as spoken.",
            ),
            BuiltinSection(
                "diagnosis",
                P,
                "The diagnosis or the hypotheses stated by the practitioner, in their "
                "words; say when none was given.",
            ),
            BuiltinSection(
                "treatment",
                B,
                "Treatments prescribed or advised with dosage, frequency and duration "
                "exactly as spoken. Never complete or infer a dosage.",
            ),
            BuiltinSection(
                "exams_to_do",
                B,
                "Exams, tests or referrals to arrange, with the timing when stated.",
            ),
            BuiltinSection(
                "next_appointment",
                B,
                "The next appointment or follow-up and its timing, resolved to a date when "
                "possible.",
            ),
            BuiltinSection(
                "questions_to_ask",
                B,
                "Questions the patient raised that stayed unanswered, and points worth "
                "asking next time. Empty when none.",
            ),
        ),
    ),
    BuiltinTemplate(
        "car_garage_appointment",
        _PERS,
        True,
        (
            BuiltinSection(
                "vehicle",
                P,
                "The vehicle concerned (make, model, mileage, anything identifying stated) "
                "in one to three sentences.",
            ),
            BuiltinSection(
                "symptoms", B, "The problems described by the customer and observed by the garage."
            ),
            BuiltinSection(
                "diagnosis", P, "The garage's diagnosis and its explanation, in their words."
            ),
            BuiltinSection(
                "proposed_work",
                B,
                "Each work item proposed with its price, parts and labour exactly as "
                "quoted, and whether it is urgent or optional.",
            ),
            BuiltinSection("decisions", B, DECISIONS),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "bank_advisor_appointment",
        _PERS,
        True,
        (
            BuiltinSection(
                "situation",
                P,
                "The customer's situation and the purpose of the appointment as discussed, "
                "in two to four sentences.",
            ),
            BuiltinSection(
                "products_proposed",
                B,
                "Each product or service proposed with what it does, one per bullet.",
            ),
            BuiltinSection(
                "conditions_and_fees",
                B,
                "Rates, fees, conditions, durations and amounts exactly as spoken, one per "
                "bullet.",
            ),
            BuiltinSection("decisions", B, DECISIONS),
            BuiltinSection("documents_to_provide", B, DOCUMENTS),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "legal_consultation",
        _PERS,
        True,
        (
            BuiltinSection(
                "matter",
                P,
                "The matter brought to the consultation and the facts as presented, in "
                "three to five sentences.",
            ),
            BuiltinSection(
                "legal_analysis",
                B,
                "The professional's analysis: applicable rules, positions and their "
                "explanation, one per bullet, in their words.",
            ),
            BuiltinSection(
                "options",
                B,
                "The options presented with their consequences, costs and timing as stated.",
            ),
            BuiltinSection("risks", B, RISKS),
            BuiltinSection("documents_to_provide", B, DOCUMENTS),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "lecture_notes",
        _LEARN,
        True,
        (
            BuiltinSection(
                "outline", B, "The structure of the lecture: its parts in order, one per bullet."
            ),
            BuiltinSection(
                "key_concepts",
                T,
                "One entry per key concept: the title names it, the summary explains it "
                "as the lecturer did, with the reasoning and the nuances.",
            ),
            BuiltinSection(
                "definitions",
                B,
                "Terms defined during the lecture, each with its definition as given.",
            ),
            BuiltinSection(
                "examples", B, "Examples, cases and demonstrations used, and what each illustrates."
            ),
            BuiltinSection(
                "takeaways",
                B,
                "What the lecturer insisted on remembering, and what will be assessed "
                "when stated.",
            ),
            BuiltinSection(
                "questions",
                B,
                "Questions asked and their answers, and points left open. Empty when none.",
            ),
        ),
    ),
    BuiltinTemplate(
        "training_workshop",
        _LEARN,
        True,
        (
            BuiltinSection("objectives", B, "The learning objectives announced, one per bullet."),
            BuiltinSection(
                "content",
                T,
                "One entry per module or part: what was taught and the key points made.",
            ),
            BuiltinSection(
                "exercises",
                B,
                "Exercises and practical cases done, with the expected result and any "
                "difficulty noted.",
            ),
            BuiltinSection(
                "points_of_attention",
                B,
                "Pitfalls, common mistakes and recommendations the trainer highlighted.",
            ),
            BuiltinSection("follow_ups", A, NEXT_STEPS),
        ),
    ),
)
