import { afterEach, describe, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { readSelectionAnswer, requestSelection } from '../transport';
import { selectionAnswerSchema, type SelectionOffer } from '../contracts';

afterEach(() => vi.restoreAllMocks());

function response(parts: string[]) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        parts.forEach(part => controller.enqueue(encoder.encode(part)));
        controller.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } }
  );
}
describe('selection response stream', () => {
  const schedule = {
    freq: 'monthly',
    anchor_date: '2030-11-12',
    interval: 1,
    byweekday: [],
    bymonthday: [],
    bymonth: [],
    nth_weekday: [-1, 1],
    times: { mode: 'at', at: [{ hour: 9, minute: 0 }], step_minutes: null, start: null, end: null },
    end: { kind: 'after_count', after_count: 3, on_date: null },
  };
  it.each([
    { kind: 'ticket', ticket: { title: 'Call Ana', description: 'Ask about the quote' } },
    { kind: 'reminder', reminder: { content: 'Call Ana', recurrence: schedule } },
    {
      kind: 'reminder',
      reminder: {
        content: 'Review the monthly notes',
        recurrence: { ...schedule, bymonthday: [-1, 1, 31], nth_weekday: null },
      },
    },
    { kind: 'reminder', reminder: { content: 'Call Ana', recurrence: null } },
  ])('keeps reviewable native fields through the terminal stream ($kind)', async proposal => {
    const result = { proposal, usage: null };
    await expect(
      readSelectionAnswer(response([`data: ${JSON.stringify({ result })}\n\n`]))
    ).resolves.toEqual(result);
  });
  it.each([
    { kind: 'ticket', ticket: { title: ' ', description: '' } },
    { kind: 'reminder', reminder: { content: '', recurrence: null } },
    {
      kind: 'reminder',
      reminder: { content: 'Call Ana', recurrence: { ...schedule, anchor_date: '2030-02-30' } },
    },
    {
      kind: 'reminder',
      reminder: {
        content: 'Call Ana',
        recurrence: { ...schedule, times: { ...schedule.times, at: [{ hour: 24, minute: 0 }] } },
      },
    },
    {
      kind: 'reminder',
      reminder: { content: 'Call Ana', recurrence: { ...schedule, nth_weekday: [0, 8] } },
    },
  ])('refuses a malformed native proposal before it can reach a form ($kind)', async proposal => {
    const value = response([`data: ${JSON.stringify({ result: { proposal, usage: null } })}\n\n`]);
    await expect(readSelectionAnswer(value)).rejects.toThrow();
    expect(value.body?.locked).toBe(false);
  });
  it.each([0, -2, 32, 1.5])(
    'refuses an invalid monthly selector (%s) without retaining the reader',
    async day => {
      const proposal = {
        kind: 'reminder',
        reminder: {
          content: 'Review the monthly notes',
          recurrence: { ...schedule, bymonthday: [day], nth_weekday: null },
        },
      };
      const value = response([
        `data: ${JSON.stringify({ result: { proposal, usage: null } })}\n\n`,
      ]);
      await expect(readSelectionAnswer(value)).rejects.toThrow();
      expect(value.body?.locked).toBe(false);
    }
  );
  it.each(['explain', 'internet'])('uses the full published deadline for %s', async action => {
    const send = vi.spyOn(apiClient, 'postResponse').mockRejectedValue(new Error('offline'));
    const offer: SelectionOffer = {
      text_max_chars: 8000,
      question_max_chars: 500,
      language_max_chars: 40,
      internet_available: true,
      read_aloud_available: true,
      internet_timeout_seconds: 360,
      call_timeout_seconds: 240,
      heartbeat_seconds: 12,
      destinations: [],
    };
    await expect(
      requestSelection('/selection', { action }, new AbortController().signal, offer)
    ).rejects.toThrow('offline');
    expect(send.mock.calls[0][2]?.timeout).toBe((action === 'internet' ? 384 : 264) * 1000);
    expect(send).toHaveBeenCalledTimes(1);
  });
  it.each([
    'not a URL',
    'javascript:alert(1)',
    'data:text/html,unsafe',
    'https://user:password@example.test',
  ])('rejects an unsafe research source: %s', url => {
    expect(
      selectionAnswerSchema.safeParse({
        proposal: {
          kind: 'research',
          query: 'Query',
          provider: 'brave',
          summary: null,
          sources: [{ title: 'Source', url, excerpt: '' }],
        },
        usage: null,
      }).success
    ).toBe(false);
  });
  it("accepts the instance's web search as a research provider (lot 18)", () => {
    expect(
      selectionAnswerSchema.safeParse({
        proposal: {
          kind: 'research',
          query: 'Query',
          provider: 'searxng',
          summary: null,
          sources: [{ title: 'Source', url: 'https://example.test/a', excerpt: '' }],
        },
        usage: null,
      }).success
    ).toBe(true);
  });
  it.each([
    new Response(null, { headers: { 'Content-Type': 'text/event-stream' } }),
    new Response('{}', { headers: { 'Content-Type': 'application/json' } }),
  ])('refuses a response that cannot carry the promised stream', async value => {
    await expect(readSelectionAnswer(value)).rejects.toThrow('Expected an assistance stream');
  });
  it('bounds an unfinished frame and releases the failed reader', async () => {
    const value = response(['data: ' + 'x'.repeat(1024 * 1024)]);
    await expect(readSelectionAnswer(value)).rejects.toThrow('Assistance frame exceeds its bound');
    expect(value.body?.locked).toBe(false);
  });
  it('refuses invalid UTF-8 without leaving the stream locked', async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([0xff]));
        controller.close();
      },
    });
    await expect(
      readSelectionAnswer(
        new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
      )
    ).rejects.toThrow();
    expect(stream.locked).toBe(false);
  });
  it('honours the published slot deadline and never repeats a lost paid answer', async () => {
    const send = vi
      .spyOn(apiClient, 'postResponse')
      .mockRejectedValue(new TypeError('Lost response'));
    const controller = new AbortController();
    const body = { text: 'A sentence', mode: 'read', action: 'explain' };
    await expect(
      requestSelection('/tool-assists/text/selection/stream', body, controller.signal, {
        text_max_chars: 8000,
        question_max_chars: 500,
        language_max_chars: 40,
        internet_available: true,
        read_aloud_available: true,
        internet_timeout_seconds: 360,
        call_timeout_seconds: 240,
        heartbeat_seconds: 12,
        destinations: [],
      })
    ).rejects.toThrow('Lost response');
    expect(send).toHaveBeenCalledExactlyOnceWith('/tool-assists/text/selection/stream', body, {
      signal: controller.signal,
      timeout: 264000,
    });
  });
  it('reads a fragmented terminal answer after heartbeats', async () => {
    const value = { proposal: { kind: 'text', text: '你好' }, usage: null };
    const frame = `data: ${JSON.stringify({ result: value })}\n\n`;
    expect(
      await readSelectionAnswer(response([': waiting\n\n', frame.slice(0, 17), frame.slice(17)]))
    ).toEqual(value);
  });
  it('a successful HTTP stream can still carry a typed refusal', async () => {
    await expect(
      readSelectionAnswer(
        response(['data: {"error":{"status":429,"detail":{"code":"assist_quota"}}}\n\n'])
      )
    ).rejects.toMatchObject({ status: 429, data: { detail: { code: 'assist_quota' } } });
  });
  it('a failed transport cleanup cannot erase an explicit terminal answer', async () => {
    const value = { proposal: { kind: 'text', text: 'Done' }, usage: null };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify({ result: value })}\n\n`)
        );
      },
      cancel() {
        throw new TypeError('Already disconnected');
      },
    });
    await expect(
      readSelectionAnswer(
        new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
      )
    ).resolves.toEqual(value);
    expect(stream.locked).toBe(false);
  });
  it.each([
    ': waiting\n\n',
    'data: {}\n\n',
    'data: {"result":{"proposal":{"kind":"text","text":12},"usage":null}}\n\n',
  ])('refuses an incomplete or malformed answer', async frame => {
    await expect(readSelectionAnswer(response([frame]))).rejects.toThrow();
  });
});
