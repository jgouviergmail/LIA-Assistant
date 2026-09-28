"""Radio domain constants — the station's editorial rules, stated once.

These are product rules of the grid and of the script contract, not deployment
settings: what an operator tunes (the timer, the daily cap, the verification
mode, the look-ahead) is a setting, never a constant of this module. A value
here changes the station's grammar for everybody, so it moves with a test,
never with an environment variable.
"""

from __future__ import annotations

from typing import Final

# =============================================================================
# Grid — the antenna's rhythm (tokenFM's published rules, read 2026-09-25, then
# adapted to a session a person starts and stops).
# =============================================================================

#: The station names itself at least this often (tokenFM: every 20 minutes).
STATION_ID_INTERVAL_SECONDS: Final[int] = 20 * 60

#: No more than this many briefs inside one rolling window (tokenFM: three per
#: half hour) — past it, a run of one-minute items stops sounding like a radio.
BRIEF_WINDOW_SECONDS: Final[int] = 30 * 60
BRIEF_MAX_PER_WINDOW: Final[int] = 3

#: When the automatic stop is this close, the next segment is the sign-off: a
#: station that goes silent mid-sentence sounds broken, one that says goodbye
#: sounds finished.
SIGN_OFF_WINDOW_SECONDS: Final[int] = 75

#: The most notifications one news flash tells (ADR-324 decision 32): the format's
#: stories bound and the flash module's, one value.
FLASH_NOTES_MAX: Final[int] = 3

#: A bulletin that falls within this long after the top of an hour is « the
#: nine o'clock news »; later than that it would be a stale promise.
TOP_OF_HOUR_GRACE_SECONDS: Final[int] = 20 * 60

#: Headlines at twenty and forty past (tokenFM's own marks), announced as such
#: only when the segment airs within this long after the mark.
HEADLINES_MARK_MINUTES: Final[tuple[int, ...]] = (20, 40)
HEADLINES_MARK_GRACE_SECONDS: Final[int] = 10 * 60

#: The listener's journal has three editions on their clock (ADR-324 decision 41):
#: the morning's until the first hour, the noon's from it, the evening's from the
#: second. A session hears the journal of the edition it starts in, and once more
#: when it crosses into another.
JOURNAL_NOON_FROM_HOUR: Final[int] = 12
JOURNAL_EVENING_FROM_HOUR: Final[int] = 18

#: A voice line refused on a provider's QUOTA waits this long before its second
#: attempt when the provider names no delay, and twice as long before each next
#: one (bounded by a setting): waits of one then two seconds met the same quota
#: three times over (measured 2026-09-26), and each lost segment had already
#: paid its voices.
TTS_RATE_LIMIT_BASE_WAIT_SECONDS: Final[float] = 5.0

#: A format whose production failed rests this long, or its own gap when that is
#: longer, before the grid plans it again: a failure is paid for, and the same
#: attempt at once mostly fails the same way (measured 2026-09-26: six analyses
#: in twenty minutes, every one refused, each one billed).
FAILED_FORMAT_REST_SECONDS: Final[int] = 5 * 60

#: What a listener's radio may spend is counted over this rolling window (ADR-324
#: decision 37): the amount is the operator's (``RADIO_BUDGET_24H_EUR``), the day
#: is the rule's.
BUDGET_WINDOW_SECONDS: Final[int] = 24 * 3600

#: Every run the radio bills to a listener starts with this — a session
#: (``radio_<hex>``) and an article's translation (``radio_article_<hex>``): the
#: budget finds what the radio spent by it, so it is spelled once.
RADIO_RUN_ID_PREFIX: Final[str] = "radio_"

#: The station's music follows the listener's day: morning music over these local
#: hours (the evening's starts with the journal's evening edition,
#: ``JOURNAL_EVENING_FROM_HOUR`` — one notion of evening), calm music over the rest;
#: news is read over its own.
MUSIC_MORNING_FROM_HOUR: Final[int] = 5
MUSIC_MORNING_UNTIL_HOUR: Final[int] = 12

# =============================================================================
# Speech — how many characters a minute of spoken radio holds, per language.
# French MEASURED on 2026-09-26 on four engines (510 characters: 876 to 1 129
# per minute, median about 1 000). The others are typical broadcast rates; they
# size a request, they never truncate an answer.
# =============================================================================

