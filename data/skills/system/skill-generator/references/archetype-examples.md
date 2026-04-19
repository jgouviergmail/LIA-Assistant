# Skill Archetype Examples

Three complete SKILL.md examples — one per archetype.
These examples follow the EXACT same structure as the existing system skills.
Use them as templates when generating new skills.

---

## 1. Prompt Expert — coaching-productivite (real system skill)

Pure instructions. No tools. The LLM follows expert guidance.

---
name: coaching-productivite
description: >
  Provides productivity coaching with prioritization frameworks (Eisenhower,
  Pomodoro) and habit-building strategies. Use when the user asks for help
  organizing tasks, managing time, or improving productivity.
category: productivite
priority: 50
---

# Coaching Productivité

## Instructions

Tu es un coach en productivité personnelle. Aide l'utilisateur à mieux
s'organiser, prioriser ses tâches et développer des habitudes efficaces.
Adapte tes conseils au contexte et aux contraintes de l'utilisateur.

## Frameworks disponibles

### Matrice d'Eisenhower
Classifier chaque tâche selon 2 axes :
- Urgent + Important → Faire immédiatement
- Important + Non urgent → Planifier (bloc calendrier)
- Urgent + Non important → Déléguer si possible
- Ni urgent ni important → Éliminer ou reporter

### Méthode Pomodoro
- Blocs de 25 min de focus intense
- Pause de 5 min entre chaque bloc
- Pause longue de 15-30 min après 4 blocs

## Approche

1. Écouter le contexte : charge actuelle, contraintes, énergie
2. Diagnostiquer : identifier le frein principal
3. Proposer un framework adapté avec des actions concrètes
4. Simplifier : commencer par 1-2 changements, pas une refonte totale

## Ressources disponibles

- references/matrice-eisenhower.md — Guide complet de la matrice d'Eisenhower
- references/techniques.md — Fiches détaillées : Pomodoro, GTD, Time Blocking

---

## 2. Advisory — preparation-reunion (real system skill)

Structured methodology. The LLM uses tools organically (calendar, contacts, emails).

---
name: preparation-reunion
description: >
  Prepares meeting materials by gathering calendar details, participant contacts,
  and recent email history. Use when the user mentions preparing for a meeting,
  reviewing attendees, or creating an agenda.
category: organisation
priority: 65
---

# Préparation de Réunion

## Instructions

1. Identifier la réunion cible dans le calendrier (la plus proche ou celle spécifiée)
2. Extraire les détails : titre, date/heure, lieu/lien, participants
3. Pour chaque participant : récupérer les coordonnées et le contexte récent
4. Chercher les échanges email récents avec les participants
5. Compiler un dossier de préparation structuré

## Format de sortie

### Informations de la réunion
- Titre, date, heure, durée
- Lieu ou lien de visioconférence
- Organisateur

### Participants
Pour chaque participant :
- Nom, fonction/titre
- Email, téléphone
- Dernier échange (date + résumé 1 ligne)

### Contexte
- Sujets en cours avec les participants
- Points en suspens des échanges récents

### Ordre du jour suggéré
1. Point sur [sujet 1]
2. Discussion [sujet 2]
3. Prochaines étapes

## Ressources disponibles

- references/template-agenda.md — Template d'ordre du jour prêt à remplir

---

## 3. Plan Template — briefing-quotidien (real system skill)

Deterministic automation. Fixed tool calls, bypasses the LLM planner.

---
name: briefing-quotidien
description: >
  Generates a comprehensive today briefing combining calendar events, priority tasks,
  and weather forecast. Use when the user asks for a briefing, daily summary,
  or "what's on my schedule today".
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters:
        days_ahead: 2
        max_results: 5
      depends_on: []
      description: Récupérer les événements du jour et du lendemain
    - step_id: get_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        show_completed: false
      depends_on: []
      description: Lister les tâches en cours et prioritaires
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        days: 3
      depends_on: []
      description: Météo aujourd'hui + tendance 3 jours
    - step_id: get_emails
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters:
        query: "in:inbox newer_than:1d"
        max_results: 5
      depends_on: []
      description: Récupérer les 5 derniers emails reçus aujourd'hui
---

# Briefing Quotidien

## Instructions

1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir via tasks
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Formater en sections structurées : Agenda → Tâches → Météo → Emails → À noter
6. Commencer par le plus urgent, terminer par les suggestions proactives

## Format de sortie

### 📅 Agenda du jour
- Lister chaque rdv avec heure, titre et lieu
- Mettre en évidence les conflits horaires éventuels

