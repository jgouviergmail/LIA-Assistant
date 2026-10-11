import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useApplicationAccountToast } from '../useApplicationAccountToast';

const notices = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: notices }));

describe('settings feedback account lifetime', () => {
  it('retires old feedback across an account change and a return to the same account', () => {
    const { result, rerender } = renderHook(({ owner }) => useApplicationAccountToast(owner), { initialProps: { owner: 'first' } });
    const retired = result.current;
    act(() => retired.success('owned saved state'));
    expect(notices.success).toHaveBeenCalledOnce();
    rerender({ owner: 'second' });
    act(() => retired.error('private previous account error'));
    expect(notices.error).not.toHaveBeenCalled();
    rerender({ owner: 'first' });
    act(() => retired.info('old private report'));
    expect(notices.info).not.toHaveBeenCalled();
    act(() => result.current.info('current account report'));
    expect(notices.info).toHaveBeenCalledExactlyOnceWith('current account report');
  });
});
