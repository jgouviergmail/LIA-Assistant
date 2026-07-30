/**
 * peers-error-messages — backend `peers_*` codes → localized toast keys.
 *
 * The mapping is the frontend half of the Lot 1 error-code contract: every
 * pinned backend code resolves to a translation key; unknown codes fall back
 * to the generic error (never a raw code on screen).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { PEERS_ERROR_KEYS, toastPeersError } from '../peers-error-messages';

const { toast } = vi.hoisted(() => ({ toast: { error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('peers-error-messages', () => {
  it('maps every backend contract code to a translation key', () => {
    // Mirror of tests/unit/domains/peers/test_error_codes_contract.py (Lot 1).
    const backendCodes = [
      'peers_self_request',
      'peers_context_message_too_long',
      'peers_already_connected',
      'peers_not_pending',
      'peers_not_connected',
      'peers_invalid_share_level',
      'peers_self_block',
      'peers_conflict',
    ];
    for (const code of backendCodes) {
      expect(PEERS_ERROR_KEYS[code], `missing mapping for ${code}`).toMatch(
        /^settings\.peers\.errors\./
      );
    }
  });

  it('toasts the mapped key for a known code', () => {
    const t = vi.fn((key: string) => key);
    toastPeersError(t, 'peers_already_connected');
    expect(toast.error).toHaveBeenCalledWith('settings.peers.errors.already_connected');
  });

  it('toasts the generic key for unknown or null codes', () => {
    const t = vi.fn((key: string) => key);
    toastPeersError(t, 'something_new');
    toastPeersError(t, null);
    expect(toast.error).toHaveBeenNthCalledWith(1, 'settings.peers.errors.generic');
    expect(toast.error).toHaveBeenNthCalledWith(2, 'settings.peers.errors.generic');
  });
});
