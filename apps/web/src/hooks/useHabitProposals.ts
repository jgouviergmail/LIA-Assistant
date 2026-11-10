'use client';

/**
 * Habit proposals (ADR-375) — what LIA proposes from what it learned of your
 * usage, and your decision on each.
 *
 * A proposal travels as FACTS (days, hours, counts, ids): the card phrases them
 * in your language, so no sentence is stored or sent. Accepting CARRIES IT OUT
 * on the server — a routine created or moved, your notification hours changed
 * or the notifications paused — and two proposals only open a screen (a failing
 * routine, a missing connector). When the act no longer matches what you were
 * shown, the server refuses with a stable reason, the proposal stays open, and
 * the reason is said in your language — never a generic failure.
 */

import { useRouter } from 'next/navigation';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import apiClient, { ApiError } from '@/lib/api-client';
import { settingsSectionHref } from '@/lib/settings-sections';
import { z } from '@/lib/zod';

export type ProposalVerdict = 'accept' | 'dismiss' | 'refuse';

// The facts of each kind, declared ONCE: the types below are inferred from
// these schemas, and the same schemas read a proposal that arrives untyped —
// the one an answer carries in its metadata (`habitProposalOf`).

const citedRoutineSchema = z.object({
  id: z.string(),
  title: z.string(),
  hour: z.number(),
  minute: z.number(),
});

const automateNeedFactsSchema = z.object({
  domain: z.string(),
  cadence: z.enum(['daily', 'weekdays', 'weekly']),
  /** 0=Monday..6=Sunday, for a weekly need only. */
  weekday: z.number().nullable(),
  /** The time the routine would be ready by. */
  hour: z.number(),
  minute: z.number(),
  distinct_days: z.number(),
  active_days: z.number(),
  part_of_day: z.enum(['morning', 'afternoon', 'evening', 'night', 'any']),
  existing_routine: citedRoutineSchema.nullable(),
});

const shiftRoutineFactsSchema = z.object({
  routine_id: z.string(),
  routine_title: z.string(),
  from_hour: z.number(),
  from_minute: z.number(),
  hour: z.number(),
  minute: z.number(),
  manual_runs: z.number(),
  manual_days: z.number(),
});

const fixRoutineFactsSchema = z.object({
  routine_id: z.string(),
  routine_title: z.string(),
  failures: z.number(),
  disabled: z.boolean(),
});

const extendWindowFactsSchema = z.object({
  start: z.number(),
  end: z.number(),
  new_start: z.number(),
  new_end: z.number(),
  outside_days: z.number(),
  outside_share: z.number(),
});

const reviewNotificationsFactsSchema = z.object({
  sent: z.number(),
  window_days: z.number(),
});

const connectSourceFactsSchema = z.object({
  category: z.string(),
  domain: z.string(),
  days: z.number(),
});

function proposalOf<K extends string, F extends z.ZodType>(kind: K, facts: F) {
  return z.object({
    id: z.string(),
    kind: z.literal(kind),
    key: z.string(),
    facts,
    created_at: z.string(),
    updated_at: z.string(),
  });
}

const habitProposalSchema = z.discriminatedUnion('kind', [
  proposalOf('automate_need', automateNeedFactsSchema),
  proposalOf('shift_routine', shiftRoutineFactsSchema),
  proposalOf('fix_routine', fixRoutineFactsSchema),
  proposalOf('extend_notification_window', extendWindowFactsSchema),
  proposalOf('review_notifications', reviewNotificationsFactsSchema),
  proposalOf('connect_source', connectSourceFactsSchema),
]);

export type AutomateNeedFacts = z.infer<typeof automateNeedFactsSchema>;
export type ShiftRoutineFacts = z.infer<typeof shiftRoutineFactsSchema>;
export type FixRoutineFacts = z.infer<typeof fixRoutineFactsSchema>;
export type ExtendWindowFacts = z.infer<typeof extendWindowFactsSchema>;
export type ReviewNotificationsFacts = z.infer<typeof reviewNotificationsFactsSchema>;
export type ConnectSourceFacts = z.infer<typeof connectSourceFactsSchema>;
export type HabitProposal = z.infer<typeof habitProposalSchema>;
export type ProposalKind = HabitProposal['kind'];

/**
 * A proposal read from a value nothing typed — an answer's archived metadata
 * or its `done` chunk (ADR-375). Anything else, or a proposal whose facts do
 * not match its kind, reads as no proposal: a card never renders from a guess.
 */
