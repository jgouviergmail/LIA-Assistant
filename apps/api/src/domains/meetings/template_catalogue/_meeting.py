"""Built-in templates — category ``meeting`` (ADR-259)."""

from __future__ import annotations

from src.domains.meetings.schemas import TemplateCategory
from src.domains.meetings.template_catalogue._shared import (
    ACTIONS,
    DECISIONS,
    FOLLOW_UPS,
    NEXT_STEPS,
    OPEN_QUESTIONS,
    RISKS,
    SUMMARY,
    TOPICS,
    A,
    B,
    BuiltinSection,
    BuiltinTemplate,
    P,
    T,
)

_C = TemplateCategory.MEETING

TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        "default_minutes",
        _C,
        True,
        (
            BuiltinSection("summary", P, SUMMARY),
            BuiltinSection("topics", T, TOPICS),
            BuiltinSection("decisions", B, DECISIONS),
            BuiltinSection("action_items", A, ACTIONS),
            BuiltinSection("risks", B, RISKS),
            BuiltinSection("open_questions", B, OPEN_QUESTIONS),
        ),
    ),
    BuiltinTemplate(
        "key_points_decisions_tasks",
        _C,
        True,
        (
            BuiltinSection(
                "key_points",
                B,
                "The key points of the meeting in chronological order: objective facts, "
                "figures, dates and data as spoken, one per bullet. No interpretation.",
            ),
            BuiltinSection(
                "decisions",
                B,
                "The important decisions made, in chronological order, one per bullet; "
                "only what was explicitly decided.",
            ),
            BuiltinSection(
                "action_items",
                A,
                "Every task discussed, with the responsible party and the deadline as an "
                "absolute date when given; put any notes about the task in the description.",
            ),
            BuiltinSection(
                "deadlines",
                B,
                "The key deadlines mentioned, one per bullet, each as 'date: what must be "
                "done by then', dates resolved to absolute dates.",
            ),
            BuiltinSection("follow_ups", B, FOLLOW_UPS),
        ),
    ),
    BuiltinTemplate(
        "meeting_secretary",
        _C,
        True,
        (
            BuiltinSection(
                "executive_summary",
                P,
                "As an experienced executive assistant writing for a busy professional: "
                "the high-level themes and the outcome of the meeting in three to five "
                "clear sentences.",
            ),
            BuiltinSection(
                "my_commitments",
                A,
                "The action items and commitments that fall on the USER (the person who "
                "recorded), each with its due date as an absolute date; owner = the user.",
            ),
            BuiltinSection(
                "detailed_breakdown",
                T,
                "One entry per topic: the key discussion points, the decisions, and who "
                "committed to what, in the order the topics came up.",
            ),
        ),
    ),
    BuiltinTemplate(
        "meeting_highlights",
        _C,
        True,
        (
            BuiltinSection(
                "key_insights",
                T,
                "Not a summary: the ideas that will still be valuable in a year. Prefer "
                "universal over contextual, counter-intuitive over common sense, mental "
                "models over isolated conclusions, transferable wisdom over particular "
                "cases. One entry per idea: the title is one sentence under twenty words "
                "that captures it, the summary the supporting insights. Quality over "
                "quantity; drop the mundane.",
            ),
        ),
    ),
    BuiltinTemplate(
        "it_project_meeting",
        _C,
        True,
        (
            BuiltinSection(
                "status_points",
                T,
                "The main subjects and their status. For a daily-style meeting group them "
                "as what was done, plans for today, obstacles; for a weekly one as project "
                "progress, achievements and strategic stakes. One entry per subject.",
            ),
            BuiltinSection(
                "key_quotes",
                B,
                "Important direct quotes with attribution, only when they carry a decision "
                "or a key statement. Empty when there is none.",
            ),
            BuiltinSection(
                "milestones",
                B,
                "High-level project timelines, phases and milestones discussed, excluding "
                "individual task deadlines. Empty when none was discussed.",
            ),
            BuiltinSection(
                "action_items",
                A,
                "Every new task announced and assigned, with the assignee and the deadline "
                "as an absolute date; notes go in the description.",
            ),
            BuiltinSection("decisions", B, DECISIONS),
            BuiltinSection("follow_ups", B, FOLLOW_UPS),
            BuiltinSection(
                "risks",
                B,
                "Open points and risks in three groups, each bullet prefixed by its group: "
                "potential risks (including obstacles), unfinished discussions, discussions "
                "without an action. Empty when nothing applies.",
            ),
        ),
    ),
    BuiltinTemplate(
        "team_meeting_sentiment",
        _C,
        True,
        (
            BuiltinSection(
                "key_points_decisions",
                T,
                "The discussion segmented by subject: one entry per subject with the key "
                "points made and the decisions taken. Never invent names, dates or tasks; "
                "mark an uncertain fact as uncertain.",
            ),
            BuiltinSection(
                "next_steps",
                B,
                "Forward-looking items: what was planned, with the timing as spoken, dates "
                "resolved to absolute dates.",
            ),
            BuiltinSection(
                "action_items",
                A,
                "Every task with its responsible party and due date as an absolute date; "
                "a missing element is left null, never guessed.",
            ),
            BuiltinSection(
                "conclusion",
                P,
                "How the meeting ended: what was agreed overall, in two to four sentences.",
            ),
            BuiltinSection(
                "team_sentiment",
                P,
                "The team's sentiment and mood as the exchange shows it — energy, "
                "agreement, tension, fatigue — with the moments that reveal it. Neutral "
                "wording, no judgement of individuals.",
            ),
        ),
    ),
    BuiltinTemplate(
        "daily_standup",
        _C,
        True,
        (
            BuiltinSection(
                "done_yesterday",
                B,
                "What each person reported as done since the last stand-up, one bullet "
                "per item, prefixed by the speaker.",
            ),
            BuiltinSection(
                "plan_today",
                B,
                "What each person plans to do today, one bullet per item, prefixed by the "
                "speaker.",
            ),
            BuiltinSection(
                "blockers",
                B,
                "Obstacles and dependencies raised, who is blocked and by what. Empty when "
                "nobody is blocked.",
            ),
            BuiltinSection("action_items", A, ACTIONS),
        ),
    ),
    BuiltinTemplate(
        "one_on_one",
        _C,
        True,
        (
            BuiltinSection(
                "context",
                P,
                "The purpose of this one-on-one and the situation it started from, in two "
                "to four sentences.",
            ),
            BuiltinSection(
                "feedback",
                B,
                "Feedback given in both directions, one point per bullet, prefixed by who "
                "gave it; wording faithful to what was said.",
            ),
            BuiltinSection("goals", B, "Goals discussed or set, with the timeframe when stated."),
            BuiltinSection(
                "blockers", B, "Difficulties, needs and blockers raised, and the support asked for."
            ),
            BuiltinSection(
                "commitments",
                A,
                "What each side committed to, with the deadline as an absolute date when given.",
            ),
            BuiltinSection("follow_ups", B, FOLLOW_UPS),
        ),
    ),
    BuiltinTemplate(
        "hiring_interview",
        _C,
        True,
        (
            BuiltinSection(
                "candidate_profile",
                P,
                "The candidate's background, current role and motivations as they "
                "presented them, in three to five sentences. Facts only.",
            ),
            BuiltinSection(
                "skills_observed",
                B,
                "Skills and experience the candidate demonstrated or described, with the "
                "example that supports each one.",
            ),
            BuiltinSection(
                "strengths",
                B,
                "Strengths noted during the exchange, each backed by something said.",
            ),
            BuiltinSection(
                "concerns",
                B,
                "Concerns, gaps and points to verify, each backed by something said. Empty "
                "when none.",
            ),
            BuiltinSection(
                "decisions",
                B,
                "What was decided about the process (next round, references, offer). Only "
                "what was explicitly decided.",
            ),
            BuiltinSection("next_steps", A, NEXT_STEPS),
        ),
    ),
    BuiltinTemplate(
        "brainstorming",
        _C,
        True,
        (
            BuiltinSection(
                "goal",
                P,
                "The question or problem the session set out to answer, in one to three "
                "sentences.",
            ),
            BuiltinSection(
                "ideas",
                T,
                "Every idea voiced, one entry each, in order: the title names the idea, the "
                "summary keeps what was said about it. Group nothing, judge nothing here.",
            ),
            BuiltinSection(
                "evaluation",
                B,
                "How the ideas were assessed: criteria, votes, objections, as expressed.",
            ),
            BuiltinSection(
                "selected_ideas",
                B,
                "The ideas the group decided to keep or explore further. Empty when no "
                "selection was made.",
            ),
            BuiltinSection("action_items", A, ACTIONS),
        ),
    ),
)
