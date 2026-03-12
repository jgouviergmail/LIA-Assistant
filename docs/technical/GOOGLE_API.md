# Google APIs - Documentation & Tarification

> **Version** : 1.1 | **Date** : 2026-02-04
>
> Documentation des APIs Google utilisées dans LIA, avec détails de tarification pour la refacturation utilisateurs.

---

## Vue d'Ensemble

L'application utilise deux catégories d'APIs Google :

| Catégorie | Authentification | Facturation |
|-----------|------------------|-------------|
| **Maps Platform** | `GOOGLE_API_KEY` (globale) | Pay-as-you-go (facturable) |
| **Workspace APIs** | OAuth2 (par utilisateur) | Gratuit (quotas uniquement) |

> **Tracking automatisé** : Depuis la v6.1, tous les appels Maps Platform sont automatiquement trackés pour la facturation utilisateur. Voir [GOOGLE_API_TRACKING.md](./GOOGLE_API_TRACKING.md) pour la documentation du système de tracking.

---

## Seuils de Gratuité - Tableau Récapitulatif

### Maps Platform (par compte de facturation, par mois)

| API | Endpoint | Seuil Gratuit/mois | Coût après seuil (/1000 req) | Économie gratuite |
|-----|----------|-------------------|------------------------------|-------------------|
| **Places API** | `/places:searchText` | **5,000 req** | $32.00 | $160.00 |
| **Places API** | `/places:searchNearby` | **5,000 req** | $32.00 | $160.00 |
| **Places API** | `/places/{id}` (Details) | **5,000 req** | $17.00 | $85.00 |
| **Places API** | `/places:autocomplete` | **10,000 req** | $2.83 | $28.30 |
| **Places API** | `/{photo}/media` | **1,000 req** | $7.00 | $7.00 |
| **Routes API** | `/directions/v2:computeRoutes` | **10,000 req** | $5.00 | $50.00 |
| **Routes API** | `/distanceMatrix/v2:computeRouteMatrix` | **10,000 req** | $5.00 | $50.00 |
| **Geocoding API** | `/geocode/json` | **10,000 req** | $5.00 | $50.00 |
| **Static Maps API** | `/staticmap` | **10,000 req** | $2.00 | $20.00 |

**Économie totale gratuite potentielle : ~$610/mois**

> **Important** : Ces seuils sont **par compte Google Cloud**, pas par utilisateur. Si vous avez 100 utilisateurs qui font chacun 100 recherches Places, vous consommez 10,000 requêtes sur le seuil de 5,000 gratuit.

### Workspace APIs (par projet, par jour)

| API | Quota Gratuit/jour | Limite/utilisateur | Coût |
|-----|--------------------|--------------------|------|
| **Gmail API** | 1,000,000,000 quota units | 250 units/sec | **GRATUIT** |
| **Calendar API** | 1,000,000 requêtes | 100 req/100sec | **GRATUIT** |
| **People API** | 90,000 requêtes | 60 req/min | **GRATUIT** |
| **Drive API** | 12,000 req/min | 1000 req/100sec | **GRATUIT** |
| **Tasks API** | 50,000 requêtes | 50 req/sec | **GRATUIT** |

---

## 1. APIs Maps Platform (Facturables)

Ces APIs utilisent la clé API globale et sont facturées au volume.

### 1.1 Places API (New)

**Base URL** : `https://places.googleapis.com/v1`

**Client** : `google_places_client.py`

| Endpoint | SKU | Coût /1000 req | Gratuit/mois | Usage dans l'app |
|----------|-----|----------------|--------------|------------------|
| `/places:searchText` | Text Search Pro | **$32.00** | 5,000 | Recherche de lieux par texte |
| `/places:searchNearby` | Nearby Search Pro | **$32.00** | 5,000 | Recherche de lieux à proximité |
| `/places/{id}` | Place Details Pro | **$17.00** | 5,000 | Détails d'un lieu |
| `/places:autocomplete` | Autocomplete | **$2.83** | 10,000 | Suggestions de saisie |
| `/{photo}/media` | Place Details Photos | **$7.00** | 1,000 | Photos de lieux |

