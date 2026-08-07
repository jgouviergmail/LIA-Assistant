/**
 * Mission: it makes the call (outbound telephony).
 *
 * The real-world-action differentiator: LIA prepares a restaurant call —
 * goal, script, callee — and NOTHING is dialed without the visitor's
 * explicit approval. A refusal renders as a respected outcome; a
 * confirmation reveals a synthetic call summary and transcript extract.
 *
 * Same data contract as every mission fixture: i18n keys, bounded 'HH:MM'
 * literals, deep-frozen (fixtures.test.ts).
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const PHONE_BOOKING: ShowroomMissionDefinition = deepFreeze({
  id: 'phone_booking',
  fixtureVersion: 'phone_booking-v1',
  titleKey: 'showroom.m.phone_booking.title',
  taglineKey: 'showroom.m.phone_booking.tagline',
  mechanismKey: 'showroom.m.phone_booking.mechanism',
  requestKey: 'showroom.m.phone_booking.request',
  proactive: false,
  sources: [
    {
      id: 'tasks',
      labelKey: 'showroom.sources.tasks',
      emoji: '✅',
      items: [{ labelKey: 'showroom.m.phone_booking.facts.birthday' }],
    },
    {
      id: 'contacts',
      labelKey: 'showroom.sources.contacts',
      emoji: '👥',
      items: [{ labelKey: 'showroom.m.phone_booking.facts.leon' }],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.sources.calendar',
      emoji: '📅',
      items: [{ labelKey: 'showroom.m.phone_booking.facts.saturday_free', time: '19:30' }],
    },
  ],
  findings: [
    { labelKey: 'showroom.m.phone_booking.findings.script_ready', time: '20:00' },
    { labelKey: 'showroom.m.phone_booking.findings.hitl_gate' },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.trace.sources',
    'showroom.trace.planning',
    'showroom.m.phone_booking.trace_script',
  ],
  decisions: [
    {
      id: 'authorize_call',
      kind: 'tool',
      allowed: ['confirm', 'cancel'],
      phaseLabelKey: 'showroom.m.phone_booking.decisions.authorize_call.phase',
      receiptLabelKey: 'showroom.m.phone_booking.decisions.authorize_call.receipt_label',
      icon: 'phone',
      toolNameKey: 'showroom.m.phone_booking.decisions.authorize_call.tool',
      args: [
        {
          labelKey: 'showroom.m.phone_booking.decisions.authorize_call.callee',
          valueKey: 'showroom.m.phone_booking.decisions.authorize_call.callee_value',
        },
        {
          labelKey: 'showroom.m.phone_booking.decisions.authorize_call.goal',
          valueKey: 'showroom.m.phone_booking.decisions.authorize_call.goal_value',
        },
      ],
      outcome: {
        confirm: 'showroom.m.phone_booking.decisions.authorize_call.applied',
        cancel: 'showroom.m.phone_booking.decisions.authorize_call.refused',
      },
    },
  ],
  receipt: {
    readsKey: 'showroom.m.phone_booking.receipt.reads',
    proposedKey: 'showroom.m.phone_booking.receipt.proposed',
  },
  noteKey: 'showroom.m.phone_booking.note',
} satisfies ShowroomMissionDefinition);
