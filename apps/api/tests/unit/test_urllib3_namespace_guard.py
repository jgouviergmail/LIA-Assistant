"""Guard: the urllib3-future fork must not clobber the genuine urllib3 (AC-001).

``caldav -> niquests -> urllib3-future`` is a runtime dependency chain. The
urllib3-future *wheel* overwrites the genuine ``urllib3`` package on disk and
installs a ``.pth`` hook that re-clobbers it at every interpreter start.
docker-py subclasses urllib3 pool internals, so the fork breaks
docker-py/testcontainers on Windows named pipes with
``NpipeHTTPConnectionPool._get_conn() got an unexpected keyword argument
'heb_timeout'`` — which silently skipped 420/559 integration tests.

The install contract (apps/api/requirements.txt) builds urllib3-future from
sdist with ``URLLIB3_NO_OVERRIDE=1`` and ``--no-binary urllib3-future``: the
genuine urllib3 then owns the ``urllib3`` namespace and the fork lives only
under ``urllib3_future`` (niquests detects this and uses the fork namespace).

These tests fail on any environment rebuilt without that contract — e.g. a
lockfile regenerated or installed without the ``--no-binary`` flag.
"""

from pathlib import Path


def test_urllib3_is_genuine_not_the_fork() -> None:
    """The importable ``urllib3`` must be the genuine package, not the fork.

    Fork versions use a >=900 micro component (e.g. 2.17.901) — the same
    convention niquests itself relies on to detect which package it got.
    """
    import urllib3

    micro = int(urllib3.__version__.split(".")[-1])
    assert micro < 900, (
        f"urllib3 {urllib3.__version__} is the urllib3-future fork — the wheel "
        "clobbered the genuine package. Rebuild the environment with "
        "URLLIB3_NO_OVERRIDE=1 pip install --require-hashes "
        "--no-binary urllib3-future -r requirements-dev.lock.txt"
    )


def test_urllib3_future_namespace_is_isolated() -> None:
    """The fork must be importable under its own ``urllib3_future`` namespace."""
    import urllib3_future

    micro = int(urllib3_future.__version__.split(".")[-1])
    assert micro >= 900, "urllib3_future should be the fork (micro >= 900)"


def test_no_reclobbering_pth_hook_installed() -> None:
    """The wheel's ``urllib3_future.pth`` startup hook must be absent.

    That hook deletes the genuine ``urllib3/`` directory and copies the fork
    over it at every interpreter start, undoing any manual repair.
    """
    import urllib3_future

    site_packages = Path(urllib3_future.__file__).resolve().parent.parent
    pth = site_packages / "urllib3_future.pth"
    assert not pth.exists(), (
        f"{pth} exists: urllib3-future was installed from its clobbering wheel. "
        "Reinstall with URLLIB3_NO_OVERRIDE=1 and --no-binary urllib3-future."
    )


def test_niquests_detects_genuine_urllib3() -> None:
    """niquests must route through ``urllib3_future``, not the clobbered name."""
    from niquests._compat import HAS_LEGACY_URLLIB3

    assert HAS_LEGACY_URLLIB3 is True, (
        "niquests sees the fork under the 'urllib3' name — namespace collision "
        "is back (see module docstring for the repair command)."
    )
