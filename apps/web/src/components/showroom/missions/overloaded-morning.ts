/**
 * Mission: an overloaded morning (the original P0 storyboard).
 *
 * Demonstrates the orchestration core: four sources read in parallel, two
 * conflicts detected, two HITL decisions (an editable email draft and a
 * calendar move) — nothing applied without the visitor.
 *
 * Pure static data, deep-frozen at module load:
 * - user-facing texts are i18n KEYS (resolved by the caller in the active
 *   locale); proper nouns (Emma, Atlas) are data — they do not translate;
 * - structural facts are bounded 'HH:MM' literals — nothing clock-derived;
 * - every email-like identifier lives on example.invalid;
 * - no URL, path, command, secret, or provider name may ever appear here
 *   (guarded by fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const OVERLOADED_MORNING: ShowroomMissionDefinition = deepFreeze({
  id: 'overloaded_morning',
  fixtureVersion: 'overloaded_morning-v2',
  titleKey: 'showroom.m.overloaded_morning.title',
  taglineKey: 'showroom.m.overloaded_morning.tagline',
  mechanismKey: 'showroom.m.overloaded_morning.mechanism',
  requestKey: 'showroom.request',
  proactive: false,
  sources: [
    {
      id: 'inbox',
      labelKey: 'showroom.sources.inbox',
      emoji: '📬',
      items: [{ labelKey: 'showroom.facts.inbox_emma_proposal', time: '09:30' }],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.sources.calendar',
      emoji: '📅',
      items: [
        { labelKey: 'showroom.facts.calendar_run', time: '07:30' },
        { labelKey: 'showroom.facts.calendar_checkpoint', time: '09:00' },
      ],
    },
    {
      id: 'tasks',
      labelKey: 'showroom.sources.tasks',
      emoji: '✅',
      items: [{ labelKey: 'showroom.facts.task_quote_due', time: '10:00' }],
    },
    {
      id: 'weather',
      labelKey: 'showroom.sources.weather',
      emoji: '🌧️',
      items: [{ labelKey: 'showroom.facts.weather_rain', time: '07:00', endTime: '09:00' }],
    },
  ],
  findings: [
    { labelKey: 'showroom.conflicts.rain_vs_run', time: '07:30', endTime: '09:00' },
    { labelKey: 'showroom.conflicts.quote_deadline', time: '10:00' },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.trace.sources',
    'showroom.trace.planning',
    'showroom.trace.proposals',
  ],
  decisions: [
    {
      id: 'email_reply',
      kind: 'draft',
      allowed: ['confirm', 'edit', 'cancel'],
      phaseLabelKey: 'showroom.phases.email_decision',
      receiptLabelKey: 'showroom.receipt.email_label',
      icon: 'mail',
      to: 'emma@atlas.example.invalid',
      subjectKey: 'showroom.proposals.email_subject',
      bodyKey: 'showroom.proposals.email_body',
      outcome: {
        confirm: 'showroom.receipt.email_applied',
        edit: 'showroom.receipt.email_edited',
        cancel: 'showroom.receipt.email_refused',
      },
    },
    {
      id: 'calendar_adjustment',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.phases.calendar_decision',
      receiptLabelKey: 'showroom.receipt.calendar_label',
      icon: 'calendar',
      toolNameKey: 'showroom.proposals.calendar_title',
      args: [
        { labelKey: 'showroom.proposals.from', value: '07:30' },
        { labelKey: 'showroom.proposals.to', value: '10:30' },
      ],
      outcome: {
        confirm: 'showroom.receipt.calendar_applied',
        cancel: 'showroom.receipt.calendar_refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.receipt.reads_value',
    proposedKey: 'showroom.receipt.proposed_value',
  },
  noteKey: 'showroom.m.overloaded_morning.note',
} satisfies ShowroomMissionDefinition);
