/** Public capture data. Handwritten examples only; never reads an account or .env. */
import { dashboardShellMocks, briefingWindowsMock } from '../fixtures/dashboard-shell';
import { loadedChatRoutes } from '../fixtures/chat';
import { makeTestUser } from '../fixtures/test-user';
import type { MockRoute } from '../fixtures/api-mock';

export const CAPTURE_TIME = '2026-10-05T07:30:00Z';
const query = 'Help me prepare my day and show my next two appointments.';
const section = (data: unknown) => ({
  status: 'ok',
  data,
  generated_at: CAPTURE_TIME,
  error_code: null,
  error_message: null,
});
const hidden = {
  status: 'hidden',
  data: null,
  generated_at: CAPTURE_TIME,
  error_code: null,
  error_message: null,
};

const appointments = [
  {
    title: 'Design review',
    start_local: '10:00',
    end_local: '11:00',
    location: 'Demo Studio — meeting room A',
  },
  { title: 'Project check-in', start_local: '14:30', end_local: '15:00', location: 'Video call' },
];
const cards = {
  weather: section({
    location_city: 'Lyon',
    temperature_c: 21,
    feels_like_c: 20,
    description: 'Clear sky',
    condition_code: 'clear',
    icon_emoji: '☀️',
    wind_speed_kmh: 8,
    wind_direction_cardinal: 'NE',
    precipitation_probability: 0,
    temperature_min_c: 14,
    temperature_max_c: 23,
    forecast_alert: null,
    air_quality: null,
    pollen: [],
    daily_forecast: [0, 1, 2, 3, 4].map(day => ({
      date_iso: `2026-10-${String(5 + day).padStart(2, '0')}`,
      temp_min_c: 13 + day,
      temp_max_c: 22 + day,
      condition_code: day < 2 ? 'clear' : 'partly_cloudy',
      icon_emoji: day < 2 ? '☀️' : '⛅',
    })),
  }),
  agenda: section({ events: appointments }),
  mails: section({
    total_unread_today: 3,
    items: [
      {
        sender_name: 'Demo Studio',
        sender_email: 'studio@example.test',
        subject: 'Design review — agenda and notes',
        received_local: '09:05',
      },
      {
        sender_name: 'Demo Team',
        sender_email: 'team@example.test',
        subject: 'Project update for this week',
        received_local: '08:40',
      },
    ],
  }),
  birthdays: section({
    items: [
      { contact_name: 'Alex Demo', date_iso: '1991-10-05', days_until: 0, age_at_next: 35 },
      { contact_name: 'Morgan Demo', date_iso: '1996-10-08', days_until: 3, age_at_next: 30 },
    ],
  }),
  reminders: section({
    items: [
      {
        id: 'demo-reminder',
        content: 'Bring the notebook to the design review',
        trigger_at_local: '09:45',
        repeats: false,
      },
    ],
  }),
  health: hidden,
  for_you: hidden,
  tasks: section({
    overdue_count: 0,
    items: [
      {
        title: 'Review the presentation',
        due_date_iso: '2026-10-05',
        days_until_due: 0,
        overdue: false,
      },
      {
        title: 'Prepare next week’s ideas',
        due_date_iso: '2026-10-06',
        days_until_due: 1,
        overdue: false,
      },
    ],
  }),
  documents: hidden,
  workboard: hidden,
};

export const chatContent = `<p>You have a clear plan for today: a design review this morning, then a short project check-in after lunch.</p>
<div class="lia-card lia-calendar"><div class="lia-card__header"><strong>Design review</strong></div><div class="lia-card__content"><p>Monday, October 5 · 10:00–11:00</p><p>📍 Demo Studio — meeting room A</p><details><summary>See more</summary><p>Review the new concept, collect feedback and agree on next steps.</p></details></div></div>
<div class="lia-card lia-calendar"><div class="lia-card__header"><strong>Project check-in</strong></div><div class="lia-card__content"><p>Monday, October 5 · 14:30–15:00</p><p>📍 Video call</p><details><summary>See more</summary><p>A brief progress update with the demonstration team.</p></details></div></div>
<h3>A little preparation goes a long way</h3><ul><li>Read the design notes before 10:00.</li><li>Keep a short break between meetings.</li><li>Bring your notebook and two questions for the team.</li></ul>`;

