---
name: dice-roller
description: >
  Rolls one or several dice with an animated 3D-like visual and a full
  breakdown of the result. Supports standard RPG notation (d4, d6, d8,
  d10, d12, d20, d100) and multiple dice (e.g. "2d6+3", "4d6kh3" for
  D&D stat rolls). Use when the user asks to roll dice, pick a random
  number, or decide something at random.
category: utilities
priority: 40
outputs: [text, frame]
---

# Dice Roller

## Instructions

This skill produces an interactive dice roller embedded in the chat.
Once rendered, the user can press **"Re-roll"** inside the frame to get
new values without sending another message.

When the user asks to roll dice:

1. Extract the dice notation from the user's query in the standard
   ``NdS[+/-M][khK|klK]`` shorthand:
   - ``"1d6"`` — one six-sided die (default if only "roll a die")
   - ``"2d6"`` — two six-sided dice
   - ``"3d20"`` — three twenty-sided dice
   - ``"1d100"`` — percentile
   - ``"2d6+3"`` — two d6 plus a flat modifier
   - ``"2d20kh1"`` — advantage (two d20, keep highest)
   - ``"4d6kh3"`` — D&D stat roll (four d6, drop lowest)

2. Call ``run_skill_script`` with:
   - ``skill_name``: ``dice-roller``
   - ``script``: ``render_dice.py``
   - ``parameters``: ``{"notation": "<extracted notation>"}``

3. Present the returned frame with a concise one-sentence caption.

Supported die sizes: 4, 6, 8, 10, 12, 20, 100.

### Fallback parsing

If the notation you pass contains extra words (for example the full user
sentence "lance 2d6 pour moi"), the script is tolerant and extracts the
first valid dice notation it finds in the string — but for best results
always pass the clean notation alone.

## Output Contract

Returns ``text`` + ``frame.html``:

- ``text``: one-line caption with the total result of the initial roll.
- ``frame.html``: the animated dice frame with a Re-roll button —
  subsequent re-rolls are handled client-side (no backend round-trip).

## Ressources disponibles

- scripts/render_dice.py — Parses the notation, seeds the initial roll
  and emits the interactive frame (crypto.getRandomValues for re-rolls).
