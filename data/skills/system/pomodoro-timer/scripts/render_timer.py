"""Render an interactive Pomodoro timer as an inline HTML frame.

Reads optional ``work_minutes`` (default 25) and ``break_minutes``
(default 5) from stdin parameters. Runtime context ``_lang`` is
auto-injected by ``run_skill_script`` — labels are localized accordingly.

Emits a ``SkillScriptOutput`` JSON on stdout with a ``frame.html``
containing an animated SVG countdown, Start/Pause/Reset/Skip controls,
and automatic work↔break phase transitions.

Theming: CSS uses ``html[data-theme="dark"]`` selectors synced with the
LIA app theme via the runtime snippet in ``output_builder``.
"""

from __future__ import annotations

import json
import sys


# Localized labels surfaced in the HTML frame + as a JSON map consumed by
# the inline JS to relabel the phase badge when the timer transitions.
_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "focus": "Concentration",
        "break": "Pause",
        "done": "Terminé",
        "cycle": "Cycle",
        "start": "Démarrer",
        "pause": "Pause",
        "reset": "Réinitialiser",
        "skip": "Passer",
        "caption": "Pomodoro prêt : {w} min de concentration / {b} min de pause.",
        "title": "Pomodoro",
    },
    "en": {
        "focus": "Focus",
        "break": "Break",
        "done": "Done",
        "cycle": "Cycle",
        "start": "Start",
        "pause": "Pause",
        "reset": "Reset",
        "skip": "Skip",
        "caption": "Pomodoro timer ready: {w} min focus / {b} min break.",
        "title": "Pomodoro",
    },
    "es": {
        "focus": "Concentración",
        "break": "Pausa",
        "done": "Hecho",
        "cycle": "Ciclo",
        "start": "Iniciar",
        "pause": "Pausar",
        "reset": "Reiniciar",
        "skip": "Saltar",
        "caption": "Pomodoro listo: {w} min concentración / {b} min pausa.",
        "title": "Pomodoro",
    },
    "de": {
        "focus": "Fokus",
        "break": "Pause",
        "done": "Fertig",
        "cycle": "Zyklus",
        "start": "Start",
        "pause": "Pause",
        "reset": "Zurücksetzen",
        "skip": "Überspringen",
        "caption": "Pomodoro bereit: {w} Min Fokus / {b} Min Pause.",
        "title": "Pomodoro",
    },
    "it": {
        "focus": "Concentrazione",
        "break": "Pausa",
        "done": "Finito",
        "cycle": "Ciclo",
        "start": "Avvia",
        "pause": "Pausa",
        "reset": "Reset",
        "skip": "Salta",
        "caption": "Pomodoro pronto: {w} min concentrazione / {b} min pausa.",
        "title": "Pomodoro",
    },
    "zh": {
        "focus": "专注",
        "break": "休息",
        "done": "完成",
        "cycle": "周期",
        "start": "开始",
        "pause": "暂停",
        "reset": "重置",
        "skip": "跳过",
        "caption": "番茄钟就绪：{w} 分钟专注 / {b} 分钟休息。",
        "title": "番茄钟",
    },
}


def _lang_code(lang: str) -> str:
    base = (lang or "en").lower().split("-")[0]
    return base if base in _LABELS else "en"


