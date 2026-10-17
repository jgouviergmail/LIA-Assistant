/** Typed, owner-scoped meeting pages; no backend, recorder or paid provider is contacted. */
import type { Page, Request } from '@playwright/test';
import type {
  MeetingListResponse,
  MeetingPreferences,
  MeetingSummary,
  MeetingTemplateListResponse,
} from '../../src/types/meetings';
import { idleNotificationStream, type MockRoute } from './api-mock';
import { minimizeCompanion } from './companion';
import { appConfig } from './dashboard-shell';
import type { TestUser } from './test-user';

export const MEETING_TIMELINE_NOW = '2026-10-26T12:00:00Z';
export const MEETING_BROWSER_ZONE = 'Europe/Paris';
// Deliberately different: the existing list formats in the BROWSER zone.
export const MEETING_ACCOUNT_ZONE = 'Pacific/Honolulu';
export const MEETING_LONG_TITLE =
  'Réunion internationale — décisions, responsabilités et préparation détaillée du prochain atelier avec les équipes de Saint-Rémy-en-Bouzemont-Saint-Genest-et-Isson';

function meeting(index: number, overrides: Partial<MeetingSummary> = {}): MeetingSummary {
  return {
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    status: 'ready',
    stage: null,
    title: `Réunion de suivi ${String(index + 1).padStart(2, '0')}`,
    started_at: '2026-10-24T18:30:00Z',
    stopped_at: '2026-10-24T18:50:00Z',
    audio_duration_seconds: 1200,
    participants_count: 2,
    action_items_count: 3,
    index_state: 'indexed',
    stt_provider: 'local',
    total_cost_eur: null,
    last_error_code: null,
    template_ref: 'builtin:meeting',
    template_name: 'Compte rendu vérifié — décisions et prochaines étapes',
    template_selection: 'auto',
    source_meeting_id: null,
    ...overrides,
  };
}

/** Newest first, exactly as GET /meetings returns it. Durations are NOT wall-time subtraction. */
export function meetingTimeline(): MeetingSummary[] {
  return [
    meeting(0, {
      title: MEETING_LONG_TITLE,
      started_at: '2026-10-26T00:15:00Z',
      stopped_at: '2026-10-26T00:35:00Z',
      audio_duration_seconds: 0,
      participants_count: 0,
      action_items_count: 0,
    }),
    meeting(1, {
      title: 'Réunion après minuit — même transcription et fin le lendemain',
      started_at: '2026-10-25T22:50:00Z',
      stopped_at: '2026-10-25T23:10:00Z',
      audio_duration_seconds: 17,
      template_selection: 'user',
      source_meeting_id: '00000000-0000-4000-8000-000000000099',
      total_cost_eur: 0.0123,
      stt_provider: 'openai',
      index_state: 'pending',
    }),
    meeting(2, {
      title: 'Réunion après le changement d’heure — deuxième 02:45',
      started_at: '2026-10-25T01:45:00Z',
      stopped_at: '2026-10-25T02:05:00Z',
      audio_duration_seconds: 900,
      stt_provider: 'fishaudio',
      template_selection: 'preference',
      index_state: 'error',
    }),
    meeting(3, {
      title: 'Réunion pendant le changement d’heure — premier 02:45',
      started_at: '2026-10-25T00:45:00Z',
      stopped_at: '2026-10-25T01:15:00Z',
      audio_duration_seconds: 1800,
      stt_provider: 'elevenlabs',
      index_state: 'disabled',
    }),
    meeting(4, {
      title: 'Réunion en transcription — informations encore inconnues',
      started_at: '2026-10-24T23:30:00Z',
      stopped_at: '2026-10-24T23:45:00Z',
      status: 'processing',
      stage: 'transcribing',
      audio_duration_seconds: null,
      template_ref: null,
      template_name: null,
      template_selection: null,
      index_state: null,
      stt_provider: null,
    }),
    meeting(5, {
      title: 'Réunion interrompue — aucune fin enregistrée',
      started_at: '2026-10-24T22:30:00Z',
      stopped_at: null,
      status: 'interrupted',
      index_state: null,
    }),
    meeting(6, {
      title: 'Réunion arrêtée — une heure d’audio conservée',
      started_at: '2026-10-24T20:30:00Z',
      stopped_at: '2026-10-24T21:45:00Z',
      status: 'stopped',
      audio_duration_seconds: 3600,
      index_state: 'pending',
    }),
    meeting(7, {
      title: null,
      status: 'failed',
      index_state: null,
      stt_provider: null,
      template_ref: null,
      template_name: null,
      template_selection: null,
    }),
  ];
}

/** Two real API pages: 20 + 3. Extra entries precede neither the DST nor midnight probes. */
export function pagedMeetingTimeline(): MeetingSummary[] {
  const rows = meetingTimeline();
  for (let index = rows.length; index < 23; index += 1) {
    const start = Date.UTC(2026, 9, 23, 17) - (index - 8) * 60 * 60 * 1000;
    rows.push(
      meeting(index, {
        started_at: new Date(start).toISOString(),
        stopped_at: new Date(start + 1200 * 1000).toISOString(),
      })
    );
  }
  return rows;
}