SPEECH_CHARS_PER_MINUTE: Final[dict[str, int]] = {
    "fr": 1000,
    "en": 900,
    "de": 950,
    "es": 1050,
    "it": 1000,
    # Mandarin is counted in characters, and one character carries a syllable:
    # a word count would not exist here at all (the ADR-274 lesson).
    "zh-CN": 280,
}

#: A script longer than its format's maximum by more than this factor is
#: REFUSED rather than cut (ADR-275: a shortened answer announced as whole is
#: the defect, not the length).
SCRIPT_LENGTH_TOLERANCE: Final[float] = 1.3

# =============================================================================
# Script contract — bounds the writer is told and the verifier enforces.
# =============================================================================

LINE_MAX_CHARS: Final[int] = 700
SCRIPT_TITLE_MAX_CHARS: Final[int] = 80
REFS_MAX_PER_LINE: Final[int] = 6
INTRO_OUTRO_MAX_LINES: Final[int] = 2

#: Small integers a TRANSITION line may say without a source (« three
#: headlines », « two guests »): the programme's own structure, not a claim
#: about the world. Anything larger, and any number in a factual line, must be
#: found in a cited fact.
TRANSITION_FREE_INTEGER_MAX: Final[int] = 10

#: A segment whose verification drops more than this share of its sourced lines
#: is refused whole: past it, what remains is no longer the segment that was
#: written.
MAX_DROPPED_LINE_RATIO: Final[float] = 0.25

# =============================================================================
# Facts — what one fact may carry into a prompt.
# =============================================================================

FACT_TEXT_MAX_CHARS: Final[int] = 2000
FACT_KEY_MAX_CHARS: Final[int] = 200
SOURCE_LABEL_MAX_CHARS: Final[int] = 120

# =============================================================================
# Spend — what a session tells its listener about its cost.
# =============================================================================

#: What the estimate of an untimed session covers: an hour of listening.
ESTIMATE_OPEN_ENDED_SECONDS: Final[int] = 60 * 60

# =============================================================================
# Player protocol — what a report may say.
# =============================================================================

#: A report placing the player further than this into one segment is not a
#: position (no segment lasts an hour): refused at the door.
PLAYHEAD_POSITION_MAX_SECONDS: Final[int] = 3600
#: The longest URL the newsroom keeps — a feed's or an article's — in UTF-8
#: BYTES: a feed's address is indexed, and an index row holds bytes, not
#: characters. A longer one is not a URL anybody needs: it is not stored.
URL_MAX_BYTES: Final[int] = 2048
#: The longest validators a feed's server may hand back and have filed — an
#: ``ETag`` is opaque, a ``Last-Modified`` is a 29-character HTTP date. A longer
#: one is neither kept nor sent back: the next request is simply unconditional.
ETAG_MAX_CHARS: Final[int] = 512
LAST_MODIFIED_MAX_CHARS: Final[int] = 128
#: The longest language tag a feed may declare (« zh-Hans-CN » is ten): a
#: longer one is not a tag the station can use, so it reads as unknown.
LANGUAGE_TAG_MAX_CHARS: Final[int] = 16
#: The longest site address a listener may type to add a source: once a scheme
#: is added (``https://``), it must still be a URL the newsroom keeps.
SOURCE_ADDRESS_MAX_CHARS: Final[int] = URL_MAX_BYTES - len("https://")
#: The longest outlet name the station keeps — a feed's, or a story's own when a
#: search found it (ADR-324 decision 40).
OUTLET_MAX_CHARS: Final[int] = 160
#: The address of a listener's interest row: no feed any newsroom could read, and no
#: address a listener could add (a site is ``http(s)``) — the row is found by its kind.
INTEREST_FEED_URL: Final[str] = "lia:interests"
#: How long one request of the newsroom waits at most (to connect, and for each
#: read): a slow outlet costs a pass a few seconds, never the pass itself.
NEWSROOM_REQUEST_TIMEOUT_S: Final[float] = 15.0
#: How long looking for a site's feed may take in all (up to ~15 bounded
#: requests; measured 2026-09-26: 0.1 to 2 s on real sites): past it, the site
#: reads as unreachable rather than holding the listener's page open.
SOURCE_DISCOVERY_TIMEOUT_S: Final[float] = 30.0
#: How long a stopping worker waits for its cancelled loops (each releases its
#: lease on the way out): past it the teardown goes on, and a lease that was
#: not released lapses on its own.
LOOP_STOP_TIMEOUT_S: Final[float] = 5.0
