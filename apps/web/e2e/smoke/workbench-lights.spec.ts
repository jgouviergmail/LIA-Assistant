/**
 * The « Tools » lights screen, hermetic (ADR-369, Task 9.2).
 *
 * The API is played by the spec: a bridge with three rooms, a colour lamp, an
 * ambiance lamp, a dimmable one and a plug, and the open room's scenes. Proven
 * at 1280 and 390 px, in light, dark and OLED: no horizontal scroll, axe clean
 * on the screen; a slider is sent on release only; a refused change shows the
 * previous value again with the refusal's own sentence; the keyboard opens a
 * room below lg and gets its card back when it closes; the lamps take the
 * columns the window holds, and a lamp alone stays a card.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Locator, Page } from '@playwright/test';

import { test, expect, waitForHydration } from '../fixtures';
import type { MockRoute } from '../fixtures/api-mock';
import { appConfig } from '../fixtures/dashboard-shell';
import { expectNoOverflow, prepareTheme } from './overflow-report';

const RAIL = {
  tools: ['mail', 'calendar', 'tasks', 'contacts', 'files', 'lights'].map(tool =>
    tool === 'lights'
      ? { tool, state: 'ready', provider: 'philips_hue', features: ['scenes'], bounds: {} }
      : { tool, state: 'not_connected', provider: null, features: [], bounds: {} }
  ),
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

function lamp(id: string, name: string, room: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    name,
    room_id: room,
    on: true,
    brightness: 70,
    supports_color: false,
    color_hex: null,
    mirek: null,
    mirek_min: null,
    mirek_max: null,
    reachable: null,
    ...extra,
  };
}

const BRIDGE = {
  rooms: [
    {
      id: 'r1',
      name: 'Living room',
      light_ids: ['a', 'b', 'c', 'e'],
      on: true,
      kind: 'room',
      supports_color: false,
      mirek_min: null,
      mirek_max: null,
    },
    {
      id: 'r2',
      name: 'Kitchen',
      light_ids: ['d'],
      on: false,
      kind: 'room',
      supports_color: false,
      mirek_min: null,
      mirek_max: null,
    },
  ],
  lights: [
    lamp('a', 'Floor lamp', 'r1', {
      brightness: 80,
      supports_color: true,
      color_hex: '#ffd59a',
      mirek: 366,
      mirek_min: 153,
      mirek_max: 500,
    }),
    lamp('b', 'Ceiling', 'r1', { brightness: 60, mirek: 300, mirek_min: 153, mirek_max: 454 }),
    lamp('c', 'Garland', 'r1', { brightness: 40 }),
    lamp('e', 'Plug', 'r1', { brightness: null }),
    lamp('d', 'Pendant', 'r2', { on: false, brightness: 100 }),
  ],
  scenes: [
    { id: 's1', name: 'Read', room_id: 'r1', active: false, dynamic: false, playing: false },
    { id: 's2', name: 'Relax', room_id: 'r1', active: true, dynamic: false, playing: false },
  ],
};

/** A zone across the rooms, a lamp the bridge cannot reach, a scene whose palette can play. */
const WHOLE_HOUSE = {
  rooms: [
    {
      id: 'r1',
      name: 'Living room',
      kind: 'room',
      light_ids: ['a', 'b'],
      on: true,
      supports_color: true,
      mirek_min: 153,
      mirek_max: 454,
    },
    {
      id: 'z1',
      name: 'Reading corner',
      kind: 'zone',
      light_ids: ['a'],
      on: true,
      supports_color: true,
      mirek_min: 153,
      mirek_max: 500,
    },
  ],
  lights: [
    lamp('a', 'Floor lamp', 'r1', {
      supports_color: true,
      color_hex: '#ffd59a',
      mirek: 366,
      mirek_min: 153,
      mirek_max: 500,
    }),
    lamp('b', 'Ceiling', 'r1', { reachable: false }),
  ],
  scenes: [
    { id: 's1', name: 'Aurora', room_id: 'r1', active: false, dynamic: true, playing: false },
  ],
};

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  sent: Array<Record<string, unknown>>,
  refuse = false,
  bridge: unknown = BRIDGE
) {
  await mockApi([
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: { ...appConfig.features, workbench_enabled: true },
        capabilities: { workbench: { enabled: true, family: 'work' } },
      },
    },
    { url: '**/api/v1/workbench', json: RAIL },
    { url: '**/api/v1/workbench/lights', method: 'GET', json: bridge },
    {
      url: '**/api/v1/workbench/lights/*',
      method: 'POST',
      handler: async route => {
        sent.push(route.request().postDataJSON() as Record<string, unknown>);
        if (refuse) {
          await route.fulfill({ status: 502, json: { detail: { code: 'provider_unavailable' } } });
          return;
        }
        await route.fulfill({ status: 204, body: '' });
      },
    },
  ]);
}

