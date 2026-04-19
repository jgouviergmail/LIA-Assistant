---
name: unit-converter
description: >
  Interactive unit converter for temperature, length, weight, volume and
  speed. Use when the user asks to convert between units, compare metric
  and imperial, or just wants a quick conversion tool at hand.
category: utilities
priority: 45
outputs: [text, frame]
plan_template:
  deterministic: true
  steps:
    - step_id: render_converter
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: unit-converter
        script: render_converter.py
        parameters: {}
      depends_on: []
      description: Render the interactive unit converter as an HTML frame.
---

# Unit Converter

## Instructions

This skill renders a self-contained interactive unit converter directly in
the chat. The plan is deterministic: a single script call emits an HTML
frame with:

- A category selector (temperature / length / weight / volume / speed).
- Two unit dropdowns (from / to) populated for the selected category.
- A numeric input that triggers live conversion on every keystroke.
- A swap button to invert the source/target units.

No network calls are made; all conversion factors live inside the frame.

## Output Contract

Returns ``text`` + ``frame.html``:

- ``text``: short caption announcing the converter is ready.
- ``frame.html``: the self-contained interactive converter.

## Ressources disponibles

- scripts/render_converter.py — Generates the unit converter HTML frame.
