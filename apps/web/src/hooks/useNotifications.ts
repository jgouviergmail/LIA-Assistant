/**
 * Hook for real-time notifications via Server-Sent Events (SSE).
 *
 * Connects to the backend SSE endpoint and listens for:
 * - reminders
 * - Other notification types
 *
 * Automatically reconnects on connection loss.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { logger } from '@/lib/logger';
import { onForegroundMessage } from '@/lib/firebase';
import type { MessagePayload } from 'firebase/messaging';

export type NotificationType = 'reminder' | 'system' | 'message' | 'oauth_health_warning' | 'oauth_health_critical' | 'proactive_interest' | 'proactive_heartbeat' | 'scheduled_action' | 'subagent_result' | 'admin_broadcast';

export interface Notification {
  id: string;
  type: NotificationType;
  content: string;
  reminder_id?: string;
  target_id?: string;
  action_id?: string;
  connector_id?: string;
  connector_type?: string;
  display_name?: string;
  authorize_url?: string;
  broadcast_id?: string;
  metadata?: Record<string, unknown>;
  timestamp: Date;
  read: boolean;
}

export interface UseNotificationsOptions {
  /** Enable SSE connection (default: true) */
  enableSSE?: boolean;
  /** Enable FCM foreground messages (default: true) */
  enableFCM?: boolean;
  /** Is user authenticated? SSE only connects when true */
  isAuthenticated?: boolean;
  /** Callback when notification received */
  onNotification?: (notification: Notification) => void;
  /** Callback when reminder received */
  onReminder?: (content: string, reminderId: string) => void;
  /** Callback when proactive notification received (interest, heartbeat, etc.) */
  onProactiveNotification?: (content: string, targetId: string, metadata?: Record<string, unknown>) => void;
  /** Callback when scheduled action execution completes */
  onScheduledAction?: (content: string, actionId: string, title: string) => void;
  /** Callback when OAuth health warning received (expiring soon) */
  onOAuthWarning?: (notification: Notification) => void;
  /** Callback when OAuth health critical received (expired/error) */
  onOAuthCritical?: (notification: Notification) => void;
  /** Callback when sub-agent execution completes (F6) */
  onSubagentResult?: (content: string, targetId: string, metadata?: Record<string, unknown>) => void;
}

export interface UseNotificationsReturn {
  /** List of received notifications */
  notifications: Notification[];
  /** Whether SSE is connected */
  isConnected: boolean;
  /** Last error message */
  error: string | null;
  /** Clear all notifications */
  clearNotifications: () => void;
  /** Mark notification as read */
  markAsRead: (id: string) => void;
  /** Mark all as read */
  markAllAsRead: () => void;
  /** Unread count */
  unreadCount: number;
}

/**
 * Hook for real-time notifications.
 *
 * @example
 * ```tsx
 * const { notifications, unreadCount, isConnected } = useNotifications({
 *   onReminder: (content, reminderId) => {
 *     toast.info(content);
 *     // Optionally scroll to the reminder in conversation
 *   },
 * });
 * ```
 */
