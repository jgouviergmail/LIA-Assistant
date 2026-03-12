/**
 * Hook for Google OAuth connection.
 * Thin wrapper around useOAuthConnect with Google-specific endpoints.
 */

import { GOOGLE_AUTH_ENDPOINTS } from '../constants';
import { useOAuthConnect } from './useOAuthConnect';

interface UseGoogleOAuthOptions {
  onError?: (error: string) => void;
}

export function useGoogleOAuth({ onError }: UseGoogleOAuthOptions = {}) {
  return useOAuthConnect(GOOGLE_AUTH_ENDPOINTS, 'useGoogleOAuth', { onError });
}
