/**
 * Mission: LIA gets there first (proactivity / heartbeat).
 *
 * Demonstrates the differentiator chatbots lack: LIA initiates. No visitor
 * request is typed — the morning scan raises two risks (rain over the
 * evening run, an answer Marc has been waiting for) and proposes bounded
 * fixes, each still gated by an explicit decision.
 *
 * Same data contract as every mission fixture: i18n keys, bounded 'HH:MM'
 * literals, example.invalid addresses, deep-frozen (fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const PROACTIVE_ALERT: ShowroomMissionDefinition = deepFreeze({
  id: 'proactive_alert',
  fixtureVersion: 'proactive_alert-v1',
  titleKey: 'showroom.m.proactive_alert.title',
  taglineKey: 'showroom.m.proactive_alert.tagline',
  mechanismKey: 'showroom.m.proactive_alert.mechanism',
  requestKey: 'showroom.m.proactive_alert.request',
  proactive: true,
  sources: [
    {
      id: 'weather',
      labelKey: 'showroom.sources.weather',
      emoji: '🌧️',
      items: [
        {
          labelKey: 'showroom.m.proactive_alert.facts.rain_evening',
          time: '17:00',
          endTime: '20:00',
        },
      ],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.sources.calendar',
      emoji: '📅',
      items: [
        { labelKey: 'showroom.m.proactive_alert.facts.run_evening', time: '18:00' },
        { labelKey: 'showroom.m.proactive_alert.facts.free_slot', time: '07:00' },
      ],
    },
    {
      id: 'inbox',
      labelKey: 'showroom.sources.inbox',
      emoji: '📬',
      items: [
        { labelKey: 'showroom.m.proactive_alert.facts.marc_waiting' },
        { labelKey: 'showroom.m.proactive_alert.facts.marc_committee', time: '10:00' },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.m.proactive_alert.findings.rain_vs_run',
      time: '17:00',
      endTime: '20:00',
    },
    { labelKey: 'showroom.m.proactive_alert.findings.reply_before', time: '10:00' },
  ],
  traceKeys: [
    'showroom.m.proactive_alert.trace_trigger',
    'showroom.trace.sources',
    'showroom.trace.planning',
    'showroom.trace.proposals',
  ],
  decisions: [
    {
      id: 'move_run',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.proactive_alert.decisions.move_run.phase',
      receiptLabelKey: 'showroom.m.proactive_alert.decisions.move_run.receipt_label',
      icon: 'calendar',
      toolNameKey: 'showroom.m.proactive_alert.decisions.move_run.tool',
      args: [
        {
          labelKey: 'showroom.proposals.from',
          valueKey: 'showroom.m.proactive_alert.decisions.move_run.from_value',
        },
        {
          labelKey: 'showroom.proposals.to',
          valueKey: 'showroom.m.proactive_alert.decisions.move_run.to_value',
        },
      ],
      outcome: {
        confirm: 'showroom.m.proactive_alert.decisions.move_run.applied',
        cancel: 'showroom.m.proactive_alert.decisions.move_run.refused',
      },
    },
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
