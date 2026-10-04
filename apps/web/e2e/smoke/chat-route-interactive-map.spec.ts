/** Actual SDK seam and production CSP, with local synthetic SDK/API only. */
import AxeBuilder from '@axe-core/playwright';
import { test, expect, waitForHydration } from '../fixtures';
import { loadedChatRoutes } from '../fixtures/chat';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const geometry = {
  version: 1,
  primary_id: 'route-1',
  omitted_count: 0,
  routes: [
    { id: 'route-0', polyline: '??_ibE_ibE', distance_meters: 0, duration_seconds: 0 },
    { id: 'route-1', polyline: '??_seK_seK', distance_meters: 1200, duration_seconds: 180 },
  ],
};
const content = `<div class="lia-card lia-route"><div class="lia-route-map" data-route-map="${JSON.stringify(geometry).replaceAll('"', '&quot;')}"><a href="https://www.google.com/maps">SOURCE_MAP</a></div></div>`;
const sdk = `(() => {
  const current=document.currentScript;
  const callback=new URL(current.src).searchParams.get('callback').split('.')[1];
  window.__mapWitness={maps:0,paths:[],styles:[],clicked:null};
  class Map { constructor(element){const box=element.getBoundingClientRect();if(box.width<50||box.height<100)throw Error('collapsed map');window.__mapWitness.maps++;element.innerHTML='<div style="height:100%;background:linear-gradient(160deg,#d8e9dd,#c6d8f0);display:grid;place-items:center;color:#111">LOCAL_SDK_MAP</div>';} fitBounds(){} setOptions(){} }
  class Polyline { constructor(options){this.options=options;window.__mapWitness.paths.push(options.path);} setMap(){} setOptions(options){window.__mapWitness.styles.push(options);} addListener(event,callback){if(!window.__mapWitness.clicked)window.__mapWitness.clicked=callback;return {remove(){}};} }
  class Bounds {extend(){} }
  window.google={maps:{MapTypeControlStyle:{DROPDOWN_MENU:1},Map,Polyline,LatLngBounds:Bounds,event:{clearInstanceListeners(){}}}};
  window.liaRouteMapsCallbacks[callback]();
})()`;

for (const sample of [
  { width: 1280, theme: 'light', retry: false },
  { width: 390, theme: 'dark', retry: false },
  { width: 320, theme: 'oled', retry: false },
  { width: 320, theme: 'dark', retry: true },
]) {
  test(`exact interactive routes ${sample.width} ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 1000 });
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
          api_version: '1',
        },
      },
      {
        url: '**/api/v1/conversations/me/messages*',
        json: {
          messages: [
            {
              id: '00000000-0000-4000-8000-00000000c499',
              role: 'assistant',
              content,
              created_at: '2026-10-03T09:00:00Z',
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
        url: '**/api/v1/connectors/google-maps/load-admissions',
        handler: async route => {
          admissions++;
          await route.fulfill({
            json: { api_key: 'hermetic-public-key', load_token: 'same-account-grant' },
          });
        },
      },
      {
        url: '**/api/v1/connectors/google-maps/load-reports',
        handler: async route => {
          reports++;
          expect(route.request().postDataJSON()).toEqual({ load_token: 'same-account-grant' });
          await route.fulfill({ json: { recorded: true } });
        },
      },
    ]);
    await page.route('https://maps.googleapis.com/**', async route => {
      scripts++;
      if (sample.retry && scripts === 1) {
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
    await awaitStyledPage(page, 'interactive routes');
    await page.evaluate(theme => {
      document.documentElement.classList.toggle('dark', theme !== 'light');
      document.documentElement.toggleAttribute('data-oled', theme === 'oled');
    }, sample.theme);
    const card = page.locator('.lia-card.lia-route');
    const activate = card.getByRole('button', { name: 'Explorer la carte' });
    await expect(activate).toBeVisible();
    expect(scripts).toBe(0);
    expect(admissions).toBe(0);
    await activate.focus();
    await activate.press('Enter');
    if (sample.retry) {
      await expect(card.getByRole('alert')).toContainText('La carte est indisponible');
      await expect(activate).toBeFocused();
      await expect(card.getByRole('link', { name: 'SOURCE_MAP' })).toBeVisible();
      expect(reports).toBe(0);
      await activate.press('Enter');
    }
    await expect(
      card.getByRole('region', { name: 'Carte interactive des itinéraires' })
    ).toBeVisible();
    await expect(card).toContainText('LOCAL_SDK_MAP');
    await expect(activate).toBeFocused();
    const alt = card.getByRole('button', { name: 'Alternative 1 0 km · 0 min' });
    await alt.focus();
    await alt.press('Enter');
    await expect(alt).toHaveAttribute('aria-pressed', 'true');
    await expect(card.getByRole('status')).toHaveText('Alternative 1 · 0 km · 0 min');
    await card.getByRole('button', { name: 'Recentrer sur la sélection' }).click();
    await expect.poll(() => reports).toBe(1);
    expect(admissions).toBe(sample.retry ? 2 : 1);
    expect(scripts).toBe(sample.retry ? 2 : 1);
    const witness = await page.evaluate(() => Reflect.get(window, '__mapWitness'));
    expect(witness.maps).toBe(1);
    expect(witness.paths).toEqual([
      [
        { lat: 0, lng: 0 },
        { lat: 1, lng: 1 },
      ],
      [
        { lat: 0, lng: 0 },
        { lat: 2, lng: 2 },
      ],
    ]);
    for (const button of await card.getByRole('button').all())
      expect((await button.boundingBox())?.height).toBeGreaterThanOrEqual(44);
    await expectNoOverflow(page, 'interactive map');
    expect(
      (
        await new AxeBuilder({ page })
          .include('.lia-card.lia-route')
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
          .analyze()
      ).violations
    ).toEqual([]);
    await card.screenshot({
      path: test.info().outputPath(`interactive-${sample.theme}.png`),
      style: 'nextjs-portal {display:none!important}',
    });
  });
}
