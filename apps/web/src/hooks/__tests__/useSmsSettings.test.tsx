import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'owner' } }) }));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: { get },
}));
import { useSmsSettings } from '../useSmsSettings';
import { publishApplicationResources } from '@/lib/application-resources';
it('refreshes current metadata from its first page after a source mutation', async () => {
  get.mockResolvedValue({
    tokens: [],
    blocks: [],
    total: 0,
    as_of: '2026-10-19T00:00:00Z',
    next_cursor: null,
  });
  const { result } = renderHook(() => useSmsSettings());
  await waitFor(() => expect(result.current.tokens.data).toBeDefined());
  act(() => result.current.setTokenCursor({ after_id: 'old', as_of: '2026-10-19T00:00:00Z' }));
  await waitFor(() =>
    expect(get.mock.calls.some(call => call[1]?.params?.after_id === 'old')).toBe(true)
  );
  act(() => publishApplicationResources('owner', new Set(['sms'])));
  await waitFor(() => expect(result.current.tokenCursor).toBeUndefined());
  expect(get.mock.lastCall?.[1]?.params?.after_id).toBeUndefined();
});
