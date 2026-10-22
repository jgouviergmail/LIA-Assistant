/** Actual native HTML crosses storage, sanitizer, production CSP and click admission. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';
import type { PlacePositionData } from '../../src/lib/place-position-data';
import { test, expect, waitForHydration, waitForMockGate, type MockRoute } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { minimizeCompanion } from '../fixtures/companion';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const reference: { html: string; html_mode: string; markdown: string; classified_at: string } =
  JSON.parse(
    readFileSync(path.join(__dirname, '../fixtures/maps/evolution-card-reference-v1.json'), 'utf8')
  );
const sdk = readFileSync(path.join(__dirname, '../fixtures/maps/position-sdk.js'), 'utf8');
// The v2 Position card is emitted by production render_positions; the two
// archive display modes below deliberately retain the original v1 fixture.
const detailsReference: { html: string } = JSON.parse(
  readFileSync(path.join(__dirname, '../fixtures/maps/position-details.json'), 'utf8')
);
const detailsHtml =
  detailsReference.html + reference.html.slice(reference.html.indexOf('\n\nRésultat sélectionné.'));
const WEST_NAME = 'Lieu Ouest — Maison des découvertes et des rencontres du quartier';
const WEST_ADDRESS =
  '12 rue de l’Ouest, Maison des découvertes et des rencontres du quartier, bâtiment des ateliers, 2e étage, 75000 Ville Exemple, France';

/** Edit only the mock wire; archived native producer fixtures remain untouched. */
function editPosition(html: string, update: (wire: PlacePositionData) => void) {
  const attribute = html.match(/data-place-position="([^"]+)"/)![1];
  const entities: Record<string, string> = {
    '&quot;': '"',
    '&#92;': '\\',
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
  };
  const wire = JSON.parse(
    attribute.replace(/&quot;|&#92;|&amp;|&lt;|&gt;/g, token => entities[token])
  ) as PlacePositionData;
  update(wire);
  const escaped: Record<string, string> = {
    '&': '&amp;',
    '"': '&quot;',
    '\\': '&#92;',
    '<': '&lt;',
    '>': '&gt;',
  };
  return html.replace(
    attribute,
    JSON.stringify(wire).replace(/[&"\\<>]/g, token => escaped[token])
  );
}

interface RouteBody {
  destination: { lat: number; lng: number };
  origin?: { lat: number; lon: number; accuracy: number | null; timestamp: number };
}
interface RouteResult {
  origin_source: 'browser' | 'last_known' | 'home';
  origin_as_of: string | null;
  travel_mode: 'WALK' | 'DRIVE';
  polyline: string;
  distance_meters: number;
  duration_seconds: number;
}
function routeResult(overrides: Partial<RouteResult> = {}): RouteResult {
  return {
    origin_source: 'home',
    origin_as_of: null,
    travel_mode: 'WALK',
    polyline: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
    // The server chooses WALK up to 2 km inclusive, DRIVE beyond that limit.
    distance_meters: 2000,
    duration_seconds: 780,
    ...overrides,
  };
}
function positionRoutes(content = detailsHtml): MockRoute[] {
  return [
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
            id: '00000000-0000-4000-8000-00000000c599',
            role: 'assistant',
            content,
            created_at: reference.classified_at,
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
      url: '**/api/v1/connectors/google-maps/load-admissions*',
      json: {
        api_key: 'hermetic-public-key',
        map_id: 'configured-map-id',
        load_token: 'same-place-grant',
      },
    },
    { url: '**/api/v1/connectors/google-maps/load-reports', json: { recorded: true } },
  ];
}
async function mockPositionSdk(page: Page) {
  await page.route('https://maps.googleapis.com/maps/api/js*', route =>
    route.fulfill({
      contentType: 'application/javascript',
      headers: {
        'access-control-allow-origin': '*',
        'cross-origin-resource-policy': 'cross-origin',
      },
      body: sdk,
    })
  );
}
async function openPosition(page: Page) {
  await page.goto('/fr/dashboard/chat');
  await waitForHydration(page);
  await awaitStyledPage(page, 'position details and route');
  await page.getByText('Voir le détail', { exact: true }).click();
  const card = page.locator('.lia-places-position');
  await expectCompactPosition(card);
  await card.getByRole('button', { name: 'Explorer la carte' }).click();
  await expect(card).toContainText('LOCAL_POSITION_MAP');
  return card;
}

async function expectCompactPosition(card: Locator) {
  const stage = card.locator('.lia-place-position__stage');
  await expect(stage).toHaveAttribute('hidden', '');
  await expect(stage).toBeHidden();
  expect(await stage.evaluate(element => element.getBoundingClientRect().height)).toBe(0);
  await expect(card.getByRole('button', { name: 'Explorer la carte' })).toBeVisible();
  const choices = card.getByRole('list', { name: 'Lieux de la réponse' });
  await expect(choices).toBeVisible();
  await expect(choices.getByRole('link')).toHaveCount(4);
  for (const link of await choices.getByRole('link').all()) await expect(link).toBeVisible();
  const badges = choices.locator('.lia-place-position__number');
  await expect(badges).toHaveText(['1', '2', '3', '4']);
  for (const badge of await badges.all()) {
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute('aria-hidden', 'true');
    const box = await badge.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(24);
    expect(box!.height).toBeLessThanOrEqual(32);
    expect(await badge.evaluate(element => getComputedStyle(element).backgroundColor)).not.toBe(
      'rgba(0, 0, 0, 0)'
    );
  }
}

async function expectNumberedMapPins(card: Locator, numbers = ['1', '2', '3']) {
  const pins = card.locator('.lia-place-position__map-pin');
  await expect(pins).toHaveCount(numbers.length);
  await expect(pins.locator('[data-position-sdk-glyph]')).toHaveText(numbers);
  for (const [index, number] of numbers.entries()) {
    const pin = pins.nth(index);
    await expect(pin).toHaveAttribute('data-place-number', number);
    await expect(pin.locator('[data-position-sdk-glyph]')).toBeVisible();
    const badge = card
      .locator('.lia-place-position__choices .lia-place-position__number')
      .nth(Number(number) - 1);
    const colorsOf = (element: Element) => {
      const css = getComputedStyle(element);
      return { background: css.backgroundColor, foreground: css.color };
    };
    // Both are read in the same attempt: a badge read once, before a theme change has
    // settled, compared a stale colour with a settled pin (observed under load).
    await expect
      .poll(async () => {
        const [pinColors, badgeColors] = await Promise.all([
          pin.evaluate(colorsOf),
          badge.evaluate(colorsOf),
        ]);
        return {
          pin: pinColors,
          sameAsBadge: JSON.stringify(pinColors) === JSON.stringify(badgeColors),
        };
      })
      .toMatchObject({ sameAsBadge: true });
  }
}

async function expectSinglePopupScroll(details: Locator) {
  const scroll = details.locator(
    'xpath=ancestor::*[contains(@class,"gm-style-iw-d") or contains(@class,"lia-place-details-dialog__body")]'
  );
  await expect(scroll).toHaveCount(1);
  const layout = await details.evaluate(element => {
    const owner = element.closest('.gm-style-iw-d, .lia-place-details-dialog__body');
    const candidates = new Set<Element>([element, ...element.querySelectorAll('*')]);
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      candidates.add(parent);
      if (parent.getAttribute('role') === 'dialog') break;
    }
    const scrollers = [...candidates].filter(candidate => {
      const css = getComputedStyle(candidate);
      return (
        /^(auto|scroll)$/.test(css.overflowY) && candidate.scrollHeight > candidate.clientHeight + 1
      );
    });
    return {
      scrollers: scrollers.map(candidate => candidate === owner),
      ownerOverflow: owner && getComputedStyle(owner).overflowY,
      rootOverflow: getComputedStyle(element).overflowY,
      rootMaxHeight: getComputedStyle(element).maxHeight,
      rootHeight: element.clientHeight,
      rootScrollHeight: element.scrollHeight,
    };
  });
  expect(layout.scrollers.length).toBeLessThanOrEqual(1);
  expect(layout.scrollers.every(isOwner => isOwner)).toBe(true);
  expect(layout.ownerOverflow).toMatch(/^(auto|scroll)$/);
  expect(layout.rootOverflow).toBe('visible');
  expect(layout.rootMaxHeight).toBe('none');
  expect(layout.rootScrollHeight).toBeLessThanOrEqual(layout.rootHeight + 1);
  return scroll;
}

