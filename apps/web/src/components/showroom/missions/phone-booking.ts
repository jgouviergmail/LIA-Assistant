/**
 * Personal-assistant showroom: phone_booking.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const PHONE_BOOKING: ShowroomMissionDefinition = deepFreeze({
  id: 'phone_booking',
  fixtureVersion: 'phone_booking-v2',
  titleKey: 'showroom.m.phone_booking.title',
  taglineKey: 'showroom.m.phone_booking.tagline',
  mechanismKey: 'showroom.m.phone_booking.mechanism',
  requestKey: 'showroom.m.phone_booking.request',
  proactive: false,
  sources: [
    {
      id: 'contacts',
      labelKey: 'showroom.personal.phone_booking.source_1',
      emoji: '☎️',
      items: [
        {
          labelKey: 'showroom.personal.phone_booking.fact_1',
        },
      ],
    },
    {
      id: 'calendar',
      labelKey: 'showroom.personal.phone_booking.source_2',
      emoji: '📅',
      items: [
        {
          labelKey: 'showroom.personal.phone_booking.fact_2',
        },
      ],
    },
    {
      id: 'mandate',
      labelKey: 'showroom.personal.phone_booking.source_3',
      emoji: '📝',
      items: [
        {
          labelKey: 'showroom.personal.phone_booking.fact_3',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.phone_booking.finding_1',
    },
    {
      labelKey: 'showroom.personal.phone_booking.finding_2',
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
      id: 'authorize_call',
      kind: 'phone_draft',
      allowed: ['confirm', 'edit', 'cancel'],
      phaseLabelKey: 'showroom.m.phone_booking.decisions.authorize_call.phase',
      receiptLabelKey: 'showroom.m.phone_booking.decisions.authorize_call.receipt_label',
      icon: 'phone',
      calleeNameKey: 'showroom.personal.phone_booking.callee',
      calleePhone: '+1 202 555 0100',
      objectiveKey: 'showroom.personal.phone_booking.goal',
      previewHtmlKey: 'showroom.personal.phone_booking.preview_html',
      outcome: {
        confirm: 'showroom.m.phone_booking.decisions.authorize_call.applied',
        edit: 'showroom.personal.phone_booking.edit_outcome',
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
