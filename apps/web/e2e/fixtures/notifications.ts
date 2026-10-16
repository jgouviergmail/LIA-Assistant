/** Typed notification sources: strict API mocks, no real data or paid provider. */
import type { Page } from '@playwright/test';
import type { HeartbeatNotification } from '../../src/hooks/useHeartbeatHistory';
import type { HubCounts } from '../../src/hooks/useHubCounts';
import type { TicketRow } from '../../src/types/workboard';
import { idleNotificationStream, waitForMockGate, type MockRoute } from './api-mock';
import { appConfig } from './dashboard-shell';
import type { TestUser } from './test-user';

/**
 * These read models currently live beside TSX or account-bound hooks. Keep the
 * isolated E2E package free of React app compilation; mirrors contain only the
 * exact wire fields read by their named components/hooks (no guessed values).
 */
interface PendingReminder {
  id: string;
  content: string;
  trigger_at: string;
}
interface RelayedMessage {
  id: string;
  peer_display_name: string;
  direction: string;
  content: string | null;
  occurred_at: string;
}
interface ScheduledActionRow {
  id: string;
  title: string;
  is_enabled: boolean;
  trigger_kind: 'time' | 'condition';
  next_trigger_at: string | null;
  schedule_display: string;
}
interface InterestNotification {
  id: string;
  created_at: string;
  content: string | null;
  source: string;
  topic: string | null;
  user_feedback: string | null;
}

export const NOTIFICATIONS_NOW = '2026-10-15T12:00:00Z';
export const NOTIFICATION_LONG_MESSAGE =
  'La préparation détaillée de notre prochaine rencontre à Saint-Rémy-en-Bouzemont-Saint-Genest-et-Isson comprend les disponibilités de chaque équipe, les décisions encore attendues et les responsabilités à confirmer. Informations importantes conservées jusqu’au bout du message.';
export const NOTIFICATION_REMINDER =
  'Préparer les documents et confirmer les disponibilités pour la rencontre internationale avec toutes les équipes de Saint-Rémy-en-Bouzemont-Saint-Genest-et-Isson';
export const NOTIFICATION_LITERAL_MARKUP =
  '<img src=x onerror="alert(1)"> contenu reçu comme texte';
export const NOTIFICATION_UNKNOWN_SOURCE = 'UNKNOWN_CONTEXT_SOURCE_'.repeat(10);

function id(index: number): string {
  return `00000000-0000-4000-8000-${String(index + 100).padStart(12, '0')}`;
}

export function notificationRoutineName(index: number): string {
  return `Routine ${String(index + 1).padStart(2, '0')} — suivi des responsabilités et décisions de l’équipe internationale`;
}

export function notificationPeerName(index: number): string {
  return index === 0
    ? NOTIFICATION_LONG_MESSAGE
    : `Message relayé ${String(index + 1).padStart(2, '0')}`;
}

export const notificationPeers: RelayedMessage[] = Array.from({ length: 12 }, (_, index) => ({
  id: id(index),
  peer_display_name: 'Camille · équipe internationale et partenariats',
  direction: index % 2 === 0 ? 'received' : 'sent',
  content:
    index === 1 ? null : index === 2 ? NOTIFICATION_LITERAL_MARKUP : notificationPeerName(index),
  occurred_at: new Date(Date.UTC(2026, 9, 15, 10) - index * 3_600_000).toISOString(),
}));

export const notificationProactive: HeartbeatNotification[] = [
  {
    id: id(30),
    created_at: '2026-10-15T09:00:00Z',
    content: 'Ton prochain rendez-vous approche : les documents utiles sont prêts à consulter.',
    sources_used: ['ANTICIPATED_MOMENT'],
    priority: 'high',
    user_feedback: 'thumbs_up',
    trigger: 'moment',
  },
  {
    id: id(31),
    created_at: '2026-10-15T08:00:00Z',
    content: 'Le suivi de tes habitudes apporte un nouveau point de repère pour la semaine.',
    sources_used: ['HABITS'],
    priority: 'medium',
    user_feedback: 'thumbs_down',
    trigger: 'tick',
  },
  {
    id: id(32),
    created_at: '2026-10-14T09:00:00Z',
    content: 'Une décision du Workboard attend ta réponse pour poursuivre le travail.',
    sources_used: ['WORKBOARD'],
    priority: 'low',
    user_feedback: null,
    trigger: 'tick',
  },
  {
    id: id(33),
    created_at: '2026-10-14T08:00:00Z',
    content:
      'Un contexte encore inconnu de cette version reste visible sans inventer sa traduction.',
    sources_used: [NOTIFICATION_UNKNOWN_SOURCE],
    priority: 'low',
    user_feedback: null,
    trigger: 'tick',
  },
];

