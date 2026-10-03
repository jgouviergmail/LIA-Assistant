"""What each language's wake phrase is, and what it is trained and measured on (ADR-329).

A phrase is a TRAINED model, never a free entry: the six phrases were proposed
and accepted on 2026-10-01 (spec A6). Every input that shapes a shipped model
carries a permissive licence (CC0, CC-BY); a voice under a share-alike or a
copyleft licence serves the held-out TEST set only, which is never shipped.

Pronunciations are written twice where speakers differ: « LIA » as one syllable
(/lja/, how espeak reads « Lia ») and as two (/li.a/, the acronym said slowly),
through Piper's inline phonemes (``[[ … ]]``). A near miss is a phrase a person
says that MUST NOT wake LIA; a homophone of the phrase (« dit Lia ») is not one
and is never listed.

Beside its phrase, a language ships a SPOKEN COMMAND (owner request
2026-10-01): its stop command, which cuts LIA's voice while she reads an answer
aloud — the name, then the word (« LIA, stop »), like an assistant is told:
« Stop » alone, one syllable, was found one time in two at its best and
false-triggered on songs (owner decision 2026-10-02). A command is the language's spec with its own words (``keyword="stop"``)
and the same voices and corpora; its banks and its work directory carry its
``slug`` (``fr-stop``), so the phrase's are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

#: What a model listens for: the wake phrase, or a spoken command.
Keyword = Literal["wake", "stop"]
KEYWORDS: tuple[Keyword, ...] = ("wake", "stop")

#: The revision every Piper voice is read at: a moving ``main`` is no provenance.
PIPER_REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"


@dataclass(frozen=True, slots=True)
class Voice:
    """One Piper voice.

    Attributes:
        key: The file stem on the voices repository (``fr_FR-mls-medium``).
        path: Its directory on the voices repository.
        licence: The licence of the dataset the voice was trained on.
        speakers: The speaker ids used; ``(0,)`` for a single-speaker voice.
        reads_as: For a voice of ANOTHER language: the espeak language every
            text is phonemised in before this voice reads it as inline
            phonemes — an accented speaker of the phrase, for a language with
            few voices of its own. Near misses go through the same voice, so
            an accent is never a cue for « positive ».
        share: The fraction of the per-voice budget this voice synthesises.
    """

    key: str
    path: str
    licence: str
    speakers: tuple[int, ...] = (0,)
    reads_as: str | None = None
    share: float = 1.0


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Everything one language's model is built from.

    Attributes:
        code: The frontend-canonical language code (``fr``, ``zh``…).
        phrase: The phrase as the interface shows it.
        positives: Spellings (or inline phonemes) Piper reads as the phrase;
            the first one is what each speaker's rate is calibrated on.
        near_misses: Phrases that must not wake LIA.
        leads: Short lead-ins, each ending on its pause (a comma): the phrase
            is never the first word of the utterance the voice speaks.
        carriers: Long continuations after the phrase: a VITS voice keeps
            its alignment on a long utterance and babbles on two words.
        phrase_seconds: The phrase's natural duration, the calibration target.
        spoken: Plain-text spellings for a synthesiser that reads text only
            (VoxCPM2): punctuation varies the prosody, a spelling the sound.
        accents: Accents a designed voice may carry (English words: the
            synthesiser's descriptions are written in English).
        train_voices: Voices the shipped model learns from (permissive licences).
        test_voices: Held-out voices and speakers the model is measured on.
        fleurs: The FLEURS configuration of the language (CC-BY 4.0).
        mls: The Multilingual LibriSpeech directory, or None (CC-BY 4.0).
        keyword: What the model listens for: the wake phrase or a command.
    """

    code: str
    phrase: str
    positives: tuple[str, ...]
    near_misses: tuple[str, ...]
    leads: tuple[str, ...]
    carriers: tuple[str, ...]
    phrase_seconds: float
    spoken: tuple[str, ...]
    accents: tuple[str, ...]
    train_voices: tuple[Voice, ...]
    test_voices: tuple[Voice, ...]
    fleurs: str
    mls: str | None
    keyword: Keyword = "wake"

    @property
    def slug(self) -> str:
        """The name its banks and work directory carry: the code, or ``<code>-<command>``."""
        return self.code if self.keyword == "wake" else f"{self.code}-{self.keyword}"


