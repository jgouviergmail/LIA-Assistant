/**
 * Chat — rich-HTML display mode rendering (ADR-177).
 *
 * Hermetic: empty mocked history + mocked SSE streaming a full `lia-response`
 * document in small chunks (several land mid-tag on purpose). Guards, in a
 * real engine (jsdom performs no layout):
 * - the components render as DOM, never as raw tag text;
 * - the collapsible toggles from the keyboard (native <summary> semantics);
 * - nothing overflows the viewport horizontally, desktop and 390px mobile;
 * - a wide table keeps readable columns on desktop and becomes stacked cards,
 *   each value under its column's name, in a phone bubble (B2).
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const NL = String.fromCharCode(10);

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c177',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E html mode',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-07-29T09:00:00Z',
  updated_at: '2026-07-29T09:00:00Z',
};

const APP_CONFIG = {
  sse: { heartbeat_interval_seconds: 15 },
  rate_limits: { enabled: false, per_minute: 60, burst: 10 },
  i18n: { supported_languages: ['fr', 'en'], default_language: 'fr' },
  features: {
    tool_approval_enabled: true,
    attachments_enabled: true,
    rag_spaces_enabled: false,
    rag_spaces_embedding_model: '',
  },
  api_version: 'v1',
};

const EMPTY_HISTORY = {
  messages: [],
  conversation_id: CONVERSATION.id,
  total_count: 0,
  has_more: false,
  next_cursor: null,
};

const HTML_ANSWER = [
  '<div class="lia-response">',
  '<h2>Synthèse de la journée</h2>',
  '<div class="lia-callout lia-callout-success"><p class="lia-callout__title">Tout est prêt</p>' +
    '<p>Trois créneaux confirmés.</p></div>',
  '<dl class="lia-kv"><dt>Date</dt><dd><strong>12 août</strong></dd>' +
    '<dt>Lieu</dt><dd>Paris</dd></dl>',
  '<div class="lia-stats"><div class="lia-stat"><span class="lia-stat__value">12</span>' +
    '<span class="lia-stat__label">rendez-vous</span></div>' +
    '<div class="lia-stat"><span class="lia-stat__value">3</span>' +
    '<span class="lia-stat__label">urgents</span></div></div>',
  '<table><caption>Comparatif</caption><thead><tr><th>Option</th><th>Durée</th></tr></thead>' +
    '<tbody><tr><td>A</td><td>1 h</td></tr><tr><td>B</td><td>2 h</td></tr></tbody></table>',
  '<details class="lia-collapsible"><summary>Voir le détail</summary>' +
    '<p>Contenu replié.</p></details>',
  '</div>',
].join('');

/**
 * A five-column comparison, the shape that broke (B2): measured before the
 * fix, 908 px wide in a 341 px phone bubble, two columns squeezed to 40 px.
 */
const WIDE_TABLE_ANSWER = [
  '<div class="lia-response">',
  '<h2>Restaurants du quartier</h2>',
  '<table><thead><tr><th>Restaurant</th><th>Adresse</th><th>Spécialité et ambiance</th>' +
    '<th>Prix</th><th>Avis</th></tr></thead><tbody>',
  '<tr><td>Le Petit Bistrot de la Gare</td><td>12 avenue du Général de Gaulle, 69003 Lyon</td>' +
    '<td>Cuisine lyonnaise traditionnelle, ambiance chaleureuse et familiale</td>' +
    '<td>25–35 €</td><td>Très bon rapport qualité-prix, service rapide, réservation conseillée</td></tr>',
  '<tr><td>Chez Marcel</td><td>4 rue Mercière, 69002 Lyon</td>' +
    '<td>Bouchon, quenelles, tablier de sapeur</td><td>30 €</td><td>Authentique</td></tr>',
  '</tbody></table>',
  '</div>',
].join('');

/** Stream the document in 24-char chunks — several land mid-tag on purpose. */
function sseAnswer(answer: string = HTML_ANSWER): string {
  const chunks: string[] = [];
  for (let i = 0; i < answer.length; i += 24) {
    chunks.push(
      'data: ' + JSON.stringify({ type: 'token', content: answer.slice(i, i + 24) }) + NL + NL
    );
  }
  return chunks.join('') + 'data: {"type":"done","content":"","metadata":null}' + NL + NL;
}

function baseRoutes(answer: string = HTML_ANSWER): MockRoute[] {
  return [
    { url: '**/api/v1/config', json: APP_CONFIG },
    { url: '**/api/v1/conversations/me', json: CONVERSATION },
    { url: '**/api/v1/conversations/me/messages*', json: EMPTY_HISTORY },
    { url: '**/api/v1/conversations/me/totals', json: {} },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: sseAnswer(answer),
        });
      },
    },
  ];
}

