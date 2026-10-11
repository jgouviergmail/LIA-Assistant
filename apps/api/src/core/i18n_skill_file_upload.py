"""Local skill file consent separates initial approval from browser file confirmation."""

from src.core.i18n_types import Language

SKILL_FILE_UPLOAD_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Fichier de compétence à importer",
        "Après cet accord, choisissez et confirmez le fichier SKILL.md ou ZIP dans ce navigateur. Sans cible indiquée, seule une nouvelle compétence peut être créée. Le remplacement porte uniquement sur la compétence affichée et peut remplacer ses ressources ; tout changement exige une nouvelle validation. Les scripts ne sont pas exécutés par l’import.",
    ),
    "en": (
        "Skill file to import",
        "After this approval, choose and confirm the SKILL.md or ZIP in this browser. Without a named target, only a new skill can be created. Replacement affects only the displayed skill and can replace its resources; changes require fresh approval. Importing does not execute scripts.",
    ),
    "de": (
        "Skill-Datei importieren",
        "Nach dieser Freigabe SKILL.md oder ZIP in diesem Browser auswählen und bestätigen. Ohne Ziel wird nur ein neuer Skill erstellt. Ersetzt wird nur der angezeigte Skill samt Ressourcen; Änderungen erfordern neue Freigabe. Der Import führt keine Skripte aus.",
    ),
    "es": (
        "Archivo de competencia para importar",
        "Tras aprobar, elija y confirme SKILL.md o ZIP en este navegador. Sin destino indicado solo se crea una competencia nueva. El reemplazo afecta únicamente a la competencia mostrada y sus recursos; cambios requieren nueva aprobación. El import no ejecuta scripts.",
    ),
    "it": (
        "File di competenza da importare",
        "Dopo l'approvazione, scegli e conferma SKILL.md o ZIP in questo browser. Senza destinazione si crea solo una nuova competenza. Si sostituisce solo la competenza mostrata e le sue risorse; modifiche richiedono nuova approvazione. L'importazione non esegue script.",
    ),
    "zh-CN": (
        "要导入的技能文件",
        "批准后在此浏览器选择并确认 SKILL.md 或 ZIP。未指定目标时只能创建新技能。替换仅影响显示的技能及其资源；变更需要重新批准。导入不会执行脚本。",
    ),
}