_MLS_FR = "fr/fr_FR/mls/medium"

FRENCH = LanguageSpec(
    code="fr",
    phrase="Dis LIA",
    positives=(
        "Dis Lia",
        "Dilia",
        "Dis, Lia",
        "Dis [[ liˈa ]]",
        "Dis [[ lˈia ]]",
    ),
    near_misses=(
        "Dis-lui",
        "Dis-le",
        "Dis là",
        "Dis-moi",
        "Dis donc",
        "Dis-leur",
        "Dis-nous",
        "Dis-le-moi",
        "Dis la vérité",
        "Dis l'heure",
        "Dis Léa",
        "Dis Lila",
        "Dis Lisa",
        "Dis Lina",
        "Dis Luna",
        "Dis Lou",
        "Dis Lili",
        "Dis Lise",
        "Dis Liam",
        "Dis Léo",
        "Dis Lucas",
        "Dis Lucie",
        "Dis Julia",
        "Dis Mia",
        "Dis Nina",
        "Dis Tia",
        "Dis Gaïa",
        "Dis Elsa",
        "Dis Alexa",
        "Dis Siri",
        "Dis Lyon",
        "Dis Lille",
        "Dis lilas",
        "Disons",
        "Dix lits",
        "Délia",
        "Lydia",
        "Dalila",
        "Liane",
        "Lilian",
        "Amélia",
        "Lia",
        "Lia, tu es là ?",
        "Allô Lia",
        "Salut Lia",
        "Merci Lia",
        "Mais dis-lui",
        "Et dis-moi",
        "Je te dis ça",
        "Tu dis quoi ?",
        "Il dit oui",
        "Dis-moi tout",
        "Dis, tu viens ?",
        "Dis, Lucas, tu viens ?",
        "Dis-lui de venir",
        "On dit là-bas",
        "Ce que je dis là",
        "Dis-le à Lila",
        "Dites-le",
        "Dis bonjour",
        "Lia, stop",
        "Lia stop",
    ),
    leads=(
        "Bon,",
        "Alors,",
        "Euh,",
        "Bah,",
        "Écoute,",
        "Oh,",
    ),
    carriers=(
        "je voudrais savoir quelle heure il est maintenant, s'il te plaît.",
        "rappelle-moi d'appeler ma sœur demain matin avant de partir au travail.",
        "est-ce que tu peux me lire mes derniers messages de la journée ?",
        "quel temps va-t-il faire cet après-midi dans la région ?",
    ),
    phrase_seconds=0.62,
    spoken=(
        "Dis Lia !",
        "Dilia !",
        "Dis Lia.",
        "Dilia.",
        "Dis Lia ?",
        "Dis, Lia.",
    ),
    accents=(
        "Parisian",
        "Southern French",
        "Belgian",
        "Quebec",
        "Swiss",
        "West African",
        "North African",
    ),
    train_voices=(
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(0, 100))),
        Voice("fr_FR-siwis-medium", "fr/fr_FR/siwis/medium", "CC-BY-4.0"),
        Voice("fr_FR-gilles-low", "fr/fr_FR/gilles/low", "CC0-1.0"),
        Voice("fr_FR-mls_1840-low", "fr/fr_FR/mls_1840/low", "CC-BY-4.0"),
    ),
    test_voices=(
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(100, 125))),
        Voice("fr_FR-upmc-medium", "fr/fr_FR/upmc/medium", "CC-BY-SA-4.0", (0, 1)),
        Voice("fr_FR-tom-medium", "fr/fr_FR/tom/medium", "AGPL-3.0"),
    ),
    fleurs="fr_fr",
    mls="mls_french",
)

_LIBRITTS = "en/en_US/libritts_r/medium"
_VCTK = "en/en_GB/vctk/medium"
_ARU = "en/en_GB/aru/medium"
_MLS_DE = "de/de_DE/mls/medium"


