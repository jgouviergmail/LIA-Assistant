/**
 * Shared OAuth reconnection entry point for every connector-health surface.
 *
 * Extracted from `ConnectorHealthAlert` when the persistent banner was added:
 * two surfaces offering the same "Reconnect" action must not each own a copy
 * of the redirect flow, or they drift on the part that matters — which URL is
 * fetched and how the redirect is validated.
 */

import apiClient from './api-client';
import { navigateToAuthorizationUrl } from './safe-navigation';
import { logger } from './logger';

/**
 * Fetch the provider authorization URL and redirect the browser to it.
 *
 * @param authorizeUrl - Backend path such as `/connectors/gmail/authorize`.
 * @throws When the API call fails — callers surface it to the user.
 */
export async function initiateOAuthReconnect(authorizeUrl: string): Promise<void> {
  try {
    const response = await apiClient.get<{ authorization_url: string }>(authorizeUrl);
    navigateToAuthorizationUrl(response.authorization_url, 'connector-reconnect');
  } catch (error) {
    logger.error('connector_reconnect_failed', error as Error, {
      component: 'connector-reconnect',
    });
    throw error;
  }
}