export function messages(content: string, metadata: unknown = null, userQuery = query) {
  return {
    messages: [
      {
        id: 'demo-message-user',
        role: 'user',
        content: userQuery,
        created_at: '2026-10-05T07:29:00Z',
      },
      {
        id: 'demo-message-assistant',
        role: 'assistant',
        content,
        message_metadata: metadata,
        created_at: CAPTURE_TIME,
        tokens_in: 2400,
        tokens_out: 380,
        tokens_cache: 800,
        cost_eur: 0.0018,
        google_api_requests: 1,
      },
    ].reverse(),
    conversation_id: '00000000-0000-4000-8000-00000000c0h1',
    total_count: 2,
    has_more: false,
    next_cursor: null,
  };
}

const memoryItems = [
  ['preference', 'I prefer concise answers with practical next steps.', 'Communication'],
  ['preference', 'Suggest a short walk between long meetings.', 'Daily routine'],
  ['personal', 'I enjoy photography and visiting exhibitions.', 'Hobbies'],
  ['relationship', 'Alex Demo is part of the demonstration project team.', 'Demo team'],
  ['event', 'The demonstration design review takes place on Monday.', 'Demo project'],
  ['procedural', 'Ask for confirmation before sending a message on my behalf.', 'Approval'],
].map(([category, content, trigger_topic], index) => ({
  id: `demo-memory-${index}`,
  category,
  content,
  trigger_topic,
  emotional_weight: 3,
  usage_nuance: 'Demonstration example',
  importance: 0.7,
  pinned: index === 0,
  usage_count: 4,
  created_at: CAPTURE_TIME,
  updated_at: CAPTURE_TIME,
  purge_risk: index === 0 ? 'protected' : 'safe',
  retention_score: 0.8,
}));

const llmSlots = [
  ['query_analyzer', 'Query Analyzer', 'pipeline', 'openai', 'gpt-4.1-mini'],
  ['planner', 'Planner', 'pipeline', 'anthropic', 'claude-sonnet-4-6'],
  ['react_agent', 'ReAct Agent', 'pipeline', 'anthropic', 'claude-sonnet-4-6'],
  ['contacts_agent', 'Contacts Agent', 'domain_agents', 'openai', 'gpt-4.1-mini'],
  ['calendar_agent', 'Calendar Agent', 'domain_agents', 'openai', 'gpt-4.1-mini'],
  ['response', 'Response', 'query_response', 'openai', 'gpt-4.1'],
].map(([llm_type, display_name, category, provider, model]) => {
  const config = {
    provider,
    model,
    provider_config: '{}',
    temperature: 0.3,
    top_p: 1,
    frequency_penalty: 0,
    presence_penalty: 0,
    max_tokens: 4096,
    timeout_seconds: 60,
    reasoning_effort: null,
    context_window: null,
  };
  return {
    llm_type,
    info: {
      llm_type,
      display_name,
      category,
      description_key: `settings.admin.llmConfig.types.${llm_type}`,
      required_capabilities: [],
      power_tier: 'medium',
      required_kind: 'chat',
    },
    effective: config,
    defaults: config,
    overrides: {},
    is_overridden: false,
  };
});

