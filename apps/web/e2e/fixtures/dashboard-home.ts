/** Full, typed home payloads: no backend, model, audio or provider is contacted. */
import type {
  BriefingResponse,
  BriefingSection,
  CardSection,
  SectionData,
  WorkboardTicketItem,
} from '../../src/types/briefing';
import type { RadioPreferences } from '../../src/lib/radio/types';
import type { ActiveRunStatus } from '../../src/lib/api/chat';
import { meetingDetail } from '../../src/__tests__/fixtures/meeting-detail';
import { appConfig, briefingWindowsMock } from './dashboard-shell';
import { idleNotificationStream, type MockRoute } from './api-mock';
import type { TestUser } from './test-user';

export const HOME_NOW = '2026-10-15T23:45:00Z';
export const HOME_GENERATED = '2026-10-15T23:40:00Z';
export const HOME_TIMEZONE = 'Pacific/Honolulu';
export const HOME_GREETING = 'Guten Abend Camille, hier ist dein persönlicher Überblick.';
export const HOME_SYNTHESIS =
  'Die internationale Projektbesprechung beginnt um 09:00. Deine Aufgaben und Erinnerungen bleiben vollständig erreichbar, auch wenn ihre Bezeichnungen sehr lang sind.';
export const HOME_MEETING_RESULT_TITLE =
  'Point de coordination des équipes internationales — décisions, responsabilités et préparation détaillée du prochain atelier';

/** Native recorder reconciliation reaches a terminal mocked result, never a microphone. */
export function homeMeetingResult(status: 'ready' | 'failed') {
  return meetingDetail({
    id: 'toast-result',
    status,
    started_at: HOME_GENERATED,
    stopped_at: HOME_NOW,
    report: { title: HOME_MEETING_RESULT_TITLE, participants: [], sections: [] },
    last_error_code: status === 'failed' ? 'synthesis_failed' : null,
  });
}

export const HOME_ORDER: BriefingSection[] = [
  'weather',
  'birthdays',
  'reminders',
  'health',
  'agenda',
  'mails',
  'for_you',
  'tasks',
  'documents',
  'workboard',
];

// Nominal server caps: core/constants.py BRIEFING_MAX_*_ITEMS_DEFAULT.
// These are received pages, never a claim to show the server's entire history.
export const HOME_CAPS = {
  agenda: 10,
  mails: 10,
  birthdays: 10,
  reminders: 10,
  for_you: 10,
  tasks: 10,
  documents: 5,
  workboard: 3,
} as const;

export function homeItemName(section: keyof typeof HOME_CAPS, index: number): string {
  return `${section} ${String(index + 1).padStart(2, '0')} · Internationale Projektabstimmung und ausführliche Vorbereitung`;
}

/** Aggregate sets are exact counts; their two received titles are only previews. */
export const HOME_WORKBOARD_GROUPS = [
  { key: 'held_by_me', labelKey: 'settings.workboard.tile_mine', count: 9 },
  { key: 'held_by_lia', labelKey: 'settings.workboard.tile_lia', count: 4 },
  {
    key: 'held_by_peers',
    labelKey: 'dashboard.briefing.cards.workboard.held_by_peers',
    count: 7,
  },
  { key: 'overdue', labelKey: 'settings.workboard.tile_overdue', count: 3 },
  { key: 'open_total', labelKey: 'dashboard.briefing.cards.workboard.tile_open', count: 13 },
] as const;

export type HomeWorkboardGroup = (typeof HOME_WORKBOARD_GROUPS)[number]['key'];

export function homeWorkboardPreviewName(group: HomeWorkboardGroup, index: number): string {
  return `${group} ${index + 1} · Übergabe der vollständigen internationalen Projektunterlagen`;
}

function workboardPreview(group: HomeWorkboardGroup): WorkboardTicketItem[] {
  return items(2, index => ({
    id: `preview-${group}-${index}`,
    title: homeWorkboardPreviewName(group, index),
    status: 'waiting',
    due_at: group === 'held_by_lia' && index === 0 ? '2026-10-16T09:45:00Z' : null,
    overdue: group === 'overdue',
  }));
}

function items<T>(count: number, make: (index: number) => T): T[] {
  return Array.from({ length: count }, (_, index) => make(index));
}

function section<T extends SectionData>(data: T): CardSection<T> {
  return {
    status: 'ok',
    data,
    generated_at: HOME_GENERATED,
    error_code: null,
    error_message: null,
    from_cache: true,
    stale_generated_at: null,
    last_attempt_at: null,
  };
}

