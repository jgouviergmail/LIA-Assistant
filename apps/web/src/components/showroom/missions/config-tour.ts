/**
 * Mission: yours to shape, in a few clicks (in-app configuration).
 *
 * Shows what is configurable from the interface — tone and reply style,
 * proactive schedule, languages and voice, one-click account connections —
 * and that a plain-language ask ("shorter replies, mornings only") maps to
 * two reversible switches. No file, no code, nothing technical.
 *
 * Same data contract as every mission fixture: i18n keys, bounded 'HH:MM'
 * literals, deep-frozen (fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const CONFIG_TOUR: ShowroomMissionDefinition = deepFreeze({
  id: 'config_tour',
  fixtureVersion: 'config_tour-v1',
  titleKey: 'showroom.m.config_tour.title',
  taglineKey: 'showroom.m.config_tour.tagline',
  mechanismKey: 'showroom.m.config_tour.mechanism',
  requestKey: 'showroom.m.config_tour.request',
  proactive: false,
  sources: [
    {
      id: 'personality',
      labelKey: 'showroom.m.config_tour.sources.personality',
      emoji: '🎭',
      items: [
        { labelKey: 'showroom.m.config_tour.facts.tone' },
        { labelKey: 'showroom.m.config_tour.facts.styles' },
      ],
    },
    {
      id: 'proactivity',
      labelKey: 'showroom.m.config_tour.sources.proactivity',
      emoji: '🔔',
      items: [
        {
          labelKey: 'showroom.m.config_tour.facts.frequency',
          time: '22:00',
          endTime: '07:00',
        },
      ],
    },
    {
      id: 'languages',
      labelKey: 'showroom.m.config_tour.sources.languages',
      emoji: '🌍',
      items: [{ labelKey: 'showroom.m.config_tour.facts.languages' }],
    },
    {
      id: 'connections',
      labelKey: 'showroom.m.config_tour.sources.connections',
      emoji: '🔗',
      items: [{ labelKey: 'showroom.m.config_tour.facts.connectors' }],
    },
  ],
  findings: [
    { labelKey: 'showroom.m.config_tour.findings.match' },
    { labelKey: 'showroom.m.config_tour.findings.reversible' },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.m.config_tour.trace_settings',
    'showroom.trace.planning',
    'showroom.trace.proposals',
  ],
  decisions: [
    {
      id: 'concise_style',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.config_tour.decisions.concise_style.phase',
      receiptLabelKey: 'showroom.m.config_tour.decisions.concise_style.receipt_label',
      icon: 'settings',
      toolNameKey: 'showroom.m.config_tour.decisions.concise_style.tool',
      args: [
        {
          labelKey: 'showroom.m.config_tour.decisions.concise_style.setting',
          valueKey: 'showroom.m.config_tour.decisions.concise_style.setting_value',
        },
        {
          labelKey: 'showroom.proposals.from',
          valueKey: 'showroom.m.config_tour.decisions.concise_style.from_value',
        },
        {
          labelKey: 'showroom.proposals.to',
          valueKey: 'showroom.m.config_tour.decisions.concise_style.to_value',
        },
      ],
      outcome: {
        confirm: 'showroom.m.config_tour.decisions.concise_style.applied',
        cancel: 'showroom.m.config_tour.decisions.concise_style.refused',
      },
    },
    {
      id: 'morning_window',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.config_tour.decisions.morning_window.phase',
      receiptLabelKey: 'showroom.m.config_tour.decisions.morning_window.receipt_label',
      icon: 'bell',
      toolNameKey: 'showroom.m.config_tour.decisions.morning_window.tool',
      args: [
        { labelKey: 'showroom.proposals.from', value: '07:00' },
        { labelKey: 'showroom.proposals.to', value: '09:00' },
      ],
      outcome: {
        confirm: 'showroom.m.config_tour.decisions.morning_window.applied',
        cancel: 'showroom.m.config_tour.decisions.morning_window.refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.m.config_tour.receipt.reads',
    proposedKey: 'showroom.m.config_tour.receipt.proposed',
  },
  noteKey: 'showroom.m.config_tour.note',
} satisfies ShowroomMissionDefinition);
