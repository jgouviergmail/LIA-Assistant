"""Complete journal rendering and eligible snapshot references for consolidation."""

from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_catalogue import journal_item_id


def format_all_entries(entries: list[JournalEntry]) -> str:
    """Format all active entries for the consolidation prompt.

    Shows full content for every entry with the full epistemic metadata so the
    LLM can reason about lifecycle (entries never injected, validated directives,
    contradicted hypotheses) and act accordingly during maintenance.

    The metadata exposed in each entry header:
        - created: original creation date
        - last_inj: last time the entry was injected into a prompt (or "never")
        - uses: total injection count
        - conf: epistemic status (low/medium/high)
        - ev/co: evidence and contradiction counters from deferred self-evaluation
        - char_count: content character count
        - hints: search hints (or "MISSING")

    Args:
        entries: All active entries ordered by created_at desc

    Returns:
        Formatted entries string
    """
    if not entries:
        return "No entries to review."

    # ID reference table for easy copy-paste
    id_lines = ["### ENTRY ID REFERENCE (copy-paste these exact IDs for update/delete):"]
    for entry in entries:
        id_lines.append(f"- {entry.id}  →  {entry.title}")

    # Full entries with epistemic metadata
    entry_lines = []
    for entry in entries:
        created_str = entry.created_at.strftime("%Y-%m-%d")
        last_inj_str = (
            entry.last_injected_at.strftime("%Y-%m-%d") if entry.last_injected_at else "never"
        )
        hints_str = (
            f" | hints: {', '.join(entry.search_hints)}"
            if entry.search_hints
            else " | hints: MISSING"
        )
        portrait_reference = (
            f" | portrait_item_id={journal_item_id(entry)}"
            if entry.level in ("L1", "L2", "L3")
            and entry.confidence in ("medium", "high")
            and entry.contradiction_count == 0
            else ""
        )
        entry_lines.append(
            f"[id={entry.id} | created={created_str} | last_inj={last_inj_str} "
            f"| uses={entry.injection_count} | conf={entry.confidence} "
            f"| ev={entry.evidence_count}/co={entry.contradiction_count} "
            f"| level={entry.level} | revision={getattr(entry, 'revision', 1)} "
            f"| {entry.theme} | {entry.mood} | {entry.char_count} chars{hints_str}{portrait_reference}]\n"
            f"**{entry.title}**\n{entry.content}\n"
        )

    return "\n".join(id_lines) + "\n\n---\n" + "\n---\n".join(entry_lines)
