"""A rewrite of a stored file that lands, for its stat identity, after the observation.

The stored-file checks (``LocalFileRead.identity_digest``) recognise a file by its
stat identity: device, inode, size, modification and change times. A filesystem
stamps a write with the tick of its clock, not the instant, so two writes inside
one tick carry the same times — and a same-size rewrite inside that tick is the
same file to its identity. Measured on Windows 2026-10-16: a 4-byte file rewritten
right after it was observed kept its identity in 3 rounds of 4, and the ``changed``
cases built that way failed 133 times in 500 (deletion cleanup) and 232 in 500
(move staging). Linux stamps finer once a timestamp has been read, which is why
the same tests stay green there.

A test meaning "the file changed after it was observed" models a LATER write: the
new bytes, then a modification time past any tick of the observed one, the way
git's own test suite sets times (``test-tool chmtime``) for the same race.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Past the coarsest modification-time step of any filesystem a test may run on
#: (FAT stores two seconds; NTFS and ext4 move by a clock tick of at most 15.6 ms).
PAST_ANY_TICK_NS = 2_000_000_000


def rewrite_later(path: Path, data: bytes) -> None:
    """Replace ``path``'s bytes, stamped past any tick of the write it replaces.

    Args:
        path: An existing file, observed before the call.
        data: Its new content, of any size — the same size included.
    """
    observed = path.stat()
    path.write_bytes(data)
    later = max(path.stat().st_mtime_ns, observed.st_mtime_ns + PAST_ANY_TICK_NS)
    os.utime(path, ns=(observed.st_atime_ns, later))


__all__ = ["PAST_ANY_TICK_NS", "rewrite_later"]