async function expectReachableWithNativeScroll(target: Locator, scroll: Locator) {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const viewport = await scroll.boundingBox();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(viewport!.y - 1);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.y + viewport!.height + 1);
}

async function expectTripFacts(
  details: Locator,
  facts: { mode: string; distance: string; duration: string }
) {
  const status = details.getByRole('status');
  await expect(status.getByText(facts.mode, { exact: true })).toBeVisible();
  for (const [term, value] of [
    ['Distance', facts.distance],
    ['Durée', facts.duration],
  ]) {
    const label = status.getByRole('term').filter({ hasText: new RegExp(`^${term}$`) });
    await expect(label).toBeVisible();
    await expect(label.locator('..').getByRole('definition')).toHaveText(value);
  }
  // Both boxes read in ONE frame, polled until the layout settles: the desktop
  // popup re-hosts the details the mobile dialog held, and two separate
  // boundingBox() calls straddling that move measured 2 000 px between the two
  // facts of one row (2026-10-22) — the notifications spec's own lesson.
  await expect
    .poll(async () => {
      const metrics = (await status.getByRole('definition').all()).slice(0, 2);
      const handles = await Promise.all(metrics.map(metric => metric.elementHandle()));
      const [first, second] = await details.page().evaluate(
        elements =>
          elements.map(element => {
            const rect = (element as Element).getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width };
          }),
        handles
      );
      return (
        first !== undefined &&
        second !== undefined &&
        Math.abs(first.y - second.y) <= 8 &&
        first.x + first.width <= second.x
      );
    })
    .toBe(true);
  await expect(details.getByRole('combobox')).toHaveCount(0);
  await expect(details.getByRole('radio')).toHaveCount(0);
}

