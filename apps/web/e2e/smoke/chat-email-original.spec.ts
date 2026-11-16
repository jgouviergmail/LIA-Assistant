/**
 * A received message in the chat opens as the Tools show it (owner, 2026-11-14).
 *
 * Nothing is read while the card's details stay closed. Once the person opens them, the original
 * layout is read under the card's own signed source, its images too, and drawn in the Tools'
 * sandboxed frame, the text a click away. A layout that could not be read is said and the text
 * stays; with the Tools switched off nothing is asked at all.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type {
  MailHtml,
  MailInlineImages,
  WorkbenchAvailability,
  WorkbenchToolAvailability,
  WorkbenchToolId,
} from '../../src/lib/workbench/types';
import { test, expect, waitForHydration, loadedChatRoutes, type MockRoute } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow } from './overflow-report';

const TOKEN = 'opaque.signed-mail-source';
const MESSAGE_ID = 'envelope-message-1';
const TEXT = 'The board meets on Thursday in the glass room.';
const CID = 'logo@board';
const PIXEL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
const CARD = `<div class="lia-response-wrapper" data-card-version="2"><div class="lia-card-binding" data-card-kind="EMAIL" data-card-target="${TOKEN}"><div class="lia-card lia-email"><div class="lia-card-top"><div class="lia-card-top__info"><a class="lia-email__subject" href="https://mail.google.com/mail/u/0/#all/${MESSAGE_ID}" target="_blank">Board meeting</a></div></div><details class="lia-collapsible"><summary class="lia-collapsible__trigger"><span>More</span></summary><div class="lia-email-original" data-message-id="${MESSAGE_ID}"><div class="lia-desc-block lia-desc-block--no-border">${TEXT}</div></div></details></div></div></div>`;
const ORIGINAL: MailHtml = {
  html: `<table style="width:100%"><tr><td><img src="cid:${CID}" alt="Board logo"><h1>Board meeting</h1><p>${TEXT}</p></td></tr></table>`,
  truncated: false,
};
const IMAGES: MailInlineImages = { images: [{ cid: CID, data_url: PIXEL }], skipped: 0 };
const TOOLS: WorkbenchToolId[] = ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'];
const AVAILABILITY: WorkbenchAvailability = {
  tools: TOOLS.map<WorkbenchToolAvailability>(tool => ({
    tool,
    state: tool === 'mail' ? 'ready' : 'not_connected',
    provider: tool === 'mail' ? 'gmail' : null,
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

interface MailWords {
  workbench: {
    mail: {
      html_frame_title: string;
      show_text: string;
      show_original: string;
      html_failed: string;
    };
  };
}

function words(lng: string): MailWords['workbench']['mail'] {
  const locale: MailWords = JSON.parse(
    readFileSync(join(__dirname, '../../locales', lng, 'translation.json'), 'utf8')
  );
  return locale.workbench.mail;
}

/** Every read of the card's message, with the proof it carried and whether the card was open. */
interface Read {
  path: string;
  id: string | null;
  proof: string | undefined;
  opened: boolean;
}

/** Set by the journey the moment the person opens the card's details. */
interface Journey {
  opened: boolean;
}

function routes(
  reads: Read[],
  journey: Journey,
  answer: 'layout' | 'failure',
  offered = true
): MockRoute[] {
  return [
    ...loadedChatRoutes(),
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, workbench_enabled: offered },
        capabilities: { workbench: { enabled: offered, family: 'work' } },
      },
    },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [
          {
            id: '00000000-0000-4000-8000-000000000211',
            role: 'assistant',
            content: CARD,
            created_at: '2026-11-14T08:00:00Z',
            metadata: null,
          },
        ],
        conversation_id: '00000000-0000-4000-8000-000000000021',
        total_count: 1,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/workbench', json: AVAILABILITY },
    {
      url: '**/api/v1/workbench/mail/message/**',
      handler: async route => {
        const url = new URL(route.request().url());
        reads.push({
          path: url.pathname.replace(/^.*\/workbench\/mail\/message/, ''),
          id: url.searchParams.get('id') ?? url.searchParams.get('message_id'),
          proof: route.request().headers()['x-lia-card-source'],
          opened: journey.opened,
        });
        if (url.pathname.endsWith('/html')) {
          await route.fulfill(
            answer === 'layout'
              ? { json: ORIGINAL }
              : { status: 500, json: { detail: { code: 'provider_unavailable' } } }
          );
        } else {
          await route.fulfill({ json: IMAGES });
        }
      },
    },
  ];
}

