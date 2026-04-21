# Guide — iPhone Shortcuts ingestion for Health Metrics

This guide walks through setting up an iPhone Shortcut automation that pushes your day's heart-rate and step samples to LIA as **batches**. Each sample carries its own start/end timestamp, so re-running the Shortcut later in the day is safe — the server upserts on `(kind, date_start, date_end)` and the last value wins.

## Prerequisites

- iOS 17+ with the **Shortcuts** app available.
- An LIA account with `HEALTH_METRICS_ENABLED=true` in the backend configuration.
- Apple Health access: **Settings → Santé → Partage de données → Apps → Raccourcis** must be allowed to read *Fréquence cardiaque* and *Nombre de pas*.

## Why "batch" and not hourly

iOS personal automations that run "every hour" require the iPhone to be unlocked at trigger time to fire reliably. In practice most of us unlock a few times a day, so an hourly push is fragile. The server-side design accepts the full daily batch on every fire and deduplicates by (kind, date_start, date_end) — re-sending the day several times is free.

## 1. Generate an ingestion token

1. Open LIA in your browser.
2. Go to **Réglages → Fonctionnalités → Données santé → API d'ingestion**.
3. Enter an optional label (e.g. *iPhone perso*), click **Générer**.
4. The raw token is shown **once** — copy it immediately. It starts with `hm_` and is 30+ characters long.

If you miss the copy window, revoke the token and create a new one. LIA never stores the raw value, only a hash and the 11-char prefix for identification.

The same token authenticates both ingestion endpoints (`/steps` and `/heart_rate`).

## 2. Create one Shortcut per kind

The simplest setup is **two Shortcuts** (one for steps, one for heart rate) — each a thin pipe: fetch Apple Health samples → format to JSON → POST.

### Shortcut A — Steps

In **Raccourcis → Mes raccourcis → + (nouveau)**:

1. **Date courante** → set as `now`.
2. **Ajuster la date** → `now` − `1 jour` → set as `since`. (Or a wider window if you want more history per send.)
3. **Obtenir des échantillons de santé**:
   - *Type de données* : **Nombre de pas**
   - *Plage de dates* : **Personnalisée**, `since` → `now`
4. **Répéter avec chaque élément** on the samples:
   - Inside the loop, build a **Dictionnaire**:
     ```
     date_start : <Date de début de l'élément>, format ISO 8601
     date_end   : <Date de fin de l'élément>,   format ISO 8601
     steps      : <Quantité de l'élément>       (entier)
     o          : iphone
     ```
   - **Ajouter au tableau** — append the dictionary to a variable `batch`.
5. **Obtenir le contenu de** the `batch` array → format = **JSON** (produces a JSON array string).
6. **Obtenir le contenu d'une URL**:
   - *URL* : `https://lia.jeyswork.com/api/v1/ingest/health/steps`
   - *Méthode* : **POST**
   - *Headers* :
     - `Authorization` = `Bearer hm_votre_token`
     - `Content-Type` = `application/json`
   - *Corps de la requête* : **Fichier** → the JSON from step 5.
7. (Optional) **Si** statut HTTP ≠ 200 → **Afficher une notification** with the response body — very useful during setup.

Save as *LIA Health Push — Pas*.

### Shortcut B — Heart rate

Identical to Shortcut A, with two changes:
- *Type de données* in step 3 = **Fréquence cardiaque**.
- In the loop (step 4), use `heart_rate` instead of `steps` as the measurement key.
- *URL* in step 6 = `https://lia.jeyswork.com/api/v1/ingest/health/heart_rate`.

Save as *LIA Health Push — FC*.

## 3. Schedule

Two reliable options:

- **Personal automation — on unlock**: `+ → Automatisation personnelle → Quand le iPhone est déverrouillé → Exécuter le raccourci`. Fires at every unlock (the iPhone is by definition ready), but can be noisy — couple it with an internal check ("only run if last send > 4h ago").
- **Personal automation — fixed time(s) of day**: `Heure du jour`, e.g. 09:00 and 21:00. Uncheck **Demander avant l'exécution**. Very predictable.

