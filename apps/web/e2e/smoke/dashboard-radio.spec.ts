/**
 * The personal radio from the dashboard (ADR-324), against a mocked API.
 *
 * What a listener must be able to rely on:
 *  - where the instance offers the radio it is on the header (from `lg`), in
 *    the logo menu (below `lg`) and on the home page — and where it does not,
 *    nothing offers it and its page says so rather than failing a click;
 *  - a start opens ONE session (`POST /radio/sessions`, the listener's settings
 *    as sent: `{}`), its bar shows under the header, and a stop is sent and
 *    told in the listener's words;
 *  - a refused start names its reason (`detail.code`) in the listener's words,
 *    never a generic « could not start »;
 *  - a news flash cuts the programme on air, and the programme then picks up
 *    where it stopped — the element seeks, it never starts over.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { test, expect, briefingCardsMock, type MockRoute } from '../fixtures';

const SESSION_ID = 'a1b2c3d4-0000-4000-8000-00000000ra01';

function config(radio: boolean) {
  return {
    sse: { heartbeat_interval_seconds: 30 },
    rate_limits: { enabled: false, per_minute: 60, burst: 10 },
    i18n: { supported_languages: ['en', 'fr', 'de', 'es', 'it', 'zh'], default_language: 'en' },
    features: { radio_enabled: radio },
    capabilities: { radio: { enabled: radio, family: 'media' } },
    api_version: 'v1',
  };
}

/** `RadioSessionResponse` (apps/api/src/domains/radio/schemas.py). */
const SESSION = {
  session_id: SESSION_ID,
  status: 'starting',
  segments: [],
  cost_eur: 0,
  stop_at: null,
  startup_estimate_s: 12,
  end_reason: null,
  mood: 'calm',
};

/** `RadioPlayheadRequest` (apps/api/src/domains/radio/schemas.py). */
interface Playhead {
  seq: number;
  position_s: number;
  playing: boolean;
  paused: boolean;
  flash_heard?: number;
}

/** Two minutes of the station's own music: a programme's voice long enough to be cut. */
const MUSIC = readFileSync(
  path.join(__dirname, '..', '..', 'public', 'radio', 'music', 'calm', 'calm-01.mp3')
);

/** An 8-bit mono WAV of `seconds` of silence: a voice built here rather than committed. */
function silentWav(seconds: number): Buffer {
  const rate = 8000;
  const samples = rate * seconds;
  const header = Buffer.alloc(44);
  header.write('RIFF', 0, 'ascii');
  header.writeUInt32LE(36 + samples, 4);
  header.write('WAVEfmt ', 8, 'ascii');
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(1, 22); // mono
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate, 28); // bytes per second
  header.writeUInt16LE(1, 32); // bytes per frame
  header.writeUInt16LE(8, 34); // bits per sample
  header.write('data', 36, 'ascii');
  header.writeUInt32LE(samples, 40);
  // 128 is the silence of unsigned 8-bit samples.
  return Buffer.concat([header, Buffer.alloc(samples, 128)]);
}

/** The home page's own calls, so it renders clean around the radio card. */
const HOME: MockRoute[] = [
  briefingCardsMock,
  {
    url: '**/api/v1/briefing/synthesis',
    json: { greeting: { text: 'Welcome back', generated_at: null, usage: null }, synthesis: null },
  },
  { url: '**/api/v1/usage/**', json: {} },
];