export const notificationInterests: InterestNotification[] = [
  {
    id: id(40),
    created_at: '2026-10-15T08:00:00Z',
    content:
      'Les recherches récentes sur la conception inclusive apportent de nouvelles pistes à explorer avec ton équipe.',
    topic: 'Conception inclusive et accessibilité numérique',
    source: 'perplexity',
    user_feedback: null,
  },
  {
    id: id(41),
    created_at: '2026-10-14T08:00:00Z',
    content: null,
    topic: null,
    source: 'wikipedia',
    user_feedback: 'thumbs_down',
  },
];

const reminders: PendingReminder[] = Array.from({ length: 12 }, (_, index) => ({
  id: id(index + 50),
  content:
    index === 0 ? NOTIFICATION_REMINDER : `Rappel à venir ${String(index + 1).padStart(2, '0')}`,
  trigger_at: new Date(Date.UTC(2026, 9, 16 + index, 9)).toISOString(),
}));

/** The real endpoint is unpaged and capped at 20 creations, not an invented third page. */
const scheduled: ScheduledActionRow[] = Array.from({ length: 12 }, (_, index) => ({
  id: id(index + 70),
  title: notificationRoutineName(index),
  is_enabled: index !== 1,
  trigger_kind: index === 2 ? 'condition' : 'time',
  next_trigger_at:
    index === 1
      ? '2028-01-01T10:00:00Z'
      : index === 2
        ? '2027-01-01T10:00:00Z'
        : '2026-10-16T10:00:00Z',
  schedule_display:
    index === 2
      ? 'Quand un nouvel événement satisfait la condition définie'
      : 'Chaque jour à midi · Europe/Paris',
}));

const ticket: TicketRow = {
  id: id(90),
  owner_user_id: id(91),
  parent_id: null,
  title: 'Confirmer la proposition et les responsabilités avec les partenaires internationaux',
  description: null,
  status: 'waiting',
  priority: 'high',
  start_at: null,
  due_at: null,
  assignee_kind: 'human',
  assignee_user_id: null,
  effective_assignee_id: id(91),
  position: 0,
  follow_owner: true,
  follow_assignee: false,
  created_by: 'user',
  execution_mode: 'react',
  status_changed_at: NOTIFICATIONS_NOW,
  run_count: 1,
  run_claimed_at: null,
  last_run_at: NOTIFICATIONS_NOW,
  last_run_outcome: 'waiting',
  last_run_error: null,
  last_run_tokens_in: 10,
  last_run_tokens_out: 5,
  last_run_cost_eur: 0.001,
  total_tokens_in: 10,
  total_tokens_out: 5,
  total_tokens_cache: 0,
  total_google_requests: 0,
  total_cost_eur: 0.001,
  created_at: NOTIFICATIONS_NOW,
  updated_at: NOTIFICATIONS_NOW,
};

export const NOTIFICATION_COUNTS: HubCounts = {
  peer_messages: notificationPeers.length,
  proactive: notificationProactive.length,
  interests: notificationInterests.length,
  reminders: reminders.length,
  scheduled: scheduled.length,
  offers: 0,
  workboard: 1,
};

export interface NotificationRead {
  path: string;
  query: string;
  status: number;
}

interface NotificationRouteOptions {
  failInterestsOnce?: boolean;
  disableOptionalFeatures?: boolean;
  includeOffer?: boolean;
  offerDecisionGate?: Promise<void>;
  offerDecisions?: string[];
}

