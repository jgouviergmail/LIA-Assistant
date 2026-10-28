/** The inert host resets only its own fixture admission budget between journeys. */
import { test, expect, type APIRequestContext } from './fixtures';

/** A bound on the probe itself, never a copy of the route's own limit. */
const PROBE_LIMIT = 64;

/** Tickets the route grants before its first refusal: the real per-account budget. */
async function ticketBudget(
  request: APIRequestContext,
  headers: Record<string, string>
): Promise<number> {
  for (let granted = 0; granted < PROBE_LIMIT; granted++) {
    const status = (
      await request.post('/api/v1/world/ticket', { headers, data: { consent: true } })
    ).status();
    if (status === 429) return granted;
    expect(status).toBe(200);
  }
  throw new Error(`The ticket route granted ${PROBE_LIMIT} tickets: its limit is gone`);
}

test('proof reset restores admission without relaxing its real per-account limit', async ({
  browser,
  baseURL,
}) => {
  if (!baseURL) throw new Error('Explicit disposable proof required');
  const context = await browser.newContext({ baseURL });
  const headers = { Origin: new URL(baseURL).origin };
  try {
    expect(
      (
        await context.request.post('/api/v1/world-proof/session', { headers, data: { index: 8 } })
      ).status()
    ).toBe(200);
    const budget = await ticketBudget(context.request, headers);
    expect(budget).toBeGreaterThan(0);
    expect((await context.request.post('/api/v1/world-proof/reset', { headers })).status()).toBe(
      204
    );
    // Restored, and exactly as bounded as before: the reset relaxes nothing.
    expect(await ticketBudget(context.request, headers)).toBe(budget);
  } finally {
    await context.close();
  }
});
