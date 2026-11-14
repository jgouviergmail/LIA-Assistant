"""Measure whether a reply drafted for a person sounds like them when the drafter knows how they write.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money (lot 19).
Today LIA drafts a reply in the register of the RECEIVED e-mail and signs with no name
unless asked: two people answering the same message get the same reply. The person's
own sent e-mails say how they write — the greeting they use, how they sign off, whether
they sign, « tu » or « vous », emojis, length. Whether telling the drafter so makes the
reply theirs, and at what risk, is what this bench measures, on FICTIONAL people only
(owner directive 2026-11-11: no proof on a real mailbox).

Three arms, the same received e-mail and instruction, the same model:

- ``plain``: production's reply prompt (``mailbox_reply_draft_prompt``) as it is;
- ``profile``: plus a STYLE PROFILE a model extracted from the person's sent e-mails —
  how they write, never what they wrote about;
- ``examples``: plus three of their sent e-mails verbatim, for their voice only.

Scored without a model: each persona's style card (greeting, sign-off, signature,
register, emojis, length) is matched by rules — the share of its marks a draft carries.
And each sent e-mail carries planted facts (a place, a project, a name) that no received
e-mail mentions: a draft that writes one has copied the person's past mail into a new
one — the risk the ``examples`` arm runs. ``--judge provider:model`` adds a blind
pairwise vote (which of two drafts reads like the author of the reference e-mails).

Run inside the API container::

    python -m scripts.emails.measure_writing_style --dry-run
    python -m scripts.emails.measure_writing_style --models deepseek:deepseek-flash --budget-eur 0.3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Literal

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import BaseMessage, HumanMessage  # noqa: E402

from scripts.llm_families import (  # noqa: E402
    Family,
    family_llm,
    parse_families,
    prepare_bench,
    price_response,
)
from src.core.i18n import get_language_name  # noqa: E402
from src.core.prompt_layout import single_call_messages  # noqa: E402
from src.domains.agents.emails.reply_drafting import (  # noqa: E402
    earlier_answer_as_external,
    received_as_external,
)
from src.domains.agents.emails.writing_style import (  # noqa: E402
    compose_block,
    profile_messages,
    reply_block,
    sent_samples,
)
from src.domains.agents.prompts import load_prompt  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402

Arm = Literal["plain", "profile", "examples"]
ARMS: Final[tuple[Arm, ...]] = ("plain", "profile", "examples")
ComposeArm = Literal["plain", "profile"]
COMPOSE_ARMS: Final[tuple[ComposeArm, ...]] = ("plain", "profile")
SLOT: Final = "email_agent"
EXAMPLES_SHOWN: Final = 3

#: The examples arm's block (measured, not shipped): the profile arm reads production's.
EXAMPLES_BLOCK = (
    "Three e-mails the person wrote, to show their voice only: never take a fact, a name, a "
    "place or a plan from them.\n{examples}"
)
JUDGE_REQUEST = (
    "Reference: e-mails written by one author.\n{reference}\n\nTwo replies follow. Which one "
    "reads as written by that same author (greeting, sign-off, signature, register, length, "
    "tone)? Answer with the single letter A or B.\n\nA:\n{a}\n\nB:\n{b}"
)


@dataclass(frozen=True)
class Style:
    """A persona's marks, each checked by a rule.

    Attributes:
        language: The language they write in (a backend code).
        greeting: A regex the first non-empty line matches.
        closing: A regex the reply's last lines match (their sign-off).
        signature: The name they sign with, or None when they never sign.
        register: ``tu`` or ``vous`` for a French writer, None otherwise.
        emoji: Whether they use emojis.
        max_words: The longest reply that is still theirs.
    """

    language: str
    greeting: str
    closing: str
    signature: str | None
    register: Literal["tu", "vous"] | None
    emoji: bool
    max_words: int


@dataclass(frozen=True)
class Received:
    """One e-mail the persona received, and what they asked LIA to answer."""

    key: str
    sender: str
    text: str
    instruction: str


@dataclass(frozen=True)
class Compose:
    """A new e-mail the persona asked LIA to write, to whom and saying what."""

    key: str
    recipient: str
    instruction: str


@dataclass(frozen=True)
class Persona:
    """A fictional person: how they write, what they sent, received and want written."""

    key: str
    name: str
    style: Style
    sent: tuple[str, ...]
    canaries: tuple[str, ...]
    received: tuple[Received, ...]
    composed: tuple[Compose, ...]


PERSONAS: Final[tuple[Persona, ...]] = (
    Persona(
        key="seb",
        name="Sébastien Morel",
        style=Style(
            "fr", r"^(salut|hello|coucou)\b", r"(\+\+|bises|a\+|à \+)", "Seb", "tu", True, 70
        ),
        sent=(
            "Salut Marco,\n\nOk pour samedi, je ramène les cordes pour Fontainebleau 🧗\n\n++\nSeb",
            "Hello Léa,\n\nTop, merci ! Je regarde le devis du garage Lambert ce soir et je te dis 👍\n\n++\nSeb",
            "Salut Tom,\n\nPas dispo jeudi, on décale à mardi ?\n\n++\nSeb",
            "Coucou Inès,\n\nJ'ai vu ton message pour le projet Orion, je m'en occupe demain 😉\n\nBises\nSeb",
            "Salut Karim,\n\nVendu ! On se retrouve au café Odette à 9h.\n\n++\nSeb",
            "Hello Paul,\n\nMerci pour les photos de Chamonix, trop belles 😍\n\n++\nSeb",
        ),
        canaries=("Fontainebleau", "Lambert", "Orion", "Odette", "Chamonix", "cordes"),
        received=(
            Received(
                "seb-meeting",
                "Claire",
                "Salut Seb, on peut décaler notre point de jeudi à vendredi 10h ? Merci ! Claire",
                "dis oui",
            ),
            Received(
                "seb-invite",
                "Julien",
                "Hello Seb, petit apéro chez moi samedi soir, tu viens ? Julien",
                "décline poliment, je ne suis pas là ce week-end",
            ),
            Received(
                "seb-doc",
                "Nadia",
                "Salut Seb, tu as pu relire le document que je t'ai envoyé ? Nadia",
                "dis que je le relis demain matin",
            ),
        ),
        composed=(
            Compose(
                "seb-move", "Claire", "propose-lui de décaler notre point de jeudi à vendredi 10h"
            ),
            Compose("seb-thanks", "Julien", "remercie-le pour l'apéro de samedi soir"),
        ),
    ),
    Persona(
        key="marie",
        name="Marie Durand",
        style=Style(
            "fr",
            r"^(bonjour|madame|monsieur|cher|chère)\b",
            r"(bien cordialement|cordialement|bien à vous)",
            "Marie Durand",
            "vous",
            False,
            110,
        ),
        sent=(
            "Bonjour Monsieur Garnier,\n\nJe vous remercie pour votre retour concernant le dossier Vauban. "
            "Je vous propose d'en reparler lors de notre réunion du comité de Lyon.\n\nBien cordialement,\nMarie Durand",
            "Bonjour Madame Petit,\n\nVeuillez trouver mes remarques sur le contrat Hélios. Je reste à votre "
            "disposition pour en discuter.\n\nBien cordialement,\nMarie Durand",
            "Bonjour,\n\nJe vous confirme ma présence au séminaire d'Annecy.\n\nBien cordialement,\nMarie Durand",
            "Bonjour Monsieur Roux,\n\nPourriez-vous me transmettre le budget révisé de l'agence de Nantes ? "
            "Je vous en remercie par avance.\n\nBien cordialement,\nMarie Durand",
            "Bonjour Madame Leroy,\n\nJe prends bonne note de votre demande et reviens vers vous d'ici "
            "vendredi.\n\nBien cordialement,\nMarie Durand",
            "Bonjour Monsieur Faure,\n\nMerci pour cet échange constructif sur le projet Atlas.\n\n"
            "Bien cordialement,\nMarie Durand",
        ),
        canaries=("Vauban", "Garnier", "Hélios", "Annecy", "Nantes", "Atlas"),
        received=(
            Received(
                "marie-meeting",
                "Thomas Bernard",
                "Bonjour Madame Durand, serait-il possible de décaler notre rendez-vous de jeudi à "
                "vendredi 10h ? Cordialement, Thomas Bernard",
                "accepte",
            ),
            Received(
                "marie-invite",
                "Sophie Martin",
                "Bonjour Marie, nous organisons un déjeuner d'équipe samedi, seriez-vous des nôtres ? "
                "Sophie Martin",
                "décline, je ne suis pas disponible",
            ),
            Received(
                "marie-doc",
                "Antoine Blanc",
                "Bonjour Madame Durand, avez-vous pu relire le document transmis lundi ? Antoine Blanc",
                "dis que je le relis demain matin",
            ),
        ),
        composed=(
            Compose(
                "marie-move",
                "Thomas Bernard",
                "propose-lui de décaler notre rendez-vous de jeudi à vendredi 10h",
            ),
            Compose("marie-thanks", "Sophie Martin", "remercie-la pour le déjeuner d'équipe"),
        ),
    ),
    Persona(
        key="jake",
        name="Jake Turner",
        style=Style("en", r"^(hey|hi)\b", r"(thx|thanks|cheers)", "J", None, False, 45),
        sent=(
            "Hey Sam,\n\nSure, Thursday works. Bring the Henderson numbers.\n\nThx,\nJ",
            "Hi Ana,\n\nGot it. Will check the Seattle lease tonight.\n\nThx,\nJ",
            "Hey Mike,\n\nCan't make it, ping me Monday.\n\nCheers,\nJ",
            "Hi Lucy,\n\nLooks good, ship it to Brightwater.\n\nThx,\nJ",
            "Hey Raj,\n\nDone. Sent the Kepler deck.\n\nThx,\nJ",
            "Hi Dan,\n\nYes to Friday, 3pm at Fulton.\n\nThx,\nJ",
        ),
        canaries=("Henderson", "Seattle", "Brightwater", "Kepler", "Fulton"),
        received=(
            Received(
                "jake-meeting",
                "Emma",
                "Hi Jake, could we move Thursday's sync to Friday at 10am? Thanks, Emma",
                "say yes",
            ),
            Received(
                "jake-invite",
                "Chris",
                "Hey Jake, a few of us are grabbing drinks on Saturday, want to join? Chris",
                "decline, I'm away this weekend",
            ),
            Received(
                "jake-doc",
                "Priya",
                "Hi Jake, did you get a chance to review the doc I sent? Priya",
                "say I'll review it tomorrow morning",
            ),
        ),
        composed=(
            Compose("jake-move", "Emma", "ask her to move Thursday's sync to Friday at 10am"),
            Compose("jake-thanks", "Chris", "thank him for the drinks on Saturday"),
        ),
    ),
    Persona(
        key="clara",
        name="Clara Weiss",
        style=Style(
            "en",
            r"^(dear|hello)\b",
            r"(warm regards|warmly|with warm wishes|kind regards)",
            "Clara",
            None,
            False,
            140,
        ),
        sent=(
            "Dear Oliver,\n\nThank you so much for your thoughtful note about the Riverside exhibition. "
            "I truly appreciated your perspective, and I look forward to continuing our conversation.\n\n"
            "Warm regards,\nClara",
            "Hello Grace,\n\nWhat a lovely surprise to hear from you! I would be delighted to join the "
            "Ashford book club next month.\n\nWarm regards,\nClara",
            "Dear Henry,\n\nI hope your week is going well. I have attached my notes on the Mercer "
            "proposal, and I would welcome your thoughts.\n\nWarm regards,\nClara",
            "Hello Ruth,\n\nThank you for the wonderful dinner at Bellamy's; it was a joy to see "
            "everyone.\n\nWarm regards,\nClara",
            "Dear Walter,\n\nI am grateful for your patience while I gathered the Lindgren figures.\n\n"
            "Warm regards,\nClara",
            "Hello Nora,\n\nI loved the photos from Kyoto; thank you for sharing them.\n\nWarm regards,\nClara",
        ),
        canaries=("Riverside", "Ashford", "Mercer", "Bellamy", "Lindgren", "Kyoto"),
        received=(
            Received(
                "clara-meeting",
                "Peter",
                "Hi Clara, would it be possible to move Thursday's meeting to Friday at 10am? Best, Peter",
                "say yes",
            ),
            Received(
                "clara-invite",
                "Laura",
                "Hello Clara, we're hosting a small garden party on Saturday. Would you like to come? Laura",
                "decline kindly, I'm away this weekend",
            ),
            Received(
                "clara-doc",
                "Ben",
                "Hi Clara, did you have a chance to look at the document I sent on Monday? Ben",
                "say I'll read it tomorrow morning",
            ),
        ),
        composed=(
            Compose("clara-move", "Peter", "ask him to move Thursday's meeting to Friday at 10am"),
            Compose("clara-thanks", "Laura", "thank her for the lovely garden party"),
        ),
    ),
)

_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
_TU = re.compile(r"\b(tu|te|t'|toi|ton|ta|tes)\b", re.IGNORECASE)
_VOUS = re.compile(r"\b(vous|votre|vos)\b", re.IGNORECASE)


@dataclass
class Draft:
    """One reply drafted, and what the rules read in it."""

    persona: str
    received: str
    family: str
    arm: str
    text: str
    marks: dict[str, bool] = field(default_factory=dict)
    leaked: list[str] = field(default_factory=list)
    cost_eur: float = 0.0


def answer_text(content: object) -> str:
    """A model's answer as words, whatever shape its content takes (pure)."""
    return coerce_content_to_text(content).strip()


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def marks(style: Style, text: str) -> dict[str, bool]:
    """Which of the persona's marks the draft carries (pure: no model)."""
    lines = _lines(text)
    first = lines[0].lower() if lines else ""
    tail = " ".join(lines[-3:]).lower() if lines else ""
    last = lines[-1] if lines else ""
    result = {
        "greeting": bool(re.search(style.greeting, first)),
        "closing": bool(re.search(style.closing, tail)),
        "signature": (last == style.signature) if style.signature else not _signed(lines),
        "emoji": bool(_EMOJI.search(text)) == style.emoji,
        "length": len(text.split()) <= style.max_words,
    }
    if style.register is not None:
        # A reply with no pronoun of address contradicts neither register.
        tu, vous = len(_TU.findall(text)), len(_VOUS.findall(text))
        result["register"] = (vous == 0 or tu > vous) if style.register == "tu" else (tu == 0)
    return result


