/** Real browser → Next BFF → native world router → isolated SQL + Redis. */
import { test, expect, type Browser, type BrowserContext, type Page } from './fixtures';
import AxeBuilder from '@axe-core/playwright';
import { installOfflineFonts } from '../fixtures/offline-fonts';
import { worldProofUrl } from './world-route';
import { openNativeWorld, enterWorld } from '../fixtures/world-admission';

interface Actor {
  alias: string;
  x: number;
  y: number;
}
interface Evidence {
  status: string;
  epoch: string;
  controlling: boolean;
  offer: number | null;
  actors: Actor[];
  you: Actor | null;
}
interface Visitor {
  index: number;
  context: BrowserContext;
  page: Page;
  latest(): Evidence | null;
  errors: string[];
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
function actor(value: unknown): Actor | null {
  if (
    !record(value) ||
    typeof value.alias !== 'string' ||
    !record(value.position) ||
    typeof value.position.x !== 'number' ||
    typeof value.position.y !== 'number'
  )
    return null;
  return { alias: value.alias, x: value.position.x, y: value.position.y };
}
const leave = [
  'Quitter le monde',
  'Leave the world',
  'Welt verlassen',
  'Salir del mundo',
  'Esci dal mondo',
  '离开世界',
];

test('five real accounts share positions; a sixth waits; duplicate control is explicit and FIFO entry stays private', async ({
  browser,
  baseURL,
}, info) => {
  // Six cold browser contexts, a duplicate tab and axe share this bounded
  // budget. App admission/lease/timeouts remain unchanged.
  test.setTimeout(180000);
  if (!baseURL) throw new Error('Missing disposable preview URL');
  const proofBaseURL = baseURL;
  const origin = new URL(proofBaseURL).origin;
  const visitors: Visitor[] = [];
  const extraBrowsers: Browser[] = [];
  const escaped: string[] = [];
  let stage = 'initializing';
  let primaryFailure = false;
  async function open(index: number, context?: BrowserContext): Promise<Visitor> {
    stage = `opening account ${index}`;
    // Each person has a foreground document, as on independent devices. The
    // intentional duplicate controller alone shares the first account's context.
    const engine =
      context || index === 1 ? browser : await browser.browserType().launch({ headless: true });
    if (!context && engine !== browser) extraBrowsers.push(engine);
    const owned =
      context ??
      (await engine.newContext({
        baseURL,
        viewport: { width: 1280, height: 800 },
        serviceWorkers: 'block',
      }));
    if (!context)
      await owned.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin === origin) return route.continue();
        escaped.push(url.origin);
        return route.abort();
      });
    const page = await owned.newPage();
    await installOfflineFonts(page);
    let latest: Evidence | null = null;
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.name));
    page.on('websocket', socket => {
      if (!socket.url().endsWith('/api/v1/world/ws')) return;
      socket.on('framereceived', event => {
        try {
          const data: unknown = JSON.parse(String(event.payload));
          if (!record(data) || data.type !== 'snapshot') return;
          const forbidden = [
            'account_id',
            'controller',
            'binding',
            'language',
            'memories',
            'profile',
          ];
          for (const key of forbidden)
            if (JSON.stringify(data).includes('"' + key + '"')) errors.push('private-field:' + key);
          if (
            typeof data.status !== 'string' ||
            typeof data.epoch !== 'string' ||
            typeof data.controlling !== 'boolean' ||
            !Array.isArray(data.actors)
          ) {
            errors.push('invalid-snapshot');
            return;
          }
          latest = {
            status: data.status,
            epoch: data.epoch,
            controlling: data.controlling,
            offer: typeof data.offer_until === 'number' ? data.offer_until : null,
            actors: data.actors.map(actor).filter((item): item is Actor => item !== null),
            you: actor(data.you),
          };
        } catch {
          errors.push('invalid-json');
        }
      });
    });
    const visitor = { index, context: owned, page, latest: () => latest, errors };
    visitors.push(visitor);
    if (!context) {
      const login = await owned.request.post('/api/v1/world-proof/session', {
        headers: { Origin: origin },
        data: { index },
      });
      expect(login.status()).toBe(200);
    }
    const lng = ['fr', 'en', 'de', 'es', 'it', 'zh'][index - 1];
    await openNativeWorld(page, `Player ${index}`, worldProofUrl(proofBaseURL, lng));
    await enterWorld(page);
    await expect.poll(() => latest?.status).toBe(index === 6 ? 'waiting' : 'active');
    console.info(`Native capacity: account ${index} admitted or queued`);
    return visitor;
  }
  try {
    for (let index = 1; index <= 6; index++) await open(index);
    stage = 'shared movement';
    const [first, second, , , , sixth] = visitors;
    expect(new Set(visitors.map(visitor => visitor.latest()?.epoch)).size).toBe(1);
    expect(sixth.latest()?.actors).toEqual([]);
    expect(sixth.latest()?.you).toBeNull();
    const before = first.latest()?.you;
    if (!before) throw new Error('Missing admitted actor');
    await first.page.bringToFront();
    // A foreground page can be recovering while its last socket snapshot is still active.
    // Wait for the native authority dialog to close before exercising real keyboard input.
    await expect(first.page.getByRole('dialog')).toBeHidden();
    const canvas = first.page.locator('canvas.world-canvas');
    await canvas.focus();
    await expect(canvas).toBeFocused();
    await first.page.keyboard.down('ArrowRight');
    try {
      await expect.poll(() => (first.latest()?.you?.x ?? 0) - before.x).toBeGreaterThan(0.3);
    } finally {
      await first.page.keyboard.up('ArrowRight');
    }
    await expect
      .poll(() => {
        const observed = second.latest()?.actors.find(actor => actor.alias === 'Player 1')?.x;
        const actual = first.latest()?.you?.x;
        return observed === undefined || actual === undefined
          ? Infinity
          : Math.abs(observed - actual);
      })
      .toBeLessThan(0.05);

    const duplicate = await open(1, first.context);
    stage = 'explicit controller takeover';
    await expect.poll(() => duplicate.latest()?.controlling).toBe(false);
    await duplicate.page
      .getByRole('button', { name: 'Piloter depuis cet onglet', exact: true })
      .click();
    await expect.poll(() => duplicate.latest()?.controlling).toBe(true);
    await expect.poll(() => first.latest()?.controlling).toBe(false);
    await duplicate.page.getByRole('button', { name: leave[0], exact: true }).click();
    await expect(duplicate.page.locator('.world-admission')).toBeVisible();
    stage = 'FIFO offer';
    await expect.poll(() => sixth.latest()?.offer).not.toBeNull();
    await sixth.page.getByRole('button', { name: '加入世界', exact: true }).click();
    await expect.poll(() => sixth.latest()?.status).toBe('active');
    stage = 'phone accessibility';

    await second.page.setViewportSize({ width: 390, height: 844 });
    await second.page.bringToFront();
    expect(
      await second.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
    ).toBe(true);
    const scan = await new AxeBuilder({ page: second.page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    const report = scan.violations.map(violation => ({
      id: violation.id,
      nodes: violation.nodes.map(node => ({ target: node.target, summary: node.failureSummary })),
    }));
    await info.attach('world-native-axe.json', {
      body: JSON.stringify(report),
      contentType: 'application/json',
    });
    expect(report, JSON.stringify(report)).toEqual([]);
    await second.page.screenshot({ path: info.outputPath('world-native-mobile.png') });
    for (const visitor of visitors) expect(visitor.errors).toEqual([]);
    expect(escaped).toEqual([]);
  } catch (error) {
    primaryFailure = true;
    await info.attach('capacity-stage.json', {
      contentType: 'application/json',
      body: JSON.stringify({
        stage,
        visitors: visitors.map(visitor => ({
          index: visitor.index,
          status: visitor.latest()?.status,
          controlling: visitor.latest()?.controlling,
          observedActors: visitor.latest()?.actors.length,
          errors: visitor.errors,
        })),
      }),
    });
    console.info(`Native capacity interrupted at: ${stage}`);
    throw error;
  } finally {
    const releaseVisitor = async (visitor: Visitor) => {
      if (visitor.page.isClosed()) return;
      await visitor.page.bringToFront();
      await visitor.page.keyboard.press('Escape');
      const button = visitor.page
        .getByRole('button', {
          name: leave[visitor.index - 1],
          exact: true,
        })
        .last();
      if (await button.isVisible()) await button.click({ timeout: 3000 });
    };
    // Foreground interactions share browser/window focus; close each person's UI in order.
    const results: PromiseSettledResult<void>[] = [];
    for (const visitor of visitors)
      results.push(...(await Promise.allSettled([releaseVisitor(visitor)])));
    results.push(
      ...(await Promise.allSettled(
        [...new Set(visitors.map(visitor => visitor.context))].map(context => context.close())
      ))
    );
    results.push(...(await Promise.allSettled(extraBrowsers.map(engine => engine.close()))));
    const failures = results.filter(result => result.status === 'rejected');
    if (failures.length && !primaryFailure) {
      throw new AggregateError(
        failures.map(result => result.reason),
        'Native capacity cleanup failed'
      );
    }
  }
});