def _single(key: str, licence: str, reads_as: str | None = None, share: float = 1.0) -> Voice:
    """A single-speaker voice whose repository path is spelled by its key."""
    language, name, quality = key.split("-")
    return Voice(key, f"{language[:2]}/{language}/{name}/{quality}", licence, (0,), reads_as, share)


ENGLISH = LanguageSpec(
    code="en",
    phrase="Hey LIA",
    positives=(
        "Hey Lia",
        "Heylia",
        "Hey, Lia",
        "Hey [[ lˈiːə ]]",
        "Hey [[ lˈiːɑː ]]",
    ),
    near_misses=(
        "Hey Lisa",
        "Hey Lee",
        "Hey Leo",
        "Hey Liam",
        "Hey Lena",
        "Hey Lily",
        "Hey Lila",
        "Hey Luna",
        "Hey Layla",
        "Hey Lola",
        "Hey Mia",
        "Hey Pia",
        "Hey Tia",
        "Hey Nia",
        "Hey Ria",
        "Hey Kia",
        "Hey Siri",
        "Hey Alexa",
        "Hey Google",
        "Hey you",
        "Hey there",
        "Hey, listen",
        "Hey, look",
        "Hey Leon",
        "Hey Julia",
        "Hey Amelia",
        "Hey Celia",
        "Hey Delia",
        "Hey Dahlia",
        "Hey Ophelia",
        "Hey Lydia",
        "Hey Lucy",
        "Hey Lou",
        "Hey Liz",
        "Hey, let's go",
        "Hey, really?",
        "Hey, little one",
        "Okay Lia",
        "Hello Lia",
        "Thanks Lia",
        "Lia",
        "Hey",
        "Hello",
        "Hey Lisa, come here",
        "Hey, what's up?",
        "Lia, stop",
        "Lia stop",
    ),
    leads=(
        "So,",
        "Okay,",
        "Well,",
        "Um,",
        "Right,",
        "Oh,",
    ),
    carriers=(
        "what's the weather going to be like this afternoon in town?",
        "remind me to call my sister tomorrow morning before I leave for work.",
        "could you read me the latest messages I received today?",
        "what time is my first meeting on Monday morning?",
    ),
    phrase_seconds=0.6,
    spoken=(
        "Hey Lia!",
        "Heylia!",
        "Hey Lia.",
        "Hey Leeah.",
        "Hey Lia?",
        "Hey, Lia.",
    ),
    accents=(
        "American",
        "British",
        "Australian",
        "Indian",
        "Irish",
        "Scottish",
        "Nigerian",
        "Canadian",
    ),
    train_voices=(
        Voice("en_US-libritts_r-medium", _LIBRITTS, "CC-BY-4.0", tuple(range(0, 700))),
        Voice("en_GB-vctk-medium", _VCTK, "CC-BY-4.0", tuple(range(0, 85))),
        Voice("en_GB-aru-medium", _ARU, "CC-BY-4.0", tuple(range(0, 10))),
        _single("en_GB-alba-medium", "CC-BY-4.0"),
        _single("en_GB-cori-medium", "Public-Domain"),
        _single("en_US-joe-medium", "CC0-1.0"),
        _single("en_US-kathleen-low", "CC0-1.0"),
        _single("en_US-mike-medium", "CC0-1.0"),
        _single("en_US-reza_ibrahim-medium", "CC0-1.0"),
        _single("en_US-john-medium", "Public-Domain"),
        _single("en_US-kristin-medium", "Public-Domain"),
        _single("en_US-bryce-medium", "Public-Domain"),
        _single("en_US-norman-medium", "Public-Domain"),
        _single("en_US-ljspeech-medium", "Public-Domain"),
        _single("en_US-sam-medium", "Apache-2.0"),
    ),
    test_voices=(
        Voice("en_US-libritts_r-medium", _LIBRITTS, "CC-BY-4.0", tuple(range(700, 904))),
        Voice("en_GB-vctk-medium", _VCTK, "CC-BY-4.0", tuple(range(85, 109))),
        Voice("en_GB-aru-medium", _ARU, "CC-BY-4.0", (10, 11)),
        _single("en_GB-northern_english_male-medium", "CC-BY-SA-4.0"),
        _single("en_GB-southern_english_female-low", "CC-BY-SA-4.0"),
    ),
    fleurs="en_us",
    mls=None,
)