for (const sample of [
  { width: 1280, theme: 'light' },
  { width: 1280, theme: 'dark' },
  { width: 390, theme: 'oled' },
] as const) {
  test(`lights screen at ${sample.width}px in ${sample.theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await prepareTheme(page, sample.theme);
    await authenticate();
    await playTheApi(mockApi, []);

    await page.goto('/en/dashboard/tools/lights');
    await waitForHydration(page, 'button[role="switch"]');
    await expect(page.getByText('Living room').first()).toBeVisible();

    await expectNoOverflow(page, `${sample.width}px ${sample.theme}`);
    const scan = await new AxeBuilder({ page }).include('main').analyze();
    expect(scan.violations).toEqual([]);
  });
}

/** What a theme token paints, measured on the page as the browser computes it. */
const tokenOf = (page: Page, name: string) =>
  page.evaluate(token => {
    const probe = document.createElement('div');
    probe.style.backgroundColor = `var(--color-${token})`;
    document.body.append(probe);
    const painted = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return painted;
  }, name);

const paintedOf = (target: Locator) =>
  target.evaluate(node => getComputedStyle(node).backgroundColor);

/** How bright a token paints, read from a pixel: its computed colour's notation varies. */
const brightnessOf = (page: Page, token: string) =>
  page.evaluate(name => {
    const probe = document.createElement('div');
    probe.style.backgroundColor = `var(--color-${name})`;
    document.body.append(probe);
    const canvas = document.createElement('canvas').getContext('2d');
    if (!canvas) throw new Error('no canvas');
    canvas.fillStyle = getComputedStyle(probe).backgroundColor;
    probe.remove();
    canvas.fillRect(0, 0, 1, 1);
    const [red = 0, green = 0, blue = 0] = canvas.getImageData(0, 0, 1, 1).data;
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  }, token);

/**
 * Owner requests (2026-11-05, 2026-11-06): what is lit keeps the card's material, and what is off
 * stands apart from the page: under it in a light theme, above it in a dark one, down to the true
 * black of OLED, where it still never outshines what is lit.
 */
for (const theme of ['light', 'dark', 'oled'] as const) {
  test(`what is off stands apart from the page and from what is lit, in ${theme}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await prepareTheme(page, theme);
    await authenticate();
    await playTheApi(mockApi, []);

    await page.goto('/en/dashboard/tools/lights');
    await waitForHydration(page, 'button[role="switch"]');
    const room = (name: string) =>
      page.locator('[data-lit]').filter({ has: page.getByRole('link', { name }) });
    const unlit = await tokenOf(page, 'unlit');
    const card = await tokenOf(page, 'card');
    expect(unlit).not.toBe(card);

    await expect(room('Kitchen')).toHaveAttribute('data-lit', 'false');
    expect(await paintedOf(room('Kitchen'))).toBe(unlit);
    expect(await paintedOf(room('Living room'))).toBe(card);
    expect(await paintedOf(page.getByRole('group', { name: 'Pendant' }))).toBe(unlit);

    await page.getByRole('link', { name: /Living room/ }).click();
    expect(await paintedOf(page.getByRole('group', { name: 'Floor lamp' }))).toBe(card);

    const ground = await brightnessOf(page, 'background');
    const off = await brightnessOf(page, 'unlit');
    const lit = await brightnessOf(page, 'card');
    if (theme === 'light') {
      expect(off, 'under the page').toBeLessThan(ground);
    } else {
      expect(off, 'above the page').toBeGreaterThan(ground);
      expect(off, 'under what is lit').toBeLessThan(lit);
    }
  });
}

