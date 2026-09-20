"""Voice sessions — what a spoken conversation with LIA IS, whichever line carries it (ADR-301).

Two carriers run a voice session: the browser (ADR-299, ADR-300: a provider
socket on the person's own key) and the phone (ADR-290: the vendor's agent on
the person's own line). Each keeps its own record — a Redis record that lives
minutes, a durable ``phone_calls`` row with four sweeps — because their life
cycles differ, and forcing two life cycles into one table produces nullable
columns and ``if carrier ==`` everywhere. What they SHARE is behaviour, and it
lives here as values and rules:

- :mod:`session` — the value (key, run id, mode, carrier, account,
  conversation) and the ONE metadata key both carriers file under;
- :mod:`transcript` — the voice-only exchanges, read from a vendor payload or
  from a session record, each turn knowing whether it was delegated;
- :mod:`projection` — what an answer becomes before a voice says it
  (flattened, bounded), mirrored byte for byte by the browser's own
  ``flattenForVoice`` through a shared corpus;
- :mod:`summary` — the queries the closing card and the bills read;
- :mod:`mandate` — the prompt blocks every voice mandate composes.

What DRIVES a session — the delegation bridge, the closing policy, the relay
— lives in ``infrastructure/scheduler`` beside the workboard and phone-relay
runners, for the reason those runners are there: it drives the chat engine
and reads the registers, and ``telephony`` must not import ``agents`` (the T2
cycle). This package imports no carrier (``live``, ``telephony``) and, of
``agents``, only the pure plain-text door (``projection``).
"""
