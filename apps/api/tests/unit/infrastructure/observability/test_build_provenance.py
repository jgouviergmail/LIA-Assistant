"""Build-provenance guard (audit F030).

Pins the single source of runtime provenance (version + commit + build date) and
prevents the stale hardcoded OTel ``service.version`` ("0.1.0") from creeping back.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.core.config import Settings
from src.core.constants import GIT_COMMIT_SHA_DEFAULT
from tests._repo_paths import find_apps_api_root

_TRACING_SRC = find_apps_api_root() / "src" / "infrastructure" / "observability" / "tracing.py"


def _settings(**env: str) -> Settings:
    with patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


class TestBuildRelease:
    def test_combines_version_and_short_sha(self):
        s = _settings(APP_VERSION="1.24.0", GIT_COMMIT_SHA="abcdef0123456789")
        assert s.app_version == "1.24.0"
        assert s.build_release == "1.24.0+abcdef012345"  # 12-char short sha

    def test_bare_version_when_sha_not_injected(self):
        # GitHub Actions always injects GITHUB_SHA — both aliases must be
        # scrubbed for "not injected" to hold on CI runners too (patch.dict
        # restores the popped keys on exit).
        with patch.dict(os.environ, {"APP_VERSION": "1.24.0"}, clear=False):
            os.environ.pop("GIT_COMMIT_SHA", None)
            os.environ.pop("GITHUB_SHA", None)
            s = Settings(_env_file=None)
            # No commit env → default sentinel → release is just the version.
            assert s.git_commit_sha == GIT_COMMIT_SHA_DEFAULT
            assert s.build_release == "1.24.0"

    def test_accepts_github_sha_alias(self):
        # CI exposes GITHUB_SHA; the field must read it too.
        with patch.dict(os.environ, {"GITHUB_SHA": "cafebabe0000"}, clear=False):
            os.environ.pop("GIT_COMMIT_SHA", None)
            s = Settings(_env_file=None)
            assert s.git_commit_sha == "cafebabe0000"


class TestTracingNoHardcodedVersion:
    def test_tracing_does_not_hardcode_service_version(self):
        src = _TRACING_SRC.read_text(encoding="utf-8")
        assert '"0.1.0"' not in src, (
            "OTel service.version must come from settings.app_version, not a "
            "hardcoded literal (audit F030)."
        )

    def test_tracing_reads_app_version_from_settings(self):
        src = _TRACING_SRC.read_text(encoding="utf-8")
        assert "settings.app_version" in src
        assert "settings.git_commit_sha" in src