async function expectPopupLayout(dialog: Locator, details: Locator, width: number) {
  const geometry = await details.evaluate(element => {
    const dialog = element.closest('[role="dialog"]')!;
    const dialogCss = getComputedStyle(dialog);
    const route = element.querySelector('.lia-place-details__route')!;
    const links = element.querySelector('.lia-place-details__links')!;
    const hours = element.querySelector('.lia-place-details__hours')!;
    const box = (target: Element) => {
      const rect = target.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    };
    return {
      dialog: box(dialog),
      viewportHeight: window.innerHeight,
      dialogPosition: {
        bottom: dialogCss.bottom,
        translate: dialogCss.translate,
        transform: dialogCss.transform,
      },
      body: box(element),
      route: box(route),
      links: box(links),
      routeBeforeLinks: Boolean(
        route.compareDocumentPosition(links) & Node.DOCUMENT_POSITION_FOLLOWING
      ),
      routeBeforeHours: Boolean(
        route.compareDocumentPosition(hours) & Node.DOCUMENT_POSITION_FOLLOWING
      ),
      horizontalOverflow: element.scrollWidth > element.clientWidth + 1,
    };
  });
  await test.info().attach('position-popup-geometry', {
    contentType: 'application/json',
    body: JSON.stringify(geometry, null, 2),
  });
  expect(geometry.routeBeforeLinks).toBe(true);
  expect(geometry.routeBeforeHours).toBe(true);
  expect(geometry.route.y + geometry.route.height).toBeLessThanOrEqual(geometry.links.y + 1);
  expect(geometry.horizontalOverflow).toBe(false);
  expect(geometry.dialog.x).toBeGreaterThanOrEqual(0);
  expect(geometry.dialog.x + geometry.dialog.width).toBeLessThanOrEqual(width + 1);
  if (width >= 640) expect(geometry.dialog.width).toBeGreaterThanOrEqual(400);
  else {
    expect(geometry.dialog.width).toBeGreaterThanOrEqual(width - 20);
    expect(geometry.dialog.width).toBeLessThanOrEqual(width - 12);
    expect(geometry.dialog.y + geometry.dialog.height).toBeGreaterThanOrEqual(
      geometry.viewportHeight - 16
    );
    expect(geometry.dialog.y + geometry.dialog.height).toBeLessThanOrEqual(geometry.viewportHeight);
    expect(geometry.viewportHeight - geometry.dialog.y - geometry.dialog.height).toBeCloseTo(8, 0);
  }
  await expect(dialog.getByRole('heading', { name: WEST_NAME, exact: true })).toHaveCount(1);
  await expect(details.getByRole('heading', { name: WEST_NAME, exact: true })).toHaveCount(0);
}

for (const mode of ['html', 'markdown'] as const) {
  test(`Position precedes content in ${mode} mode`, async ({ page, authenticate, mockApi }) => {
    await minimizeCompanion(page);
    await authenticate({ language: 'fr', response_display_mode: mode });
    let scripts = 0;
    await page.route('https://maps.googleapis.com/**', async route => {
      scripts++;
      await route.abort('failed');
    });
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
              id: '00000000-0000-4000-8000-00000000c597',
              role: 'assistant',
              content: reference[mode === 'html' ? 'html_mode' : 'markdown'],
              created_at: reference.classified_at,
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000c099',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, `compact position in ${mode} mode`);
    const card = page.locator('.lia-places-position');
    await expect(card.getByText('Position', { exact: true })).toBeVisible();
    await expectCompactPosition(card);
    await expect(page.locator('.lia-card.lia-place')).toHaveCount(0);
    expect(
      await page.locator('main').evaluate(element => {
        const text = element.textContent ?? '';
        return text.indexOf('Position') < text.indexOf('Résultat sélectionné.');
      })
    ).toBe(true);
    expect(scripts).toBe(0);
    await card.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-before-activation.png'),
    });
  });
}