> **Note** : Les tarifs indiqués sont les tarifs de base. Ils diminuent avec le volume (jusqu'à -92.5% à 5M+ requêtes).

**Estimation mensuelle** (usage modéré par utilisateur) :
- 50 recherches texte/mois × $0.032 = $1.60
- 20 détails lieu/mois × $0.017 = $0.34
- 100 autocomplete/mois × $0.00283 = $0.28
- 30 photos/mois × $0.007 = $0.21
- **Total estimé : ~$2.43/utilisateur/mois**

---

### 1.2 Routes API

**Base URL** : `https://routes.googleapis.com`

**Client** : `google_routes_client.py`

| Endpoint | SKU | Coût /1000 req | Gratuit/mois | Usage dans l'app |
|----------|-----|----------------|--------------|------------------|
| `/directions/v2:computeRoutes` | Compute Routes (Essentials) | **$5.00** | 10,000 | Calcul d'itinéraires simples |
| `/directions/v2:computeRoutes` | Compute Routes Pro* | **$10.00** | 5,000 | Avec trafic temps réel |
| `/distanceMatrix/v2:computeRouteMatrix` | Route Matrix (Essentials) | **$5.00** | 10,000 | Matrice de distances |
| `/distanceMatrix/v2:computeRouteMatrix` | Route Matrix Pro* | **$10.00** | 5,000 | Avec trafic temps réel |

> *Pro = avec `routingPreference: TRAFFIC_AWARE` ou `TRAFFIC_AWARE_OPTIMAL`

**Estimation mensuelle** :
- 30 itinéraires/mois × $0.005 = $0.15/utilisateur/mois

---

### 1.3 Geocoding API

**Base URL** : `https://maps.googleapis.com/maps/api`

**Client** : `google_geocoding_helpers.py`

| Endpoint | SKU | Coût /1000 req | Gratuit/mois | Usage dans l'app |
|----------|-----|----------------|--------------|------------------|
| `/geocode/json` | Geocoding | **$5.00** | 10,000 | Conversion adresse ↔ coordonnées |

**Estimation mensuelle** :
- 10 géocodages/mois × $0.005 = $0.05/utilisateur/mois

---

### 1.4 Static Maps API

**Base URL** : `https://maps.googleapis.com/maps/api`

**Client** : `router.py` (endpoint `/connectors/static-map`)

| Endpoint | SKU | Coût /1000 req | Gratuit/mois | Usage dans l'app |
|----------|-----|----------------|--------------|------------------|
| `/staticmap` | Static Maps | **$2.00** | 10,000 | Images de cartes statiques |

**Estimation mensuelle** :
- 20 cartes/mois × $0.002 = $0.04/utilisateur/mois

---

### Résumé Tarification Maps Platform

| API | Coût principal /1000 | Seuil gratuit | Risque coût |
|-----|---------------------|---------------|-------------|
| **Places Text Search** | $32.00 | 5,000/mois | **ÉLEVÉ** |
| **Places Nearby** | $32.00 | 5,000/mois | **ÉLEVÉ** |
| **Places Details** | $17.00 | 5,000/mois | MOYEN |
| **Places Photos** | $7.00 | 1,000/mois | MOYEN |
| **Places Autocomplete** | $2.83 | 10,000/mois | FAIBLE |
| **Routes** | $5.00-$10.00 | 5-10,000/mois | FAIBLE |
| **Geocoding** | $5.00 | 10,000/mois | FAIBLE |
| **Static Maps** | $2.00 | 10,000/mois | FAIBLE |

**Coût total estimé par utilisateur actif** : **$2.50 - $5.00/mois**

---

## 2. APIs Workspace (Gratuites - Quotas)

Ces APIs utilisent OAuth2 et sont **gratuites** dans les limites de quotas.

### 2.1 Gmail API

**Base URL** : `https://gmail.googleapis.com/gmail/v1`

**Client** : `google_gmail_client.py`

| Endpoint | Quota | Coût |
|----------|-------|------|
| `/users/me/messages` | 250 quota units/user/sec | **GRATUIT** |
| `/users/me/messages/send` | 100 quota units/user/sec | **GRATUIT** |
| `/users/me/messages/{id}` | 5 quota units/user/sec | **GRATUIT** |
| `/users/me/messages/{id}/modify` | 200 quota units/user/sec | **GRATUIT** |
| `/users/me/messages/{id}/trash` | 10 quota units/user/sec | **GRATUIT** |
| `/users/me/labels` | 1 quota unit/user/sec | **GRATUIT** |

**Quota global** : 1,000,000,000 quota units/jour/projet

---

### 2.2 Google Calendar API

**Base URL** : `https://www.googleapis.com/calendar/v3`

**Client** : `google_calendar_client.py`

| Endpoint | Quota | Coût |
|----------|-------|------|
| `/calendars/{id}/events` (list) | 100 req/100sec/user | **GRATUIT** |
| `/calendars/{id}/events` (insert) | 500 req/100sec/user | **GRATUIT** |
| `/calendars/{id}/events/{eventId}` (get) | 100 req/100sec/user | **GRATUIT** |
| `/calendars/{id}/events/{eventId}` (update) | 100 req/100sec/user | **GRATUIT** |
| `/calendars/{id}/events/{eventId}` (delete) | 100 req/100sec/user | **GRATUIT** |
| `/users/me/calendarList` | 100 req/100sec/user | **GRATUIT** |

**Quota global** : 1,000,000 requêtes/jour/projet

---

### 2.3 People API (Contacts)

**Base URL** : `https://people.googleapis.com/v1`

**Client** : `google_people_client.py`

| Endpoint | Quota | Coût |
|----------|-------|------|
| `/people:searchContacts` | 60 req/min/user | **GRATUIT** |
| `/people/me/connections` | 60 req/min/user | **GRATUIT** |
| `/people/{resourceName}` | 60 req/min/user | **GRATUIT** |
| `/people:createContact` | 60 req/min/user | **GRATUIT** |
| `/{resourceName}:updateContact` | 60 req/min/user | **GRATUIT** |
| `/{resourceName}:deleteContact` | 60 req/min/user | **GRATUIT** |

**Quota global** : 90,000 requêtes/jour/projet

---

### 2.4 Google Drive API

**Base URL** : `https://www.googleapis.com/drive/v3`

**Client** : `google_drive_client.py`

| Endpoint | Quota | Coût |
|----------|-------|------|
| `/files` (list) | 1000 req/100sec/user | **GRATUIT** |
| `/files/{fileId}` (get) | 1000 req/100sec/user | **GRATUIT** |
| `/files/{fileId}` (delete) | 1000 req/100sec/user | **GRATUIT** |

**Quota global** : 12,000 requêtes/minute/projet

---

### 2.5 Google Tasks API

**Base URL** : `https://tasks.googleapis.com/tasks/v1`

**Client** : `google_tasks_client.py`

| Endpoint | Quota | Coût |
|----------|-------|------|
| `/users/@me/lists` | 50 req/sec/user | **GRATUIT** |
| `/users/@me/lists/{id}` | 50 req/sec/user | **GRATUIT** |
| `/lists/{listId}/tasks` | 50 req/sec/user | **GRATUIT** |
| `/lists/{listId}/tasks/{taskId}` | 50 req/sec/user | **GRATUIT** |

**Quota global** : 50,000 requêtes/jour/projet

---

## 3. Infrastructure OAuth

| Service | URL | Coût |
|---------|-----|------|
| Token Endpoint | `https://oauth2.googleapis.com/token` | **GRATUIT** |
| Revocation | `https://oauth2.googleapis.com/revoke` | **GRATUIT** |
| UserInfo | `https://www.googleapis.com/oauth2/v2/userinfo` | **GRATUIT** |

---

## 4. Modèle de Refacturation Proposé

### 4.1 Coûts Réels Estimés

| Profil Utilisateur | Places | Routes | Geocoding | Static Maps | **Total/mois** |
|--------------------|--------|--------|-----------|-------------|----------------|
| Light (occasionnel) | $0.80 | $0.05 | $0.02 | $0.01 | **~$0.90** |
| Medium (régulier) | $2.50 | $0.15 | $0.05 | $0.04 | **~$2.75** |
| Heavy (intensif) | $8.00 | $0.50 | $0.15 | $0.10 | **~$8.75** |

### 4.2 Recommandations Pricing

1. **Seuil gratuit** : Inclure dans le forfait de base jusqu'au seuil Google gratuit (~5000 recherches Places/mois)

2. **Au-delà** : Facturer avec marge de 20-30% :
   - Places Search : $0.04/recherche (coût réel $0.032)
   - Places Details : $0.02/détail (coût réel $0.017)
   - Routes : $0.007/itinéraire (coût réel $0.005)

3. **Forfait "Power User"** : $5-10/mois pour usage illimité raisonnable

### 4.3 Métriques à Tracker

> **✅ Implémenté** : Le système de tracking est maintenant en production (v6.1).
> Voir [GOOGLE_API_TRACKING.md](./GOOGLE_API_TRACKING.md) pour la documentation complète.

**Tables utilisées** :

```python
# Table: google_api_usage_logs (audit trail immutable)
class GoogleApiUsageLog(BaseModel):
    user_id: UUID
    run_id: str  # LangGraph run_id
    api_name: str  # "places", "routes", "geocoding", "static_maps"
    endpoint: str
    request_count: int
    cost_usd: Decimal
    cost_eur: Decimal
    cached: bool
```

**Tracking automatique** via ContextVar pattern - voir [GOOGLE_API_TRACKING.md](./GOOGLE_API_TRACKING.md).

---

## 5. Optimisations Coûts

### 5.1 Déjà Implémentées

- **Cache Redis** : Résultats Places et Routes cachés (TTL 1h-24h)
- **Rate Limiting** : Limitation requêtes par utilisateur
- **Field Masks** : Demande uniquement les champs nécessaires (réduit coût Places Details)

### 5.2 À Considérer

- **Session Tokens** : Pour Autocomplete (réduit coût de $2.83 à $0.00 si suivi d'un Place Details)
- **Batch Requests** : Regrouper les requêtes Geocoding
- **Fallback Wikipedia** : Pour infos générales, utiliser Wikipedia (gratuit) avant Places

---

## 6. Références

**Documentation Interne** :
- [GOOGLE_API_TRACKING.md](./GOOGLE_API_TRACKING.md) - Système de tracking et facturation
- [LLM_PRICING_MANAGEMENT.md](./LLM_PRICING_MANAGEMENT.md) - Pricing LLM + exports

**Documentation Google** :
- [Google Maps Platform Pricing](https://mapsplatform.google.com/pricing/)
- [Maps Platform Billing & Pricing Details](https://developers.google.com/maps/billing-and-pricing/pricing)
- [Gmail API Quotas](https://developers.google.com/gmail/api/reference/quota)
- [Calendar API Quotas](https://developers.google.com/workspace/calendar/api/guides/quota)
- [People API Quotas](https://developers.google.com/people/api/rest/v1/quota)
- [Drive API Quotas](https://developers.google.com/drive/api/guides/limits)
- [Tasks API Quotas](https://developers.google.com/tasks/reference/quota)

---

## 7. Changelog

| Date | Version | Changement |
|------|---------|------------|
| 2026-02-04 | 1.1 | Références vers GOOGLE_API_TRACKING.md, tracking implémenté |
| 2026-02-03 | 1.0 | Création initiale |
