"""Render an HTML calendar grid for the current month.

Reads optional ``month`` (1-12) and ``year`` (YYYY) from ``parameters`` on
stdin. Runtime context ``_lang`` is auto-injected by ``run_skill_script``
so the labels (month names, weekdays, "X days") follow the user's locale.

Emits a ``SkillScriptOutput`` JSON on stdout with a ``frame.html``
containing the inline calendar grid.

Theming:
    The CSS uses ``[data-theme="dark"]`` selectors. The runtime snippet
    injected by ``output_builder`` applies this attribute on the iframe
    root in sync with the host app theme (``prefers-color-scheme``
    fallback, ``ui/theme-changed`` override via postMessage).
"""

from __future__ import annotations

import calendar
import json
import sys
from datetime import date


# Localized labels. Keys use LIA's 6 supported locales. Unknown locales
# fall back to English. Month names are 1-indexed (index 0 left blank so
# ``MONTH_NAMES[locale][1] == January``).
_WEEKDAY_LABELS: dict[str, list[str]] = {
    "fr": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    "it": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"],
    "zh": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
}
_MONTH_NAMES: dict[str, list[str]] = {
    "fr": ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "de": ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "it": ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    "zh": ["", "一月", "二月", "三月", "四月", "五月", "六月", "七月",
           "八月", "九月", "十月", "十一月", "十二月"],
}
_DAYS_LABEL: dict[str, str] = {
    "fr": "jours",
    "en": "days",
    "es": "días",
    "de": "Tage",
    "it": "giorni",
    "zh": "天",
}
_CAPTION_HERE_IS: dict[str, str] = {
    "fr": "Voici {month} {year}.",
    "en": "Here is {month} {year}.",
    "es": "Aquí tiene {month} {year}.",
    "de": "Hier ist {month} {year}.",
    "it": "Ecco {month} {year}.",
    "zh": "这是 {year} 年 {month}。",
}


def _lang_code(lang: str) -> str:
    """Normalize a language code to our supported keys (fallback 'en')."""
    base = (lang or "en").lower().split("-")[0]
    return base if base in _WEEKDAY_LABELS else "en"


def _build_html(year: int, month: int, today: date, lang: str) -> str:
    """Return the inline HTML of the month calendar grid."""
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    month_label = f"{_MONTH_NAMES[lang][month]} {year}"

    header_cells = "".join(
        f'<div class="dow{" weekend" if i >= 5 else ""}">{label}</div>'
        for i, label in enumerate(_WEEKDAY_LABELS[lang])
    )

    day_cells: list[str] = []
    for week in weeks:
        for weekday_idx, day in enumerate(week):
            if day == 0:
                day_cells.append('<div class="cell blank" aria-hidden="true"></div>')
                continue
            classes = ["cell"]
            if weekday_idx >= 5:
                classes.append("weekend")
            if year == today.year and month == today.month and day == today.day:
                classes.append("today")
            day_cells.append(
                f'<div class="{" ".join(classes)}"><span>{day}</span></div>'
            )

    days_in_month = calendar.monthrange(year, month)[1]
    days_label = _DAYS_LABEL[lang]

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{month_label}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: transparent;
      color: #1f2937;
      padding: 20px 16px 24px;
    }}
    .cal {{ max-width: 640px; margin: 0 auto; }}
    .cal-header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: 16px;
      padding: 0 4px;
    }}
    .cal-title {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      font-size: 1.35rem;
      font-weight: 700;
      color: #111827;
      letter-spacing: -0.015em;
      text-transform: capitalize;
    }}
    .cal-title .icon {{ font-size: 1.25rem; }}
    .cal-count {{ font-size: 0.8rem; color: #9ca3af; font-weight: 500; }}
    .grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; }}
    .dow {{
      text-align: center;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      color: #9ca3af;
      letter-spacing: 0.08em;
      padding: 4px 0 8px;
    }}
    .dow.weekend {{ color: #d1d5db; }}
    .cell {{
      aspect-ratio: 1 / 1;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f9fafb;
      border-radius: 10px;
      font-size: 0.95rem;
      color: #374151;
      transition: transform 120ms ease, background 120ms ease, box-shadow 120ms ease;
      animation: cell-in 240ms ease both;
    }}
    .cell span {{ position: relative; }}
    .cell:hover {{
      transform: translateY(-1px);
      background: #eef2ff;
      box-shadow: 0 2px 6px rgba(79, 70, 229, 0.08);
    }}
    .cell.weekend {{ background: #f3f4f6; color: #6b7280; }}
    .cell.weekend:hover {{ background: #e5e7eb; }}
    .cell.blank {{ background: transparent; pointer-events: none; animation: none; }}
    .cell.today {{
      background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
      color: white;
      font-weight: 700;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
      position: relative;
    }}
    .cell.today::after {{
      content: '';
      position: absolute;
      inset: 6px;
      border-radius: 8px;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.35) inset;
      pointer-events: none;
    }}
    .cell.today:hover {{
      background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%);
      transform: translateY(-2px);
    }}
    @keyframes cell-in {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    html[data-theme="dark"] body {{ color: #e5e7eb; }}
    html[data-theme="dark"] .cal-title {{ color: #f9fafb; }}
    html[data-theme="dark"] .cal-count {{ color: #6b7280; }}
    html[data-theme="dark"] .dow {{ color: #6b7280; }}
    html[data-theme="dark"] .dow.weekend {{ color: #4b5563; }}
    html[data-theme="dark"] .cell {{ background: #1f2937; color: #e5e7eb; }}
    html[data-theme="dark"] .cell:hover {{ background: #374151; }}
    html[data-theme="dark"] .cell.weekend {{ background: #111827; color: #9ca3af; }}
    html[data-theme="dark"] .cell.weekend:hover {{ background: #1f2937; }}
    html[data-theme="dark"] .cell.today {{
      background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.45);
    }}
  </style>
</head>
<body>
  <div class="cal">
    <div class="cal-header">
      <div class="cal-title">
        <span class="icon">📅</span>
        <span>{month_label}</span>
      </div>
      <div class="cal-count">{days_in_month} {days_label}</div>
    </div>
    <div class="grid">
      {header_cells}
      {"".join(day_cells)}
    </div>
  </div>
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
    today = date.today()

    try:
        month = int(params.get("month") or today.month)
    except (TypeError, ValueError):
        month = today.month
    try:
        year = int(params.get("year") or today.year)
    except (TypeError, ValueError):
        year = today.year

    if not (1 <= month <= 12):
        month = today.month
    if not (1900 <= year <= 2100):
        year = today.year

    html = _build_html(year, month, today, lang)
    month_name = _MONTH_NAMES[lang][month]
    caption = _CAPTION_HERE_IS[lang].format(month=month_name, year=year)

    print(
        json.dumps(
            {
                "text": caption,
                "frame": {
                    "html": html,
                    "title": f"{month_name.capitalize()} {year}",
                    "aspect_ratio": 1.1,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
