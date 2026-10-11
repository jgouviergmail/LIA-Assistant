"""Health erasure confirms complete counts, source scope and independent retained records."""

from src.core.i18n_types import Language

HEALTH_REMOVAL_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Mesures santé à supprimer",
        "Supprimer définitivement toutes les mesures du type affiché, ou de tous les types si le type est nul, avec les comptes complets affichés. Aucune valeur médicale n’est transmise pour cette confirmation. Une modification ou une nouvelle mesure invalide cet accord. Les graphiques et comparaisons se recalculent depuis les mesures restantes. Les jetons d’ingestion restent actifs et peuvent envoyer de nouvelles mesures ; les mémoires et journaux déjà appris sont des données séparées. Aucun appel de modèle. Droits retirés ou accord expiré : refuser. Résultat incertain : vérifier avant toute nouvelle demande, sans rejeu automatique.",
    ),
    "en": (
        "Health samples to erase",
        "Permanently erase every sample of the displayed kind, or every kind when null, using the complete displayed counts. No medical value enters this confirmation. Changed or new samples invalidate approval. Charts and comparisons read remaining measurements. Ingestion tokens remain active and may send new samples; previously learned memories and journals are separate records. No model call. Withdrawn rights or expired consent refuse execution. Verify uncertain completion before a new request; never automatically replay.",
    ),
    "de": (
        "Zu löschende Gesundheitsmessungen",
        "Alle Messungen des angezeigten Typs oder bei null aller Typen endgültig löschen; die angezeigten Anzahlen sind vollständig. Keine Messwerte werden zur Bestätigung übermittelt. Geänderte oder neue Messungen machen die Zustimmung ungültig. Diagramme und Vergleiche verwenden verbleibende Daten. Eingabe-Token bleiben aktiv; bereits gelernte Erinnerungen und Journale sind getrennte Daten. Kein Modellaufruf. Entzogene Rechte oder abgelaufene Zustimmung verweigern die Ausführung. Unsicheren Abschluss vor einer neuen Anfrage prüfen; nie automatisch wiederholen.",
    ),
    "es": (
        "Medidas de salud que eliminar",
        "Eliminar permanentemente todas las medidas del tipo indicado o todos los tipos si es nulo, con los recuentos completos. No se envían valores médicos para confirmar. Medidas nuevas o modificadas invalidan la aprobación. Gráficos y comparaciones usan los datos restantes. Los tokens siguen activos y pueden enviar nuevas medidas; memorias y diarios aprendidos son registros separados. Sin llamada al modelo. Permisos retirados o aprobación caducada impiden ejecutar. Verificar un resultado incierto antes de otra solicitud; no repetir automáticamente.",
    ),
    "it": (
        "Misure salute da eliminare",
        "Eliminare definitivamente tutte le misure del tipo mostrato o tutti i tipi se nullo, con i conteggi completi. Nessun valore medico viene inviato per confermare. Misure nuove o modificate invalidano il consenso. Grafici e confronti usano i dati rimanenti. I token restano attivi e possono inviare nuove misure; memorie e diari appresi sono dati separati. Nessuna chiamata al modello. Permessi revocati o consenso scaduto impediscono l’esecuzione. Verificare un risultato incerto prima di una nuova richiesta; mai ripetere automaticamente.",
    ),
    "zh-CN": (
        "待删除健康测量",
        "按显示的完整数量永久删除所选类型的全部测量，类型为null时删除所有类型。确认不包含医疗测量值。新增或修改的测量会使批准失效。图表和比较使用剩余数据。接收令牌仍可发送新测量；已经学习的记忆和日记是独立记录。不调用模型。权限撤销或批准过期时拒绝执行。结果不确定时先核实，再提出新请求，不得自动重放。",
    ),
}
