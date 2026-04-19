"""Render a self-contained interactive unit converter as an HTML frame.

Reads optional ``_lang`` (auto-injected by ``run_skill_script``). Emits a
``SkillScriptOutput`` JSON on stdout with a ``frame.html`` containing a
small JavaScript application that converts between units across five
categories (temperature, length, weight, volume, speed). All conversion
factors and localized labels are bundled inline.

Theming: CSS uses ``html[data-theme="dark"]`` selectors synced with the
LIA app theme via the runtime snippet in ``output_builder``.
"""

from __future__ import annotations

import json
import sys


_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "title": "🧮 Convertisseur d'unités",
        "from": "De",
        "to": "Vers",
        "swap": "Inverser",
        "temperature": "🌡️ Température",
        "length": "📏 Longueur",
        "weight": "⚖️ Poids",
        "volume": "🧪 Volume",
        "speed": "💨 Vitesse",
        "caption": "Convertisseur d'unités prêt.",
    },
    "en": {
        "title": "🧮 Unit converter",
        "from": "From",
        "to": "To",
        "swap": "Swap",
        "temperature": "🌡️ Temperature",
        "length": "📏 Length",
        "weight": "⚖️ Weight",
        "volume": "🧪 Volume",
        "speed": "💨 Speed",
        "caption": "Unit converter ready.",
    },
    "es": {
        "title": "🧮 Conversor de unidades",
        "from": "De",
        "to": "A",
        "swap": "Invertir",
        "temperature": "🌡️ Temperatura",
        "length": "📏 Longitud",
        "weight": "⚖️ Peso",
        "volume": "🧪 Volumen",
        "speed": "💨 Velocidad",
        "caption": "Conversor de unidades listo.",
    },
    "de": {
        "title": "🧮 Einheiten-Umrechner",
        "from": "Von",
        "to": "Nach",
        "swap": "Tauschen",
        "temperature": "🌡️ Temperatur",
        "length": "📏 Länge",
        "weight": "⚖️ Gewicht",
        "volume": "🧪 Volumen",
        "speed": "💨 Geschwindigkeit",
        "caption": "Einheiten-Umrechner bereit.",
    },
    "it": {
        "title": "🧮 Convertitore di unità",
        "from": "Da",
        "to": "A",
        "swap": "Inverti",
        "temperature": "🌡️ Temperatura",
        "length": "📏 Lunghezza",
        "weight": "⚖️ Peso",
        "volume": "🧪 Volume",
        "speed": "💨 Velocità",
        "caption": "Convertitore di unità pronto.",
    },
    "zh": {
        "title": "🧮 单位转换器",
        "from": "从",
        "to": "到",
        "swap": "交换",
        "temperature": "🌡️ 温度",
        "length": "📏 长度",
        "weight": "⚖️ 重量",
        "volume": "🧪 体积",
        "speed": "💨 速度",
        "caption": "单位转换器已就绪。",
    },
}


