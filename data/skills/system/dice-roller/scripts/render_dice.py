"""Roll dice and render an interactive HTML frame.

Parses the ``notation`` parameter from stdin (default ``1d6``) in the
standard RPG shorthand ``NdS[+/-M][kh/kl K]`` and emits a
``SkillScriptOutput`` JSON on stdout with:

    - ``text`` — caption with the initial total (localized via ``_lang``).
    - ``frame.html`` — a self-contained interactive frame that:
        * Rolls the dice client-side via ``crypto.getRandomValues`` the
          first time it loads (deterministic output == 0 when the user
          just wants the frame) and every time the user clicks "Re-roll".
        * Plays an entrance animation on every roll (staggered per die),
          highlights critical success / failure for d20+, dims dropped
          dice when ``kh``/``kl`` is specified.
        * Shows the detailed breakdown and the grand total.

Design note:
    The first-roll values baked into the server-rendered HTML come from a
    ``secrets.SystemRandom()`` draw so the *caption* (seen by the LLM)
    reflects a realistic outcome. The frame's client JS overrides the
    displayed roll on DOMContentLoaded so the user sees a fresh tirage
    with animation — and can re-roll without round-tripping to the API.
"""

from __future__ import annotations

import html
import json
import re
import secrets
import sys
from typing import Any


_VALID_SIZES = (4, 6, 8, 10, 12, 20, 100)
_MAX_DICE = 20
# Strict pattern — exactly one notation as the whole string.
_NOTATION_RE = re.compile(
    r"^\s*(\d*)\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*(?:k(h|l)\s*(\d+))?\s*$",
    re.IGNORECASE,
)
# Lenient fallback — extracts the first ``NdS[+/-M][khK|klK]`` found
# anywhere in a larger string (e.g. a full user sentence like
# "lance 2d6 pour moi"). Uses word boundaries to avoid false positives
# inside identifiers.
_NOTATION_FIND_RE = re.compile(
    r"\b(\d*)d(\d+)(\s*[+-]\s*\d+)?(?:k(h|l)(\d+))?\b",
    re.IGNORECASE,
)

# Localized captions and button labels.
_LABELS: dict[str, dict[str, str]] = {
    "fr": {"caption": "Jet de {n} : {t}.", "reroll": "🎲 Relancer", "total": "Total"},
    "en": {"caption": "Rolled {n}: {t}.", "reroll": "🎲 Re-roll", "total": "Total"},
    "es": {"caption": "Tirada de {n}: {t}.", "reroll": "🎲 Relanzar", "total": "Total"},
    "de": {"caption": "Wurf {n}: {t}.", "reroll": "🎲 Neu würfeln", "total": "Gesamt"},
    "it": {"caption": "Lancio {n}: {t}.", "reroll": "🎲 Rilancia", "total": "Totale"},
    "zh": {"caption": "{n} 的结果:{t}。", "reroll": "🎲 重新投掷", "total": "总计"},
}


def _lang_code(lang: str) -> str:
    base = (lang or "en").lower().split("-")[0]
    return base if base in _LABELS else "en"


def _parse_notation(notation: str) -> dict[str, Any] | None:
    """Parse a dice notation string. Tolerates free-form queries.

    First tries a strict match on the whole string. If that fails, scans
    the string for the first valid ``NdS[+/-M][khK|klK]`` occurrence —
    this lets the skill still work when the LLM passes the full user
    sentence (``"lance 2d6 pour moi"``) rather than the clean notation.
    """
    candidates: list[tuple[str | None, str, str | None, str | None, str | None]] = []

    strict = _NOTATION_RE.match(notation)
    if strict:
        candidates.append(strict.groups())
    else:
        for m in _NOTATION_FIND_RE.finditer(notation):
            candidates.append(m.groups())

    for count_s, size_s, mod_s, keep_side, keep_n_s in candidates:
        try:
            size = int(size_s)
        except (TypeError, ValueError):
            continue
        if size not in _VALID_SIZES:
            continue
        count = int(count_s) if count_s and count_s.strip() else 1
        if count < 1 or count > _MAX_DICE:
            continue
        modifier = (
            int(mod_s.replace(" ", "")) if mod_s and mod_s.strip() else 0
        )
        keep: tuple[str, int] | None = None
        if keep_side and keep_n_s:
            keep_n = int(keep_n_s)
            if 1 <= keep_n <= count:
                keep = (keep_side.lower(), keep_n)
        return {"count": count, "size": size, "modifier": modifier, "keep": keep}
    return None


def _roll_initial(count: int, size: int) -> list[int]:
    """Initial draw for the server-rendered caption. CSPRNG for fairness."""
    rng = secrets.SystemRandom()
    return [rng.randint(1, size) for _ in range(count)]


