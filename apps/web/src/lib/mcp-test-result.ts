import type { TFunction } from 'i18next';

import type { TestConnectionResponse } from '@/hooks/useUserMCPServers';

/**
 * What a failed connection test tells the person, wherever it is shown (the list's toast,
 * the edit form). A failure with a remedy speaks from its code in the person's language
 * (an OAuth server awaiting its authorization points at « Connect via OAuth »); any other
 * keeps the API's technical summary, or the generic failure when there is none.
 */
export function mcpTestFailureMessage(
  result: Pick<TestConnectionResponse, 'error' | 'error_code'> | null | undefined,
  t: TFunction
): string {
  if (result?.error_code === 'oauth_authorization_required')
    // The button's own label, so the sentence names exactly the control the card shows.
    return t('settings.mcp.test_oauth_required', { action: t('settings.mcp.connect_oauth') });
  return result?.error || t('settings.mcp.test_failed');
}
