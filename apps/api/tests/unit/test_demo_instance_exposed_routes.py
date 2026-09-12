"""What the demonstrator edge lets through, route by real route.

The allowlist next door pins PREFIXES. Prefixes are how a surface grows
without anyone deciding: mount one endpoint under an already-allowed prefix
and it is public on the demonstrator the same day, reviewed by nobody. The
companion guard checks a handful of sensitive paths somebody thought to write
down — which is exactly the routes we already knew about.

So this file works the other way round: it enumerates the routes the
application ACTUALLY mounts, computes which ones the edge would forward, and
compares that to a frozen decision. Adding a route under an allowed prefix
fails here until someone writes it down. Removing one from the visitor's
journey fails too — a demonstrator quietly missing an endpoint is a bug the
visitor discovers for us.

Read the list below as the answer to "what can an anonymous stranger reach".
"""

from __future__ import annotations

import importlib
import re
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from tests._demo_template import capability_flags
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

CADDYFILE = repo_root_or_skip() / "infrastructure" / "demo-instance" / "Caddyfile"

#: Every route the edge forwards, as "METHOD /path". Frozen on purpose: this
#: is the demonstrator's public surface, and it changes only by decision.
#:
#: It is long because the demonstrator shows the REAL product — a visitor
#: reaches every feature their own account owns. What is NOT here is what
#: matters: no /connectors (linking a real mailbox), no /admin, no
#: /usage-limits/admin, no /metrics, no federated sign-in — and nothing of a
#: family the demonstrator template switches OFF (attachments, spaces,
#: skills, MCP, heartbeat, channels, meetings, telephony…): their routers
#: are not mounted there, so their prefixes in the Caddyfile open nothing.
#: Until 2026-09-12 this list carried 57 such routes, read from the TEST
#: process's routers rather than the demonstrator's.
EXPECTED_EXPOSED_ROUTES: frozenset[str] = frozenset(
    {
        "POST /api/v1/account/export",
        "GET /api/v1/account/export/latest",
        "GET /api/v1/account/export/{job_id}/download",
        "POST /api/v1/agents/chat/stream",
        # Reading and deleting one's OWN files survives the uploads ceiling
        # (ADR-279, amended 2026-09-12): every generated document is served by
        # the GET, so with the router unmounted the demonstrator wrote reports
        # nobody could open. The upload stays refused by the route's own
        # capability guard (ATTACHMENTS_ENABLED=false here): forwarded by the
        # edge, refused by the application, which is the honest shape.
        "GET /api/v1/attachments/{attachment_id}",
        "DELETE /api/v1/attachments/{attachment_id}",
        "POST /api/v1/attachments/upload",
        "GET /api/v1/agents/health",
        "GET /api/v1/agents/hitl/pending",
        "GET /api/v1/agents/runs/active",
        "POST /api/v1/agents/runs/active/cancel",
        "GET /api/v1/agents/runs/{stream_id}/stream",
        "GET /api/v1/auth/features",
        "POST /api/v1/auth/login",
        "POST /api/v1/auth/logout",
        "POST /api/v1/auth/logout-all",
        "GET /api/v1/auth/me",
        "PATCH /api/v1/auth/me/debug-panel-preference",
        "PATCH /api/v1/auth/me/display-mode-preference",
        "PATCH /api/v1/auth/me/execution-mode-preference",
        "PATCH /api/v1/auth/me/health-metrics-agents-preference",
        "GET /api/v1/auth/me/last-location",
        "PUT /api/v1/auth/me/last-location",
        "PATCH /api/v1/auth/me/location-preference",
        "PATCH /api/v1/auth/me/login-notifications-preference",
        "PATCH /api/v1/auth/me/memory-preference",
        "PATCH /api/v1/auth/me/onboarding-checklist",
        "PATCH /api/v1/auth/me/onboarding-preference",
        "PATCH /api/v1/auth/me/tokens-display-preference",
        "GET /api/v1/auth/me/voice-mode-preference",
        "PATCH /api/v1/auth/me/voice-mode-preference",
        "PATCH /api/v1/auth/me/voice-preference",
        "POST /api/v1/auth/password/disable",
        "GET /api/v1/auth/profile-image-proxy",
        "POST /api/v1/auth/refresh",
        "POST /api/v1/auth/register",
        "POST /api/v1/auth/request-password-reset",
        "POST /api/v1/auth/reset-password",
        "GET /api/v1/auth/sessions",
        "POST /api/v1/auth/sessions/revoke-others",
        "DELETE /api/v1/auth/sessions/{display_id}",
        "POST /api/v1/auth/step-up/password",
        "GET /api/v1/auth/step-up/status",
        "POST /api/v1/auth/step-up/totp",
        "POST /api/v1/auth/step-up/webauthn/options",
        "POST /api/v1/auth/step-up/webauthn/verify",
        "POST /api/v1/auth/verify-email",
        "GET /api/v1/briefing/cards",
        "GET /api/v1/briefing/preferences",
        "PUT /api/v1/briefing/preferences",
        # Lot 4-A2 (ADR-237): the listen button reads the DISPLAYED synthesis
        # aloud — auth-gated, cost-bounded (BRIEFING_AUDIO_MAX_*), usage-limits
        # apply. The demo visitor gets the real product, bounded like everyone.
        "POST /api/v1/briefing/synthesis/audio",
        "POST /api/v1/briefing/refresh",
        "POST /api/v1/briefing/refresh-cards",
        "GET /api/v1/briefing/synthesis",
        "GET /api/v1/capabilities",
        "GET /api/v1/chat/shortcuts",
        "PUT /api/v1/chat/shortcuts",
        "GET /api/v1/chat/suggestions",
        "GET /api/v1/chat/users/me/statistics",
        "GET /api/v1/config",
        "GET /api/v1/conversations/me",
        "GET /api/v1/conversations/me/messages",
        "POST /api/v1/conversations/me/messages/{message_id}/feedback",
        "POST /api/v1/conversations/me/reset",
        "GET /api/v1/conversations/me/stats",
        "GET /api/v1/conversations/me/totals",
        "POST /api/v1/habits/presence",
        "POST /api/v1/habits/recompute",
        "PATCH /api/v1/habits/settings",
        "DELETE /api/v1/habits/{habit_id}",
        "GET /api/v1/habits/{habit_id}/explanation",
        "POST /api/v1/habits/{habit_id}/status",
        "GET /api/v1/health-metrics/aggregate",
        "DELETE /api/v1/health-metrics/all",
        "GET /api/v1/health-metrics/tokens",
        "POST /api/v1/health-metrics/tokens",
        "DELETE /api/v1/health-metrics/tokens/{token_id}",
        "GET /api/v1/interests",
        "POST /api/v1/interests",
        "DELETE /api/v1/interests/all",
        "GET /api/v1/interests/categories",
        "GET /api/v1/interests/export",
        "GET /api/v1/interests/notifications/history",
        "GET /api/v1/interests/settings",
        "PATCH /api/v1/interests/settings",
        "DELETE /api/v1/interests/{interest_id}",
        "PATCH /api/v1/interests/{interest_id}",
        "GET /api/v1/interests/{interest_id}/explanation",
        "POST /api/v1/interests/{interest_id}/feedback",
        "GET /api/v1/interests/{interest_id}/provenance",
        "POST /api/v1/interests/{interest_id}/reactivate",
        "DELETE /api/v1/journals",
        "GET /api/v1/journals",
        "POST /api/v1/journals",
        "POST /api/v1/journals/consolidate",
        "GET /api/v1/journals/export",
        "GET /api/v1/journals/portrait",
        "POST /api/v1/journals/portrait/feedback",
        "GET /api/v1/journals/settings",
        "PATCH /api/v1/journals/settings",
        "GET /api/v1/journals/themes",
        "DELETE /api/v1/journals/{entry_id}",
        "PATCH /api/v1/journals/{entry_id}",
        "GET /api/v1/journals/{entry_id}/provenance",
        "GET /api/v1/mcp/servers",
        "POST /api/v1/mcp/servers",
        "GET /api/v1/mcp/servers/oauth/callback",
        "DELETE /api/v1/mcp/servers/{server_id}",
        "PATCH /api/v1/mcp/servers/{server_id}",
        "POST /api/v1/mcp/servers/{server_id}/app/call-tool",
        "POST /api/v1/mcp/servers/{server_id}/app/read-resource",
        "POST /api/v1/mcp/servers/{server_id}/generate-description",
        "POST /api/v1/mcp/servers/{server_id}/oauth/authorize",
        "POST /api/v1/mcp/servers/{server_id}/oauth/disconnect",
        "POST /api/v1/mcp/servers/{server_id}/test",
        "PATCH /api/v1/mcp/servers/{server_id}/toggle",
        "DELETE /api/v1/memories",
        "GET /api/v1/memories",
        "POST /api/v1/memories",
        "GET /api/v1/memories/categories",
        "GET /api/v1/memories/export",
        "DELETE /api/v1/memories/{memory_id}",
        "GET /api/v1/memories/{memory_id}",
        "PATCH /api/v1/memories/{memory_id}",
        "PATCH /api/v1/memories/{memory_id}/pin",
        "GET /api/v1/memories/{memory_id}/provenance",
        "POST /api/v1/notifications/admin/broadcast",
        "GET /api/v1/notifications/broadcasts/unread",
        "POST /api/v1/notifications/broadcasts/{broadcast_id}/read",
        "GET /api/v1/notifications/hub-counts",
        # Decided 2026-08-24 (ADR-246): a demonstrator visitor running a
        # native shell needs it, it demands a session, and it answers only
        # values every published Android build already ships in its APK.
        "GET /api/v1/notifications/push-config",
        "POST /api/v1/notifications/register-token",
        "GET /api/v1/notifications/stream",
        "POST /api/v1/notifications/test",
        "GET /api/v1/notifications/tokens",
        "DELETE /api/v1/notifications/tokens/{token_id}",
        "POST /api/v1/notifications/unregister-token",
        "GET /api/v1/open-loops",
        "PATCH /api/v1/open-loops/{loop_id}",
        "POST /api/v1/open-loops/{loop_id}/close",
        "GET /api/v1/personalities",
        "GET /api/v1/personalities/admin",
        "POST /api/v1/personalities/admin",
        "DELETE /api/v1/personalities/admin/{personality_id}",
        "GET /api/v1/personalities/admin/{personality_id}",
        "PATCH /api/v1/personalities/admin/{personality_id}",
        "POST /api/v1/personalities/admin/{personality_id}/auto-translate",
        "POST /api/v1/personalities/admin/{personality_id}/translations",
        "GET /api/v1/personalities/current",
        "PATCH /api/v1/personalities/current",
        # The action register (ADR-263): a visitor's own record of what the
        # assistant did for them, on their own demo account. Same class as
        # memories and journals — read-only, user-scoped, and the settings page
        # that reads it is part of the real product the demonstrator shows.
        "GET /api/v1/effects/export",
        # The five records about the visitor, in one file. Same scope as the
        # per-register export beside it — the route declares no account
        # parameter — and the same contract as the administrator's: no
        # content, every identifier a handle. Nothing here that the exports
        # above do not already expose.
        "GET /api/v1/effects/export/article12",
        "GET /api/v1/effects/journal",
        "GET /api/v1/effects/run/{run_id}",
        "GET /api/v1/effects/treatments/journal",
        "GET /api/v1/effects/treatments/run/{run_id}",
        # And the proof over them (ADR-263, lot 5). Read-only and user-scoped
        # like the journals themselves: a visitor can only ever verify their
        # own chain, and a verdict says whether rows were altered — never what
        # any of them says. On the demonstrator the sealing is off, so the
        # honest answer is « this instance does not seal », which is exactly
        # what the surface is built to say.
        # The reader's own records as figures. Every label is a BOUNDED value
        # — a model, a graph node, a domain, a status — and none names a person
        # or quotes anything, so there is nothing here to withhold.
        "GET /api/v1/effects/statistics",
        "GET /api/v1/effects/chain/status",
        "GET /api/v1/effects/chain/verify",
        "GET /api/v1/product/public-demo-link",
        "GET /api/v1/psyche/expression",
        "GET /api/v1/psyche/history",
        "POST /api/v1/psyche/reset",
        "GET /api/v1/psyche/settings",
        "PATCH /api/v1/psyche/settings",
        "GET /api/v1/psyche/state",
        "GET /api/v1/psyche/summary",
        "DELETE /api/v1/relations/favorites/{name}",
        "PUT /api/v1/relations/favorites/{name}",
        "POST /api/v1/relations/merges",
        "DELETE /api/v1/relations/merges/{name}",
        "GET /api/v1/relations/overview-scope",
        "PUT /api/v1/relations/overview-scope",
        "GET /api/v1/relations/{name}",
        "GET /api/v1/relations/{name}/context",
        # The relationship debrief: a visitor reaches their OWN, over their own
        # data, like every other feature of their own account. The build verb is
        # capped per account per day on its own budget, and the read never
        # builds — so neither can be turned into a way to spend the
        # demonstrator's LLM allowance from outside.
        "GET /api/v1/relations/{name}/debrief",
        "POST /api/v1/relations/{name}/debrief",
        # ...and the switch that turns it off, or the visitor could not decline
        # a capability the same page offers them.
        "PATCH /api/v1/relations/settings",
        # The reminders domain gained a management screen on 2026-09-06, so a
        # visitor creates and edits their OWN reminders exactly as they create
        # and edit their own routines below. Nothing here reaches another
        # account: every handler resolves the row through the session owner and
        # answers "not found" for someone else's id.
        "GET /api/v1/reminders",
        "GET /api/v1/reminders/detail",
        "POST /api/v1/reminders",
        "PATCH /api/v1/reminders/{reminder_id}",
        "DELETE /api/v1/reminders/{reminder_id}",
        "GET /api/v1/scheduled-actions",
        "GET /api/v1/scheduled-actions/week",
        "POST /api/v1/scheduled-actions",
        "DELETE /api/v1/scheduled-actions/{action_id}",
        "PATCH /api/v1/scheduled-actions/{action_id}",
        "POST /api/v1/scheduled-actions/{action_id}/execute",
        "PATCH /api/v1/scheduled-actions/{action_id}/toggle",
        "GET /api/v1/system-settings/debug-panel-status",
        "GET /api/v1/usage-limits/me",
        "GET /api/v1/usage/export/consumption-summary",
        "GET /api/v1/usage/export/google-api-usage",
        "GET /api/v1/usage/export/stt-usage",
        "GET /api/v1/usage/export/token-usage",
        "GET /api/v1/usage/export/tts-usage",
        "GET /api/v1/users/admin/autocomplete",
        "GET /api/v1/users/admin/search",
        "PATCH /api/v1/users/admin/{user_id}/activation",
        "DELETE /api/v1/users/admin/{user_id}/delete-account",
        "DELETE /api/v1/users/admin/{user_id}/gdpr",
        "DELETE /api/v1/users/me/home-location",
        "GET /api/v1/users/me/home-location",
        "PUT /api/v1/users/me/home-location",
        "GET /api/v1/users/me/settings-shortcuts",
        "PUT /api/v1/users/me/settings-shortcuts",
        "GET /api/v1/users/search/by-email",
        "GET /api/v1/users/timezones",
        "DELETE /api/v1/users/{user_id}",
        "GET /api/v1/users/{user_id}",
        "PATCH /api/v1/users/{user_id}",
        "POST /api/v1/voice/ticket",
        # Three families were listed as `/x/*`, which never matched the bare
        # `/x`: the Relations overview, the learned-habits panel (and its
        # « forget everything »), the health samples list (and its per-kind
        # delete) answered 404 while every sub-route worked (2026-09-12). All
        # four read or delete the visitor's OWN rows.
        "GET /api/v1/relations",
        "GET /api/v1/habits",
        "DELETE /api/v1/habits",
        "GET /api/v1/health-metrics",
        "DELETE /api/v1/health-metrics",
        # Same shape: the generation route was listed EXACT, so the options
        # the picker reads (qualities and sizes of the configured model) were
        # not. Read-only, no account parameter.
        "GET /api/v1/image-generation/options",
        # The visitor's own timeline of what LIA did proactively for them —
        # the same class as the effects register exposed above: read-only,
        # paged with exact totals, nothing but the visitor's account.
        "GET /api/v1/activity/timeline",
        # The gallery of what LIA produced (ADR-279): the same class as the
        # attachments beside it — a visitor's own images, documents and
        # screenshots, listed, deleted, never anyone else's. Hidden by
        # omission since v1.44.1: the settings tab came up empty.
        "GET /api/v1/generated-assets",
        "POST /api/v1/generated-assets/delete",
        "DELETE /api/v1/generated-assets/{asset_id}",
        # The answers a visitor keeps (ADR-282): a COPY of their own bubble
        # into their own rows, bounded by BOOKMARKS_MAX_PER_USER, no model
        # spend, no external effect. The bubble shows the toggle whenever the
        # capability is on, so a hidden route would be a button that fails.
        "POST /api/v1/bookmarks",
        "GET /api/v1/bookmarks",
        "GET /api/v1/bookmarks/state",
        "DELETE /api/v1/bookmarks/by-message/{message_id}",
        "DELETE /api/v1/bookmarks/{bookmark_id}",
        # The workboard (ADR-276): a visitor's own tickets, held by them or by
        # LIA. A run spends the visitor's own allowance exactly as a routine
        # does (scheduled-actions, exposed above), under the same ceilings;
        # every handler resolves the row through the session owner. Switched
        # ON in the demonstrator template on 2026-09-12.
        "GET /api/v1/workboard/summary",
        "GET /api/v1/workboard/needs-me",
        "GET /api/v1/workboard/tickets",
        "POST /api/v1/workboard/tickets",
        "GET /api/v1/workboard/tickets/{ticket_id}",
        "PATCH /api/v1/workboard/tickets/{ticket_id}",
        "DELETE /api/v1/workboard/tickets/{ticket_id}",
        "POST /api/v1/workboard/tickets/{ticket_id}/comments",
        "POST /api/v1/workboard/tickets/{ticket_id}/move",
        "POST /api/v1/workboard/tickets/{ticket_id}/run-now",
        # Peer connections: two demonstrator accounts, throwaway on both sides
        # and wiped together the same night. Discovery answers an EXACT email
        # only (the by-email search above is already exposed), a request has
        # to be accepted by the other side, and the sharing scope is the
        # accepting account's own choice. Switched ON on 2026-09-12.
        "GET /api/v1/peers/me",
        "PUT /api/v1/peers/me",
        "POST /api/v1/peers/discovery/search",
        "GET /api/v1/peers/requests",
        "POST /api/v1/peers/requests",
        "POST /api/v1/peers/requests/{connection_id}/respond",
        "GET /api/v1/peers/connections",
        "DELETE /api/v1/peers/connections/{connection_id}",
        "PUT /api/v1/peers/connections/{connection_id}/shares",
        "GET /api/v1/peers/messages",
        "GET /api/v1/peers/blocks",
        "POST /api/v1/peers/blocks",
        "DELETE /api/v1/peers/blocks/{peer_id}",
        "GET /api/v1/peers/access-log",
    }
)