export interface MeetingApiRequest {
  phase: 'request' | 'response';
  atMs: number;
  method: string;
  pathname: string;
  query: string;
  mainFrame: boolean;
  status?: number;
}

/** Every meetings request, plus auth/config ordering to identify a startup remount. */
export function observeMeetingRequests(page: Page): MeetingApiRequest[] {
  const requests: MeetingApiRequest[] = [];
  const started = performance.now();
  const record = (request: Request, phase: MeetingApiRequest['phase'], status?: number) => {
    const url = new URL(request.url());
    if (
      url.pathname === '/api/v1/meetings' ||
      url.pathname.startsWith('/api/v1/meetings/') ||
      url.pathname === '/api/v1/config' ||
      url.pathname === '/api/v1/auth/me'
    ) {
      requests.push({
        phase,
        atMs: Number((performance.now() - started).toFixed(2)),
        method: request.method(),
        pathname: url.pathname,
        query: url.search,
        mainFrame: request.frame() === page.mainFrame(),
        ...(status === undefined ? {} : { status }),
      });
    }
  };
  page.on('request', request => record(request, 'request'));
  page.on('response', response => record(response.request(), 'response', response.status()));
  return requests;
}

/** Actual device preference: a collapsed companion leaves its native restore control. */
export async function prepareMeetingReadingView(page: Page): Promise<void> {
  await minimizeCompanion(page);
}
export interface MeetingPageRead {
  limit: number;
  offset: number;
}

/**
 * Exact API paths from lib/meetings/api.ts. No per-id detail route is mocked:
 * a list doing N+1 reads hits the harness's 501 boundary and fails the spec.
 */
export function meetingTimelineRoutes(
  user: TestUser,
  rows: readonly MeetingSummary[] = meetingTimeline(),
  reads: MeetingPageRead[] = []
): MockRoute[] {
  return [
    {
      url: '**/api/v1/auth/me',
      method: 'GET',
      json: { ...user, onboarding_checklist: { dismissed_at: MEETING_TIMELINE_NOW } },
    },
    {
      url: '**/api/v1/config',
      method: 'GET',
      json: { ...appConfig, features: { ...appConfig.features, meetings_enabled: true } },
    },
    {
      url: /\/api\/v1\/meetings(?:\?.*)?$/,
      method: 'GET',
      handler: async route => {
        const query = new URL(route.request().url()).searchParams;
        const limit = Number(query.get('limit'));
        const offset = Number(query.get('offset'));
        if (
          limit !== 20 ||
          !query.has('offset') ||
          !Number.isInteger(offset) ||
          offset < 0 ||
          [...query.keys()].some(key => key !== 'limit' && key !== 'offset')
        ) {
          throw new Error(`Unexpected meeting page query: ${query.toString()}`);
        }
        reads.push({ limit, offset });
        const page: MeetingListResponse = {
          items: rows.slice(offset, offset + limit),
          total: rows.length,
          limit,
          offset,
        };
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(page),
        });
      },
    },
    {
      url: /\/api\/v1\/meetings\/[0-9a-f-]{36}(?:\?.*)?$/,
      handler: async route => {
        await route.fulfill({
          status: 501,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'unexpected_meeting_detail_read',
            method: route.request().method(),
            url: route.request().url(),
          }),
        });
      },
    },
    {
      url: '**/api/v1/meetings/active',
      method: 'GET',
      handler: async route => {
        await route.fulfill({ status: 204, body: '' });
      },
    },
    {
      url: '**/api/v1/meetings/preferences',
      method: 'GET',
      json: {
        stt_engine: 'auto',
        language: 'auto',
        auto_email: false,
        keep_audio_hours: 0,
        default_template_ref: null,
        keep_audio_hours_max: 72,
      } satisfies MeetingPreferences,
    },
    {
      url: '**/api/v1/meetings/templates',
      method: 'GET',
      json: { items: [], max_user_templates: 50 } satisfies MeetingTemplateListResponse,
    },
    { url: '**/api/v1/notifications/broadcasts/unread', method: 'GET', json: { broadcasts: [] } },
    { url: '**/api/v1/agents/runs/active', method: 'GET', json: { active: false } },
    {
      url: '**/api/v1/product/me/results',
      method: 'GET',
      json: {
        cycle_start: '2026-10-01',
        useful_results: 0,
        actions: 0,
        automations: 0,
        commitments_closed: 0,
        measured: true,
      },
    },
    {
      url: '**/api/v1/habits/presence',
      method: 'POST',
      handler: async route => {
        await route.fulfill({ status: 204, body: '' });
      },
    },
    idleNotificationStream,
  ];
}
