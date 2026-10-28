/** Real server seating and native dashboard UI; paid briefing data is an explicit inert fixture. */
import { test, expect, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { openNativeWorld, enterWorld, revealWorldControls } from '../fixtures/world-admission';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { homeBriefing, HOME_ORDER, HOME_STATISTICS } from '../fixtures/dashboard-home';
import { worldProofUrl } from './world-route';
import { parseWorldFrame, type WorldView } from '../../src/features/world/protocol';
import en from '../../locales/en/translation.json';
import { WORLD } from '../../src/features/world/definition';
import { clickWorldProp } from '../fixtures/world-scene-navigation';
import { signIn } from './world-arcade-helpers';

const SYNTHESIS = 'INERT native dashboard summary, generated only after explicit acceptance.';
async function dashboardData(page: Page, holdFirst?: Promise<void>) {
  const briefing = homeBriefing();
  briefing.greeting.text = 'Welcome to your native dashboard';
  if (briefing.synthesis) briefing.synthesis.text = SYNTHESIS;
  const reads: string[] = [];
  let synthesis = 0;
  const payloads: Readonly<Record<string, unknown>> = {
    '/briefing/cards': { cards: briefing.cards, windows: briefing.windows },
    '/briefing/synthesis': { greeting: briefing.greeting, synthesis: briefing.synthesis },
    '/briefing/preferences': { hidden: [], order: HOME_ORDER },
    '/chat/users/me/statistics': HOME_STATISTICS,
    '/product/me/results': {
      cycle_start: '2026-10-01',
      useful_results: 37,
      actions: 19,
      automations: 11,
      commitments_closed: 7,
      measured: true,
    },
  };
  await page.route(
    /\/api\/v1\/(?:briefing\/(?:cards|synthesis|preferences)|chat\/users\/me\/statistics|product\/me\/results)(?:\?.*)?$/,
    async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
      reads.push(path);
      if (path === '/briefing/synthesis') {
        synthesis++;
        if (synthesis === 1 && holdFirst) await holdFirst;
      }
      await route.fulfill({ json: payloads[path] });
    }
  );
  return { reads, textCount: () => synthesis };
}
function observe(page: Page) {
  let view: WorldView | null = null;
  let stands = 0;
  let snapshots = 0;
  page.on('websocket', socket => {
    if (!socket.url().endsWith('/world/ws')) return;
    socket.on('framereceived', ({ payload }) => {
      const frame = parseWorldFrame(String(payload));
      if (frame.type !== 'snapshot') return;
      view = frame;
      snapshots++;
    });
    socket.on('framesent', ({ payload }) => {
      const frame: { type?: string; slot?: string | null } = JSON.parse(String(payload));
      if (frame.type === 'pose' && frame.slot === null) stands++;
    });
  });
  return {
    latest: () => view,
    stands: () => stands,
    /** Authoritative time: resolves after this many more server snapshots. */
    async after(count: number) {
      const target = snapshots + count;
      await expect.poll(() => snapshots).toBeGreaterThanOrEqual(target);
    },
  };
}
async function sit(page: Page) {
  await expect(page.locator('.world-admission')).not.toBeVisible();
  await expect(page.locator('.world-hud-toggle')).toBeAttached();
  const seat = WORLD.props.find(prop => prop.key === 'atrium-n');
  if (!seat) throw new Error('Missing atrium seat');
  await clickWorldProp(page, seat, id => en.world.zones[id as keyof typeof en.world.zones]);
  await expect(
    page.getByRole('button', { name: en.world.dashboard.stay, exact: true })
  ).toBeVisible({ timeout: 30000 });
}
async function accept(page: Page) {
  await page.getByRole('button', { name: en.world.dashboard.open, exact: true }).click();
}
async function reoffer(page: Page) {
  await revealWorldControls(page);
  await page.getByRole('button', { name: en.world.dashboard.title, exact: true }).click();
}
const panel = (page: Page) => page.locator('[data-world-native-panel]:visible');

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test(`confirmed table dashboard stays private, seated and single-purchase at ${viewport.width}px`, async ({
    browser,
    baseURL,
  }, info) => {
    if (!baseURL) throw new Error('Disposable proof required');
    const context = await browser.newContext({
      baseURL,
      viewport,
      serviceWorkers: 'block',
      reducedMotion: 'reduce',
    });
    try {
      await signIn(context, baseURL, 8);
      const page = await context.newPage();
      await installOfflineFonts(page);
      const data = await dashboardData(page);
      const actor = observe(page);
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.name));
      await openNativeWorld(page, 'Dashboard visitor', worldProofUrl(baseURL, 'en'));
      await enterWorld(page);
      await sit(page).catch(async error => {
        await info.attach('seat-at-failure.json', {
          body: JSON.stringify(actor.latest()),
          contentType: 'application/json',
        });
        throw error;
      });
      await expect.poll(() => actor.latest()?.you?.pose).toBe('atrium-n:0');
      expect(data.reads).toEqual([]);
      const stay = page.getByRole('button', { name: en.world.dashboard.stay, exact: true });
      await stay.click();
      await expect(stay).toHaveCount(0);
      // Judge the decline on frames the server sent after it, not on the last one before.
      await actor.after(10);
      expect(actor.latest()?.you?.pose).toBe('atrium-n:0');
      expect(actor.stands()).toBe(0);
      expect(data.reads).toEqual([]);
      await reoffer(page);
      await accept(page);
      await expect(page.getByText(SYNTHESIS, { exact: true })).toBeVisible();
      await expect(
        panel(page).getByRole('heading', { name: en.dashboard.results.title })
      ).toBeVisible();
      await expect(
        panel(page).getByRole('heading', { name: en.dashboard.statistics.consumption_title })
      ).toBeVisible();
      await actor.after(10);
      expect(data.textCount()).toBe(1);
      expect(
        (
          await new AxeBuilder({ page })
            .include('[data-world-native-panel]')
            .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
            .analyze()
        ).violations
      ).toEqual([]);
      await page.screenshot({ path: info.outputPath(`native-dashboard-${viewport.width}.png`) });
      const href = page.url();
      const boardRead = page.waitForRequest(request => {
        const url = new URL(request.url());
        return (
          url.pathname.endsWith('/workboard/tickets') && url.searchParams.get('assignee') === 'lia'
        );
      });
      await panel(page)
        .getByRole('link', { name: new RegExp(en.settings.workboard.tile_lia) })
        .click();
      await boardRead;
      if (viewport.width < 768)
        await panel(page)
          .locator('summary')
          .filter({ hasText: en.workboard.filters.title })
          .click();
      await expect(panel(page).getByLabel(en.workboard.filters.search)).toBeVisible();
      expect(page.url()).toBe(href);
      await panel(page).getByRole('button', { name: en.common.back, exact: true }).click();
      await expect(page.getByText(SYNTHESIS, { exact: true })).toBeVisible();
      expect(data.textCount()).toBe(1);
      await panel(page).getByRole('button', { name: en.common.close, exact: true }).click();
      await expect(page.locator('canvas.world-canvas')).toBeFocused();
      await actor.after(10);
      expect(actor.latest()?.you?.pose).toBe('atrium-n:0');
      expect(actor.stands()).toBe(0);
      await reoffer(page);
      await accept(page);
      await expect(page.getByText(SYNTHESIS, { exact: true })).toBeVisible();
      await actor.after(10);
      expect(data.textCount()).toBe(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
      expect(errors).toEqual([]);
    } finally {
      await context.close();
    }
  });
}

