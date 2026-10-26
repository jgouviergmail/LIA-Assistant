import { expect, type Page } from '@playwright/test';

/** Exercise native account identity, never a world-local pseudonym. Disposable proof only. */
export async function setNativeWorldName(page: Page, name: string): Promise<void> {
  const me = await page.request.get('/api/v1/auth/me');
  expect(me.status()).toBe(200);
  const user: unknown = await me.json();
  if (!user || typeof user !== 'object' || !('id' in user) || typeof user.id !== 'string')
    throw new Error('Missing native proof identity');
  const saved = await page.request.patch('/api/v1/users/' + user.id, { data: { full_name: name } });
  expect(saved.status()).toBe(200);
}
/** Set the inert native identity before navigation, without aborting hydrated reads. */
export async function openNativeWorld(page: Page, name: string, url: string | URL): Promise<void> {
  await setNativeWorldName(page, name);
  await page.goto(String(url));
  await expect(page.locator('[data-world-public-name]')).toBeVisible();
}
export async function enterWorld(page: Page): Promise<void> {
  const admission = page.locator('.world-admission');
  const enter = admission.getByRole('button').filter({ hasText: /./ }).last();
  await expect(admission.locator('[data-world-public-name]')).toBeVisible();
  const consent = admission.locator('input[name="world-presence-consent"]');
  if (await consent.isVisible()) await consent.check();
  await enter.click();
}

/** Reveal the actual compact toolbar; never force-click a hidden control. */
export async function revealWorldControls(page: Page): Promise<void> {
  const toggle = page.locator('.world-hud-toggle');
  if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'false')
    await toggle.click();
}
