"""Read-only light levels and supplied color facts; no bridge commands."""

from collections.abc import Mapping

from src.core.i18n_cards import card_label
from src.core.i18n_drafts import label_separator
from src.domains.agents.display.components.base import RenderContext, escape_html, render_d_item
from src.domains.agents.display.components.card_content import render_details
from src.domains.agents.display.values import nonnegative_number


def _measurements(value: object, keys: tuple[str, ...]) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {
        key: number for key in keys if (number := nonnegative_number(value.get(key))) is not None
    }


def hue_display_fields(light: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    color = light.get("color")
    if isinstance(color, dict):
        result["color"] = {"xy": _measurements(color.get("xy"), ("x", "y"))}
    temperature = light.get("color_temperature")
    if isinstance(temperature, dict):
        result["color_temperature"] = {
            **_measurements(temperature, ("mirek",)),
            "mirek_valid": temperature.get("mirek_valid") is True,
            "mirek_schema": _measurements(
                temperature.get("mirek_schema"), ("mirek_minimum", "mirek_maximum")
            ),
        }
    return result


def render_light_level(value: object, ctx: RenderContext) -> str:
    level = nonnegative_number(value)
    if level is None or level > 100:
        return ""
    label = escape_html(card_label("brightness", ctx.language))
    return f'<meter class="lia-light-level" min="0" max="100" value="{level:g}" aria-label="{label}">{level:g}%</meter>'


def _temperature_text(value: dict[str, object], ctx: RenderContext) -> str:
    mirek = nonnegative_number(value.get("mirek"))
    # A fractional sub-mirek is not a Hue reading; its reciprocal can overflow.
    if mirek is None or mirek < 1 or value.get("mirek_valid") is not True:
        return card_label("measurement_unavailable", ctx.language)
    return f"{1000000 / mirek:.0f} K ({mirek:g} mirek)"


def render_light_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    rows: list[str] = []
    temperature = data.get("color_temperature")
    if isinstance(temperature, dict):
        label = card_label("color_temperature", ctx.language)
        rows.append(
            render_d_item(
                "thermostat",
                escape_html(
                    f"{label}{label_separator(ctx.language)}{_temperature_text(temperature, ctx)}"
                ),
            )
        )
        bounds = _measurements(temperature.get("mirek_schema"), ("mirek_minimum", "mirek_maximum"))
        minimum, maximum = bounds.get("mirek_minimum"), bounds.get("mirek_maximum")
        if minimum is not None and maximum is not None and 1 <= minimum <= maximum:
            rows.append(
                render_d_item(
                    "thermostat",
                    f"{1000000 / maximum:.0f}–{1000000 / minimum:.0f} K ({minimum:g}–{maximum:g} mirek)",
                )
            )
    color = data.get("color")
    xy = color.get("xy") if isinstance(color, dict) else None
    if isinstance(xy, dict):
        x, y = nonnegative_number(xy.get("x")), nonnegative_number(xy.get("y"))
        if x is not None and y is not None and x <= 1 and y <= 1:
            rows.append(render_d_item("palette", f"CIE xy · x {x:g} · y {y:g}"))
    return render_details("".join(rows), ctx)
