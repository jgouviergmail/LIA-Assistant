/**
 * Reading presence ping (ADR-214 amendment): sent on mount, on
 * visibilitychange→visible and on focus, throttled; never when hidden, never
 * unauthenticated, silent on failure.
 */

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PresencePing } from '@/components/telemetry/PresencePing';

const postMock = vi.fn();
const authState = { user: null as null | { id: string }, isLoading: false };

vi.mock('@/lib/api-client', () => ({
  default: { post: (...args: unknown[]) => postMock(...args) },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => authState,
}));

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
}

describe('PresencePing', () => {
  beforeEach(() => {
    postMock.mockReset();
    postMock.mockResolvedValue(undefined);
    authState.user = { id: 'u1' };
    authState.isLoading = false;
    setVisibility('visible');
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-03T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('pings once on mount for an authenticated, visible user', () => {
    render(<PresencePing />);
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock).toHaveBeenCalledWith('/habits/presence');
  });

  it('never pings when unauthenticated or still loading', () => {
    authState.user = null;
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();
    authState.user = { id: 'u1' };
    authState.isLoading = true;
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();
  });

  it('never pings while the document is hidden', () => {
    setVisibility('hidden');
    render(<PresencePing />);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('focus'));
    });
    expect(postMock).not.toHaveBeenCalled();
  });

  it('throttles: a focus inside the window is dropped, one after it is sent', () => {
    render(<PresencePing />);
    expect(postMock).toHaveBeenCalledTimes(1);
    act(() => {
      vi.setSystemTime(new Date('2026-09-03T12:05:00Z'));
      window.dispatchEvent(new Event('focus'));
    });
    expect(postMock).toHaveBeenCalledTimes(1);
    act(() => {
      vi.setSystemTime(new Date('2026-09-03T12:20:00Z'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(postMock).toHaveBeenCalledTimes(2);
  });

  it('stays silent when the API call fails', async () => {
    postMock.mockRejectedValueOnce(new Error('offline'));
    expect(() => render(<PresencePing />)).not.toThrow();
    await act(async () => {
      await Promise.resolve();
    });
    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it('removes its listeners on unmount', () => {
    const { unmount } = render(<PresencePing />);
    unmount();
    act(() => {
      vi.setSystemTime(new Date('2026-09-03T13:00:00Z'));
      window.dispatchEvent(new Event('focus'));
    });
    expect(postMock).toHaveBeenCalledTimes(1);
  });
});