GERMAN = LanguageSpec(
    code="de",
    phrase="Hey LIA",
    positives=(
        "Hey Lia",
        "Heylia",
        "Hey, Lia",
        "[[ hˈeɪ ]] Lia",
        "Hey [[ lˈiːa ]]",
    ),
    near_misses=(
        "Hey Lisa",
        "Hey Lea",
        "Hey Leo",
        "Hey Lena",
        "Hey Lili",
        "Hey Lilli",
        "Hey Lina",
        "Hey Luna",
        "Hey Laura",
        "Hey Linda",
        "Hey Leila",
        "Hey Dalia",
        "Hey Mia",
        "Hey Nina",
        "Hey Julia",
        "Hey Liam",
        "Hey Lukas",
        "Hey Max",
        "Hey Ilja",
        "Hey Siri",
        "Hey Alexa",
        "Hey Google",
        "Hey du",
        "Hey, hallo",
        "Hey Leute",
        "Hey, sieh mal",
        "Hey, warte",
        "Hey, wie geht's?",
        "Hallo Lia",
        "Danke Lia",
        "Lia",
        "Amelia",
        "Die Lisa",
        "Hey, Lisa, komm her",
        "Heiliger",
        "Heilige Nacht",
        "Lia, stopp",
        "Lia stopp",
    ),
    leads=(
        "Also,",
        "Na,",
        "Ähm,",
        "So,",
        "Gut,",
    ),
    carriers=(
        "wie wird das Wetter heute Nachmittag in der Stadt?",
        "erinnere mich daran, morgen früh meine Schwester anzurufen.",
        "kannst du mir bitte die letzten Nachrichten von heute vorlesen?",
        "wann ist mein erster Termin am Montagmorgen?",
    ),
    phrase_seconds=0.62,
    spoken=(
        "Hey Lia!",
        "Heylia!",
        "Hey Lia.",
        "Hey Lia?",
        "Hey Liah.",
        "Hey, Lia.",
    ),
    accents=(
        "Standard German",
        "Austrian",
        "Swiss German",
        "Bavarian",
        "Berlin",
        "Northern German",
    ),
    train_voices=(
        Voice("de_DE-mls-medium", _MLS_DE, "CC-BY-4.0", tuple(range(0, 200))),
        _single("de_DE-thorsten-medium", "CC0-1.0"),
        Voice(
            "de_DE-thorsten_emotional-medium",
            "de/de_DE/thorsten_emotional/medium",
            "CC0-1.0",
            tuple(range(8)),
            share=0.5,
        ),
        _single("de_DE-kerstin-low", "CC0-1.0"),
    ),
    test_voices=(
        Voice("de_DE-mls-medium", _MLS_DE, "CC-BY-4.0", tuple(range(200, 236))),
        _single("de_DE-eva_k-x_low", "see-model-card"),
        _single("de_DE-karlsson-low", "see-model-card"),
        _single("de_DE-ramona-low", "see-model-card"),
    ),
    fleurs="de_de",
    mls="mls_german",
)