export function habitProposalOf(value: unknown): HabitProposal | null {
  const parsed = habitProposalSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export interface HabitProposalsPage {
  proposals: HabitProposal[];
  /** Exact count over every open proposal, beyond this page too. */
  total: number;
  /** False when habit learning is off for you or on this instance: nothing is served. */
  learning_enabled: boolean;
}

/** Why an accepted proposal could not be carried out — each has its sentence. */
export const PROPOSAL_REFUSALS = [
  'routine_limit',
  'routine_gone',
  'routine_changed',
  'settings_changed',
] as const;
export type ProposalRefusal = (typeof PROPOSAL_REFUSALS)[number];

const conflictSchema = z.object({
  status: z.literal(409),
  data: z.object({
    detail: z.union([
      z.object({ error_code: z.literal('PROPOSAL_NOT_OPEN') }),
      z.object({
        error_code: z.literal('PROPOSAL_ACTION_REFUSED'),
        reason: z.enum(PROPOSAL_REFUSALS),
      }),
    ]),
  }),
});

/** The stable refusal a 409 carries, or null for any other failure. */
export function proposalConflictOf(
  error: unknown
):
  | { error_code: 'PROPOSAL_NOT_OPEN' }
  | { error_code: 'PROPOSAL_ACTION_REFUSED'; reason: ProposalRefusal }
  | null {
  if (!(error instanceof ApiError)) return null;
  const parsed = conflictSchema.safeParse({ status: error.status, data: error.data });
  return parsed.success ? parsed.data.data.detail : null;
}

const learningOffSchema = z.object({
  status: z.literal(403),
  data: z.object({ detail: z.object({ error_code: z.literal('FEATURE_DISABLED') }) }),
});

/**
 * Whether a decision was refused because habit learning is off — the person's
 * switch or the instance's. A card shown before the switch (the chat archives
 * it with its answer) can no longer be decided: retrying would not help.
 */
export function learningIsOff(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false;
  return learningOffSchema.safeParse({ status: error.status, data: error.data }).success;
}

/** The screen an accepted proposal opens, when it opens one. */
export function proposalDestination(lng: string, proposal: HabitProposal): string | null {
  if (proposal.kind === 'fix_routine') return settingsSectionHref(lng, 'scheduled-actions');
  if (proposal.kind === 'connect_source') return settingsSectionHref(lng, 'connectors');
  return null;
}

/** Proposals whose accept writes something: they confirm it with a toast. */
const CONFIRMED_KINDS: ReadonlySet<ProposalKind> = new Set<ProposalKind>([
  'automate_need',
  'shift_routine',
  'extend_notification_window',
  'review_notifications',
]);

async function submitDecision(id: string, verdict: ProposalVerdict): Promise<void> {
  await apiClient.post(`/habits/proposals/${id}/${verdict}`);
}

export interface ProposalDecisions {
  /** The decision in flight, if any — every other button waits for it. */
  pending: { id: string; verdict: ProposalVerdict } | null;
  /** Decided here: hidden at once, even before the list is read again. */
  decided: ReadonlySet<string>;
  decide: (proposal: HabitProposal, verdict: ProposalVerdict) => Promise<void>;
}

/**
 * One decision at a time, kept above the fold so a decision survives the
 * section closing and reopening while it is in flight.
 *
 * @param onDecided Called once a proposal left the list; `restoreFocus` says
 *   whether the focus was still on the button that decided it.
 */
export function useProposalDecisions({
  lng,
  onDecided,
}: {
  lng: string;
  onDecided: (restoreFocus: boolean) => void;
}): ProposalDecisions {
  const { t } = useTranslation();
  const router = useRouter();
  const lock = useRef(false);
  const [pending, setPending] = useState<ProposalDecisions['pending']>(null);
  const [decided, setDecided] = useState<ReadonlySet<string>>(() => new Set());

  const forget = (id: string) => setDecided(previous => new Set(previous).add(id));

  const decide = async (proposal: HabitProposal, verdict: ProposalVerdict) => {
    if (lock.current || decided.has(proposal.id)) return;
    const initiator = document.activeElement;
    lock.current = true;
    setPending({ id: proposal.id, verdict });
    try {
      await submitDecision(proposal.id, verdict);
      forget(proposal.id);
    } catch (error) {
      const conflict = proposalConflictOf(error);
      if (conflict?.error_code === 'PROPOSAL_NOT_OPEN' || learningIsOff(error)) {
        // Decided elsewhere (the chat, another device), withdrawn tonight, or
        // learning switched off since it was shown: it leaves, and saying why
        // beats a silent disappearance — or a « try again » that cannot work.
        forget(proposal.id);
        toast.info(
          t(
            conflict
              ? 'habits.proposals.not_open'
              : 'notifications_hub.sections.offers.learning_off'
          )
        );
        onDecided(document.activeElement === initiator);
        return;
      }
      toast.error(
        conflict ? t(`habits.proposals.refused.${conflict.reason}`) : t('habits.proposals.error')
      );
      return;
    } finally {
      lock.current = false;
      setPending(null);
    }
    if (verdict === 'accept') {
      if (CONFIRMED_KINDS.has(proposal.kind))
        toast.success(t(`habits.proposals.${proposal.kind}.done`));
      const destination = proposalDestination(lng, proposal);
      if (destination) router.push(destination);
    }
    onDecided(document.activeElement === initiator);
  };

  return { pending, decided, decide };
}
