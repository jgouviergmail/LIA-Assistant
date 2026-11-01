/**
 * The composer's state (ADR-369, Review focus 3): a second press that lands
 * before the render showing the first sends nothing; one key per open
 * composer, kept across a refusal the person fixes; a draft whose words
 * changed is saved before it is sent, and sent at the revision just saved.
 */

import { describe, expect, it, vi } from 'vitest';

import { act, renderHook } from '@/__tests__/test-utils';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { ApiError } from '@/lib/api-client';
import type { ComposerTarget } from '@/lib/workbench/mail-compose';

import { useComposer } from '../useComposer';

function writing(overrides: Partial<WorkbenchMailWriting> = {}): WorkbenchMailWriting {
  return {
    send: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    reply: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    forward: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    saveDraft: vi.fn(),
    sendDraft: vi.fn().mockResolvedValue({ id: 's1', thread_id: 't1' }),
    ...overrides,
  };
}

function composer(target: ComposerTarget, write: WorkbenchMailWriting) {
  return renderHook(() =>
    useComposer({
      target,
      writing: write,
      recipientsMax: 100,
      onSent: vi.fn(),
      onDraftSaved: vi.fn(),
    })
  );
}

describe('useComposer', () => {
  it('sends nothing for a second press that lands before the first is shown', async () => {
    let answer!: (value: unknown) => void;
    const write = writing({
      send: vi.fn().mockReturnValue(new Promise(resolve => (answer = resolve))),
    });
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org' }));

    let first!: Promise<void>;
    let second!: Promise<void>;
    act(() => {
      first = result.current.send();
      second = result.current.send();
    });
    await act(async () => {
      answer({ id: 's1', thread_id: 't1' });
      await Promise.all([first, second]);
    });

    expect(write.send).toHaveBeenCalledTimes(1);
  });

  it('keeps its one key across a refusal the person fixes', async () => {
    const send = vi
      .fn()
      .mockRejectedValueOnce(
        new ApiError('refused', 429, { detail: { code: 'provider_rate_limited' } })
      )
      .mockResolvedValueOnce({ id: 's1', thread_id: 't1' });
    const { result } = composer({ kind: 'new' }, writing({ send }));
    act(() => result.current.set({ to: 'ana@example.org' }));

    await act(() => result.current.send());
    expect(result.current.problem).toEqual({
      key: 'workbench.errors.provider_rate_limited',
      field: undefined,
      values: undefined,
    });
    await act(() => result.current.send());

    const [[first], [second]] = send.mock.calls;
    expect(second.idempotency_key).toBe(first.idempotency_key);
  });

  it('sends a new message saved as a draft AS that draft, never as a second copy', async () => {
    const saveDraft = vi.fn().mockResolvedValue({ id: 'd1', revision: 'r1' });
    const write = writing({ saveDraft });
    const { result } = composer({ kind: 'new' }, write);
    act(() => result.current.set({ to: 'ana@example.org', body: 'Hello' }));
    await act(() => result.current.saveDraft());

    await act(() => result.current.send());

    expect(write.send).not.toHaveBeenCalled();
    expect(write.sendDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd1', expected_revision: 'r1' })
    );
  });

  it('never saves a draft without the files the person chose: the draft could not keep them', async () => {
    const write = writing();
    const { result } = composer({ kind: 'new' }, write);
    act(() =>
      result.current.set({
        to: 'ana@example.org',
        files: [
          {
            id: 'f1',
            filename: 'report.pdf',
            mime_type: 'application/pdf',
            size: 10,
            origin: 'upload',
            expires_at: null,
          },
        ],
      })
    );

    await act(() => result.current.saveDraft());

    expect(write.saveDraft).not.toHaveBeenCalled();
    expect(result.current.problem).toEqual({ key: 'workbench.mail.compose.draft_no_files' });
  });

  it('saves a changed draft first, then sends the revision just saved', async () => {
    const saveDraft = vi.fn().mockResolvedValue({ id: 'd2', revision: 'r2' });
    const write = writing({ saveDraft });
    const { result } = composer(
      {
        kind: 'draft',
        draft: {
          id: 'd1',
          revision: 'r1',
          to: [{ name: '', address: 'ana@example.org' }],
          cc: [],
          bcc: [],
          subject: 'Plan',
          body: 'Old',
          attachments: [],
          updated_at: null,
        },
      },
      write
    );
    act(() => result.current.set({ body: 'New' }));

    await act(() => result.current.send());

    expect(saveDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd1', expected_revision: 'r1', body: 'New' })
    );
    expect(write.sendDraft).toHaveBeenCalledWith(
      expect.objectContaining({ draft_id: 'd2', expected_revision: 'r2' })
    );
  });
});
