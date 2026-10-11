/**
 * Personal-assistant showroom: daily_briefing.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const DAILY_BRIEFING: ShowroomMissionDefinition = deepFreeze({
  id: 'daily_briefing',
  fixtureVersion: 'daily_briefing-v2',
  titleKey: 'showroom.m.daily_briefing.title',
  taglineKey: 'showroom.m.daily_briefing.tagline',
  mechanismKey: 'showroom.m.daily_briefing.mechanism',
  requestKey: 'showroom.m.daily_briefing.request',
  proactive: false,
  sources: [
    {
      id: 'calendar',
      labelKey: 'showroom.personal.daily_briefing.source_1',
      emoji: '📅',
      items: [
        {
          labelKey: 'showroom.personal.daily_briefing.fact_1',
        },
      ],
    },
    {
      id: 'relations',
      labelKey: 'showroom.personal.daily_briefing.source_2',
      emoji: '👥',
      items: [
        {
          labelKey: 'showroom.personal.daily_briefing.fact_2',
        },
      ],
    },
    {
      id: 'radio',
      labelKey: 'showroom.personal.daily_briefing.source_3',
      emoji: '📻',
      items: [
        {
          labelKey: 'showroom.personal.daily_briefing.fact_3',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.daily_briefing.finding_1',
    },
    {
      labelKey: 'showroom.personal.daily_briefing.finding_2',
    },
  ],
  traceKeys: [
    'showroom.trace.routing',
    'showroom.personal.trace_context',
    'showroom.personal.trace_compare',
    'showroom.personal.trace_result',
  ],
  decisions: [],
  receipt: {
    readsKey: 'showroom.m.daily_briefing.receipt.reads',
    proposedKey: 'showroom.m.daily_briefing.receipt.proposed',
  },
  noteKey: 'showroom.m.daily_briefing.note',
} satisfies ShowroomMissionDefinition);
