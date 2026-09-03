"""Built-in templates — categories ``business`` and ``technical`` (ADR-259)."""

from __future__ import annotations

from src.domains.meetings.schemas import TemplateCategory
from src.domains.meetings.template_catalogue._shared import (
    ACTIONS,
    DECISIONS,
    NEXT_STEPS,
    RISKS,
    A,
    B,
    BuiltinSection,
    BuiltinTemplate,
    P,
    T,
)

_BUS = TemplateCategory.BUSINESS
_TECH = TemplateCategory.TECHNICAL

TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        "bant_analysis",
        _BUS,
        True,
        (
            BuiltinSection(
                "budget",
                P,
                "The financial resources planned and how they are allocated, as stated; "
                "say when nothing was said.",
            ),
            BuiltinSection(
                "authority", P, "Who decides and what influences the decision process, as stated."
            ),
            BuiltinSection(
                "need",
                P,
                "The essential requirements and specifications to meet, as expressed by "
                "the prospect.",
            ),
            BuiltinSection(
                "timeline",
                P,
                "The important dates and key stages of the decision and the project, "
                "resolved to absolute dates.",
            ),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "consulting_session",
        _BUS,
        True,
        (
            BuiltinSection(
                "diagnosis",
                T,
                "The central theme, the interlocutors and the apparent objective, then one "
                "entry per challenge: explicit or implicit, its root causes, its impact on "
                "the business. Analytical, objective, constructively provocative.",
            ),
            BuiltinSection(
                "process_optimization",
                B,
                "Bottlenecks and inefficiencies identified, with the workflow redesign "
                "proposed for each: clarity, efficiency, redundancy removed.",
            ),
            BuiltinSection(
                "ai_automation",
                B,
                "Repetitive or large-scale tasks that could be automated or improved with "
                "AI, each with the type of AI and the use case.",
            ),
            BuiltinSection(
                "strategic_solutions",
                B,
                "Training, restructuring, new tools, culture change or leadership "
                "development proposed to address root causes and seize opportunities.",
            ),
            BuiltinSection(
                "beyond_the_obvious",
                B,
                "Recurring patterns, resistance to change, misalignment between teams, "
                "lack of clarity in the vision and innovation opportunities the exchange "
                "reveals.",
            ),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "requirements_gathering",
        _BUS,
        True,
        (
            BuiltinSection(
                "project_goals",
                P,
                "The project goals and scope, referring to the client's current software "
                "system or expressed needs, in three to six sentences.",
            ),
            BuiltinSection(
                "stakeholders",
                B,
                "The client or jurisdiction and every participant with their role.",
            ),
            BuiltinSection(
                "functional_requirements",
                B,
                "What the system must do: functional requirements, data requirements "
                "(format, sources), user interface requirements. One per bullet.",
            ),
            BuiltinSection(
                "non_functional_requirements",
                B,
                "Performance targets, security measures, usability, scalability, "
                "regulatory and compliance requirements. One per bullet.",
            ),
            BuiltinSection(
                "assumptions_constraints",
                B,
                "Assumptions made while gathering and limitations affecting the current "
                "system or the project.",
            ),
            BuiltinSection(
                "definitions",
                B,
                "Ambiguous terms defined, or flagged as needing clarification when no "
                "definition was given.",
            ),
            BuiltinSection(
                "gaps",
                B,
                "Missing elements or problems the client identified in the current system, "
                "and any functional gap identified.",
            ),
            BuiltinSection("risks", B, "Possible risks and ambiguities to raise with the client."),
            BuiltinSection("action_items", A, ACTIONS),
        ),
    ),
    BuiltinTemplate(
        "sales_discovery_call",
        _BUS,
        True,
        (
            BuiltinSection(
                "customer_context",
                P,
                "Who the customer is, their situation and what triggered the call, in "
                "three to five sentences.",
            ),
            BuiltinSection(
                "needs",
                B,
                "The needs, pains and expected outcomes the customer expressed, one per "
                "bullet, wording faithful to theirs.",
            ),
            BuiltinSection(
                "objections",
                B,
                "Objections, doubts and competing options raised, with the answer given "
                "when there was one. Empty when none.",
            ),
            BuiltinSection(
                "decision_process",
                P,
                "How and when the customer decides: people involved, budget signals, "
                "timeline, as stated.",
            ),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "technical_deep_dive",
        _TECH,
        True,
        (
            BuiltinSection(
                "topic_index",
                B,
                "An index of the topics and sub-topics discussed, in order, one per bullet.",
            ),
            BuiltinSection(
                "technical_details",
                T,
                "For engineers, developers and architects: one entry per topic with the "
                "technical substance without simplification — system design, debugging, "
                "APIs, coding, infrastructure, security protocols — as discussed.",
            ),
            BuiltinSection(
                "code_and_commands",
                B,
                "Every piece of code, command, log line and configuration mentioned, "
                "reproduced verbatim, one per bullet with the context in a few words.",
            ),
            BuiltinSection(
                "architecture",
                P,
                "The architecture, workflows and infrastructure discussed, described "
                "precisely enough to serve as a reference for absent team members.",
            ),
            BuiltinSection(
                "unresolved_issues",
                B,
                "Problems left unresolved, each with an assessment and a recommendation "
                "clearly marked as LIA's suggestion, not a decision of the meeting.",
            ),
        ),
    ),
    BuiltinTemplate(
        "it_topics_for_clients",
        _TECH,
        True,
        (
            BuiltinSection(
                "plain_summary",
                P,
                "The meeting explained to a non-technical client: clear, precise "
                "sentences, IT jargon avoided wherever possible, the client's interest "
                "first. Four to eight sentences.",
            ),
            BuiltinSection("decisions", B, DECISIONS),
            BuiltinSection("action_items", A, ACTIONS),
            BuiltinSection(
                "vendor_notes",
                B,
                "The technical points in precise terminology, for the vendor: what was "
                "specified, agreed or challenged.",
            ),
            BuiltinSection("risks", B, RISKS),
        ),
    ),
)