SPANISH = LanguageSpec(
    code="es",
    phrase="Oye LIA",
    positives=(
        "Oye Lía",
        "Oyelía",
        "Oye, Lía",
        "Oye [[ liʲˈa ]]",
        "Oye [[ lˈiʲa ]]",
    ),
    near_misses=(
        "Oye Lisa",
        "Oye Lea",
        "Oye Lili",
        "Oye Lila",
        "Oye Lina",
        "Oye Luna",
        "Oye Lola",
        "Oye Lucía",
        "Oye Lucas",
        "Oye Luis",
        "Oye Julia",
        "Oye Mía",
        "Oye tía",
        "Oye Leo",
        "Oye Delia",
        "Oye Lidia",
        "Oye Lima",
        "Oye linda",
        "Oye Siri",
        "Oye Alexa",
        "Oye Google",
        "Oye tú",
        "Oye, mira",
        "Oye, escucha",
        "Oye, ¿qué pasa?",
        "Oye, ¿y tú?",
        "Oye, la cena",
        "Oiga",
        "Hola Lía",
        "Gracias Lía",
        "Lía",
        "Oye, Lisa, ven aquí",
        "Hoy llegan",
        "Oye, lleva esto",
        "Lía, detente",
        "Lía detente",
    ),
    leads=(
        "Bueno,",
        "A ver,",
        "Eh,",
        "Mira,",
        "Vale,",
    ),
    carriers=(
        "¿qué tiempo va a hacer esta tarde en la ciudad?",
        "recuérdame llamar a mi hermana mañana por la mañana.",
        "¿puedes leerme los últimos mensajes que recibí hoy?",
        "¿a qué hora es mi primera reunión del lunes?",
    ),
    phrase_seconds=0.68,
    spoken=(
        "¡Oye Lía!",
        "¡Oyelía!",
        "Oye Lía.",
        "¿Oye Lía?",
        "Oyelía.",
        "Oye, Lía.",
    ),
    accents=(
        "Castilian",
        "Mexican",
        "Argentinian",
        "Colombian",
        "Chilean",
        "Andalusian",
        "Caribbean",
    ),
    train_voices=(
        _single("es_ES-davefx-medium", "CC0-1.0"),
        _single("es_ES-mls_10246-low", "CC-BY-4.0"),
        _single("es_ES-mls_9972-low", "CC-BY-4.0"),
        _single("es_ES-carlfm-x_low", "Public-Domain"),
        _single("es_MX-ald-medium", "Unlicense"),
        _single("es_MX-claude-high", "Apache-2.0"),
        Voice("es_ES-sharvard-medium", "es/es_ES/sharvard/medium", "CC-BY-3.0", (0,)),
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(0, 100)), "es", 0.5),
        Voice("de_DE-mls-medium", _MLS_DE, "CC-BY-4.0", tuple(range(0, 200)), "es", 0.5),
    ),
    test_voices=(
        Voice("es_ES-sharvard-medium", "es/es_ES/sharvard/medium", "CC-BY-3.0", (1,)),
        _single("es_AR-daniela-high", "CC-BY-SA-4.0"),
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(100, 125)), "es"),
    ),
    fleurs="es_419",
    mls="mls_spanish",
)

ITALIAN = LanguageSpec(
    code="it",
    phrase="Ehi LIA",
    positives=(
        "Ehi Lia",
        "Ehilia",
        "Ehi, Lia",
        "Ehi [[ lˈiʲa ]]",
        "Ehi [[ lˈiːa ]]",
    ),
    near_misses=(
        "Ehi Lisa",
        "Ehi Lea",
        "Ehi Lina",
        "Ehi Lino",
        "Ehi Luna",
        "Ehi Lucia",
        "Ehi Livia",
        "Ehi Luca",
        "Ehi Laura",
        "Ehi Lilla",
        "Ehi Lilli",
        "Ehi Giulia",
        "Ehi Ilaria",
        "Ehi Dalia",
        "Ehi Elia",
        "Ehi Lidia",
        "Ehi Delia",
        "Ehi Mia",
        "Ehi zia",
        "Ehi Leo",
        "Ehi Siri",
        "Ehi Alexa",
        "Ehi Google",
        "Ehi tu",
        "Ehi, senti",
        "Ehi, guarda",
        "Ehi, aspetta",
        "Ehi, come va?",
        "Ciao Lia",
        "Grazie Lia",
        "Lia",
        "Ehi, Lisa, vieni qui",
        "E lì",
        "Ehi là",
        "Lia, stop",
        "Lia stop",
    ),
    leads=(
        "Allora,",
        "Senti,",
        "Ehm,",
        "Dai,",
        "Bene,",
    ),
    carriers=(
        "che tempo farà questo pomeriggio in città?",
        "ricordami di chiamare mia sorella domani mattina prima di uscire.",
        "puoi leggermi gli ultimi messaggi che ho ricevuto oggi?",
        "a che ora è il mio primo appuntamento di lunedì?",
    ),
    phrase_seconds=0.68,
    spoken=(
        "Ehi Lia!",
        "Ehilia!",
        "Ehi Lia.",
        "Ehi Lia?",
        "Ehilia.",
        "Ehi, Lia.",
    ),
    accents=(
        "Standard Italian",
        "Roman",
        "Milanese",
        "Neapolitan",
        "Sicilian",
        "Tuscan",
        "Venetian",
    ),
    train_voices=(
        _single("it_IT-serena-medium", "CC-BY-4.0"),
        _single("es_ES-davefx-medium", "CC0-1.0", reads_as="it"),
        _single("es_ES-mls_10246-low", "CC-BY-4.0", reads_as="it"),
        _single("es_ES-mls_9972-low", "CC-BY-4.0", reads_as="it"),
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(0, 100)), "it"),
        Voice("de_DE-mls-medium", _MLS_DE, "CC-BY-4.0", tuple(range(0, 200)), "it", 0.5),
    ),
    test_voices=(
        _single("it_IT-paola-medium", "see-model-card"),
        _single("it_IT-riccardo-x_low", "see-model-card"),
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(100, 125)), "it"),
    ),
    fleurs="it_it",
    mls="mls_italian",
)

