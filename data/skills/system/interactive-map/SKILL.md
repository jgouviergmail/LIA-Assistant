---
name: interactive-map
description: >
  Shows an interactive Google Maps view for a given location (city, landmark,
  address). Use when the user asks to show, display, or find a place on a map.
category: utilities
priority: 50
outputs: [text, frame]
---

# Interactive Map

## Instructions

This skill displays a Google Maps embed directly in the chat so the user can
pan, zoom and interact with the map without leaving the conversation.

When the user asks to show a place on a map:

1. Extract the `location` from the user's query (place name, landmark, address,
   or coordinates). Examples: "Paris", "Eiffel Tower", "1 Infinite Loop,
   Cupertino", "48.8584,2.2945".
2. Call `run_skill_script` with:
   - `skill_name`: `interactive-map`
   - `script`: `render_map.py`
   - `parameters`: `{"location": "<extracted location>"}`
3. Present the returned frame with a concise one-sentence caption (e.g.,
   "Voici Paris sur la carte." / "Here is Paris on the map.").

### Output contract

The script returns a `SkillScriptOutput` JSON with:
- `text`: short caption (used for voice/accessibility)
- `frame.url`: Google Maps embed URL (external iframe, HTTPS)
- `frame.title`: header badge
- `frame.aspect_ratio`: 1.333 (4:3, default)

### Examples

- "Show Paris on a map" → `location = "Paris"`
- "Where is the Eiffel Tower?" → `location = "Eiffel Tower"`
- "Display the Louvre on the map" → `location = "Louvre Museum"`
- "Montre-moi la Tour Eiffel sur la carte" → `location = "Tour Eiffel"`

## Ressources disponibles

- `scripts/render_map.py` — Generates the Google Maps embed URL from the location.
