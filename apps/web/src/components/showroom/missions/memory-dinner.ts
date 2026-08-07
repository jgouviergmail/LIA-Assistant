/**
 * Mission: it remembers for you (persistent memory + learned habits).
 *
 * One short ask — "book a dinner with Sarah on Friday" — and LIA applies
 * three remembered preferences (Sarah's diet, the usual dinner time, the
 * free evening) without asking anything twice. Both effects stay gated:
 * an editable message draft and a calendar event confirmation.
 *
 * Same data contract as every mission fixture: i18n keys, bounded 'HH:MM'
 * literals, example.invalid addresses, deep-frozen (fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const MEMORY_DINNER: ShowroomMissionDefinition = deepFreeze({
  id: 'memory_dinner',
  fixtureVersion: 'memory_dinner-v1',
  titleKey: 'showroom.m.memory_dinner.title',
  taglineKey: 'showroom.m.memory_dinner.tagline',
  mechanismKey: 'showroom.m.memory_dinner.mechanism',
  requestKey: 'showroom.m.memory_dinner.request',
  proactive: false,
  sources: [
    {
      id: 'memory',
      labelKey: 'showroom.sources.memory',
      emoji: '🧠',
      items: [
        { labelKey: 'showroom.m.memory_dinner.facts.sarah_veg' },
        { labelKey: 'showroom.m.memory_dinner.facts.last_dinner' },
      ],
    },
    {
      id: 'habits',
      labelKey: 'showroom.sources.habits',
      emoji: '🔁',
      items: [{ labelKey: 'showroom.m.memory_dinner.facts.dinner_time', time: '20:00' }],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.sources.calendar',
      emoji: '📅',
      items: [{ labelKey: 'showroom.m.memory_dinner.facts.friday_free', time: '19:00' }],
    },
    {
      id: 'contacts',
      labelKey: 'showroom.sources.contacts',
      emoji: '👥',
      items: [{ labelKey: 'showroom.m.memory_dinner.facts.sarah_contact' }],
    },
  ],
  findings: [
    { labelKey: 'showroom.m.memory_dinner.findings.prefs_applied' },
    { labelKey: 'showroom.m.memory_dinner.findings.slot', time: '20:00' },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.trace.sources',
    'showroom.m.memory_dinner.trace_recall',
    'showroom.trace.proposals',
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
          value: '20:00',
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
