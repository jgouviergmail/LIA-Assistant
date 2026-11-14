/** Real companion + mocked SSE: no tool plan or prepared draft earns an action gesture. */
import { test, expect, chatRoutes, waitForClockedHydration } from '../fixtures';
import { scanPage } from '../a11y/scan';
import type { Locator, Page } from '@playwright/test';
import { MAX_FRAME_MS } from '../../src/components/eyes/rig/scheduler';
import { SKETCH_FIRST_MAX_DELAY_MS } from '../../src/components/eyes/rig/sketches';
import { GAZE_TARGET_ATTRIBUTE } from '../../src/components/eyes/gaze-target';
import { HAND_OVER_AFTER_MS } from '../../src/components/eyes/exchange-beats';
import { paintedEyeHeights, paintedEyesRow } from '../fixtures/organ-paint';

for (const outcome of ['prepared', 'succeeded', 'failed', 'unknown'] as const) {
  test(`companion distinguishes ${outcome}, then forgets it on reload`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await page.setViewportSize({ width: 375, height: 812 });
    await page.addInitScript(() => {
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'bip', size: 'md' }, version: 0 })
      );
    });
    await mockApi(chatRoutes([]));
    await page.route('**/api/v1/agents/chat/stream', async route => {
      const activity = {
        version: 1,
        run_id: 'e2e',
        invocation_id: 'actual',
        family: 'communicating',
        intent: outcome === 'prepared' ? 'prepare' : 'act',
        phase: 'finished',
        outcome,
      };
      const chunks = [
        { type: 'execution_step', content: '', metadata: { step_type: 'activity', activity } },
        { type: 'token', content: 'Voici la réponse de contrôle.', metadata: null },
        {
          type: 'done',
          content: '',
          metadata: { expressivity: { register: 'warm', intensity: 0.5, accent: 'none' } },
        },
      ];
      await route.fulfill({
        contentType: 'text/event-stream',
        body: chunks.map(chunk => `data: ${JSON.stringify(chunk)}\n\n`).join(''),
      });
    });
    await page.goto('/en/dashboard/chat');
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await expect(avatar).toBeVisible();
    await page.locator('textarea').fill('Contrôle du compagnon');
    await page.locator('textarea').press('Enter');
    await expect(page.getByText('Voici la réponse de contrôle.', { exact: true })).toBeVisible();
    await expect(avatar).toHaveAttribute('data-accomplished', String(outcome === 'succeeded'));
    await expect(avatar).toHaveAttribute('data-expression', 'tender');
    const bounds = await avatar.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(375);
    expect(await avatar.getAttribute('aria-hidden')).toBe('true');
    await page.reload();
    await expect(avatar).toBeVisible();
    await expect(avatar).toHaveAttribute('data-accomplished', 'false');
    await expect(avatar).not.toHaveAttribute('data-expression', 'tender');
  });
}

