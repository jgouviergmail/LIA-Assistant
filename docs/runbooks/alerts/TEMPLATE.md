# [Alert Name] - Runbook

**Severity**: [critical|warning|info]
**Component**: [api|database|agents|infrastructure|llm|auth|conversations|tokens|redis]
**Impact**: [Description concise de l'impact utilisateur/business]
**SLA Impact**: [Yes/No - Si oui, quel SLA est impacté]

---

## 📊 Alert Definition

**Alert Name**: `[AlertName]`

**Prometheus Expression**:
```promql
[Expression PromQL complète depuis alerts.yml.template]
```

**Threshold**:
- **Production**: [valeur] ([unité]) - [contexte]
- **Staging**: [valeur] ([unité])
- **Development**: [valeur] ([unité])

**Firing Duration**: `for: [duration]`

**Labels**:
- `severity`: [critical|warning|info]
- `component`: [component]
- [autres labels si pertinents]

---

## 🔍 Symptoms

### What Users See
- [Symptôme utilisateur visible 1 - ex: Pages lentes à charger]
- [Symptôme utilisateur visible 2 - ex: Erreurs 500 dans l'interface]
- [Symptôme utilisateur visible 3 - ex: Fonctionnalité X indisponible]

### What Ops See
- [Métrique anormale 1 - ex: Error rate > 5%]
- [Log pattern 1 - ex: "Connection refused" dans logs API]
- [Dashboard indicator 1 - ex: Panel "API Errors" rouge dans Grafana]

---

## 🎯 Possible Causes

### 1. [Catégorie Cause 1 - ex: Database Connection Pool Saturation]

**Likelihood**: [High|Medium|Low]

**Description**:
[Explication détaillée de cette cause - pourquoi ça arrive, dans quels contextes, etc.]

**How to Verify**:
```bash
# [Commande diagnostic 1]
[commande concrète]

# [Commande diagnostic 2]
[commande concrète]
```

**Expected Output if This is the Cause**:
```
[Exemple de sortie attendue qui confirme cette cause]
```

---

### 2. [Catégorie Cause 2]

**Likelihood**: [High|Medium|Low]

**Description**:
[Explication détaillée]

**How to Verify**:
```bash
[Commandes de vérification]
```

---

### 3. [Catégorie Cause 3]

[Répéter structure ci-dessus]

---

## 🔧 Diagnostic Steps

### Quick Health Check (< 2 minutes)

**Objectif**: Vérifier l'état général et identifier rapidement le composant défaillant.

```bash
# 1. Vérifier statut tous les containers
docker-compose ps

# 2. Vérifier logs récents du composant concerné
docker-compose logs --tail=100 [service_name] | grep -i error

# 3. Vérifier métriques Prometheus pour ce composant
curl -s "http://localhost:9090/api/v1/query?query=[métrique_clé]" | jq '.data.result'
```

**Interprétation**:
- Si [condition 1], alors → [conclusion 1]
- Si [condition 2], alors → [conclusion 2]

---

### Deep Dive Investigation (5-10 minutes)

**Objectif**: Identifier la cause racine exacte.

#### Step 1: [Vérifier Aspect Spécifique 1]
```bash
[Commandes détaillées]
```

**What to Look For**:
- [Indicateur 1]
- [Indicateur 2]

---

#### Step 2: [Vérifier Aspect Spécifique 2]
```bash
[Commandes détaillées]
```

---

#### Step 3: [Analyser Corrélations]
```bash
# Vérifier si d'autres alerts sont actives (peut indiquer cause commune)
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.status.state=="firing") | .labels.alertname'
```

---

### Automated Diagnostic Script

Pour gagner du temps, utilisez le script diagnostic automatisé:

```bash
infrastructure/observability/scripts/diagnose_[component].sh
```

---

## ✅ Resolution Steps

### Immediate Mitigation (Stop the Bleeding)

**Objectif**: Restaurer le service rapidement, même si ce n'est pas la solution définitive.

#### Option A: [Solution Rapide 1]
```bash
# [Commandes]
```

**Pros**: [Avantages]
**Cons**: [Inconvénients]
**Duration**: [Temps d'exécution]

---

#### Option B: [Solution Rapide 2]
```bash
# [Commandes]
```

**Pros**: [Avantages]
**Cons**: [Inconvénients]
**Duration**: [Temps d'exécution]

---

### Verification After Mitigation

```bash
# 1. Vérifier que l'alert ne fire plus
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="[AlertName]") | .status.state'

# 2. Vérifier métrique est revenue à la normale
curl -s "http://localhost:9090/api/v1/query?query=[métrique]" | jq '.data.result'

# 3. Vérifier logs ne montrent plus d'erreurs
docker-compose logs --tail=50 [service] | grep -i error
```

**Expected**: [Résultats attendus après mitigation]

---

### Root Cause Fix (Permanent Solution)

**Objectif**: Résoudre définitivement pour éviter récurrence.

#### 1. Investigation Approfondie
```bash
[Commandes d'investigation]
```

#### 2. Identification Root Cause
[Questions à se poser pour identifier vraie cause]

#### 3. Implementation du Fix
```bash
# [Étapes de correction]
```

#### 4. Testing
```bash
# [Commandes de test]
```

#### 5. Deployment
[Procédure de déploiement du fix]

#### 6. Monitoring Post-Fix
[Métriques à surveiller après le fix - durée recommandée]

---

## 📈 Related Dashboards & Queries

### Grafana Dashboards
- **[Dashboard Name 1]**: `http://localhost:3000/d/[dashboard-id]`
  - Panel: [nom panel pertinent]
  - Métrique: [métrique affichée]

### Prometheus Queries
```promql
# Query 1: [Description]
[query]

# Query 2: [Description]
[query]
```

### Logs Queries
```bash
# Logs API avec erreurs liées
docker-compose logs [service] --since=30m | grep -E "[pattern]"
```

---

## 📚 Related Runbooks

- **[Related Alert 1]**: [lien vers runbook] - [Relation]
- **[Related Alert 2]**: [lien vers runbook] - [Relation]

---

## 🔄 Common Patterns & Known Issues

### Pattern 1: [Nom du Pattern]
**Description**: [Quand ce pattern se produit]
**Resolution**: [Comment résoudre]
**Prevention**: [Comment éviter]

### Known Issue 1: [Description]
**Symptom**: [Symptôme spécifique]
**Workaround**: [Solution temporaire]
**Tracking**: [Lien GitHub issue si applicable]

---

## 🆘 Escalation

### When to Escalate

Escalader immédiatement si:
- [ ] Mitigation n'a pas fonctionné après 2 tentatives
- [ ] Impact utilisateurs > [seuil] utilisateurs affectés
- [ ] Durée > [seuil] minutes sans résolution
- [ ] Suspicion de faille sécurité
- [ ] Perte de données en cours
- [ ] [Autre critère spécifique à cet alert]

### Escalation Path

**Level 1 - Team Lead** (0-15min):
- **Contact**: [Nom/Rôle]
- **Slack**: #[channel]
- **Phone**: [si applicable]

**Level 2 - Senior Engineer / Architect** (15-30min):
- **Contact**: [Nom/Rôle]
- **Slack**: #[channel]
- **Phone**: [numéro on-call]

**Level 3 - CTO / Management** (30min+):
- **Contact**: [Nom/Rôle]
- **Email**: [email]
- **Phone**: [numéro]

### Escalation Template Message

```
🚨 ALERT ESCALATION 🚨

Alert: [AlertName]
Severity: [critical|warning]
Duration: [temps depuis firing]
Impact: [description impact]

Actions Taken:
- [Action 1]
- [Action 2]

Current Status: [status actuel]

Need: [ce dont vous avez besoin - assistance, décision, etc.]

Dashboard: http://localhost:3000/d/[id]
```

---

## 📝 Post-Incident Actions

### Immediate (< 1h après résolution)

- [ ] Créer incident report dans [système de tracking]
- [ ] Notifier stakeholders de la résolution
- [ ] Documenter timeline dans incident report
- [ ] Capturer logs/métriques pour analyse post-mortem

### Short-Term (< 24h après résolution)

- [ ] Mettre à jour ce runbook si gaps identifiés
- [ ] Créer GitHub issues pour fixes permanents si workaround utilisé
- [ ] Review alert threshold si false positive
- [ ] Ajouter monitoring si blind spot découvert

### Long-Term (< 1 semaine après résolution)

- [ ] Post-mortem meeting avec équipe
- [ ] Documentation des learnings
- [ ] Implementation des action items du post-mortem
- [ ] Update de la documentation architecture si nécessaire

---

## 📋 Incident Report Template

```markdown
# Incident Report - [AlertName] - [Date]

## Summary
[Résumé 2-3 lignes]

## Timeline
- **[HH:MM]** - Alert fired
- **[HH:MM]** - [Action prise]
- **[HH:MM]** - [Action prise]
- **[HH:MM]** - Resolved

## Impact
- **Users Affected**: [nombre/pourcentage]
- **Duration**: [durée]
- **Revenue Impact**: [si applicable]
- **SLA Impact**: [Yes/No]

## Root Cause
[Explication cause racine]

## Resolution
[Ce qui a été fait pour résoudre]

## Action Items
- [ ] [Action 1] - Owner: [nom] - Due: [date]
- [ ] [Action 2] - Owner: [nom] - Due: [date]

## Prevention
[Comment éviter récurrence]
```

---

## 🔗 Additional Resources

### Documentation
- [Lien vers architecture doc]
- [Lien vers API doc]
- [Lien vers deployment guide]

### Code References
- [Lien vers code source pertinent]
- [Lien vers config files]

### External Resources
- [Lien vers doc externe pertinente]
- [Lien vers best practices]

---

## 📅 Runbook Metadata

**Created**: [Date]
**Last Updated**: [Date]
**Maintainer**: [Équipe/Personne]
**Version**: [Numéro version]
**Related GitHub Issues**: [#123, #456]

**Changelog**:
- **[Date]**: [Changement apporté]
- **[Date]**: [Changement apporté]

---

## ✅ Runbook Validation Checklist

Avant de considérer ce runbook complet:

- [ ] Alert definition vérifiée contre alerts.yml.template
- [ ] Toutes les commandes testées et fonctionnelles
- [ ] Liens dashboards/queries validés
- [ ] Escalation path confirmé avec équipe
- [ ] Au moins 1 dry-run du runbook effectué
- [ ] Review par au moins 2 personnes de l'équipe
- [ ] Templates messages testés

---

**Note**: Ce runbook doit être mis à jour après chaque incident pour rester pertinent et utile.
