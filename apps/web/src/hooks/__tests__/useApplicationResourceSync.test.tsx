import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { publishApplicationResources } from '@/lib/application-resources';
import { useApplicationResourceSync } from '../useApplicationResourceSync';
const { warning } = vi.hoisted(() => ({ warning: vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: warning } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

describe('application resource invalidation', () => {
  it('reports a failed reread and allows the next invalidation to recover', async () => {
    const read = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const reset = vi.fn();
    const { unmount } = renderHook(() => useApplicationResourceSync('one', 'chat_shortcuts', read, reset));
    act(() => { publishApplicationResources('one', new Set(['chat_shortcuts'])); });
    await waitFor(() => expect(warning).toHaveBeenCalledWith('settings.application_tools.sync_failed'));
    expect(reset).not.toHaveBeenCalled();
    act(() => { publishApplicationResources('one', new Set(['chat_shortcuts'])); });
    await waitFor(() => expect(reset).toHaveBeenCalledTimes(1));
    unmount();
  });
  it('coalesces only the addressed account and resource and releases its override', async () => {
    let release: (() => void) | undefined;
    const held = new Promise<void>(resolve => { release = resolve; });
    const read = vi.fn().mockReturnValueOnce(held).mockResolvedValue(undefined);
    const reset = vi.fn();
    const { unmount } = renderHook(() => useApplicationResourceSync('one', 'chat_shortcuts', read, reset));
    act(() => {
      publishApplicationResources('two', new Set(['chat_shortcuts']));
      publishApplicationResources('one', new Set(['briefing_preferences']));
    });
    expect(read).not.toHaveBeenCalled();
    act(() => {
      publishApplicationResources('one', new Set(['chat_shortcuts']));
      publishApplicationResources('one', new Set(['chat_shortcuts']));
    });
    expect(read).toHaveBeenCalledTimes(1);
    await act(async () => { release?.(); });
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(reset).toHaveBeenCalledTimes(1);
    unmount();
    act(() => { publishApplicationResources('one', new Set(['chat_shortcuts'])); });
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('never applies an obsolete response after unmount', async () => {
    let release: (() => void) | undefined;
    const held = new Promise<void>(resolve => { release = resolve; });
    const read = vi.fn().mockReturnValue(held);
    const reset = vi.fn();
    const { unmount } = renderHook(() => useApplicationResourceSync('one', 'briefing_preferences', read, reset));
    act(() => { publishApplicationResources('one', new Set(['briefing_preferences'])); });
    unmount();
    await act(async () => { release?.(); });
    expect(reset).not.toHaveBeenCalled();
  });
});
