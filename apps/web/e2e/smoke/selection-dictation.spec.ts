/** Native Chromium recorder, controlled STT, caret insertion and cancellation. */
import { test, expect, waitForHydration, waitForMockGate } from '../fixtures';
import {
  selectionRoutes,
  undoNativeEdit,
  dictationEnabled as enabled,
} from '../fixtures/selection-assist';
import en from '../../locales/en/translation.json';

test.use({
  launchOptions: {
    args: [
      '--disable-features=AutofillServerCommunication',
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
    ],
  },
});
test.skip(
  ({ browserName }) => browserName !== 'chromium',
  'Chromium alone supplies a fake microphone through these launch flags.'
);

test('dictates at the caret, keeps native undo, and releases the socket when leaving the field', async ({
  page,
  context,
  authenticate,
  mockApi,
  browserName,
}, testInfo) => {
  await context.grantPermissions(['microphone']);
  await authenticate();
  let ticketCount = 0;
  let pendingTickets = 0;
  let releasePrewarm!: () => void;
  const recordingRequested = new Promise<void>(resolve => {
    releasePrewarm = resolve;
  });
  await mockApi([
    ...selectionRoutes,
    enabled,
    {
      url: '**/api/v1/voice/ticket',
      method: 'POST',
      handler: async (route, signal) => {
        const id = ++ticketCount;
        pendingTickets++;
        try {
          // Force startup to overtake the existing idle prewarm. Both connections
          // must close; a fixed one-socket-per-recording count misses this race.
          if (id === 2) releasePrewarm();
          if (id === 1 && !(await waitForMockGate(recordingRequested, signal))) return;
          await route.fulfill({
            json: { ticket: `hermetic-dictation-${id}`, ttl_seconds: 30 },
          });
        } finally {
          pendingTickets--;
        }
      },
    },
  ]);
  const opened = new Set<string>();
  const closed = new Set<string>();
  const events: { id: string; event: 'open' | 'close' }[] = [];
  let chunks = 0;
  await page.routeWebSocket('**/api/v1/voice/ws/audio?ticket=hermetic-dictation-*', socket => {
    const id = socket.url();
    opened.add(id);
    events.push({ id, event: 'open' });
    socket.onClose(() => {
      closed.add(id);
      events.push({ id, event: 'close' });
    });
    socket.onMessage(message => {
      if (typeof message !== 'string') chunks++;
      if (message === 'PING') socket.send(JSON.stringify({ type: 'pong' }));
      if (message === 'END')
        socket.send(JSON.stringify({ type: 'transcription', text: 'Hello', duration_seconds: 1 }));
    });
  });
  await page.goto('/en/dashboard/tools/mail');
  await waitForHydration(page, 'main');
  await page.getByRole('button', { name: 'New email', exact: true }).first().click();
  const form = page.getByRole('dialog', { name: 'New email', exact: true });
  const subject = form.getByRole('textbox', { name: 'Subject', exact: true });
  const message = form.getByRole('textbox', { name: 'Message', exact: true });
  await subject.fill(', friend');
  await subject.press('Home');
  const caret = page.getByRole('toolbar', { name: en.selectionAssist.voice.dictate });
  await expect(caret).toBeVisible();
  expect(ticketCount).toBe(0);
  expect(opened.size).toBe(0);
  await caret.getByRole('button', { name: 'Dictate', exact: true }).click();
  await expect.poll(() => chunks).toBeGreaterThan(0);
  await caret.getByRole('button', { name: en.selectionAssist.voice.stop_dictation }).click();
  await expect(subject).toHaveValue('Hello, friend');
  await expect
    .poll(() => pendingTickets === 0 && opened.size === ticketCount && closed.size === opened.size)
    .toBe(true);
  expect(ticketCount).toBeGreaterThanOrEqual(2);
  await undoNativeEdit(subject, browserName);
  await expect(subject).toHaveValue(', friend');
  await subject.press('End');
  const previousChunks = chunks;
  await caret.getByRole('button', { name: 'Dictate', exact: true }).click();
  await expect.poll(() => chunks).toBeGreaterThan(previousChunks);
  await message.focus();
  await expect
    .poll(() => pendingTickets === 0 && opened.size === ticketCount && closed.size === opened.size)
    .toBe(true);
  await expect(
    caret.getByRole('button', { name: en.selectionAssist.voice.stop_dictation })
  ).toHaveCount(0);
  await expect(subject).toHaveValue(', friend');
  await expect(message).toHaveValue('');
  await testInfo.attach('dictation-connection-lifetimes', {
    body: JSON.stringify({ ticketCount, pendingTickets, events }, null, 2),
    contentType: 'application/json',
  });
});
