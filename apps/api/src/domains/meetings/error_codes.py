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
#: The model was cut at its output budget while writing the minutes (ADR-275).
#: PERMANENT by nature: the same transcript through the same prompt is cut at
#: the same place, so a requeue would buy the identical refusal.
ERROR_SYNTHESIS_TOO_LONG = "synthesis_too_long"
ERROR_UNEXPECTED = "unexpected"
#: The worker stopped heartbeating with no retry budget left (reaper dead-letter).
ERROR_WORKER_LOST = "worker_lost"
#: An imported file is longer than the instance's recording cap — judged on the
#: length ffprobe measured, before any engine is paid (owner request 2026-10-24).
ERROR_IMPORT_TOO_LONG = "import_too_long"
#: ffmpeg cannot read an imported file through the demuxer of its format.
ERROR_AUDIO_UNREADABLE = "audio_unreadable"
#: An import whose upload stopped before it was complete (reaper).
ERROR_IMPORT_INCOMPLETE = "import_incomplete"
