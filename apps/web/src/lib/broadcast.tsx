'use client';

import { createContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react';
import { onForegroundMessage } from '@/lib/firebase';
import type { MessagePayload } from 'firebase/messaging';

/**
 * Broadcast message info from the backend.
 */
export interface BroadcastInfo {
  id: string;
  message: string;
  sent_at: string;
  sender_name?: string;
}

/**
 * Context value for broadcast management.
 */
interface BroadcastContextValue {
  /** Currently displayed broadcast */
  currentBroadcast: BroadcastInfo | null;
  /** Whether the modal should be shown */
  showModal: boolean;
  /** Number of broadcasts in queue */
  queueLength: number;
  /** Dismiss current broadcast and show next */
  handleDismiss: () => Promise<void>;
  /** Handle incoming broadcast (from SSE via useNotifications) */
  handleNewBroadcast: (message: string, broadcastId: string) => void;
}

export const BroadcastContext = createContext<BroadcastContextValue | undefined>(undefined);

const BROADCAST_CHANNEL_NAME = 'admin_broadcasts';
const INITIAL_CHECK_DEBOUNCE_MS = 5 * 60 * 1000; // 5 minutes for initial mount
const VISIBILITY_CHECK_DEBOUNCE_MS = 10 * 1000; // 10 seconds for visibility change
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';

interface BroadcastProviderProps {
  children: ReactNode;
  isAuthenticated: boolean;
}

/**
 * Provider for admin broadcast messages.
 *
 * Handles:
 * - Fetching unread broadcasts at login and on visibility change
 * - Receiving broadcasts via FCM foreground messages
 * - SSE broadcasts are received via useNotifications and passed here via handleNewBroadcast
 * - Multi-tab synchronization via BroadcastChannel API
 * - Queue management for multiple broadcasts
 *
 * @example
 * ```tsx
 * <BroadcastProvider isAuthenticated={!!user}>
 *   <BroadcastModal lng={lng} />
 *   {children}
 * </BroadcastProvider>
 * ```
 */
export function BroadcastProvider({ children, isAuthenticated }: BroadcastProviderProps) {
  const [currentBroadcast, setCurrentBroadcast] = useState<BroadcastInfo | null>(null);
  const [queue, setQueue] = useState<BroadcastInfo[]>([]);
  const [showModal, setShowModal] = useState(false);
  const lastCheckRef = useRef<number>(0);
  const channelRef = useRef<BroadcastChannel | null>(null);

  // Ref to hold the latest handleNewBroadcast for FCM listener (avoids stale closure)
  const handleNewBroadcastRef = useRef<(message: string, broadcastId: string) => void>(() => {});

  /**
   * Show the next broadcast from the queue.
   * Called when queue changes and no modal is currently shown.
   */
  const showNext = useCallback((broadcasts: BroadcastInfo[]) => {
    if (broadcasts.length === 0) {
      setShowModal(false);
      setCurrentBroadcast(null);
      return;
    }
    const next = broadcasts[0];
    setCurrentBroadcast(next);
    setShowModal(true);
    // Notify other tabs
    channelRef.current?.postMessage({ type: 'broadcast_shown', broadcastId: next.id });
  }, []);

  // Setup BroadcastChannel for multi-tab sync
  useEffect(() => {
    if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
      channelRef.current = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
      channelRef.current.onmessage = e => {
        if (e.data.type === 'broadcast_shown') {
          // Another tab showed this broadcast, remove from our queue
          setQueue(prev => prev.filter(b => b.id !== e.data.broadcastId));
        }
      };
    }
    return () => channelRef.current?.close();
  }, []);

  /**
   * Fetch unread broadcasts from the backend.
   *
   * @param debounceMs - Debounce duration in ms (default: INITIAL_CHECK_DEBOUNCE_MS)
   *                     Use shorter debounce for visibility changes to catch missed broadcasts
   */
  const fetchUnread = useCallback(
    async (debounceMs: number = INITIAL_CHECK_DEBOUNCE_MS) => {
      const now = Date.now();
      if (now - lastCheckRef.current < debounceMs) return;
      lastCheckRef.current = now;

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/notifications/broadcasts/unread`, {
          credentials: 'include',
        });
        if (!response.ok) return;
        const data = await response.json();
        if (data.broadcasts?.length > 0) {
          setQueue(data.broadcasts);
          showNext(data.broadcasts);
        }
      } catch (error) {
        console.error('Failed to fetch unread broadcasts:', error);
      }
    },
    [showNext]
  );

  // Fetch at login
  useEffect(() => {
    if (isAuthenticated) {
      fetchUnread();
    }
  }, [isAuthenticated, fetchUnread]);

  // Fetch on visibility change (app comes to foreground)
  // Uses shorter debounce to catch broadcasts missed while tab was in background
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && isAuthenticated) {
        fetchUnread(VISIBILITY_CHECK_DEBOUNCE_MS);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [isAuthenticated, fetchUnread]);

  /**
   * Handle a new broadcast from SSE (via useNotifications) or FCM.
   * Pure state update - no side effects inside setQueue.
   */
  const handleNewBroadcast = useCallback((message: string, broadcastId: string) => {
    const broadcast: BroadcastInfo = {
      id: broadcastId,
      message,
      sent_at: new Date().toISOString(),
    };
    setQueue(prev => {
      // Dedup
      if (prev.some(b => b.id === broadcastId)) return prev;
      return [...prev, broadcast];
    });
  }, []);

  // Keep ref updated with latest handleNewBroadcast (for FCM listener)
  useEffect(() => {
    handleNewBroadcastRef.current = handleNewBroadcast;
  }, [handleNewBroadcast]);

  // React to queue changes: show modal if queue has items and modal is not shown
  useEffect(() => {
    if (queue.length > 0 && !showModal) {
      showNext(queue);
    }
  }, [queue, showModal, showNext]);

  // Listen for FCM foreground messages for broadcasts
  useEffect(() => {
    if (!isAuthenticated) return;

    const unsubscribe = onForegroundMessage((payload: MessagePayload) => {
      if (payload.data?.type === 'admin_broadcast' && payload.data?.broadcast_id) {
        // Use ref to always get the latest handleNewBroadcast
        handleNewBroadcastRef.current(
          payload.notification?.body || payload.data?.message || '',
          payload.data.broadcast_id
        );
      }
    });

    return () => unsubscribe?.();
  }, [isAuthenticated]);

  // Listen for SSE broadcasts directly (independent of useNotifications in chat page)
  // This ensures broadcasts are received regardless of which page the user is on
  useEffect(() => {
    if (!isAuthenticated) return;

    const eventSource = new EventSource(`${API_BASE_URL}/api/v1/notifications/stream`, {
      withCredentials: true,
    });

    eventSource.addEventListener('notification', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'admin_broadcast' && data.broadcast_id) {
          handleNewBroadcastRef.current(data.message || '', data.broadcast_id);
        }
      } catch (error) {
        console.error('Failed to parse SSE broadcast:', error);
      }
    });

    eventSource.onerror = () => {
      // SSE errors are expected during reconnection, don't log
    };

    return () => eventSource.close();
  }, [isAuthenticated]);

  /**
   * Mark current broadcast as read and show the next one.
   */
  const handleDismiss = useCallback(async () => {
    if (!currentBroadcast) return;

    try {
      await fetch(`${API_BASE_URL}/api/v1/notifications/broadcasts/${currentBroadcast.id}/read`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (error) {
      console.error('Failed to mark broadcast as read:', error);
    }

    const remaining = queue.filter(b => b.id !== currentBroadcast.id);
    setQueue(remaining);
    showNext(remaining);
  }, [currentBroadcast, queue, showNext]);

  return (
    <BroadcastContext.Provider
      value={{
        currentBroadcast,
        showModal,
        queueLength: queue.length,
        handleDismiss,
        handleNewBroadcast,
      }}
    >
      {children}
    </BroadcastContext.Provider>
  );
}
