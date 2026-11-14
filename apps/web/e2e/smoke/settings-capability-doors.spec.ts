/**
 * A settings section whose routes the operator closed is not a door (ADR-280).
 *
 * Seven routers refuse under their switch every route their section reads: the
 * channels, the psyche, the journals, the skills, the personal MCP servers,
 * the knowledge spaces and image generation. Their sections could show nothing
 * but that refusal — and did: listed in the rail, opened on an error whose
 * retry could never work. Telephony's sections show RECORDS instead — a stored
 * number, the history of the calls — which the API serves under the switch.
 *
 * Unit tests pin the index and the pane. Only a browser proves what a reader
 * meets: the rail lists none of them, a stale link says so honestly, and NO
 * request leaves for a closed router. One section depends on the DEVICE
 * instead: the haptic feedback, which the WebKit of an iPhone cannot offer.
 */
import type { Route } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';
import {
  configRoute,
  label,
  SWITCHED,
  watchClosedRouters,
  type Switched,
} from '../fixtures/capability-doors';

/** Capability → the titles of the sections its switch closes, as the rail prints them. */
const SECTIONS: Readonly<Record<Switched, readonly string[]>> = {
  channels: [label('settings.channels.title')],
  psyche: [label('psyche.title')],
  journals: [label('journals.title')],
  skills: [label('settings.skills.title')],
  mcp: [label('settings.mcp.title')],
  rag_spaces: [label('settings.rag_spaces.title')],
  image_generation: [label('settings.image_generation.title')],
  // Its two sections show RECORDS — a stored number, the history of the calls —
  // that the API serves under the switch: they stay (see the journey below).
  telephony: [],
};
const ADMIN_SECTIONS = {
  skills: label('settings.skills.admin_title'),
  rag_spaces: label('settings.admin.ragSpaces.title'),
} as const;

const NAV_LABEL = label('settings.shell.nav_label');
const HAPTICS = label('settings.haptics.title');
const TELEPHONY_GROUP = new RegExp(
  `${label('settings.connectors.available_telephony')}|${label('settings.connectors.connected_telephony')}`
);
const APPEARS_COLD = 60_000;

