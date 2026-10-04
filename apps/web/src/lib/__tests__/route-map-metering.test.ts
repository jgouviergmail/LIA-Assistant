import { afterEach, expect, it, vi } from 'vitest';
import { apiClient } from '../api-client';
import { reportRouteMapLoad } from '../route-map-metering';
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it('keeps the grant through network retries and permits keepalive after navigation', async () => {
  vi.useFakeTimers();
  const post = vi
    .spyOn(apiClient, 'post')
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue({ recorded: true });
  const result = reportRouteMapLoad('signed-grant');
  await vi.advanceTimersByTimeAsync(301);
  await result;
  expect(post.mock.calls).toEqual(
    Array(2).fill([
      '/connectors/google-maps/load-reports',
      { load_token: 'signed-grant' },
      { keepalive: true, timeout: 5000 },
    ])
  );
});
it('bounds permanent failure and rejects instead of pretending a load was recorded', async () => {
  vi.useFakeTimers();
  const post = vi.spyOn(apiClient, 'post').mockRejectedValue(new Error('offline'));
  const result = reportRouteMapLoad('grant');
  const witness = expect(result).rejects.toThrow('offline');
  await vi.runAllTimersAsync();
  await witness;
  expect(post).toHaveBeenCalledTimes(3);
});
