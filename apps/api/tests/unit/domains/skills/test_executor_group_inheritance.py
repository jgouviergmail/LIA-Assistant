"""Supplementary-group inheritance in the skill sandbox — SEC-001 baseline.

``test_executor_socket_isolation.py`` proves the privilege drop works, but it is
skipped unless the test process is **root**. Production is the opposite case:
the API runs as ``appuser`` (uid 1000, ``USER appuser`` in ``Dockerfile.prod``)
with the host Docker gid added via ``group_add``, and ``/var/run/docker.sock``
mounted read-write. Under that uid the drop is never armed
(``executor.py`` only sets ``drop_uid`` when ``os.geteuid() == 0``), so the
forked script keeps every supplementary group — including ``docker``.

``env -i`` scrubs the environment, not Unix credentials: groups survive both
``fork`` and ``exec``.

These tests pin that invariant at the only place it is decided —
``_build_rlimit_preexec`` — without needing root, a Docker socket, or a real
subprocess. ``test_groups_are_not_cleared_without_drop`` asserts the *defect*:
invert it once the sandbox guarantees a group-free child.
"""

from __future__ import annotations

import platform
from unittest.mock import MagicMock

import pytest

from src.domains.skills.executor import _build_rlimit_preexec

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="POSIX credential APIs (setgroups/setgid/setuid) and `resource` are POSIX-only",
)

_UNPRIVILEGED_UID = 65534
_UNPRIVILEGED_GID = 65534


def _apply_preexec(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> dict[str, MagicMock]:
    """Build a preexec callable and run it with credential syscalls mocked.

    The real ``setgroups``/``setgid``/``setuid`` would mutate the test process,
    so they are replaced by recorders. ``resource.setrlimit`` is neutralised for
    the same reason: lowering RLIMIT_NPROC in the pytest process is destructive.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        **kwargs: Overrides forwarded to ``_build_rlimit_preexec``.

    Returns:
        Mapping of syscall name to its recorder mock.
    """
    import os
    import resource

    recorders = {
        "setgroups": MagicMock(),
        "setgid": MagicMock(),
        "setuid": MagicMock(),
    }
    for name, mock in recorders.items():
        monkeypatch.setattr(os, name, mock, raising=False)
    monkeypatch.setattr(resource, "setrlimit", MagicMock(), raising=False)

    params: dict[str, object] = {
        "max_memory_mb": 512,
        "max_processes": 64,
        "max_file_size_mb": 10,
        "max_cpu_seconds": 30,
    }
    params.update(kwargs)

    preexec = _build_rlimit_preexec(**params)  # type: ignore[arg-type]
    assert preexec is not None, "POSIX platforms must return a preexec callable"
    preexec()
    return recorders


class TestSupplementaryGroupInheritance:
    """What the child process inherits, with and without a privilege drop."""

    def test_groups_are_cleared_when_drop_is_armed(self, monkeypatch: pytest.MonkeyPatch):
        """With a drop (API running as root), groups are reset to the target gid.

        This is the protective path, and the ordering matters: ``setgroups``
        must run before ``setuid``, otherwise the process has already lost the
        privilege required to change its groups.
        """
        recorders = _apply_preexec(
            monkeypatch,
            drop_to_uid=_UNPRIVILEGED_UID,
            drop_to_gid=_UNPRIVILEGED_GID,
        )

        recorders["setgroups"].assert_called_once_with([_UNPRIVILEGED_GID])
        recorders["setgid"].assert_called_once_with(_UNPRIVILEGED_GID)
        recorders["setuid"].assert_called_once_with(_UNPRIVILEGED_UID)

    def test_groups_are_not_cleared_without_drop(self, monkeypatch: pytest.MonkeyPatch):
        """DEFECT (SEC-001): no drop ⇒ no ``setgroups`` ⇒ ``docker`` survives.

        This is the production configuration: the API runs as uid 1000, so
        ``executor.py`` leaves ``drop_uid`` as ``None`` and the sandbox never
        clears supplementary groups. A skill script therefore inherits the
        ``docker`` group and can open the mounted socket.

        Removing a supplementary group requires ``CAP_SETGID``, which a non-root
        ``USER`` does not hold — which is why the fix cannot be a one-liner here
        and has to remove the socket/group from the API or run the script in an
        isolated container.
        """
        recorders = _apply_preexec(monkeypatch, drop_to_uid=None, drop_to_gid=None)

        recorders["setgroups"].assert_not_called()
        recorders["setgid"].assert_not_called()
        recorders["setuid"].assert_not_called()

    def test_partial_drop_configuration_is_ignored(self, monkeypatch: pytest.MonkeyPatch):
        """A uid without a gid performs no credential change at all.

        Guards against a future refactor calling ``setuid`` without the
        preceding ``setgroups``/``setgid`` — which would drop privileges while
        keeping the dangerous groups, the worst of both worlds.
        """
        recorders = _apply_preexec(monkeypatch, drop_to_uid=_UNPRIVILEGED_UID, drop_to_gid=None)

        recorders["setgroups"].assert_not_called()
        recorders["setgid"].assert_not_called()
        recorders["setuid"].assert_not_called()