test('an interrupted initial dashboard text requires explicit retry after reopening', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Disposable proof required');
  let finishText!: () => void;
  const delayedText = new Promise<void>(resolve => {
    finishText = resolve;
  });
  const context = await browser.newContext({
    baseURL,
    serviceWorkers: 'block',
    reducedMotion: 'reduce',
  });
  try {
    await signIn(context, baseURL, 8);
    const page = await context.newPage();
    await installOfflineFonts(page);
    const data = await dashboardData(page, delayedText);
    await openNativeWorld(page, 'Interrupted dashboard visitor', worldProofUrl(baseURL, 'en'));
    await enterWorld(page);
    await sit(page);
    await accept(page);
    await expect.poll(data.textCount).toBe(1);
    await expect(panel(page).locator('#briefing-section-heading')).toBeVisible();
    await panel(page).getByRole('button', { name: en.common.close, exact: true }).click();
    finishText();
    await reoffer(page);
    await accept(page);
    await expect(
      page.getByText(en.dashboard.briefing.text_unavailable, { exact: true })
    ).toBeVisible();
    expect(data.textCount()).toBe(1);
    await panel(page).getByRole('button', { name: en.common.retry, exact: true }).click();
    await expect(page.getByText(SYNTHESIS, { exact: true })).toBeVisible();
    expect(data.textCount()).toBe(2);
    await expect(panel(page).locator('#briefing-section-heading')).toBeFocused();
  } finally {
    finishText();
    await context.close();
  }
});
