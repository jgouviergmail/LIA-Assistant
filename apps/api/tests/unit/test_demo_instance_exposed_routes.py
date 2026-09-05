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

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

CADDYFILE = repo_root_or_skip() / "infrastructure" / "demo-instance" / "Caddyfile"

#: Every route the edge forwards, as "METHOD /path". Frozen on purpose: this
#: is the demonstrator's public surface, and it changes only by decision.
#:
#: It is long because the demonstrator shows the REAL product — a visitor
#: reaches every feature their own account owns. What is NOT here is what
#: matters: no /connectors (linking a real mailbox), no /admin, no
#: /usage-limits/admin, no /metrics, no federated sign-in.
EXPECTED_EXPOSED_ROUTES: frozenset[str] = frozenset(
    {
        "POST /api/v1/account/export",
        "GET /api/v1/account/export/latest",
        "GET /api/v1/account/export/{job_id}/download",
        "POST /api/v1/agents/chat/stream",
        "GET /api/v1/agents/health",
        "GET /api/v1/agents/hitl/pending",
        "GET /api/v1/agents/runs/active",
        "POST /api/v1/agents/runs/active/cancel",
        "GET /api/v1/agents/runs/{stream_id}/stream",
        "POST /api/v1/attachments/upload",
        "DELETE /api/v1/attachments/{attachment_id}",
        "GET /api/v1/attachments/{attachment_id}",
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
        "GET /api/v1/heartbeat/history",
        # Lot 5-C2 (ADR-238): the proposals inbox — a pull-only VIEW over the
        # visitor's own undecided habit offers; deciding rides the feedback
        # route already exposed below.
        "GET /api/v1/heartbeat/offers",
        "PATCH /api/v1/heartbeat/notifications/{notification_id}/feedback",
        "GET /api/v1/heartbeat/settings",
        "PATCH /api/v1/heartbeat/settings",
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
        "GET /api/v1/mcp/admin-servers",
        "POST /api/v1/mcp/admin-servers/{server_key}/app/call-tool",
        "POST /api/v1/mcp/admin-servers/{server_key}/app/read-resource",
        "PATCH /api/v1/mcp/admin-servers/{server_key}/toggle",
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
        "GET /api/v1/rag-spaces",
        "POST /api/v1/rag-spaces",
        "POST /api/v1/rag-spaces/admin/reindex",
        "GET /api/v1/rag-spaces/admin/reindex/status",
        "GET /api/v1/rag-spaces/admin/system-spaces",
        "POST /api/v1/rag-spaces/admin/system-spaces/{space_name}/reindex",
        "GET /api/v1/rag-spaces/admin/system-spaces/{space_name}/staleness",
        "DELETE /api/v1/rag-spaces/{space_id}",
        "GET /api/v1/rag-spaces/{space_id}",
        "PATCH /api/v1/rag-spaces/{space_id}",
        "POST /api/v1/rag-spaces/{space_id}/documents",
        # Document operations (ADR-259): the same surface as upload/delete —
        # a visitor's own documents, in the visitor's own spaces.
        "GET /api/v1/rag-spaces/{space_id}/documents/archive",
        "POST /api/v1/rag-spaces/{space_id}/documents/bulk-delete",
        "POST /api/v1/rag-spaces/{space_id}/documents/move",
        "GET /api/v1/rag-spaces/{space_id}/documents/{document_id}/download",
        "DELETE /api/v1/rag-spaces/{space_id}/documents/{document_id}",
        "GET /api/v1/rag-spaces/{space_id}/documents/{document_id}/status",
        "GET /api/v1/rag-spaces/{space_id}/drive-browse",
        "GET /api/v1/rag-spaces/{space_id}/drive-sources",
        "POST /api/v1/rag-spaces/{space_id}/drive-sources",
        "DELETE /api/v1/rag-spaces/{space_id}/drive-sources/{source_id}",
        "POST /api/v1/rag-spaces/{space_id}/drive-sources/{source_id}/sync",
        "GET /api/v1/rag-spaces/{space_id}/drive-sources/{source_id}/sync-status",
        # Mail source (ADR-262): the visitor's own Gmail labels, in their own spaces.
        "GET /api/v1/rag-spaces/{space_id}/mail-labels",
        "GET /api/v1/rag-spaces/{space_id}/mail-sources",
        "POST /api/v1/rag-spaces/{space_id}/mail-sources",
        "DELETE /api/v1/rag-spaces/{space_id}/mail-sources/{source_id}",
        "POST /api/v1/rag-spaces/{space_id}/mail-sources/{source_id}/sync",
        "GET /api/v1/rag-spaces/{space_id}/mail-sources/{source_id}/sync-status",
        "PATCH /api/v1/rag-spaces/{space_id}/toggle",
        "DELETE /api/v1/relations/favorites/{name}",
        "PUT /api/v1/relations/favorites/{name}",
        "POST /api/v1/relations/merges",
        "DELETE /api/v1/relations/merges/{name}",
        "GET /api/v1/relations/overview-scope",
        "PUT /api/v1/relations/overview-scope",
        "GET /api/v1/relations/{name}",
        "GET /api/v1/relations/{name}/context",
        "GET /api/v1/reminders",
        "DELETE /api/v1/reminders/{reminder_id}",
        "GET /api/v1/scheduled-actions",
        "POST /api/v1/scheduled-actions",
        "DELETE /api/v1/scheduled-actions/{action_id}",
        "PATCH /api/v1/scheduled-actions/{action_id}",
        "POST /api/v1/scheduled-actions/{action_id}/execute",
        "PATCH /api/v1/scheduled-actions/{action_id}/toggle",
        "GET /api/v1/skills",
        "POST /api/v1/skills/admin/import",
        "GET /api/v1/skills/admin/list",
        "DELETE /api/v1/skills/admin/{skill_name}",
        "PATCH /api/v1/skills/admin/{skill_name}/description",
        "GET /api/v1/skills/admin/{skill_name}/download",
        "PATCH /api/v1/skills/admin/{skill_name}/system-toggle",
        "POST /api/v1/skills/admin/{skill_name}/translate-description",
        "POST /api/v1/skills/import",
        "POST /api/v1/skills/import-from-url",
        "POST /api/v1/skills/reload",
        "DELETE /api/v1/skills/{skill_name}",
        "GET /api/v1/skills/{skill_name}/download",
        "GET /api/v1/skills/{skill_name}/preview",
        "PATCH /api/v1/skills/{skill_name}/toggle",
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
        "GET /api/v1/users/search/by-email",
        "GET /api/v1/users/timezones",
        "DELETE /api/v1/users/{user_id}",
        "GET /api/v1/users/{user_id}",
        "PATCH /api/v1/users/{user_id}",
        "POST /api/v1/voice/ticket",
    }
)


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


def _mounted_routes() -> set[str]:
    """Every "METHOD /path" the API actually mounts, prefix included."""
    from src.api.v1.routes import api_router

    routes: set[str] = set()
    for route in api_router.routes:
        path = "/api/v1" + str(getattr(route, "path", ""))
        for method in getattr(route, "methods", None) or []:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.add(f"{method} {path}")
    return routes


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
