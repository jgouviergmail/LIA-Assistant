/**
 * The settings rail — master-detail navigation, desktop and drill-down.
 *
 * Unit tests pin what the rail renders (model, gates, aria-current). Only a
 * browser proves the layout half of the contract:
 *
 *  - on desktop the rail and the pane are visible TOGETHER, the rail stays
 *    available once the page is scrolled (sticky), and picking an entry swaps
 *    the pane without losing the rail;
 *  - below `lg` the rail IS the landing screen, a pick replaces it with the
 *    pane, and the back control returns to the rail — the drill-down pattern
 *    a phone reader expects;
 *  - a superuser gets the administration block; nobody else does.
 */
import { test, expect, type MockRoute } from '../fixtures';

const ROUTES: MockRoute[] = [
  { url: '**/api/v1/connectors', json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

/** French labels — the suite runs in `fr`. */
const NAV_LABEL = 'Sections des réglages';
const BACK_LABEL = 'Retour aux réglages';

const APPEARS = 20_000;
const APPEARS_COLD = 60_000;

test.describe('settings rail — desktop', () => {
  test('shows the rail beside the overview, and swaps the pane on a pick', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    // The overview cards carry the descriptions the rail does not.
    await expect(page.getByRole('heading', { level: 2, name: 'Personnalisation' })).toBeVisible();

    await nav.getByRole('button', { name: 'Apparence' }).click();
    await expect(page.locator('#settings-section-theme')).toBeVisible({ timeout: APPEARS });
    // The rail survives the pick (desktop keeps both halves)…
    await expect(nav).toBeVisible();
    // …and states the active entry.
    await expect(nav.getByRole('button', { name: 'Apparence' })).toHaveAttribute(
      'aria-current',
      'true'
    );
    // Master-detail: exactly one section mounted.
    await expect(page.locator('[id^="settings-section-"]')).toHaveCount(1);
    expect(new URL(page.url()).searchParams.get('section')).toBe('theme');
  });

  test('states on the overview what each section currently holds', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    // The shell fixture answers one live capability (memory, 12) and one
    // dormant (connectors) — both states of the line, from ONE aggregate.
    const memories = page.getByRole('button', { name: /^Mémoire/ }).last();
    await expect(memories).toContainText('12', { timeout: APPEARS_COLD });

    const connectors = page.getByRole('button', { name: /^Mes Connecteurs/ }).last();
    await expect(connectors).toContainText('À configurer');

    // A section the aggregate says nothing about claims nothing.
    await expect(page.getByRole('button', { name: /^Apparence/ }).last()).not.toContainText(
      'À configurer'
    );
  });

  test('keeps the rail reachable once the page is scrolled', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });

    // The overview is long enough to scroll; the sticky rail must follow.
    await page.mouse.wheel(0, 3000);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(500);

    const box = await nav.boundingBox();
    expect(box, 'rail must stay in the viewport').not.toBeNull();
    expect(box!.y, 'rail must stick below the dashboard header').toBeGreaterThanOrEqual(0);
    await expect(nav).toBeVisible();
  });

  test('shows the administration block to a superuser only', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr', is_superuser: true });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    await expect(nav.getByText('Administration', { exact: true })).toBeVisible();

    await nav.getByRole('button', { name: 'Administration des utilisateurs' }).click();
    await expect(page.locator('#settings-section-admin-users')).toBeVisible({ timeout: APPEARS });
  });

  test('hides the administration block from a regular account', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    await expect(nav.getByText('Administration', { exact: true })).toHaveCount(0);
  });
});

test.describe('settings rail — drill-down below lg', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('the rail is the landing, a pick opens the pane, back returns', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings');

    const nav = page.getByRole('navigation', { name: NAV_LABEL });
    await expect(nav).toBeVisible({ timeout: APPEARS_COLD });
    // The overview cards are a desktop surface: on a phone the rail IS the
    // landing (asserted through the personalization heading of the overview).
    await expect(
      page.getByRole('heading', { level: 2, name: 'Personnalisation' })
    ).toBeHidden();

    await nav.getByRole('button', { name: 'Apparence' }).click();

    // Drill-down: the pane takes the screen, the rail leaves it.
    await expect(page.locator('#settings-section-theme')).toBeVisible({ timeout: APPEARS });
    await expect(nav).toBeHidden();

    const back = page.getByRole('button', { name: BACK_LABEL });
    await expect(back).toBeVisible();
    await back.click();

    await expect(nav).toBeVisible();
    await expect(page.locator('[id^="settings-section-"]')).toHaveCount(0);
    await expect
      .poll(async () => new URL(page.url()).searchParams.get('section'), { timeout: 10_000 })
      .toBeNull();
  });

  test('a deep link lands straight on the pane, with the back control', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(ROUTES);
    await page.goto('/fr/dashboard/settings?section=voice-mode');

    await expect(page.locator('#settings-section-voice-mode')).toBeVisible({
      timeout: APPEARS_COLD,
    });
    await expect(page.getByRole('navigation', { name: NAV_LABEL })).toBeHidden();
    await expect(page.getByRole('button', { name: BACK_LABEL })).toBeVisible();
  });
});