test.describe('the radio from the dashboard', () => {
  test('starts from the header, shows its bar, and stops when asked', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const starts: unknown[] = [];
    const stops: string[] = [];
    await authenticate();
    await mockApi([
      ...HOME,
      { url: '**/api/v1/config', json: config(true) },
      {
        url: '**/api/v1/radio/sessions',
        method: 'POST',
        handler: async route => {
          starts.push(route.request().postDataJSON());
          await route.fulfill({
            status: 201,
            contentType: 'application/json',
            body: JSON.stringify(SESSION),
          });
        },
      },
      {
        url: `**/api/v1/radio/sessions/${SESSION_ID}/playhead`,
        method: 'POST',
        json: { ...SESSION, status: 'on_air' },
      },
      {
        url: `**/api/v1/radio/sessions/${SESSION_ID}/stop`,
        method: 'POST',
        handler: async route => {
          stops.push(route.request().url());
          await route.fulfill({ status: 204, body: '' });
        },
      },
    ]);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/en/dashboard');

    // The home card offers the same command as the header.
    await expect(page.getByRole('heading', { name: 'LIA Radio' })).toBeVisible();
    const header = page.locator('header');
    // ADR-324 decision 28: the station's music starts with the first answer, in
    // the mood it names, from this origin's library.
    const music = page.waitForRequest(request =>
      /\/radio\/music\/calm\/calm-\d+\.mp3$/.test(new URL(request.url()).pathname)
    );
    await header.getByRole('button', { name: 'Start the radio' }).click();

    const bar = page.getByRole('status').filter({ hasText: 'Between two programmes' });
    await expect(bar).toBeVisible();
    expect(starts).toEqual([{}]);
    await music;

    await page.setViewportSize({ width: 390, height: 844 });
    const banner = page.getByRole('region', { name: 'LIA Radio' });
    await banner.getByRole('button', { name: 'Minimize radio player' }).click();
    await expect(banner.getByRole('button', { name: 'Expand radio player' })).toBeVisible();
    await expect(banner.getByRole('link', { name: 'Transcript and sources' })).toBeHidden();
    await expect.poll(async () => (await banner.boundingBox())?.height ?? 0).toBeLessThan(75);
    await banner.getByRole('button', { name: 'Expand radio player' }).click();
    await expect(banner.getByRole('button', { name: 'Minimize radio player' })).toBeVisible();
    await page.setViewportSize({ width: 1280, height: 900 });

    const stop = header.getByRole('button', { name: 'Stop the radio' });
    await expect(stop).toHaveAttribute('aria-pressed', 'true');
    await stop.click();

    await expect(
      page.getByRole('status').filter({ hasText: 'You stopped the radio.' })
    ).toBeVisible();
    expect(stops).toHaveLength(1);
    await expect(header.getByRole('button', { name: 'Start the radio' })).toBeVisible();
  });

  test('a refused start says why, in the listener’s words', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi([
      ...HOME,
      { url: '**/api/v1/config', json: config(true) },
      {
        url: '**/api/v1/radio/sessions',
        method: 'POST',
        status: 503,
        json: { detail: { code: 'radio_instance_full' } },
      },
    ]);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/en/dashboard');

    await page.locator('header').getByRole('button', { name: 'Start the radio' }).click();

    await expect(
      page
        .getByRole('status')
        .filter({ hasText: 'The radio is busy on this instance — try again in a few minutes.' })
    ).toBeVisible();
  });

  test('reached from another page, the home page shows the radio without waiting', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Every read of the configuration takes 4 s. The home page starts from the
    // layout's last read (ADR-324 decision 30): read alone, its radio card
    // landed a round trip after the page and pushed « My dashboard » down.
    await authenticate();
    await mockApi([
      ...HOME,
      {
        url: '**/api/v1/config',
        handler: async route => {
          await new Promise(resolve => setTimeout(resolve, 4000));
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(config(true)),
          });
        },
      },
    ]);
    await page.setViewportSize({ width: 1280, height: 900 });
    // Compiled and seen once, so the navigation below measures the page alone.
    await page.goto('/en/dashboard');
    await expect(page.getByRole('heading', { name: 'LIA Radio' })).toBeVisible({ timeout: 30_000 });
    await page.goto('/en/dashboard/faq');
    await expect(page.getByRole('button', { name: 'Start the radio' })).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole('link', { name: 'Home' }).first().click();
    await expect(page.getByRole('heading', { name: 'LIA Radio' })).toBeVisible({ timeout: 2000 });
  });

  test('a news flash cuts the programme, which then picks up where it stopped', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // ADR-324 decision 32, in a real browser: the flash lasts eight seconds, so
    // at least one periodic report (every five) lands while it airs.
    const line = (text: string) => ({ role: 'host', text, offset_s: 0, sources: [] });
    const programme = {
      seq: 1,
      format: 'opening',
      mood: 'calm',
      title: 'Good morning',
      duration_s: 118,
      transcript: [line('Good morning, this is your radio.')],
    };
    const flash = {
      seq: 100_001,
      format: 'flash',
      mood: null,
      title: 'From the chat',
      duration_s: 8,
      transcript: [line('A word from the chat, then back to the programme.')],
    };
    const onAir = { ...SESSION, status: 'on_air', segments: [programme] };
    const reports: Playhead[] = [];
    let offered = false;
    let heard = false;
    await authenticate();
    await mockApi([
      { url: '**/api/v1/config', json: config(true) },
      { url: '**/api/v1/radio/sessions', method: 'POST', status: 201, json: onAir },
      {
        url: `**/api/v1/radio/sessions/${SESSION_ID}/playhead`,
        method: 'POST',
        handler: async route => {
          const report = route.request().postDataJSON() as Playhead;
          reports.push(report);
          // LIA writes in the chat once the programme has played a while; the
          // API names the flash until a report says it was heard.
          offered ||= report.seq === programme.seq && report.position_s >= 2;
          heard ||= (report.flash_heard ?? 0) >= flash.seq;
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...onAir, flash: offered && !heard ? flash : null }),
          });
        },
      },
      {
        url: `**/api/v1/radio/sessions/${SESSION_ID}/segments/${programme.seq}/audio`,
        handler: route => route.fulfill({ status: 200, contentType: 'audio/mpeg', body: MUSIC }),
      },
      {
        url: `**/api/v1/radio/sessions/${SESSION_ID}/segments/${flash.seq}/audio`,
        handler: route =>
          route.fulfill({ status: 200, contentType: 'audio/wav', body: silentWav(8) }),
      },
    ]);
    await page.goto('/en/dashboard/radio');
    await page.getByRole('main').getByRole('button', { name: 'Start the radio' }).click();

    await expect(page.getByRole('heading', { name: 'Good morning' })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole('heading', { name: 'From the chat' })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByRole('status').filter({ hasText: 'News flash' })).toContainText(
      'From the chat'
    );
    await expect(page.getByRole('heading', { name: 'Good morning' })).toBeVisible({
      timeout: 20_000,
    });
    await expect.poll(() => reports.some(report => report.flash_heard === flash.seq)).toBe(true);

    // While the flash aired, every report named the programme it cut, frozen
    // where it stopped; the first one after it says the flash was heard and
    // finds the programme there again — never back at its start.
    const offeredBy = reports.findIndex(report => report.position_s >= 2);
    const resumed = reports.findIndex(report => report.flash_heard === flash.seq);
    const during = reports.slice(offeredBy + 1, resumed);
    expect(during.length).toBeGreaterThan(0);
    const cutAt = during[0].position_s;
    expect(cutAt).toBeGreaterThanOrEqual(2);
    expect(during).toEqual(during.map(() => ({ seq: 1, position_s: cutAt, playing: true, paused: false })));
    expect(reports[resumed]).toMatchObject({ seq: 1, playing: true, paused: false });
    expect(reports[resumed].position_s).toBeGreaterThanOrEqual(cutAt - 0.5);
  });

  test('on a phone, the logo menu carries the radio', async ({ page, authenticate, mockApi }) => {
    await authenticate();
    await mockApi([...HOME, { url: '**/api/v1/config', json: config(true) }]);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/en/dashboard');

    await page.getByRole('button', { name: 'Menu' }).click();
    await expect(page.getByRole('menuitem', { name: 'Start the radio' })).toBeVisible();
  });

  test('where the instance does not offer the radio, nothing offers it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi([...HOME, { url: '**/api/v1/config', json: config(false) }]);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/en/dashboard');

    await expect(page.getByRole('main')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start the radio' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'LIA Radio' })).toHaveCount(0);

    await page.goto('/en/dashboard/radio');
    await expect(page.getByText('The radio is not offered on this instance.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start the radio' })).toHaveCount(0);
  });
});
