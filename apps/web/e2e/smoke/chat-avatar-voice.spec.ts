/**
 * A mouth that opens on the voice it HEARS (ADR-294, follow-up of 2026-11-13).
 *
 * A voice comment of three held tones parted by silences plays through the chat's own
 * queue, on the real clock. Made-up syllables open and close on their own rhythm,
 * through the silences as through the sound; a face that hears its voice holds its
 * mouth open through each tone and shut through each silence. The browser must PAINT
 * that opening too, on a drawn mouth and on a sculpted one.
 */
import { Buffer } from 'node:buffer';
import type { Locator, Page } from '@playwright/test';

import {
  test,
  expect,
  loadedChatRoutes,
  waitForHydration,
  type MockRoute,
  type TestUser,
} from '../fixtures';
import { paintedMouthHeight } from '../fixtures/organ-paint';
import { SPEECH_OPEN_MAX } from '../../src/components/eyes/rig/speech';

const RATE = 24000;
/** A held tone, far longer than any syllable the face would make up. */
const TONE_MS = 900;
type Segment = readonly [sounding: boolean, ms: number];
/** The first reply, for the timeline: a silence first, so the face is heard shut. */
const TIMELINE: readonly Segment[] = [
  [false, 600],
  [true, TONE_MS],
  [false, TONE_MS],
  [true, TONE_MS],
  [false, TONE_MS],
  [true, TONE_MS],
  [false, 400],
];
/** The second reply, for the photographs: states far longer than a photograph takes. */
const PICTURES: readonly Segment[] = [
  [true, 2500],
  [false, 2500],
];

/** Mono 16-bit PCM in a WAV: a 300 Hz tone at about -13 dBFS, or nothing. */
function heldTones(segments: readonly Segment[]): string {
  const frames = segments.reduce((sum, [, ms]) => sum + (RATE * ms) / 1000, 0);
  const wav = Buffer.alloc(44 + frames * 2);
  wav.write('RIFF');
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(RATE, 24);
  wav.writeUInt32LE(RATE * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(frames * 2, 40);
  let frame = 0;
  for (const [sounding, ms] of segments)
    for (let n = 0; n < (RATE * ms) / 1000; n++, frame++) {
      const sample = sounding ? 0.3 * Math.sin((2 * Math.PI * 300 * n) / RATE) : 0;
      wav.writeInt16LE(Math.round(sample * 32767), 44 + frame * 2);
    }
  return wav.toString('base64');
}

interface Sample {
  t: number;
  open: number;
  /** Where the eyes are turned, sideways: the rig's own channel. */
  gazeX: number;
  speaking: boolean;
}

/** How long a face takes to come back to the person from the answer it was watching. */
const GAZE_SETTLE_MS = 800;
/** The reading walk this guards against swept the eyes over more than a unit, every 1.4 s. */
const GAZE_HELD_SPAN = 0.2;

declare global {
  interface Window {
    mouthSamples?: Sample[];
  }
}

/** Every frame's opening, as the rig wrote it, while the face is on screen. */
async function record(avatar: Locator): Promise<void> {
  await avatar.evaluate(root => {
    const samples: Sample[] = [];
    window.mouthSamples = samples;
    const tick = () => {
      const style = getComputedStyle(root);
      samples.push({
        t: performance.now(),
        open: Number(style.getPropertyValue('--rig-mouth-open') || 0),
        gazeX: Number(style.getPropertyValue('--rig-gaze-x') || 0),
        speaking: root.getAttribute('data-expression') === 'speaking',
      });
      // Until the spec takes the samples away.
      if (window.mouthSamples === samples) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

async function openNow(avatar: Locator): Promise<number> {
  return avatar.evaluate(root =>
    Number(getComputedStyle(root).getPropertyValue('--rig-mouth-open') || 0)
  );
}

type Run = { state: 'open' | 'shut'; from: number; to: number };

/** The spoken stretch, as runs of a mouth held open or held shut. */
function runsOf(samples: Sample[]): { low: number; high: number; runs: Run[] } {
  const spoken = samples.filter(sample => sample.speaking);
  const low = Math.min(...spoken.map(sample => sample.open));
  const high = Math.max(...spoken.map(sample => sample.open));
  const runs: Run[] = [];
  for (const sample of spoken) {
    const state =
      sample.open >= low + 0.6 * (high - low)
        ? 'open'
        : sample.open <= low + 0.25 * (high - low)
          ? 'shut'
          : null;
    if (!state) continue;
    const last = runs.at(-1);
    if (last?.state === state) last.to = sample.t;
    else runs.push({ state, from: sample.t, to: sample.t });
  }
  return { low, high, runs };
}

async function openChat(
  page: Page,
  authenticate: (overrides?: Partial<TestUser>) => Promise<TestUser>,
  mockApi: (routes: MockRoute[]) => Promise<void>,
  style: string,
  variant: 'male' | 'female'
): Promise<Locator> {
  await page.addInitScript(
    ({ style, variant }) => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style, size: 'xl' }, version: 0 })
      );
      if (variant === 'male') document.cookie = 'lia_gender=male; path=/';
    },
    { style, variant }
  );
  await authenticate({ voice_enabled: true });
  await mockApi(loadedChatRoutes());
  let replies = 0;
  await page.route('**/api/v1/agents/chat/stream', async route => {
    const run = `held-tones-${++replies}`;
    const chunks = [
      { type: 'voice_comment_start', content: '', metadata: { run_id: run } },
      { type: 'token', content: 'Held tones.', metadata: null },
      {
        type: 'voice_audio_chunk',
        content: {
          audio_base64: heldTones(replies === 1 ? TIMELINE : PICTURES),
          phrase_index: 0,
          is_last: true,
          mime_type: 'audio/wav',
        },
        metadata: { run_id: run },
      },
      { type: 'voice_complete', content: '', metadata: { chunk_count: 1 } },
      { type: 'done', content: '', metadata: {} },
    ];
    await route.fulfill({
      contentType: 'text/event-stream',
      body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
    });
  });
  await page.goto('/en/dashboard/chat');
  await waitForHydration(page);
  const avatar = page.locator('.lia-eyes-widget .lia-eyes').last();
  await expect(avatar).toBeVisible();
  return avatar;
}

