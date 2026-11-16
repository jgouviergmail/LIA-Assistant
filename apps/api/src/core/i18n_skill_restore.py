"""A skill's previous version coming back: what the confirmation card says, in six languages."""

from src.core.i18n_types import Language

SKILL_RESTORE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Compétence dont la version précédente revient",
        "Remet en place la version que le dernier remplacement de cette compétence a mise de côté. La version actuelle devient à son tour la version précédente : la restauration peut elle-même être annulée de la même façon. Une compétence changée entre-temps demande une nouvelle proposition.",
    ),
    "en": (
        "Skill whose previous version comes back",
        "Puts back the version this skill's last replacement put aside. The current version becomes the previous one in turn, so the restoration can itself be undone the same way. A skill changed meanwhile needs a new proposal.",
    ),
    "de": (
        "Skill, dessen vorherige Version zurückkommt",
        "Stellt die Version wieder her, die der letzte Ersatz dieses Skills beiseitegelegt hat. Die aktuelle Version wird ihrerseits zur vorherigen: Die Wiederherstellung lässt sich ebenso rückgängig machen. Ein inzwischen geänderter Skill braucht einen neuen Vorschlag.",
    ),
    "es": (
        "Competencia cuya versión anterior vuelve",
        "Vuelve a poner la versión que el último reemplazo de esta competencia dejó aparte. La versión actual pasa a ser la anterior: la restauración también puede deshacerse de la misma manera. Una competencia cambiada mientras tanto requiere una nueva propuesta.",
    ),
    "it": (
        "Competenza la cui versione precedente ritorna",
        "Rimette la versione che l'ultima sostituzione di questa competenza ha messo da parte. La versione attuale diventa a sua volta la precedente: anche il ripristino si può annullare allo stesso modo. Una competenza cambiata nel frattempo richiede una nuova proposta.",
    ),
    "zh-CN": (
        "恢复上一版本的技能",
        "恢复此技能上一次被替换时搁置的版本。当前版本随之成为上一版本，因此恢复本身也可以用同样的方式撤销。期间已被更改的技能需要重新提议。",
    ),
}
