import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCardComposition } from '../useCardComposition';
import type { CardCompositionDraft } from '@/types/card-actions';

const confirm = vi.fn();
beforeEach(() => confirm.mockReset());
vi.mock('@/components/ui/use-confirm', () => ({
  useConfirm: () => ({ confirm, confirmDialog: null }),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
const draft: CardCompositionDraft = {
  text: 'Please prepare a reply.',
  label: 'A subject',
  selection: {
    version: 1,
    message_id: '00000000-0000-0000-0000-000000000003',
    run_id: 'run-a',
    registry_id: 'email_a',
    action: 'reply',
  },
};

function mount(initialMessage = '') {
  const saveDraft = vi.fn();
  return {
    saveDraft,
    ...renderHook(() => useCardComposition({ initialMessage, saveDraft, disabled: false })),
  };
}

describe('card composition ownership of the draft', () => {
  it('opens an editable, unsent selection and persists text with its context', async () => {
    const { result, saveDraft } = mount();
    await act(() => result.current.onCompose(draft));
    expect(result.current.prefill.text).toBe(draft.text);
    expect(result.current.composition).toEqual(draft);
    act(() => result.current.onTextChange('Edited reply'));
    expect(saveDraft).toHaveBeenLastCalledWith('Edited reply', { ...draft, text: 'Edited reply' });
  });

  it('replaces a draft only after explicit consent and disables actions while chat is locked', async () => {
    confirm.mockResolvedValueOnce(true);
    const saveDraft = vi.fn();
    const { result, rerender } = renderHook(
      ({ disabled }) =>
        useCardComposition({
          initialMessage: 'Existing draft',
          saveDraft,
          disabled,
        }),
      { initialProps: { disabled: false } }
    );
    await act(() => result.current.onCompose(draft));
    expect(result.current.composition).toEqual(draft);
    rerender({ disabled: true });
    expect(result.current.onAvailableCompose).toBeUndefined();
    rerender({ disabled: false });
    expect(result.current.onAvailableCompose).toBe(result.current.onCompose);
  });

  it('preserves an existing draft on dismissal and rejects double clicks', async () => {
    let settle: (confirmed: boolean) => void = () => {};
    confirm.mockImplementationOnce(
      () =>
        new Promise<boolean>(resolve => {
          settle = resolve;
        })
    );
    const { result } = mount('Existing draft');
    let pending: Promise<void>;
    act(() => {
      pending = result.current.onCompose(draft);
    });
    await act(() => result.current.onCompose(draft));
    expect(confirm).toHaveBeenCalledTimes(1);
    await act(async () => {
      settle(false);
      await pending;
    });
    expect(result.current.prefill.nonce).toBe(0);
    expect(result.current.composition).toBeNull();
  });

  it('does not overwrite text edited while the replacement dialog was open', async () => {
    let settle: (confirmed: boolean) => void = () => {};
    confirm.mockImplementationOnce(
      () =>
        new Promise<boolean>(resolve => {
          settle = resolve;
        })
    );
    const { result } = mount('Existing draft');
    let pending: Promise<void>;
    act(() => {
      pending = result.current.onCompose(draft);
    });
    act(() => result.current.onTextChange('Newer typing'));
    await act(async () => {
      settle(true);
      await pending;
    });
    expect(result.current.prefill.nonce).toBe(0);
    expect(result.current.composition).toBeNull();
  });

  it('clears the context on empty input or another prefill without erasing typed text on removal', async () => {
    const { result, saveDraft } = mount();
    await act(() => result.current.onCompose(draft));
    act(() => result.current.removeComposition());
    expect(saveDraft).toHaveBeenLastCalledWith(draft.text);
    await act(() => result.current.onCompose(draft));
    act(() => result.current.prefillText('Unrelated question'));
    expect(result.current.composition).toBeNull();
    expect(result.current.prefill.text).toBe('Unrelated question');
    act(() => result.current.onTextChange(''));
    expect(saveDraft).toHaveBeenLastCalledWith('', undefined);
  });
});
