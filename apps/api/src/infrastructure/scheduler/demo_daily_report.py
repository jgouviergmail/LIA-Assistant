"""Daily operator report for the public demonstrator.

The instance keeps its database in tmpfs and empties it at 02:30 UTC, so
everything it knows about a day disappears with the accounts it describes.
This report is therefore the only historised trace of the demonstrator's
activity: the operator's mailbox is the archive, and nothing has to be retained
on the instance — which is also how the terms' promise ("rien n'est conservé")
stays true while the operator still gets figures.

It travels the path the instance ALREADY uses for its verification emails: the
application talks to the private mail relay, the relay alone reaches the
smarthost. No new route, and none of the container-to-host isolation is
touched — unlike a metrics dashboard, which would have required a permanent
socket between the public stack and the private one.

Sent EVERY day (owner arbitration 2026-08-07). A report that only arrives when
something happened cannot be distinguished from a machine that stopped, so a
quiet day says so in words rather than by silence.

FRENCH ONLY, also an owner arbitration, and a deliberate departure from the
project's six-language rule: this goes to a single operator address, never to a
user. Every string lives in ``LABELS`` so a later internationalisation is a
substitution rather than a rewrite.

Created: 2026-08-07 (live-demonstrator programme)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select

from src.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Every user-facing string of the report, in one place. See the module
#: docstring for why they are not translated.
LABELS: dict[str, str] = {
    "subject_active": "Demonstrateur LIA - rapport du {day}",
    "subject_quiet": "Demonstrateur LIA - rapport du {day} (aucune activite)",
    "title": "Rapport quotidien du demonstrateur",
    "synthesis": "Synthese",
    "detail": "Detail",
    "quiet_day": "Aucune activite sur la periode : personne ne s'est inscrit et aucune conversation n'a eu lieu.",
    "alert_budget": "Plafond de depense presque atteint",
    "alert_signups": "Plafond d'inscriptions presque atteint",
    "no_limit": "aucun plafond configure",
    "visitors": "Comptes visiteurs",
    "verified": "dont adresses verifiees",
    "signups": "Inscriptions",
    "conversations": "Conversations",
    "user_messages": "Messages envoyes",
    "assistant_messages": "Reponses de LIA",
    "runs": "Executions facturees",
    "tokens_in": "Jetons en entree",
    "tokens_out": "Jetons en sortie",
    "tokens_cached": "Jetons en cache",
    "cost": "Cout de la journee",
    "budget": "Plafond quotidien",
    "signup_limit": "Plafond d'inscriptions",
    "footer": (
        "Ces chiffres sont agreges. Ils ne contiennent aucune donnee nominative, "
        "et la base du demonstrateur est supprimee chaque nuit."
    ),
    "period": "Periode close le {day} a {time} UTC",
}

#: Share of a ceiling above which the report says so in its synthesis.
ALERT_RATIO = Decimal("0.80")

#: Narrow no-break space: 412 000 rather than 412000, and it survives a mail
#: client that would collapse a plain space.
_THIN_SPACE = " "


@dataclass(frozen=True)
class DemoDayReport:
    """One day of the demonstrator, as figures an operator can act on."""

    utc_day: date
    visitors: int
    verified: int
    signups: int
    signup_limit: int | None
    conversations: int
    user_messages: int
    assistant_messages: int
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    runs: int
    cost_eur: Decimal
    budget_eur: Decimal | None

    @property
    def is_quiet(self) -> bool:
        """Nothing happened — stated in words, never left to silence."""
        return self.signups == 0 and self.conversations == 0 and self.user_messages == 0


def _number(value: int) -> str:
    return f"{value:,}".replace(",", _THIN_SPACE)


def _euro(value: Decimal) -> str:
    return f"{value:.2f}".replace(".", ",") + _THIN_SPACE + "€"


def _near(used: Decimal | int, ceiling: Decimal | int | None) -> bool:
    """Whether a figure has consumed most of the ceiling that bounds it."""
    if not ceiling:
        return False
    return Decimal(used) / Decimal(ceiling) >= ALERT_RATIO


def _row(label: str, value: str, *, strong: bool = False) -> str:
    weight = "600" if strong else "400"
    return (
        '<tr><td style="padding:6px 12px 6px 0;color:#475569;font-size:14px">'
        f"{label}</td>"
        f'<td style="padding:6px 0;text-align:right;font-variant-numeric:tabular-nums;'
        f'font-weight:{weight};color:#0f172a;font-size:14px">{value}</td></tr>'
    )


def _card(title: str, rows: str) -> str:
    return (
        '<div style="border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;'
        'margin:0 0 16px 0;background:#ffffff">'
        f'<h2 style="margin:0 0 10px 0;font-size:15px;color:#0f172a">{title}</h2>'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table></div>'
    )


def _alerts(report: DemoDayReport) -> str:
    """The one thing an operator must see without reading anything else."""
    notes: list[str] = []
    if _near(report.cost_eur, report.budget_eur):
        notes.append(LABELS["alert_budget"])
    if _near(report.signups, report.signup_limit):
        notes.append(LABELS["alert_signups"])
    if not notes:
        return ""
    items = "".join(f"<li style='margin:2px 0'>{note}</li>" for note in notes)
    return (
        '<div style="border-left:4px solid #f59e0b;background:#fffbeb;padding:10px 14px;'
        'border-radius:8px;margin:0 0 16px 0"><ul style="margin:0;padding-left:18px;'
        f'color:#92400e;font-size:14px">{items}</ul></div>'
    )


def render_demo_day_report_html(report: DemoDayReport) -> str:
    """Build the report body: synthesis first, detail below.

    Inline styles only, and no external asset: mail clients drop ``<style>``
    blocks and refuse remote images, so anything not written on the element
    itself is not displayed.

    Args:
        report: The day's aggregated figures.

    Returns:
        A self-contained HTML document.
    """
    day = report.utc_day.strftime("%d/%m/%Y")
    budget = _euro(report.budget_eur) if report.budget_eur else LABELS["no_limit"]
    signup_ceiling = _number(report.signup_limit) if report.signup_limit else LABELS["no_limit"]

    synthesis = _card(
        LABELS["synthesis"],
        _row(LABELS["visitors"], _number(report.visitors), strong=True)
        + _row(LABELS["conversations"], _number(report.conversations), strong=True)
        + _row(LABELS["cost"], _euro(report.cost_eur), strong=True)
        + _row(LABELS["budget"], budget)
        + _row(LABELS["signup_limit"], signup_ceiling),
    )

    detail = _card(
        LABELS["detail"],
        _row(LABELS["verified"], _number(report.verified))
        + _row(LABELS["signups"], _number(report.signups))
        + _row(LABELS["user_messages"], _number(report.user_messages))
        + _row(LABELS["assistant_messages"], _number(report.assistant_messages))
        + _row(LABELS["runs"], _number(report.runs))
        + _row(LABELS["tokens_in"], _number(report.tokens_in))
        + _row(LABELS["tokens_out"], _number(report.tokens_out))
        + _row(LABELS["tokens_cached"], _number(report.tokens_cached)),
    )

    quiet = (
        f'<p style="margin:0 0 16px 0;color:#475569;font-size:14px">{LABELS["quiet_day"]}</p>'
        if report.is_quiet
        else ""
    )

    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'background:#f8fafc;padding:24px;margin:0">'
        '<div style="max-width:560px;margin:0 auto">'
        f'<h1 style="margin:0 0 4px 0;font-size:18px;color:#0f172a">{LABELS["title"]}</h1>'
        f'<p style="margin:0 0 18px 0;color:#64748b;font-size:13px">'
        f'{LABELS["period"].format(day=day, time="02:15")}</p>'
        f"{_alerts(report)}{quiet}{synthesis}{detail}"
        f'<p style="margin:8px 0 0 0;color:#94a3b8;font-size:12px;line-height:1.5">'
        f'{LABELS["footer"]}</p>'
        "</div></div>"
    )


async def _collect(session: AsyncSession) -> DemoDayReport:
    """Read the day's figures from the instance's own database.

    Counts are aggregates over the whole set, never the length of a page: a
    count shown to an operator is exact or it does not exist.
    """
    from src.domains.chat.models import MessageTokenSummary
    from src.domains.conversations.models import Conversation, ConversationMessage
    from src.domains.usage_limits.models import InstanceDailyBudget
    from src.domains.users.models import User

    today = datetime.now(UTC).date()

    visitors = await session.scalar(select(func.count()).select_from(User)) or 0
    verified = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.is_verified.is_(True))
        )
        or 0
    )
    conversations = await session.scalar(select(func.count()).select_from(Conversation)) or 0

    role_rows = (
        await session.execute(
            select(ConversationMessage.role, func.count()).group_by(ConversationMessage.role)
        )
    ).all()
    by_role: dict[str, int] = {str(role): int(count) for role, count in role_rows}

    tokens = (
        await session.execute(
            select(
                func.coalesce(func.sum(MessageTokenSummary.total_prompt_tokens), 0),
                func.coalesce(func.sum(MessageTokenSummary.total_completion_tokens), 0),
                func.coalesce(func.sum(MessageTokenSummary.total_cached_tokens), 0),
            )
        )
    ).one()

    ledger = (
        await session.execute(
            select(InstanceDailyBudget).where(InstanceDailyBudget.utc_day == today)
        )
    ).scalar_one_or_none()

    return DemoDayReport(
        utc_day=today,
        visitors=visitors,
        verified=verified,
        signups=getattr(ledger, "signup_count", 0) or 0,
        signup_limit=settings.demo_daily_signup_limit,
        conversations=conversations,
        user_messages=int(by_role.get("user", 0)),
        assistant_messages=int(by_role.get("assistant", 0)),
        tokens_in=int(tokens[0]),
        tokens_out=int(tokens[1]),
        tokens_cached=int(tokens[2]),
        runs=getattr(ledger, "run_count", 0) or 0,
        cost_eur=Decimal(getattr(ledger, "spent_cost_eur", 0) or 0),
        budget_eur=settings.instance_daily_budget_eur,
    )


async def _send(recipient: str, subject: str, html: str) -> None:
    """Hand the report to the mail service the instance already uses."""
    from src.infrastructure.email.email_service import EmailService

    await EmailService().send_email(to_email=recipient, subject=subject, html_body=html)


async def run_demo_daily_report() -> None:
    """Collect the day and mail it, minutes before the purge erases it.

    Never raises: it runs inside the same scheduler as the purge, and an
    exception here must not take that purge — the instance's own promise —
    down with it.
    """
    if not settings.demo_mode_enabled:
        return
    recipient = (getattr(settings, "demo_daily_report_recipient", "") or "").strip()
    if not recipient:
        logger.debug("demo_daily_report_no_recipient")
        return

    try:
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as session:
            report = await _collect(session)

        day = report.utc_day.strftime("%d/%m/%Y")
        key = "subject_quiet" if report.is_quiet else "subject_active"
        await _send(recipient, LABELS[key].format(day=day), render_demo_day_report_html(report))
        logger.info(
            "demo_daily_report_sent",
            utc_day=str(report.utc_day),
            visitors=report.visitors,
            conversations=report.conversations,
            cost_eur=float(report.cost_eur),
        )
    except Exception as exc:  # noqa: BLE001 — never take the purge down
        logger.error("demo_daily_report_failed", error_type=type(exc).__name__, error=str(exc))
