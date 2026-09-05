"""Durable ledger of the external effects LIA performs (ADR-263).

One row per external effect: CLAIMED before the effect happens, closed from an
explicit result, bound to the authority that allowed it. The ledger is the
source of FACTS about what was done; LangGraph state carries intentions and
verdicts, which is not the same thing (ADR-184).

Measured 2026-09-03, the three holes it closes:

- a confirmed draft could execute TWICE (the approval was never consumed);
- a ReAct call placed before an interrupted one was replayed on resume;
- nothing durable said which tool ran, under which approval, with what result.
"""
