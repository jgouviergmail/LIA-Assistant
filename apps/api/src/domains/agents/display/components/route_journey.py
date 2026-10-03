"""Local journey reading with complete steps and no navigation simulation."""

from collections.abc import Mapping
from math import isfinite

from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_collapsible,
)
from src.domains.agents.display.icons import get_travel_mode_icon, icon
from src.domains.agents.display.urls import build_route_url, safe_css_color, safe_url
from src.domains.agents.display.values import (
    list_values,
    nonnegative_integer,
    nonnegative_number,
    scalar_text,
)

_MANEUVERS = {
    "TURN_LEFT": "turn_left",
    "TURN_RIGHT": "turn_right",
    "TURN_SLIGHT_LEFT": "turn_slight_left",
    "TURN_SLIGHT_RIGHT": "turn_slight_right",
    "UTURN_LEFT": "u_turn_left",
    "UTURN_RIGHT": "u_turn_right",
    "ROUNDABOUT_LEFT": "roundabout_left",
    "ROUNDABOUT_RIGHT": "roundabout_right",
    "STRAIGHT": "straight",
    "MERGE": "merge",
    "FORK_LEFT": "fork_left",
    "FORK_RIGHT": "fork_right",
}


def journey_measurements(data: Mapping[str, object]) -> str:
    meters = nonnegative_integer(data.get("distance_meters"))
    seconds = nonnegative_integer(data.get("duration_seconds"))
    distance = (
        (f"{meters / 1000:g} km" if meters >= 1000 else f"{meters} m") if meters is not None else ""
    )
    duration = (
        (
            f"{seconds // 60} min" + (f" {seconds % 60} s" if seconds % 60 else "")
            if seconds >= 60
            else f"{seconds} s"
        )
        if seconds is not None
        else ""
    )
    return " · ".join(value for value in (distance, duration) if value)


def route_summary(data: Mapping[str, object], duration: str, ctx: RenderContext) -> str:
    meters = nonnegative_integer(data.get("distance_meters"))
    km = nonnegative_number(data.get("distance_km"))
    distance = journey_measurements({"distance_meters": meters})
    if not distance and km is not None:
        distance = f"{km:g} km" if km >= 1 else f"{km * 1000:g} m"
    facts = [
        (V3Messages.get_duration_label(ctx.language), duration),
        (V3Messages.get_distance_label(ctx.language), distance),
    ]
    return (
        '<dl class="lia-route-summary">'
        + "".join(
            f"<div><dt>{escape_html(label)}</dt><dd>{escape_html(value)}</dd></div>"
            for label, value in facts
            if value
        )
        + "</dl>"
        if any(value for _, value in facts)
        else ""
    )


def _step(value: object) -> Mapping[str, object]:
    if isinstance(value, str):
        return {"instruction": value}
    if not isinstance(value, dict):
        return {}
    navigation = value.get("navigationInstruction")
    raw = navigation if isinstance(navigation, dict) else {}
    return {
        **value,
        "instruction": scalar_text(value.get("instruction"))
        or scalar_text(raw.get("instructions")),
        "distance_meters": value.get("distance_meters", value.get("distanceMeters")),
    }


def _transit(data: Mapping[str, object], ctx: RenderContext) -> str:
    mode = scalar_text(data.get("vehicle_name")) or scalar_text(data.get("vehicle_type"))
    line = scalar_text(data.get("line_name"))
    accent = safe_css_color(scalar_text(data.get("line_color"))) or "var(--lia-border)"
    badge = (
        f'<span class="lia-route__transit-badge" style="border-inline-start-color:{accent}">{escape_html(line)}</span>'
        if line
        else ""
    )
    stops = " → ".join(
        text for key in ("departure_stop", "arrival_stop") if (text := scalar_text(data.get(key)))
    )
    headsign = scalar_text(data.get("headsign"))
    count = nonnegative_integer(data.get("stop_count"))
    count_text = V3Messages.get_transit_stops(ctx.language, count) if count is not None else ""
    content = "".join(
        f"<p>{escape_html(text)}</p>" for text in (mode, headsign, stops, count_text) if text
    )
    return badge + content


def _render_step(value: Mapping[str, object], index: int, ctx: RenderContext) -> str:
    mode = scalar_text(value.get("travel_mode"))
    instruction = scalar_text(value.get("instruction")) or V3Messages.get_travel_mode(
        ctx.language, mode
    )
    transit = value.get("transit")
    detail = _transit(transit, ctx) if isinstance(transit, dict) else ""
    measurements = journey_measurements(value)
    symbol = (
        get_travel_mode_icon(mode)
        if mode in ("WALK", "TRANSIT")
        else _MANEUVERS.get(scalar_text(value.get("maneuver")), "straight")
    )
    variant = "--transit" if isinstance(transit, dict) else ("--walk" if mode == "WALK" else "")
    return (
        f'<li class="lia-route__step lia-route__step{variant}">'
        f'<span class="lia-route__step-number" aria-hidden="true">{index}</span>'
        f'<details class="lia-route-step"><summary>{icon(symbol)}<span class="lia-route__step-instruction">{escape_html(instruction)}</span></summary>'
        f'<div class="lia-route-step__detail">{detail}<p class="lia-route__step-distance">{escape_html(measurements)}</p></div></details></li>'
    )


