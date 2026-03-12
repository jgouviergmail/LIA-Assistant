/**
 * Hook for Microsoft 365 OAuth connection.
 * Thin wrapper around useOAuthConnect with Microsoft-specific endpoints.
 */

import { MICROSOFT_AUTH_ENDPOINTS } from '../constants';
import { useOAuthConnect } from './useOAuthConnect';

interface UseMicrosoftOAuthOptions {
  onError?: (error: string) => void;
}

export function useMicrosoftOAuth({ onError }: UseMicrosoftOAuthOptions = {}) {
  return useOAuthConnect(MICROSOFT_AUTH_ENDPOINTS, 'useMicrosoftOAuth', { onError });
}
