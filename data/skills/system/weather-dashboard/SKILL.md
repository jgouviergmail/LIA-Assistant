---
name: weather-dashboard
description: >
  Displays a visual multi-day weather dashboard with daily cards (conditions
  icon, min/max temperature, humidity, wind). Use when the user asks for a
  weather dashboard, a visual forecast, the weather at a glance, or a
  graphical summary of the upcoming days.
category: quotidien
priority: 55
outputs: [text, frame]
compatibility: "Requires an OpenWeatherMap API key (configured in Connectors)"
plan_template:
  deterministic: true
  steps:
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        location: auto
        days: 5
      depends_on: []
      description: Fetch the 5-day weather forecast for the user's location.

    - step_id: render_dashboard
      agent_name: query_agent
      tool_name: run_skill_script
      parameters:
        skill_name: weather-dashboard
        script: render_dashboard.py
        parameters:
          forecasts: "$steps.get_weather.forecasts"
          location: "$steps.get_weather.location"
      depends_on: [get_weather]
      description: Render the forecast as an interactive HTML dashboard.
---

# Weather Dashboard

## Instructions

This skill produces a visual weather dashboard from a 5-day forecast. The
plan is fully deterministic:

1. Fetch the 5-day forecast for the user's current location.
2. Pass the forecast data to the Python script which renders an interactive
   HTML grid: one card per day with the weather icon, min/max temperature,
   conditions, humidity and wind speed.

The resulting frame appears directly in the chat. The ``text`` field carries
a brief textual summary used for voice and accessibility fallback.

## Output Contract

Returns ``text`` + ``frame.html`` via the SkillScriptOutput contract:

- ``text``: one-line summary (e.g., "Weather for Paris — 5 days.")
- ``frame.html``: the inline dashboard HTML (srcDoc iframe)

## Ressources disponibles

- scripts/render_dashboard.py — Generates the dashboard HTML from the forecast data.
