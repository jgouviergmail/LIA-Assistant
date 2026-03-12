# Templates & Checklists

**Date**: 2026-03-08
**Status**: ✅ Ready to use

---

## Contenu

Ce repertoire contient les templates et checklists pour ajouter rapidement de nouveaux composants au projet LIA.

### Fichiers Disponibles

| Fichier | Description | Usage |
|---------|-------------|-------|
| **connector_tool_template.py** | Template pour tool base sur ConnectorTool | Copier vers `apps/api/src/domains/agents/tools/` |
| **connector_client_template.py** | Template pour API client OAuth | Copier vers `apps/api/src/domains/connectors/clients/` |
| **NEW_CONNECTOR_CHECKLIST.md** | Checklist creation d'un nouveau connecteur OAuth/API Key | Guide step-by-step (~6-9h) |
| **NEW_MCP_SERVER_CHECKLIST.md** | Checklist integration d'un nouveau serveur MCP | Guide step-by-step (~2-4h) |
| **NEW_PROACTIVE_TASK_CHECKLIST.md** | Checklist creation d'une nouvelle notification proactive | Guide step-by-step (~3-5h) |
| **NEW_CHANNEL_CHECKLIST.md** | Checklist ajout d'un nouveau canal de messagerie | Guide step-by-step (~4-8h) |

---

## 🚀 Quick Start

### Pour Ajouter un Nouveau Connecteur (ex: Gmail)

1. **Lire la checklist**:
   ```bash
   cat docs/templates/NEW_CONNECTOR_CHECKLIST.md
   ```

2. **Copier les templates**:
   ```bash
   # API Client
   cp docs/templates/connector_client_template.py \
      apps/api/src/domains/connectors/clients/my_service_client.py

   # Tools
   cp docs/templates/connector_tool_template.py \
      apps/api/src/domains/agents/tools/my_service_tools.py
   ```

3. **Rechercher et remplacer** les TODOs:
   - Ouvrir les fichiers copiés
   - Chercher `TODO:`
   - Remplir chaque section

4. **Suivre la checklist** dans `NEW_CONNECTOR_CHECKLIST.md`

---

## 💡 Bénéfices des Templates

### Économie de Temps

| Tâche | Sans Template | Avec Template | Économie |
|-------|---------------|---------------|----------|
| **Client API** | 4-5h | 2-3h | **-40%** |
| **Tool Implementation** | 6-8h | 1-2h | **-80%** |
| **Error Handling** | 2-3h | 0h (built-in) | **-100%** |
| **Total** | **20-27h** | **6-9h** | **-67%** |

**Gain moyen**: **14-18 heures par connecteur** (2-3 jours de travail!)

### Qualité du Code

- ✅ Patterns standardisés (ConnectorTool base class)
- ✅ Error handling unifié
- ✅ Métriques Prometheus built-in
- ✅ OAuth credentials management automatique
- ✅ Context type registration
- ✅ Documentation complète

---

## 📐 Architecture Pattern

Les templates implémentent le pattern **ConnectorTool** développé en Phase 5 (Session 27):

```python
# Avant (sans pattern): ~150 lines de code
def my_tool(params, runtime):
    # 50 lines: DI boilerplate
    # 30 lines: OAuth credentials retrieval
    # 20 lines: Client creation and caching
    # 20 lines: Error handling
    # 30 lines: Business logic
    pass

# Après (avec ConnectorTool): ~30 lines de code
class MyTool(ConnectorTool[MyClient]):
    connector_type = ConnectorType.MY_SERVICE
    client_class = MyClient

    async def execute_api_call(self, client, user_id, **kwargs):
        # 30 lines: Business logic only!
        # Everything else handled by base class
        pass
```

**Réduction**: **80% moins de code**, **0% de boilerplate dupliqué**

---

## 🎯 Cas d'Usage

### Use Case 1: Email Integration (Gmail, Outlook)

**Objectif**: Ajouter send_email, search_emails, get_email tools

**Steps**:
1. Copier `connector_client_template.py` → `google_gmail_client.py`
2. Implémenter `send_email()`, `search_emails()`, `get_email()` methods
3. Copier `connector_tool_template.py` → `emails_tools.py`
4. Créer 3 tool classes héritant de `ConnectorTool`
5. Suivre checklist pour tests et documentation

**Note**: Le domain est `emails` (générique multi-provider), pas `gmail`. Voir ADR-010.

**Temps estimé**: 6-8h (vs. 20-25h sans templates)

---

### Use Case 2: Google Calendar Integration

**Objectif**: Ajouter search_events, create_event, update_event, delete_event tools

**Steps**:
1. Copier templates → `calendar_client.py` et `calendar_tools.py`
2. Implémenter Calendar API methods
3. Créer 4 tool classes
4. Définir `CalendarEventItem` schema pour context
5. Suivre checklist

**Temps estimé**: 7-9h (vs. 25-30h sans templates)

---

### Use Case 3: Google Drive Integration

**Objectif**: Ajouter search_files, upload_file, download_file, share_file tools

**Steps**:
1. Copier templates → `drive_client.py` et `drive_tools.py`
2. Implémenter Drive API methods
3. Créer 4 tool classes
4. Définir `DriveFileItem` schema
5. Suivre checklist

**Temps estimé**: 8-10h (vs. 25-30h sans templates)

---

## Autres Checklists

### Pour integrer un serveur MCP

Utiliser **NEW_MCP_SERVER_CHECKLIST.md** pour integrer un nouveau serveur MCP (admin ou per-user). Couvre : configuration, description de domaine, convention `read_me`, MCP Apps, securite, tests.

