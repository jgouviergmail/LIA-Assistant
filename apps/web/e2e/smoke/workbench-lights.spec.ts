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
    calendar_window_max_events: 500,
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
    ...extra,
  };
}

const BRIDGE = {
  rooms: [
    { id: 'r1', name: 'Living room', light_ids: ['a', 'b', 'c', 'e'], on: true },
    { id: 'r2', name: 'Kitchen', light_ids: ['d'], on: false },
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
    { id: 's1', name: 'Read', room_id: 'r1', active: false },
    { id: 's2', name: 'Relax', room_id: 'r1', active: true },
  ],
};

async function playTheApi(
  mockApi: (routes: MockRoute[]) => Promise<void>,
  sent: Array<Record<string, unknown>>,
  refuse = false
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
    { url: '**/api/v1/workbench/lights', method: 'GET', json: BRIDGE },
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

/**
 * Owner requests (2026-10-31): rooms and lamps in alphabetical order — the room open by
 * default is the first of them — and a lamp's temperature and colour folded until opened.
 */
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
  await floor.getByText('Temperature and colour').click();
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
