---
name: qr-code
description: >
  Generates a scannable QR code from text, URL, WiFi credentials or contact
  info. Use when the user asks for a QR code, or wants to share a link, a
  WiFi network, or a phone number/contact via QR.
category: utilities
priority: 50
outputs: [text, image]
plan_template:
  deterministic: true
  steps:
    - step_id: render_qr
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: qr-code
        script: render_qr.py
        parameters:
          content: "{{ query.text }}"
      depends_on: []
      description: Render the QR code PNG from the user's content.
---

# QR Code

## Instructions

This skill produces a scannable QR code embedded inline in the chat.

1. Extract the payload from the user's query:
   - **URL** — if the query contains a URL, use it directly.
   - **WiFi** — if the query gives an SSID and password, build the standard
     WiFi payload: ``WIFI:T:<WPA|WEP|nopass>;S:<ssid>;P:<password>;;``.
   - **Contact (vCard)** — if the query gives a contact card, build a minimal
     VCARD 3.0 payload (``BEGIN:VCARD...``).
   - **Plain text** — otherwise, encode the text as-is.
2. The rendering script handles the encoding (``segno`` pure-Python). It
   returns a PNG image encoded as a ``data:image/png;base64,...`` URI so
   no external service is needed and the QR remains available offline.
3. Present the returned image with a one-sentence caption.

## Output Contract

Returns ``text`` + ``image.url`` via the SkillScriptOutput contract:

- ``text``: one-line caption describing what the QR encodes.
- ``image.url``: ``data:image/png;base64,...`` data URI (no external fetch).
- ``image.alt``: human-readable description for accessibility.

## Ressources disponibles

- scripts/render_qr.py — Generates the QR code PNG from the user's content.
