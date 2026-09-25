"""Catalogue manifest of ``send_email_to_me_tool`` — an e-mail to the user themselves.

Beside ``catalogue_manifests.py`` because that module is at its size cap
(``attachment_manifest.py`` precedent). The recipient is NOT a parameter: the
tool writes to the person's own mailbox, or without one to their verified
account address — which is what lets it run with no confirmation card and in a
routine (ADR-314, the ``call_me`` precedent of ADR-290).
"""

from datetime import UTC, datetime

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

send_email_to_me_catalogue_manifest = ToolManifest(
    name="send_email_to_me_tool",
    # No confirmation card, by construction: the recipient is the account holder
    # and never a parameter, so the one who would confirm is the one who
    # receives. ``reversible`` is also what lets a routine run it unattended —
    # the effect gate LEDGERS it where it refuses a draft (ADR-276).
    mutation_policy="reversible",
    mutation_policy_reason=(
        "The recipient is the account holder themselves and is never a parameter: the "
        "address their connected mailbox states as its own, or without one their "
        "VERIFIED account address. The message lands with the person who asked for it, "
        "who can delete it."
    ),
    agent="email_agent",
    description=(
        "**Tool: send_email_to_me_tool** - Send an e-mail to the USER THEMSELVES, in their "
        "own mailbox: a note, a summary, a digest, a copy for later. Needs no confirmation "
        "and works in routines ('every morning, e-mail me the weather'). The recipient is "
        "always the user, never anyone else (for anybody else use send_email_tool). "
        "Provide subject + body, or content_instruction."
    ),
    parameters=[
        ParameterSchema(
            name="subject",
            type="string",
            required=False,
            description="Subject. Required unless content_instruction is provided.",
        ),
        ParameterSchema(
            name="body",
            type="string",
            required=False,
            description="Content. Required unless content_instruction is provided.",
        ),
        ParameterSchema(
            name="content_instruction",
            type="string",
            required=False,
            description=(
                "What the e-mail should contain, for generation (e.g. 'a short summary of "
                "today's forecast'). Use instead of subject/body."
            ),
        ),
        ParameterSchema(name="is_html", type="boolean", required=False, description="Is HTML body"),
    ],
    outputs=[
        OutputFieldSchema(
            path="sent_to",
            type="string",
            description="mailbox (the connected mailbox) or account_email (LIA's relay)",
        ),
        OutputFieldSchema(
            path="message_id",
            type="string",
            nullable=True,
            description="Provider message id, when the mailbox returned one",
        ),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=80, est_cost_usd=0.005, est_latency_ms=900),
    permissions=PermissionProfile(
        # No scope: without a connected mailbox, LIA's own relay sends.
        required_scopes=[],
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    semantic_keywords=[
        "email me",
        "send me an email",
        "mail it to my inbox",
        "send a copy to myself",
        "email me a summary every morning",
    ],
    reference_examples=["sent_to"],
    display=DisplayMetadata(emoji="📬", i18n_key="send_email_to_me", visible=True, category="tool"),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = ["send_email_to_me_catalogue_manifest"]