def _step_list(value: object, ctx: RenderContext) -> str:
    steps = [step for value in list_values(value) if (step := _step(value))]
    return (
        '<ol class="lia-route__steps">'
        + "".join(_render_step(step, index, ctx) for index, step in enumerate(steps, 1))
        + "</ol>"
        if steps
        else ""
    )


def render_route_steps(value: object, ctx: RenderContext) -> str:
    content = _step_list(value, ctx)
    return render_collapsible(
        f"{V3Messages.get_route_steps(ctx.language)} ({len(list_values(value))})",
        content,
        with_separator=False,
    )


def render_route_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    legs = [leg for leg in list_values(data.get("legs")) if isinstance(leg, dict)]
    if not legs:
        return render_route_steps(data.get("steps"), ctx)
    content = "".join(
        f'<section class="lia-route-leg"><p class="lia-route-leg__heading">{escape_html(card_label("route_leg", ctx.language))} {index} · {escape_html(journey_measurements(leg))}</p>{_leg_map(leg, ctx)}{_step_list(leg.get("steps"), ctx)}</section>'
        for index, leg in enumerate(legs, 1)
    )
    return render_collapsible(
        V3Messages.get_route_steps(ctx.language), content, with_separator=False
    )


def render_route_tolls(value: object, ctx: RenderContext) -> str:
    estimates = [
        scalar_text(entry.get("formatted"))
        for entry in list_values(value)
        if isinstance(entry, dict)
    ]
    content = " · ".join(estimate for estimate in estimates if estimate)
    return (
        f'<p class="lia-route-leg__heading">{escape_html(V3Messages.get_toll_label(ctx.language))} · {escape_html(content)}</p>'
        if content
        else ""
    )


def render_route_alternatives(value: object, ctx: RenderContext) -> str:
    alternatives = [entry for entry in list_values(value) if isinstance(entry, dict)]
    content = "".join(
        f'<div class="lia-route-alternative"><p class="lia-route-leg__heading">{index} · {escape_html(journey_measurements(entry))}</p>{_alternative_steps(entry, ctx)}</div>'
        for index, entry in enumerate(alternatives, 1)
    )
    return render_collapsible(
        f'{card_label("route_alternatives", ctx.language)} ({len(alternatives)})',
        content,
        with_separator=False,
    )


def _alternative_steps(data: Mapping[str, object], ctx: RenderContext) -> str:
    legs = [leg for leg in list_values(data.get("legs")) if isinstance(leg, dict)]
    return "".join(_leg_map(leg, ctx) + _step_list(leg.get("steps"), ctx) for leg in legs)


def _leg_map(data: Mapping[str, object], ctx: RenderContext) -> str:
    start, end = data.get("start_location"), data.get("end_location")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return ""
    origin, destination = _coordinate(start), _coordinate(end)
    if not origin or not destination:
        return ""
    url = build_route_url(origin, destination, scalar_text(data.get("travel_mode")))
    return f'<a class="lia-route-leg__map" href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{escape_html(V3Messages.get_open_in_maps(ctx.language))}</a>'


def _coordinate(data: Mapping[str, object]) -> str:
    values = [scalar_text(data.get(key)) for key in ("latitude", "longitude")]
    try:
        latitude, longitude = (float(value) for value in values)
    except ValueError, OverflowError:
        return ""
    if not (
        isfinite(latitude)
        and isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return ""
    return ",".join(values)


def render_waypoint_links(data: Mapping[str, object], ctx: RenderContext) -> str:
    points = [
        scalar_text(data.get("origin")),
        *[value for value in list_values(data.get("waypoints")) if isinstance(value, str)],
        scalar_text(data.get("destination")),
    ]
    links = []
    for index, (start, end) in enumerate(zip(points, points[1:], strict=False), 1):
        url = build_route_url(
            start,
            end,
            scalar_text(data.get("travel_mode")),
            avoid_tolls=data.get("avoid_tolls") is True,
            avoid_highways=data.get("avoid_highways") is True,
            avoid_ferries=data.get("avoid_ferries") is True,
        )
        if url:
            links.append(
                f'<li><a class="lia-route-leg__map" href="{safe_url(url)}" target="_blank" rel="noopener noreferrer">{escape_html(card_label("route_leg", ctx.language))} {index} · {escape_html(start)} → {escape_html(end)}</a></li>'
            )
    return (
        render_collapsible(
            card_label("route_links", ctx.language),
            '<ol class="lia-route-links">' + "".join(links) + "</ol>",
            with_separator=False,
        )
        if links
        else ""
    )
