"""Google push channels bounded context (lot H, 2026-08).

Phase 1: Calendar events.watch + Drive changes.watch channels pushing to a
verified webhook endpoint. Phase 2: Gmail users.watch through Pub/Sub.
Polling remains the fallback whenever push is disabled or stale.
"""