const ROUTES: MockRoute[] = [
  { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('settings — a capability the operator switched off', () => {
  test('lists none of its sections, mounts none, and asks none of its routes', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const asked = watchClosedRouters(page);
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, configRoute(SWITCHED)]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    // The rail is drawn: what no switch governs is there.
    await expect(nav.getByRole('button', { name: 'Apparence' })).toBeVisible();
    for (const title of Object.values(SECTIONS).flat())
      await expect(nav.getByRole('button', { name: title, exact: true }), title).toHaveCount(0);

    // A stale link — a bookmark, a pinned shortcut — says so and loads nothing.
    for (const [section, title] of [
      ['journals', SECTIONS.journals[0]],
      ['image-generation', SECTIONS.image_generation[0]],
    ] as const) {
      await page.goto(`/fr/dashboard/settings?section=${section}`);
      await expect(page.getByTestId('empty-state'), section).toContainText(title, {
        timeout: APPEARS_COLD,
      });
      await expect(page.locator('[id^="settings-section-"]'), section).toHaveCount(0);
    }

    expect(asked, 'requests sent to a router its switch closed').toEqual([]);
  });

  for (const closed of ['journals', 'image_generation'] as const) {
    test(`closes ${closed} alone: its sections go, every other stays`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: 'fr' });
      await mockApi([...ROUTES, configRoute([closed])]);
      await page.goto('/fr/dashboard/settings');

      const nav = page.getByRole('navigation', { name: NAV_LABEL });
      await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
      for (const title of SECTIONS[closed])
        await expect(nav.getByRole('button', { name: title, exact: true }), title).toHaveCount(0);
      for (const capability of SWITCHED) {
        if (capability === closed) continue;
        for (const title of SECTIONS[capability])
          await expect(nav.getByRole('button', { name: title, exact: true }), title).toBeVisible();
      }
    });
  }

  test('withdraws the administration section of a capability from its own administrator', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The administrator who switched the skills off is the one who would open
    // « System skills » on a refusal.
    await authenticate({ language: 'fr', is_superuser: true });
    await mockApi([...ROUTES, configRoute(['skills'])]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    await expect(
      nav.getByRole('button', { name: ADMIN_SECTIONS.rag_spaces, exact: true })
    ).toBeVisible();
    await expect(nav.getByRole('button', { name: ADMIN_SECTIONS.skills, exact: true })).toHaveCount(
      0
    );
    await expect(nav.getByRole('button', { name: SECTIONS.skills[0], exact: true })).toHaveCount(0);
  });

  test('offers no telephony connection under the switch, and offers it where telephony is offered', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Connecting a key creates an agent at the vendor: an act of the
    // capability, which its router refuses under the switch.
    const asked = watchClosedRouters(page);
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, configRoute(['telephony'])]);
    await page.goto('/fr/dashboard/settings?section=connectors');

    const section = page.locator('#settings-section-connectors');
    await expect(section).toBeVisible({ timeout: APPEARS_COLD });
    await expect(
      section.getByRole('button', { name: label('settings.connectors.available_google') })
    ).toBeVisible();
    await expect(section.getByRole('button', { name: TELEPHONY_GROUP })).toHaveCount(0);
    expect(asked.filter(path => path.includes('/telephony'))).toEqual([]);

    // The same page on an instance that offers telephony: the group is there.
    await mockApi([configRoute([])]);
    await page.goto('/fr/dashboard/settings?section=connectors');

    await expect(page.locator('#settings-section-connectors')).toBeVisible({
      timeout: APPEARS_COLD,
    });
    await expect(
      page.getByRole('button', { name: label('settings.connectors.available_telephony') })
    ).toBeVisible();
  });

  test('keeps a stored telephony key removable under the switch', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // A switch removes the capability, never the record: the key is the
    // person's, and the API serves its removal outside the switch.
    let stored = true;
    const removals: string[] = [];
    const telephonyKey = {
      id: '00000000-0000-4000-8000-00000000te1e',
      connector_type: 'elevenlabs_telephony',
      status: 'active',
      created_at: '2026-11-12T08:00:00Z',
    };
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      configRoute(['telephony']),
      {
        url: /\/api\/v1\/connectors(?:\?fresh=true)?$/,
        handler: (route: Route) =>
          route.fulfill({ json: { connectors: stored ? [telephonyKey] : [] } }),
      },
      {
        url: '**/api/v1/telephony/connector',
        method: 'DELETE',
        handler: async (route: Route) => {
          removals.push(route.request().method());
          stored = false;
          await route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=connectors');

    const section = page.locator('#settings-section-connectors');
    await expect(section).toBeVisible({ timeout: APPEARS_COLD });
    const group = section.getByRole('button', {
      name: label('settings.connectors.connected_telephony'),
    });
    await expect(group).toBeVisible();
    // Nothing to connect under the switch: the wizard is the capability.
    await expect(
      section.getByRole('button', { name: label('settings.connectors.available_telephony') })
    ).toHaveCount(0);

    await group.click();
    await section.getByTitle(label('settings.connectors.google.disconnect')).click();

    await expect.poll(() => removals).toEqual(['DELETE']);
    await expect(section.getByRole('button', { name: TELEPHONY_GROUP })).toHaveCount(0);
  });

  test('keeps a stored phone number readable and removable under the switch, and offers no call', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The number is the person's record: the API serves its reading and its
    // removal outside the switch. Declaring one, verifying it by a call and
    // tuning owner calls are the capability, and are not offered.
    let stored = true;
    const removals: string[] = [];
    const identity = () => ({
      phone_number: stored ? '+33612345678' : null,
      verified: stored,
      verified_at: stored ? '2026-11-01T09:00:00Z' : null,
      rich_context_enabled: true,
      disabled_domains: [],
      available_domains: ['email', 'event'],
      verification_pending: false,
      call_mode: 'delegated',
      call_mode_effective: 'delegated',
      live_available: false,
      live_unavailable_reason: null,
    });
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      configRoute(['telephony']),
      {
        url: '**/api/v1/telephony/identity',
        method: 'GET',
        handler: (route: Route) => route.fulfill({ json: identity() }),
      },
      {
        url: '**/api/v1/telephony/identity/number',
        method: 'DELETE',
        handler: async (route: Route) => {
          removals.push(route.request().method());
          stored = false;
          await route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=telephony-identity');

    const section = page.locator('#settings-section-telephony-identity');
    await expect(section).toBeVisible({ timeout: APPEARS_COLD });
    const number = section.getByRole('textbox', {
      name: label('settings.telephony.identity.number_label'),
    });
    await expect(number).toHaveValue('+33612345678');
    await expect(number).toHaveAttribute('readonly', '');
    await expect(
      section.getByRole('button', { name: label('settings.telephony.identity.verify_by_call') })
    ).toHaveCount(0);
    await expect(section.getByRole('button', { name: label('common.save') })).toHaveCount(0);

    await section
      .getByRole('button', { name: label('settings.telephony.identity.remove') })
      .click();

    await expect.poll(() => removals).toEqual(['DELETE']);
  });

  test('shows no telephony key on a deployment that mounts no telephony', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // No route answers there, the removal included: a card would end on a 404.
    const asked = watchClosedRouters(page);
    await authenticate({ language: 'fr' });
    await mockApi([
      ...ROUTES,
      configRoute(['telephony'], { telephony_enabled: false }),
      {
        url: /\/api\/v1\/connectors(?:\?fresh=true)?$/,
        json: {
          connectors: [
            {
              id: '00000000-0000-4000-8000-00000000te1e',
              connector_type: 'elevenlabs_telephony',
              status: 'active',
              created_at: '2026-11-12T08:00:00Z',
            },
          ],
        },
      },
    ]);
    await page.goto('/fr/dashboard/settings?section=connectors');

    const section = page.locator('#settings-section-connectors');
    await expect(section).toBeVisible({ timeout: APPEARS_COLD });
    await expect(
      section.getByRole('button', { name: label('settings.connectors.available_google') })
    ).toBeVisible();
    await expect(section.getByRole('button', { name: TELEPHONY_GROUP })).toHaveCount(0);
    expect(asked.filter(path => path.includes('/telephony'))).toEqual([]);
  });
});

