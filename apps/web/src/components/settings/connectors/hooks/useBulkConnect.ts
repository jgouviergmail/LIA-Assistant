/**
 * Hook for bulk OAuth connector connection (Google + Microsoft).
 * Manages queues of connectors to connect via sequential OAuth redirects.
 *
 * Uses localStorage to persist the queue across OAuth redirects:
 * 1. User clicks "Connect All" → first connector starts OAuth
 * 2. After callback redirect, useEffect detects remaining queue
 * 3. Next connector in queue starts OAuth automatically
 * 4. Repeat until queue is empty
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import apiClient from '@/lib/api-client';
import { logger } from '@/lib/logger';
import {
  BULK_CONNECT_QUEUE_KEY,
  GOOGLE_AUTH_ENDPOINTS,
  GOOGLE_CONNECTOR_TYPES,
  GMAIL_TYPES,
  MICROSOFT_AUTH_ENDPOINTS,
  MICROSOFT_BULK_CONNECT_QUEUE_KEY,
  MICROSOFT_CONNECTOR_TYPES,
} from '../constants';
import { type Connector, isConnectorTypeActive } from '../types';

interface UseBulkConnectOptions {
  connectors: Connector[];
  loading: boolean;
  t: (key: string) => string;
}

interface UseBulkConnectReturn {
  bulkConnecting: boolean;
  connectAllGoogle: () => Promise<void>;
  connectAllMicrosoft: () => Promise<void>;
}

/**
 * Process a bulk connection queue from localStorage.
 *
 * @param queueKey - localStorage key for the queue
 * @param authEndpoints - mapping connector type → auth endpoint
 * @param completeMessageKey - i18n key for completion toast
 * @param connectors - current connectors state
 * @param t - translation function
 */
async function processQueue(
  queueKey: string,
  authEndpoints: Record<string, string>,
  completeMessageKey: string,
  connectors: Connector[],
  t: (key: string) => string
): Promise<void> {
  const queueJson = localStorage.getItem(queueKey);
  if (!queueJson) return;

  const queue = JSON.parse(queueJson) as string[];

  if (queue.length === 0) {
    localStorage.removeItem(queueKey);
    return;
  }

  const nextConnector = queue[0];
  const endpoint = authEndpoints[nextConnector];

  if (!endpoint) {
    // Skip unknown connector and continue
    const newQueue = queue.slice(1);
    if (newQueue.length > 0) {
      localStorage.setItem(queueKey, JSON.stringify(newQueue));
      await processQueue(queueKey, authEndpoints, completeMessageKey, connectors, t);
    } else {
      localStorage.removeItem(queueKey);
      toast.success(t(completeMessageKey));
    }
    return;
  }

  // Check if already connected (only ACTIVE connectors count)
  const checkTypes = nextConnector === 'google_gmail' ? GMAIL_TYPES : undefined;
  const isAlreadyConnected = isConnectorTypeActive(connectors, nextConnector, checkTypes);

  if (isAlreadyConnected) {
    const newQueue = queue.slice(1);
    if (newQueue.length > 0) {
      localStorage.setItem(queueKey, JSON.stringify(newQueue));
      await processQueue(queueKey, authEndpoints, completeMessageKey, connectors, t);
    } else {
      localStorage.removeItem(queueKey);
      toast.success(t(completeMessageKey));
    }
    return;
  }

  // Update queue before redirect (remove current item)
  localStorage.setItem(queueKey, JSON.stringify(queue.slice(1)));

  const response = await apiClient.get<{ authorization_url: string }>(endpoint);
  window.location.href = response.authorization_url;
}

/**
 * Start a bulk connection flow for a provider.
 *
 * @param connectorTypes - all connector types for this provider
 * @param authEndpoints - mapping connector type → auth endpoint
 * @param queueKey - localStorage key for the queue
 * @param allConnectedKey - i18n key when all already connected
 * @param errorKey - i18n key for error toast
 * @param providerName - provider name for logging
 * @param connectors - current connectors state
 * @param t - translation function
 * @param setBulkConnecting - state setter
 */
