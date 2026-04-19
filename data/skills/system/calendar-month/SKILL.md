---
name: calendar-month
description: >
  Displays a visual calendar of the current month (or a specified month) as
  an interactive HTML grid with weekday headers and highlighted current day.
  Use when the user asks to show the calendar of the month, the month at a
  glance, or a specific month's grid.
category: utilities
priority: 45
outputs: [text, frame]
plan_template:
  deterministic: true
  steps:
    - step_id: render_month
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: calendar-month
        script: render_month.py
        parameters: {}
      depends_on: []
      description: Render the current month's calendar as an interactive HTML grid.
---

# Calendar Month

## Instructions

This skill renders a visual calendar of the current month as an interactive
frame. The plan is fully deterministic: the single step calls the rendering
script which generates the HTML grid from the system date. No external API
is involved.

The resulting frame shows:
- The month name and year in the header
- Seven weekday columns (Mon → Sun)
- All days of the month, with today highlighted
- Blank cells for days outside the current month

## Output Contract

Returns:
- ``text``: a short caption ("Here is <Month> <Year>.")
- ``frame.html``: the inline calendar HTML (srcDoc iframe)

## Ressources disponibles

- scripts/render_month.py — Generates the month calendar HTML from the current date.