test('drawn eyes respect reduced motion and the widget remains keyboard operable', async ({
  page,
  authenticate,
  mockApi,
}, testInfo) => {
  await authenticate();
  await mockApi(chatRoutes([]));
  await page.addInitScript(() =>
    localStorage.setItem(
      'lia_eyes_widget_prefs',
      JSON.stringify({ state: { visible: true, style: 'anneaux', size: 'md' }, version: 0 })
    )
  );
  await page.goto('/en/dashboard/chat');
  const avatar = page.locator('.lia-eyes[data-style="anneaux"]').last();
  await expect(avatar).toBeVisible();
  const widget = page.getByRole('group', { name: /LIA's expressive eyes/ });
  await widget.focus();
  const before = await widget.boundingBox();
  await page.keyboard.press('ArrowLeft');
  await expect.poll(async () => (await widget.boundingBox())!.x).toBeLessThan(before!.x);
  const path = avatar.locator('[data-rig-mouth]');
  const shape = await path.getAttribute('d');
  await page.waitForTimeout(1100); // Observe a full host heartbeat under reduced motion.
  expect(await path.getAttribute('d')).toBe(shape);
  await page.getByRole('button', { name: 'Hide the eyes', exact: true }).click();
  await expect(avatar).not.toBeVisible();
  await page.getByRole('button', { name: 'Show the eyes', exact: true }).click();
  await expect(avatar).toBeVisible();
  const { blocking, summary } = await scanPage(page, testInfo, 'chat-avatar');
  expect(blocking, summary).toEqual([]);
});

/**
 * Advance half a second sparsely, in jumps no longer than the longest slice
 * the rig integrates at once, so each one is a single step. runFor executes
 * and yields after every 16 ms rAF; under WebKit tracing, idle frames can
 * consume the test's 90 s.
 */
async function advanceSparsely(page: Page): Promise<void> {
  for (let remaining = 500; remaining > 0; ) {
    // runFor may end between rAFs; leave room for that first remainder.
    const cap = remaining === 500 ? MAX_FRAME_MS / 2 : MAX_FRAME_MS;
    const step = Math.min(remaining, cap);
    await page.clock.fastForward(step);
    remaining -= step;
  }
}

/** Longer than the longest wait before a first scene: on a face at rest, one
 * has played by then (the last scenario of this file proves it on this page). */
const A_SCENE_WOULD_HAVE_PLAYED_MS = SKETCH_FIRST_MAX_DELAY_MS + 5000;

async function openLivingCompanion(
  page: Page,
  position: { xPct: number; yPct: number } | null = null,
  size: 'md' | 'xl' = 'md'
): Promise<void> {
  await page.addInitScript(
    ({ parked, size }) =>
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({
          state: { visible: true, style: 'bip', size, position: parked },
          version: 0,
        })
      ),
    { parked: position, size }
  );
  const clockStart = new Date('2026-09-21T12:00:00Z');
  await page.clock.install({ time: clockStart });
  // Pause before navigation so layout, snapshots and screenshots cannot move
  // the rig's timeline between the advances we explicitly observe.
  await page.clock.pauseAt(new Date(clockStart.getTime() + 1000));
  await page.goto('/en/dashboard/chat');
}

/** What the page holds to write an answer piece by piece (see the scenario). */
interface HeldAnswer {
  opened(): boolean;
  write(chunk: unknown): void;
  deliver(): void;
}

/**
 * A mocked route answers whole. An answer that is still being WRITTEN — or a
 * turn that is still WORKING — needs a body that stays open: held in the page,
 * never on the network.
 */
async function holdTheAnswer(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    const encoder = new TextEncoder();
    let body: ReadableStreamDefaultController<Uint8Array> | null = null;
    const held: HeldAnswer = {
      opened: () => body !== null,
      write: chunk => body?.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`)),
      deliver: () => body?.close(),
    };
    Object.assign(window, { __answer: held });
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      if (!url.includes('/agents/chat/stream')) return original(input, init);
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          body = controller;
        },
      });
      return Promise.resolve(
        new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } })
      );
    };
  });
  // Plain page calls: the application's content policy forbids evaluating a
  // string, in the page as anywhere else.
  return {
    answerIs: (state: 'opened') =>
      page.evaluate(name => (Reflect.get(window, '__answer') as HeldAnswer)[name](), state),
    writeAnswer: (chunk: unknown) =>
      page.evaluate(piece => (Reflect.get(window, '__answer') as HeldAnswer).write(piece), chunk),
    deliverAnswer: () =>
      page.evaluate(() => (Reflect.get(window, '__answer') as HeldAnswer).deliver()),
  };
}

/**
 * Where the painted eyes stand, read only while they are OPEN: a spontaneous
 * blink moves the paint as much as a look does (it lands at random, and once
 * on the rest sample of a run it took the whole look away). Each sample keeps
 * its row when both eyes are painted at least 80 % as tall as the tallest
 * sample; the rows kept are returned.
 */
async function openEyesRows(page: Page, avatar: Locator, stepsMs: readonly number[]) {
  const samples: { row: number; height: number }[] = [];
  for (const step of stepsMs) {
    await page.clock.runFor(step);
    const [left, right] = await paintedEyeHeights(page, avatar);
    samples.push({ row: await paintedEyesRow(page, avatar), height: Math.min(left, right) });
  }
  const open = Math.max(...samples.map(sample => sample.height));
  return samples.filter(sample => sample.height >= open * 0.8).map(sample => sample.row);
}

/** One execution event of the turn, as the stream delivers it. */
function toolEvent(
  invocation: string,
  phase: 'started' | 'finished',
  outcome: 'succeeded' | 'failed' | null
) {
  return {
    type: 'execution_step',
    content: '',
    metadata: {
      step_type: 'activity',
      activity: {
        version: 1,
        run_id: 'e2e-wait',
        invocation_id: invocation,
        family: 'reading',
        intent: 'read',
        phase,
        outcome,
      },
    },
  };
}

test.describe('living companion', () => {
  test.use({ contextOptions: { reducedMotion: 'no-preference' } });

  test('looks at the field being typed in where it is, not below the face', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate();
    await mockApi(chatRoutes([]));
    // Parked on the right, half-way down: the field is down and to the LEFT of
    // the face, where the fixed look down of before would never have gone.
    await openLivingCompanion(page, { xPct: 78, yPct: 50 });
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    await page.locator('textarea').pressSequentially('Bonjour');
    await page.clock.runFor(600);
    await expect(avatar).toHaveAttribute('data-expression', 'attentive');
    // The screen declares the field; the face looks at its middle from where it
    // stands. The oracle is the geometry, read in the page.
    const expected = await page.evaluate(attribute => {
      const field = [...document.querySelectorAll(`[${attribute}="input"]`)].at(-1);
      const face = document.querySelector('.lia-eyes-widget');
      if (!field || !face) return null;
      const box = field.getBoundingClientRect();
      const at = face.getBoundingClientRect();
      const clamp = (value: number) => Math.min(1, Math.max(-1, value));
      return {
        x: clamp((box.left + box.width / 2 - (at.left + at.width / 2)) / (innerWidth / 2)),
        y: clamp((box.top + box.height / 2 - (at.top + at.height / 2)) / (innerHeight / 2)),
      };
    }, GAZE_TARGET_ATTRIBUTE);
    expect(expected, 'The composer must declare the field').not.toBeNull();
    expect(
      Math.hypot(expected!.x, expected!.y - 1),
      'The field must not sit straight below the face, or the look down would pass'
    ).toBeGreaterThan(0.2);
    // ...and not at the end of the eyes' travel either: a saturated look could
    // not tell the middle of the field from its edge.
    expect(Math.abs(expected!.y), 'The look must not be saturated').toBeLessThan(0.95);
    expect(Number(await avatar.getAttribute('data-gaze-x'))).toBeCloseTo(expected!.x, 2);
    expect(Number(await avatar.getAttribute('data-gaze-y'))).toBeCloseTo(expected!.y, 2);
  });

  test('lives the wait: acknowledges the message, reads while a tool reads, marks what it found', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Most of a minute of the face's own time, a frame at a time: WebKit takes
    // twice the default budget over it on a slow machine, and asserts the same.
    test.slow();
    await authenticate();
    await mockApi(chatRoutes([]));
    const { answerIs, writeAnswer, deliverAnswer } = await holdTheAnswer(page);
    await openLivingCompanion(page);
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    /** Advance until the face says so, one frame at a time; false if it never does. */
    const seen = async (attribute: string, value: string, withinMs: number) => {
      for (let elapsed = 0; elapsed <= withinMs; elapsed += 32) {
        if ((await avatar.getAttribute(attribute)) === value) return true;
        await page.clock.runFor(32);
      }
      return false;
    };
    const rig = (channel: string) =>
      avatar.evaluate(
        (root, name) => parseFloat((root as HTMLElement).style.getPropertyValue(name) || '0'),
        channel
      );

    // 1. The message leaves: the face acknowledges it, and the beat is PLAYED
    // (the brows it raises are the rig's, not an attribute).
    const restingBrow = await rig('--rig-brow-y-l');
    await page.locator('textarea').fill('Contrôle de l’attente');
    await page.locator('textarea').press('Enter');
    expect(await seen('data-gesture', 'perk', 3000), 'the message is acknowledged').toBe(true);
    let raised = 0;
    for (let elapsed = 0; elapsed < 400; elapsed += 32) {
      await page.clock.runFor(32);
      raised = Math.min(raised, (await rig('--rig-brow-y-l')) - restingBrow);
    }
    expect(raised, 'the acknowledgement raises the brows').toBeLessThan(-0.015);
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return answerIs('opened');
      })
      .toBe(true);

    // 2. A tool reads: the eyes walk lines — along one, back to the start of
    // the next — on a page that sits below them.
    await writeAnswer(toolEvent('read-1', 'started', null));
    expect(await seen('data-activity', 'reading', 3000), 'the tool is seen reading').toBe(true);
    let onThePage = 0;
    let returns = 0;
    let previous = await rig('--rig-gaze-x');
    let travelling = 0;
    const READING_MS = 9000;
    for (let elapsed = 0; elapsed < READING_MS; elapsed += 48) {
      await page.clock.runFor(48);
      const across = await rig('--rig-gaze-x');
      if ((await rig('--rig-gaze-y')) > 0.06) onThePage += 48;
      const step = across - previous;
      travelling = Math.sign(step) === Math.sign(travelling) ? travelling + step : step;
      if (travelling < -0.45) {
        returns += 1;
        travelling = 0;
      }
      previous = across;
      expect(await avatar.getAttribute('data-scene'), `${elapsed} ms into the reading`).toBe('');
    }
    expect(onThePage, 'the eyes stay on the page').toBeGreaterThan(READING_MS * 0.55);
    expect(returns, 'the eyes go back to the start of a line').toBeGreaterThanOrEqual(2);

    // 3. The tool comes back with a result: a blink, and the brows lift.
    await writeAnswer(toolEvent('read-1', 'finished', 'succeeded'));
    expect(await seen('data-gesture', 'brow-twitch', 3000), 'the result is marked').toBe(true);
    await page.clock.runFor(700);
    expect(await avatar.getAttribute('data-gesture')).toBeNull();

    // 4. A tool that fails is marked by nothing: the face celebrates evidence.
    await writeAnswer(toolEvent('read-2', 'started', null));
    expect(await seen('data-activity', 'reading', 3000)).toBe(true);
    await writeAnswer(toolEvent('read-2', 'finished', 'failed'));
    expect(await seen('data-activity', '', 3000), 'the failed tool is over').toBe(true);
    for (let elapsed = 0; elapsed < 900; elapsed += 32) {
      await page.clock.runFor(32);
      expect(await avatar.getAttribute('data-gesture'), 'a failure earns no mark').toBeNull();
    }

    await writeAnswer({ type: 'token', content: 'Voici ce que j’ai lu.', metadata: null });
    await writeAnswer({ type: 'done', content: '', metadata: null });
    await deliverAnswer();
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return page.getByText('Voici ce que j’ai lu.').isVisible();
      })
      .toBe(true);
  });

  test('follows the answer being written: looks at it, plays no scene, lets go when it is delivered', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Most of a minute of the face's own time, a frame at a time: WebKit takes
    // twice the default budget over it on a slow machine, and asserts the same.
    test.slow();
    await authenticate();
    await mockApi(chatRoutes([]));
    const { answerIs, writeAnswer, deliverAnswer } = await holdTheAnswer(page);
    await openLivingCompanion(page);
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    await page.locator('textarea').fill('Contrôle du regard');
    await page.locator('textarea').press('Enter');
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return answerIs('opened');
      })
      .toBe(true);
    await writeAnswer({ type: 'token', content: 'Voici le début', metadata: null });
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return page.getByText('Voici le début').isVisible();
      })
      .toBe(true);
    await page.clock.runFor(1200);
    await expect(avatar).toHaveAttribute('data-expression', 'attentive');
    // The screen declares the block being written; the face looks at its end
    // from where it stands. The oracle is the geometry, read in the page.
    const expected = await page.evaluate(attribute => {
      const block = [...document.querySelectorAll(`[${attribute}="answer"]`)].at(-1);
      const face = document.querySelector('.lia-eyes-widget');
      if (!block || !face) return null;
      const text = block.getBoundingClientRect();
      const box = face.getBoundingClientRect();
      const clamp = (value: number) => Math.min(1, Math.max(-1, value));
      return {
        x: clamp((text.left + text.width / 2 - (box.left + box.width / 2)) / (innerWidth / 2)),
        y: clamp(
          (Math.min(innerHeight, text.bottom) - (box.top + box.height / 2)) / (innerHeight / 2)
        ),
      };
    }, GAZE_TARGET_ATTRIBUTE);
    expect(expected, 'The thread must declare the answer being written').not.toBeNull();
    expect(
      Math.hypot(expected!.x, expected!.y),
      'The text must not sit under the face, or any look would pass'
    ).toBeGreaterThan(0.1);
    expect(Number(await avatar.getAttribute('data-gaze-x'))).toBeCloseTo(expected!.x, 2);
    expect(Number(await avatar.getAttribute('data-gaze-y'))).toBeCloseTo(expected!.y, 2);
    for (let elapsed = 0; elapsed < A_SCENE_WOULD_HAVE_PLAYED_MS; elapsed += 500) {
      await advanceSparsely(page);
      expect(await avatar.getAttribute('data-scene'), `${elapsed} ms into the answer`).toBe('');
      expect(await avatar.getAttribute('data-gesture')).toBeNull();
    }
    await writeAnswer({ type: 'done', content: '', metadata: null });
    await deliverAnswer();
    // Delivered: nothing is being written, and the screen declares no answer
    // being written (the composer's field stays declared: it is still there).
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return page.locator(`[${GAZE_TARGET_ATTRIBUTE}="answer"]`).count();
      })
      .toBe(0);
  });

  test('hands its answer over: looks at it as it presents it, then « à toi » once it was seen', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    test.slow();
    await authenticate();
    await mockApi(chatRoutes([]));
    const { answerIs, writeAnswer, deliverAnswer } = await holdTheAnswer(page);
    await openLivingCompanion(page, null, 'xl');
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    await page.clock.runFor(1200);
    const resting = await openEyesRows(page, avatar, [100, 100, 100]);
    expect(resting.length, 'The eyes must be painted open at rest').toBeGreaterThan(0);
    const atRest = resting.reduce((sum, row) => sum + row, 0) / resting.length;
    await page.locator('textarea').fill('Une question');
    await page.locator('textarea').press('Enter');
    await expect
      .poll(async () => {
        await page.clock.runFor(32);
        return answerIs('opened');
      })
      .toBe(true);
    await writeAnswer({ type: 'token', content: 'La réponse, posée là.', metadata: null });
    // The face follows the answer as it is written, as it does in real use: the
    // arrival of the answer's own face once it is delivered used to wipe the
    // presentation a commit after it started.
    await page.clock.runFor(1200);
    // The model declared a factual register and no accent, like 94 % of the
    // answers measured in production.
    await writeAnswer({
      type: 'done',
      content: '',
      metadata: { expressivity: { register: 'factual', intensity: 0.3, accent: 'none' } },
    });
    await deliverAnswer();
    await expect
      .poll(async () => {
        await page.clock.runFor(16);
        return avatar.getAttribute('data-gesture');
      })
      .toBe('present-factual');
    // The look at the answer holds from a few hundred milliseconds in, once the
    // look that followed the text has come back (measured: +6.5 px at xl, and
    // -0.2 px for a presentation that looks up instead): the eyes are PAINTED
    // lower than at rest, wherever the formula says they point.
    const rows = await openEyesRows(page, avatar, [450, 75, 75]);
    expect(rows.length, 'The eyes must be painted open while they look').toBeGreaterThan(0);
    expect(
      Math.min(...rows) - atRest,
      'The eyes must stay on the answer they present'
    ).toBeGreaterThan(3);
    // « À toi » comes once the presentation has been seen, and not before.
    await page.clock.runFor(HAND_OVER_AFTER_MS - 600 - 150);
    expect(await avatar.getAttribute('data-gesture')).toBe('present-factual');
    await page.clock.runFor(300);
    expect(await avatar.getAttribute('data-gesture')).toBe('listen');
  });

  test('fits phone and desktop viewports and actually performs a spontaneous scene', async ({
    page,
    authenticate,
    mockApi,
  }, testInfo) => {
    await authenticate();
    await mockApi(chatRoutes([]));
    await openLivingCompanion(page);
    const avatar = page.locator('[data-character="bip"] .lia-eyes').last();
    await waitForClockedHydration(page, avatar);
    await expect(avatar).toBeVisible();
    for (const width of [320, 375, 768, 1440]) {
      await page.setViewportSize({ width, height: 812 });
      await page.clock.runFor(500);
      const box = await avatar.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.y + box!.height).toBeLessThanOrEqual(812);
    }
    const restingMouth = await avatar.locator('[data-rig-mouth]').getAttribute('d');
    const advanceRestingBeat = () => advanceSparsely(page);
    let scene = '';
    for (let beat = 0; beat < 120 && !scene; beat++) {
      await advanceRestingBeat();
      scene = (await avatar.getAttribute('data-scene')) ?? '';
    }
    expect(scene).not.toBe('');
    await page.clock.runFor(1000);
    expect(await avatar.locator('[data-rig-mouth]').getAttribute('d')).not.toBe(restingMouth);
    const capture = testInfo.outputPath('bip-scene.png');
    await avatar.screenshot({ path: capture });
    await testInfo.attach('bip-scene', { path: capture, contentType: 'image/png' });
    // Keep every active scene frame. Only use sparse sampling after its end
    // is observed, while still advancing the full 12 seconds before the oracle.
    for (let remaining = 12_000; remaining > 0; remaining -= 500) {
      if ((await avatar.getAttribute('data-scene')) === '') {
        await advanceRestingBeat();
      } else {
        await page.clock.runFor(500);
      }
    }
    await expect(avatar).toHaveAttribute('data-scene', '');
  });
});
