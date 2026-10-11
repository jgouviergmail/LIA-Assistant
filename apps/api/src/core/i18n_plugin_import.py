"""Personal package consent explains per-component outcomes in every supported language."""

PLUGIN_IMPORT_COPY = {
    "fr": (
        "Plugin à importer depuis une URL",
        "Cette confirmation importe le paquet indiqué et peut remplacer uniquement le plugin identifié. Les composants supprimés de la nouvelle version seront retirés. Les compétences et serveurs MCP sont traités séparément : les réussites, refus et résultats partiels sont signalés. Aucun script n’est exécuté. Une source ou un état modifié impose une nouvelle confirmation ; un commit incertain ne peut pas être rejoué automatiquement.",
    ),
    "en": (
        "Plugin to import from a URL",
        "This confirmation imports the listed package and may replace only the identified plugin. Components absent from the new version will be removed. Skills and MCP servers are processed separately: successful, skipped and partial outcomes are reported. No script runs. Changed source or state requires new confirmation; an uncertain commit cannot replay automatically.",
    ),
    "de": (
        "Über eine URL zu importierendes Plugin",
        "Diese Bestätigung importiert das angegebene Paket und ersetzt nur das bezeichnete Plugin. In der neuen Version fehlende Komponenten werden entfernt. Skills und MCP-Server werden einzeln verarbeitet; erfolgreiche, übersprungene und teilweise Ergebnisse werden gemeldet. Kein Skript wird ausgeführt. Änderungen an Quelle oder Zustand erfordern eine neue Bestätigung; ein ungewisser Commit wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Plugin que se importará desde una URL",
        "Esta confirmación importa el paquete indicado y solo puede sustituir el plugin identificado. Se retirarán los componentes ausentes de la nueva versión. Las competencias y los servidores MCP se procesan por separado; se informan los éxitos, omisiones y resultados parciales. No se ejecuta ningún script. Una fuente o estado modificado requiere nueva confirmación; un commit incierto no se repite automáticamente.",
    ),
    "it": (
        "Plugin da importare da un URL",
        "Questa conferma importa il pacchetto indicato e può sostituire solo il plugin identificato. I componenti assenti dalla nuova versione vengono rimossi. Competenze e server MCP sono elaborati separatamente; successi, esclusioni e risultati parziali vengono segnalati. Nessuno script viene eseguito. Una fonte o uno stato modificato richiede una nuova conferma; un commit incerto non viene ripetuto automaticamente.",
    ),
    "zh-CN": (
        "要从网址导入的插件",
        "此确认将导入所列的软件包，且只能替换指定插件。新版本中缺少的组件将被移除。技能和 MCP 服务器分别处理，并明确报告成功、跳过及部分完成的结果。不执行任何脚本。来源或状态发生变化时需要重新确认；提交结果不确定时不会自动重复执行。",
    ),
}

PLUGIN_FILE_IMPORT_COPY = {
    "fr": (
        "Plugin à importer depuis un fichier",
        "Après cette confirmation, choisissez et confirmez explicitement le ZIP dans ce navigateur. Le remplacement vise uniquement le plugin indiqué ; les composants absents de la nouvelle version seront retirés. Les résultats partiels et les nettoyages incomplets sont signalés. Aucun script n’est exécuté. Un état modifié impose une nouvelle confirmation et un commit incertain ne peut pas être rejoué automatiquement.",
    ),
    "en": (
        "Plugin to import from a file",
        "After this confirmation, choose and explicitly confirm the ZIP in this browser. Replacement targets only the listed plugin; components absent from the new version will be removed. Partial outcomes and incomplete cleanup are reported. No script runs. Changed state requires new confirmation; an uncertain commit cannot replay automatically.",
    ),
    "de": (
        "Plugin aus einer Datei importieren",
        "Wählen und bestätigen Sie nach dieser Bestätigung die ZIP-Datei ausdrücklich in diesem Browser. Nur das angegebene Plugin wird ersetzt; in der neuen Version fehlende Komponenten werden entfernt. Teilergebnisse und unvollständige Bereinigung werden gemeldet. Kein Skript wird ausgeführt. Ein geänderter Zustand erfordert eine neue Bestätigung; ein ungewisser Commit wird nicht automatisch wiederholt.",
    ),
    "es": (
        "Plugin que se importará desde un archivo",
        "Después de esta confirmación, elija y confirme explícitamente el ZIP en este navegador. Solo se sustituye el plugin indicado; se retiran los componentes ausentes de la nueva versión. Se informan los resultados parciales y la limpieza incompleta. No se ejecuta ningún script. Un estado modificado requiere nueva confirmación; un commit incierto no se repite automáticamente.",
    ),
    "it": (
        "Plugin da importare da un file",
        "Dopo questa conferma, scegli e conferma esplicitamente lo ZIP in questo browser. Viene sostituito solo il plugin indicato; i componenti assenti dalla nuova versione vengono rimossi. Risultati parziali e pulizia incompleta vengono segnalati. Nessuno script viene eseguito. Uno stato modificato richiede una nuova conferma; un commit incerto non viene ripetuto automaticamente.",
    ),
    "zh-CN": (
        "要从文件导入的插件",
        "确认后，请在此浏览器中选择并明确确认 ZIP 文件。只能替换所列的插件；新版本中缺少的组件将被移除。部分完成及未完成的清理会明确报告。不执行任何脚本。状态发生变化时需要重新确认；提交结果不确定时不会自动重复执行。",
    ),
}