#: What the edge keeps from visitors ON PURPOSE, family by family, each with
#: the reason. A key ending in `*` is a prefix; any other key is an exact path.
#: Every mounted route the edge does not forward must fall under one of these
#: or under ``HIDDEN_PENDING_DECISION`` — a family nobody listed is not
#: "closed by decision", it is closed by omission, and that is how the gallery
#: and the kept answers shipped to the demonstrator as empty screens.
HIDDEN_BY_DECISION: dict[str, str] = {
    "/api/v1/admin/*": "the operator's surface; a visitor is never an administrator",
    "/api/v1/usage-limits/admin/*": "the operator's ceilings and blocks",
    "GET /api/v1/users": "the superuser listing of every account (the /users/me routes are exposed)",
    "/api/v1/connectors*": "nobody links a real mailbox to an instance wiped nightly",
    "GET /api/v1/": "the API root banner; the web reads /health and /ready",
    "GET /api/v1/health": "the API's own probe; the edge exposes /health and /ready instead",
}

#: Families no decision has been written for yet. Shrink-only: an entry leaves
#: when the owner decides — exposed (written above), closed (written in
#: ``HIDDEN_BY_DECISION``), or switched off in the demonstrator template, in
#: which case the router is not mounted at all and the decision lives with
#: the flag (meetings, channels, plugins left this table that way on
#: 2026-09-12). Each names the question the decision must answer.
HIDDEN_PENDING_DECISION: dict[str, str] = {
    "/api/v1/ingest/*": "the mobile health ingestion; nothing on the demonstrator produces samples",
}


