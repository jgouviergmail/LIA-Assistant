/**
 * Backend `peers_*` error codes → localized toast keys (peers program, Lot 2).
 *
 * Frontend half of the Lot 1 contract pinned by
 * `apps/api/tests/unit/domains/peers/test_error_codes_contract.py`: the API
 * reports guard failures as stable machine codes; this table is the ONLY
 * place they meet translation keys. Unknown codes fall back to the generic
 * message — a raw code must never reach the screen.
 */

import { toast } from 'sonner';

export const PEERS_ERROR_KEYS: Record<string, string> = {
  peers_self_request: 'settings.peers.errors.self_request',
  peers_context_message_too_long: 'settings.peers.errors.context_too_long',
  peers_already_connected: 'settings.peers.errors.already_connected',
  peers_not_pending: 'settings.peers.errors.not_pending',
  peers_not_connected: 'settings.peers.errors.not_connected',
  peers_invalid_share_level: 'settings.peers.errors.invalid_share_level',
  peers_self_block: 'settings.peers.errors.self_block',
  peers_conflict: 'settings.peers.errors.conflict',
};

const GENERIC_KEY = 'settings.peers.errors.generic';

/**
 * Toast the localized message for a backend error code.
 *
 * @param t - Translation function from `useTranslation`.
 * @param code - Backend `peers_*` code, or null when the shape was unknown.
 */
export function toastPeersError(t: (key: string) => string, code: string | null): void {
  const key = (code && PEERS_ERROR_KEYS[code]) || GENERIC_KEY;
  toast.error(t(key));
}