for (const sample of [
  { lng: 'en', width: 1280 },
  { lng: 'fr', width: 390 },
] as const) {
  test(`the mail opens in its original layout, its text a click away — ${sample.lng} ${sample.width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const said = words(sample.lng);
    const reads: Read[] = [];
    const journey: Journey = { opened: false };
    await page.setViewportSize({ width: sample.width, height: 900 });
    await authenticate({ language: sample.lng, response_display_mode: 'html_cards' });
    await mockApi(routes(reads, journey, 'layout'));
    await page.goto(`/${sample.lng}/dashboard/chat`);
    await waitForHydration(page);

    const more = page.locator('summary', { hasText: 'More' });
    await expect(more).toBeVisible();
    await expect(page.getByTitle(said.html_frame_title)).toHaveCount(0);

    // Opened by the keyboard: every read comes after, under the card's own proof.
    journey.opened = true;
    await more.focus();
    await page.keyboard.press('Enter');
    const frame = page.getByTitle(said.html_frame_title);
    await expect(frame).toBeVisible();
    await expect(frame).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox');
    await expect
      .poll(() => reads)
      .toEqual(
        expect.arrayContaining([
          { path: '/html', id: MESSAGE_ID, proof: TOKEN, opened: true },
          { path: '/images', id: MESSAGE_ID, proof: TOKEN, opened: true },
        ])
      );
    expect(reads.every(read => read.proof === TOKEN && read.opened)).toBe(true);

    await page.getByRole('button', { name: said.show_text }).click();
    await expect(page.getByText(TEXT, { exact: true })).toBeVisible();
    await expect(frame).toHaveCount(0);
    const back = page.getByRole('button', { name: said.show_original });
    await back.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTitle(said.html_frame_title)).toBeVisible();
    await expectNoOverflow(page, `mail original ${sample.lng} ${sample.width}px`);
  });
}

test('a layout that could not be read is said, and the text stays', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const said = words('en');
  const reads: Read[] = [];
  const journey: Journey = { opened: true };
  await authenticate({ language: 'en', response_display_mode: 'html_cards' });
  await mockApi(routes(reads, journey, 'failure'));
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);

  await page.locator('summary', { hasText: 'More' }).click();
  await expect(page.getByText(said.html_failed, { exact: true })).toBeVisible();
  await expect(page.getByText(TEXT, { exact: true })).toBeVisible();
  await expect(page.getByTitle(said.html_frame_title)).toHaveCount(0);
  expect(reads).toEqual(
    expect.arrayContaining([{ path: '/html', id: MESSAGE_ID, proof: TOKEN, opened: true }])
  );
  expect(reads.every(read => read.proof === TOKEN)).toBe(true);
});

test('with the Tools switched off, the card asks nothing', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const reads: Read[] = [];
  const journey: Journey = { opened: true };
  await authenticate({ language: 'en', response_display_mode: 'html_cards' });
  await mockApi(routes(reads, journey, 'layout', false));
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);

  await page.locator('summary', { hasText: 'More' }).click();
  await expect(page.getByText(TEXT, { exact: true })).toBeVisible();
  await expect(page.getByTitle(words('en').html_frame_title)).toHaveCount(0);
  expect(reads).toHaveLength(0);
});