def _allowed_patterns() -> set[str]:
    match = re.search(r"@allowed\s+path\s+([^\n]+)", CADDYFILE.read_text(encoding="utf-8"))
    assert match, "the edge must declare a single @allowed path matcher"
    return set(match.group(1).split())


def _refused_regexps() -> list[re.Pattern[str]]:
    """Path regexps the edge refuses BEFORE the allowlist is consulted.

    Modelled in the same order as Caddy evaluates them: a refusal placed
    after the allowlist would never fire, so reading them independently
    would credit the instance with a protection it does not have.
    """
    text = CADDYFILE.read_text(encoding="utf-8")
    allowlist_at = text.index("@allowed")
    return [
        re.compile(pattern)
        for pattern in re.findall(r"path_regexp\s+(\S+)\s*$", text[:allowlist_at], re.MULTILINE)
    ]


def _matches(pattern: str, path: str) -> bool:
    """Caddy path-matching semantics: exact, or prefix when it ends with *."""
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return pattern == path


def _routes_of(api_router: object) -> set[str]:
    """Every "METHOD /path" a router mounts, prefix included."""
    routes: set[str] = set()
    for route in getattr(api_router, "routes", []):
        path = "/api/v1" + str(getattr(route, "path", ""))
        for method in getattr(route, "methods", None) or []:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.add(f"{method} {path}")
    return routes


