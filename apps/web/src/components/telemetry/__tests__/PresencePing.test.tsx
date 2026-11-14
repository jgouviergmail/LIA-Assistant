/**
 * Reading presence ping (ADR-214 amendment): sent on mount, on
 * visibilitychange→visible and on focus, throttled; never when hidden, never
 * unauthenticated, silent on failure — and never where the instance does not
 * learn habits: the route refuses under the operator's switch (ADR-280), and
 * a refusal swallowed on every page is a request nobody needed.
 */

import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PresencePing } from '@/components/telemetry/PresencePing';

const postMock = vi.fn();
const authState = { user: null as null | { id: string; is_active: boolean }, isLoading: false };
const configState = {
  value: null as null | {
    features: { habits_enabled?: boolean };
    capabilities?: Record<string, { enabled: boolean; family: string }>;
  },
  asked: [] as boolean[],
};

vi.mock('@/lib/api-client', () => ({
  default: { post: (...args: unknown[]) => postMock(...args) },
}));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => authState,
}));
vi.mock('@/hooks/useAppConfig', () => ({
  useAppConfig: (enabled = true) => {
    configState.asked.push(enabled);
    return { config: enabled ? configState.value : null };
  },
}));

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
}

describe('PresencePing', () => {
  beforeEach(() => {
    postMock.mockReset();
    postMock.mockResolvedValue(undefined);
    authState.user = { id: 'u1', is_active: true };
    authState.isLoading = false;
    configState.value = { features: { habits_enabled: true } };
    configState.asked = [];
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

  it('never pings where the operator switched the habits off, including on focus', () => {
    configState.value = {
      features: { habits_enabled: true },
      capabilities: { habits: { enabled: false, family: 'knowledge' } },
    };
    render(<PresencePing />);
    act(() => {
      window.dispatchEvent(new Event('focus'));
    });
    expect(postMock).not.toHaveBeenCalled();
  });

  it('never pings where the deployment does not learn habits, nor before the configuration answers', () => {
    configState.value = { features: { habits_enabled: false } };
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();

    configState.value = null;
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();
  });

  it('pings once the configuration says the habits are learned', () => {
    configState.value = null;
    const { rerender } = render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();

    configState.value = { features: { habits_enabled: true } };
    rerender(<PresencePing />);

    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it('asks the configuration for a signed-in person alone', () => {
    authState.user = null;
    render(<PresencePing />);

    expect(configState.asked).toEqual([false]);
  });

  it('never pings when unauthenticated or still loading', () => {
    authState.user = null;
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();
    authState.user = { id: 'u1', is_active: true };
    authState.isLoading = true;
    render(<PresencePing />);
    expect(postMock).not.toHaveBeenCalled();
  });

  it('never pings for an inactive account, including on focus', () => {
    authState.user = { id: 'u1', is_active: false };
    render(<PresencePing />);
    act(() => {
      window.dispatchEvent(new Event('focus'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(postMock).not.toHaveBeenCalled();
  });

  it('removes active listeners when the account becomes inactive', () => {
    const { rerender } = render(<PresencePing />);
    expect(postMock).toHaveBeenCalledTimes(1);
    authState.user = { id: 'u1', is_active: false };
    rerender(<PresencePing />);
    act(() => {
      vi.setSystemTime(new Date('2026-09-03T13:00:00Z'));
      window.dispatchEvent(new Event('focus'));
    });
    expect(postMock).toHaveBeenCalledTimes(1);
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
