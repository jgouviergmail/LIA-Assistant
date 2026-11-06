"""Where a content policy goes in a document that will run in a frame.

A policy injected after a ``<head>`` found by a regex reads the document as text,
and the browser does not: a ``<head>`` inside a comment or a string puts the
policy nowhere, and a script before ``<head>`` runs ahead of it. Both leaked on
Chromium, Firefox and WebKit (measured 2026-11-04, ADR-370). Written first, the
policy needs no reading of the document at all. The browser opens the head on
it, then ignores the document's own doctype and ``<head>`` as parse errors and
merges its ``<html>`` attributes, so the page keeps its language and standards
mode.
"""

from __future__ import annotations


def with_leading_policy(policy_meta: str, document: str) -> str:
    """Put a content policy ahead of every byte of a document.

    Args:
        policy_meta: The ``<meta http-equiv="Content-Security-Policy">`` tag.
        document: The document, whatever it contains.

    Returns:
        The document under that policy, in standards mode.
    """
    return f'<!DOCTYPE html><meta charset="utf-8">{policy_meta}{document}'