def _lang_code(lang: str) -> str:
    base = (lang or "en").lower().split("-")[0]
    return base if base in _LABELS else "en"


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="__LANG__">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: transparent;
      color: #1f2937;
      padding: 20px 16px;
    }
    .conv {
      max-width: 440px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 6px 24px rgba(0, 0, 0, 0.06);
    }
    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1.1rem;
      font-weight: 700;
      color: #111827;
      margin-bottom: 16px;
      letter-spacing: -0.01em;
    }
    .cats {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }
    .cat-btn {
      flex: 1 1 auto;
      padding: 8px 12px;
      border: none;
      border-radius: 10px;
      background: #f3f4f6;
      color: #374151;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 120ms ease, color 120ms ease;
      font-family: inherit;
    }
    .cat-btn:hover { background: #e5e7eb; }
    .cat-btn.active {
      background: #4f46e5;
      color: white;
      box-shadow: 0 2px 6px rgba(79, 70, 229, 0.25);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 10px;
    }
    label {
      font-size: 0.72rem;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      display: block;
      margin-bottom: 4px;
    }
    input[type="number"], select {
      width: 100%;
      padding: 10px 12px;
      font-size: 1rem;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #f9fafb;
      color: #111827;
      font-family: inherit;
      font-variant-numeric: tabular-nums;
    }
    input[type="number"]:focus, select:focus {
      outline: none;
      border-color: #6366f1;
      background: white;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
    }
    .swap {
      display: flex;
      justify-content: center;
      margin: 4px 0;
    }
    .swap-btn {
      border: none;
      background: #f3f4f6;
      color: #374151;
      width: 34px;
      height: 34px;
      border-radius: 999px;
      font-size: 1.1rem;
      cursor: pointer;
      transition: transform 180ms ease, background 120ms ease;
      font-family: inherit;
    }
    .swap-btn:hover { background: #e5e7eb; transform: rotate(180deg); }
    .result {
      margin-top: 8px;
      padding: 12px 14px;
      background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%);
      border-radius: 10px;
      color: #312e81;
      font-weight: 600;
      text-align: center;
      font-size: 1rem;
      font-variant-numeric: tabular-nums;
    }
    html[data-theme="dark"] body { color: #e5e7eb; }
    html[data-theme="dark"] .conv { background: #1f2937; box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35); }
    html[data-theme="dark"] .title { color: #f9fafb; }
    html[data-theme="dark"] label { color: #9ca3af; }
    html[data-theme="dark"] .cat-btn { background: #374151; color: #e5e7eb; }
    html[data-theme="dark"] .cat-btn:hover { background: #4b5563; }
    html[data-theme="dark"] input[type="number"],
    html[data-theme="dark"] select { background: #111827; border-color: #374151; color: #f9fafb; }
    html[data-theme="dark"] input[type="number"]:focus,
    html[data-theme="dark"] select:focus { background: #1f2937; }
    html[data-theme="dark"] .swap-btn { background: #374151; color: #e5e7eb; }
    html[data-theme="dark"] .swap-btn:hover { background: #4b5563; }
    html[data-theme="dark"] .result { background: linear-gradient(135deg, #312e81 0%, #4c1d95 100%); color: #e0e7ff; }
  </style>
</head>
<body>
  <div class="conv">
    <div class="title">__LBL_TITLE__</div>
    <div class="cats" id="cats"></div>
    <div class="row">
      <div>
        <label>__LBL_FROM__</label>
        <input type="number" id="value-in" value="1" step="any">
        <select id="unit-from"></select>
      </div>
      <div class="swap">
        <button class="swap-btn" id="swap" title="__LBL_SWAP__">⇅</button>
      </div>
    </div>
    <div>
      <label>__LBL_TO__</label>
      <select id="unit-to"></select>
    </div>
    <div class="result" id="result">—</div>
  </div>
  <script>
    (function() {
      // Conversion factors: everything expressed relative to a base unit
      // within each category. fromBase(v) / toBase(v) handle non-linear
      // cases like temperature (°C is the base, °F and K use offsets).
      var CATEGORIES = {
        temperature: {
          label: '__LBL_CAT_TEMPERATURE__',
          base: 'c',
          units: {
            c:  { name: 'Celsius (°C)',    to: function(v){return v;},           from: function(v){return v;} },
            f:  { name: 'Fahrenheit (°F)', to: function(v){return (v-32)*5/9;},  from: function(v){return v*9/5+32;} },
            k:  { name: 'Kelvin (K)',      to: function(v){return v-273.15;},    from: function(v){return v+273.15;} }
          }
        },
        length: {
          label: '__LBL_CAT_LENGTH__',
          base: 'm',
          units: {
            mm: { name: 'Millimeter (mm)', factor: 0.001 },
            cm: { name: 'Centimeter (cm)', factor: 0.01 },
            m:  { name: 'Meter (m)',       factor: 1 },
            km: { name: 'Kilometer (km)',  factor: 1000 },
            in: { name: 'Inch (in)',       factor: 0.0254 },
            ft: { name: 'Foot (ft)',       factor: 0.3048 },
            yd: { name: 'Yard (yd)',       factor: 0.9144 },
            mi: { name: 'Mile (mi)',       factor: 1609.344 }
          }
        },
        weight: {
          label: '__LBL_CAT_WEIGHT__',
          base: 'kg',
          units: {
            mg: { name: 'Milligram (mg)', factor: 0.000001 },
            g:  { name: 'Gram (g)',       factor: 0.001 },
            kg: { name: 'Kilogram (kg)',  factor: 1 },
            t:  { name: 'Metric ton (t)', factor: 1000 },
            oz: { name: 'Ounce (oz)',     factor: 0.0283495 },
            lb: { name: 'Pound (lb)',     factor: 0.453592 },
            st: { name: 'Stone (st)',     factor: 6.35029 }
          }
        },
        volume: {
          label: '__LBL_CAT_VOLUME__',
          base: 'l',
          units: {
            ml:  { name: 'Milliliter (mL)',    factor: 0.001 },
            cl:  { name: 'Centiliter (cL)',    factor: 0.01 },
            dl:  { name: 'Deciliter (dL)',     factor: 0.1 },
            l:   { name: 'Liter (L)',          factor: 1 },
            m3:  { name: 'Cubic meter (m³)',   factor: 1000 },
            tsp: { name: 'Teaspoon (tsp, US)', factor: 0.00492892 },
            tbsp:{ name: 'Tablespoon (tbsp, US)', factor: 0.0147868 },
            cup: { name: 'Cup (cup, US)',      factor: 0.24 },
            pt:  { name: 'Pint (pt, US)',      factor: 0.473176 },
            qt:  { name: 'Quart (qt, US)',     factor: 0.946353 },
            gal: { name: 'Gallon (gal, US)',   factor: 3.78541 }
          }
        },
        speed: {
          label: '__LBL_CAT_SPEED__',
          base: 'mps',
          units: {
            mps:  { name: 'Meter/sec (m/s)',   factor: 1 },
            kph:  { name: 'Kilometer/h (km/h)', factor: 1/3.6 },
            mph:  { name: 'Mile/h (mph)',      factor: 0.44704 },
            kn:   { name: 'Knot (kn)',         factor: 0.514444 },
            fps:  { name: 'Foot/sec (ft/s)',   factor: 0.3048 }
          }
        }
      };

      var $cats = document.getElementById('cats');
      var $unitFrom = document.getElementById('unit-from');
      var $unitTo = document.getElementById('unit-to');
      var $valueIn = document.getElementById('value-in');
      var $result = document.getElementById('result');
      var $swap = document.getElementById('swap');

      var current = 'temperature';

      function toBase(category, unitKey, v) {
        var u = CATEGORIES[category].units[unitKey];
        if (u.to) return u.to(v);
        return v * u.factor;
      }
      function fromBase(category, unitKey, v) {
        var u = CATEGORIES[category].units[unitKey];
        if (u.from) return u.from(v);
        return v / u.factor;
      }
      function formatNumber(n) {
        if (!isFinite(n)) return '—';
        var abs = Math.abs(n);
        // Use fixed decimals for readable numbers, scientific when extreme
        if (abs !== 0 && (abs < 1e-4 || abs >= 1e9)) return n.toExponential(4);
        // Trim trailing zeros while keeping up to 6 significant decimals
        var rounded = Number(n.toPrecision(7));
        return rounded.toLocaleString('en-US', { maximumFractionDigits: 6 });
      }
      function buildCats() {
        $cats.innerHTML = '';
        Object.keys(CATEGORIES).forEach(function(key) {
          var btn = document.createElement('button');
          btn.className = 'cat-btn' + (key === current ? ' active' : '');
          btn.textContent = CATEGORIES[key].label;
          btn.addEventListener('click', function() {
            current = key;
            buildCats();
            buildUnits();
            convert();
          });
          $cats.appendChild(btn);
        });
      }
      function buildUnits() {
        var cat = CATEGORIES[current];
        $unitFrom.innerHTML = '';
        $unitTo.innerHTML = '';
        var keys = Object.keys(cat.units);
        keys.forEach(function(key, idx) {
          var opt1 = document.createElement('option');
          opt1.value = key; opt1.textContent = cat.units[key].name;
          $unitFrom.appendChild(opt1);
          var opt2 = document.createElement('option');
          opt2.value = key; opt2.textContent = cat.units[key].name;
          $unitTo.appendChild(opt2);
        });
        // Defaults: first unit source, a sensible different target
        $unitFrom.value = keys[0];
        $unitTo.value = keys[Math.min(1, keys.length - 1)];
      }
      function convert() {
        var v = parseFloat($valueIn.value);
        if (isNaN(v)) { $result.textContent = '—'; return; }
        var baseVal = toBase(current, $unitFrom.value, v);
        var targetVal = fromBase(current, $unitTo.value, baseVal);
        var unitToLabel = $unitTo.options[$unitTo.selectedIndex].textContent;
        $result.textContent = formatNumber(targetVal) + ' ' + unitToLabel;
      }

      $valueIn.addEventListener('input', convert);
      $unitFrom.addEventListener('change', convert);
      $unitTo.addEventListener('change', convert);
      $swap.addEventListener('click', function() {
        var tmp = $unitFrom.value;
        $unitFrom.value = $unitTo.value;
        $unitTo.value = tmp;
        convert();
      });

      buildCats();
      buildUnits();
      convert();
    })();
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
    labels = _LABELS[lang]

    # Resolve all __LBL_*__ placeholders in the template. Title appears both
    # in <title> and in the header, so we use the same replacement.
    replacements = {
        "__LANG__": lang,
        "__TITLE__": labels["title"],
        "__LBL_TITLE__": labels["title"],
        "__LBL_FROM__": labels["from"],
        "__LBL_TO__": labels["to"],
        "__LBL_SWAP__": labels["swap"],
        "__LBL_CAT_TEMPERATURE__": labels["temperature"],
        "__LBL_CAT_LENGTH__": labels["length"],
        "__LBL_CAT_WEIGHT__": labels["weight"],
        "__LBL_CAT_VOLUME__": labels["volume"],
        "__LBL_CAT_SPEED__": labels["speed"],
    }
    html = _HTML_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)

    print(
        json.dumps(
            {
                "text": labels["caption"],
                "frame": {
                    "html": html,
                    "title": labels["title"],
                    "aspect_ratio": 0.85,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