def _mounted_routes() -> set[str]:
    """The routes the application mounts UNDER THE DEMONSTRATOR'S CEILINGS.

    ``routes.py`` includes a router or not at import time, reading
    ``settings``, and the test environment declares no capability flag — so
    the census used to see the TEST process's routers: the heartbeat and MCP
    routes counted as exposed while the demonstrator switches both off and
    mounts neither, and a family the demonstrator switches ON (peers) was
    invisible here and closed at the edge without anyone noticing. The
    router is therefore rebuilt with the flags of ``.env.demo-instance.example``
    patched onto ``settings`` and restored afterwards, so what this file
    freezes is what the demonstrator actually serves.
    """
    from src.api.v1 import routes as routes_module
    from src.core.config import settings

    ceilings = {
        key.lower(): value
        for key, value in capability_flags().items()
        if hasattr(settings, key.lower())
    }
    assert ceilings, "the demonstrator template declares no *_ENABLED ceiling"
    try:
        with ExitStack() as stack:
            for name, value in ceilings.items():
                stack.enter_context(patch.object(settings, name, value))
            return _routes_of(importlib.reload(routes_module).api_router)
    finally:
        importlib.reload(routes_module)


def _exposed_routes() -> set[str]:
    patterns = _allowed_patterns()
    refused = _refused_regexps()
    exposed = set()
    for route in _mounted_routes():
        path = route.split(" ", 1)[1]
        if any(regexp.match(path) for regexp in refused):
            continue
        if any(_matches(pattern, path) for pattern in patterns):
            exposed.add(route)
    return exposed


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/google/login",
        "/api/v1/auth/google/callback",
        # A provider added later inherits the refusal from its shape.
        "/api/v1/auth/apple/login",
    ],
)
def test_federated_sign_in_never_reaches_the_instance(path: str) -> None:
    """The one door is email + terms; a provider would skip both.

    Guarded here as well as in the application: this is the layer that keeps
    the request from arriving at all, and it only works because the refusal
    is declared BEFORE the allowlist opens /auth/*.
    """
    assert any(regexp.match(path) for regexp in _refused_regexps()), (
        f"{path} is not refused at the edge — check that the path_regexp block "
        "still sits above @allowed in the Caddyfile"
    )


