/**
 * Personal-assistant showroom: memory_dinner.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const MEMORY_DINNER: ShowroomMissionDefinition = deepFreeze({
  id: 'memory_dinner',
  fixtureVersion: 'memory_dinner-v2',
  titleKey: 'showroom.m.memory_dinner.title',
  taglineKey: 'showroom.m.memory_dinner.tagline',
  mechanismKey: 'showroom.m.memory_dinner.mechanism',
  requestKey: 'showroom.m.memory_dinner.request',
  proactive: false,
  sources: [
    {
      id: 'memory',
      labelKey: 'showroom.personal.memory_dinner.source_1',
      emoji: '🧠',
      items: [
        {
          labelKey: 'showroom.personal.memory_dinner.fact_1',
        },
      ],
    },
    {
      id: 'peer',
      labelKey: 'showroom.personal.memory_dinner.source_2',
      emoji: '🤝',
      items: [
        {
          labelKey: 'showroom.personal.memory_dinner.fact_2',
        },
      ],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.personal.memory_dinner.source_3',
      emoji: '📅',
      items: [
        {
          labelKey: 'showroom.personal.memory_dinner.fact_3',
        },
      ],
    },
    {
      id: 'inbox',
      labelKey: 'showroom.personal.memory_dinner.source_4',
      emoji: '📬',
      items: [
        {
          labelKey: 'showroom.personal.memory_dinner.fact_4',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.memory_dinner.finding_1',
    },
    {
      labelKey: 'showroom.personal.memory_dinner.finding_2',
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
      id: 'invite_sarah',
      kind: 'draft',
      allowed: ['confirm', 'edit', 'cancel'],
      phaseLabelKey: 'showroom.m.memory_dinner.decisions.invite_sarah.phase',
      receiptLabelKey: 'showroom.m.memory_dinner.decisions.invite_sarah.receipt_label',
      icon: 'mail',
      to: 'sarah@willow.example.invalid',
      subjectKey: 'showroom.m.memory_dinner.decisions.invite_sarah.subject',
      bodyKey: 'showroom.m.memory_dinner.decisions.invite_sarah.body',
      outcome: {
        confirm: 'showroom.m.memory_dinner.decisions.invite_sarah.applied',
        edit: 'showroom.m.memory_dinner.decisions.invite_sarah.edited',
        cancel: 'showroom.m.memory_dinner.decisions.invite_sarah.refused',
      },
    },
    {
      id: 'create_event',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.memory_dinner.decisions.create_event.phase',
      receiptLabelKey: 'showroom.m.memory_dinner.decisions.create_event.receipt_label',
      icon: 'calendar',
      toolNameKey: 'showroom.m.memory_dinner.decisions.create_event.tool',
      args: [
        {
          labelKey: 'showroom.m.memory_dinner.decisions.create_event.what',
          valueKey: 'showroom.m.memory_dinner.decisions.create_event.what_value',
        },
        {
          labelKey: 'showroom.m.memory_dinner.decisions.create_event.when',
          value: '19:30',
        },
      ],
      outcome: {
        confirm: 'showroom.m.memory_dinner.decisions.create_event.applied',
        cancel: 'showroom.m.memory_dinner.decisions.create_event.refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.m.memory_dinner.receipt.reads',
    proposedKey: 'showroom.m.memory_dinner.receipt.proposed',
  },
  noteKey: 'showroom.m.memory_dinner.note',
} satisfies ShowroomMissionDefinition);
