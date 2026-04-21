# Guide — iPhone Shortcuts ingestion for Health Metrics

This guide walks through setting up an iPhone Shortcut automation that pushes your heart rate and the number of steps recorded since the previous run to LIA, every hour.

## Prerequisites

- iOS 17+ with the **Shortcuts** app available.
- An LIA account with `HEALTH_METRICS_ENABLED=true` in the backend configuration.
- Apple Health access: **Settings → Santé → Partage de données → Apps → Raccourcis** must be allowed to read *Fréquence cardiaque* and *Nombre de pas*.

## Important — what `p` represents

The backend interprets `p` as **the number of steps recorded since the previous sample** (an increment), not as a daily cumulative count. Aim for an hourly automation; the server will sum per bucket so the chart shows steps per hour, per day, etc.

If you change the trigger frequency (e.g. every 30 min), keep `p` as "steps since the previous run" — the bucketing aggregation stays correct.

## 1. Generate an ingestion token

1. Open LIA in your browser.
2. Go to **Réglages → Fonctionnalités → Données santé → API d'ingestion**.
3. Enter an optional label (e.g. *iPhone perso*), click **Générer**.
4. The raw token is shown **once** — copy it immediately. It starts with `hm_` and is 30+ characters long.

If you miss the copy window, revoke the token and create a new one. LIA never stores the raw value, only a hash and the 11-char prefix for identification.

## 2. Create the Shortcut

In **Raccourcis → Mes raccourcis → + (nouveau)**:

### Step A — Get the heart rate

- Action **Obtenir des échantillons de santé** (*Find Health Samples*):
  - *Type de données* : **Fréquence cardiaque**
  - *Trier par* : **Date de fin**
  - *Ordre* : **Décroissant**
  - *Limite* : **1**
- Action **Définir la variable** → name = `hr` → value = the sample from the previous step.

### Step B — Get the steps recorded in the last hour

- Action **Date** → set to **Date courante** → store as `now`.
- Action **Ajuster la date** → input = `now`, opération = **Soustraire**, valeur = `1 hour` → store as `since`.
- Action **Obtenir des échantillons de santé**:
  - *Type de données* : **Nombre de pas**
  - *Plage de dates* : **Personnalisée**
  - *Date de début* : variable `since`
  - *Date de fin* : variable `now`
- Action **Calcul de statistique** (*Calculate Statistic on Health Samples*):
  - *Statistique* : **Somme**
  - *Échantillons* : result of the previous action
- Action **Définir la variable** → name = `steps` → value = the sum.

> If your automation runs every 30 minutes instead of every hour, change `1 hour` in step B to `30 minutes`.

### Step C — Build the JSON payload

- Action **Dictionnaire**:
  ```
  data:
    Dictionary:
      c:  <Magic Variable: hr>
      p:  <Magic Variable: steps>
      o:  iphone
  ```
- Action **Obtenir le contenu de** → format = **JSON** (converts the dictionary to a JSON string).

### Step D — POST to LIA

- Action **Obtenir le contenu d'une URL**:
  - *URL* : `https://lia.jeyswork.com/api/v1/ingest/health`
  - *Méthode* : **POST**
  - *Requête* :
    - Header: `Authorization` = `Bearer hm_votre_token_ici`
    - Header: `Content-Type` = `application/json`
  - *Corps de la requête* : **Fichier** → Variable = the JSON from Step C.

### Step E (optional) — Log/notify on failure

- Action **Si** → Statut HTTP ≠ 202 → **Afficher une notification** with the response body. Useful during setup.

Save the Shortcut and name it e.g. *LIA Health Push*.

## 3. Schedule it hourly

- Open the **Automation** tab → **+ → Automatisation personnelle → Heure du jour**.
- Pick any hour and tick **Répéter → Toutes les heures** (or every 30 min if you prefer finer granularity).
- Uncheck **Demander avant l'exécution**.
- Action: **Exécuter le raccourci → LIA Health Push**.

## 4. Verify

- Open **Réglages → Fonctionnalités → Données santé → Graphiques** — select period **Heure**. The latest bucket should show a non-null heart-rate point and a step count for the last hour.
- The bar chart will display one bar per hour, summing whatever `p` you sent during that hour.
- Check the response body returned by the Shortcut (`status: "accepted"` or `"partial"` expected).

## Expected request / response

**Request** (example: 4 521 steps walked during the last hour, HR = 72 bpm)

```
POST https://lia.jeyswork.com/api/v1/ingest/health
Authorization: Bearer hm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json

{"data": {"c": 72, "p": 4521, "o": "iphone"}}
```

**Response — 202 Accepted** (both fields stored)

```json
{
  "status": "accepted",
  "recorded_at": "2026-04-20T18:03:21.482937+00:00",
  "stored_fields": ["heart_rate", "steps"],
  "nullified_fields": []
}
```

**Response — 202 Accepted, partial** (one field was out of range)

```json
{
  "status": "partial",
  "recorded_at": "2026-04-20T18:03:21.482937+00:00",
  "stored_fields": ["steps"],
  "nullified_fields": ["heart_rate"]
}
```

**Errors**

| Code | Meaning                                          | Action                          |
| ---- | ------------------------------------------------ | ------------------------------- |
| 401  | Missing or invalid token                         | Regenerate from Settings        |
| 422  | Malformed JSON body                              | Check the `data` wrapper and types |
| 429  | Rate limit exceeded (5 req/hour/token by default)| Reduce the automation frequency |

## Troubleshooting

- **No data appears on the charts**: period selector defaults to *Jour*; switch to *Heure* to see individual samples.
- **Heart rate reads stale values**: Apple Shortcuts returns the last-recorded sample. If the Watch hasn't measured recently, it can be hours old. Consider triggering the Shortcut after a Watch measurement or forcing a reading with "Démarrer un entraînement".
- **Step count is always zero**: verify Step B's date range — `since` must be earlier than `now`. Also confirm the Shortcuts app has Health → Steps read access.
- **Step count above 15 000 per sample → field stored as NULL**: that's the per-sample upper bound (see `HEALTH_METRICS_STEPS_MAX`); raise it in `.env` if your trigger interval ever covers more than ~2h of intense activity.

## Security notes

- Treat the token like a password. Anyone in possession of it can inject data into your account.
- Tokens can be revoked any time from **Settings → Health Metrics → Ingestion API → Existing tokens**.
- You can hold multiple active tokens at once (e.g. one per device). Generate a fresh one for each device rather than reusing.
