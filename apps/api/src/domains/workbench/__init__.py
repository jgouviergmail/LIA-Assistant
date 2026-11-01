"""The workbench: the person's own door to their connected services (ADR-369).

The « Tools » section of the dashboard reads and acts on the person's mailbox,
calendar, tasks, contacts, Drive files and Hue lights BY HAND — no model in the
path, no register row (these are not acts of LIA), no table of its own. Every
provider client is opened through the ADR-304 door, every refusal is a stable
``detail.code``, and every bound it enforces is published by ``GET /workbench``.
"""
