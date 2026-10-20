/** Real Relations UI with an arbitrary SMS-only sender and no external model call. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, idleNotificationStream } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { relationsData } from '../fixtures/relations';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
interface Reference {
  data: {
    id: string;
    sender: string;
    display_name: string;
    body: string;
    received_at: string;
    date_kind: string;
    origin: string;
    identity_source: string;
    identity_state: string;
    relation_key: null;
  };
  html: string;
}
const references: Reference[] = JSON.parse(
  readFileSync(
    path.join(__dirname, '../../../api/tests/unit/domains/agents/sms/card_reference_corpus.json'),
    'utf8'
  )
);
const locale: { relations: { scope_title: string; sms_title: string } } = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
for (const reference of references.slice(1)) {
  test(`SMS-only relation ${reference.data.sender} at 390px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const name = reference.data.display_name;
    const builds: string[] = [];
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes('/debrief'))
        builds.push(request.url());
    });
    await page.setViewportSize({ width: 390, height: 900 });
    await authenticate({ language: 'fr', timezone: 'Europe/Paris' });
    const empty = {
      status: 'not_configured',
      from_cache: false,
      generated_at: '2026-10-19T13:00:00Z',
      contact: null,
      emails: [],
      events: [],
    };
    await mockApi([
      idleNotificationStream,
      ...relationsData,
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
      },
      {
        url: '**/api/v1/relations',
        json: {
          relations: [
            {
              display_name: name,
              identity_confidence: 'exact',
              open_loops_count: 0,
              calls_count: 0,
              peer_messages_count: 0,
              sms_count: 137,
              last_interaction_at: reference.data.received_at,
              is_favorite: false,
              is_peer: false,
            },
          ],
          relations_total: 1,
          debrief_enabled: true,
          sms_available: true,
        },
      },
      {
        url: '**/api/v1/relations/lookup/person?*',
        json: {
          display_name: name,
          identity_confidence: 'exact',
          open_loops: [],
          open_loops_total: 0,
          recent_calls: [],
          recent_calls_total: 0,
          memories: [],
          memories_total: 0,
          peer_messages: [],
          peer_messages_total: 0,
          peer_link: null,
          is_favorite: false,
          is_peer: false,
          sms: [reference.data],
          sms_total: 137,
          sms_available: true,
        },
      },
      {
        url: '**/api/v1/relations/lookup/person/context?*',
        json: {
          contact: empty,
          emails: empty,
          events: empty,
          addresses_used: 0,
          window_days: 90,
          email_window_days: 365,
        },
      },
      {
        url: '**/api/v1/relations/lookup/person/debrief?*',
        json: {
          status: 'stale',
          person: name,
          body: null,
          generated_at: '2026-10-19T12:00:00Z',
          generated_for: '2026-10-19',
          sections_used: ['sms'],
          unavailable: [],
          usage: null,
          can_rebuild: true,
        },
      },
      { url: '**/api/v1/sms/' + reference.data.id, json: reference.data },
    ]);
    await page.goto('/fr/dashboard/relations', { waitUntil: 'domcontentloaded' });
    await awaitStyledPage(page, 'SMS-only relations');
    const card = page.getByRole('main').getByRole('button').filter({ hasText: name }).first();
    await expect(card).toContainText('137');
    await card.click();
    await expect(page.getByRole('heading', { level: 2, name, exact: true })).toBeVisible();
    await page
      .getByRole('button', { name: locale.relations.sms_title, exact: false })
      .filter({ hasText: '137' })
      .click();
    await expect(page.getByText(reference.data.body, { exact: true })).toBeVisible();
    await expect(page.getByText(/Les SMS ont changé/)).toBeVisible();
    await page.getByRole('button', { name: locale.relations.scope_title }).click();
    await expect(page.getByRole('checkbox', { name: 'SMS', exact: true })).not.toBeChecked();
    expect(builds).toEqual([]);
    await expectNoOverflow(page, 'SMS-only relation');
    const audit = await new AxeBuilder({ page }).include('main').analyze();
    expect(
      audit.violations.filter(item => ['serious', 'critical'].includes(item.impact ?? ''))
    ).toEqual([]);
    const link = page.getByRole('link', { name: /Ouvrir ce SMS/ });
    await expect(link).toHaveAttribute('href', '/fr/dashboard/sms?message=' + reference.data.id);
  });
}
