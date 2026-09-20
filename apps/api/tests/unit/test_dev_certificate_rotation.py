"""The dev TLS certificate is renewed on what it IS, never on how old it is.

``infrastructure/ssl/generate-certs.sh`` runs at every start of the dev stack
(``ssl-init``, a dependency of ``api`` and ``web``). It used to throw away any
certificate older than 30 days although it issues them for 365 — so the first
restart after a month served a NEW certificate to a browser that trusted the
OLD one (``task dev:trust-cert``): « Your connection is not private » again,
and WebAuthn refused every ceremony (measured 2026-09-19: the trusted
fingerprint dated 2026-07-20, the served one 2026-09-19 07:14, both valid to
2027).

The rule now: a certificate is KEPT while it is valid past the renewal window,
covers ``SSL_DOMAIN`` (and the LAN IP a nip.io domain names) and matches its
key; it is regenerated otherwise, and the script says which case applied.
The executable tests drive the real script on a temporary directory and are
skipped only where a POSIX shell or ``openssl`` is unavailable (CI has both).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
SCRIPT = ROOT / "infrastructure" / "ssl" / "generate-certs.sh"


def test_the_script_decides_on_expiry_and_coverage_never_on_age() -> None:
    """The regression that broke the trust store was an AGE check; it must not return."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "-mtime" not in text, "a certificate's age says nothing about its validity"
    assert "-checkend" in text, "renewal is decided against the certificate's own expiry"
    assert "subjectAltName" in text, "a domain change must be caught, not served stale"


def _tool(name: str) -> str | None:
    return shutil.which(name)


def _fingerprint(cert: Path) -> str:
    out = subprocess.run(
        [
            _tool("openssl") or "openssl",
            "x509",
            "-in",
            cert.as_posix(),
            "-noout",
            "-fingerprint",
            "-sha256",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return out.stdout.strip()


def _issue(cert_dir: Path, domain: str, *, days: int) -> None:
    """A certificate the way a previous run would have left it, with ``days`` of life."""
    openssl = _tool("openssl") or "openssl"
    subprocess.run(
        [openssl, "genrsa", "-out", (cert_dir / "key.pem").as_posix(), "2048"],
        capture_output=True,
        check=True,
        timeout=120,
    )
    subprocess.run(
        [
            openssl,
            "req",
            "-new",
            "-x509",
            "-key",
            (cert_dir / "key.pem").as_posix(),
            "-out",
            (cert_dir / "cert.pem").as_posix(),
            "-days",
            str(days),
            "-subj",
            f"/C=FR/ST=Dev/L=Dev/O=LIA/CN={domain}",
            "-addext",
            f"subjectAltName=DNS:{domain},DNS:localhost,IP:127.0.0.1",
        ],
        capture_output=True,
        check=True,
        timeout=120,
    )


@pytest.mark.skipif(
    _tool("sh") is None or _tool("openssl") is None, reason="sh/openssl unavailable"
)
class TestGenerateCerts:
    def _run(self, cert_dir: Path, domain: str, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "CERT_DIR": cert_dir.as_posix(),
            "SSL_DOMAIN": domain,
            # Git Bash on Windows rewrites `/C=FR/...` into a path for a native
            # openssl; inert on the Linux CI runner and inside the container.
            "MSYS_NO_PATHCONV": "1",
            **extra,
        }
        return subprocess.run(
            [_tool("sh") or "sh", SCRIPT.as_posix()],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )

    def test_a_fresh_volume_gets_a_certificate_covering_the_domain_and_the_lan_ip(
        self, tmp_path: Path
    ) -> None:
        proc = self._run(tmp_path, "192.168.1.100.nip.io")
        assert proc.returncode == 0, proc.stderr
        assert "generated" in proc.stdout.lower()
        san = subprocess.run(
            [
                _tool("openssl") or "openssl",
                "x509",
                "-in",
                (tmp_path / "cert.pem").as_posix(),
                "-noout",
                "-ext",
                "subjectAltName",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        ).stdout
        assert "DNS:192.168.1.100.nip.io" in san
        assert "IP Address:192.168.1.100" in san
        assert "DNS:localhost" in san

    def test_a_valid_certificate_is_kept_whatever_its_age(self, tmp_path: Path) -> None:
        # The defect: a 61-day-old certificate with 300 days of life left was
        # regenerated at every restart, and the browser's trust went with it.
        _issue(tmp_path, "localhost", days=300)
        before = _fingerprint(tmp_path / "cert.pem")
        old = time.time() - 61 * 86400
        os.utime(tmp_path / "cert.pem", (old, old))
        os.utime(tmp_path / "key.pem", (old, old))
        proc = self._run(tmp_path, "localhost")
        assert proc.returncode == 0, proc.stderr
        assert "kept" in proc.stdout.lower()
        assert _fingerprint(tmp_path / "cert.pem") == before

    def test_a_certificate_inside_the_renewal_window_is_regenerated(self, tmp_path: Path) -> None:
        _issue(tmp_path, "localhost", days=5)
        before = _fingerprint(tmp_path / "cert.pem")
        proc = self._run(tmp_path, "localhost", SSL_RENEW_BEFORE_DAYS="30")
        assert proc.returncode == 0, proc.stderr
        assert "expires" in proc.stdout.lower()
        assert _fingerprint(tmp_path / "cert.pem") != before

    def test_a_certificate_that_no_longer_covers_the_domain_is_regenerated(
        self, tmp_path: Path
    ) -> None:
        # SSL_DOMAIN changed in .env (a new LAN address): the old SAN is stale.
        _issue(tmp_path, "localhost", days=300)
        before = _fingerprint(tmp_path / "cert.pem")
        proc = self._run(tmp_path, "10.0.0.7.nip.io")
        assert proc.returncode == 0, proc.stderr
        assert "cover" in proc.stdout.lower()
        assert _fingerprint(tmp_path / "cert.pem") != before

    def test_a_failed_issuance_is_loud_and_keeps_the_previous_pair(self, tmp_path: Path) -> None:
        # The script used to swallow the issuance error and announce a
        # certificate with an empty fingerprint over a directory holding a key alone.
        _issue(tmp_path, "localhost", days=5)
        before = _fingerprint(tmp_path / "cert.pem")
        proc = self._run(tmp_path, "localhost", SSL_CERT_DAYS="not-a-number")
        assert proc.returncode != 0
        assert "issuance failed" in proc.stderr.lower()
        assert _fingerprint(tmp_path / "cert.pem") == before
        assert not (tmp_path / "cert.pem.new").exists()
        assert not (tmp_path / "key.pem.new").exists()

    def test_a_key_that_does_not_match_its_certificate_is_regenerated(self, tmp_path: Path) -> None:
        # A generation interrupted between the key and the certificate: the
        # servers would refuse to start on the pair.
        _issue(tmp_path, "localhost", days=300)
        before = _fingerprint(tmp_path / "cert.pem")
        subprocess.run(
            [
                _tool("openssl") or "openssl",
                "genrsa",
                "-out",
                (tmp_path / "key.pem").as_posix(),
                "2048",
            ],
            capture_output=True,
            check=True,
            timeout=120,
        )
        proc = self._run(tmp_path, "localhost")
        assert proc.returncode == 0, proc.stderr
        assert "match" in proc.stdout.lower()
        assert _fingerprint(tmp_path / "cert.pem") != before