def _signed(lines: list[str]) -> bool:
    """A last line made of one or two capitalised words reads as a signature."""
    if not lines:
        return False
    words = lines[-1].split()
    return 0 < len(words) <= 2 and all(word[:1].isupper() for word in words)


def leaked(persona: Persona, text: str) -> list[str]:
    """The planted facts of the person's past mail that the new reply writes."""
    lowered = text.lower()
    return [canary for canary in persona.canaries if canary.lower() in lowered]


def tally(drafts: list[Draft]) -> dict[str, dict[str, object]]:
    """Per family and arm: the share of marks carried, per mark, and the leaks."""
    groups: dict[str, list[Draft]] = defaultdict(list)
    for draft in drafts:
        groups[f"{draft.family} / {draft.arm}"].append(draft)
    summary: dict[str, dict[str, object]] = {}
    for key, rows in sorted(groups.items()):
        carried = sum(sum(d.marks.values()) for d in rows)
        possible = sum(len(d.marks) for d in rows)
        per_mark: dict[str, str] = {}
        for mark in sorted({m for d in rows for m in d.marks}):
            have = [d.marks[mark] for d in rows if mark in d.marks]
            per_mark[mark] = f"{sum(have)}/{len(have)}"
        summary[key] = {
            "marks": f"{carried}/{possible}",
            "per_mark": per_mark,
            "leaks": sum(1 for d in rows if d.leaked),
            "drafts": len(rows),
        }
    return summary


