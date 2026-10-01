/**
 * The landing video (ADR-330, amended), against a mocked media origin.
 *
 * The section exists only when the server names a video; the ONE element the
 * layout owns autoplays once in view, obeys its two controls, keeps its music
 * while the reader scrolls on (docked) and while they move to another public
 * page (the titles there beating too), stops on the sign-in page, reports no
 * blocking a11y violation, and stays still for a reader who asked for less
 * motion. The clip is a two-second generated fixture served from
 * `fixtures/media/`.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Page, Route } from '@playwright/test';

import { scanPage } from '../a11y/scan';
import { test, expect } from '../fixtures';

import { awaitStyledPage } from './overflow-report';

const FIXTURES = join(__dirname, '..', 'fixtures', 'media');
const MEDIA_PREFIX = '/e2e-media/';

const DESCRIPTOR = {
  poster: `${MEDIA_PREFIX}clip-poster.webp`,
  renditions: [{ src: `${MEDIA_PREFIX}clip.mp4`, type: 'video/mp4; codecs="avc1.42E01E"' }],
  aspectRatio: [16, 9],
  durationSeconds: 2,
  hasBeats: true,
  credit: { label: '@fixture', url: 'https://example.org/fixture' },
  aiGenerated: true,
};

/**
 * Serve a fixture the way a media host does: Chromium's media pipeline asks
 * for byte ranges and stalls on a mock that answers every request with the
 * whole file and no `Accept-Ranges` (measured: `paused` never turned false).
 */
function fulfillMedia(route: Route, name: string): Promise<void> {
  const body = readFileSync(join(FIXTURES, name));
  const contentType = name.endsWith('.mp4') ? 'video/mp4' : 'image/webp';
  const range = /^bytes=(\d*)-(\d*)$/.exec(route.request().headers()['range'] ?? '');
  if (!range) {
    return route.fulfill({
      status: 200,
      body,
      headers: { 'Content-Type': contentType, 'Accept-Ranges': 'bytes' },
    });
  }
  const start = range[1] ? Number(range[1]) : 0;
  const end = range[2] ? Math.min(Number(range[2]), body.length - 1) : body.length - 1;
  return route.fulfill({
    status: 206,
    body: body.subarray(start, end + 1),
    headers: {
      'Content-Type': contentType,
      'Accept-Ranges': 'bytes',
      'Content-Range': `bytes ${start}-${end}/${body.length}`,
    },
  });
}

async function mockMedia(page: Page, video: typeof DESCRIPTOR | null): Promise<void> {
  await page.route('**/api/landing-media', route => route.fulfill({ json: { video } }));
  await page.route('**/api/landing-media/beats', route =>
    route.fulfill({ path: join(FIXTURES, 'clip-beats.json'), contentType: 'application/json' })
  );
  await page.route(`**${MEDIA_PREFIX}*`, route =>
    fulfillMedia(route, route.request().url().split('/').pop() ?? '')
  );
}

const section = (page: Page) => page.getByTestId('landing-video');
const player = (page: Page) => page.getByTestId('landing-video-player');
const video = (page: Page) => page.locator('video');
const isPaused = (page: Page) => video(page).evaluate(v => (v as HTMLVideoElement).paused);
const isMuted = (page: Page) => video(page).evaluate(v => (v as HTMLVideoElement).muted);
const currentTime = (page: Page) => video(page).evaluate(v => (v as HTMLVideoElement).currentTime);
const beating = (page: Page) => page.locator('html').getAttribute('data-beat');

/**
 * Wait for every finite animation to end before an axe scan: the sections
 * passed on the way down play their entrance (`FadeInOnScroll`, opacity from
 * 0 over 0.6 s), and scanned mid-fade axe composites a translucent text over
 * the background and reports contrast violations no reader ever sees
 * (measured: 61). The infinite ones never end.
 */
async function awaitAnimations(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(a => a.playState === 'finished' || a.effect?.getTiming().iterations === Infinity)
  );
}

/** A plain scroll: a beating title is never « stable » for Playwright's click. */
const scrollToCta = (page: Page) =>
  page.evaluate(() => document.getElementById('cosmos-cta-title')?.scrollIntoView());

test.describe('landing video — no video configured', () => {
  test('the section does not exist, nor any player', async ({ page }) => {
    await mockMedia(page, null);
    const answered = page.waitForResponse('**/api/landing-media');
    await page.goto('/fr');
    await answered;
    await awaitStyledPage(page, 'landing without video');
    await expect(section(page)).toHaveCount(0);
    await expect(player(page)).toHaveCount(0);
  });
});

