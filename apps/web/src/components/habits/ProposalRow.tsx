'use client';

/**
 * One habit proposal: the facts LIA observed, phrased in your language, and
 * three answers — carry it out, later, never (ADR-375).
 *
 * The sentence is built HERE from structured facts (days, hours, counts), never
 * stored as text: the same proposal reads in French, in Chinese, and the day
 * the copy improves. The accept button says what it will do (« Create the
 * routine », « Move it to 09:30 »), because accepting acts.
 *
 * Shared by the alerts inbox and, later, the card under a chat answer: the
 * decision state lives above both (`useProposalDecisions`), so a decision in
 * flight keeps every button busy wherever it is shown.
 */

import { Check, CircleSlash, Clock, type LucideIcon } from '@/lib/icons';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import type {
  AutomateNeedFacts,
  HabitProposal,
  ProposalDecisions,
  ProposalVerdict,
} from '@/hooks/useHabitProposals';
import { weekdayName } from '@/lib/habit-labels';
import { clockLabel } from '@/lib/recurrence';

/** The one thing the copy needs from i18next: a key and its values in, a sentence out. */
type Translate = (key: string, options?: Record<string, unknown>) => string;

interface ProposalCopy {
  text: string;
  /** A second fact worth knowing before deciding, when there is one. */
  detail: string | null;
  /** What accepting does, as a verb phrase. */
  accept: string;
}

const clock = (hour: number, minute = 0) => clockLabel({ hour, minute });

function scheduleOf(t: Translate, locale: string, facts: AutomateNeedFacts): string {
  return facts.cadence === 'weekly' && facts.weekday !== null
    ? t('habits.proposals.schedule.weekly', { day: weekdayName(locale, facts.weekday) })
    : t(`habits.proposals.schedule.${facts.cadence === 'weekdays' ? 'weekdays' : 'daily'}`);
}

/** The sentence, its detail and its accept label — one branch per kind. */
export function proposalCopy(t: Translate, locale: string, proposal: HabitProposal): ProposalCopy {
  const base = `habits.proposals.${proposal.kind}`;
  switch (proposal.kind) {
    case 'automate_need': {
      const facts = proposal.facts;
      const cited = facts.existing_routine;
      return {
        text: t(`${base}.text`, {
          domain: t(`habits.proposals.domain.${facts.domain}`, { defaultValue: facts.domain }),
          days: facts.distinct_days,
          active: facts.active_days,
          schedule: scheduleOf(t, locale, facts),
          time: clock(facts.hour, facts.minute),
        }),
        detail: cited
          ? t(`${base}.existing`, { title: cited.title, time: clock(cited.hour, cited.minute) })
          : null,
        accept: t(`${base}.accept`),
      };
    }
    case 'shift_routine': {
      const facts = proposal.facts;
      const time = clock(facts.hour, facts.minute);
      return {
        text: t(`${base}.text`, {
          title: facts.routine_title,
          time,
          runs: facts.manual_runs,
          days: facts.manual_days,
          from: clock(facts.from_hour, facts.from_minute),
        }),
        detail: null,
        accept: t(`${base}.accept`, { time }),
      };
    }
    case 'fix_routine':
      return {
        text: t(`${base}.${proposal.facts.disabled ? 'text_disabled' : 'text_failing'}`, {
          title: proposal.facts.routine_title,
          failures: proposal.facts.failures,
        }),
        detail: null,
        accept: t(`${base}.accept`),
      };
    case 'extend_notification_window': {
      const facts = proposal.facts;
      const extended = `${clock(facts.new_start)}–${clock(facts.new_end)}`;
      return {
        text: t(`${base}.text`, {
          window: `${clock(facts.start)}–${clock(facts.end)}`,
          days: facts.outside_days,
          new_window: extended,
        }),
        detail: null,
        accept: t(`${base}.accept`, { new_window: extended }),
      };
    }
    case 'review_notifications':
      return {
        text: t(`${base}.text`, {
          sent: proposal.facts.sent,
          days: proposal.facts.window_days,
        }),
        detail: null,
        accept: t(`${base}.accept`),
      };
    case 'connect_source':
      return {
        text: t(`${base}.text`, {
          domain: t(`habits.proposals.domain.${proposal.facts.domain}`, {
            defaultValue: proposal.facts.domain,
          }),
          category: t(`habits.proposals.category.${proposal.facts.category}`, {
            defaultValue: proposal.facts.category,
          }),
          days: proposal.facts.days,
        }),
        detail: null,
        accept: t(`${base}.accept`),
      };
  }
}

function DecisionButton({
  proposal,
  verdict,
  label,
  icon: Icon,
  variant,
  decisions,
}: {
  proposal: HabitProposal;
  verdict: ProposalVerdict;
  label: string;
  icon: LucideIcon;
  variant: 'default' | 'outline' | 'ghost';
  decisions: ProposalDecisions;
}) {
  const { pending, decided, decide } = decisions;
  const busy = pending?.id === proposal.id && pending.verdict === verdict;
  return (
    <Button
      size="sm"
      variant={variant}
      className="h-auto min-h-11 whitespace-normal py-2"
      // aria-disabled, never `disabled`: a disabled button drops the focus
      // the reader is resting on while the decision is in flight.
      aria-disabled={Boolean(pending) || decided.has(proposal.id) || undefined}
      aria-busy={busy || undefined}
      onClick={() => void decide(proposal, verdict)}
    >
      {busy ? (
        <LoadingSpinner className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Icon className="h-4 w-4" aria-hidden="true" />
      )}
      {label}
    </Button>
  );
}

export function ProposalRow({
  proposal,
  decisions,
  compact = false,
}: {
  proposal: HabitProposal;
  decisions: ProposalDecisions;
  /** One wrapping row of actions at every width: the chat band spends less height. */
  compact?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const copy = proposalCopy(t, i18n.language, proposal);
  return (
    <div className="min-w-0 space-y-3">
      <div className="min-w-0">
        <p className="break-words text-sm leading-relaxed text-foreground/90">{copy.text}</p>
        {copy.detail && (
          <p className="mt-1 break-words text-xs text-muted-foreground">{copy.detail}</p>
        )}
      </div>
      <div
        className={
          compact
            ? 'flex flex-wrap items-center gap-2'
            : 'flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end'
        }
      >
        <DecisionButton
          proposal={proposal}
          verdict="accept"
          label={copy.accept}
          icon={Check}
          variant="default"
          decisions={decisions}
        />
        <DecisionButton
          proposal={proposal}
          verdict="dismiss"
          label={t('habits.proposals.later')}
          icon={Clock}
          variant="outline"
          decisions={decisions}
        />
        <DecisionButton
          proposal={proposal}
          verdict="refuse"
          label={t('habits.proposals.never')}
          icon={CircleSlash}
          variant="ghost"
          decisions={decisions}
        />
      </div>
    </div>
  );
}

/** The open proposals of the inbox, one row each. */
export function ProposalList({
  proposals,
  decisions,
}: {
  proposals: readonly HabitProposal[];
  decisions: ProposalDecisions;
}) {
  return (
    <ul className="space-y-2" role="list">
      {proposals.map(proposal => (
        <li
          key={proposal.id}
          className="min-w-0 border-t border-border py-4 first:border-t-0 first:pt-0"
        >
          <ProposalRow proposal={proposal} decisions={decisions} />
        </li>
      ))}
    </ul>
  );
}
