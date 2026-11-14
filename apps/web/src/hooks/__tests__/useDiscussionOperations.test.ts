/** Lifecycle transport keeps its confirmation identity and reconciles unknown outcomes once. */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import type { ConversationOperationResult, ConversationSummary } from '@/types/conversation';
import { useDiscussionOperations } from '../useDiscussionOperations';

const api = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  get: vi.fn(),
}));
vi.mock('@/lib/api-client', async original => ({
  ...(await original<typeof import('@/lib/api-client')>()),
  default: api,
}));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

const target: ConversationSummary = {
  id: 'annex',
  user_id: 'owner',
  kind: 'secondary',
  revision: 2,
  title: 'Voyage',
  message_count: 4,
  total_tokens: 20,
  created_at: '2026-11-11T00:00:00Z',
  updated_at: '2026-11-11T00:00:00Z',
};
const receipt: ConversationOperationResult = {
  operation_id: 'confirmed-delete',
  conversation_id: target.id,
  old_revision: target.revision,
  new_revision: null,
  previous_message_count: 4,
  logical_applied: true,
  cleanup_complete: false,
  state: 'pending',
  replayed: true,
};

beforeEach(() => {
  for (const method of Object.values(api)) method.mockReset();
});

it('reconciles a lost deletion reply through its receipt without repeating the DELETE', async () => {
  api.delete.mockRejectedValue(new Error('Lost acknowledgement'));
  api.get.mockResolvedValue(receipt);
  const hook = renderHook(() => useDiscussionOperations('owner'));
  let result: ConversationOperationResult | undefined;
  await act(async () => {
    result = await hook.result.current.retire(target, 'delete', receipt.operation_id);
  });
  expect(result).toEqual(receipt);
  expect(api.delete).toHaveBeenCalledOnce();
  expect(api.delete).toHaveBeenCalledWith(
    '/conversations/annex',
    expect.objectContaining({
      body: JSON.stringify({
        operation_id: receipt.operation_id,
        expected_revision: target.revision,
      }),
      headers: { 'content-type': 'application/json' },
    })
  );
  expect(api.get).toHaveBeenCalledWith(
    '/conversations/operations/confirmed-delete',
    expect.anything()
  );
});

it('propagates an explicit busy refusal without querying a receipt or repeating the mutation', async () => {
  const busy = new ApiError('Busy', 409, { detail: { error: 'conversation_busy' } });
  api.delete.mockRejectedValue(busy);
  const hook = renderHook(() => useDiscussionOperations('owner'));
  await act(async () => {
    await expect(hook.result.current.retire(target, 'delete', receipt.operation_id)).rejects.toBe(
      busy
    );
  });
  expect(api.delete).toHaveBeenCalledOnce();
  expect(api.get).not.toHaveBeenCalled();
});

it.each([
  { ...receipt, conversation_id: 'another-discussion' },
  { ...receipt, old_revision: target.revision - 1 },
  { ...receipt, new_revision: target.revision + 1 },
])('rejects a receipt that does not confirm the reviewed deletion', async response => {
  api.delete.mockResolvedValue(response);
  const hook = renderHook(() => useDiscussionOperations('owner'));
  await act(async () => {
    await expect(
      hook.result.current.retire(target, 'delete', receipt.operation_id)
    ).rejects.toThrow();
  });
});

it('cannot delete Main or a foreign discussion even through a retained action callback', async () => {
  const hook = renderHook(() => useDiscussionOperations('owner'));
  await expect(
    hook.result.current.retire({ ...target, kind: 'main' }, 'delete', receipt.operation_id)
  ).rejects.toThrow();
  await expect(
    hook.result.current.retire({ ...target, user_id: 'other' }, 'delete', receipt.operation_id)
  ).rejects.toThrow();
  expect(api.delete).not.toHaveBeenCalled();
});

it('cannot accept a late acknowledgement after its authenticated owner retires', async () => {
  const delayed = Promise.withResolvers<ConversationOperationResult>();
  api.delete.mockReturnValue(delayed.promise);
  const hook = renderHook(() => useDiscussionOperations('owner'));
  const deleting = hook.result.current.retire(target, 'delete', receipt.operation_id);
  hook.unmount();
  delayed.resolve(receipt);
  await expect(deleting).rejects.toMatchObject({ name: 'AbortError' });
  expect(api.get).not.toHaveBeenCalled();
});
