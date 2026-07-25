"""Guard: the FCM webpush icon must name a frontend asset that exists.

Regression 2026-07-24. ``WebpushNotification(icon=...)`` pointed at
``/icon-192x192.png``, a file that has never existed in ``apps/web/public/``.
Nothing failed: Next.js answers unknown paths with the HTML app shell, the
browser cannot decode it as an image and silently falls back to a generic
bell — so every push notification shipped unbranded, on both the backend
payload and the service worker, with no error anywhere to notice it by.

The path is a *frontend* asset referenced from *backend* code, so no type
checker, linter or HTTP status can catch a typo. This test is the only thing
that can. Its twin on the web side is
``apps/web/src/__tests__/service-worker.test.ts``.
"""

import re

import pytest

from src.core.constants import FCM_WEBPUSH_ICON_PATH
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

# Reaches outside apps/api, so it needs the monorepo root — via the shared
# helper, never a fixed `parents[n]` (audit F050: a hard-coded depth breaks
# under the flat apps/api mount, where the guard must skip, not error).
_WEB_PUBLIC = repo_root_or_skip() / "apps" / "web" / "public"
_SERVICE_WORKER = _WEB_PUBLIC / "firebase-messaging-sw.js"


def test_webpush_icon_exists_in_web_public() -> None:
    """The configured icon must resolve to a real file in apps/web/public/."""
    assert FCM_WEBPUSH_ICON_PATH.startswith("/"), "icon must be an absolute web path"

    asset = _WEB_PUBLIC / FCM_WEBPUSH_ICON_PATH.lstrip("/")
    assert asset.is_file(), f"{FCM_WEBPUSH_ICON_PATH} is not a file under apps/web/public/"


def test_webpush_icon_matches_the_service_worker() -> None:
    """Backend and service worker must brand notifications identically.

    A push rendered by the browser from the FCM payload and one rendered by
    the service worker's ``showNotification`` must not show different icons.
    """
    source = _SERVICE_WORKER.read_text(encoding="utf-8")
    # Read code, not prose: comments quote the old broken path on purpose.
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))
    match = re.search(r"^\s*icon:\s*'([^']+)'", code, re.MULTILINE)

    assert match is not None, "no icon option found in the service worker"
    assert match.group(1) == FCM_WEBPUSH_ICON_PATH