for (const sample of [
  { width: 1280, theme: 'light', failure: false, reduced: false },
  { width: 390, theme: 'dark', failure: false, reduced: true },
  { width: 320, theme: 'oled', failure: true, reduced: false },
]) {
  test(`native qualifications and places ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 1200 });
    if (sample.width >= 1024) await minimizeCompanion(page);
    await page.emulateMedia({ reducedMotion: sample.reduced ? 'reduce' : 'no-preference' });
    await authenticate({ language: 'fr', response_display_mode: 'cards' });
    let scripts = 0,
      admissions = 0,
      reports = 0;
    const routeBodies: RouteBody[] = [];
    const placesRequests: string[] = [];
    page.on('request', request => {
      if (/places\.googleapis\.com|\/maps\/api\/place\//.test(request.url()))
        placesRequests.push(request.url());
    });
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/config',
        json: {
          sse: { heartbeat_interval_seconds: 30 },
          rate_limits: { enabled: false, per_minute: 60, burst: 10 },
          i18n: { supported_languages: ['fr'], default_language: 'fr' },
          features: { interactive_route_maps_enabled: true },
          route_maps: { enabled: true, estimated_cost_eur: '0.006' },
          place_maps: { enabled: true, estimated_cost_eur: '0.006' },
          api_version: '1',
        },
      },
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c599',
              role: 'assistant',
              content: detailsHtml,
              created_at: reference.classified_at,
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
        url: '**/api/v1/connectors/google-maps/place-route',
        method: 'POST',
        handler: async route => {
          const body: RouteBody = route.request().postDataJSON();
          routeBodies.push(body);
          expect(body.origin).toBeUndefined();
          const attempts = routeBodies.filter(
            value => value.destination.lat === body.destination.lat
          ).length;
          if (sample.failure && body.destination.lat === 1 && attempts === 1) {
            await route.fulfill({
              status: 422,
              json: {
                detail: {
                  code: 'place_route_origin_unavailable',
                  message: 'No origin available',
                },
              },
            });
          } else if (sample.width === 390 && body.destination.lat === 0 && attempts === 1) {
            await route.fulfill({ status: 503, json: { detail: 'Route unavailable' } });
          } else {
            await route.fulfill({
              json:
                body.destination.lat === 1
                  ? routeResult()
                  : routeResult({
                      origin_source: 'last_known',
                      origin_as_of: '2026-10-19T09:30:00Z',
                      travel_mode: 'DRIVE',
                      distance_meters: 2400,
                      duration_seconds: 660,
                    }),
            });
          }
        },
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
              load_token: 'same-place-grant',
            },
          });
        },
      },
      {
        url: '**/api/v1/connectors/google-maps/load-reports',
        handler: async route => {
          reports++;
          expect(route.request().postDataJSON()).toEqual({ load_token: 'same-place-grant' });
          await route.fulfill({ json: { recorded: true } });
        },
      },
    ]);
    await page.route('https://maps.googleapis.com/maps/api/js*', async route => {
      scripts++;
      if (sample.failure && scripts === 1) {
        await route.abort('failed');
        return;
      }
      await route.fulfill({
        contentType: 'application/javascript',
        headers: {
          'access-control-allow-origin': '*',
          'cross-origin-resource-policy': 'cross-origin',
        },
        body: sdk,
      });
    });
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await awaitStyledPage(page, 'native classifications and positions');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    await page.getByText('Voir le détail', { exact: true }).click();
    const phishing = page.locator('.content-classification-badge--phishing');
    await expect(phishing).toHaveText('⚠ Phishing/Arnaque');
    await expect(
      page.locator('.lia-classification').getByText('Professionnel', { exact: true })
    ).toBeVisible();
    // Stored annotations remain readable but never replay a fresh attention pulse.
    expect(await phishing.evaluate(element => getComputedStyle(element).animationName)).toBe(
      'none'
    );
    const card = page.locator('.lia-places-position');
    await expect(card.getByText('Position', { exact: true })).toBeVisible();
    expect(
      await card.evaluate(element => {
        const place = document.querySelector('.lia-card.lia-place');
        return Boolean(
          place && element.compareDocumentPosition(place) & Node.DOCUMENT_POSITION_FOLLOWING
        );
      })
    ).toBe(true);
    await expect(
      card.getByRole('link', { name: 'Lieu sans coordonnées', exact: true })
    ).toBeVisible();
    await expect(card).toContainText('0,006');
    expect(scripts).toBe(0);
    expect(admissions).toBe(0);
    expect(reports).toBe(0);
    await expectCompactPosition(card);
    const activate = card.getByRole('button', { name: 'Explorer la carte' });
    await activate.focus();
    await expect(activate).toBeFocused();
    await card.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-compact-card.png'),
    });
    await activate.press('Enter');
    if (sample.failure) {
      await expect(card.getByRole('alert')).toContainText('La carte est indisponible');
      await expectCompactPosition(card);
      await expect(activate).toBeFocused();
      await expect(activate).toHaveAttribute('aria-disabled', 'false');
      expect(reports).toBe(0);
      await card.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-error-retracted.png'),
      });
      await activate.press('Enter');
    }
    await expect(card).toContainText('LOCAL_POSITION_MAP');
    const stage = card.locator('.lia-place-position__stage');
    await expect(stage).not.toHaveAttribute('hidden');
    await expect(stage).toBeVisible();
    expect((await stage.boundingBox())?.height).toBeGreaterThanOrEqual(240);
    await expect(card.getByRole('region', { name: 'Position des lieux' })).toBeVisible();
    await expectNumberedMapPins(card);
    await expect(activate).toBeFocused();
    await expect(activate).toHaveAttribute('aria-disabled', 'true');
    expect(routeBodies).toEqual([]);
    await card.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-ready-expanded.png'),
    });
    const west = card.getByRole('button', { name: WEST_NAME, exact: true, includeHidden: true });
    await west.focus();
    await west.press('Enter');
    const mobile = sample.width < 640;
    const westDialog = page.getByRole('dialog', { name: WEST_NAME, exact: true });
    await expect(westDialog).toBeVisible();
    if (mobile)
      await expect
        .poll(() => westDialog.evaluate(element => element.contains(document.activeElement)))
        .toBe(true);
    else await expect(west).toBeFocused();
    await expect(west).toHaveAttribute('aria-pressed', 'true');
    const westDetails = westDialog.getByRole('region', { name: WEST_NAME, exact: true });
    await expect(westDialog.getByRole('heading', { name: WEST_NAME })).toBeVisible();
    await expect(westDetails).toContainText(WEST_ADDRESS);
    await expect(westDetails).toContainText('4,7 / 5 · 42 avis');
    await expect(westDetails.getByRole('link', { name: 'Site internet' })).toHaveAttribute(
      'href',
      'https://west.example.test/'
    );
    await expect(westDetails.getByRole('link', { name: '+33102030405' })).toHaveAttribute(
      'href',
      'tel:+33102030405'
    );
    const source = westDetails.getByRole('link', { name: `Ouvrir ${WEST_NAME} dans Google Maps` });
    await expect(source).toHaveAttribute(
      'href',
      'https://www.google.com/maps/place/?q=place_id:west'
    );
    await expectPopupLayout(westDialog, westDetails, sample.width);
    const popupScroll = await expectSinglePopupScroll(westDetails);
    await expectReachableWithNativeScroll(
      westDetails.getByRole('heading', { name: 'Trajet' }),
      popupScroll
    );
    // Returning to the top still exposes the route before secondary details.
    await popupScroll.evaluate(element => {
      element.scrollTop = 0;
    });
    {
      const refresh = westDetails.getByRole('button', { name: 'Actualiser le trajet' });
      const box = await refresh.boundingBox();
      const viewport = await popupScroll.boundingBox();
      expect(box!.y).toBeGreaterThanOrEqual(viewport!.y - 1);
      expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.y + viewport!.height + 1);
    }
    await westDialog.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-details-overview.png'),
    });
    const hours = westDetails.locator('summary').filter({ hasText: 'Horaires' });
    await hours.focus();
    await hours.press('Enter');
    await expect(westDetails.getByRole('listitem')).toHaveCount(7);
    await expect(westDetails).toContainText('Lundi: 09:00–12:30, 14:00–18:30');
    const nativeScroll = await expectSinglePopupScroll(westDetails);
    if (sample.width === 320) {
      await expectReachableWithNativeScroll(source, nativeScroll);
      await source.focus();
      await expect(source).toBeFocused();
      await expectReachableWithNativeScroll(hours, nativeScroll);
      await expectReachableWithNativeScroll(
        westDetails.getByText('Dimanche: 10:00–13:00', { exact: true }),
        nativeScroll
      );
      const overflow = await nativeScroll.evaluate(element => ({
        needed: element.scrollHeight > element.clientHeight + 1,
        top: element.scrollTop,
      }));
      if (overflow.needed) expect(overflow.top).toBeGreaterThan(0);
    }
    await westDialog.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-details-hours.png'),
    });
    if (sample.failure) {
      await expect(westDetails.getByRole('alert')).toContainText('renseigne ton domicile');
      await expect(westDetails).toContainText(WEST_ADDRESS);
      const retry = westDetails.getByRole('button', { name: 'Actualiser le trajet' });
      await retry.focus();
      await westDialog.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-origin-unavailable.png'),
      });
      await retry.press('Enter');
      await expect(retry).toBeFocused();
      await expect(retry).toHaveAttribute('aria-disabled', 'false');
    }
    await expect(westDetails.getByRole('status')).toContainText('Depuis ton domicile');
    await expectTripFacts(westDetails, { mode: 'À pied', distance: '2 km', duration: '13 min' });
    if (sample.width === 320) {
      await expectReachableWithNativeScroll(westDetails.getByRole('status'), nativeScroll);
      const refresh = westDetails.getByRole('button', { name: 'Actualiser le trajet' });
      await expectReachableWithNativeScroll(refresh, nativeScroll);
      await refresh.focus();
      await expect(refresh).toBeFocused();
      await expectSinglePopupScroll(westDetails);
      await westDialog.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-details-single-scroll-route.png'),
      });
    }
    if (mobile) {
      await hours.focus();
      await hours.press('Enter');
      await popupScroll.evaluate(element => {
        element.scrollTop = 0;
      });
      await westDialog.getByRole('heading', { name: WEST_NAME, exact: true }).click();
      await westDialog.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-details-ready-overview.png'),
      });
      await page.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-details-context.png'),
        fullPage: true,
      });
    }
    const westRequests = routeBodies.length;
    if (mobile) {
      await westDialog.getByRole('button', { name: 'Fermer', exact: true }).click();
      await expect(westDialog).toBeHidden();
      await expect(west).toBeFocused();
    }
    await west.focus();
    await west.press('Enter');
    await expect(westDetails.getByRole('status')).toContainText('2 km');
    expect(routeBodies).toHaveLength(westRequests);
    await westDialog.getByRole('button', { name: 'Fermer', exact: true }).click();
    await expect(westDialog).toBeHidden();
    if (mobile) await expect(west).toBeFocused();
    await card.getByRole('button', { name: '1. Lieu Est', exact: true }).click();
    await expect(
      card.getByRole('button', { name: 'Lieu Est', exact: true, includeHidden: true })
    ).toHaveAttribute('aria-pressed', 'true');
    const eastDialog = page.getByRole('dialog', { name: 'Lieu Est', exact: true });
    const eastDetails = eastDialog.getByRole('region', { name: 'Lieu Est', exact: true });
    await expect(eastDialog).toBeVisible();
    await expect(page.getByRole('dialog', { name: WEST_NAME, exact: true })).toHaveCount(0);
    await expect(eastDetails).toContainText('8 avenue de l’Est, Ville Exemple');
    if (sample.width === 390) {
      await expect(eastDetails.getByRole('alert')).toContainText('n’a pas pu être calculé');
      await expect(eastDetails.getByRole('link', { name: 'Site internet' })).toHaveAttribute(
        'href',
        'https://east.example.test/'
      );
      const retry = eastDetails.getByRole('button', { name: 'Actualiser le trajet' });
      await retry.focus();
      await eastDialog.screenshot({
        animations: 'disabled',
        path: test.info().outputPath('position-route-error.png'),
      });
      await retry.press('Enter');
      await expect(retry).toBeFocused();
    }
    await expect(eastDetails.getByRole('status')).toContainText('dernière position connue');
    await expect(eastDetails.getByRole('status')).toContainText('19/10/2026');
    await expectTripFacts(eastDetails, {
      mode: 'En voiture',
      distance: '2,4 km',
      duration: '11 min',
    });
    await eastDialog.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-details-route.png'),
    });
    expect(
      (
        await new AxeBuilder({ page })
          .include(mobile ? '.lia-place-details-dialog' : '.lia-places-position')
          .analyze()
      ).violations
    ).toEqual([]);
    for (const button of await eastDialog.getByRole('button').all())
      expect((await button.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    if (mobile) {
      await eastDialog.getByRole('button', { name: 'Fermer', exact: true }).click();
      await expect(eastDialog).toBeHidden();
    }
    await card.getByRole('button', { name: 'Voir tous les repères' }).click();
    await expect.poll(() => reports).toBe(1);
    const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
    expect(witness.maps).toBe(1);
    expect(witness.infoWindows).toBe(mobile ? 0 : 1);
    expect(witness.infoWindowOptions).toEqual(mobile ? [] : [{ maxWidth: 440 }]);
    expect(witness.polylines).toHaveLength(1);
    expect(witness.polylines[0].map).toBe(1);
    expect(witness.polylines[0].path).toHaveLength(3);
    expect(
      witness.popupOpens.every(
        (value: { map: number; shouldFocus: boolean }) =>
          value.map === 1 && value.shouldFocus === false
      )
    ).toBe(true);
    expect(witness.libraryCalls).toEqual(['marker']);
    expect(witness.placesCalls).toBe(0);
    expect(placesRequests).toEqual([]);
    expect(witness.sizes).toHaveLength(1);
    expect(witness.sizes[0].width).toBeGreaterThanOrEqual(50);
    expect(witness.sizes[0].height).toBeGreaterThanOrEqual(240);
    expect(witness.sizes[0].stageHidden).toBe(false);
    expect(witness.markers).toHaveLength(3);
    expect(witness.pins.map((pin: { glyphText: string }) => pin.glyphText)).toEqual([
      '1',
      '2',
      '3',
    ]);
    expect(witness.markers.map((value: { position: object }) => value.position)).toEqual([
      { lat: 0, lng: 179.9 },
      { lat: 1, lng: -179.9 },
      { lat: 0, lng: 179.9 },
    ]);
    expect(witness.options[0]).toMatchObject({
      mapId: 'configured-map-id',
      colorScheme: sample.theme === 'light' ? 'LIGHT' : 'DARK',
    });
    expect(witness.bounds[0]).toMatchObject({ north: 1, south: 0, west: 179.9, east: -179.9 });
    expect(admissions).toBe(sample.failure ? 2 : 1);
    for (const button of await card.getByRole('button').all())
      expect((await button.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expectNoOverflow(page, 'positions and badges');
    expect(
      (
        await new AxeBuilder({ page })
          .include('.lia-places-position')
          .include('.lia-classification')
          .analyze()
      ).violations
    ).toEqual([]);
    await page.screenshot({
      animations: 'disabled',
      path: test.info().outputPath('position-classification.png'),
      fullPage: true,
    });
  });
}

test('numbered pins keep source positions around an unlocated place on mobile', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const html = editPosition(detailsHtml, wire => {
    const [east, west, same, missing] = wire.places;
    wire.places = [east, west, missing, same];
  });
  await page.setViewportSize({ width: 320, height: 1200 });
  await authenticate({ language: 'fr', response_display_mode: 'cards' });
  await mockPositionSdk(page);
  const bodies: RouteBody[] = [];
  let reports = 0;
  await mockApi([
    ...positionRoutes(html),
    {
      url: '**/api/v1/connectors/google-maps/place-route',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({ json: routeResult() });
      },
    },
    {
      url: '**/api/v1/connectors/google-maps/load-reports',
      handler: async route => {
        reports++;
        await route.fulfill({ json: { recorded: true } });
      },
    },
  ]);
  const card = await openPosition(page);
  // The modal hides the underlying list from assistive technology while open.
  const choices = card.getByRole('list', { name: 'Lieux de la réponse', includeHidden: true });
  const missing = choices.getByRole('listitem').nth(2);
  await expect(missing.locator('.lia-place-position__number')).toHaveText('3');
  await expect(
    missing.getByRole('link', { name: 'Lieu sans coordonnées', exact: true })
  ).toBeVisible();
  await expect(missing.getByRole('button')).toHaveCount(0);
  await expectNumberedMapPins(card, ['1', '2', '4']);
  await card.screenshot({
    animations: 'disabled',
    path: test.info().outputPath('position-numbered-pins-gap-before-selection.png'),
  });
  const marker = card.getByRole('button', { name: '4. Lieu aux mêmes coordonnées', exact: true });
  await marker.focus();
  await expect(marker).toBeFocused();
  await marker.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Lieu aux mêmes coordonnées', exact: true });
  await expectTripFacts(dialog, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  const selected = choices.getByRole('button', {
    name: 'Lieu aux mêmes coordonnées',
    exact: true,
    includeHidden: true,
  });
  await expect(selected).toHaveAttribute('aria-pressed', 'true');
  expect(bodies.map(body => body.destination)).toEqual([{ lat: 0, lng: 179.9 }]);
  await dialog.getByRole('button', { name: 'Fermer', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(selected).toBeFocused();
  await page.evaluate(() => document.documentElement.classList.add('dark'));
  await expectNumberedMapPins(card, ['1', '2', '4']);
  const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
  expect(witness.maps).toBe(1);
  expect(witness.pins.map((pin: { glyphText: string }) => pin.glyphText)).toEqual(['1', '2', '4']);
  expect(witness.markers.map((marker: { title: string }) => marker.title)).toEqual([
    '1. Lieu Est',
    `2. ${WEST_NAME}`,
    '4. Lieu aux mêmes coordonnées',
  ]);
  expect(witness.placesCalls).toBe(0);
  await expect.poll(() => reports).toBe(1);
  expect(bodies).toHaveLength(1);
  await card.screenshot({
    animations: 'disabled',
    path: test.info().outputPath('position-numbered-pins-gap.png'),
  });
});

test('selected place survives mobile and desktop popup changes without another load', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const name = '地'.repeat(200);
  const html = editPosition(detailsHtml, wire => {
    const extreme = wire.places.find(place => place.ref === 'west')!;
    extreme.label = name;
    expect(extreme.label.length).toBe(200);
  }).replaceAll(WEST_NAME, name);
  await test.info().attach('extreme-position-wire', {
    contentType: 'application/json',
    body: JSON.stringify({ ref: 'west', label: name, length: name.length }),
  });
  await page.setViewportSize({ width: 320, height: 1200 });
  await authenticate({ language: 'fr', response_display_mode: 'cards' });
  await mockPositionSdk(page);
  const bodies: RouteBody[] = [];
  let reports = 0;
  await mockApi([
    ...positionRoutes(html),
    {
      url: '**/api/v1/connectors/google-maps/place-route',
      method: 'POST',
      handler: async route => {
        bodies.push(route.request().postDataJSON());
        await route.fulfill({ json: routeResult() });
      },
    },
    {
      url: '**/api/v1/connectors/google-maps/load-reports',
      handler: async route => {
        reports++;
        await route.fulfill({ json: { recorded: true } });
      },
    },
  ]);
  const card = await openPosition(page);
  const west = card.getByRole('button', { name, exact: true, includeHidden: true });
  await west.click();
  const dialog = page.getByRole('dialog', { name, exact: true });
  const details = dialog.getByRole('region', { name, exact: true });
  await expect(page.locator('.lia-place-details-dialog')).toBeVisible();
  await expectTripFacts(details, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  expect(bodies).toHaveLength(1);

  await page.setViewportSize({ width: 1280, height: 1000 });
  await expect(page.locator('.lia-place-details-dialog')).toBeHidden();
  await expect(card.locator('.gm-style-iw-c')).toBeVisible();
  await expectTripFacts(details, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  await expect(west).toHaveAttribute('aria-pressed', 'true');
  expect(bodies).toHaveLength(1);
  const desktopRefresh = details.getByRole('button', { name: 'Actualiser le trajet' });
  await desktopRefresh.focus();
  await expect(desktopRefresh).toBeFocused();

  await page.setViewportSize({ width: 320, height: 1200 });
  await expect(card.locator('.gm-style-iw-c')).toHaveCount(0);
  await expect(page.locator('.lia-place-details-dialog')).toBeVisible();
  await expectTripFacts(details, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  await expect(west).toHaveAttribute('aria-pressed', 'true');
  expect(bodies).toHaveLength(1);
  await expect.poll(() => reports).toBe(1);
  const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
  expect(witness.maps).toBe(1);
  expect(witness.infoWindows).toBe(1);
  expect(witness.infoWindowOptions).toEqual([{ maxWidth: 440 }]);
  expect(witness.polylines).toHaveLength(1);
  expect(witness.placesCalls).toBe(0);
  await dialog.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(west).toBeFocused();

  await page.setViewportSize({ width: 1280, height: 1000 });
  await west.click();
  await expect(card.locator('.gm-style-iw-c')).toBeVisible();
  await expectTripFacts(details, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  await desktopRefresh.focus();
  await desktopRefresh.press('Escape');
  await expect(dialog).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 1200 });
  await expect(page.locator('.lia-place-details-dialog')).toHaveCount(0);

  // The same panel must reflow with the account's largest supported text scale.
  await page.evaluate(() => document.documentElement.style.setProperty('--lia-text-scale', '1.75'));
  await west.click();
  await expectTripFacts(details, { mode: 'À pied', distance: '2 km', duration: '13 min' });
  expect(bodies).toHaveLength(1);
  const title = dialog.getByRole('heading', { name, exact: true });
  expect(
    await title.evaluate(element => parseFloat(getComputedStyle(element).fontSize))
  ).toBeGreaterThanOrEqual(29);
  await dialog.screenshot({
    animations: 'disabled',
    path: test.info().outputPath('position-details-mobile-text-scale.png'),
  });
  await details.locator('summary').filter({ hasText: 'Horaires' }).click();
  const scroll = await expectSinglePopupScroll(details);
  expect(await scroll.evaluate(element => element.clientHeight)).toBeGreaterThan(0);
  expect(await scroll.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  expect(await details.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(
    true
  );
  await expectReachableWithNativeScroll(
    details.getByRole('link', { name: `Ouvrir ${name} dans Google Maps` }),
    scroll
  );
  await expectReachableWithNativeScroll(
    details.getByText('Dimanche: 10:00–13:00', { exact: true }),
    scroll
  );
  await dialog.screenshot({
    animations: 'disabled',
    path: test.info().outputPath('position-details-mobile-text-scale-hours.png'),
  });
  await dialog.getByRole('button', { name: 'Fermer', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(west).toBeFocused();
});

test('latest place selection owns its route and the short-lived cache', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ language: 'fr', response_display_mode: 'cards' });
  await mockPositionSdk(page);
  let releaseSlow: () => void = () => {
    throw new Error('Slow route gate was not initialized');
  };
  let finishSlow: () => void = () => {
    throw new Error('Slow route completion was not initialized');
  };
  const slow = new Promise<void>(resolve => {
    releaseSlow = resolve;
  });
  const slowFinished = new Promise<void>(resolve => {
    finishSlow = resolve;
  });
  const bodies: RouteBody[] = [];
  let slowAborted = false;
  page.on('requestfailed', request => {
    if (
      request.url().endsWith('/google-maps/place-route') &&
      request.postDataJSON()?.destination?.lat === 1
    )
      slowAborted = true;
  });
  await mockApi([
    ...positionRoutes(),
    {
      url: '**/api/v1/connectors/google-maps/place-route',
      method: 'POST',
      handler: async (route, signal) => {
        const body: RouteBody = route.request().postDataJSON();
        bodies.push(body);
        if (body.destination.lat === 1) {
          try {
            if ((await waitForMockGate(slow, signal)) && !route.request().failure())
              await route.fulfill({
                json: routeResult({
                  polyline: '??_ibE_ibE',
                  travel_mode: 'DRIVE',
                  distance_meters: 9900,
                }),
              });
          } finally {
            finishSlow();
          }
        } else
          await route.fulfill({
            json: routeResult({
              distance_meters: 1200,
              duration_seconds: 600,
            }),
          });
      },
    },
  ]);
  const card = await openPosition(page);
  await card.getByRole('button', { name: WEST_NAME, exact: true }).click();
  await expect.poll(() => bodies.length).toBe(1);
  await expect(card.getByRole('region', { name: WEST_NAME, exact: true })).toContainText(
    'Calcul du trajet'
  );
  await page.evaluate(() => Reflect.get(window, '__clickPositionMarker')(0));
  const details = card.getByRole('region', { name: 'Lieu Est', exact: true });
  await expectTripFacts(details, { mode: 'À pied', distance: '1,2 km', duration: '10 min' });
  releaseSlow();
  await slowFinished;
  await expect.poll(() => slowAborted).toBe(true);
  await expect(details).not.toContainText('9,9 km');
  expect(bodies.map(body => body.destination)).toEqual([
    { lat: 1, lng: -179.9 },
    { lat: 0, lng: 179.9 },
  ]);
  await card.getByRole('button', { name: 'Lieu Est', exact: true }).click();
  await expect(details.getByRole('status')).toContainText('1,2 km');
  expect(bodies).toHaveLength(2);
  await page.clock.setFixedTime(new Date(Date.now() + 121_000));
  await card.getByRole('button', { name: 'Lieu Est', exact: true }).click();
  await expect.poll(() => bodies.length).toBe(3);
  await expect(details.getByRole('status')).toContainText('1,2 km');
  const refresh = details.getByRole('button', { name: 'Actualiser le trajet' });
  await refresh.focus();
  await refresh.press('Enter');
  await expect.poll(() => bodies.length).toBe(4);
  await expect(refresh).toBeFocused();
  await expect(refresh).toHaveAttribute('aria-disabled', 'false');
  const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
  expect(witness.maps).toBe(1);
  expect(witness.polylines).toHaveLength(1);
  expect(witness.polylines[0].map).toBe(1);
  expect(witness.polylines[0].path).toHaveLength(3);
});

for (const location of [
  { enabled: false, permission: 'granted' },
  { enabled: true, permission: 'prompt' },
  { enabled: true, permission: 'granted' },
] as const) {
  test(`place origin respects opt-in ${location.enabled} and permission ${location.permission}`, async ({
    page,
    context,
    authenticate,
    mockApi,
  }) => {
    await context.setGeolocation({ latitude: 48.86, longitude: 2.35, accuracy: 12 });
    if (location.permission === 'granted') await context.grantPermissions(['geolocation']);
    await page.addInitScript(() => {
      // Start the unrelated chat location hook opted out; set the tested
      // account preference immediately before the explicit place selection.
      localStorage.setItem('geolocation_enabled', 'false');
      Reflect.set(window, '__positionGpsReads', 0);
      const read = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);
      navigator.geolocation.getCurrentPosition = (success, error, options) => {
        Reflect.set(window, '__positionGpsReads', Reflect.get(window, '__positionGpsReads') + 1);
        read(success, error, options);
      };
    });
    await authenticate({ language: 'fr', response_display_mode: 'cards' });
    await mockPositionSdk(page);
    const bodies: RouteBody[] = [];
    const browserOrigin = location.enabled && location.permission === 'granted';
    await mockApi([
      ...positionRoutes(),
      {
        url: '**/api/v1/connectors/google-maps/place-route',
        method: 'POST',
        handler: async route => {
          bodies.push(route.request().postDataJSON());
          await route.fulfill({
            json: routeResult({ origin_source: browserOrigin ? 'browser' : 'home' }),
          });
        },
      },
    ]);
    const card = await openPosition(page);
    expect(await page.evaluate(() => Reflect.get(window, '__positionGpsReads'))).toBe(0);
    expect(bodies).toEqual([]);
    await page.evaluate(enabled => {
      localStorage.setItem('geolocation_enabled', String(enabled));
    }, location.enabled);
    const west = card.getByRole('button', { name: WEST_NAME, exact: true });
    await west.focus();
    await west.press('Enter');
    const details = card.getByRole('region', { name: WEST_NAME, exact: true });
    await expect(details.getByRole('status')).toContainText(
      browserOrigin ? 'Depuis ta position actuelle' : 'Depuis ton domicile'
    );
    expect(bodies).toHaveLength(1);
    expect(bodies[0].destination).toEqual({ lat: 1, lng: -179.9 });
    if (browserOrigin)
      expect(bodies[0].origin).toEqual({
        lat: 48.86,
        lon: 2.35,
        accuracy: 12,
        timestamp: expect.any(Number),
      });
    else expect(bodies[0].origin).toBeUndefined();
    expect(await page.evaluate(() => Reflect.get(window, '__positionGpsReads'))).toBe(
      browserOrigin ? 1 : 0
    );
  });
}

for (const reduced of [false, true]) {
  test(`finite phishing attention, reduced motion ${reduced}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr', response_display_mode: 'cards' });
    await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
    await page.clock.setFixedTime(new Date(reference.classified_at));
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c598',
              role: 'assistant',
              content: reference.html,
              created_at: reference.classified_at,
              metadata: null,
            },
          ],
          conversation_id: '00000000-0000-4000-8000-00000000c099',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        },
      },
    ]);
    await page.goto('/fr/dashboard/chat');
    await waitForHydration(page);
    await page.getByText('Voir le détail', { exact: true }).click();
    const badge = page.locator('.content-classification-badge--phishing');
    await expect(badge).toBeVisible();
    if (reduced)
      expect(await badge.evaluate(element => getComputedStyle(element).animationName)).toBe('none');
    else {
      await expect
        .poll(() =>
          badge.evaluate(element => {
            const css = getComputedStyle(element);
            return [css.animationName, css.animationDuration, css.animationIterationCount];
          })
        )
        .toEqual(['classification-attention', '1s', '4']);
      await expect
        .poll(
          () =>
            badge.evaluate(
              element =>
                element.getAnimations().filter(animation => animation.playState === 'running')
                  .length
            ),
          { timeout: 7000 }
        )
        .toBe(0);
    }
    await page.clock.setFixedTime(new Date(Date.parse(reference.classified_at) + 10000));
    await page.reload();
    await waitForHydration(page);
    await page.getByText('Voir le détail', { exact: true }).click();
    expect(await badge.evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  });
}
