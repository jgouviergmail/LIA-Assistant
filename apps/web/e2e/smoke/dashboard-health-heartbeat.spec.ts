/**
 * The heart rate beats at its own pace on the Health card (owner, 2026-11-14).
 *
 * jsdom reads a class and an inline style; only a browser proves the keyframes exist and run:
 * the figure beats once per heartbeat for a reader who welcomes motion, holds still for one who
 * asked for less, and a step count never beats.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { test, expect, waitForHydration } from '../fixtures';
import { HOME_TIMEZONE, homeBriefing, homeRoutes } from '../fixtures/dashboard-home';

interface HealthWords {
  dashboard: { briefing: { cards: { health: { kind_heart_rate: string; kind_steps: string } } } };
}

function kinds(lng: string) {
  const locale: HealthWords = JSON.parse(
    readFileSync(join(__dirname, '../../locales', lng, 'translation.json'), 'utf8')
  );
  return locale.dashboard.briefing.cards.health;
}

const HEALTH = homeBriefing().cards.health.data;
const RATE = HEALTH?.items.find(item => item.kind === 'heart_rate')?.value_today ?? 0;
const STEPS = HEALTH?.items.find(item => item.kind === 'steps')?.value_today ?? 0;

/** The figure of a metric, inside the metric that names it. */
function figure(page: Page, kindLabel: string, value: string): Locator {
  return page.locator('li', { hasText: kindLabel }).getByText(value, { exact: true });
}

async function motion(locator: Locator) {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      name: style.animationName,
      duration: style.animationDuration,
      iterations: style.animationIterationCount,
    };
  });
}

for (const reducedMotion of ['no-preference', 'reduce'] as const) {
  test(`the pulse ${reducedMotion === 'reduce' ? 'holds still' : 'beats at its own pace'} (${reducedMotion})`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.emulateMedia({ reducedMotion });
    const user = await authenticate({ language: 'en', timezone: HOME_TIMEZONE });
    await mockApi(homeRoutes(user));
    await page.goto('/en/dashboard');
    await waitForHydration(page, 'main');
    const said = kinds('en');

    const pulse = figure(page, said.kind_heart_rate, String(Math.round(RATE)));
    const steps = figure(
      page,
      said.kind_steps,
      new Intl.NumberFormat('en').format(Math.round(STEPS))
    );
    await expect(pulse).toBeVisible();
    await expect(steps).toBeVisible();

    if (reducedMotion === 'reduce') {
      expect((await motion(pulse)).name).toBe('none');
    } else {
      expect(await motion(pulse)).toEqual({
        name: 'heart-beat',
        duration: `${Number((60 / Math.round(RATE)).toFixed(3))}s`,
        iterations: 'infinite',
      });
    }
    expect((await motion(steps)).name, 'a step count never beats').toBe('none');
  });
}