def draft_messages(
    persona: Persona, received: Received, arm: Arm, profile: str | None
) -> list[BaseMessage]:
    """The drafting call for one arm, rendered as production renders it (pure).

    The received e-mail reaches the model as external content and the static rules as
    the system message (``reply_drafting.draft_reply_body``); the profile arm's block is
    production's own (``writing_style.reply_block``), in its place. A cut, stated: the
    model answers in plain text here, not through the structured door.
    """
    original = {"id": received.key, "from": received.sender, "subject": "", "body": received.text}
    style = ""
    if arm == "profile":
        style = reply_block(profile)
    elif arm == "examples":
        shown = "\n\n---\n\n".join(persona.sent[:EXAMPLES_SHOWN])
        style = EXAMPLES_BLOCK.format(examples=shown) + "\n\n"
    rendered = load_prompt("mailbox_reply_draft_prompt").format(
        instruction=received.instruction,
        original=received_as_external(original),
        previous_reply=earlier_answer_as_external(original, None),
        sender_name=persona.name,
        user_language=get_language_name(persona.style.language),
        writing_style=style,
    )
    return single_call_messages(rendered)


def compose_prompt(persona: Persona, item: Compose, arm: ComposeArm, profile: str | None) -> str:
    """The new-mail call for one arm, rendered as production renders it (pure).

    Production sends the generation prompt as ONE string (``generate_email_content``);
    the profile arm's block is production's own (``writing_style.compose_block``).
    """
    return load_prompt("email_content_generation_prompt").format(
        instruction=item.instruction,
        recipient=item.recipient,
        sender_name=persona.name,
        user_language=get_language_name(persona.style.language),
        writing_style=compose_block(profile) if arm == "profile" else "",
    )


