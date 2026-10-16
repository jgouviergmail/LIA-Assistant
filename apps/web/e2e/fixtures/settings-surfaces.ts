/** Real wire payloads for the neutral-surface browser proof; no provider calls. */
import type { MockRoute } from './api-mock';
import { appConfig } from './dashboard-shell';
import { radioOptions, radioPreferences } from '../../src/lib/radio/__tests__/fixtures';

const stamp = '2026-10-16T08:00:00Z';
export const surfacePeerName = 'Camille Surface Fixture';
export const surfaceJournalTitle =
  'A fictional observation about a long conversation and a shared project';
export const surfaceBookmarkAnswer = 'A fictional preserved answer';

export const surfaceMemoryCategories = [
  'preference',
  'personal',
  'relationship',
  'event',
  'pattern',
  'sensitivity',
  'procedural',
] as const;
/** Mirrors the pure MemoryListResponse wire fields in useMemories.ts. */
const surfaceMemories = {
  items: surfaceMemoryCategories.map((category, index) => ({
    id: `00000000-0000-4000-8000-${String(index + 301).padStart(12, '0')}`,
    content: 'A fictional preserved memory.',
    category,
    emotional_weight: 0,
    trigger_topic: 'fiction',
    usage_nuance: '',
    importance: 0.5,
  })),
  total: surfaceMemoryCategories.length,
  by_category: Object.fromEntries(surfaceMemoryCategories.map(category => [category, 1])),
};

