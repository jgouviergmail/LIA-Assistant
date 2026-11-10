/** A card opens its exact native item; both click and provider-read refusals stay explicit. */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type {
  WorkbenchAvailability,
  WorkbenchContact,
  WorkbenchToolAvailability,
  WorkbenchToolId,
} from '../../src/lib/workbench/types';
import { test, expect, waitForHydration, loadedChatRoutes, type MockRoute } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow } from './overflow-report';

const CONTACT: WorkbenchContact = {
  id: 'people/card & scoped',
  name: 'Ana Lima',
  given_name: 'Ana',
  family_name: 'Lima',
  email: null,
  phone: null,
  organization: 'Verified source',
  name_key: 'ana lima',
  emails: [],
  phones: [],
  addresses: [],
  notes: 'Only the verified record is open.',
  job_title: null,
  website: null,
  birthday: null,
};
const TOOLS: WorkbenchToolId[] = ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'];
const AVAILABILITY: WorkbenchAvailability = {
  tools: TOOLS.map<WorkbenchToolAvailability>(tool => ({
    tool,
    state: tool === 'contacts' ? 'ready' : 'not_connected',
    provider: tool === 'contacts' ? 'google_contacts' : null,
    features: [],
    bounds: { name_max_chars: 512, photo_max_bytes: 10485760 },
  })),
  limits: {
    page_size: 25,
    bulk_max_items: 50,
    download_max_bytes: 26214400,
    upload_max_bytes: 26214400,
    calendar_window_max_events: 500,
    send_undo_seconds: 0,
    draft_autosave_seconds: 0,
    search_max_chars: 500,
    assist_text_max_chars: 8000,
    assist_instruction_max_chars: 500,
  },
};
const TOKEN = 'opaque.signed-card-source';
const HTML = `<div class="lia-response-wrapper" data-card-version="2"><div class="lia-card-binding" data-card-kind="CONTACT" data-card-target="${TOKEN}"><div class="lia-card lia-contact"><div class="lia-card-top"><div class="lia-card-top__info"><a class="lia-card-top__title" title="Ana Lima" href="https://contacts.google.com/person/stale" target="_blank">Ana Lima</a></div></div><p>Contact in the assistant answer.</p></div></div></div>`;

for (const sample of [
  { lng: 'en', width: 1280 },
  { lng: 'fr', width: 390 },
] as const) {
  for (const result of ['available', 'source_changed', 'changed_at_read'] as const) {
    test(`card target ${result} ${sample.lng} ${sample.width}px`, async ({
      page,
      context,
      authenticate,
      mockApi,
    }) => {
      const words: {
        card_tools: { source_changed: string };
        workbench: { errors: { card_source_changed: string } };
      } = JSON.parse(
        readFileSync(join(__dirname, '../../locales', sample.lng, 'translation.json'), 'utf8')
      );
      const checked: unknown[] = [];
      const opened: { id: string | null; proof: string | undefined }[] = [];
      await page.setViewportSize({ width: sample.width, height: 900 });
      await authenticate({ language: sample.lng, response_display_mode: 'html_cards' });
      const routes: MockRoute[] = [
        ...loadedChatRoutes(),
        {
          url: '**/api/v1/config',
          json: {
            ...appConfig,
            features: { ...appConfig.features, workbench_enabled: true },
            capabilities: { workbench: { enabled: true, family: 'work' } },
          },
        },
        {
          url: '**/api/v1/conversations/me/messages*',
          json: {
            messages: [
              {
                id: '00000000-0000-4000-8000-000000000111',
                role: 'assistant',
                content: HTML,
                created_at: '2026-11-08T08:00:00Z',
                metadata: null,
              },
            ],
            conversation_id: '00000000-0000-4000-8000-000000000011',
            total_count: 1,
            has_more: false,
            next_cursor: null,
          },
        },
        {
          url: '**/api/v1/workbench/card-target',
          method: 'POST',
          handler: async route => {
            checked.push(route.request().postDataJSON());
            await route.fulfill({
              json:
                result === 'source_changed'
                  ? { available: false, target: null, reason: 'source_changed' }
                  : {
                      available: true,
                      target: {
                        kind: 'contact',
                        item_id: CONTACT.id,
                        container_id: null,
                        day: null,
                        is_folder: false,
                      },
                      reason: null,
                    },
            });
          },
        },
        { url: '**/api/v1/workbench', json: AVAILABILITY },
        { url: '**/api/v1/relations', json: { relations: [], relations_total: 0 } },
        {
          url: '**/api/v1/workbench/contacts**',
          handler: async route => {
            const url = new URL(route.request().url());
            if (url.pathname.endsWith('/contact')) {
              opened.push({
                id: url.searchParams.get('id'),
                proof: route.request().headers()['x-lia-card-source'],
              });
              await route.fulfill(
                result === 'changed_at_read'
                  ? { status: 409, json: { detail: { code: 'card_source_changed' } } }
                  : { json: CONTACT }
              );
            } else if (url.pathname.endsWith('/photo')) {
              await route.fulfill({ status: 404, json: { detail: { code: 'item_gone' } } });
            } else {
              await route.fulfill({ json: { items: [], next_page_token: null, truncated: false } });
            }
          },
        },
      ];
      await mockApi(routes);
      await page.goto(`/${sample.lng}/dashboard/chat`);
      await waitForHydration(page);
      const title = page.getByRole('button', { name: CONTACT.name, exact: true });
      await expect(title).toBeVisible();
      await expect(page.getByRole('link', { name: CONTACT.name, exact: true })).toHaveCount(0);
      expect(checked).toHaveLength(0);
      expect(opened).toHaveLength(0);
      await title.click({ button: 'middle' });
      expect(checked).toHaveLength(0);
      await title.focus();
      await title.press('Enter');
      await expect.poll(() => checked).toEqual([{ token: TOKEN }]);
      if (result === 'source_changed') {
        await expect(
          page.getByRole('status').filter({ hasText: words.card_tools.source_changed })
        ).toBeVisible();
        expect(opened).toHaveLength(0);
        expect(new URL(page.url()).pathname).toMatch(/\/dashboard\/chat$/);
        await expect(title).toBeFocused();
      } else {
        await expect.poll(() => opened).toEqual([{ id: CONTACT.id, proof: TOKEN }]);
        expect(new URL(page.url()).searchParams.get('card_source')).toBe(TOKEN);
        if (result === 'available') {
          await expect(page.getByRole('article', { name: CONTACT.name })).toBeVisible();
          await expect(page.getByText(CONTACT.notes!, { exact: true })).toBeVisible();
        } else {
          await expect(
            page.getByText(words.workbench.errors.card_source_changed, { exact: true })
          ).toBeVisible();
          await expect(page.getByText(CONTACT.notes!, { exact: true })).toHaveCount(0);
        }
      }
      expect(context.pages()).toHaveLength(1);
      await expectNoOverflow(page, `card target ${result} ${sample.width}px`);
    });
  }
}