for (const { width, lng, label } of [
  { width: 1280, lng: 'en', label: 'Rich HTML + cards' },
  { width: 390, lng: 'fr', label: 'HTML enrichi + cartes' },
]) {
  test(`combined display persists and renders rich content with cards at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const corpus = JSON.parse(
      readFileSync(
        path.join(
          __dirname,
          '../../../api/tests/unit/domains/agents/display/contact_card_corpus.json'
        ),
        'utf8'
      )
    ) as { id: string; html: string; data: { name: string } }[];
    const card = corpus.find(item => item.id === 'initials');
    if (!card) throw new Error('The API contact corpus must include an initials card');
    await page.setViewportSize({ width, height: 900 });
    const account = await authenticate({ language: lng, response_display_mode: 'cards' });
    let mode = 'cards';
    const updates: unknown[] = [];
    await mockApi([
      ...baseRoutes(HTML_ANSWER + '<div class="lia-response">' + card.html + '</div>'),
      {
        url: '**/api/v1/auth/me',
        handler: route => route.fulfill({ json: { ...account, response_display_mode: mode } }),
      },
      {
        url: '**/api/v1/auth/me/display-mode-preference',
        method: 'PATCH',
        handler: async route => {
          const body = route.request().postDataJSON();
          updates.push(body);
          mode = body.response_display_mode;
          await route.fulfill({ json: { response_display_mode: mode } });
        },
      },
    ]);
    await page.goto(`/${lng}/dashboard/settings?section=display-mode`);
    await waitForHydration(page, 'button[aria-pressed]');
    const option = page.getByRole('button', { name: label, exact: true });
    await option.focus();
    await page.keyboard.press('Enter');
    await expect(option).toHaveAttribute('aria-pressed', 'true');
    expect(updates).toEqual([{ response_display_mode: 'html_cards' }]);
    await expect(option).toBeFocused();
    await expectNoOverflow(page, `combined display settings ${width}`);
    await page.reload();
    await expect(option).toHaveAttribute('aria-pressed', 'true');

    await page.goto(`/${lng}/dashboard/chat`);
    await waitForHydration(page);
    await awaitStyledPage(page, 'combined display chat');
    await sendAndAwaitAnswer(page);
    await expect(page.locator('.lia-callout-success .lia-callout__title')).toHaveText(
      'Tout est prêt'
    );
    await expect(page.locator('.lia-card.lia-contact')).toHaveCount(1);
    await expect(page.locator('.lia-card.lia-contact')).toContainText(card.data.name);
    const details = page.locator('details.lia-collapsible');
    await details.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(details).toHaveAttribute('open', '');
    await expectNoOverflow(page, `combined answer ${width}`);
  });
}

// The same global styles also draw the avatar's weather accessories. Cards
// must retain normal flow and pointer input when those styles are loaded.
for (const width of [1280, 390]) {
  test(`weather cards keep their layout and interactions at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ response_display_mode: 'cards' });
    const cards = ['current', 'forecast', 'hourly'].map(
      kind =>
        `<div class="lia-card lia-weather lia-weather--${kind === 'current' ? 'fog' : kind}">` +
        `<div class="lia-weather__layout"><div class="lia-weather__left">` +
        '<span class="lia-weather__temp">12°C</span></div>' +
        '<div class="lia-weather__right"><div class="lia-weather__city">Paris</div></div></div>' +
        `<details><summary>Détails ${kind}</summary><p>Humidité : 80 %</p></details></div>`
    );
    await mockApi(
      baseRoutes('<h2>Météo</h2><div class="lia-response">' + cards.join('') + '</div>')
    );
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'weather cards');
    await sendAndAwaitAnswer(page, 'Météo');
    const rendered = page.locator('.lia-card.lia-weather');
    await expect(rendered).toHaveCount(3);
    for (const card of await rendered.all()) {
      await expect(card).toBeVisible();
      await expect(card).not.toHaveCSS('position', 'absolute');
      await expect(card).toHaveCSS('pointer-events', 'auto');
      await card.locator('summary').click();
      await expect(card.locator('details')).toHaveAttribute('open', '');
    }
    const boxes = await rendered.evaluateAll(nodes =>
      nodes.map(node => {
        const box = node.getBoundingClientRect();
        return { top: box.top, bottom: box.bottom, width: box.width };
      })
    );
    expect(boxes[0].width).toBeGreaterThan(200);
    expect(boxes[1].top).toBeGreaterThanOrEqual(boxes[0].bottom);
    expect(boxes[2].top).toBeGreaterThanOrEqual(boxes[1].bottom);
    await expectNoOverflow(page, `weather cards ${width}`);
  });
}

