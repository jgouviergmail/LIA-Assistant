/**
 * Personal-assistant showroom: proactive_alert.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const PROACTIVE_ALERT: ShowroomMissionDefinition = deepFreeze({
  id: 'proactive_alert',
  fixtureVersion: 'proactive_alert-v2',
  titleKey: 'showroom.m.proactive_alert.title',
  taglineKey: 'showroom.m.proactive_alert.tagline',
  mechanismKey: 'showroom.m.proactive_alert.mechanism',
  requestKey: 'showroom.m.proactive_alert.request',
  proactive: true,
  sources: [
    {
      id: 'routine',
      labelKey: 'showroom.personal.proactive_alert.source_1',
      emoji: '🔔',
      items: [
        {
          labelKey: 'showroom.personal.proactive_alert.fact_1',
        },
      ],
    },
    {
      id: 'inbox',
      labelKey: 'showroom.personal.proactive_alert.source_2',
      emoji: '📬',
      items: [
        {
          labelKey: 'showroom.personal.proactive_alert.fact_2',
        },
      ],
    },
    {
      id: 'relations',
      labelKey: 'showroom.personal.proactive_alert.source_3',
      emoji: '👥',
      items: [
        {
          labelKey: 'showroom.personal.proactive_alert.fact_3',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.proactive_alert.finding_1',
    },
    {
      labelKey: 'showroom.personal.proactive_alert.finding_2',
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
      id: 'reply_marc',
      kind: 'draft',
      allowed: ['confirm', 'edit', 'cancel'],
      phaseLabelKey: 'showroom.m.proactive_alert.decisions.reply_marc.phase',
      receiptLabelKey: 'showroom.m.proactive_alert.decisions.reply_marc.receipt_label',
      icon: 'mail',
      to: 'marc@nordic.example.invalid',
      subjectKey: 'showroom.m.proactive_alert.decisions.reply_marc.subject',
      bodyKey: 'showroom.m.proactive_alert.decisions.reply_marc.body',
      outcome: {
        confirm: 'showroom.m.proactive_alert.decisions.reply_marc.applied',
        edit: 'showroom.m.proactive_alert.decisions.reply_marc.edited',
        cancel: 'showroom.m.proactive_alert.decisions.reply_marc.refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.m.proactive_alert.receipt.reads',
    proposedKey: 'showroom.m.proactive_alert.receipt.proposed',
  },
  noteKey: 'showroom.m.proactive_alert.note',
} satisfies ShowroomMissionDefinition);
