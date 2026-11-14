/**
 * The chat reads the psyche only where the instance offers it (ADR-280).
 *
 * The message list hydrates LIA's mood for every thread it shows. The psyche
 * router refuses every route under the operator's switch, so each chat opened
 * on such an instance used to send two requests whose only possible answer was
 * a refusal — and showed nothing of it. The caller that holds the instance
 * configuration now says whether the psyche is offered.
 *
 * The oracle is the transport: the real query hooks run over a controlled
 * `apiClient`, and the account has an id — without one no account-scoped read
 * leaves at all, and « nothing asked » would prove nothing.
 */
import { act, cleanup, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/__tests__/test-utils';
import { usePsycheStore } from '@/stores/psycheStore';
import type { PsycheSettings } from '@/types/psyche';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({ user: { id: 'one', tokens_display_enabled: false } }),
}));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation: () => ({ mutate: vi.fn() }) }));
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get },
}));

import { ChatMessageList } from '../ChatMessageList';

const preferences: PsycheSettings = {
  psyche_enabled: true,
  psyche_display_avatar: true,
  psyche_sensitivity: 50,
  psyche_stability: 50,
};

/** Every read sent to the psyche router, in order. */
const psycheReads = () =>
  get.mock.calls.map(([endpoint]) => String(endpoint)).filter(url => url.startsWith('/psyche'));

beforeEach(() => {
  usePsycheStore.getState().reset();
  get
    .mockReset()
    .mockImplementation(async (endpoint: string) =>
      endpoint === '/psyche/settings' ? preferences : null
    );
});
afterEach(() => cleanup());

describe('ChatMessageList — the psyche of the thread', () => {
  it('hydrates the mood where the instance offers the psyche', async () => {
    await act(async () => renderWithProviders(<ChatMessageList messages={[]} psycheOffered />));

    await waitFor(() =>
      expect(psycheReads().sort()).toEqual(['/psyche/settings', '/psyche/state?initialize=false'])
    );
    await waitFor(() => expect(usePsycheStore.getState().enabled).toBe(true));
  });

  it('asks nothing of the psyche the instance has switched off', async () => {
    await act(async () =>
      renderWithProviders(<ChatMessageList messages={[]} psycheOffered={false} />)
    );
    // Long enough for a deferred first read to leave, had one been queued.
    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 30));
    });

    expect(psycheReads()).toEqual([]);
    // Nothing was read: the thread shows no mood of a capability that is off.
    expect(usePsycheStore.getState().enabled).toBe(false);
  });
});