/** Every data read has a bounded and exact query; wrong methods fall through to 501. */
function paged<T>(
  path: string,
  key: string,
  rows: readonly T[],
  reads: NotificationRead[],
  failOnce = false
): MockRoute {
  let pendingFailure = failOnce;
  return {
    url: new RegExp(`/api/v1${path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\?.*)?$`),
    method: 'GET',
    handler: async route => {
      const query = new URL(route.request().url()).searchParams;
      const limit = Number(query.get('limit'));
      const offset = Number(query.get('offset'));
      if (
        limit !== 10 ||
        !query.has('offset') ||
        !Number.isInteger(offset) ||
        offset < 0 ||
        [...query.keys()].some(name => name !== 'limit' && name !== 'offset')
      ) {
        throw new Error(`Unexpected notification query for ${path}: ${query.toString()}`);
      }
      const status = pendingFailure ? 503 : 200;
      pendingFailure = false;
      reads.push({ path, query: query.toString(), status });
      await route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(
          status === 503
            ? { detail: 'Temporary notification source failure' }
            : { [key]: rows.slice(offset, offset + limit), total: rows.length }
        ),
      });
    },
  };
}

export function notificationsRoutes(
  user: TestUser,
  reads: NotificationRead[] = [],
  options: NotificationRouteOptions = {}
): MockRoute[] {
  const enabled = !options.disableOptionalFeatures;
  const offerRows: HeartbeatNotification[] = options.includeOffer
    ? [
        {
          id: id(95),
          created_at: '2026-10-15T10:00:00Z',
          content:
            'Souhaites-tu préparer le prochain rendez-vous avec les équipes internationales ? Rien ne sera envoyé sans ta validation.',
          sources_used: ['MISSED_ROUTINE'],
          priority: 'medium',
          user_feedback: null,
          trigger: 'tick',
        },
      ]
    : [];
  return [
    {
      url: '**/api/v1/auth/me',
      method: 'GET',
      json: { ...user, onboarding_checklist: { dismissed_at: NOTIFICATIONS_NOW } },
    },
    {
      url: '**/api/v1/config',
      method: 'GET',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          peers_enabled: enabled,
          heartbeat_enabled: enabled,
          workboard_enabled: enabled,
          activity_timeline_enabled: enabled,
        },
      },
    },
    {
      url: '**/api/v1/notifications/hub-counts',
      method: 'GET',
      handler: async route => {
        reads.push({ path: '/notifications/hub-counts', query: '', status: 200 });
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...NOTIFICATION_COUNTS, offers: offerRows.length }),
        });
      },
    },
    paged('/heartbeat/offers', 'notifications', offerRows, reads),
    {
      url: new RegExp('/api/v1/heartbeat/notifications/' + id(95) + '/feedback' + '$'),
      method: 'PATCH',
      handler: async (route, signal) => {
        const payload: unknown = route.request().postDataJSON();
        if (
          !payload ||
          typeof payload !== 'object' ||
          !('feedback' in payload) ||
          (payload.feedback !== 'thumbs_up' && payload.feedback !== 'thumbs_down')
        )
          throw new Error('Invalid offer feedback payload');
        options.offerDecisions?.push(payload.feedback);
        if (
          options.offerDecisionGate &&
          !(await waitForMockGate(options.offerDecisionGate, signal))
        )
          return;
        offerRows.splice(0);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true }),
        });
      },
    },
    paged('/peers/messages', 'messages', notificationPeers, reads),
    paged('/heartbeat/history', 'notifications', notificationProactive, reads),
    paged(
      '/interests/notifications/history',
      'notifications',
      notificationInterests,
      reads,
      options.failInterestsOnce
    ),
    paged('/reminders', 'reminders', reminders, reads),
    paged(
      '/workboard/needs-me',
      'tickets',
      [{ ...ticket, owner_user_id: user.id, effective_assignee_id: user.id }],
      reads
    ),
    {
      url: /\/api\/v1\/scheduled-actions(?:\?.*)?$/,
      method: 'GET',
      handler: async route => {
        const query = new URL(route.request().url()).search;
        if (query) throw new Error(`The routine endpoint does not support pagination: ${query}`);
        reads.push({ path: '/scheduled-actions', query: '', status: 200 });
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ scheduled_actions: scheduled, total: scheduled.length }),
        });
      },
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

export async function prepareNotificationReadingView(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: false }, version: 0 })
    );
  });
}
