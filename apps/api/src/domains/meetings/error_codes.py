"""Error codes stored on a meeting row (``last_error_code``) — the frontend maps them.

One module, imported by the job (which classifies failures) and by the
repository (whose reaper dead-letters a lost worker), so neither depends on
the other for a string.
"""

from __future__ import annotations

ERROR_USAGE_LIMIT = "usage_limit"
ERROR_NO_ENGINE = "no_engine_available"
ERROR_NORMALIZE = "audio_normalize_failed"
ERROR_AUDIO_UNAVAILABLE = "audio_unavailable"
ERROR_SYNTHESIS = "synthesis_failed"
ERROR_UNEXPECTED = "unexpected"
#: The worker stopped heartbeating with no retry budget left (reaper dead-letter).
ERROR_WORKER_LOST = "worker_lost"