/** Mirrors all ten REQUIRED CardsBundle sections and both TextSection envelopes. */
export function homeBriefing(): BriefingResponse {
  const usage = {
    tokens_in: 740,
    tokens_out: 85,
    tokens_cache: 120,
    cost_eur: 0.0017,
    model_name: 'hermetic-fixture',
  };
  return {
    windows: { ...briefingWindowsMock },
    greeting: { text: HOME_GREETING, generated_at: HOME_GENERATED, usage },
    synthesis: { text: HOME_SYNTHESIS, generated_at: HOME_GENERATED, usage },
    cards: {
      weather: section({
        temperature_c: 21,
        temperature_min_c: 14,
        temperature_max_c: 23,
        condition_code: 'Clouds',
        description: 'Überwiegend bewölkt',
        icon_emoji: '☁️',
        location_city: 'Saint-Rémy-en-Bouzemont-Saint-Genest-et-Isson',
        wind_speed_kmh: 15,
        wind_direction_cardinal: 'NE',
        precipitation_probability: 0.35,
        forecast_alert: { kind: 'rain', time: '18:30' },
        daily_forecast: items(5, index => ({
          date_iso: `2026-10-${15 + index}`,
          temp_min_c: 12 + index,
          temp_max_c: 22 + index,
          condition_code: 'Clouds',
          icon_emoji: '☁️',
        })),
        air_quality: { value: 32, category: 'Gut', index_label: 'Universal AQI' },
        pollen: [{ name: 'Gräser', category: 'Gering', index: 1 }],
      }),
      agenda: section({
        events: items(HOME_CAPS.agenda, index => ({
          id: `agenda-${index}`,
          start_at: new Date(
            Date.UTC(2026, 9, 15 + Math.floor(index / 5), 19 + (index % 5))
          ).toISOString(),
          title: homeItemName('agenda', index),
          start_local: `${String(9 + (index % 5)).padStart(2, '0')}:00`,
          end_local: `${String(9 + (index % 5)).padStart(2, '0')}:30`,
          // Current payloads carry one already-localized range; the last row
          // deliberately models an old cached response that lacks the field.
          ...(index === HOME_CAPS.agenda - 1
            ? {}
            : {
                time_range_local: `${index < 5 ? 'aujourd’hui' : 'demain'} ${String(9 + (index % 5)).padStart(2, '0')}:00 – ${String(9 + (index % 5)).padStart(2, '0')}:30`,
              }),
          location: 'Besprechungsraum Alexander-von-Humboldt',
        })),
      }),
      mails: section({
        total_unread_today: 42,
        items: items(HOME_CAPS.mails, index => ({
          sender_name: 'Internationale Koordinationsstelle',
          sender_email: 'koordination@example.test',
          subject: homeItemName('mails', index),
          received_local: '08:35',
        })),
      }),
      birthdays: section({
        items: items(HOME_CAPS.birthdays, index => ({
          contact_name: homeItemName('birthdays', index),
          date_iso: '--10-16',
          days_until: 1,
          age_at_next: 40 + index,
        })),
      }),
      reminders: section({
        items: items(HOME_CAPS.reminders, index => ({
          id: `reminder-${index}`,
          content: homeItemName('reminders', index),
          trigger_at_local: 'Demain à 09:15',
          repeats: false,
        })),
      }),
      health: section({
        items: [
          {
            kind: 'steps',
            value_today: 8342,
            value_avg_window: 7100,
            unit: 'steps',
            window_days: 14,
            days_with_data: 14,
          },
          {
            kind: 'heart_rate',
            value_today: 68,
            value_avg_window: 72,
            unit: 'bpm',
            window_days: 14,
            days_with_data: 12,
          },
        ],
      }),
      for_you: section({
        open_loops: items(HOME_CAPS.for_you, index => ({
          id: `loop-${index}`,
          subject: homeItemName('for_you', index),
          counterparty: 'Camille',
          direction: 'user_owes',
          due_hint: null,
          days_open: index + 1,
        })),
        recent_automations: [],
        next_automation: {
          id: 'automation-1',
          title: 'Nächste internationale Zusammenfassung',
          executed_at: null,
          next_trigger_at: '2026-10-16T17:00:00Z',
          next_trigger_local: 'Demain à 07:00',
        },
      }),
      tasks: section({
        overdue_count: 2,
        items: items(HOME_CAPS.tasks, index => ({
          title: homeItemName('tasks', index),
          due_date_iso: index < 2 ? '2026-10-14' : '2026-10-16',
          days_until_due: index < 2 ? -1 : 1,
          overdue: index < 2,
        })),
      }),
      documents: section({
        items: items(HOME_CAPS.documents, index => ({
          name: homeItemName('documents', index),
          modified_local: 'Aujourd’hui à 08:45',
          web_view_link: `https://drive.example.test/document-${index}`,
          mime_type: 'application/pdf',
        })),
      }),
      workboard: section({
        needs_me: 11,
        held_by_me: 9,
        held_by_lia: 4,
        held_by_peers: 7,
        overdue: 3,
        open_total: 13,
        items: items(HOME_CAPS.workboard, index => ({
          id: `ticket-${index}`,
          title: homeItemName('workboard', index),
          status: 'waiting',
          due_at: null,
          overdue: false,
        })),
        previews: {
          // Sent for the hub; the card shows no « needs me » set.
          needs_me: [],
          held_by_me: workboardPreview('held_by_me'),
          held_by_lia: workboardPreview('held_by_lia'),
          held_by_peers: workboardPreview('held_by_peers'),
          overdue: workboardPreview('overdue'),
          open_total: workboardPreview('open_total'),
        },
      }),
    },
  };
}