def profile_request(persona: Persona) -> list[BaseMessage]:
    """Production's learning call on the persona's sent e-mails (``profile_messages``)."""
    return profile_messages(sent_samples([{"body": mail} for mail in persona.sent]))


def composed_body(answer: str) -> str:
    """The body of a composed mail as production reads it (fences off, JSON), else empty."""
    content = answer.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return ""
    return str(parsed.get("body") or "").strip() if isinstance(parsed, dict) else ""


async def run_compose(families: list[Family | None], budget: float) -> dict[str, object]:
    """Every persona's new mails, with and without their profile, on every family."""
    await prepare_bench()
    drafts: list[Draft] = []
    spent = 0.0
    for family in families:
        model, llm, _config = family_llm(SLOT, family)
        for persona in PERSONAS:
            profile, cost = await _ask(llm, profile_request(persona), model)
            spent += cost
            for item in persona.composed:
                for arm in COMPOSE_ARMS:
                    if spent > budget:
                        raise SystemExit(f"budget reached: {spent:.4f} EUR")
                    answer, cost = await _ask(
                        llm,
                        [HumanMessage(content=compose_prompt(persona, item, arm, profile))],
                        model,
                    )
                    spent += cost
                    body = composed_body(answer)
                    drafts.append(
                        Draft(
                            persona=persona.key,
                            received=item.key,
                            family=model,
                            arm=arm,
                            text=body,
                            marks=marks(persona.style, body),
                            leaked=leaked(persona, body),
                            cost_eur=cost,
                        )
                    )
    return {
        "summary": tally(drafts),
        "unparsed": sum(1 for d in drafts if not d.text),
        "spent_eur": round(spent, 4),
        "drafts": [asdict(d) for d in drafts],
    }