CHINESE = LanguageSpec(
    code="zh",
    phrase="嗨 LIA",
    positives=(
        "嗨，莉娅",
        "嗨 莉娅",
        "嗨莉娅",
    ),
    near_misses=(
        "嗨",
        "莉娅",
        "嗨，莉莎",
        "嗨，莉莉",
        "嗨，丽丽",
        "嗨，丽娜",
        "嗨，琳达",
        "嗨，米娅",
        "嗨，小爱",
        "嗨，小雅",
        "嗨，小李",
        "嗨，老李",
        "嗨，朋友",
        "嗨，大家好",
        "嗨，你好",
        "你好",
        "你好呀",
        "喂，你好",
        "哈喽",
        "哎呀",
        "海里呀",
        "来了呀",
        "好的",
        "嗨，丽莎来了",
        "莉娅，停下",
        "莉娅停下",
    ),
    leads=(
        "那个，",
        "嗯，",
        "好，",
        "对了，",
    ),
    carriers=(
        "今天下午天气怎么样？",
        "提醒我明天早上给我姐姐打电话。",
        "帮我读一下今天收到的最新消息。",
        "我星期一的第一个会议是几点？",
    ),
    phrase_seconds=0.65,
    spoken=(
        "嗨莉娅！",
        "嗨莉娅。",
        "嗨 莉娅！",
        "嗨莉娅？",
        "嗨Lia！",
        "嗨，莉娅。",
    ),
    accents=(
        "Beijing",
        "Northern Mandarin",
        "Southern Mandarin",
        "Taiwanese Mandarin",
        "Sichuan",
        "Shanghai",
    ),
    train_voices=(
        _single("zh_CN-chaowen-medium", "CC0-1.0"),
        Voice("en_US-libritts_r-medium", _LIBRITTS, "CC-BY-4.0", tuple(range(0, 300)), "cmn"),
        Voice("fr_FR-mls-medium", _MLS_FR, "CC-BY-4.0", tuple(range(0, 100)), "cmn", 0.5),
        Voice("de_DE-mls-medium", _MLS_DE, "CC-BY-4.0", tuple(range(0, 200)), "cmn", 0.5),
    ),
    test_voices=(
        _single("zh_CN-huayan-medium", "unknown"),
        _single("zh_CN-xiao_ya-medium", "non-commercial"),
        Voice("en_US-libritts_r-medium", _LIBRITTS, "CC-BY-4.0", tuple(range(700, 760)), "cmn"),
    ),
    fleurs="cmn_hans_cn",
    mls=None,
)

LANGUAGES: dict[str, LanguageSpec] = {
    spec.code: spec for spec in (FRENCH, ENGLISH, GERMAN, SPANISH, ITALIAN, CHINESE)
}


