/** Actual native HTML crosses storage, sanitizer, production CSP and click admission. */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const reference: { html: string; html_mode: string; markdown: string; classified_at: string } =
  JSON.parse(
    readFileSync(
      path.join(
        __dirname,
        '../../../api/tests/unit/domains/agents/display/evolution_card_reference.json'
      ),
      'utf8'
    )
  );
const sdk = `(() => {
 const callback=new URL(document.currentScript.src).searchParams.get('callback').split('.')[1];
 window.__positionWitness={maps:0,markers:[],bounds:[],options:[]};
 const witness=window.__positionWitness;
 const markers=[];
 window.__clickPositionMarker=index=>markers[index].dispatchEvent(new Event('gmp-click'));
 class Map {constructor(element,options){witness.maps++;witness.options.push(options);const box=element.getBoundingClientRect();if(box.width<50||box.height<100)throw Error('collapsed');element.innerHTML='<div style="height:100%;background:#d8e9dd;color:#111;display:grid;place-items:center">LOCAL_POSITION_MAP</div>';}fitBounds(bounds){witness.bounds.push(bounds);}setOptions(options){witness.options.push(options);}}
 class Marker extends EventTarget {constructor(options){super();markers.push(this);witness.markers.push(options);this.map=options.map;}}
 class Bounds {constructor(value){Object.assign(this,value);}extend(){}}
 window.google={maps:{Map,Polyline:class{},LatLngBounds:Bounds,MapTypeControlStyle:{DROPDOWN_MENU:1},event:{clearInstanceListeners(){}},importLibrary:async()=>({AdvancedMarkerElement:Marker})}};
 window.liaRouteMapsCallbacks[callback]();
})()`;

for (const mode of ['html', 'markdown'] as const) {
  test(`Position precedes content in ${mode} mode`, async ({ page, authenticate, mockApi }) => {
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
    const card = page.locator('.lia-places-position');
    await expect(card.getByText('Position', { exact: true })).toBeVisible();
    await expect(card.getByRole('button', { name: 'Explorer la carte' })).toBeVisible();
    await expect(page.locator('.lia-card.lia-place')).toHaveCount(0);
    expect(
      await page.locator('main').evaluate(element => {
        const text = element.textContent ?? '';
        return text.indexOf('Position') < text.indexOf('Résultat sélectionné.');
      })
    ).toBe(true);
    expect(scripts).toBe(0);
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
    await page.emulateMedia({ reducedMotion: sample.reduced ? 'reduce' : 'no-preference' });
    await authenticate({ language: 'fr', response_display_mode: 'cards' });
    let scripts = 0,
      admissions = 0,
      reports = 0;
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
    await page.route('https://maps.googleapis.com/**', async route => {
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
    const activate = card.getByRole('button', { name: 'Explorer la carte' });
    await activate.focus();
    await activate.press('Enter');
    if (sample.failure) {
      await expect(card.getByRole('alert')).toContainText('La carte est indisponible');
      expect(reports).toBe(0);
      await activate.press('Enter');
    }
    await expect(card).toContainText('LOCAL_POSITION_MAP');
    const west = card.getByRole('button', { name: 'Lieu Ouest', exact: true });
    await west.focus();
    await west.press('Enter');
    await expect(west).toHaveAttribute('aria-pressed', 'true');
    await page.evaluate(() => Reflect.get(window, '__clickPositionMarker')(0));
    await expect(card.getByRole('button', { name: 'Lieu Est', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await card.getByRole('button', { name: 'Voir tous les repères' }).click();
    await expect.poll(() => reports).toBe(1);
    const witness = await page.evaluate(() => Reflect.get(window, '__positionWitness'));
    expect(witness.maps).toBe(1);
    expect(witness.markers).toHaveLength(3);
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
      path: test.info().outputPath('position-classification.png'),
      fullPage: true,
    });
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