def test_the_password_form_is_not_caught_by_the_refusal() -> None:
    """The refusal must not take the demonstrator's only way in with it."""
    for path in ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/verify-email"):
        assert not any(regexp.match(path) for regexp in _refused_regexps()), path


def test_the_public_surface_is_exactly_what_was_decided() -> None:
    """No route reaches the public demonstrator without a written decision."""
    exposed = _exposed_routes()
    added = exposed - EXPECTED_EXPOSED_ROUTES
    removed = EXPECTED_EXPOSED_ROUTES - exposed
    assert not added, (
        f"{len(added)} route(s) newly reachable by anonymous visitors — review each, "
        f"then add it to EXPECTED_EXPOSED_ROUTES:\n" + "\n".join(sorted(added))
    )
    assert (
        not removed
    ), "route(s) no longer reachable — the visitor journey may be broken:\n" + "\n".join(
        sorted(removed)
    )


def _hidden_key_matches(key: str, route: str) -> bool:
    """A table key is a prefix (``/x/*``) or an exact ``METHOD /path``."""
    path = route.split(" ", 1)[1]
    if key.endswith("*"):
        return _matches(key, path)
    return key == route


def test_every_hidden_route_is_hidden_by_a_written_decision() -> None:
    """A mounted route the edge does not forward is closed on purpose, or the build reds.

    The exposed list above only ever sees routes under an ALLOWED prefix, so
    a whole new family — the gallery, the kept answers — could ship to the
    demonstrator as a 404 without failing anything (measured 2026-09-12:
    176 hidden routes, 15 of them families the product shows on screen).
    The refusal block is a decision in its own right and is read as one.
    """
    refused = _refused_regexps()
    hidden = _mounted_routes() - _exposed_routes()
    declared = {**HIDDEN_BY_DECISION, **HIDDEN_PENDING_DECISION}
    undeclared = sorted(
        route
        for route in hidden
        if not any(regexp.match(route.split(" ", 1)[1]) for regexp in refused)
        and not any(_hidden_key_matches(key, route) for key in declared)
    )
    assert not undeclared, (
        f"{len(undeclared)} mounted route(s) the demonstrator cannot reach and nobody "
        "decided about — expose them in the Caddyfile and EXPECTED_EXPOSED_ROUTES, or "
        "declare them in HIDDEN_BY_DECISION / HIDDEN_PENDING_DECISION with a reason:\n"
        + "\n".join(undeclared)
    )
    stale = sorted(key for key in declared if not any(_hidden_key_matches(key, r) for r in hidden))
    assert not stale, "hidden-table entries that hide nothing any more (delete them): " + ", ".join(
        stale
    )


def test_a_hidden_family_is_not_also_exposed() -> None:
    """The two tables and the allowlist cannot disagree about one family."""
    exposed = _exposed_routes()
    for key in {**HIDDEN_BY_DECISION, **HIDDEN_PENDING_DECISION}:
        leaked = sorted(r for r in exposed if _hidden_key_matches(key, r))
        assert not leaked, f"{key} is declared hidden but the edge forwards: {leaked}"


def test_paths_outside_the_api_prefix_are_refused_by_decision() -> None:
    """A root path must be closed on purpose, not by luck.

    ``/metrics`` does not live under ``/api``, so the "any other API path"
    block missed it and the request reached the web fallback, which answered
    404 for want of a page. That is the right status for the wrong reason: it
    would change the day the front serves a catch-all. Measured against a real
    Caddy on 2026-08-06 — it was being forwarded.
    """
    text = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(r"@other_api\s+path\s+(.+)", text)
    assert match, "the edge must declare the catch-all refusal"
    refused = set(match.group(1).split())
    assert "/metrics" in refused, "the metrics endpoint must be refused explicitly"
