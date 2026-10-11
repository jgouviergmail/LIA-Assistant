/**
 * Personal-assistant showroom: overloaded_morning.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const OVERLOADED_MORNING: ShowroomMissionDefinition = deepFreeze({
  id: 'overloaded_morning',
  fixtureVersion: 'overloaded_morning-v3',
  titleKey: 'showroom.m.overloaded_morning.title',
  taglineKey: 'showroom.m.overloaded_morning.tagline',
  mechanismKey: 'showroom.m.overloaded_morning.mechanism',
  requestKey: 'showroom.request',
  proactive: false,
  sources: [
    {
      id: 'relations',
      labelKey: 'showroom.personal.overloaded_morning.source_1',
      emoji: '👥',
      items: [
        {
          labelKey: 'showroom.personal.overloaded_morning.fact_1',
        },
      ],
    },
    {
      id: 'knowledge',
      labelKey: 'showroom.personal.overloaded_morning.source_2',
      emoji: '📚',
      items: [
        {
          labelKey: 'showroom.personal.overloaded_morning.fact_2',
        },
      ],
    },
    {
      id: 'inbox',
      labelKey: 'showroom.personal.overloaded_morning.source_3',
      emoji: '📬',
      items: [
        {
          labelKey: 'showroom.personal.overloaded_morning.fact_3',
        },
      ],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.personal.overloaded_morning.source_4',
      emoji: '📅',
      items: [
        {
          labelKey: 'showroom.personal.overloaded_morning.fact_4',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.overloaded_morning.finding_1',
    },
    {
      labelKey: 'showroom.personal.overloaded_morning.finding_2',
    },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.personal.trace_context',
    'showroom.personal.trace_compare',
    'showroom.personal.trace_result',
  ],
  decisions: [
    {
      id: 'email_reply',
      kind: 'draft',
      allowed: ['confirm', 'edit', 'cancel'],
      phaseLabelKey: 'showroom.phases.email_decision',
      receiptLabelKey: 'showroom.receipt.email_label',
      icon: 'mail',
      to: 'claire@atlas.example.invalid',
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
        {
          labelKey: 'showroom.proposals.from',
          value: '08:30',
        },
        {
          labelKey: 'showroom.proposals.to',
          value: '08:50',
        },
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