/**
 * A browser's autoplay policy, emulated: sound without a user gesture is
 * refused with `NotAllowedError`, a muted start is not, and a gesture lifts
 * the refusal. Emulated rather than switched on, because the headless shell
 * does not refuse anything (measured: `--autoplay-policy=user-gesture-required`
 * still played with sound), and the component's fallback is what the test
 * must exercise.
 *
 * The gesture is a REAL input event, never `navigator.userActivation`: under
 * Playwright every `evaluate` — and every `expect`, which evaluates — is a user
 * gesture to Chromium (measured: `isActive` false from load until the first
 * `page.evaluate`, then true for about five seconds after each one), so the
 * activation flag was on before the video's first `play()`. A pointer or a
 * key is produced by `locator.click()` and `keyboard.press()` alone — a
 * `mouse.wheel` grants nothing, as in a real browser.
 */
async function refuseSoundWithoutGesture(page: Page): Promise<void> {
  await page.addInitScript(() => {
    let gestured = false;
    for (const type of ['pointerdown', 'keydown']) {
      window.addEventListener(
        type,
        () => {
          gestured = true;
        },
        { capture: true, passive: true }
      );
    }
    const original = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
      if (!this.muted && !gestured) {
        return Promise.reject(
          new DOMException(
            'play() failed because the user did not interact with the document first.',
            'NotAllowedError'
          )
        );
      }
      return original.call(this);
    };
  });
}

test.describe('landing video — configured, motion allowed, the browser wants a gesture for sound', () => {
  // contextOptions, not the top-level option: the config sets the default through
  // contextOptions, which wins (measured: the top-level override left `reduce`).
  test.use({ contextOptions: { reducedMotion: 'no-preference' }, locale: 'fr-FR' });

  test('starts muted when sound is refused, obeys its controls, keeps its music docked off-screen', async ({
    page,
  }, testInfo) => {
    await refuseSoundWithoutGesture(page);
    await mockMedia(page, DESCRIPTOR);
    await page.goto('/fr');
    await awaitStyledPage(page, 'landing with video');

    await expect(section(page)).toBeVisible();
    await expect(section(page).getByRole('link', { name: /@fixture/ })).toHaveAttribute(
      'href',
      'https://example.org/fixture'
    );
    await expect(section(page).getByText('Vidéo générée par IA')).toBeVisible();

    await section(page).scrollIntoViewIfNeeded();
    await expect(player(page)).toHaveAttribute('data-mode', 'framed');
    await expect(video(page)).toHaveAttribute('loop', '');
    await expect(video(page)).toHaveAttribute('playsinline', '');
    // Sound was wanted, refused without a gesture, and the start fell back to muted.
    await expect.poll(() => isPaused(page), { timeout: 10_000 }).toBe(false);
    expect(await isMuted(page)).toBe(true);

    const playPause = page.getByTestId('landing-video-play');
    await expect(playPause).toHaveAccessibleName('Mettre la vidéo en pause');
    await playPause.click();
    await expect.poll(() => isPaused(page)).toBe(true);
    await expect(playPause).toHaveAccessibleName('Lire la vidéo');
    await playPause.click();
    await expect.poll(() => isPaused(page)).toBe(false);

    const sound = page.getByTestId('landing-video-sound');
    await expect(sound).toHaveAttribute('aria-pressed', 'false');
    const beats = page.waitForRequest('**/api/landing-media/beats');
    await sound.click();
    await beats;
    expect(await isMuted(page)).toBe(false);
    await expect(sound).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => beating(page)).not.toBeNull();

    // Scrolling far away with the sound on: the music goes on, docked.
    await scrollToCta(page);
    await expect(player(page)).toHaveAttribute('data-mode', 'docked');
    const dock = page.getByRole('group', { name: 'Vidéo en lecture' });
    await expect(dock).toBeVisible();
    expect(await isPaused(page)).toBe(false);
    await expect(dock.getByRole('link', { name: 'Revenir à la vidéo' })).toHaveAttribute(
      'href',
      /#video$/
    );

    await awaitAnimations(page);
    const { blocking } = await scanPage(page, testInfo, '/landing-video');
    expect(blocking).toEqual([]);

    await dock.getByRole('button', { name: 'Mettre la vidéo en pause' }).click();
    await expect.poll(() => isPaused(page)).toBe(true);
    await expect(dock).toHaveCount(0);
    await expect(player(page)).toHaveAttribute('data-mode', 'framed');
  });
});

