"""Render a multi-day weather dashboard as an inline HTML frame.

Reads ``forecasts`` (list of per-day forecast dicts) and ``location`` from
stdin parameters. Both come from ``$steps.get_weather.*`` resolution in the
deterministic plan template of the ``weather-dashboard`` skill. The
runtime context ``_lang`` is auto-injected by ``run_skill_script`` so the
day labels and caption follow the user's locale.

Icon / gradient mapping follows the OpenWeatherMap condition groups:
    https://openweathermap.org/weather-conditions
Keywords match both English standard labels and French translations
(the tool is called with lang=fr by default when the user speaks French).

Theming: CSS uses ``html[data-theme="dark"]`` selectors; the runtime
snippet injected by ``output_builder`` applies the attribute in sync with
the host app theme.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime


# OpenWeatherMap condition groups → (emoji, gradient, accent).
# Order matters: more specific rules FIRST (thunder > rain, shower > rain).
_WEATHER_STYLES: list[tuple[tuple[str, ...], str, str, str]] = [
    # Group 2xx — Thunderstorm
    (("thunder", "orage"), "⛈️",
     "linear-gradient(135deg, #4c1d95 0%, #1e1b4b 100%)", "#c4b5fd"),
    # Group 6xx — Snow (incl. sleet)
    (("snow", "neige", "sleet", "blizzard"), "❄️",
     "linear-gradient(135deg, #e0f2fe 0%, #bae6fd 60%, #7dd3fc 100%)", "#0369a1"),
    # Group 3xx — Drizzle / shower
    (("drizzle", "bruine"), "🌦️",
     "linear-gradient(135deg, #94a3b8 0%, #64748b 100%)", "#cbd5e1"),
    (("shower",), "🌦️",
     "linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%)", "#dbeafe"),
    # Group 5xx — Rain
    (("rain", "pluie", "verglaçante", "freezing"), "🌧️",
     "linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)", "#bfdbfe"),
    # Group 7xx — Atmosphere
    (("fog", "brouillard", "mist", "brume", "haze", "smoke", "fumée",
      "dust", "poussière", "sand", "sable", "ash", "cendres",
      "squall", "rafale", "tornado", "tornade"), "🌫️",
     "linear-gradient(135deg, #94a3b8 0%, #cbd5e1 100%)", "#475569"),
    # Group 80x — Clouds (overcast/broken before partly/few)
    (("overcast", "couvert", "broken", "très nuageux"), "☁️",
     "linear-gradient(135deg, #9ca3af 0%, #6b7280 100%)", "#e5e7eb"),
    (("partly", "partiellement", "scattered", "peu nuageux", "few clouds", "quelques"), "⛅",
     "linear-gradient(135deg, #fbbf24 0%, #60a5fa 100%)", "#fffbeb"),
    # Group 800 — Clear
    (("clear", "dégagé", "ciel clair", "sunny", "sun", "soleil"), "☀️",
     "linear-gradient(135deg, #fbbf24 0%, #f97316 100%)", "#fef3c7"),
    # Fallback cloud
    (("cloud", "nuage"), "☁️",
     "linear-gradient(135deg, #cbd5e1 0%, #94a3b8 100%)", "#f1f5f9"),
]
_DEFAULT_STYLE = ("🌡️", "linear-gradient(135deg, #64748b 0%, #475569 100%)", "#e5e7eb")

# Locale tables for weekday / month names. We don't rely on
# ``locale.setlocale`` because the locales ``fr_FR.UTF-8`` / ``de_DE.UTF-8``
# etc. may not be installed in minimal container images, in which case
# ``strftime`` silently falls back to English. These tables guarantee
# a deterministic localized output regardless of the host's installed
# locales. Index mapping: ``datetime.weekday()`` → 0=Monday … 6=Sunday.
_WEEKDAYS_LONG: dict[str, list[str]] = {
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    "it": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"],
    "zh": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
}
_WEEKDAYS_SHORT: dict[str, list[str]] = {
    "fr": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."],
    "de": ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."],
    "it": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
    "zh": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
}
# 1-indexed so MONTHS_LONG[lang][1] = January. Index 0 = empty slot.
_MONTHS_LONG: dict[str, list[str]] = {
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
    "zh": ["", "1月", "2月", "3月", "4月", "5月", "6月", "7月",
           "8月", "9月", "10月", "11月", "12月"],
}
_MONTHS_SHORT: dict[str, list[str]] = {
    "fr": ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
           "août", "sept.", "oct.", "nov.", "déc."],
    "en": ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
           "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es": ["", "ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.",
           "ago.", "sep.", "oct.", "nov.", "dic."],
    "de": ["", "Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli",
           "Aug.", "Sep.", "Okt.", "Nov.", "Dez."],
    "it": ["", "gen.", "feb.", "mar.", "apr.", "mag.", "giu.", "lug.",
           "ago.", "set.", "ott.", "nov.", "dic."],
    "zh": ["", "1月", "2月", "3月", "4月", "5月", "6月", "7月",
           "8月", "9月", "10月", "11月", "12月"],
}
_CAPTION_LOCATION: dict[str, str] = {
    "fr": "Météo pour {loc} — {n} jours.",
    "en": "Weather for {loc} — {n} days.",
    "es": "Clima para {loc} — {n} días.",
    "de": "Wetter für {loc} — {n} Tage.",
    "it": "Meteo per {loc} — {n} giorni.",
    "zh": "{loc} 的天气 — {n} 天。",
}
_CAPTION_NOLOC: dict[str, str] = {
    "fr": "Prévisions météo — {n} jours.",
    "en": "Weather forecast — {n} days.",
    "es": "Pronóstico del tiempo — {n} días.",
    "de": "Wettervorhersage — {n} Tage.",
    "it": "Previsioni meteo — {n} giorni.",
    "zh": "天气预报 — {n} 天。",
}
_TITLE_WORD: dict[str, str] = {
    "fr": "Météo",
    "en": "Weather",
    "es": "Clima",
    "de": "Wetter",
    "it": "Meteo",
    "zh": "天气",
}


def _lang_code(lang: str) -> str:
    base = (lang or "en").lower().split("-")[0]
    return base if base in _CAPTION_LOCATION else "en"


def _pick_style(description: str | None) -> tuple[str, str, str]:
    if not description:
        return _DEFAULT_STYLE
    lower = description.lower()
    for keywords, emoji, gradient, accent in _WEATHER_STYLES:
        for kw in keywords:
            if kw in lower:
                return emoji, gradient, accent
    return _DEFAULT_STYLE


def _weekday_label(date_iso: str | None, lang: str, *, short: bool = True) -> str:
    """Return a locale-aware ``<weekday> <day> <month>`` label.

    Built from translation tables (``_WEEKDAYS_*`` / ``_MONTHS_*``) to
    avoid the ``setlocale`` pitfall: minimal container images often lack
    the ``fr_FR.UTF-8`` / etc. locale data, so ``strftime`` silently
    reverts to English. Explicit tables guarantee correct output.
    """
    if not date_iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(date_iso))
    except ValueError:
        return str(date_iso)[:10]
    wd_tbl = (_WEEKDAYS_SHORT if short else _WEEKDAYS_LONG)[lang]
    mo_tbl = (_MONTHS_SHORT if short else _MONTHS_LONG)[lang]
    weekday = wd_tbl[dt.weekday()]
    month = mo_tbl[dt.month]
    if lang == "zh":
        # Chinese convention: <month><day> <weekday>
        return f"{month}{dt.day}日 {weekday}"
    return f"{weekday} {dt.day} {month}"


def _format_temp(value: object) -> str:
    if value in (None, "", "N/A"):
        return "—"
    return str(value)


def _render_hero(day: dict, lang: str) -> str:
    emoji, gradient, accent = _pick_style(day.get("description"))
    label = _weekday_label(day.get("date"), lang, short=False)
    temp_min = _format_temp(day.get("temp_min"))
    temp_max = _format_temp(day.get("temp_max"))
    temp_avg = _format_temp(day.get("temp_avg") or day.get("temp_day"))
    desc = day.get("description") or "—"
    humidity = day.get("humidity")
    wind = day.get("wind_speed")

    pills: list[str] = []
    if humidity not in (None, "", "N/A"):
        pills.append(f'<span class="pill">💧 {humidity}</span>')
    if wind not in (None, "", "N/A"):
        pills.append(f'<span class="pill">💨 {wind}</span>')
    pills_html = "".join(pills)

    return f"""
    <div class="hero" style="background:{gradient}; --accent:{accent};">
      <div class="hero-top">
        <div class="hero-label">{label}</div>
        <div class="hero-desc">{desc}</div>
      </div>
      <div class="hero-main">
        <div class="hero-icon">{emoji}</div>
        <div class="hero-temp">
          <div class="hero-avg">{temp_avg}</div>
          <div class="hero-range">
            <span class="tmax">↑ {temp_max}</span>
            <span class="tmin">↓ {temp_min}</span>
          </div>
        </div>
      </div>
      <div class="hero-pills">{pills_html}</div>
    </div>
    """


def _render_compact_card(day: dict, lang: str) -> str:
    emoji, gradient, _accent = _pick_style(day.get("description"))
    label = _weekday_label(day.get("date"), lang)
    temp_min = _format_temp(day.get("temp_min"))
    temp_max = _format_temp(day.get("temp_max"))

    return f"""
    <div class="card" style="background:{gradient};">
      <div class="card-day">{label}</div>
      <div class="card-icon">{emoji}</div>
      <div class="card-temps">
        <span class="tmax">{temp_max}</span>
        <span class="tsep">/</span>
        <span class="tmin">{temp_min}</span>
      </div>
    </div>
    """


def _build_html(location_display: str, forecasts: list[dict], lang: str) -> str:
    if not forecasts:
        return "<html><body><p>No forecast data available.</p></body></html>"

    hero_html = _render_hero(forecasts[0], lang)
    upcoming = forecasts[1:]
    upcoming_html = "".join(_render_compact_card(d, lang) for d in upcoming)
    upcoming_section = f'<div class="grid">{upcoming_html}</div>' if upcoming_html else ""

    title_word = _TITLE_WORD[lang]
    title = f"{title_word} · {location_display}" if location_display else title_word

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: transparent;
      color: #1f2937;
      padding: 20px 16px 24px;
    }}
    .dash {{ max-width: 900px; margin: 0 auto; }}
    .title {{
      display: flex;
      align-items: baseline;
      gap: 8px;
      font-size: 1rem;
      font-weight: 600;
      color: #374151;
      margin-bottom: 14px;
      padding: 0 2px;
    }}
    .title .icon {{ font-size: 1.1rem; }}
    .hero {{
      border-radius: 18px;
      padding: 22px 24px;
      color: white;
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.08);
      margin-bottom: 14px;
      position: relative;
      overflow: hidden;
      animation: card-in 320ms ease both;
    }}
    .hero::after {{
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at top right, rgba(255, 255, 255, 0.15), transparent 60%);
      pointer-events: none;
    }}
    .hero-top {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      position: relative;
    }}
    .hero-label {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      opacity: 0.85;
      font-weight: 600;
    }}
    .hero-desc {{
      font-size: 0.9rem;
      text-transform: capitalize;
      opacity: 0.95;
      text-align: right;
    }}
    .hero-main {{
      display: flex;
      align-items: center;
      gap: 20px;
      margin: 10px 0 12px;
      position: relative;
    }}
    .hero-icon {{ font-size: 4.5rem; line-height: 1; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.2)); }}
    .hero-temp {{ display: flex; flex-direction: column; gap: 4px; }}
    .hero-avg {{ font-size: 3rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1; }}
    .hero-range {{ display: flex; gap: 10px; font-size: 0.85rem; font-weight: 600; opacity: 0.95; }}
    .hero-range .tmin {{ opacity: 0.85; }}
    .hero-pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; position: relative; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 10px;
      background: rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 500;
      backdrop-filter: blur(4px);
      -webkit-backdrop-filter: blur(4px);
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }}
    .card {{
      border-radius: 14px;
      padding: 14px 10px 12px;
      color: white;
      text-align: center;
      box-shadow: 0 3px 10px rgba(0, 0, 0, 0.06);
      transition: transform 140ms ease, box-shadow 140ms ease;
      animation: card-in 320ms ease both;
      position: relative;
      overflow: hidden;
    }}
    .card::after {{
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at top left, rgba(255, 255, 255, 0.18), transparent 55%);
      pointer-events: none;
    }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12); }}
    .card-day {{
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      opacity: 0.9;
      margin-bottom: 6px;
      position: relative;
    }}
    .card-icon {{ font-size: 2.3rem; line-height: 1; margin: 4px 0 6px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.18)); position: relative; }}
    .card-temps {{ font-size: 0.92rem; font-weight: 700; letter-spacing: -0.01em; position: relative; }}
    .card-temps .tmax {{ opacity: 1; }}
    .card-temps .tsep {{ opacity: 0.6; margin: 0 3px; }}
    .card-temps .tmin {{ opacity: 0.8; }}
    @keyframes card-in {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    html[data-theme="dark"] body {{ color: #e5e7eb; }}
    html[data-theme="dark"] .title {{ color: #f1f5f9; }}
  </style>
</head>
<body>
  <div class="dash">
    <div class="title"><span class="icon">⛅</span><span>{title}</span></div>
    {hero_html}
    {upcoming_section}
  </div>
</body>
</html>"""


def main() -> None:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"text": "Invalid payload.", "error": "stdin is not valid JSON"}))
        return

    params = payload.get("parameters") or {}
    lang = _lang_code(params.get("_lang", "en"))
    forecasts = params.get("forecasts") or []
    location = params.get("location") or {}
    location_display = (
        location.get("display")
        if isinstance(location, dict)
        else (location if isinstance(location, str) else "")
    ) or ""

    if not isinstance(forecasts, list) or not forecasts:
        print(
            json.dumps(
                {
                    "text": "No forecast data available.",
                    "error": "Missing or empty 'forecasts' parameter",
                }
            )
        )
        return

    html = _build_html(location_display, forecasts, lang)
    n = len(forecasts)
    caption_template = _CAPTION_LOCATION[lang] if location_display else _CAPTION_NOLOC[lang]
    caption = caption_template.format(loc=location_display, n=n)

    print(
        json.dumps(
            {
                "text": caption,
                "frame": {
                    "html": html,
                    "title": f"{_TITLE_WORD[lang]} · {location_display}"
                    if location_display
                    else f"{_TITLE_WORD[lang]}",
                    "aspect_ratio": 1.6,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