export const surfaceRoutes: MockRoute[] = [
  { url: /\/api\/v1\/memories(?:\?.*)?$/, json: surfaceMemories },
  {
    url: '**/api/v1/memories/categories',
    json: {
      categories: surfaceMemoryCategories.map(name => ({
        name,
        label: name,
        description: 'Fictional category',
        icon: '',
      })),
    },
  },
  { url: '**/api/v1/psyche/summary', json: { summary: 'A fictional calm perspective about LIA.' } },
  { url: '**/api/v1/psyche/history**', json: [] },
  { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  {
    url: '**/api/v1/system-settings/debug-panel-status',
    json: { enabled: false, user_access_available: false },
  },
  { url: '**/api/v1/habits/presence', method: 'POST', status: 204 },
  {
    url: '**/api/v1/radio/budget',
    json: { limit_eur: 0, spent_eur: 0, window_hours: 24, lifts_at: null },
  },
  {
    url: '**/api/v1/voice/lia-voices',
    json: {
      available: true,
      engine: 'edge/edge-tts',
      provider: 'edge',
      male: null,
      female: null,
      voices: [
        { voice_id: 'fixture-male', label: 'Fixture male voice', gender: 'male', language: 'en' },
        {
          voice_id: 'fixture-female',
          label: 'Fixture female voice',
          gender: 'female',
          language: 'en',
        },
      ],
      default_male: {
        voice_id: 'fixture-male',
        label: 'Fixture male voice',
        gender: 'male',
        language: 'en',
      },
      default_female: {
        voice_id: 'fixture-female',
        label: 'Fixture female voice',
        gender: 'female',
        language: 'en',
      },
    },
  },

  {
    url: '**/api/v1/config',
    json: {
      ...appConfig,
      features: {
        ...appConfig.features,
        radio_enabled: true,
        peers_enabled: true,
        journals_enabled: true,
        bookmarks_enabled: true,
        health_metrics_enabled: true,
        image_generation_enabled: true,
      },
    },
  },
  {
    url: '**/api/v1/auth/me/voice-mode-preference',
    json: {
      voice_mode_enabled: false,
      voice_stt_mode: 'remote',
      stt_remote_available: true,
      stt_remote_provider: 'openai',
    },
  },
  {
    url: '**/api/v1/image-generation/options',
    json: {
      active_model: 'fixture-image-model',
      provider: 'openai',
      qualities: [
        { value: 'low', min_cost_usd: 0.01, max_cost_usd: 0.01 },
        { value: 'high', min_cost_usd: 0.04, max_cost_usd: 0.04 },
      ],
      sizes: [
        {
          value: '1024x1024',
          orientation: 'square',
          tier: null,
          label_key: 'settings.image_generation.size_square',
        },
      ],
      effective_quality: 'low',
      effective_size: '1024x1024',
      prompt_enhancement_available: true,
    },
  },
  { url: '**/api/v1/radio/options', json: radioOptions() },
  { url: '**/api/v1/radio/preferences', json: radioPreferences({ station_name: 'Fixture Radio' }) },
  { url: '**/api/v1/radio/sources', json: [] },
  {
    url: '**/api/v1/health-metrics/aggregate?*',
    json: {
      period: 'day',
      from_ts: '2026-10-15T00:00:00Z',
      to_ts: stamp,
      points: [
        {
          bucket: stamp,
          heart_rate_avg: 72,
          heart_rate_min: 60,
          heart_rate_max: 94,
          steps_total: 4800,
          has_data: true,
        },
      ],
      averages: { heart_rate_avg: 72, steps_per_day_avg: 4800 },
    },
  },
  { url: '**/api/v1/health-metrics/tokens', json: { tokens: [] } },
  {
    url: '**/api/v1/psyche/settings',
    json: {
      psyche_enabled: true,
      psyche_display_avatar: false,
      psyche_sensitivity: 50,
      psyche_stability: 50,
    },
  },
  { url: '**/api/v1/peers/me', json: { discovery_enabled: true, email_visible: false } },
  { url: '**/api/v1/peers/requests', json: [] },
  { url: '**/api/v1/peers/blocks', json: [] },
  { url: '**/api/v1/peers/access-log', json: [] },
  {
    url: '**/api/v1/peers/connections',
    json: [
      {
        id: '00000000-0000-4000-8000-000000000102',
        peer_id: '00000000-0000-4000-8000-000000000202',
        peer_display_name: surfacePeerName,
        peer_email_hint: 'c•••@example.test',
        peer_email: 'camille@example.test',
        status: 'accepted',
        direction: null,
        requested_at: stamp,
        responded_at: stamp,
        context_message: null,
        my_shares: [{ domain: 'calendar', level: 'availability' }],
        their_shares: [{ domain: 'calendar', level: 'details' }],
      },
    ],
  },
  {
    url: /\/api\/v1\/bookmarks\?/,
    json: {
      items: [
        {
          id: '00000000-0000-4000-8000-000000000301',
          message_id: null,
          conversation_id: null,
          content: `**${surfaceBookmarkAnswer}**`,
          request_content: 'A fictional request',
          answered_at: stamp,
          created_at: stamp,
        },
      ],
      total: 1,
      limit: 24,
      offset: 0,
      max_limit: 100,
      max_per_user: 500,
    },
  },
  { url: /\/api\/v1\/generated-assets\?/, json: { items: [], total: 0, limit: 24, offset: 0 } },
  {
    url: /\/api\/v1\/journals$/,
    json: {
      entries: [
        {
          id: '00000000-0000-4000-8000-000000000401',
          theme: 'self_reflection',
          title: surfaceJournalTitle,
          content: 'A quiet fictional observation.',
          mood: 'reflective',
          status: 'active',
          source: 'conversation',
          personality_code: null,
          char_count: 30,
          search_hints: null,
          injection_count: 0,
          last_injected_at: null,
          confidence: 'medium',
          evidence_count: 0,
          contradiction_count: 0,
          level: 'L0',
          created_at: stamp,
          updated_at: stamp,
        },
      ],
      by_theme: [{ theme: 'self_reflection', count: 1 }],
      total: 1,
      total_chars: 30,
      max_total_chars: 100000,
      usage_pct: 0.03,
    },
  },
  {
    url: '**/api/v1/journals/settings',
    json: {
      journals_enabled: true,
      journal_consolidation_enabled: false,
      journal_consolidation_with_history: false,
      journal_max_total_chars: 100000,
      journal_context_max_chars: 5000,
      journal_max_entry_chars: 1000,
      journal_context_max_results: 5,
      size_info: { total_chars: 30, max_total_chars: 100000, usage_pct: 0.03 },
      last_cost: {
        tokens_in: null,
        tokens_out: null,
        cost_eur: null,
        timestamp: null,
        source: null,
      },
    },
  },
  {
    url: '**/api/v1/journals/themes',
    json: {
      themes: [
        { code: 'self_reflection', label: 'Self-reflection' },
        { code: 'user_observations', label: 'User observations' },
        { code: 'ideas_analyses', label: 'Ideas and analyses' },
        { code: 'learnings', label: 'Learnings' },
      ],
    },
  },
];
