"""Controlled egress of a sandbox run (ADR-298).

A network run lives in three places that must agree: the Redis registry of
live runs (every worker's), the proxy ruleset rendered from that registry, and
the throwaway container that holds the run's opaque tokens. This package owns
the first two and hands the executor what the third needs.
"""
