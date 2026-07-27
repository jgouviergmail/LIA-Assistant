/**
 * Warning before the quota wall (A5).
 *
 * The backend grades usage (`warning` ≥80 %, `critical` ≥95 %) and returns
 * every dimension plus the cycle boundaries; the chat read `is_blocked` and
 * threw the rest away. The limit was therefore invisible until it stopped the
 * user mid-task, with no indication of when it would lift.
 *
 * Proven here against the real page: the warning appears while the user can
 * still act, it never doubles up with the blocking banner, and a healthy
 * account sees nothing.
 */
import { test, expect, type MockRoute } from '../fixtures';

const CHAT: MockRoute[] = [
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [],
      conversation_id: null,
      total_count: 0,
      has_more: false,
      next_cursor: null,
    },
  },
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
];

/** A dimension at `pct` of its limit (null = unlimited). */
function detail(pct: number | null) {
  return {
    current: pct ?? 0,
    limit: pct === null ? null : 100,
    usage_pct: pct,
    exceeded: pct !== null && pct >= 100,
  };
}

/** A `/usage-limits/me` payload with the given status and token usage. */
function usage(status: string, pct: number | null, isBlocked = false) {
  return {
    url: '**/api/v1/usage-limits/me',
    json: {
      status,
      is_blocked: isBlocked,
      blocked_reason: isBlocked ? 'Quota exceeded' : null,
      cycle_tokens: detail(pct),
      cycle_messages: detail(null),
      cycle_cost: detail(null),
      absolute_tokens: detail(null),
      absolute_messages: detail(null),
      absolute_cost: detail(null),
      cycle_start: '2026-07-01T00:00:00Z',
      cycle_end: '2026-08-01T00:00:00Z',
    },
  };
}

test.describe('quota warning', () => {
  test('warns while the user can still act', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([usage('warning', 84), ...CHAT]);
    await page.goto('/fr/dashboard/chat');

    const banner = page.getByRole('status').filter({ hasText: /quota/ });
    await expect(banner).toBeVisible({ timeout: 30_000 });
    await expect(banner).toContainText('84');
    // The reset date must be readable, never a raw ISO instant.
    await expect(banner).not.toContainText('2026-08-01T00:00:00Z');

    // Crucially: the composer still works. This is a warning, not a wall.
    await expect(page.getByRole('textbox').first()).toBeEnabled();
  });

  test('stays quiet on a healthy account', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi([usage('ok', 12), ...CHAT]);
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByRole('textbox').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('status').filter({ hasText: /quota/ })).toHaveCount(0);
  });

  test('gives way to the blocking banner once blocked', async ({ page, authenticate, mockApi }) => {
    // Two messages about the same wall would be noise at the worst moment.
    await authenticate({ language: 'fr' });
    await mockApi([usage('blocked_limit', 100, true), ...CHAT]);
    await page.goto('/fr/dashboard/chat');

    await expect(page.getByRole('textbox').first()).toBeDisabled({ timeout: 30_000 });
    await expect(page.getByRole('status').filter({ hasText: /quota/ })).toHaveCount(0);
  });
});
