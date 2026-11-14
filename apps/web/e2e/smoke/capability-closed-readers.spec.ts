/**
 * Outside the settings index, nobody asks a router its switch closed (ADR-280).
 *
 * Three surfaces read a capability from a place no section gate covers: the
 * chat (LIA's mood, the skills of the « / » menu, the in-call band — the band
 * on every turn), a routine's form (the personal MCP servers it may
 * pre-approve) and the shortcuts dock (a pinned section). Under the operator's
 * switch each sent a request whose only possible answer was a refusal, or drew
 * a link to a section that is not there.
 *
 * Each journey closes ONE capability and watches the others still being read
 * on the same page: « nothing was asked » only proves something beside « it IS
 * asked where it is offered », and a reader wired to the wrong capability
 * would otherwise go unseen.
 */
import { test, expect, chatRoutes, type MockRoute } from '../fixtures';
import { configRoute, label, watchClosedRouters } from '../fixtures/capability-doors';

const APPEARS_COLD = 60_000;
/** Long enough for a deferred read to leave, had one been queued. */
const QUIET_MS = 2_500;

/** Capability → what the chat asks of its router where the instance offers it. */
const CHAT_READS = {
  psyche: ['/api/v1/psyche/settings', '/api/v1/psyche/state'],
  skills: ['/api/v1/skills'],
  telephony: ['/api/v1/telephony/calls'],
} as const;
type ChatCapability = keyof typeof CHAT_READS;
const CHAT_CAPABILITIES = Object.keys(CHAT_READS) as ChatCapability[];
const CHAT_ROUTER = /^\/api\/v1\/(psyche|skills|telephony)(\/|$)/;

/** The distinct requests the chat sent to those three routers, sorted. */
const chatReads = (asked: readonly string[]) =>
  [...new Set(asked.filter(path => CHAT_ROUTER.test(path)))].sort();
/** What the chat must ask once `closed` is switched off: the readers of the others. */
const readsWithout = (closed: readonly ChatCapability[]) =>
  CHAT_CAPABILITIES.filter(capability => !closed.includes(capability))
    .flatMap(capability => [...CHAT_READS[capability]])
    .sort();

const CHAT_ROUTES: MockRoute[] = [
  ...chatRoutes([]),
  {
    url: '**/api/v1/psyche/settings',
    json: {
      psyche_enabled: true,
      psyche_display_avatar: true,
      psyche_sensitivity: 50,
      psyche_stability: 50,
    },
  },
  { url: '**/api/v1/skills', json: { skills: [], total: 0 } },
];

const ROUTINE_ROUTES: MockRoute[] = [
  { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
  { url: '**/api/v1/mcp/admin-servers', json: [] },
  { url: '**/api/v1/mcp/servers', json: { servers: [], total: 0 } },
];

test.describe('the chat — a capability the operator switched off', () => {
  for (const closed of [
    ['psyche'],
    ['skills'],
    ['telephony'],
    ['psyche', 'skills', 'telephony'],
    [],
  ] as const satisfies readonly (readonly ChatCapability[])[]) {
    const title =
      closed.length === 0
        ? 'reads the psyche, the skills and telephony where all three are offered'
        : `asks nothing of ${closed.join(', ')} once closed, and still reads what is offered`;
    test(title, async ({ page, authenticate, mockApi }) => {
      const asked = watchClosedRouters(page);
      await authenticate({ language: 'fr' });
      await mockApi([...CHAT_ROUTES, configRoute(closed)]);
      await page.goto('/fr/dashboard/chat');

      await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: APPEARS_COLD });
      // The readers still offered have left: the page is past the point where
      // the closed one would have asked.
      await expect
        .poll(() => chatReads(asked), { timeout: APPEARS_COLD })
        .toEqual(expect.arrayContaining(readsWithout(closed)));
      await page.waitForTimeout(QUIET_MS);

      expect(chatReads(asked), 'the chat reads exactly what the instance offers').toEqual(
        readsWithout(closed)
      );
    });
  }

  test('still reads the psyche and telephony from a server that publishes no capability map', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The `/config` every other journey of this suite runs under, and that of
    // an API older than the switches: a capability with no published
    // deployment flag was always offered, so LIA's mood is still read, and
    // telephony's flag is one this configuration publishes. The skills carry
    // a flag it does not publish: not offered.
    const asked = watchClosedRouters(page);
    await authenticate({ language: 'fr' });
    await mockApi(CHAT_ROUTES);
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: APPEARS_COLD });
    await expect
      .poll(() => chatReads(asked), { timeout: APPEARS_COLD })
      .toEqual(expect.arrayContaining(readsWithout(['skills'])));
    await page.waitForTimeout(QUIET_MS);

    expect(chatReads(asked)).toEqual(readsWithout(['skills']));
  });
});