### ✅ Tâches prioritaires
- Tâches en retard (avec date d'échéance dépassée)
- Tâches du jour classées par priorité

### 🌤 Météo
- Conditions actuelles (température, ciel, vent)
- Prévisions pour la journée
- Tendance sur 3 jours

### 📧 Emails du jour
- Les 5 derniers emails reçus aujourd'hui
- Expéditeur, objet et résumé court

### 💡 À noter
- Suggestions proactives basées sur le contexte

## Ressources disponibles

- references/output-format.md — Template détaillé du format de sortie

---

## 4. Visualizer — interactive-map (reference example)

Skill emitting an interactive iframe. No `plan_template` — the ReAct agent
extracts the parameter from the user's query and calls `run_skill_script`.

### SKILL.md

```yaml
---
name: interactive-map
description: >
  Shows an interactive Google Maps view for a given location. Use when the
  user asks to show, display, or find a place on a map.
category: utilities
priority: 50
outputs: [text, frame]
---

# Interactive Map

## Instructions

1. Extract the `location` from the user's query (place name, address, or landmark).
2. Call `run_skill_script` with:
   - script: `render_map.py`
   - parameters: `{"location": "<extracted location>"}`
3. Present the resulting frame with a one-sentence caption.

## Ressources disponibles

- scripts/render_map.py — Generates the Google Maps embed URL
```

### scripts/render_map.py

```python
"""Render an interactive Google Maps iframe for a given location."""

import json
import sys
from urllib.parse import quote


def main() -> None:
    raw = sys.stdin.read() or "{}"
    payload = json.loads(raw)
    params = payload.get("parameters", {})
    location = (params.get("location") or "").strip()

    if not location:
        print(json.dumps({
            "text": "No location was provided.",
            "error": "Missing 'location' parameter",
        }))
        return

    url = f"https://maps.google.com/maps?q={quote(location)}&output=embed"
    print(json.dumps({
        "text": f"Here is {location} on the map.",
        "frame": {
            "url": url,
            "title": f"Map: {location}",
            "aspect_ratio": 1.333,
        },
    }))


if __name__ == "__main__":
    main()
```

---

## 5. Generator — qr-code (reference example)

Skill emitting a generated image (base64-encoded) alongside a confirmation.
Demonstrates the `image` field of `SkillScriptOutput`.

### SKILL.md

```yaml
---
name: qr-code
description: >
  Generates a QR code image for any text or URL. Use when the user asks to
  create a QR code or to encode something visually.
category: utilities
priority: 45
outputs: [text, image]
---

# QR Code Generator

## Instructions

1. Extract the content to encode from the user's query (text, URL, vCard...).
2. Call `run_skill_script` with:
   - script: `generate_qr.py`
   - parameters: `{"content": "<text to encode>"}`
3. Present the generated QR code with a one-sentence caption.

## Ressources disponibles

- scripts/generate_qr.py — Generates the QR code as a data: URI image
```

### scripts/generate_qr.py

```python
"""Generate a QR code image as a base64 data URI.

Uses the ``segno`` library (pure Python, bundled with LIA — no compiled
deps, no external service). The ``_lang`` parameter is auto-injected by
``run_skill_script`` and used here to localize the caption.
"""

import base64
import io
import json
import sys

import segno  # type: ignore[import-untyped]


_LABELS = {
    "fr": "Code QR pour : {c}",
    "en": "QR code for: {c}",
    "es": "Código QR para: {c}",
    "de": "QR-Code für: {c}",
    "it": "Codice QR per: {c}",
    "zh": "QR 码:{c}",
}


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    params = payload.get("parameters", {})
    content = (params.get("content") or "").strip()
    lang = (params.get("_lang") or "en").lower().split("-")[0]
    caption_tpl = _LABELS.get(lang, _LABELS["en"])

    if not content:
        print(json.dumps({
            "text": "No content was provided to encode.",
            "error": "Missing 'content' parameter",
        }))
        return

    qr = segno.make(content, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=2)
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    print(json.dumps({
        "text": caption_tpl.format(c=content[:60]),
        "image": {
            "url": data_uri,
            "alt": caption_tpl.format(c=content[:60]),
        },
    }))


if __name__ == "__main__":
    main()
```

---

## 6. Interactive Visualizer — canonical pattern

Minimal reference for a frame that:

- Reads the auto-injected ``_lang`` to localize its labels (tables inline,
  no ``setlocale`` dependency).
- Uses ``html[data-theme="dark"]`` (NOT ``@media prefers-color-scheme``)
  so the iframe follows the LIA app theme.
- Embeds client-side JS so the user can interact without a new backend
  round-trip (here: a re-roll button).

Use this as the starting template for any interactive Visualizer skill.

### SKILL.md

```yaml
---
name: coin-flip
description: >
  Flips a virtual coin and shows the result. Use when the user wants to
  decide between two options or get a random heads/tails.
category: utilities
priority: 40
outputs: [text, frame]
---

# Coin Flip

## Instructions

1. Call run_skill_script with:
   - script: render_coin.py
   - parameters: {} (no user input needed — the script seeds an initial flip)
2. Present the returned frame with a one-sentence caption. The user can
   re-flip directly inside the frame.

## Ressources disponibles

- scripts/render_coin.py — Interactive coin-flip frame.
```

### scripts/render_coin.py

```python
"""Interactive coin flip — client-side re-roll, i18n, theme-aware."""

import json
import secrets
import sys


_LABELS = {
    "fr": {"heads": "Pile", "tails": "Face", "reroll": "Relancer", "caption": "Pièce tirée : {r}"},
    "en": {"heads": "Heads", "tails": "Tails", "reroll": "Flip again", "caption": "Coin flipped: {r}"},
    "es": {"heads": "Cara", "tails": "Cruz", "reroll": "Relanzar", "caption": "Moneda: {r}"},
    "de": {"heads": "Kopf", "tails": "Zahl", "reroll": "Nochmal", "caption": "Münze: {r}"},
    "it": {"heads": "Testa", "tails": "Croce", "reroll": "Rilancia", "caption": "Moneta: {r}"},
    "zh": {"heads": "正面", "tails": "反面", "reroll": "再抛一次", "caption": "硬币:{r}"},
}


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    params = payload.get("parameters", {})
    lang = (params.get("_lang") or "en").lower().split("-")[0]
    labels = _LABELS.get(lang, _LABELS["en"])

    # Seed an initial flip for the LLM-visible caption.
    initial = "heads" if secrets.randbelow(2) == 0 else "tails"
    initial_label = labels[initial]

    # The inline JS receives the localized labels via a small config block.
    cfg = json.dumps(labels, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #1f2937;
      padding: 24px 16px;
      text-align: center;
    }}
    .coin {{
      width: 120px; height: 120px; border-radius: 50%;
      background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
      color: white; font-weight: 800; font-size: 1.5rem;
      display: flex; align-items: center; justify-content: center;
      margin: 0 auto 20px;
      box-shadow: 0 8px 24px rgba(245, 158, 11, 0.4);
      animation: flip 500ms cubic-bezier(.2,.9,.3,1.2) both;
    }}
    @keyframes flip {{
      0%   {{ transform: rotateY(0) scale(0.6); opacity: 0; }}
      70%  {{ transform: rotateY(720deg) scale(1.08); opacity: 1; }}
      100% {{ transform: rotateY(720deg) scale(1); }}
    }}
    button {{
      border: none; border-radius: 999px;
      padding: 10px 22px; font-size: 0.95rem; font-weight: 600;
      background: linear-gradient(135deg, #6366f1, #4f46e5);
      color: white; cursor: pointer; font-family: inherit;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }}
    button:hover {{ filter: brightness(1.06); }}
    html[data-theme="dark"] body {{ color: #e5e7eb; }}
  </style>
</head>
<body>
  <div class="coin" id="coin">{initial_label}</div>
  <button id="reroll">{labels["reroll"]}</button>
  <script>
    (function() {{
      var LABELS = {cfg};
      var $coin = document.getElementById('coin');
      var $btn = document.getElementById('reroll');
      function flip() {{
        var buf = new Uint32Array(1);
        crypto.getRandomValues(buf);
        var side = (buf[0] & 1) ? LABELS.heads : LABELS.tails;
        // Remove + re-add the node so the CSS animation replays.
        var next = $coin.cloneNode(false);
        next.textContent = side;
        $coin.parentNode.replaceChild(next, $coin);
        $coin = next;
      }}
      $btn.addEventListener('click', flip);
    }})();
  </script>
</body>
</html>"""

    print(json.dumps({
        "text": labels["caption"].format(r=initial_label),
        "frame": {"html": html, "title": "Coin Flip", "aspect_ratio": 1.2},
    }))


if __name__ == "__main__":
    main()
```

**Pattern recap** (apply to every interactive Visualizer):

1. `_lang` read from params, defaults to `en`. Translation table inline,
   no ``setlocale``.
2. CSS uses ``html[data-theme="dark"]`` — the backend snippet sets the
   attribute from the LIA app theme automatically.
3. Client JS uses ``crypto.getRandomValues`` for CSPRNG and
   ``addEventListener`` (inline ``onclick=""`` is blocked by CSP).
4. Animation is replayed by replacing the element (``cloneNode`` +
   ``replaceChild``), not by toggling a class.
5. Nothing to do for resize / transparent background — the injected
   snippet handles both.

---

### Combining frame + image

The `SkillScriptOutput` contract allows both fields to coexist. Example:

```json
{
  "text": "Here is your weekly productivity report.",
  "frame": {
    "html": "<!DOCTYPE html><html><body><h1>Dashboard</h1>...</body></html>",
    "title": "Weekly productivity",
    "aspect_ratio": 1.777
  },
  "image": {
    "url": "data:image/png;base64,...",
    "alt": "Productivity chart"
  }
}
```

Rendering order in the chat: **text** (markdown) → **image** (card) → **frame** (iframe).