export const debugHistory = [
  {
    id: 'demo-run',
    timestamp: CAPTURE_TIME,
    query,
    metrics: {
      execution_mode: 'pipeline',
      intent_detection: {
        detected_intent: 'actionable',
        confidence: 0.96,
        user_goal: 'Prepare the day and retrieve two appointments',
        goal_reasoning: 'Read-only calendar request',
        thresholds: {
          high_threshold: { value: 0.7, actual: 0.96, passed: true },
          fallback_threshold: { value: 0.5, actual: 0.96, passed: true },
        },
      },
      domain_selection: {
        selected_domains: ['calendar'],
        primary_domain: 'calendar',
        top_score: 0.95,
        all_scores: { calendar: 0.95 },
        thresholds: {
          primary_min: { value: 0.15, actual: 0.95, passed: true },
          max_domains: { value: 3, info: 'Maximum domains to select' },
        },
      },
      routing_decision: {
        route_to: 'planner',
        confidence: 0.96,
        bypass_llm: false,
        reasoning_trace: ['Calendar data requested', 'Read-only plan'],
        thresholds: {
          chat_semantic_threshold: { value: 0.4, actual: 0.96, passed: true },
          high_semantic_threshold: { value: 0.7, actual: 0.96, passed: true },
          min_confidence: { value: 0.5, actual: 0.96, passed: true },
          chat_override_threshold: { value: 0.75, info: 'Override threshold' },
        },
      },
      context_resolution: {
        turn_type: 'initial',
        is_reference: false,
        source_turn_id: null,
        source_domain: null,
        resolved_references: null,
        thresholds: {
          confidence_threshold: { value: 0.6, info: 'Minimum confidence' },
          active_window_turns: { value: 6, info: 'Active window' },
        },
      },
      query_info: {
        original_query: query,
        english_query: query,
        english_enriched_query: null,
        user_language: 'en',
        implicit_intents: [],
        anticipated_needs: [],
        fallback_strategies: [],
      },
    },
  },
];