test.describe('a routine form — the personal MCP servers the instance does not offer', () => {
  for (const [title, closed, config] of [
    ['asks the instance servers alone under the switch', true, configRoute(['mcp'])],
    [
      'asks the instance servers alone where no router is mounted for the personal ones',
      true,
      configRoute([], { mcp_user_enabled: false }),
    ],
    ['asks both lists where the personal servers are offered', false, configRoute([])],
  ] as const) {
    test(title, async ({ page, authenticate, mockApi }) => {
      const mcp: string[] = [];
      page.on('request', request => {
        const { pathname } = new URL(request.url());
        if (pathname.startsWith('/api/v1/mcp/')) mcp.push(pathname);
      });
      await authenticate({ language: 'fr' });
      await mockApi([...ROUTINE_ROUTES, config]);
      await page.goto('/fr/dashboard/settings?section=scheduled-actions');

      await expect(page.locator('#settings-section-scheduled-actions')).toBeVisible({
        timeout: APPEARS_COLD,
      });
      // The instance servers' router carries no such guard: still read.
      await expect
        .poll(() => mcp.includes('/api/v1/mcp/admin-servers'), { timeout: APPEARS_COLD })
        .toBe(true);
      if (closed) {
        await page.waitForTimeout(QUIET_MS);
        expect([...new Set(mcp)]).toEqual(['/api/v1/mcp/admin-servers']);
      } else {
        await expect
          .poll(() => [...new Set(mcp)].sort(), { timeout: APPEARS_COLD })
          .toEqual(['/api/v1/mcp/admin-servers', '/api/v1/mcp/servers']);
      }
    });
  }
});

test.describe('the shortcuts dock — a pinned section the operator closed', () => {
  const PINNED = ['theme', 'journals', 'image-generation'];
  const DOCK = /raccourcis/i;

  test('draws no link to it, and keeps the others in their order', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // It led to « this section is not showing here », and the picker — which
    // lists what the shell shows — offered no box to take it away.
    await authenticate({ language: 'fr', settings_shortcuts: PINNED });
    await mockApi([configRoute(['journals'])]);
    await page.goto('/fr/dashboard/settings');

    const links = page.getByRole('navigation', { name: DOCK }).getByRole('link');
    await expect(links).toHaveCount(2, { timeout: APPEARS_COLD });
    await expect(links.first()).toHaveAccessibleName(label('settings.theme.title'));
    await expect(links.nth(1)).toHaveAccessibleName(label('settings.image_generation.title'));
  });

  test('draws every pinned section where nothing is closed', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr', settings_shortcuts: PINNED });
    await mockApi([configRoute([])]);
    await page.goto('/fr/dashboard/settings');

    const links = page.getByRole('navigation', { name: DOCK }).getByRole('link');
    await expect(links).toHaveCount(3, { timeout: APPEARS_COLD });
    await expect(links.nth(1)).toHaveAccessibleName(label('journals.title'));
  });

  test('counts in the picker what the dock draws', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr', settings_shortcuts: PINNED });
    await mockApi([
      configRoute(['journals']),
      {
        url: '**/api/v1/users/me/settings-shortcuts',
        method: 'GET',
        json: { shortcuts: PINNED, max_count: 3 },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=my-shortcuts');

    const picker = page.locator('#settings-section-my-shortcuts');
    await expect(picker).toBeVisible({ timeout: APPEARS_COLD });
    // Three stored, two drawn, a cap of three: two are counted and a third box is takeable.
    await expect(picker.getByRole('checkbox', { checked: true })).toHaveCount(2);
    await expect(picker.getByText(label('settings.my_shortcuts.limit_reached'))).toHaveCount(0);
    await expect(
      picker.getByRole('checkbox', { name: label('settings.font.title'), exact: true })
    ).not.toHaveAttribute('aria-disabled', 'true');
  });
});