In both cases the action is *Exécuter le raccourci* → *LIA Health Push — Pas*, then *Exécuter le raccourci* → *LIA Health Push — FC*.

## 4. Verify

- Open **Réglages → Fonctionnalités → Données santé → Graphiques**, period **Heure** or **Jour**. The timeline should show the samples you just pushed.
- Check the response body returned by the Shortcut:
  ```json
  {"received": 24, "inserted": 20, "updated": 4, "rejected": []}
  ```
  `inserted` + `updated` = `received` − `len(rejected)`.

## Expected request / response

**Request** — batch of two step samples:

```
POST https://lia.jeyswork.com/api/v1/ingest/health/steps
Authorization: Bearer hm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json

[
  {"date_start": "2026-04-21T06:00:00+02:00",
   "date_end":   "2026-04-21T07:00:00+02:00",
   "steps": 1234, "o": "iphone"},
  {"date_start": "2026-04-21T07:00:00+02:00",
   "date_end":   "2026-04-21T08:00:00+02:00",
   "steps": 5678, "o": "iphone"}
]
```

**Response — 200 OK** (both samples were new):

```json
{"received": 2, "inserted": 2, "updated": 0, "rejected": []}
```

**Response — 200 OK, partial** (one out-of-range sample dropped, two valid saved):

```json
{
  "received": 3,
  "inserted": 2,
  "updated": 0,
  "rejected": [{"index": 1, "reason": "out_of_range:above_max"}]
}
```

**Errors**

| Code | Meaning                                             | Action                                    |
| ---- | --------------------------------------------------- | ----------------------------------------- |
| 400  | Malformed body (not JSON / not a recognized shape)  | Check step 5's "Obtenir le contenu de"    |
| 401  | Missing / invalid / revoked token                   | Regenerate from Settings                  |
| 413  | Batch exceeds `health_metrics_max_samples_per_request` (default 1000) | Narrow the date range |
| 422  | Request schema invalid                              | Check that you posted an array of dicts   |
| 429  | Rate limit exceeded (60 req/h/token default)        | Reduce the automation frequency           |

## Why ISO 8601 with a timezone offset

Samples are deduplicated on `(user_id, kind, date_start, date_end)`. For the unique key to be stable across sends, the timestamp must be **absolute** — an offset-less `"2026-04-21T14:30:00"` is ambiguous and is rejected with `invalid_date`. Use `"2026-04-21T14:30:00+02:00"` or the `Z` suffix for UTC.

iOS's "format ISO 8601" option on the *Format de date* action already produces a compliant value when *Inclure le décalage horaire* is on.

## Troubleshooting

- **No data appears on the charts**: the default period is *Jour*; switch to *Heure* if you pushed short-interval samples.
- **`invalid_date` rejection**: the sample's date string lacks a timezone. Turn on *Inclure le décalage horaire* in the *Format de date* action.
- **`missing_field` rejection**: one of the measurement keys (`steps` or `heart_rate`) is absent — check the dictionary keys in the loop.
- **Everything gets rejected with `malformed:not_a_dict`**: step 5 produced a string, not a JSON array. Wire the loop result into *Obtenir le contenu de* with output = **JSON**.
- **Shortcut silently fails**: add the "Si statut ≠ 200" notification branch (step 7) — iOS otherwise swallows ingestion errors.
- **Heart rate reads stale values**: Apple Shortcuts returns the recorded samples. If the Watch hasn't measured recently, the loop will emit nothing. Consider triggering after a Watch measurement.

## Security notes

- Treat the token like a password. Anyone holding it can inject data into your account.
- Tokens can be revoked any time from **Settings → Health Metrics → Ingestion API → Existing tokens**.
- You can hold multiple active tokens at once (e.g. one per device). Generate a fresh one for each device rather than reusing.
