"""Open Loops bounded context — commitments ledger (P5, ADR-139).

Tracks commitments surfaced in conversation: things the user owes someone
and things the user is waiting on. Extraction happens post-response
(``agents/services/open_loop_extractor``); nudging flows through the
heartbeat decision context.
"""
