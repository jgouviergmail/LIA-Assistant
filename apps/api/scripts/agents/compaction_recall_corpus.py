"""Fictional discussions for the compaction recall bench (lot 16): no real person's data.

Each discussion plants facts in its older part, the part a compaction summarises, and
asks one question per fact with the rule its answer must satisfy. Four kinds:

- ``person``: what the person said in their own words (a constraint, a name, an amount);
- ``tool``: what a tool returned and the answer did not repeat;
- ``identifier``: an exact token to copy (a reference, an address);
- ``decision``: what LIA did on the person's request (an event, a reminder, a share).

The last discussion ends on a turn heavy in tool calls, the shape of a ReAct turn: its
``recent`` fact sits in a turn the response window still showed before the compaction,
but outside the tail of messages the compaction keeps.

Every fact's rule matches the exchange that plants it and nothing else, so a match in a
context is the fact itself, never an echo (``tests/unit/scripts/test_compaction_recall_measure.py``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.infrastructure.llm.message_view import stamped_now

Kind = Literal["person", "tool", "identifier", "decision"]
KINDS: Final[tuple[Kind, ...]] = ("person", "tool", "identifier", "decision")

#: When the first message of every discussion was written; each turn follows by 7 minutes.
START: Final = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)
_STEP: Final = timedelta(minutes=7)


@dataclass(frozen=True)
class Fact:
    """One planted fact, the question that asks for it, and the rule an answer meets.

    Attributes:
        key: Stable name.
        kind: What sort of fact it is.
        exchange: The exchange that plants it.
        question: Asked in the discussion's language.
        pattern: A regular expression the answer, and a context still holding the
            fact, must match.
        recent: True when the exchange sits in the turns the response window showed
            before the compaction.
    """

    key: str
    kind: Kind
    exchange: str
    question: str
    pattern: str
    recent: bool = False


@dataclass(frozen=True)
class Exchange:
    """One turn: the person's message, the tool calls it led to, and the answer.

    Attributes:
        key: Stable name, referenced by the facts it plants.
        person: What the person wrote.
        answer: LIA's final answer.
        tool_rounds: Each round is a list of ``(tool name, arguments, result)``.
    """

    key: str
    person: str
    answer: str
    tool_rounds: tuple[tuple[tuple[str, dict[str, object], dict[str, object]], ...], ...] = ()


@dataclass(frozen=True)
class Discussion:
    """A fictional discussion, in the order its exchanges happened."""

    key: str
    language: str
    exchanges: tuple[Exchange, ...]
    facts: tuple[Fact, ...]


def exchange_messages(discussion: str, index: int, exchange: Exchange) -> list[BaseMessage]:
    """The messages of one exchange, the person's stamped with when it was written.

    Args:
        discussion: The discussion's key, for the message ids.
        index: The exchange's position, which dates it.
        exchange: The exchange.

    Returns:
        The person's message, each tool round (a call, then its results), the answer.
    """
    prefix = f"{discussion}-{exchange.key}"
    written = START + _STEP * index
    messages: list[BaseMessage] = [
        stamped_now(HumanMessage(exchange.person, id=f"{prefix}-person"), written)
    ]
    for round_index, calls in enumerate(exchange.tool_rounds):
        ids = [f"{prefix}-call-{round_index}-{n}" for n in range(len(calls))]
        messages.append(
            AIMessage(
                "",
                id=f"{prefix}-calls-{round_index}",
                tool_calls=[
                    {"name": name, "args": args, "id": call_id}
                    for (name, args, _result), call_id in zip(calls, ids, strict=True)
                ],
            )
        )
        messages.extend(
            ToolMessage(
                json.dumps(result, ensure_ascii=False),
                tool_call_id=call_id,
                name=name,
                id=f"{call_id}-result",
            )
            for (name, _args, result), call_id in zip(calls, ids, strict=True)
        )
    messages.append(AIMessage(exchange.answer, id=f"{prefix}-answer"))
    return messages


def discussion_messages(discussion: Discussion) -> list[BaseMessage]:
    """Every message of the discussion, oldest first."""
    return [
        message
        for index, exchange in enumerate(discussion.exchanges)
        for message in exchange_messages(discussion.key, index, exchange)
    ]


# ---------------------------------------------------------------------------
# Small talk that plants nothing: it gives the compacted part its length.
# ---------------------------------------------------------------------------

_FILLER_FR: Final = (
    Exchange(
        "f-aller",
        "Tu peux me rappeler la différence entre un billet aller simple et un aller-retour ouvert ?",
        "Un aller simple ne couvre que le trajet de départ. Un aller-retour ouvert réserve le "
        "trajet retour sans en fixer la date : tu choisis le jour plus tard, dans la limite de "
        "validité du billet, souvent quelques mois. C'est pratique quand on ne connaît pas encore "
        "la durée du séjour, un peu plus cher qu'un retour daté.",
    ),
    Exchange(
        "f-saison",
        "Quelle est la meilleure saison pour flâner dans le Vieux Lyon ?",
        "Le printemps et le début de l'automne sont les plus agréables : les traboules sont moins "
        "fréquentées qu'en été et les terrasses restent ouvertes. En décembre, la Fête des "
        "Lumières attire beaucoup de monde le soir, mieux vaut s'y promener le matin.",
    ),
    Exchange(
        "f-bouchons",
        "Donne-moi trois spécialités qu'on trouve dans les bouchons lyonnais.",
        "Les quenelles de brochet sauce Nantua, le tablier de sapeur et la cervelle de canut, un "
        "fromage blanc aux herbes. On y sert aussi souvent la salade lyonnaise et la tarte aux "
        "pralines en dessert.",
    ),
    Exchange(
        "f-italien",
        "Comment dit-on « bon appétit » en italien ?",
        "« Buon appetito ». On répond souvent « altrettanto », qui veut dire « à vous aussi ».",
    ),
    Exchange(
        "f-lumieres",
        "Résume-moi en deux phrases l'origine de la Fête des Lumières.",
        "Elle remonte à décembre 1852, quand les Lyonnais ont illuminé leurs fenêtres pour "
        "l'inauguration d'une statue de la Vierge sur la colline de Fourvière. La tradition des "
        "lumignons aux fenêtres est restée et la ville en a fait un festival de lumière.",
    ),
    Exchange(
        "f-climat",
        "Quel temps fait-il d'habitude à Lyon fin novembre ?",
        "Il fait frais : souvent entre 3 et 9 °C, avec des matinées brumeuses près des quais. "
        "Prévois un manteau chaud et des chaussures qui supportent la pluie.",
    ),
    Exchange(
        "f-valise",
        "Quelle taille de valise me conseilles-tu pour un court séjour ?",
        "Une valise cabine suffit en général : environ 55 cm, de quoi emporter deux tenues, une "
        "trousse de toilette et un pull. Elle évite l'attente aux bagages.",
    ),
    Exchange(
        "f-merci",
        "Merci, c'est très clair.",
        "Avec plaisir ! Dis-moi si tu veux que je prépare autre chose pour le séjour.",
    ),
    Exchange(
        "f-musee",
        "Il y a un musée à ne pas manquer là-bas ?",
        "Le musée des Confluences, à la pointe de la presqu'île : sciences naturelles et "
        "anthropologie dans un bâtiment spectaculaire. Le musée des Beaux-Arts, place des "
        "Terreaux, est aussi très riche.",
    ),
    Exchange(
        "f-metro",
        "Le métro lyonnais est-il pratique pour se déplacer ?",
        "Oui : quatre lignes et un funiculaire jusqu'à Fourvière. Un ticket à l'unité couvre une "
        "heure de trajet avec correspondances.",
    ),
)

_FILLER_EN: Final = (
    Exchange(
        "f-grout",
        "What's the difference between sanded and unsanded grout?",
        "Sanded grout has fine sand mixed in, which makes it stronger for wide joints, usually "
        "above an eighth of an inch. Unsanded grout is smoother and suits narrow joints and "
        "delicate surfaces like polished stone, which sand could scratch.",
    ),
    Exchange(
        "f-paint",
        "Should I use eggshell or satin paint in a hallway?",
        "Satin is the safer pick for a hallway: it wipes clean more easily and stands up to scuffs. "
        "Eggshell looks softer but marks sooner in places people brush past.",
    ),
    Exchange(
        "f-drying",
        "How long does tile adhesive need before grouting?",
        "Most cement-based adhesives want about a day before you grout, longer in a cold or damp "
        "room. The bag gives the figure for that product.",
    ),
    Exchange(
        "f-joke",
        "Tell me a quick joke about plumbers.",
        "Why did the plumber break up with the sink? It was always so draining.",
    ),
    Exchange(
        "f-light",
        "Warm or cool white bulbs for a kitchen?",
        "Many people like a neutral white around 3000 to 4000 kelvin in a kitchen: warm enough to "
        "feel cosy, cool enough to see food colours properly over the worktop.",
    ),
    Exchange(
        "f-dust",
        "Any tips to keep dust down while they work?",
        "Seal doorways with plastic sheeting, cover vents, and run an air purifier in the next "
        "room. A damp mop at the end of each day stops the dust spreading through the house.",
    ),
    Exchange(
        "f-thanks",
        "Thanks, that helps.",
        "Glad it does! Tell me if you want me to look into anything else for the work.",
    ),
    Exchange(
        "f-skip",
        "Is it worth hiring a skip for the old cabinets?",
        "For a full kitchen, usually yes: a small skip takes the old units and the rubble in one "
        "go. Check whether it can stand on the road, which may need a permit from the council.",
    ),
    Exchange(
        "f-seal",
        "Do I need to seal natural stone worktops?",
        "Yes, most natural stone is porous: a penetrating sealer stops oil and wine from staining. "
        "Granite needs it less often than marble or limestone.",
    ),
    Exchange(
        "f-socket",
        "How high should kitchen sockets be above the worktop?",
        "A common height is about a hand's span above the worktop, so plugs clear the splashback "
        "and cables stay out of the way.",
    ),
)


def _call(name: str, args: dict[str, object], result: dict[str, object]) -> tuple:
    return (name, args, result)


# ---------------------------------------------------------------------------
# Discussion 1 (fr): a trip to Lyon.
# ---------------------------------------------------------------------------

_TRIP: Final = Discussion(
    key="trip-fr",
    language="fr",
    exchanges=(
        _FILLER_FR[0],
        Exchange(
            "p-vol",
            "Petite règle pour tous mes voyages : je ne prends jamais de vol avant 10 h du matin.",
            "C'est noté, je ne te proposerai aucun vol qui décolle avant cette heure-là.",
        ),
        _FILLER_FR[1],
        Exchange(
            "p-fille",
            "Ma fille Inès vient avec nous, elle a sept ans.",
            "Très bien, je compte un enfant dans les réservations.",
        ),
        _FILLER_FR[2],
        Exchange(
            "p-budget",
            "Pour l'hôtel, mon budget maximum est de 1 450 € pour les trois nuits.",
            "Entendu, je reste sous ce plafond pour l'hébergement.",
        ),
        _FILLER_FR[3],
        Exchange(
            "t-hotel",
            "Réserve l'Hôtel des Célestins à partir du 20 novembre, trois nuits.",
            "C'est réservé : trois nuits à l'Hôtel des Célestins à partir du 20 novembre.",
            (
                (
                    _call(
                        "book_hotel_tool",
                        {"hotel": "Hôtel des Célestins", "check_in": "2026-11-20", "nights": 3},
                        {
                            "status": "confirmed",
                            "reference": "LYC-58213",
                            "contact_email": "reservations@hotel-celestins.example",
                            "total_eur": 1290,
                        },
                    ),
                ),
            ),
        ),
        _FILLER_FR[4],
        Exchange(
            "d-train",
            "Ajoute le train à mon agenda : départ le 20 novembre à 10 h 34 de Paris Gare de Lyon.",
            "C'est dans ton agenda.",
            (
                (
                    _call(
                        "create_event_tool",
                        {"title": "Train Paris → Lyon", "start": "2026-11-20T10:34:00+01:00"},
                        {"status": "created", "event_id": "evt_4c19b2"},
                    ),
                ),
            ),
        ),
        _FILLER_FR[5],
        _FILLER_FR[6],
        _FILLER_FR[7],
        _FILLER_FR[8],
        _FILLER_FR[9],
        Exchange(
            "f-q1",
            "Et pour le dîner du premier soir ?",
            "Je te conseille un bouchon près des Terreaux.",
        ),
        Exchange(
            "f-q2", "Il faut réserver ?", "Oui, surtout le vendredi soir : les salles sont petites."
        ),
    ),
    facts=(
        Fact(
            "vol",
            "person",
            "p-vol",
            "À partir de quelle heure la personne accepte-t-elle de prendre un vol ?",
            r"\b10\s*(?:h|heures?|:)\s*(?:00)?(?!\s*\d)",
        ),
        Fact(
            "fille", "person", "p-fille", "Comment s'appelle la fille de la personne ?", r"In[eè]s"
        ),
        Fact(
            "budget",
            "person",
            "p-budget",
            "Quel est le budget maximum de la personne pour l'hôtel ? Donne le montant.",
            r"1[\s  .,]?450",
        ),
        Fact(
            "reference",
            "identifier",
            "t-hotel",
            "Quelle est la référence de la réservation d'hôtel ?",
            r"LYC-?58213",
        ),
        Fact(
            "email",
            "identifier",
            "t-hotel",
            "Quelle est l'adresse e-mail de contact de l'hôtel ?",
            r"reservations@hotel-celestins\.example",
        ),
        Fact(
            "montant",
            "tool",
            "t-hotel",
            "Combien coûtent au total les trois nuits réservées à l'hôtel ?",
            r"1[\s  .,]?290",
        ),
        Fact(
            "train",
            "decision",
            "d-train",
            "À quelle heure part le train pour Lyon que LIA a ajouté à l'agenda ?",
            r"10\s*[h:]\s*34",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Discussion 2 (en): a kitchen renovation.
# ---------------------------------------------------------------------------

_KITCHEN: Final = Discussion(
    key="kitchen-en",
    language="en",
    exchanges=(
        _FILLER_EN[0],
        Exchange(
            "p-wednesday",
            "One rule: never call me on Wednesdays, I teach all day.",
            "Understood, I won't schedule any call on that day.",
        ),
        _FILLER_EN[1],
        Exchange(
            "p-tiles",
            "For the kitchen it has to be the matte sage-green tiles, not the glossy ones.",
            "Noted, I'll keep that finish in mind for the order.",
        ),
        _FILLER_EN[2],
        Exchange(
            "p-ladder",
            "My neighbour Bartholomew is lending us his ladder on Saturday.",
            "Good, one less thing to buy.",
        ),
        _FILLER_EN[3],
        Exchange(
            "t-quote",
            "Find the contractor's quote in my emails.",
            "I found the contractor's quote for the kitchen; it is valid until mid-December.",
            (
                (
                    _call(
                        "search_emails_tool",
                        {"query": "contractor quote kitchen"},
                        {
                            "emails": [
                                {
                                    "from": "quotes@renov-pro.example",
                                    "subject": "Your kitchen renovation quote",
                                    "body": "Quote Q-2291: kitchen renovation, 8,740 EUR incl. "
                                    "VAT, valid until 15 December 2026.",
                                }
                            ]
                        },
                    ),
                ),
            ),
        ),
        _FILLER_EN[4],
        Exchange(
            "d-reminder",
            "Remind me to call the contractor back on 3 December at 9am.",
            "Done, I'll remind you then.",
            (
                (
                    _call(
                        "create_reminder_tool",
                        {"text": "Call the contractor back", "trigger_at": "2026-12-03T09:00"},
                        {"status": "created", "reminder_id": "rem_77a1"},
                    ),
                ),
            ),
        ),
        _FILLER_EN[5],
        _FILLER_EN[6],
        _FILLER_EN[7],
        _FILLER_EN[8],
        _FILLER_EN[9],
        Exchange(
            "f-q1",
            "Should the fridge go left of the sink?",
            "Left works if the door opens away from it.",
        ),
        Exchange("f-q2", "And the bin?", "Under the sink, in a pull-out unit."),
    ),
    facts=(
        Fact(
            "wednesday",
            "person",
            "p-wednesday",
            "On which day of the week must LIA never call the person?",
            r"(?i)wednesday",
        ),
        Fact(
            "tiles",
            "person",
            "p-tiles",
            "Which tiles did the person choose for the kitchen?",
            r"(?i)matte.{0,25}sage|sage.{0,25}matte",
        ),
        Fact("ladder", "person", "p-ladder", "Who is lending the ladder?", r"Bartholomew"),
        Fact(
            "amount",
            "tool",
            "t-quote",
            "What is the amount of the contractor's quote?",
            r"8[\s,. ]?740",
        ),
        Fact("quote", "identifier", "t-quote", "What is the quote's number?", r"Q-?2291"),
        Fact(
            "reminder",
            "decision",
            "d-reminder",
            "For when is the reminder to call the contractor back set?",
            r"(?i)\b3(rd)?\s+december|december\s+3(rd)?\b|2026-12-03",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Discussion 3 (fr): running.
# ---------------------------------------------------------------------------

_RUNNING: Final = Discussion(
    key="running-fr",
    language="fr",
    exchanges=(
        _FILLER_FR[3],
        Exchange(
            "p-allergie",
            "Je suis allergique aux arachides, pense-y pour toutes les recettes.",
            "C'est noté, je les écarterai de toutes mes propositions.",
        ),
        _FILLER_FR[0],
        Exchange(
            "p-medecin",
            "Mon médecin du sport, le Dr Okonkwo, ne consulte que le mardi.",
            "D'accord, je proposerai les rendez-vous ce jour-là.",
        ),
        _FILLER_FR[6],
        Exchange(
            "p-objectif",
            "Mon objectif : boucler la course en moins de 52 minutes.",
            "Objectif enregistré, on bâtira le plan d'entraînement autour.",
        ),
        _FILLER_FR[9],
        Exchange(
            "t-course",
            "Inscris-moi aux Foulées de l'Erdre.",
            "Tu es inscrit aux Foulées de l'Erdre.",
            (
                (
                    _call(
                        "register_race_tool",
                        {"race": "Les Foulées de l'Erdre"},
                        {
                            "status": "registered",
                            "bib_reference": "ERD-7734",
                            "race_date": "2026-12-06",
                        },
                    ),
                ),
            ),
        ),
        _FILLER_FR[8],
        Exchange(
            "d-fractionne",
            "Ajoute un entraînement fractionné chaque jeudi à 19 h.",
            "C'est ajouté à ton agenda.",
            (
                (
                    _call(
                        "create_event_tool",
                        {
                            "title": "Fractionné",
                            "start": "19:00",
                            "recurrence": "FREQ=WEEKLY;BYDAY=TH",
                        },
                        {"status": "created", "event_id": "evt_9d02"},
                    ),
                ),
            ),
        ),
        _FILLER_FR[1],
        _FILLER_FR[2],
        _FILLER_FR[4],
        _FILLER_FR[5],
        _FILLER_FR[7],
        Exchange("f-q1", "Je cours en côte demain ?", "Oui, une séance courte suffit."),
        Exchange("f-q2", "Avec quelles chaussures ?", "Tes chaussures d'entraînement habituelles."),
    ),
    facts=(
        Fact(
            "allergie",
            "person",
            "p-allergie",
            "À quoi la personne est-elle allergique ?",
            r"(?i)arachide|cacahu[eè]te",
        ),
        Fact(
            "medecin",
            "person",
            "p-medecin",
            "Comment s'appelle le médecin du sport de la personne ?",
            r"Okonkwo",
        ),
        Fact(
            "objectif",
            "person",
            "p-objectif",
            "En combien de minutes au plus la personne veut-elle boucler la course ?",
            r"\b52\b",
        ),
        Fact(
            "dossard",
            "identifier",
            "t-course",
            "Quelle est la référence de l'inscription à la course ?",
            r"ERD-?7734",
        ),
        Fact(
            "date",
            "tool",
            "t-course",
            "À quelle date a lieu la course des Foulées de l'Erdre ?",
            r"(?i)\b6\s+d[ée]cembre|\b6\s+december|december\s+6\b|2026-12-06",
        ),
        Fact(
            "fractionne",
            "decision",
            "d-fractionne",
            "Quel jour et à quelle heure a lieu l'entraînement fractionné ajouté à l'agenda ?",
            r"(?i)jeudi.{0,40}19|19\s*h.{0,40}jeudi",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Discussion 4 (en): a launch at work, ending on a turn heavy in tool calls.
# ---------------------------------------------------------------------------

_LAUNCH: Final = Discussion(
    key="launch-en",
    language="en",
    exchanges=(
        _FILLER_EN[1],
        Exchange(
            "p-priya",
            "Never copy my manager Priya on anything about the budget.",
            "Understood, she won't be on any budget email.",
        ),
        _FILLER_EN[9],
        Exchange(
            "p-british",
            "Use British spelling in every document you write for me.",
            "Will do, from now on.",
        ),
        _FILLER_EN[4],
        Exchange(
            "t-roadmap",
            "Find the Q4 roadmap document.",
            "Found it: the Q4 roadmap, in your drive.",
            (
                (
                    _call(
                        "search_files_tool",
                        {"query": "Q4 roadmap"},
                        {"files": [{"id": "doc_8f3a2c", "name": "Q4 roadmap", "owner": "me"}]},
                    ),
                ),
            ),
        ),
        Exchange(
            "d-share",
            "Share it with Hamza, with edit rights.",
            "Shared: Hamza can now edit it.",
            (
                (
                    _call(
                        "share_file_tool",
                        {"file": "Q4 roadmap", "with": "hamza@studio.example", "role": "writer"},
                        {"status": "shared"},
                    ),
                ),
            ),
        ),
        _FILLER_EN[6],
        _FILLER_EN[2],
        Exchange(
            "p-deadline",
            "Heads-up: the launch deadline moved to Thursday 26 November.",
            "Noted, I'll plan around that date.",
        ),
        _FILLER_EN[3],
        Exchange(
            "f-sweep",
            "Check my calendar, my emails and my tasks for anything about the launch.",
            "Three items: the go/no-go meeting, the press kit email awaiting your reply, and the "
            "QA task still open.",
            (
                (
                    _call(
                        "list_events_tool", {"query": "launch"}, {"events": [{"title": "Go/no-go"}]}
                    ),
                    _call(
                        "search_emails_tool",
                        {"query": "launch"},
                        {"emails": [{"subject": "Press kit"}]},
                    ),
                    _call(
                        "list_tasks_tool", {"query": "launch"}, {"tasks": [{"title": "QA pass"}]}
                    ),
                ),
                (
                    _call("get_event_tool", {"title": "Go/no-go"}, {"room": "Atrium"}),
                    _call("get_email_tool", {"subject": "Press kit"}, {"needs_reply": True}),
                ),
            ),
        ),
    ),
    facts=(
        Fact("priya", "person", "p-priya", "Who must never be copied on budget emails?", r"Priya"),
        Fact(
            "spelling",
            "person",
            "p-british",
            "Which spelling must LIA use in the person's documents?",
            r"(?i)british",
        ),
        Fact(
            "document",
            "identifier",
            "t-roadmap",
            "What is the identifier of the Q4 roadmap document?",
            r"doc_8f3a2c",
        ),
        Fact(
            "share",
            "decision",
            "d-share",
            "With whom was the Q4 roadmap shared?",
            r"(?i)hamza",
        ),
        Fact(
            "deadline",
            "person",
            "p-deadline",
            "What is the new launch deadline?",
            r"(?i)\b26(th)?\s+november|november\s+26|2026-11-26",
            recent=True,
        ),
    ),
)

# ---------------------------------------------------------------------------
# Discussion 5 (en): dense. Thirty searches with long results bury the person's own
# constraints, so the summary, bounded, must choose what to keep.
# ---------------------------------------------------------------------------

_TOPICS: Final = (
    "the history of the bicycle",
    "how tides work",
    "the life cycle of honeybees",
    "medieval castle architecture",
    "the chemistry of bread baking",
    "coral reef ecosystems",
    "the invention of the printing press",
    "how glaciers shape valleys",
    "the migration of monarch butterflies",
    "early jazz in New Orleans",
    "the physics of rainbows",
    "how lighthouses guide ships",
    "the origins of chess",
    "volcanic island formation",
    "the art of origami",
    "how owls hunt at night",
    "the silk road trade routes",
    "the science of sourdough starters",
    "how bridges carry loads",
    "the history of maps",
    "desert plant adaptations",
    "the craft of violin making",
    "how wind turbines work",
    "ancient Roman aqueducts",
    "the behaviour of octopuses",
    "the history of tea",
    "how auroras form",
    "the design of Japanese gardens",
)
_ASPECTS: Final = (
    "an introduction",
    "key facts",
    "a short timeline",
    "common myths",
    "what experts say",
    "a field guide",
    "frequently asked questions",
    "a beginner's overview",
    "the main debates",
    "a photo essay",
    "practical tips",
    "further reading",
    "a glossary",
    "a museum guide",
    "a classroom activity",
)


def _search(index: int, topic: str) -> Exchange:
    """A search with long results that plants nothing."""
    slug = "-".join(word for word in topic.split() if len(word) > 3)
    results = [
        {
            "title": f"{topic.capitalize()}: {aspect}",
            "url": f"https://{slug}.library.example/{aspect.replace(' ', '-')}",
            "snippet": (
                f"This page on {topic} offers {aspect}. It explains the main ideas in plain "
                "language, compares several sources and points to the open questions "
                "researchers still discuss. Readers often keep it for its clear diagrams and "
                "its careful notes on terminology."
            ),
        }
        for aspect in _ASPECTS
    ]
    return Exchange(
        f"f-search-{index}",
        f"Look up {topic} for me.",
        f"Here is what I found on {topic}: the sources agree on the basics, and the clearest "
        f"overview comes from the {slug} library. Tell me if you want one of them in detail.",
        ((_call("web_search_tool", {"query": topic}, {"results": results}),),),
    )


_DENSE_PLANTED: Final = {
    2: Exchange(
        "p-diet",
        "I'm vegetarian but I do eat fish, remember that for every restaurant you suggest.",
        "Noted, I'll only suggest places that suit you.",
    ),
    7: Exchange(
        "p-son",
        "My son Thaddeus starts at the conservatory in January.",
        "How exciting, good luck to him!",
    ),
    12: Exchange(
        "p-mortgage",
        "Our mortgage is 1,912 euros a month, never plan a budget that ignores it.",
        "Understood, I'll always count it in.",
    ),
    17: Exchange(
        "p-transport",
        "I never drive into the city centre, I always take the tram.",
        "Got it, I'll plan your trips that way.",
    ),
    22: Exchange(
        "p-fruit",
        "Strawberries make me ill, keep them out of any recipe.",
        "Noted, none in anything I suggest.",
    ),
    26: Exchange(
        "d-table",
        "Book a table at Maison Verdier for Friday evening.",
        "Your table is booked.",
        (
            (
                _call(
                    "book_table_tool",
                    {"restaurant": "Maison Verdier", "day": "Friday"},
                    {"status": "confirmed", "confirmation": "MV-3307"},
                ),
            ),
        ),
    ),
}


def _dense_exchanges() -> tuple[Exchange, ...]:
    topics = iter(_TOPICS)
    total = len(_TOPICS) + len(_DENSE_PLANTED)
    return tuple(
        _DENSE_PLANTED[index] if index in _DENSE_PLANTED else _search(index, next(topics))
        for index in range(total)
    )


_DENSE: Final = Discussion(
    key="dense-en",
    language="en",
    exchanges=_dense_exchanges(),
    facts=(
        Fact(
            "diet",
            "person",
            "p-diet",
            "What is the person's diet?",
            r"(?i)pescatarian|vegetarian.{0,80}fish|fish.{0,80}vegetarian",
        ),
        Fact("son", "person", "p-son", "What is the name of the person's son?", r"Thaddeus"),
        Fact(
            "mortgage",
            "person",
            "p-mortgage",
            "How much is the person's monthly mortgage payment?",
            r"1[\s,. ]?912",
        ),
        Fact(
            "transport",
            "person",
            "p-transport",
            "How does the person always travel into the city centre?",
            r"(?i)\btram\b",
        ),
        Fact(
            "fruit",
            "person",
            "p-fruit",
            "Which fruit must never appear in the person's recipes?",
            r"(?i)strawberr",
        ),
        Fact(
            "restaurant",
            "decision",
            "d-table",
            "At which restaurant did LIA book a table?",
            r"(?i)maison verdier",
        ),
        Fact(
            "confirmation",
            "identifier",
            "d-table",
            "What is the confirmation code of the restaurant booking?",
            r"MV-?3307",
        ),
    ),
)

DISCUSSIONS: Final[tuple[Discussion, ...]] = (_TRIP, _KITCHEN, _RUNNING, _LAUNCH, _DENSE)