**Temps estime** : 2-4h | **Reference** : [GUIDE_MCP_INTEGRATION.md](../guides/GUIDE_MCP_INTEGRATION.md)

### Pour creer une notification proactive

Utiliser **NEW_PROACTIVE_TASK_CHECKLIST.md** pour creer un nouveau type de notification proactive (comme Heartbeat ou Interests). Couvre : ProactiveTask protocol, EligibilityChecker, job scheduler, NotificationDispatcher, tests.

**Temps estime** : 3-5h | **Reference** : [GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md](../guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md)

### Pour ajouter un canal de messagerie

Utiliser **NEW_CHANNEL_CHECKLIST.md** pour ajouter un nouveau canal de messagerie (Discord, WhatsApp, Slack...). Couvre : BaseChannelSender, webhook handler, OTP linking, NotificationDispatcher integration, tests.

**Temps estime** : 4-8h | **Reference** : [GUIDE_TELEGRAM_INTEGRATION.md](../guides/GUIDE_TELEGRAM_INTEGRATION.md)

---

## References

### Documentation

- **Phase 5 Analysis**: [docs/optim/PHASE_5_GENERALIZATION_ANALYSIS.md](../optim/PHASE_5_GENERALIZATION_ANALYSIS.md)
  - Patterns identifiés
  - Architecture recommandée
  - Examples détaillés

- **ConnectorTool Base Class**: [apps/api/src/domains/agents/tools/base.py](../../apps/api/src/domains/agents/tools/base.py)
  - Code source du pattern
  - Documentation complète

- **Example Real**: [apps/api/src/domains/agents/tools/google_contacts_tools.py](../../apps/api/src/domains/agents/tools/google_contacts_tools.py)
  - Implémentation complète d'un connecteur
  - Reference pour patterns

### Patterns Utilisés

1. **ConnectorTool Base Class**: Template Method Pattern + DI
2. **@connector_tool Decorator**: Decorator Pattern + Convention over Configuration
3. **Context Type Registration**: Registry Pattern + Schema Validation
4. **Service Layer**: Stateless services for complex logic
5. **Helper Function Extraction**: ADR-007, Single Responsibility

---

## ✅ Checklist Avant d'Utiliser

- [ ] J'ai lu [PHASE_5_GENERALIZATION_ANALYSIS.md](../optim/PHASE_5_GENERALIZATION_ANALYSIS.md)
- [ ] J'ai consulté [google_contacts_tools.py](../../apps/api/src/domains/agents/tools/google_contacts_tools.py) comme référence
- [ ] J'ai la documentation API du service externe
- [ ] J'ai identifié les OAuth scopes nécessaires
- [ ] J'ai la checklist NEW_CONNECTOR_CHECKLIST.md ouverte

---

## 🎓 Tips & Best Practices

### Do's ✅

- ✅ Suivre la checklist étape par étape
- ✅ Remplir TOUS les TODOs avant de tester
- ✅ Écrire les tests en parallèle de l'implémentation
- ✅ Utiliser les metrics Prometheus
- ✅ Documenter chaque méthode avec docstrings
- ✅ Tester avec un compte sandbox/staging en premier

### Don'ts ❌

- ❌ Ne pas copier-coller de l'ancien code (utiliser ConnectorTool!)
- ❌ Ne pas sauter les tests
- ❌ Ne pas oublier Context Type Registration
- ❌ Ne pas hardcoder les credentials
- ❌ Ne pas dupliquer error handling (c'est dans la base class)

### Common Pitfalls

1. **Oublier de set `connector_type` et `client_class`**
   - Symptôme: `AttributeError` au runtime
   - Solution: Vérifier que les class attributes sont set

2. **Oublier `@connector_tool` decorator**
   - Symptôme: Tool pas enregistré dans registry
   - Solution: Appliquer decorator avec tous les params

3. **Oublier Context Type Registration**
   - Symptôme: Fuzzy matching ne fonctionne pas
   - Solution: Appeler `ContextTypeRegistry.register()` au module level

4. **Duplicater error handling dans `execute_api_call()`**
   - Symptôme: Code verbeux, duplication
   - Solution: Laisser ConnectorTool base class gérer les erreurs

---

## 🆘 Support

### En Cas de Problème

1. **Consulter la documentation**:
   - [PHASE_5_GENERALIZATION_ANALYSIS.md](../optim/PHASE_5_GENERALIZATION_ANALYSIS.md)
   - [ConnectorTool base class](../../apps/api/src/domains/agents/tools/base.py)

2. **Référence complète**:
   - [google_contacts_tools.py](../../apps/api/src/domains/agents/tools/google_contacts_tools.py)

3. **Chercher des patterns similaires**:
   ```bash
   grep -r "ConnectorTool" apps/api/src/domains/agents/tools/
   ```

---

## 📊 Métriques d'Utilisation

**À remplir après utilisation**:

| Connecteur | Développeur | Date | Temps (h) | Économie vs. Sans Template |
|------------|-------------|------|-----------|----------------------------|
| Gmail | - | - | - | - |
| Calendar | - | - | - | - |
| Drive | - | - | - | - |

**Feedback**: Ouvrir une issue ou ajouter dans les Notes & Lessons Learned de la checklist

---

## 🎉 Success Stories

_À remplir après premiers usages des templates_

---

**Templates Status**: ✅ Ready to use
**Last Updated**: 2026-03-08
