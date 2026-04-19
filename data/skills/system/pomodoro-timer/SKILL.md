---
name: pomodoro-timer
description: >
  Launches an interactive Pomodoro timer (work/break cycle) with an animated
  circular countdown. Use when the user asks to start a Pomodoro, a focus
  session, a 25/5 timer, or any timed work/break interval.
category: quotidien
priority: 50
outputs: [text, frame]
plan_template:
  deterministic: true
  steps:
    - step_id: render_timer
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: pomodoro-timer
        script: render_timer.py
        parameters:
          work_minutes: 25
          break_minutes: 5
      depends_on: []
      description: Render the interactive Pomodoro timer as an HTML frame.
---

# Pomodoro Timer

## Instructions

This skill launches a self-contained interactive Pomodoro timer directly in
the chat. The plan is deterministic: the rendering script emits an HTML
frame with an animated SVG countdown, start/pause/reset controls, and an
automatic work→break transition.

Default cycle: 25 minutes of focus, followed by 5 minutes of break. The
user can override either duration in their query (e.g. "50/10 pomodoro"
or "minuteur de 15 minutes de travail"). The response LLM should detect
these overrides and pass ``work_minutes`` / ``break_minutes`` accordingly
when invoking the script.

## Output Contract

Returns ``text`` + ``frame.html``:

- ``text``: one-line caption announcing the timer.
- ``frame.html``: the inline interactive HTML (SVG + inline JS).

## Ressources disponibles

- scripts/render_timer.py — Generates the interactive Pomodoro HTML frame.