def _build_html(
    work_minutes: int, break_minutes: int, lang: str, work_seconds: int, break_seconds: int
) -> str:
    labels = _LABELS[lang]
    labels_json = json.dumps(
        {
            "focus": labels["focus"],
            "break": labels["break"],
            "done": labels["done"],
            "start": labels["start"],
            "pause": labels["pause"],
        },
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{labels["title"]} — {work_minutes}/{break_minutes}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: transparent;
      color: #1f2937;
      padding: 24px 16px;
    }}
    .pomo {{ max-width: 360px; margin: 0 auto; text-align: center; }}
    .phase {{
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 6px;
      transition: color 240ms ease;
    }}
    .cycle {{ font-size: 0.78rem; color: #9ca3af; margin-bottom: 18px; }}
    .dial {{ width: 240px; height: 240px; margin: 0 auto 20px; position: relative; }}
    .dial svg {{ width: 100%; height: 100%; transform: rotate(-90deg); }}
    .dial .track {{ stroke: #e5e7eb; stroke-width: 10; fill: none; }}
    .dial .progress {{
      stroke: var(--accent);
      stroke-width: 12;
      stroke-linecap: round;
      fill: none;
      transition: stroke-dashoffset 1s linear, stroke 240ms ease;
    }}
    .dial .time {{
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #111827;
      font-variant-numeric: tabular-nums;
    }}
    .controls {{ display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
    button {{
      border: none;
      border-radius: 999px;
      padding: 10px 20px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: transform 120ms ease, background 120ms ease, filter 120ms ease;
      font-family: inherit;
    }}
    .primary {{
      background: var(--accent);
      color: white;
      box-shadow: 0 3px 10px color-mix(in srgb, var(--accent) 40%, transparent);
    }}
    .primary:hover {{ transform: translateY(-1px); filter: brightness(1.05); }}
    .secondary {{ background: #f3f4f6; color: #374151; }}
    .secondary:hover {{ background: #e5e7eb; }}
    .pomo[data-phase="work"] {{ --accent: #dc2626; }}
    .pomo[data-phase="break"] {{ --accent: #059669; }}
    .pomo[data-phase="done"] {{ --accent: #6b7280; }}
    html[data-theme="dark"] body {{ color: #e5e7eb; }}
    html[data-theme="dark"] .dial .track {{ stroke: #374151; }}
    html[data-theme="dark"] .dial .time {{ color: #f9fafb; }}
    html[data-theme="dark"] .cycle {{ color: #6b7280; }}
    html[data-theme="dark"] .secondary {{ background: #1f2937; color: #e5e7eb; }}
    html[data-theme="dark"] .secondary:hover {{ background: #374151; }}
  </style>
</head>
<body>
  <div class="pomo" id="pomo" data-phase="work">
    <div class="phase" id="phase">{labels["focus"]}</div>
    <div class="cycle">{labels["cycle"]} <span id="cycle-num">1</span></div>
    <div class="dial">
      <svg viewBox="0 0 100 100">
        <circle class="track" cx="50" cy="50" r="44"></circle>
        <circle class="progress" id="progress"
                cx="50" cy="50" r="44"
                stroke-dasharray="276.46" stroke-dashoffset="0"></circle>
      </svg>
      <div class="time" id="time">{work_minutes:02d}:00</div>
    </div>
    <div class="controls">
      <button class="primary" id="toggle-btn">{labels["start"]}</button>
      <button class="secondary" id="reset-btn">{labels["reset"]}</button>
      <button class="secondary" id="skip-btn">{labels["skip"]}</button>
    </div>
  </div>
  <script>
    (function() {{
      var WORK_SEC = {work_seconds};
      var BREAK_SEC = {break_seconds};
      var CIRCUMFERENCE = 276.46;
      var LABELS = {labels_json};

      var phase = 'work';
      var remaining = WORK_SEC;
      var running = false;
      var cycleNum = 1;
      var timerId = null;

      var $pomo = document.getElementById('pomo');
      var $phase = document.getElementById('phase');
      var $cycle = document.getElementById('cycle-num');
      var $time = document.getElementById('time');
      var $progress = document.getElementById('progress');
      var $toggle = document.getElementById('toggle-btn');
      var $reset = document.getElementById('reset-btn');
      var $skip = document.getElementById('skip-btn');

      function totalSeconds() {{ return phase === 'work' ? WORK_SEC : BREAK_SEC; }}
      function formatTime(sec) {{
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return (m < 10 ? '0' + m : m) + ':' + (s < 10 ? '0' + s : s);
      }}
      function render() {{
        $time.textContent = formatTime(remaining);
        var pct = remaining / totalSeconds();
        $progress.setAttribute('stroke-dashoffset',
          (CIRCUMFERENCE * (1 - pct)).toFixed(2));
        $phase.textContent = phase === 'work' ? LABELS.focus :
                             phase === 'break' ? LABELS.break : LABELS.done;
        $pomo.setAttribute('data-phase', phase);
        $cycle.textContent = cycleNum;
        $toggle.textContent = running ? LABELS.pause : LABELS.start;
      }}
      function tick() {{
        if (!running) return;
        if (remaining > 0) {{ remaining -= 1; render(); }}
        if (remaining === 0) {{
          running = false;
          clearInterval(timerId);
          try {{
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.frequency.value = phase === 'work' ? 660 : 880;
            gain.gain.setValueAtTime(0.15, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.6);
            osc.start(); osc.stop(ctx.currentTime + 0.6);
          }} catch(e) {{}}
          if (phase === 'work') {{ phase = 'break'; remaining = BREAK_SEC; }}
          else {{ phase = 'work'; remaining = WORK_SEC; cycleNum += 1; }}
          render();
        }}
      }}
      function start() {{ if (running) return; running = true; timerId = setInterval(tick, 1000); render(); }}
      function pause() {{ running = false; if (timerId) clearInterval(timerId); render(); }}
      function reset() {{ pause(); phase = 'work'; remaining = WORK_SEC; cycleNum = 1; render(); }}
      function skip() {{
        pause();
        if (phase === 'work') {{ phase = 'break'; remaining = BREAK_SEC; }}
        else {{ phase = 'work'; remaining = WORK_SEC; cycleNum += 1; }}
        render();
      }}
      $toggle.addEventListener('click', function() {{ running ? pause() : start(); }});
      $reset.addEventListener('click', reset);
      $skip.addEventListener('click', skip);
      render();
    }})();
  </script>
</body>
</html>"""


def main() -> None:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}

    params = payload.get("parameters") or {}
    lang = _lang_code(params.get("_lang", "en"))

    try:
        work_minutes = int(params.get("work_minutes") or 25)
    except (TypeError, ValueError):
        work_minutes = 25
    try:
        break_minutes = int(params.get("break_minutes") or 5)
    except (TypeError, ValueError):
        break_minutes = 5

    work_minutes = max(1, min(work_minutes, 120))
    break_minutes = max(1, min(break_minutes, 60))

    html = _build_html(
        work_minutes=work_minutes,
        break_minutes=break_minutes,
        lang=lang,
        work_seconds=work_minutes * 60,
        break_seconds=break_minutes * 60,
    )

    caption = _LABELS[lang]["caption"].format(w=work_minutes, b=break_minutes)

    print(
        json.dumps(
            {
                "text": caption,
                "frame": {
                    "html": html,
                    "title": f"{_LABELS[lang]['title']} · {work_minutes}/{break_minutes}",
                    "aspect_ratio": 0.9,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