test.describe('landing video — configured, motion allowed, the browser allows sound', () => {
  // The headless shell allows sound without a gesture (measured, and Playwright
  // refuses launchOptions inside a describe anyway): nothing to pin here.
  test.use({ contextOptions: { reducedMotion: 'no-preference' }, locale: 'fr-FR' });

  test('starts with the sound, the titles beat, and a click from the dock mutes it', async ({
    page,
  }) => {
    await mockMedia(page, DESCRIPTOR);
    const beats = page.waitForRequest('**/api/landing-media/beats');
    await page.goto('/fr');
    await awaitStyledPage(page, 'landing with video, sound allowed');
    await section(page).scrollIntoViewIfNeeded();

    await expect.poll(() => isPaused(page), { timeout: 10_000 }).toBe(false);
    expect(await isMuted(page)).toBe(false);
    const sound = page.getByTestId('landing-video-sound');
    await expect(sound).toHaveAttribute('aria-pressed', 'true');
    await beats;
    await expect.poll(() => beating(page)).not.toBeNull();

    // The hero title beats too — its lines, since the entrance animation owns
    // the h1's own transform: a transform the stylesheet derives from --beat.
    const heroTitle = page.locator('main h1 > span').first();
    await expect
      .poll(() => heroTitle.evaluate(el => getComputedStyle(el).transform), { timeout: 5_000 })
      .not.toBe('none');

    await scrollToCta(page);
    const dock = page.getByRole('group', { name: 'Vidéo en lecture' });
    await expect(dock).toBeVisible();
    expect(await isPaused(page)).toBe(false);

    // Muting from the dock: a muted video off-screen pauses, the dock goes.
    await dock.getByRole('button', { name: 'Couper le son' }).click();
    await expect.poll(() => isMuted(page)).toBe(true);
    await expect.poll(() => isPaused(page)).toBe(true);
    await expect(dock).toHaveCount(0);
  });

  test('keeps playing across the public pages, the titles there beating, and stops at sign-in', async ({
    page,
  }) => {
    await mockMedia(page, DESCRIPTOR);
    await page.goto('/fr');
    await awaitStyledPage(page, 'landing with video, before leaving');
    await section(page).scrollIntoViewIfNeeded();
    await expect.poll(() => isPaused(page), { timeout: 10_000 }).toBe(false);
    await expect.poll(() => beating(page)).not.toBeNull();
    const before = await currentTime(page);

    // The header's own link: a client-side navigation, the layout stays.
    await page.locator('header').getByRole('link', { name: 'Blog' }).first().click();
    await page.waitForURL(/\/blog/);
    await awaitStyledPage(page, 'blog with the music on');
    await expect(player(page)).toHaveAttribute('data-mode', 'docked');
    await expect(page.getByRole('group', { name: 'Vidéo en lecture' })).toBeVisible();
    expect(await isPaused(page)).toBe(false);
    expect(await isMuted(page)).toBe(false);
    await expect.poll(() => currentTime(page)).toBeGreaterThanOrEqual(before);
    await expect.poll(() => beating(page)).not.toBeNull();
    const blogTitle = page.locator('main h2').first();
    await expect
      .poll(() => blogTitle.evaluate(el => getComputedStyle(el).transform), { timeout: 5_000 })
      .not.toBe('none');

    // Sign-in: the player stops and leaves.
    await page.locator('header').getByRole('link', { name: 'Se connecter' }).first().click();
    await page.waitForURL(/\/login/);
    await expect(video(page)).toHaveCount(0);
    await expect(player(page)).toHaveCount(0);
    await expect.poll(() => beating(page)).toBeNull();
  });
});

test.describe('landing video — configured, reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' }, locale: 'fr-FR' });

  test('stays on its poster until the reader presses play', async ({ page }) => {
    await mockMedia(page, DESCRIPTOR);
    await page.goto('/fr');
    await awaitStyledPage(page, 'landing with video, reduced motion');
    await section(page).scrollIntoViewIfNeeded();
    await expect(video(page).locator('source')).toHaveCount(1);
    await page.waitForTimeout(1_000);
    expect(await isPaused(page)).toBe(true);

    await page.getByTestId('landing-video-play').click();
    await expect.poll(() => isPaused(page), { timeout: 10_000 }).toBe(false);
  });
});