/** One message sent, until its reply speaks. */
async function speak(page: Page, avatar: Locator, message: string, replies: number) {
  await page.locator('textarea').fill(message);
  await page.locator('textarea').press('Enter');
  await expect(page.getByText('Held tones.', { exact: true })).toHaveCount(replies);
  await expect(avatar).toHaveAttribute('data-expression', 'speaking', { timeout: 10_000 });
}

test.describe('a mouth that opens on the voice it hears', () => {
  // A face that speaks moves: the suite's reduced motion keeps it still on purpose. One
  // device pixel per CSS pixel: a sculpted head painted at twice the density starves
  // the frames a timeline is read on (measured at 13 a second on a loaded host).
  test.use({ contextOptions: { reducedMotion: 'no-preference' } });

  for (const { style, variant } of [
    { style: 'bip', variant: 'female' },
    { style: 'spirit', variant: 'male' },
  ] as const)
    test(`${style} (${variant}) holds its mouth open on each tone and shut in each silence`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      const pageErrors: string[] = [];
      page.on('pageerror', error => pageErrors.push(error.name));
      const avatar = await openChat(page, authenticate, mockApi, style, variant);
      // An engine build without Web Audio plays no voice at all (Playwright's WebKit
      // on Windows): there is no sound for the face to hear, and it says so.
      test.skip(
        !(await page.evaluate(() => typeof AudioContext === 'function')),
        'this engine build has no Web Audio: no voice can play'
      );
      await record(avatar);
      await speak(page, avatar, 'Speak in held tones', 1);
      await expect(avatar).not.toHaveAttribute('data-expression', 'speaking', {
        timeout: 10_000,
      });

      const samples = await page.evaluate(() => {
        const taken = window.mouthSamples ?? [];
        window.mouthSamples = undefined;
        return taken;
      });
      const { low, high, runs } = runsOf(samples);
      // It really opens: most of the way a full voice may take it.
      expect(high - low).toBeGreaterThan(0.6 * SPEECH_OPEN_MAX);
      // Shut before the first tone and after the last; in between, one held opening
      // per tone, one held closing per silence — never a syllable's flutter.
      while (runs[0]?.state === 'shut') runs.shift();
      while (runs.at(-1)?.state === 'shut') runs.pop();
      expect(runs.map(run => run.state)).toEqual(['open', 'shut', 'open', 'shut', 'open']);
      // A run is read between its first and last frame: a frame late on either edge
      // shortens it, a syllable's flutter never comes near (it holds 0 to 85 ms).
      for (const run of runs) expect(run.to - run.from).toBeGreaterThan(0.4 * TONE_MS);

      // It speaks TO the person (owner rule 2026-11-14): once the eyes are back from
      // the answer they watched being written, they hold — no line is read aloud.
      const spoken = samples.filter(sample => sample.speaking);
      const settled = spoken.filter(sample => sample.t >= spoken[0].t + GAZE_SETTLE_MS);
      const gazes = settled.map(sample => sample.gazeX);
      expect(settled.length, 'frames of a face that speaks').toBeGreaterThan(30);
      expect(Math.max(...gazes) - Math.min(...gazes)).toBeLessThan(GAZE_HELD_SPAN);

      // And the picture follows: a mouth painted open on a tone, shut in a silence.
      // Photographs slow the page's frames, so they are taken on a second reply of
      // long states, each between two reads of the channel.
      await speak(page, avatar, 'Speak again', 2);
      const shots: { before: number; after: number; height: number }[] = [];
      while ((await avatar.getAttribute('data-expression')) === 'speaking' && shots.length < 40) {
        const before = await openNow(avatar);
        const height = await paintedMouthHeight(page, avatar);
        shots.push({ before, after: await openNow(avatar), height });
      }
      const held = (state: 'open' | 'shut') =>
        shots
          .filter(shot =>
            [shot.before, shot.after].every(open =>
              state === 'open'
                ? open >= low + 0.6 * (high - low)
                : open <= low + 0.25 * (high - low)
            )
          )
          .map(shot => shot.height);
      const open = held('open');
      const shut = held('shut');
      expect(open.length, 'a shot of the mouth on a tone').toBeGreaterThan(0);
      expect(shut.length, 'a shot of the mouth in a silence').toBeGreaterThan(0);
      expect(Math.min(...open)).toBeGreaterThan(Math.max(...shut) + 2);
      expect(pageErrors).toEqual([]);
    });
});