async def _ask(llm: BaseChatModel, messages: list[BaseMessage], model: str) -> tuple[str, float]:
    response = await llm.ainvoke(messages)
    priced = price_response(response, model)
    # A Responses-API family answers with a list of blocks: read its words, never its repr.
    return answer_text(response.content), priced.cost_eur


async def run(
    families: list[Family | None], judge: Family | None, budget: float
) -> dict[str, object]:
    """Every persona, received e-mail and arm, on every family, within the budget."""
    await prepare_bench()
    drafts: list[Draft] = []
    spent = 0.0
    votes: dict[str, list[int]] = defaultdict(list)
    for family in families:
        model, llm, _config = family_llm(SLOT, family)
        for persona in PERSONAS:
            profile, cost = await _ask(llm, profile_request(persona), model)
            spent += cost
            for received in persona.received:
                for arm in ARMS:
                    if spent > budget:
                        raise SystemExit(f"budget reached: {spent:.4f} EUR")
                    text, cost = await _ask(
                        llm, draft_messages(persona, received, arm, profile), model
                    )
                    spent += cost
                    drafts.append(
                        Draft(
                            persona=persona.key,
                            received=received.key,
                            family=model,
                            arm=arm,
                            text=text,
                            marks=marks(persona.style, text),
                            leaked=leaked(persona, text),
                            cost_eur=cost,
                        )
                    )
    if judge is not None:
        judge_model, judge_llm, _ = family_llm(SLOT, judge)
        rng = random.Random(19)
        by_key = {(d.family, d.persona, d.received, d.arm): d for d in drafts}
        for (family_name, persona_key, received_key, arm_name), draft in by_key.items():
            if arm_name == "plain":
                continue
            plain = by_key[(family_name, persona_key, received_key, "plain")]
            persona = next(p for p in PERSONAS if p.key == persona_key)
            flipped = rng.random() < 0.5
            a, b = (draft.text, plain.text) if not flipped else (plain.text, draft.text)
            verdict, cost = await _ask(
                judge_llm,
                [
                    HumanMessage(
                        content=JUDGE_REQUEST.format(
                            reference="\n\n---\n\n".join(persona.sent[EXAMPLES_SHOWN:]), a=a, b=b
                        )
                    )
                ],
                judge_model,
            )
            spent += cost
            letter = verdict.strip()[:1].upper()
            won = (letter == "A") != flipped
            votes[f"{family_name} / {arm_name} beats plain"].append(int(won))
    return {
        "summary": tally(drafts),
        "judge": {key: f"{sum(v)}/{len(v)}" for key, v in sorted(votes.items())},
        "spent_eur": round(spent, 4),
        "drafts": [asdict(d) for d in drafts],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--models", default=None, help="provider:model[@level],... (default: the slot)"
    )
    parser.add_argument("--judge", default=None, help="provider:model[@level] for the blind vote")
    parser.add_argument("--budget-eur", type=float, default=0.30, help="stop past this spend")
    parser.add_argument("--out", type=Path, default=None, help="write every draft as JSON")
    parser.add_argument("--dry-run", action="store_true", help="print the calls, ask no model")
    parser.add_argument(
        "--compose", action="store_true", help="measure NEW mails (the generation prompt)"
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        persona = PERSONAS[0]
        for arm in ARMS:
            messages = draft_messages(persona, persona.received[0], arm, "(profile)")
            sys.stdout.write(f"--- {arm}: {sum(len(str(m.content)) for m in messages)} chars\n")
        for compose_arm in COMPOSE_ARMS:
            prompt = compose_prompt(persona, persona.composed[0], compose_arm, "(profile)")
            sys.stdout.write(f"--- compose {compose_arm}: {len(prompt)} chars\n")
        return 0
    if args.compose:
        result = asyncio.run(run_compose(parse_families(args.models), args.budget_eur))
        shown: tuple[str, ...] = ("summary", "unparsed", "spent_eur")
    else:
        judge = parse_families(args.judge)[0] if args.judge else None
        result = asyncio.run(run(parse_families(args.models), judge, args.budget_eur))
        shown = ("summary", "judge", "spent_eur")
    if args.out is not None:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump(
        {key: result[key] for key in shown},
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