test.describe('settings — a router the deployment does not mount', () => {
  test('lists no personal MCP servers where the instance mounts none, and asks nothing of them', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The instance's own MCP servers on, the personal ones off: the capability
    // map still says « offered », and every route of the section answered 404.
    const asked = watchClosedRouters(page);
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, configRoute([], { mcp_user_enabled: false })]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    await expect(nav.getByRole('button', { name: SECTIONS.mcp[0], exact: true })).toHaveCount(0);
    // Every other section a switch governs is offered: nothing else closed.
    for (const capability of SWITCHED) {
      if (capability === 'mcp') continue;
      for (const title of SECTIONS[capability])
        await expect(nav.getByRole('button', { name: title, exact: true }), title).toBeVisible();
    }

    await page.goto('/fr/dashboard/settings?section=mcp-servers');
    await expect(page.getByTestId('empty-state')).toContainText(SECTIONS.mcp[0], {
      timeout: APPEARS_COLD,
    });
    await expect(page.locator('[id^="settings-section-"]')).toHaveCount(0);
    expect(asked.filter(path => path.includes('/mcp/servers'))).toEqual([]);
  });

  test('lists them where the instance mounts their router', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, configRoute([])]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    await expect(nav.getByRole('button', { name: SECTIONS.mcp[0], exact: true })).toBeVisible();
  });
});

test.describe('settings — a section only some devices can offer', () => {
  test('lists the haptic feedback on a device that can vibrate', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi([...ROUTES, configRoute([])]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    expect(await page.evaluate(() => typeof navigator.vibrate)).toBe('function');
    await expect(nav.getByRole('button', { name: HAPTICS, exact: true })).toBeVisible();
  });

  test('lists it nowhere on a device without the Vibration API, and a stale link says so', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // iOS WebKit does not implement the API: the section rendered nothing there while
    // the rail, the overview, the search and the shortcut picker all listed it.
    await page.addInitScript(() => {
      Reflect.deleteProperty(Navigator.prototype, 'vibrate');
    });
    await authenticate({ language: 'fr', settings_shortcuts: ['haptics', 'theme'] });
    await mockApi([...ROUTES, configRoute([])]);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    expect(await page.evaluate(() => typeof navigator.vibrate)).toBe('undefined');
    await expect(nav.getByRole('button', { name: 'Apparence' })).toBeVisible();
    await expect(nav.getByRole('button', { name: HAPTICS, exact: true })).toHaveCount(0);
    // The dock keeps the pin and draws only what this device can open.
    const dock = page.getByRole('navigation', { name: /raccourcis/i });
    await expect(dock.getByRole('link')).toHaveCount(1);
    await expect(dock.getByRole('link')).toHaveAccessibleName('Apparence');

    await page.goto('/fr/dashboard/settings?section=haptics');
    await expect(page.getByTestId('empty-state')).toContainText(HAPTICS, {
      timeout: APPEARS_COLD,
    });
    await expect(page.locator('[id^="settings-section-"]')).toHaveCount(0);
  });
});
