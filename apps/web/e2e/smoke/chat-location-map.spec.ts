/** Archived address projection, actual sanitizer/SDK seam and hermetic Google traffic. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow, prepareTheme } from './overflow-report';

const sdk = readFileSync(path.join(__dirname, '../fixtures/maps/position-sdk.js'), 'utf8');
interface Reference {
  id: string;
  language: string;
  html: string;
}
const references: Reference[] = JSON.parse(
  readFileSync(
    path.join(
      __dirname,
      '../../../api/tests/unit/domains/agents/display/card_reference_corpus.json'
    ),
    'utf8'
  )
);

for (const sample of [
  { width: 1280, theme: 'light', retry: false },
  { width: 1280, theme: 'dark', retry: false },
  { width: 390, theme: 'light', retry: false },
  { width: 390, theme: 'dark', retry: false },
  { width: 320, theme: 'oled', retry: true },
] as const) {
  test(`address map ${sample.width}px ${sample.theme}: explicit admission and no route`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const reference = references.find(item => item.id === 'locations' && item.language === 'fr');
    if (!reference) throw new Error('Missing backend location reference');
    const auditedViewport = { width: sample.width, height: 1000 };
    await page.setViewportSize(auditedViewport);
    await prepareTheme(page, sample.theme);
    await authenticate({ language: 'fr', theme: sample.theme, response_display_mode: 'cards' });
    let scripts = 0,
      admissions = 0,
      reports = 0,
      routes = 0;
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/config',
        json: {
          sse: { heartbeat_interval_seconds: 30 },
          rate_limits: { enabled: false, per_minute: 60, burst: 10 },
          i18n: { supported_languages: ['fr'], default_language: 'fr' },
          features: {},
          place_maps: { enabled: true, estimated_cost_eur: '0.006' },
          api_version: '1',
        },
      },
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c799',
              role: 'assistant',
              content: reference.html,
              created_at: '2026-11-07T12:00:00Z',
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000c099',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
      {
        url: '**/api/v1/connectors/google-location/static-map*',
        handler: route =>
          route.fulfill({
            path: path.join(__dirname, '../fixtures/maps/lyon-location.png'),
            contentType: 'image/png',
          }),
      },
      {
        url: '**/api/v1/connectors/street-view*',
        handler: route =>
          route.fulfill({
            path: path.join(__dirname, '../fixtures/maps/lyon-location.png'),
            contentType: 'image/png',
          }),
      },
      {
        url: '**/api/v1/connectors/google-maps/load-admissions*',
        handler: async route => {
          admissions++;
          expect(new URL(route.request().url()).searchParams.get('purpose')).toBe('places');
          await route.fulfill({
            json: {
              api_key: 'hermetic-public-key',
              map_id: 'configured-map-id',
              load_token: 'address-grant',
            },
          });
        },
      },
      {
        url: '**/api/v1/connectors/google-maps/load-reports',
        handler: async route => {
          reports++;
          expect(route.request().postDataJSON()).toEqual({ load_token: 'address-grant' });
          await route.fulfill({ json: { recorded: true } });
        },
      },
      {
        url: '**/api/v1/connectors/google-maps/place-route',
        handler: async route => {
          routes++;
          await route.fulfill({ status: 500, json: { detail: 'Unexpected route request' } });
        },
      },
    ]);
    await page.route('https://maps.googleapis.com/**', async route => {
      scripts++;
      if (sample.retry && scripts === 1) return route.abort('failed');
      await route.fulfill({
        contentType: 'application/javascript',
        body: sdk,
        headers: {
          'access-control-allow-origin': '*',
          'cross-origin-resource-policy': 'cross-origin',
        },
      });
    });
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'address map');
    const card = page.locator('.lia-card.lia-location');
    const activate = card.getByRole('button', { name: 'Explorer cette adresse' });
    await expect(activate).toBeVisible();
    const preview = card.getByRole('img', { name: 'Ouvrir dans Maps' });
    await expect(preview).toBeVisible();
    await expect(card.getByRole('img', { name: 'Street View', exact: true })).toBeVisible();
    await card.screenshot({
      path: test.info().outputPath(`address-preview-${sample.width}-${sample.theme}.png`),
    });
    await expect(card.locator('.lia-location__label')).toBeVisible();
    await expect(card.getByRole('heading', { name: 'Lyon', exact: true })).toBeVisible();
    for (const fact of ['Place Bellecour, 69002 Lyon', 'France', 'Latitude', 'Longitude'])
      await expect(card).toContainText(fact);
    expect(admissions).toBe(0);
    expect(scripts).toBe(0);
    expect(routes).toBe(0);
    await activate.focus();
    await activate.press('Enter');
    if (sample.retry) {
      await expect(card.getByRole('alert')).toContainText('La carte est indisponible');
      await expect(preview).toBeVisible();
      await expect(activate).toBeFocused();
      expect(reports).toBe(0);
      await activate.press('Enter');
    }
    await expect(
      card.getByRole('region', { name: 'Carte interactive de l’adresse' })
    ).toBeVisible();
    await expect(card).toContainText('LOCAL_POSITION_MAP');
    const choice = card.getByRole('button', { name: 'Lyon', exact: true });
    await choice.focus();
    await choice.press('Enter');
    if (sample.width < 640) {
      const dialog = page.getByRole('dialog', { name: 'Lyon' });
      await expect(dialog.getByRole('heading', { name: 'Lyon' })).toBeFocused();
      await expect(dialog).toContainText('45.757800, 4.832000');
      await expect(dialog.getByRole('heading', { name: 'Trajet' })).toHaveCount(0);
      await expectNoOverflow(page, 'address details');
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(choice).toBeFocused();
    } else {
      await expect(page.getByText('45.757800, 4.832000', { exact: true })).toBeVisible();
    }
    await page.evaluate(() => {
      document.documentElement.dataset.theme = 'forest';
    });
    await card.getByRole('button', { name: 'Voir tous les repères' }).click();
    await expect.poll(() => reports).toBe(1);
    expect(admissions).toBe(sample.retry ? 2 : 1);
    expect(routes).toBe(0);
    const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
    expect(witness.maps).toBe(1);
    expect(witness.markers).toHaveLength(1);
    expect(witness.placesCalls).toBe(0);
    await expectNoOverflow(page, 'address map');
    expect(
      (
        await new AxeBuilder({ page })
          .include('.lia-card.lia-location')
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
          .analyze()
      ).violations
    ).toEqual([]);
    const captureHeight = await card.evaluate(element => {
      const scrollport = element.closest('.chat-scrollbar');
      if (!scrollport) throw new Error('Missing chat scroll viewport');
      return Math.ceil(
        element.getBoundingClientRect().height + window.innerHeight - scrollport.clientHeight
      );
    });
    const expandCapture = captureHeight > auditedViewport.height;
    if (expandCapture) await page.setViewportSize({ ...auditedViewport, height: captureHeight });
    await card.screenshot({
      path: test.info().outputPath(`location-${sample.theme}.png`),
      style:
        'body * { visibility: hidden !important; } .lia-card, .lia-card * { visibility: visible !important; }',
    });
    if (expandCapture) await page.setViewportSize(auditedViewport);
  });
}