export function publicScreenshotRoutes(): MockRoute[] {
  return [
    ...dashboardShellMocks,
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/capabilities',
      json: {
        nodes: [
          { key: 'memory', active: true, detail: memoryItems.length },
          { key: 'connectors', active: false, detail: 0 },
        ],
        live: 1,
        total: 2,
      },
    },
    { url: '**/api/v1/telephony/calls*', json: { calls: [], total: 0 } },
    { url: '**/api/v1/channels', json: { bindings: [], total: 0, telegram_bot_username: null } },
    {
      url: '**/api/v1/heartbeat/settings',
      json: {
        heartbeat_enabled: false,
        heartbeat_notify_start_hour: 8,
        heartbeat_notify_end_hour: 22,
        available_sources: [],
        disabled_sources: [],
        all_sources: [],
        source_dependencies: {},
      },
    },
    { url: '**/api/v1/scheduled-actions', json: { actions: [], total: 0 } },
    {
      url: '**/api/v1/scheduled-actions/week*',
      json: { week_start: '2026-10-05', today: 1, cells: [] },
    },
    {
      url: '**/api/v1/product/me/results',
      json: {
        cycle_start: '2026-10-01T00:00:00Z',
        useful_results: 32,
        actions: 12,
        automations: 8,
        commitments_closed: 5,
        measured: true,
      },
    },
    {
      url: '**/api/v1/auth/me',
      json: {
        ...makeTestUser({
          full_name: 'Alex Demo',
          email: 'alex@example.test',
          is_superuser: true,
          language: 'en',
          timezone: 'Europe/Paris',
          response_display_mode: 'html_cards',
          debug_panel_enabled: true,
        }),
        onboarding_checklist: { celebrated_at: CAPTURE_TIME },
      },
    },
    { url: '**/api/v1/conversations/me/messages*', json: messages(chatContent) },
    {
      url: '**/api/v1/conversations/me/totals',
      json: {
        total_tokens_in: 12400,
        total_tokens_out: 2800,
        total_tokens_cache: 4200,
        total_cost_eur: 0.04,
        total_google_api_requests: 3,
        context_tokens: 8200,
        context_threshold: 100000,
      },
    },
    { url: '**/api/v1/briefing/cards', json: { windows: briefingWindowsMock, cards } },
    {
      url: '**/api/v1/briefing/synthesis',
      json: {
        greeting: {
          text: 'Good morning, Alex. A clear plan and a little room to breathe.',
          generated_at: CAPTURE_TIME,
          usage: null,
        },
        synthesis: {
          text: 'Your design review starts at 10:00. Read the notes beforehand, then keep a short break before your afternoon check-in. You have three new messages and one reminder to bring your notebook.',
          generated_at: CAPTURE_TIME,
          usage: null,
        },
      },
    },
    {
      url: '**/api/v1/briefing/preferences',
      json: { hidden: ['health', 'for_you', 'documents', 'workboard'], order: Object.keys(cards) },
    },
    {
      url: '**/api/v1/briefing/companion-context',
      json: { timezone: 'Europe/Paris', weather: null },
    },
    {
      url: '**/api/v1/chat/users/me/statistics',
      json: {
        total_since: '2026-09-01T00:00:00Z',
        total_messages: 420,
        total_prompt_tokens: 420000,
        total_completion_tokens: 80000,
        total_cached_tokens: 120000,
        total_cost_eur: 2.84,
        total_google_api_requests: 64,
        cycle_messages: 48,
        cycle_prompt_tokens: 42000,
        cycle_completion_tokens: 8000,
        cycle_cached_tokens: 12000,
        cycle_cost_eur: 0.28,
        cycle_google_api_requests: 8,
        current_cycle_start: '2026-10-01T00:00:00Z',
      },
    },
    {
      url: '**/api/v1/memories/categories',
      json: {
        categories: [
          'preference',
          'personal',
          'relationship',
          'event',
          'pattern',
          'sensitivity',
          'procedural',
        ].map(name => ({ name, label: name, description: '', icon: '🧠' })),
      },
    },
    {
      url: '**/api/v1/memories',
      json: {
        items: memoryItems,
        total: memoryItems.length,
        by_category: { preference: 2, personal: 1, relationship: 1, event: 1, procedural: 1 },
      },
    },
    {
      url: '**/api/v1/psyche/settings',
      json: {
        psyche_enabled: true,
        psyche_display_avatar: true,
        psyche_sensitivity: 0.6,
        psyche_stability: 0.7,
      },
    },
    {
      url: '**/api/v1/psyche/summary*',
      json: {
        summary:
          'LIA is calm, curious and ready to help. Our demonstration conversations have built a comfortable rhythm: concise answers, practical suggestions and room for a little humour.',
      },
    },
    { url: '**/api/v1/psyche/history*', json: { snapshots: [], hours: 24 } },
    { url: '**/api/v1/connectors', json: { connectors: [] } },
    {
      url: '**/api/v1/journals/portrait',
      json: { full: null, brief: null, compiled_at: null, sources: null },
    },
    { url: '**/api/v1/habits/presence', json: {} },
    { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
    { url: '**/api/v1/skills*', json: { skills: [] } },
    { url: '**/api/v1/chat/shortcuts*', json: { shortcuts: [] } },
    { url: '**/api/v1/chat/suggestions*', json: { suggestions: [] } },
    {
      url: '**/api/v1/system-settings/debug-panel-status',
      json: { enabled: false, user_access_available: true },
    },
    { url: '**/api/v1/debug/jev', json: { calls: [], limit: 30, retention_seconds: 3600 } },
    { url: '**/api/v1/voice/ticket', json: { ticket: 'public-demo-ticket', ttl_seconds: 60 } },
    { url: '**/api/v1/admin/llm-config/types', json: { configs: llmSlots } },
    {
      url: '**/api/v1/admin/llm-config/providers',
      json: {
        providers: ['openai', 'anthropic', 'google'].map(provider => ({
          provider,
          display_name:
            provider === 'openai' ? 'OpenAI' : provider === 'anthropic' ? 'Anthropic' : 'Google',
          has_db_key: true,
          masked_key: '•••••••• DEMO',
          updated_at: CAPTURE_TIME,
        })),
      },
    },
    { url: '**/api/v1/admin/llm-config/metadata/models*', json: { providers: {} } },
    {
      url: '**/api/v1/admin/capabilities',
      json: ['image_generation', 'live', 'radio', 'memory', 'skills', 'browser'].map(
        capability => ({
          capability,
          label_key: `capabilities.items.${capability}`,
          switch_enabled: true,
          deployment_available: true,
          effective_enabled: true,
          enforced_in_catalogue: true,
          enforced_on_routes: true,
          enforced_in_service: false,
          family: ['image_generation', 'live', 'radio'].includes(capability)
            ? 'media'
            : 'knowledge',
          updated_by: null,
          updated_at: CAPTURE_TIME,
          is_default: true,
        })
      ),
    },
  ];
}
