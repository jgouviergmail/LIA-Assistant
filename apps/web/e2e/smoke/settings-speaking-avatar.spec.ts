import { test, expect, loadedChatRoutes } from '../fixtures';
import { avatarConfig } from '../fixtures/simli';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';
import { scanPage } from '../a11y/scan';
import { appConfig } from '../fixtures/dashboard-shell';

const faces = ['Proud Cuckoo', 'Gleaming Loon', 'Distinct Ladybug', 'Impressed Tiger'].map(
  (name, index) => ({
    id: `00000000-0000-4000-8000-00000000000${index + 1}`,
    name,
    source: 'private',
    preview_image_url: `https://mintcdn.com/simli/fixture/images/${index}.png`,
  })
);

for (const width of [320, 1280]) {
  test(`account avatar selection has a free static preview at ${width}px`, async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await authenticate({ voice_enabled: false });
    const config = { ...avatarConfig, enabled: false, face_id: faces[3].id };
    const writes: unknown[] = [];
    const starts: unknown[] = [];
    await mockApi([
      ...loadedChatRoutes(),
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, avatar_enabled: true } },
      },
      { url: '**/api/v1/connectors', json: { connectors: [] } },
      { url: '**/api/v1/avatars/config', handler: route => route.fulfill({ json: config }) },
      { url: '**/api/v1/avatars/faces', json: faces },
      {
        url: '**/api/v1/avatars/sessions',
        method: 'POST',
        handler: async route => {
          starts.push(route.request().postDataJSON());
          await route.fulfill({ status: 500, json: {} });
        },
      },
      {
        url: '**/api/v1/avatars/settings',
        method: 'PUT',
        handler: async route => {
          const body = route.request().postDataJSON();
          writes.push(body);
          Object.assign(config, body);
          await route.fulfill({ json: config });
        },
      },
    ]);
    await page.route('https://mintcdn.com/simli/fixture/images/*', route =>
      route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="176" height="176"><rect width="176" height="176" fill="#305070"/></svg>',
      })
    );
    await page.goto('/en/dashboard/settings?section=avatar');
    await awaitStyledPage(page, 'avatar settings');
    await expect(page.getByRole('img', { name: 'Impressed Tiger' })).toBeVisible();
    await expect
      .poll(() =>
        page
          .getByRole('img', { name: 'Impressed Tiger' })
          .evaluate(image => (image as HTMLImageElement).naturalWidth)
      )
      .toBeGreaterThan(0);
    await page.getByRole('combobox', { name: 'Avatar' }).click();
    for (const face of faces)
      await expect(page.getByRole('option', { name: face.name, exact: true })).toBeVisible();
    await page.getByRole('option', { name: 'Gleaming Loon', exact: true }).click();
    await expect(page.getByRole('img', { name: 'Gleaming Loon' })).toBeVisible();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toEqual({ enabled: false, face_id: faces[1].id });
    // HTTP receipt is earlier than the form's completed save/refresh cycle.
    const picker = page.getByRole('combobox', { name: 'Avatar' });
    await expect(picker).toBeEnabled();
    await expect(picker).toHaveCSS('opacity', '1');
    await expect(page.locator('#avatar-face-custom')).toHaveCSS('opacity', '1');
    expect(starts).toHaveLength(0);
    await expectNoOverflow(page, `avatar preview at ${width}px`);
    const { blocking, summary } = await scanPage(page, testInfo, 'avatar-settings');
    expect(blocking, summary).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('avatar-settings.png') });
  });
}