/** UserStatistics, with different period/lifetime values and real cost field names. */
export const HOME_STATISTICS = {
  total_since: '2026-01-01T12:00:00Z',
  current_cycle_start: '2026-10-01',
  cycle_prompt_tokens: 1200,
  cycle_completion_tokens: 300,
  cycle_cached_tokens: 100,
  total_prompt_tokens: 12000,
  total_completion_tokens: 3000,
  total_cached_tokens: 1000,
  cycle_cost_eur: 2.34,
  total_cost_eur: 23.45,
  cycle_messages: 17,
  total_messages: 217,
  cycle_google_api_requests: 8,
  total_google_api_requests: 108,
  cycle_google_api_cost_eur: 0.12,
  total_google_api_cost_eur: 1.23,
};

const radioPreferences: RadioPreferences = {
  frequencies: {},
  disabled_sources: [],
  disabled_feeds: [],
  voices: {},
  verification: null,
  timer_minutes: null,
  public_mode: false,
  personality_id: null,
  station_name: 'Hermetic Home Radio',
};

export function homeRoutes(user: TestUser, briefing = homeBriefing()): MockRoute[] {
  return [
    {
      url: '**/api/v1/auth/me',
      json: { ...user, onboarding_checklist: { dismissed_at: HOME_GENERATED } },
    },
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, radio_enabled: true },
        capabilities: { radio: { enabled: true, family: 'media' } },
      },
    },
    {
      url: '**/api/v1/briefing/cards/initial',
      method: 'GET',
      json: {
        cards: briefing.cards,
        windows: briefing.windows,
        pending: [],
        act: 'e2e-act',
        act_expires_at: '2099-01-01T00:00:00Z',
        section_concurrency: 4,
      },
    },
    {
      url: '**/api/v1/briefing/text',
      method: 'POST',
      json: {
        greeting: briefing.greeting,
        synthesis: briefing.synthesis,
        reused: false,
        state: 'ready',
      },
    },
    {
      url: '**/api/v1/briefing/preferences',
      method: 'GET',
      json: { hidden: [], order: HOME_ORDER },
    },
    { url: '**/api/v1/chat/users/me/statistics', method: 'GET', json: HOME_STATISTICS },
    {
      url: '**/api/v1/product/me/results',
      method: 'GET',
      json: {
        cycle_start: '2026-10-01',
        useful_results: 37,
        actions: 19,
        automations: 11,
        commitments_closed: 7,
        measured: true,
      },
    },
    { url: '**/api/v1/radio/preferences', method: 'GET', json: radioPreferences },
    { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
    // PresencePing posts no payload; the real endpoint acknowledges with an empty 204.
    {
      url: '**/api/v1/habits/presence',
      method: 'POST',
      handler: async route => {
        await route.fulfill({ status: 204, body: '' });
      },
    },
    // CompanionPresence polls the existing read-only active-run contract.
    {
      url: '**/api/v1/agents/runs/active',
      method: 'GET',
      json: { active: false } satisfies ActiveRunStatus,
    },
    idleNotificationStream,
  ];
}
