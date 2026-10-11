/**
 * Personal-assistant showroom: config_tour.
 * Historical telemetry id retained; the versioned fixture defines this story.
 * All data is fictional, immutable and resolved through the active locale.
 */

import { deepFreeze } from '@/components/showroom/missions/deep-freeze';
import type { ShowroomMissionDefinition } from '@/components/showroom/types';

export const CONFIG_TOUR: ShowroomMissionDefinition = deepFreeze({
  id: 'config_tour',
  fixtureVersion: 'config_tour-v2',
  titleKey: 'showroom.m.config_tour.title',
  taglineKey: 'showroom.m.config_tour.tagline',
  mechanismKey: 'showroom.m.config_tour.mechanism',
  requestKey: 'showroom.m.config_tour.request',
  proactive: false,
  sources: [
    {
      id: 'transcript',
      labelKey: 'showroom.personal.config_tour.source_1',
      emoji: '🎙️',
      items: [
        {
          labelKey: 'showroom.personal.config_tour.fact_1',
        },
      ],
    },
    {
      id: 'template',
      labelKey: 'showroom.personal.config_tour.source_2',
      emoji: '📄',
      items: [
        {
          labelKey: 'showroom.personal.config_tour.fact_2',
        },
      ],
    },
    {
      id: 'participants',
      labelKey: 'showroom.personal.config_tour.source_3',
      emoji: '👥',
      items: [
        {
          labelKey: 'showroom.personal.config_tour.fact_3',
        },
      ],
    },
  ],
  findings: [
    {
      labelKey: 'showroom.personal.config_tour.finding_1',
    },
    {
      labelKey: 'showroom.personal.config_tour.finding_2',
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
    readsKey: 'showroom.m.config_tour.receipt.reads',
    proposedKey: 'showroom.m.config_tour.receipt.proposed',
  },
  noteKey: 'showroom.m.config_tour.note',
} satisfies ShowroomMissionDefinition);
