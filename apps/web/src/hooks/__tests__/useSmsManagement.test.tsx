import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const { useAuth, post } = vi.hoisted(() => ({ useAuth: vi.fn(), post: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({ useAuth }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { post },
}));
vi.mock('@/lib/logger', () => ({ logger: { error: vi.fn() } }));
import { useSmsManagement } from '../useSmsManagement';

const proposal = {
  command_id: 'df63b582-413f-4fd4-9f63-df30d1d3a4a2',
  operation_id: 'sms_token.create',
  content_digest: 'a'.repeat(64),
  before: { ingestion_token_to_create: null },
  after: { ingestion_token_to_create: { label: 'iPhone', source_id: null } },
  expires_at: '2099-01-01T00:00:00Z',
};
const completion = {
  outcome: {
    success: true,
    committed: true,
    phase: 'committed',
    no_op: false,
    values: {},
    error_code: null,
    interaction: null,
  },
  secret: { token: 'pi_once_only', id: proposal.command_id },
};
beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
});

it('proposes without confirmation, then returns the secret once to visible local state', async () => {
  post.mockResolvedValueOnce(proposal).mockResolvedValueOnce(completion);
  const { result } = renderHook(() => useSmsManagement());
  await act(async () => {
    await result.current.propose('sms_token.create', { label: 'iPhone' });
  });
  expect(post).toHaveBeenCalledTimes(1);
  expect(result.current.proposal?.command_id).toBe(proposal.command_id);
  expect(result.current.secret).toBeNull();
  await act(async () => {
    await result.current.confirm();
  });
  expect(post).toHaveBeenLastCalledWith(
    `/sms/commands/${proposal.command_id}/confirm`,
    { content_digest: proposal.content_digest },
    undefined
  );
  expect(result.current.secret).toBe('pi_once_only');
  expect(result.current.proposal).toBeNull();
  await act(async () => {
    await result.current.confirm();
  });
  expect(post).toHaveBeenCalledTimes(2);
  act(() => result.current.clearSecret());
  expect(result.current.secret).toBeNull();
});

it('does not show a late secret after an account switch or when returning to the same account', async () => {
  post.mockResolvedValueOnce(proposal);
  const { result, rerender } = renderHook(() => useSmsManagement());
  await act(async () => {
    await result.current.propose('sms_token.create', {});
  });
  let finish: ((value: typeof completion) => void) | undefined;
  post.mockImplementationOnce(
    () =>
      new Promise<typeof completion>(resolve => {
        finish = resolve;
      })
  );
  let pending: Promise<void> | undefined;
  act(() => {
    pending = result.current.confirm();
  });
  useAuth.mockReturnValue({ user: { id: 'other' } });
  rerender();
  await act(async () => {
    finish?.(completion);
    await pending;
  });
  expect(result.current.secret).toBeNull();
  useAuth.mockReturnValue({ user: { id: 'owner' } });
  rerender();
  expect(result.current.secret).toBeNull();
  expect(result.current.proposal).toBeNull();
});

it('consumes a confirmation after a lost acknowledgement instead of silently replaying it', async () => {
  post.mockResolvedValueOnce(proposal).mockRejectedValueOnce(new Error('lost acknowledgement'));
  const { result } = renderHook(() => useSmsManagement());
  await act(async () => {
    await result.current.propose('sms_token.create', {});
  });
  await act(async () => {
    await result.current.confirm();
  });
  expect(result.current.uncertain).toBe(true);
  expect(result.current.proposal).toBeNull();
  expect(result.current.secret).toBeNull();
  await act(async () => {
    await result.current.confirm();
  });
  expect(post).toHaveBeenCalledTimes(2);
});
