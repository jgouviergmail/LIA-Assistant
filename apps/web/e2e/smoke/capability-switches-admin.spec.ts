/**
 * The admin capability panel, grouped and measured (B7, ADR-280).
 *
 * The panel listed twelve switches in one column; it now holds twenty-five.
 * Three things only a laid-out page proves:
 *
 * 1. **the families are drawn, in the declared order** — an operator who
 *    switched something must find the panel where they left it;
 * 2. **at 320 px nothing scrolls sideways** — a row is a label, a description,
 *    a state sentence and a switch, and that is exactly the shape that breaks
 *    a narrow screen;
 * 3. **an inert switch is unmistakable** — a capability the deployment forbids
 *    keeps its switch visible and disabled, and says so. Letting an operator
 *    flip something that changes nothing is the one thing this panel must
 *    never do.
 */
import { test, expect, waitForHydration, type MockRoute } from '../fixtures';

/** A node the section really renders once its payload lands. */
const SWITCH = 'button[role="switch"]';

function capability(overrides: Record<string, unknown> = {}) {
  return {
    capability: 'image_generation',
    label_key: 'capabilities.items.image_generation',
    switch_enabled: true,
    deployment_available: true,
    effective_enabled: true,
    enforced_in_catalogue: true,
    enforced_on_routes: true,
    enforced_in_service: false,
    family: 'media',
    updated_by: null,
    updated_at: null,
    is_default: true,
    ...overrides,
  };
}

const ROUTES: MockRoute[] = [
  {
    url: '**/api/v1/admin/capabilities',
    json: [
      capability(),
      capability({
        capability: 'telephony',
        label_key: 'capabilities.items.telephony',
        family: 'media',
        deployment_available: false,
        effective_enabled: false,
      }),
      capability({
        capability: 'memory',
        label_key: 'capabilities.items.memory',
        family: 'knowledge',
        enforced_in_catalogue: false,
        enforced_on_routes: false,
        enforced_in_service: true,
      }),
      capability({
        capability: 'workboard',
        label_key: 'capabilities.items.workboard',
        family: 'work',
        enforced_in_catalogue: false,
        enforced_on_routes: true,
      }),
      capability({
        capability: 'peers',
        label_key: 'capabilities.items.peers',
        family: 'people',
        enforced_in_catalogue: false,
        enforced_on_routes: true,
      }),
    ],
  },
];

test.describe('the admin capability panel', () => {
  test('groups its switches by family, in the declared order', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(ROUTES);

    await page.goto('/en/dashboard/settings?section=admin-capabilities');
    await waitForHydration(page, SWITCH);

    const families = await page
      .locator('[data-family]')
      .evaluateAll(nodes => nodes.map(node => node.getAttribute('data-family')));
    expect(families).toEqual(['media', 'knowledge', 'work', 'people']);
  });

  test('says a capability is enforced at a service chokepoint, not on a route', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(ROUTES);

    await page.goto('/en/dashboard/settings?section=admin-capabilities');
    await waitForHydration(page, SWITCH);

    const knowledge = page.locator('[data-family="knowledge"]');
    await expect(knowledge).toContainText(/internal chokepoint/i);
    // The sentence that matters: the ability stops, the record stays.
    await expect(knowledge).toContainText(/already produced stays/i);
  });

  test('keeps a deployment-blocked switch visible, disabled and explained', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(ROUTES);

    await page.goto('/en/dashboard/settings?section=admin-capabilities');
    await waitForHydration(page, SWITCH);

    const blocked = page.getByRole('switch', { name: 'Phone calls' });
    await expect(blocked).toBeVisible();
    await expect(blocked).toBeDisabled();
    // And it SAYS why, rather than merely greying out.
    await expect(page.locator('[data-family="media"]')).toContainText(/deployment/i);
  });

  test('never scrolls sideways at 320 px', async ({ page, authenticate, mockApi }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await authenticate({ language: 'en', is_superuser: true });
    await mockApi(ROUTES);

    await page.goto('/en/dashboard/settings?section=admin-capabilities');
    await waitForHydration(page, SWITCH);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