async function startBulkConnect(
  connectorTypes: readonly string[],
  authEndpoints: Record<string, string>,
  queueKey: string,
  allConnectedKey: string,
  errorKey: string,
  providerName: string,
  connectors: Connector[],
  t: (key: string) => string,
  setBulkConnecting: (v: boolean) => void
): Promise<void> {
  // Get list of connectors not yet connected
  const notConnected = connectorTypes.filter(type => {
    if (type === 'gmail') return false; // Skip legacy type
    const checkTypes = type === 'google_gmail' ? GMAIL_TYPES : undefined;
    return !isConnectorTypeActive(connectors, type, checkTypes);
  });

  if (notConnected.length === 0) {
    toast.info(t(allConnectedKey));
    return;
  }

  setBulkConnecting(true);

  try {
    // Store remaining queue in localStorage (skip the first one — we connect it now)
    if (notConnected.length > 1) {
      localStorage.setItem(queueKey, JSON.stringify(notConnected.slice(1)));
    }

    const firstConnector = notConnected[0];
    const endpoint = authEndpoints[firstConnector];

    if (!endpoint) {
      throw new Error(`No endpoint for connector: ${firstConnector}`);
    }

    const response = await apiClient.get<{ authorization_url: string }>(endpoint);
    window.location.href = response.authorization_url;
  } catch (error) {
    setBulkConnecting(false);
    localStorage.removeItem(queueKey);
    logger.error(`Failed to start bulk ${providerName} connection`, error as Error, {
      component: 'useBulkConnect',
    });
    toast.error(t(errorKey));
  }
}

export function useBulkConnect({
  connectors,
  loading,
  t,
}: UseBulkConnectOptions): UseBulkConnectReturn {
  const [bulkConnecting, setBulkConnecting] = useState(false);
  const isProcessingQueueRef = useRef(false);

  // Check and continue any bulk connection queue on mount
  useEffect(() => {
    const continueQueues = async () => {
      if (isProcessingQueueRef.current) return;
      isProcessingQueueRef.current = true;

      try {
        // Process Google queue
        await processQueue(
          BULK_CONNECT_QUEUE_KEY,
          GOOGLE_AUTH_ENDPOINTS,
          'settings.connectors.google.connect_all_complete',
          connectors,
          t
        );
        // Process Microsoft queue
        await processQueue(
          MICROSOFT_BULK_CONNECT_QUEUE_KEY,
          MICROSOFT_AUTH_ENDPOINTS,
          'settings.connectors.microsoft.connect_all_complete',
          connectors,
          t
        );
      } catch (error) {
        localStorage.removeItem(BULK_CONNECT_QUEUE_KEY);
        localStorage.removeItem(MICROSOFT_BULK_CONNECT_QUEUE_KEY);
        logger.error('Failed to continue bulk connection', error as Error, {
          component: 'useBulkConnect',
        });
      } finally {
        isProcessingQueueRef.current = false;
      }
    };

    if (!loading && connectors.length >= 0) {
      continueQueues();
    }
  }, [loading, connectors, t]);

  const connectAllGoogle = useCallback(
    () =>
      startBulkConnect(
        GOOGLE_CONNECTOR_TYPES,
        GOOGLE_AUTH_ENDPOINTS,
        BULK_CONNECT_QUEUE_KEY,
        'settings.connectors.google.all_already_connected',
        'settings.connectors.google.connect_all_error',
        'Google',
        connectors,
        t,
        setBulkConnecting
      ),
    [connectors, t]
  );

  const connectAllMicrosoft = useCallback(
    () =>
      startBulkConnect(
        MICROSOFT_CONNECTOR_TYPES,
        MICROSOFT_AUTH_ENDPOINTS,
        MICROSOFT_BULK_CONNECT_QUEUE_KEY,
        'settings.connectors.microsoft.all_already_connected',
        'settings.connectors.microsoft.connect_all_error',
        'Microsoft',
        connectors,
        t,
        setBulkConnecting
      ),
    [connectors, t]
  );

  return {
    bulkConnecting,
    connectAllGoogle,
    connectAllMicrosoft,
  };
}
