/** Scope mismatches and vanished annexes cannot become Main or a permanent loading state. */
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { ConversationSummary } from '@/types/conversation';
import { useSelectedDiscussion } from '../useSelectedDiscussion';

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const row: ConversationSummary = {
  id: 'annex',
  user_id: 'owner',
  kind: 'secondary',
  revision: 2,
  title: 'Voyage',
  message_count: 0,
  total_tokens: 0,
  created_at: '2026-11-11T00:00:00Z',
  updated_at: '2026-11-11T00:00:00Z',
};
const location = { id: row.id, revision: 2, malformed: false };

beforeEach(() => api.get.mockReset());

it.each([null, { ...row, id: 'another-discussion' }, { ...row, user_id: 'another-account' }])(
  'refuses missing or mismatched metadata without publishing it as verified',
  async response => {
    api.get.mockResolvedValue(response);
    const verified = vi.fn();
    const { result } = renderHook(() => useSelectedDiscussion('owner', location, true, verified));
    await waitFor(() => expect(result.current.refused).toBe(true));
    expect(result.current.ready).toBe(false);
    expect(result.current.selected).toBeNull();
    expect(verified).toHaveBeenCalledWith(null);
  }
);

it('authorizes the exact annex and refuses a stale generation', async () => {
  api.get.mockResolvedValue(row);
  const verified = vi.fn();
  const { result, rerender } = renderHook(
    ({ revision }) => useSelectedDiscussion('owner', { ...location, revision }, true, verified),
    { initialProps: { revision: row.revision } }
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.selected).toEqual(row);
  rerender({ revision: row.revision - 1 });
  expect(result.current.refused).toBe(true);
  expect(result.current.ready).toBe(false);
});

it('admits a genuinely empty Main without creating it', async () => {
  api.get.mockResolvedValue(null);
  const { result } = renderHook(() =>
    useSelectedDiscussion('owner', { id: null, revision: null, malformed: false }, true, vi.fn())
  );
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.refused).toBe(false);
  expect(api.get).toHaveBeenCalledWith('/conversations/me', expect.anything());
});

it('never reads a malformed target', () => {
  const { result } = renderHook(() =>
    useSelectedDiscussion('owner', { ...location, malformed: true }, true, vi.fn())
  );
  expect(result.current.refused).toBe(true);
  expect(result.current.ready).toBe(false);
  expect(api.get).not.toHaveBeenCalled();
});