/**
 * Owner requests (2026-10-31): rooms and lamps in alphabetical order — the room open by
 * default is the first of them — and a lamp's temperature and colour folded until opened.
 */
/** Owner request (2026-11-06): the two columns start on one line. */
test('from a large screen the first room’s card starts where the room’s title does', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, [], false, WHOLE_HOUSE);

  await page.goto('/en/dashboard/tools/lights');
  await waitForHydration(page, 'main');
  const firstRoom = page.locator('[aria-current="true"][data-lit]').first();
  const title = page.getByRole('heading', { name: 'Living room' });
  await expect(title).toBeVisible();

  const [room, name] = await Promise.all([firstRoom.boundingBox(), title.boundingBox()]);
  expect(Math.abs((room?.y ?? 0) - (name?.y ?? 1))).toBeLessThanOrEqual(1);
  await expect(page.getByText('Brightness', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('slider', { name: /Brightness of/ }).first()).toBeVisible();
});

/** Owner request (2026-11-06): the question stands right after the room's name, at any width. */
for (const width of [390, 1280]) {
  test(`asking LIA about a room stands beside its name at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width, height: 844 });
    await authenticate({ timezone: 'Europe/Paris' });
    await playTheApi(mockApi, [], false, WHOLE_HOUSE);

    await page.goto('/en/dashboard/tools/lights?room=r1');
    await waitForHydration(page, 'main');
    const name = page.getByRole('heading', { name: 'Living room' });
    const ask = page.getByRole('button', { name: 'Ask LIA' });
    await expect(ask).toBeVisible();

    const [title, act] = await Promise.all([name.boundingBox(), ask.boundingBox()]);
    expect((act?.x ?? 0) - ((title?.x ?? 0) + (title?.width ?? 0))).toBeLessThanOrEqual(8);
  });
}

test('a zone, a lamp that does not answer and a scene in motion hold on a phone', async ({
  page,
  authenticate,
  mockApi,
}) => {
  const sent: Array<Record<string, unknown>> = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate({ timezone: 'Europe/Paris' });
  await playTheApi(mockApi, sent, false, WHOLE_HOUSE);

  await page.goto('/en/dashboard/tools/lights');
  await waitForHydration(page, 'main');
  const zone = page.getByRole('link', { name: /Reading corner/ });
  await expect(zone).toContainText('Zone');
  // A lamp that does not answer says so on its own card, never on its room's.
  await expect(page.getByRole('link', { name: /Living room/ })).not.toContainText('answering');

  await page.getByRole('switch', { name: 'Turn on “Reading corner”' }).click();
  await expect.poll(() => sent.at(-1)).toEqual({ room_id: 'z1', kind: 'zone', on: false });

  await page.getByText('Customize').first().click();
  await expect(page.getByRole('slider', { name: 'Temperature' }).first()).toBeVisible();
  await expectNoOverflow(page, 'lights with a zone at 390px');

  await page.goto('/en/dashboard/tools/lights?room=r1');
  await waitForHydration(page, 'main');
  const ceiling = page.getByRole('group', { name: 'Ceiling' });
  await expect(ceiling.getByText('This lamp is not answering')).toBeVisible();
  await expect(ceiling.getByRole('switch')).toBeDisabled();
  const silentName = await ceiling
    .getByText('Ceiling', { exact: true })
    .evaluate(name => getComputedStyle(name).color);
  const ground = await page
    .getByRole('group', { name: 'Floor lamp' })
    .getByText('Floor lamp', { exact: true })
    .evaluate(name => getComputedStyle(name).color);
  expect(silentName, 'the name of a lamp that does not answer is greyed').not.toBe(ground);

  await page.getByRole('button', { name: 'Play “Aurora” in motion' }).first().click();
  await expect.poll(() => sent.at(-1)).toEqual({ scene_id: 's1', play: true });

  await expectNoOverflow(page, 'a room at 390px');
  const scan = await new AxeBuilder({ page }).include('main').analyze();
  expect(scan.violations).toEqual([]);
});

test('rooms and lamps come in alphabetical order, the tone folded until opened', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate();
  await playTheApi(mockApi, []);

  await page.goto('/en/dashboard/tools/lights');
  await waitForHydration(page, 'button[role="switch"]');
  await expect(page.getByRole('heading', { level: 2, name: 'Kitchen' })).toBeVisible();
  const rooms = await page.getByRole('link', { name: /^(Kitchen|Living room)/ }).allTextContents();
  expect(rooms.map(text => text.slice(0, 7))).toEqual(['Kitchen', 'Living ']);

  await page.goto('/en/dashboard/tools/lights?room=r1');
  await waitForHydration(page, 'button[role="switch"]');
  const floor = page.getByRole('group', { name: 'Floor lamp' });
  await expect(floor).toBeVisible();
  const lamps = await page
    .getByRole('group')
    .evaluateAll(groups => groups.map(group => group.getAttribute('aria-label') ?? ''));
  expect(lamps.filter(name => ['Ceiling', 'Floor lamp', 'Garland', 'Plug'].includes(name))).toEqual(
    ['Ceiling', 'Floor lamp', 'Garland', 'Plug']
  );

  await expect(floor.getByRole('slider', { name: 'Temperature' })).toHaveCount(0);
  await floor.getByText('Customize').click();
  await expect(floor.getByRole('slider', { name: 'Temperature' })).toBeVisible();
  await expect(floor.getByLabel('Colour')).toHaveValue('#ffd59a');
});

/**
 * Owner request (2026-11-04): the lamps use the width the tools were given — as many
 * columns as hold a 24 rem card, where a fixed two drew 766 px cards at 1920 px.
 */
for (const sample of [
  { width: 1100, columns: 1 },
  { width: 1280, columns: 2 },
  { width: 1920, columns: 3 },
  { width: 2560, columns: 4 },
] as const) {
  test(`four lamps stand in ${sample.columns} column(s) at ${sample.width}px`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.setViewportSize({ width: sample.width, height: 900 });
    await authenticate();
    await playTheApi(mockApi, []);

    await page.goto('/en/dashboard/tools/lights?room=r1');
    await waitForHydration(page, 'button[role="switch"]');
    await expect(page.getByRole('group', { name: 'Floor lamp' })).toBeVisible();

    const columns = new Set<number>();
    for (const name of ['Ceiling', 'Floor lamp', 'Garland', 'Plug']) {
      const card = await page.getByRole('group', { name, exact: true }).boundingBox();
      if (!card) throw new Error(`${name} is not drawn`);
      columns.add(Math.round(card.x));
    }
    expect(columns.size).toBe(sample.columns);
  });
}

test('a lamp alone in its room stays a card on the widest window', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 2560, height: 900 });
  await authenticate();
  await playTheApi(mockApi, []);

  await page.goto('/en/dashboard/tools/lights?room=r2');
  await waitForHydration(page, 'button[role="switch"]');
  const card = await page.getByRole('group', { name: 'Pendant' }).boundingBox();
  if (!card) throw new Error('the lamp is not drawn');

  expect(card.width).toBeLessThan(600);
});

test('a slider is sent on release, and a refused one shows its previous value', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await authenticate();
  const sent: Array<Record<string, unknown>> = [];
  await playTheApi(mockApi, sent, true);

  // The room is named: the one open by default is the first in alphabetical order.
  await page.goto('/en/dashboard/tools/lights?room=r1');
  await waitForHydration(page, 'button[role="switch"]');
  const slider = page.getByRole('group', { name: 'Floor lamp' }).getByRole('slider', {
    name: 'Brightness',
  });
  await slider.focus();
  await page.keyboard.press('ArrowLeft');

  await expect(page.getByText('The service is not answering: try again later.')).toBeVisible();
  expect(sent).toEqual([{ light_id: 'a', brightness: 79 }]);
  await expect(slider).toHaveValue('80');
});

test('the keyboard opens a room below lg and gets its card back', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticate();
  await playTheApi(mockApi, []);

  await page.goto('/en/dashboard/tools/lights');
  await waitForHydration(page, 'button[role="switch"]');
  const room = page.getByRole('link', { name: /Living room/ });
  await room.focus();
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: 'All rooms' })).toBeFocused();
  await expectNoOverflow(page, 'room at 390px');
  await page.keyboard.press('Enter');

  await expect(page.getByRole('link', { name: /Living room/ })).toBeFocused();
});
