/**
 * Peer connections — the « Connexions » settings section journey (Lot 2).
 *
 * Hermetic: every /peers endpoint is a stateful mock (mutable closures — the
 * accept step really moves the row from requests to connections). Covers the
 * deep link, the discovery toggle, exact-name search with the pinned email
 * hint (A6), request → accept, BOTH share directions on the connection card,
 * a share change, an axe scan of the expanded section, and a mobile-viewport
 * render with the no-horizontal-overflow guard.
 */
import { scanPage } from '../a11y/scan';
import { test, expect, type MockRoute } from '../fixtures';

interface ShareItem {
  domain: string;
  level: string;
}
interface ConnectionRow {
  id: string;
  peer_id: string;
  peer_display_name: string;
  peer_email_hint: string;
  status: string;
  direction: string | null;
  requested_at: string;
  responded_at: string | null;
  context_message: string | null;
  my_shares: ShareItem[];
  their_shares: ShareItem[];
}

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 30 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: false,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: 'test',
    journals_enabled: false,
    peers_enabled: true,
  },
  api_version: 'v1',
};

function buildState() {
  const discovery = { discovery_enabled: false };
  const requests: ConnectionRow[] = [
    {
      id: 'conn-incoming',
      peer_id: 'peer-beta',
      peer_display_name: 'Peer Beta',
      peer_email_hint: 'b…@t….local',
      status: 'pending',
      direction: 'incoming',
      requested_at: '2026-07-29T08:00:00Z',
      responded_at: null,
      context_message: 'On se connecte ?',
      my_shares: [],
      their_shares: [],
    },
  ];
  const connections: ConnectionRow[] = [];
  return { discovery, requests, connections };
}

function buildRoutes(state: ReturnType<typeof buildState>): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/connectors', json: { connectors: [] } },
    { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
    { url: '**/api/v1/peers/me', method: 'GET', handler: route =>
        route.fulfill({ json: state.discovery }) },
    { url: '**/api/v1/peers/me', method: 'PUT', handler: async route => {
        state.discovery.discovery_enabled =
          route.request().postDataJSON().discovery_enabled;
        await route.fulfill({ json: state.discovery });
      } },
    { url: '**/api/v1/peers/discovery/search', method: 'POST', json: [
        {
          peer_id: 'peer-marie',
          display_name: 'Marie Dupont',
          email_hint: 'm…@g….com',
          relationship: 'none',
        },
      ] },
    { url: '**/api/v1/peers/requests', method: 'GET', handler: route =>
        route.fulfill({ json: state.requests }) },
    { url: '**/api/v1/peers/requests', method: 'POST', handler: async route => {
        state.requests.push({
          id: 'conn-outgoing',
          peer_id: 'peer-matheo',
          peer_display_name: 'Marie Dupont',
          peer_email_hint: 'm…@g….com',
          status: 'pending',
          direction: 'outgoing',
          requested_at: '2026-07-29T09:00:00Z',
          responded_at: null,
          context_message: null,
          my_shares: [],
          their_shares: [],
        });
        await route.fulfill({ status: 201, json: { id: 'conn-outgoing', status: 'pending' } });
      } },
    { url: '**/api/v1/peers/requests/*/respond', method: 'POST', handler: async route => {
        const accepted = state.requests.shift();
        if (accepted) {
          state.connections.push({
            ...accepted,
            status: 'accepted',
            direction: null,
            responded_at: '2026-07-29T09:30:00Z',
            their_shares: [{ domain: 'task', level: 'titles' }],
          });
        }
        await route.fulfill({ json: { id: 'conn-incoming', status: 'accepted' } });
      } },
    { url: '**/api/v1/peers/connections', method: 'GET', handler: route =>
        route.fulfill({ json: state.connections }) },
    { url: '**/api/v1/peers/connections/*/shares', method: 'PUT', handler: async route => {
        const body = route.request().postDataJSON();
        state.connections[0].my_shares = body.level === null
          ? []
          : [{ domain: body.domain, level: body.level }];
        await route.fulfill({ status: 204, json: {} });
      } },
    { url: '**/api/v1/peers/blocks', method: 'GET', json: [] },
    { url: '**/api/v1/peers/access-log', json: [] },
  ];
}

test.describe('peer connections section', () => {
  test('full journey: deep link, toggle, search, request, accept, shares', async (
    { page, authenticate, mockApi },
    testInfo
  ) => {
    const state = buildState();
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes(state));
    await page.goto('/fr/dashboard/settings?section=peer-connections');

    // Deep link resolves and expands the section (settings-deep-links pattern).
    const section = page.locator('#settings-section-peer-connections');
    await expect(section).toBeAttached({ timeout: 20_000 });
    await expect(section).toHaveAttribute('data-state', 'open', { timeout: 10_000 });

    // Discovery toggle persists through the mocked PUT.
    const toggle = section.getByRole('switch').first();
    await toggle.click();
    await expect
      .poll(() => state.discovery.discovery_enabled, { timeout: 5_000 })
      .toBe(true);

    // Exact-name search surfaces the match with the pinned email hint (A6).
    await section.getByLabel(/nom complet/i).fill('Marie Dupont');
    await section.getByRole('button', { name: /rechercher/i }).click();
    await expect(section.getByText('m…@g….com')).toBeVisible();

    // Request the connection → it lands in the outgoing pending list.
    await section.getByRole('button', { name: /demander la connexion/i }).click();
    await expect(section.getByText(/en attente de réponse/i)).toBeVisible();

    // Accept the seeded incoming request → connection card appears with BOTH
    // share directions (their task share is a read-only badge).
    await section.getByRole('button', { name: /^accepter$/i }).click();
    await expect(section.getByText(/tâches — titres/i)).toBeVisible({ timeout: 10_000 });

    // Change my calendar share level through the native select.
    await section.getByLabel(/calendrier/i).first().selectOption('availability');
    await expect
      .poll(() => state.connections[0]?.my_shares[0]?.level, { timeout: 5_000 })
      .toBe('availability');

    // Axe scan with the expanded section on screen (the shared helper —
    // styled-window guard + severity policy live there).
    await scanPage(page, testInfo, 'settings-peer-connections');
  });

  test('mobile viewport renders without horizontal overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const state = buildState();
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes(state));
    await page.goto('/fr/dashboard/settings?section=peer-connections');

    const section = page.locator('#settings-section-peer-connections');
    await expect(section).toBeAttached({ timeout: 20_000 });
    await expect(section).toHaveAttribute('data-state', 'open', { timeout: 10_000 });

    // The overflow guard (landing-responsive precedent): the page body must
    // never scroll horizontally at mobile width.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
