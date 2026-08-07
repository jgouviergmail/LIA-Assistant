"""Instance-wide switches for what the platform OFFERS.

Distinct from ``domains/capabilities``, which answers "what can LIA do for
THIS ACCOUNT right now" by probing every subsystem. This package answers
"what does the operator allow this INSTANCE to offer at all" — a much smaller,
much colder question, and one that must stay a LEAF: routers across every
domain import it, so importing any domain back would close a cycle (F009).

The capability map is a legitimate CONSUMER of these switches: a feature the
operator switched off is reported "unavailable" there.
"""