export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const {
    enableSSE = true,
    enableFCM = true,
    isAuthenticated = false,
    onNotification,
    onReminder,
    onProactiveNotification,
    onScheduledAction,
    onOAuthWarning,
    onOAuthCritical,
    onSubagentResult,
  } = options;

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);

  const MAX_RECONNECT_ATTEMPTS = 5;
  const RECONNECT_DELAY_MS = 3000;

  /**
   * Add a new notification to the list.
   */
  const addNotification = useCallback(
    (notification: Notification) => {
      setNotifications((prev) => {
        // Avoid duplicates by checking id
        if (prev.some((n) => n.id === notification.id)) {
          return prev;
        }
        return [notification, ...prev].slice(0, 50); // Keep last 50
      });

      onNotification?.(notification);

      // Handle specific notification types
      if (notification.type === 'reminder' && notification.reminder_id) {
        onReminder?.(notification.content, notification.reminder_id);
      } else if ((notification.type as string).startsWith('proactive_') && notification.target_id) {
        // Generic proactive handler: covers interest, heartbeat, and future types
        onProactiveNotification?.(notification.content, notification.target_id, notification.metadata);
      } else if (notification.type === 'scheduled_action' && notification.action_id) {
        const actionTitle = (notification.metadata?.title as string) || notification.action_id;
        onScheduledAction?.(notification.content, notification.action_id, actionTitle);
      } else if (notification.type === 'subagent_result' && notification.target_id) {
        onSubagentResult?.(notification.content, notification.target_id, notification.metadata);
      } else if (notification.type === 'oauth_health_warning') {
        onOAuthWarning?.(notification);
      } else if (notification.type === 'oauth_health_critical') {
        onOAuthCritical?.(notification);
      }
      // Note: admin_broadcast is handled separately by BroadcastProvider (has its own SSE/FCM listeners)
    },
    [onNotification, onReminder, onProactiveNotification, onScheduledAction, onOAuthWarning, onOAuthCritical, onSubagentResult]
  );

  /**
   * Connect to SSE endpoint.
   */
  const connectSSE = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (eventSourceRef.current) return;

    try {
      // Build SSE URL - use direct connection to backend API
      // Cross-origin is handled by allowedDevOrigins in next.config.ts
      // Proxy doesn't work reliably with self-signed certs in Next.js 16
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';
      const sseUrl = `${baseUrl}/api/v1/notifications/stream`;

      const eventSource = new EventSource(sseUrl, {
        withCredentials: true,
      });

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;

        logger.info('SSE: Connected to notifications stream', {
          component: 'useNotifications',
        });
      };

      // Handler for parsing notification events
      const handleNotificationEvent = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);

          // Construct metadata for types that send fields at top level
          const metadata: Record<string, unknown> | undefined =
            data.type === 'scheduled_action'
              ? { type: 'scheduled_action', action_id: data.action_id, title: data.title }
              : data.metadata;

          const notification: Notification = {
            id: data.reminder_id || data.target_id || data.action_id || data.connector_id || data.broadcast_id || `notif-${Date.now()}`,
            type: data.type || 'system',
            content: data.content || data.message || '',
            reminder_id: data.reminder_id,
            target_id: data.target_id,
            action_id: data.action_id,
            connector_id: data.connector_id,
            connector_type: data.connector_type,
            display_name: data.display_name,
            authorize_url: data.authorize_url,
            broadcast_id: data.broadcast_id,
            metadata,
            timestamp: new Date(),
            read: false,
          };

          addNotification(notification);

          logger.debug('SSE: Notification received', {
            component: 'useNotifications',
            type: notification.type,
          });
        } catch (error) {
          logger.warn('SSE: Failed to parse message', {
            component: 'useNotifications',
            data: event.data,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      };

      // Listen for custom "notification" event type (backend sends: event: notification)
      eventSource.addEventListener('notification', handleNotificationEvent);

      // Also listen for default message events (fallback)
      eventSource.onmessage = handleNotificationEvent;

      eventSource.onerror = (_event) => {
        logger.warn('SSE: Connection error', {
          component: 'useNotifications',
          readyState: eventSource.readyState,
        });

        setIsConnected(false);
        eventSource.close();
        eventSourceRef.current = null;

        // Attempt reconnect with backoff
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current += 1;
          const delay = RECONNECT_DELAY_MS * reconnectAttempts.current;

          reconnectTimeoutRef.current = setTimeout(() => {
            logger.info('SSE: Attempting reconnect', {
              component: 'useNotifications',
              attempt: reconnectAttempts.current,
            });
            connectSSE();
          }, delay);
        } else {
          setError('Connection to notification server lost. Please refresh the page.');
          logger.error('SSE: Max reconnect attempts reached', new Error('Max reconnect attempts'), {
            component: 'useNotifications',
          });
        }
      };

      eventSourceRef.current = eventSource;
    } catch (err) {
      logger.error('SSE: Failed to create EventSource', err as Error, {
        component: 'useNotifications',
      });
      setError('Failed to connect to notification server');
    }
  }, [addNotification]);

  /**
   * Disconnect SSE.
   */
  const disconnectSSE = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    setIsConnected(false);
    reconnectAttempts.current = 0;
  }, []);

  // Setup SSE connection (only when authenticated)
  useEffect(() => {
    if (!enableSSE) return;
    if (!isAuthenticated) {
      // Not authenticated yet - don't connect
      disconnectSSE();
      return;
    }

    connectSSE();

    return () => {
      disconnectSSE();
    };
  }, [enableSSE, isAuthenticated, connectSSE, disconnectSSE]);

  // Setup FCM foreground message handler
  useEffect(() => {
    if (!enableFCM) return;
    if (typeof window === 'undefined') return;

    const unsubscribe = onForegroundMessage((payload: MessagePayload) => {
      logger.info('FCM: Foreground message received', {
        component: 'useNotifications',
        title: payload.notification?.title,
      });

      // Build metadata from FCM data fields for proactive notifications
      // FCM sends flat data (not nested), so we reconstruct metadata here
      const fcmType = payload.data?.type as NotificationType | undefined;
      const fcmMetadata: Record<string, unknown> | undefined =
        fcmType && (fcmType as string).startsWith('proactive_')
          ? {
              type: fcmType,
              target_id: payload.data?.target_id,
              feedback_enabled: payload.data?.feedback_enabled === 'true',
            }
          : fcmType === 'scheduled_action'
            ? {
                type: 'scheduled_action',
                action_id: payload.data?.action_id,
                title: payload.data?.title,
              }
            : undefined;

      const notification: Notification = {
        id: payload.data?.reminder_id || payload.data?.target_id || payload.data?.action_id || payload.data?.connector_id || payload.data?.broadcast_id || `fcm-${Date.now()}`,
        type: fcmType || 'system',
        content: payload.notification?.body || payload.data?.body || payload.data?.message || '',
        reminder_id: payload.data?.reminder_id,
        target_id: payload.data?.target_id,
        action_id: payload.data?.action_id,
        connector_id: payload.data?.connector_id,
        connector_type: payload.data?.connector_type,
        display_name: payload.data?.display_name,
        authorize_url: payload.data?.authorize_url,
        broadcast_id: payload.data?.broadcast_id,
        metadata: fcmMetadata,
        timestamp: new Date(),
        read: false,
      };

      addNotification(notification);
    });

    return () => {
      unsubscribe?.();
    };
  }, [enableFCM, addNotification]);

  /**
   * Clear all notifications.
   */
  const clearNotifications = useCallback(() => {
    setNotifications([]);
  }, []);

  /**
   * Mark a notification as read.
   */
  const markAsRead = useCallback((id: string) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
  }, []);

  /**
   * Mark all notifications as read.
   */
  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  return {
    notifications,
    isConnected,
    error,
    clearNotifications,
    markAsRead,
    markAllAsRead,
    unreadCount,
  };
}
