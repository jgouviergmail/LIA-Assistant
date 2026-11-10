import { beforeEach, expect, it, vi } from 'vitest';
import apiClient from '@/lib/api-client';
import { requestReadAloud } from '../speech';
import { ASSIST_TIMEOUT_MS } from '@/lib/workbench/assist';

vi.mock('@/lib/api-client', () => ({ default: { post: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

it('preserves the selected bytes and cancellation signal through the existing speech door', async () => {
  const received = { audio: 'SUQz', cut: true, cost_eur: 0.002, usage: null };
  vi.mocked(apiClient.post).mockResolvedValue(received);
  const signal = new AbortController().signal;
  expect(await requestReadAloud('/tool-assists/read-aloud', { text: '  字\n' }, signal)).toEqual(
    received
  );
  expect(apiClient.post).toHaveBeenCalledWith(
    '/tool-assists/read-aloud',
    { text: '  字\n' },
    { signal, timeout: ASSIST_TIMEOUT_MS }
  );
});

it.each([
  { audio: '', cut: false, cost_eur: 0, usage: null },
  { audio: '<script>', cut: false, cost_eur: 0, usage: null },
  { audio: 'SUQz', cut: false, cost_eur: -1, usage: null },
  { audio: 'SUQz', cost_eur: 0, usage: null },
])('refuses a malformed audio result before rendering a player: %j', async result => {
  vi.mocked(apiClient.post).mockResolvedValue(result);
  await expect(
    requestReadAloud('/tool-assists/read-aloud', { text: 'Words' }, new AbortController().signal)
  ).rejects.toThrow();
});