def _apply_keep(rolls: list[int], keep: tuple[str, int] | None) -> set[int]:
    if not keep:
        return set(range(len(rolls)))
    side, n = keep
    indexed = sorted(enumerate(rolls), key=lambda p: p[1], reverse=(side == "h"))
    return {idx for idx, _ in indexed[:n]}


def _build_html(parsed: dict[str, Any], initial_rolls: list[int], lang: str) -> str:
    count = parsed["count"]
    size = parsed["size"]
    modifier = parsed["modifier"]
    keep = parsed["keep"]
    labels = _LABELS[lang]

    # Build the notation display (kept for the header).
    notation_display = f"{count}d{size}"
    if keep:
        notation_display += f"k{keep[0]}{keep[1]}"
    if modifier > 0:
        notation_display += f"+{modifier}"
    elif modifier < 0:
        notation_display += f"{modifier}"

    # Serialize the roll config so the inline JS can re-roll without
    # another backend call. ``keep`` is encoded as ``[side, n]`` or null.
    roll_config = {
        "count": count,
        "size": size,
        "modifier": modifier,
        "keep": list(keep) if keep else None,
        "initialRolls": initial_rolls,
        "labels": {"total": labels["total"]},
    }
    config_json = json.dumps(roll_config, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dice · {html.escape(notation_display)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      color: #1f2937;
      padding: 24px 16px;
    }}
    .roll {{ max-width: 480px; margin: 0 auto; text-align: center; }}
    .notation {{
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #6b7280;
      margin-bottom: 14px;
    }}
    .dice {{
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 16px;
      min-height: 80px;
    }}
    .die {{
      width: 68px;
      height: 68px;
      border-radius: 14px;
      background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
      color: white;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
      font-weight: 700;
      position: relative;
      animation: die-in 420ms cubic-bezier(.2,.9,.3,1.2) both;
    }}
    .die .face {{ font-size: 1.6rem; line-height: 1; font-variant-numeric: tabular-nums; }}
    .die .sides {{
      font-size: 0.6rem;
      font-weight: 500;
      opacity: 0.75;
      margin-top: 4px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }}
    .die.crit {{
      background: linear-gradient(135deg, #10b981 0%, #059669 100%);
      box-shadow: 0 4px 14px rgba(16, 185, 129, 0.45);
    }}
    .die.fail {{
      background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%);
      box-shadow: 0 4px 14px rgba(239, 68, 68, 0.45);
    }}
    .die.dropped {{ opacity: 0.42; filter: grayscale(0.6); transform: scale(0.9); }}
    @keyframes die-in {{
      0%   {{ opacity: 0; transform: translateY(-26px) rotate(-45deg) scale(0.55); }}
      50%  {{ transform: translateY(6px) rotate(14deg) scale(1.08); opacity: 1; }}
      75%  {{ transform: translateY(-2px) rotate(-4deg) scale(0.98); }}
      100% {{ opacity: 1; transform: translateY(0) rotate(0) scale(1); }}
    }}
    .total {{
      font-size: 2.6rem;
      font-weight: 800;
      color: #111827;
      letter-spacing: -0.03em;
      line-height: 1;
      margin-bottom: 6px;
      font-variant-numeric: tabular-nums;
    }}
    .breakdown {{
      font-size: 0.85rem;
      color: #6b7280;
      font-variant-numeric: tabular-nums;
      margin-bottom: 18px;
    }}
    .reroll {{
      border: none;
      border-radius: 999px;
      padding: 10px 22px;
      font-size: 0.95rem;
      font-weight: 700;
      cursor: pointer;
      background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
      color: white;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
      transition: transform 140ms ease, box-shadow 140ms ease, filter 120ms ease;
      font-family: inherit;
    }}
    .reroll:hover {{ transform: translateY(-1px); filter: brightness(1.06); }}
    .reroll:active {{ transform: translateY(1px); }}
    html[data-theme="dark"] body {{ color: #e5e7eb; }}
    html[data-theme="dark"] .notation {{ color: #9ca3af; }}
    html[data-theme="dark"] .total {{ color: #f9fafb; }}
    html[data-theme="dark"] .breakdown {{ color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="roll">
    <div class="notation">🎲 {html.escape(notation_display)}</div>
    <div class="dice" id="dice"></div>
    <div class="total" id="total">—</div>
    <div class="breakdown" id="breakdown">—</div>
    <button class="reroll" id="reroll-btn">{html.escape(labels["reroll"])}</button>
  </div>
  <script>
    (function() {{
      var CFG = {config_json};

      // Cryptographically strong integer in [1, size].
      function rollOne(size) {{
        var buf = new Uint32Array(1);
        // Rejection sampling to avoid modulo bias.
        var limit = Math.floor(0xffffffff / size) * size;
        var n;
        do {{
          crypto.getRandomValues(buf);
          n = buf[0];
        }} while (n >= limit);
        return (n % size) + 1;
      }}

      function rollAll() {{
        var rolls = [];
        for (var i = 0; i < CFG.count; i++) rolls.push(rollOne(CFG.size));
        return rolls;
      }}

      function applyKeep(rolls) {{
        if (!CFG.keep) {{
          var all = new Set();
          for (var i = 0; i < rolls.length; i++) all.add(i);
          return all;
        }}
        var side = CFG.keep[0];
        var n = CFG.keep[1];
        var idx = rolls.map(function(v, i) {{ return [i, v]; }});
        idx.sort(function(a, b) {{
          return side === 'h' ? b[1] - a[1] : a[1] - b[1];
        }});
        var kept = new Set();
        for (var j = 0; j < n; j++) kept.add(idx[j][0]);
        return kept;
      }}

      var $dice = document.getElementById('dice');
      var $total = document.getElementById('total');
      var $breakdown = document.getElementById('breakdown');
      var $btn = document.getElementById('reroll-btn');

      function render(rolls) {{
        var kept = applyKeep(rolls);
        // Clear and re-append to restart animations on each roll.
        $dice.innerHTML = '';
        for (var i = 0; i < rolls.length; i++) {{
          var v = rolls[i];
          var isKept = kept.has(i);
          var isCrit = v === CFG.size;
          var isFail = v === 1 && CFG.size >= 20;
          var cls = ['die', 'd' + CFG.size];
          if (!isKept) cls.push('dropped');
          if (isCrit) cls.push('crit');
          if (isFail) cls.push('fail');
          var el = document.createElement('div');
          el.className = cls.join(' ');
          el.style.animationDelay = (i * 80) + 'ms';
          var face = document.createElement('span');
          face.className = 'face';
          face.textContent = String(v);
          var sides = document.createElement('span');
          sides.className = 'sides';
          sides.textContent = 'd' + CFG.size;
          el.appendChild(face);
          el.appendChild(sides);
          $dice.appendChild(el);
        }}
        // Build breakdown + total.
        var keptVals = [];
        for (var k = 0; k < rolls.length; k++) if (kept.has(k)) keptVals.push(rolls[k]);
        var sum = keptVals.reduce(function(a, b) {{ return a + b; }}, 0);
        var grand = sum + CFG.modifier;
        var parts = keptVals.join(' + ') || '0';
        var modStr = CFG.modifier > 0 ? ' + ' + CFG.modifier :
                     CFG.modifier < 0 ? ' − ' + Math.abs(CFG.modifier) : '';
        $total.textContent = String(grand);
        $breakdown.textContent = parts + modStr + ' = ' + grand;
      }}

      $btn.addEventListener('click', function() {{ render(rollAll()); }});

      // Initial render: use the server-baked roll to keep parity with the
      // LLM-visible caption, then immediately trigger the animation.
      render(CFG.initialRolls);
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
    notation = params.get("notation") or "1d6"
    if not isinstance(notation, str):
        notation = "1d6"

    parsed = _parse_notation(notation)
    if parsed is None:
        print(
            json.dumps(
                {
                    "text": f"Invalid dice notation: '{notation}'. Try '1d6', '2d20', '3d6+2'.",
                    "error": "INVALID_NOTATION",
                }
            )
        )
        return

    initial_rolls = _roll_initial(parsed["count"], parsed["size"])
    kept = _apply_keep(initial_rolls, parsed["keep"])
    total = sum(v for i, v in enumerate(initial_rolls) if i in kept) + parsed["modifier"]

    # Canonical notation rebuilt from parsed parts so the caption stays
    # clean even when the caller passed a full sentence (e.g. "lance 2d6").
    clean_notation = f"{parsed['count']}d{parsed['size']}"
    if parsed["keep"]:
        clean_notation += f"k{parsed['keep'][0]}{parsed['keep'][1]}"
    if parsed["modifier"] > 0:
        clean_notation += f"+{parsed['modifier']}"
    elif parsed["modifier"] < 0:
        clean_notation += f"{parsed['modifier']}"

    lang = _lang_code(params.get("_lang", "en"))
    html_out = _build_html(parsed, initial_rolls, lang)
    caption = _LABELS[lang]["caption"].format(n=clean_notation, t=total)

    print(
        json.dumps(
            {
                "text": caption,
                "frame": {
                    "html": html_out,
                    "title": f"🎲 {notation}",
                    "aspect_ratio": 1.4,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