def _stop(
    base: LanguageSpec,
    *,
    phrase: str,
    positives: tuple[str, ...],
    near_misses: tuple[str, ...],
    leads: tuple[str, ...],
    carriers: tuple[str, ...],
    phrase_seconds: float,
    spoken: tuple[str, ...],
) -> LanguageSpec:
    """A language's stop command: its own words, the language's voices and corpora.

    LIA's name, then the word, with or without a pause between, or the word
    doubled — how a person cuts someone off. Its leads and continuations are
    what one says around it (« ok, LIA, stop, I got it »), and its near misses
    the words that sound like it: the word alone, another name, another word.
    """
    return replace(
        base,
        keyword="stop",
        phrase=phrase,
        positives=positives,
        near_misses=near_misses,
        leads=leads,
        carriers=carriers,
        phrase_seconds=phrase_seconds,
        spoken=spoken,
    )


STOP_WORDS: dict[str, LanguageSpec] = {
    "fr": _stop(
        FRENCH,
        phrase="LIA, stop",
        positives=("Lia, stop", "Lia stop", "[[ liˈa ]], stop", "Lia, stop stop"),
        near_misses=(
            "Stop",
            "Stop stop",
            "Bon, stop",
            "Allez, stop",
            "Lia",
            "Dis Lia",
            "Léa, stop",
            "Lila, stop",
            "Lisa, stop",
            "Julia, stop",
            "Mia, stop",
            "Lia, top",
            "Lia, stock",
            "Lia, start",
            "Lia, sport",
            "Lia, store",
            "Lia, tu es là ?",
            "Lia, s'il te plaît",
            "Lia, reprends",
            "Délia",
            "Lydia",
        ),
        leads=("Bon,", "Non,", "Oh,", "Ok,", "Attends,"),
        carriers=(
            "j'ai compris, merci.",
            "ça suffit pour l'instant.",
            "c'est bon, je lirai la suite.",
            "on en reparlera plus tard.",
        ),
        phrase_seconds=0.75,
        spoken=("Lia, stop !", "Lia, stop.", "Lia stop !", "Lia stop.", "Lia, stop stop !"),
    ),
    "en": _stop(
        ENGLISH,
        phrase="LIA, stop",
        positives=("Lia, stop", "Lia stop", "[[ lˈiːə ]], stop", "Lia, stop stop"),
        near_misses=(
            "Stop",
            "Stop stop",
            "Okay, stop",
            "No, stop",
            "Lia",
            "Hey Lia",
            "Leah, stop",
            "Lisa, stop",
            "Julia, stop",
            "Mia, stop",
            "Lia, top",
            "Lia, stock",
            "Lia, start",
            "Lia, shop",
            "Lia, step",
            "Lia, store",
            "Lia, are you there?",
            "Lia, please",
            "Delia",
            "Lydia",
        ),
        leads=("Okay,", "No,", "Oh,", "Wait,", "Right,"),
        carriers=(
            "I got it, thanks.",
            "that's enough for now.",
            "I'll read the rest myself.",
            "we can talk about it later.",
        ),
        phrase_seconds=0.7,
        spoken=("Lia, stop!", "Lia, stop.", "Lia stop!", "Lia stop.", "Lia, stop stop!"),
    ),
    "de": _stop(
        GERMAN,
        phrase="LIA, stopp",
        positives=("Lia, stopp", "Lia stopp", "[[ lˈiːa ]], stopp", "Lia, stopp stopp"),
        near_misses=(
            "Stopp",
            "Stopp stopp",
            "Okay, stopp",
            "Nein, stopp",
            "Lia",
            "Hey Lia",
            "Lea, stopp",
            "Lisa, stopp",
            "Julia, stopp",
            "Mia, stopp",
            "Lia, Topf",
            "Lia, Stoff",
            "Lia, Stock",
            "Lia, Start",
            "Lia, Sport",
            "Lia, bist du da?",
            "Lia, bitte",
            "Delia",
            "Lydia",
        ),
        leads=("Okay,", "Nein,", "Oh,", "Warte,", "Gut,"),
        carriers=(
            "ich hab's verstanden, danke.",
            "das reicht fürs Erste.",
            "den Rest lese ich selbst.",
            "darüber reden wir später.",
        ),
        phrase_seconds=0.75,
        spoken=("Lia, stopp!", "Lia, stopp.", "Lia stopp!", "Lia stopp.", "Lia, stopp stopp!"),
    ),
    "es": _stop(
        SPANISH,
        # Not « para »: the preposition (« for ») is in almost every sentence. Not
        # « basta » either: « bastante » begins with it. « Detente » is what
        # Spanish speakers already tell a voice assistant (owner delegation).
        phrase="LIA, detente",
        positives=("Lía, detente", "Lía detente", "[[ liʲˈa ]], detente", "Lía, detente, detente"),
        near_misses=(
            "Detente",
            "Vale, detente",
            "No, detente",
            "Lía",
            "Oye Lía",
            "Lea, detente",
            "Lisa, detente",
            "Julia, detente",
            "Mía, detente",
            "Lía, detener",
            "Lía, de repente",
            "Lía, depende",
            "Lía, detalle",
            "Lía, deporte",
            "Lía, ¿estás ahí?",
            "Lía, por favor",
            "Delia",
            "Lidia",
        ),
        leads=("Vale,", "No,", "Espera,", "Bueno,", "Oh,"),
        carriers=(
            "ya lo entendí, gracias.",
            "es suficiente por ahora.",
            "el resto lo leo yo.",
            "hablamos luego.",
        ),
        phrase_seconds=0.9,
        spoken=(
            "¡Lía, detente!",
            "Lía, detente.",
            "¡Lía detente!",
            "Lía detente.",
            "¡Lía, detente, detente!",
        ),
    ),
    "it": _stop(
        ITALIAN,
        phrase="LIA, stop",
        positives=("Lia, stop", "Lia stop", "[[ lˈiʲa ]], stop", "Lia, stop stop"),
        near_misses=(
            "Stop",
            "Stop stop",
            "Ok, stop",
            "No, stop",
            "Lia",
            "Ehi Lia",
            "Lea, stop",
            "Lisa, stop",
            "Giulia, stop",
            "Mia, stop",
            "Lia, top",
            "Lia, stock",
            "Lia, sto",
            "Lia, sport",
            "Lia, ci sei?",
            "Lia, per favore",
            "Delia",
            "Lidia",
        ),
        leads=("Ok,", "No,", "Aspetta,", "Bene,", "Oh,"),
        carriers=(
            "ho capito, grazie.",
            "per ora va bene così.",
            "il resto lo leggo io.",
            "ne parliamo dopo.",
        ),
        phrase_seconds=0.75,
        spoken=("Lia, stop!", "Lia, stop.", "Lia stop!", "Lia stop.", "Lia, stop stop!"),
    ),
    "zh": _stop(
        CHINESE,
        phrase="LIA，停下",
        positives=("莉娅，停下", "莉娅停下", "莉娅，停下来"),
        near_misses=(
            "停下",
            "停下来",
            "好的，停下",
            "不，停下",
            "莉娅",
            "嗨莉娅",
            "丽娜，停下",
            "莉莉，停下",
            "米娅，停下",
            "莉娅，停车",
            "莉娅，停电",
            "莉娅，等一下",
            "莉娅，听一下",
            "莉娅，天下",
            "莉娅，你在吗？",
            "莉娅，请",
        ),
        leads=("好，", "不，", "等等，", "嗯，"),
        carriers=("我明白了，谢谢。", "先这样吧。", "剩下的我自己看。", "我们晚点再说。"),
        phrase_seconds=0.8,
        spoken=("莉娅，停下！", "莉娅，停下。", "莉娅停下！", "莉娅，停下来！", "莉娅停下来。"),
    ),
}


def spec_of(code: str, keyword: Keyword = "wake") -> LanguageSpec:
    """The language's spec (its phrase, or its command), or a clear refusal naming the known ones."""
    table = LANGUAGES if keyword == "wake" else STOP_WORDS
    try:
        return table[code]
    except KeyError:
        known = ", ".join(sorted(table))
        raise SystemExit(f"unknown language {code!r}; known: {known}") from None
