"""The writing-style cards the assistant prepares, in the six languages (ADR-383).

A learning card says what is read and what it costs, a forgetting card what is removed
and what is not; both say nothing happens before the person confirms.
"""

from typing import NamedTuple

from src.core.i18n_types import Language


class WritingStyleActionCopy(NamedTuple):
    """The words of the two writing-style cards."""

    learn_note: str
    forget_note: str
    mails_to_read: str
    nothing_learned: str
    replaces: str
    learned_on: str
    mails_read: str


WRITING_STYLE_ACTION_COPY: dict[Language, WritingStyleActionCopy] = {
    "fr": WritingStyleActionCopy(
        learn_note=(
            "Après ta confirmation, LIA lit tes derniers mails envoyés et apprend ta façon "
            "d’écrire : ta voix, jamais tes faits. Un appel au modèle compte dans ton usage. "
            "Tes mails ne sont pas modifiés."
        ),
        forget_note=(
            "LIA efface ce qu’elle a appris de ta façon d’écrire. Tes mails et ton interrupteur "
            "restent inchangés ; rien n’est réappris tant que tu ne le demandes pas."
        ),
        mails_to_read="Mails envoyés à lire",
        nothing_learned="Rien n’a encore été appris.",
        replaces="Remplace ce qui a été appris :",
        learned_on="Appris le",
        mails_read="Mails envoyés lus",
    ),
    "en": WritingStyleActionCopy(
        learn_note=(
            "After your confirmation, LIA reads your latest sent e-mails and learns how you "
            "write: your voice, never your facts. One model call counts toward your usage. "
            "Your e-mails are not changed."
        ),
        forget_note=(
            "LIA deletes what it learned of how you write. Your e-mails and your switch are "
            "not changed; nothing is learned again until you ask."
        ),
        mails_to_read="Sent e-mails to read",
        nothing_learned="Nothing has been learned yet.",
        replaces="Replaces what was learned:",
        learned_on="Learned on",
        mails_read="Sent e-mails read",
    ),
    "de": WritingStyleActionCopy(
        learn_note=(
            "Nach deiner Bestätigung liest LIA deine zuletzt gesendeten E-Mails und lernt, wie "
            "du schreibst: deine Stimme, nie deine Fakten. Ein Modellaufruf zählt zu deiner "
            "Nutzung. Deine E-Mails werden nicht verändert."
        ),
        forget_note=(
            "LIA löscht, was sie über deinen Schreibstil gelernt hat. Deine E-Mails und dein "
            "Schalter bleiben unverändert; nichts wird neu gelernt, bis du darum bittest."
        ),
        mails_to_read="Zu lesende gesendete E-Mails",
        nothing_learned="Bisher wurde nichts gelernt.",
        replaces="Ersetzt, was gelernt wurde:",
        learned_on="Gelernt am",
        mails_read="Gelesene gesendete E-Mails",
    ),
    "es": WritingStyleActionCopy(
        learn_note=(
            "Tras tu confirmación, LIA lee tus últimos correos enviados y aprende cómo "
            "escribes: tu voz, nunca tus datos. Una llamada al modelo cuenta en tu uso. Tus "
            "correos no se modifican."
        ),
        forget_note=(
            "LIA borra lo que aprendió de cómo escribes. Tus correos y tu interruptor no "
            "cambian; no se vuelve a aprender nada hasta que lo pidas."
        ),
        mails_to_read="Correos enviados que se leerán",
        nothing_learned="Todavía no se ha aprendido nada.",
        replaces="Sustituye lo aprendido:",
        learned_on="Aprendido el",
        mails_read="Correos enviados leídos",
    ),
    "it": WritingStyleActionCopy(
        learn_note=(
            "Dopo la tua conferma, LIA legge le tue ultime e-mail inviate e impara come "
            "scrivi: la tua voce, mai i tuoi fatti. Una chiamata al modello conta nel tuo "
            "utilizzo. Le tue e-mail non vengono modificate."
        ),
        forget_note=(
            "LIA cancella ciò che ha imparato del tuo modo di scrivere. Le tue e-mail e il tuo "
            "interruttore restano invariati; niente viene reimparato finché non lo chiedi."
        ),
        mails_to_read="E-mail inviate da leggere",
        nothing_learned="Non è ancora stato imparato niente.",
        replaces="Sostituisce ciò che è stato imparato:",
        learned_on="Imparato il",
        mails_read="E-mail inviate lette",
    ),
    "zh-CN": WritingStyleActionCopy(
        learn_note=(
            "在你确认后，LIA 会读取你最近发送的邮件并学习你的写法：学的是你的语气，"
            "绝不是你的内容。一次模型调用会计入你的用量。你的邮件不会被修改。"
        ),
        forget_note=(
            "LIA 会删除已学到的你的写法。你的邮件和开关保持不变；在你提出之前，不会重新学习。"
        ),
        mails_to_read="要读取的已发送邮件",
        nothing_learned="尚未学习任何内容。",
        replaces="将替换已学到的内容：",
        learned_on="学习时间",
        mails_read="已读取的已发送邮件",
    ),
}