async function sendAndAwaitAnswer(
  page: import('@playwright/test').Page,
  heading = 'Synthèse de la journée'
): Promise<void> {
  await page.locator('textarea').fill('Synthèse de ma journée en HTML');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: heading, level: 2 })).toBeVisible({
    timeout: 15_000,
  });
}

/** What a wide table's frame says, and how wide its cells are drawn. */
async function measureWideTable(page: import('@playwright/test').Page) {
  const frame = page.locator('.table-frame').first();
  await expect(frame).toHaveAttribute('data-stacked', /true|false/);
  return frame.evaluate(node => {
    const box = node.querySelector('.table-wrapper') as HTMLElement;
    const cells = [...node.querySelectorAll('tbody tr:first-child td')] as HTMLElement[];
    return {
      stacked: node.getAttribute('data-stacked'),
      overflow: box.scrollWidth - box.clientWidth,
      cellWidths: cells.map(cell => cell.getBoundingClientRect().width),
      rowHeight: (node.querySelector('tbody tr') as HTMLElement).getBoundingClientRect().height,
      labels: cells.map(cell => cell.getAttribute('data-label')),
      firstLabelPrinted: getComputedStyle(cells[0], '::before').content,
    };
  });
}

test.describe('rich HTML display mode (ADR-177)', () => {
  test('components render as DOM, collapsible is keyboard-operable, no overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-html-mode desktop');

    await sendAndAwaitAnswer(page);

    // Raw tag source must never be readable anywhere in the thread — the
    // regression this whole mode guards against.
    expect(await page.locator('body').textContent()).not.toContain('<h2>');

    await expect(page.locator('.lia-callout-success .lia-callout__title')).toHaveText(
      'Tout est prêt'
    );
    const kv = page.locator('dl.lia-kv');
    await expect(kv.locator('dt')).toHaveCount(2);
    await expect(page.locator('.lia-stat__value').first()).toHaveText('12');
    await expect(page.locator('table caption')).toHaveText('Comparatif');

    // Keyboard: <summary> is natively focusable; Enter toggles the details.
    const details = page.locator('details.lia-collapsible');
    await expect(details).not.toHaveAttribute('open', '');
    await details.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(details).toHaveAttribute('open', '');
    await expect(page.getByText('Contenu replié.')).toBeVisible();

    await expectNoOverflow(page, 'html-answer desktop');
  });

  test('mobile 390px: rich components stack without horizontal overflow', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(baseRoutes());

    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-html-mode mobile');

    await sendAndAwaitAnswer(page);

    await expect(page.locator('.lia-stat__value').first()).toBeVisible();
    await expectNoOverflow(page, 'html-answer mobile');
  });

  test('desktop: a wide table keeps readable columns and stays a table', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(baseRoutes(WIDE_TABLE_ANSWER));
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-wide-table desktop');
    await sendAndAwaitAnswer(page, 'Restaurants du quartier');

    const table = await measureWideTable(page);
    expect(table.stacked).toBe('false');
    // Measured before the fix: 40-42 px for « Prix » and « Avis ».
    for (const width of table.cellWidths) expect(width).toBeGreaterThanOrEqual(80);
    expect(table.rowHeight).toBeLessThan(200);
    await expectNoOverflow(page, 'wide-table desktop');
  });

  test('mobile 390px: an overflowing table becomes cards, each value named', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate();
    await mockApi(baseRoutes(WIDE_TABLE_ANSWER));
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'chat-wide-table mobile');
    await sendAndAwaitAnswer(page, 'Restaurants du quartier');

    const table = await measureWideTable(page);
    expect(table.stacked).toBe('true');
    expect(table.overflow).toBeLessThanOrEqual(1);
    expect(table.labels).toEqual([
      'Restaurant',
      'Adresse',
      'Spécialité et ambiance',
      'Prix',
      'Avis',
    ]);
    expect(table.firstLabelPrinted).toBe('"Restaurant"');
    await expectNoOverflow(page, 'wide-table mobile');

    // Turned to a wide screen, the cards become a table again. The bubble
    // used to follow its content, so a stacked (narrow) table kept its own
    // bubble narrow and stayed stacked at any width.
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.locator('.table-frame').first()).toHaveAttribute('data-stacked', 'false');
  });
});
