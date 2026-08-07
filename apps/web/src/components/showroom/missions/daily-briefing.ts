/**
 * Mission: your morning, already digested (the daily briefing).
 *
 * The rich-answer showcase: a proactive morning digest of inbox, calendar,
 * weather and tasks, closed by ONE small optional decision (a focus slot to
 * answer Claire). The value lives in the receipt's rich HTML reply — stat
 * tiles, agenda table, overlap warning — rendered by the production
 * pipeline.
 *
 * Same data contract as every mission fixture: i18n keys, bounded 'HH:MM'
 * literals, deep-frozen (fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const DAILY_BRIEFING: ShowroomMissionDefinition = deepFreeze({
  id: 'daily_briefing',
  fixtureVersion: 'daily_briefing-v1',
  titleKey: 'showroom.m.daily_briefing.title',
  taglineKey: 'showroom.m.daily_briefing.tagline',
  mechanismKey: 'showroom.m.daily_briefing.mechanism',
  requestKey: 'showroom.m.daily_briefing.request',
  proactive: true,
  sources: [
    {
      id: 'inbox',
      labelKey: 'showroom.sources.inbox',
      emoji: '📬',
      items: [{ labelKey: 'showroom.m.daily_briefing.facts.new_mails' }],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.sources.calendar',
      emoji: '📅',
      items: [
        { labelKey: 'showroom.m.daily_briefing.facts.meetings', time: '09:00' },
        { labelKey: 'showroom.m.daily_briefing.facts.overlap', time: '14:00' },
      ],
    },
    {
      id: 'tasks',
      labelKey: 'showroom.sources.tasks',
      emoji: '✅',
      items: [{ labelKey: 'showroom.m.daily_briefing.facts.due' }],
    },
    {
      id: 'weather',
      labelKey: 'showroom.sources.weather',
      emoji: '☀️',
      items: [{ labelKey: 'showroom.m.daily_briefing.facts.clear' }],
    },
  ],
  findings: [
    { labelKey: 'showroom.m.daily_briefing.findings.claire', time: '09:00' },
    {
      labelKey: 'showroom.m.daily_briefing.findings.overlap',
      time: '14:00',
      endTime: '15:30',
    },
  ],
  traceKeys: [
    'showroom.m.daily_briefing.trace_schedule',
    'showroom.trace.sources',
    'showroom.trace.planning',
    'showroom.m.daily_briefing.trace_compose',
  ],
  decisions: [
    {
      id: 'focus_block',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.daily_briefing.decisions.focus_block.phase',
      receiptLabelKey: 'showroom.m.daily_briefing.decisions.focus_block.receipt_label',
      icon: 'task',
      toolNameKey: 'showroom.m.daily_briefing.decisions.focus_block.tool',
      args: [
        { labelKey: 'showroom.proposals.from', value: '08:30' },
        { labelKey: 'showroom.proposals.to', value: '08:50' },
      ],
      outcome: {
        confirm: 'showroom.m.daily_briefing.decisions.focus_block.applied',
        cancel: 'showroom.m.daily_briefing.decisions.focus_block.refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.m.daily_briefing.receipt.reads',
    proposedKey: 'showroom.m.daily_briefing.receipt.proposed',
  },
  noteKey: 'showroom.m.daily_briefing.note',
} satisfies ShowroomMissionDefinition);
