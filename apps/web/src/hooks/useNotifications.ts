/**
 * Hook for real-time notifications via Server-Sent Events (SSE).
 *
 * Connects to the backend SSE endpoint and listens for:
 * - reminders
 * - Other notification types
 * - the thread's own sync signals (ADR-320), handed to their own callback
 *
 * A dropped stream is reopened for as long as the tab is looked at — never
 * given up on: a channel that stops after five failures leaves the chat
 * silent until a manual reload, which is the defect ADR-320 fixed. Retries
 * wait longer each time, up to a ceiling, pause while the tab is hidden and
 * start again at once when the device is back online. A reopened stream is
 * announced: Pub/Sub keeps nothing, so whatever was published meanwhile is
 * lost and the caller catches up.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useSmsNotificationSignals } from '@/hooks/useSmsNotificationSignals';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
import { z } from '@/lib/zod';
import { logger } from '@/lib/logger';
import { redirectToLogin } from '@/lib/api-client';
import { onForegroundMessage } from '@/lib/firebase';
import type { MessagePayload } from 'firebase/messaging';

export type NotificationType =
  | 'reminder'
  | 'system'
  | 'message'
  | 'oauth_health_warning'
  | 'oauth_health_critical'
  | 'proactive_interest'
  | 'proactive_heartbeat'
  | 'proactive_discussion'
  | 'scheduled_action'
  | 'subagent_result'
  | 'admin_broadcast';

/** The thread's own sync signals (ADR-320) — never shown as notifications. */
export type ConversationSignal = 'conversation_updated' | 'conversation_reset';

const CONVERSATION_SIGNALS: ReadonlySet<string> = new Set<ConversationSignal>([
  'conversation_updated',
  'conversation_reset',
]);

/** First reconnect delay; each further failure waits one unit more. */
export const RECONNECT_DELAY_MS = 3000;
/** The longest wait between two attempts: retries never stop, they slow down. */
export const RECONNECT_MAX_DELAY_MS = 60_000;

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
  /** Authenticated owner of phone resource signals. Never supplied by a payload. */
  ownerId?: string;
  onSmsReceived?: (signal: SmsReceivedSignal) => void;
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
  onProactiveNotification?: (
    content: string,
    targetId: string,
    metadata?: Record<string, unknown>
  ) => void;
  /** Callback when scheduled action execution completes */
  onScheduledAction?: (content: string, actionId: string, title: string) => void;
  /** Callback when OAuth health warning received (expiring soon) */
  onOAuthWarning?: (notification: Notification) => void;
  /** Callback when OAuth health critical received (expired/error) */
  onOAuthCritical?: (notification: Notification) => void;
  /** Callback when sub-agent execution completes (F6) */
  onSubagentResult?: (
    content: string,
    targetId: string,
    metadata?: Record<string, unknown>
  ) => void;
  /** The thread's sync signals (ADR-320): a message landed, or the
   *  conversation was reset. Not notifications: never listed nor counted. */
  onConversationEvent?: (signal: ConversationSignal) => void;
  /** A dropped stream is open again: what was published meanwhile is lost. */
  onReconnected?: () => void;
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

/** Type-specific side-effect callbacks a notification can trigger. */
export interface NotificationRouteHandlers {
  onReminder?: (content: string, reminderId: string) => void;
  onProactiveNotification?: (
    content: string,
    targetId: string,
    metadata?: Record<string, unknown>
  ) => void;
  onScheduledAction?: (content: string, actionId: string, title: string) => void;
  onSubagentResult?: (
    content: string,
    targetId: string,
    metadata?: Record<string, unknown>
  ) => void;
  onOAuthWarning?: (notification: Notification) => void;
  onOAuthCritical?: (notification: Notification) => void;
}

type NotificationRoute = (notification: Notification, h: NotificationRouteHandlers) => void;

/** Exact-type routes (proactive_* is prefix-matched separately in
 * routeNotification). Each guards on the entity id it needs. */
const NOTIFICATION_ROUTES: Record<string, NotificationRoute> = {
  reminder: (n, h) => {
    if (n.reminder_id) h.onReminder?.(n.content, n.reminder_id);
  },
  scheduled_action: (n, h) => {
    if (n.action_id) {
      const title = (n.metadata?.title as string) || n.action_id;
      h.onScheduledAction?.(n.content, n.action_id, title);
    }
  },
  subagent_result: (n, h) => {
    if (n.target_id) h.onSubagentResult?.(n.content, n.target_id, n.metadata);
  },
  oauth_health_warning: (n, h) => h.onOAuthWarning?.(n),
  oauth_health_critical: (n, h) => h.onOAuthCritical?.(n),
};

/** Dispatch a notification to its type-specific handler (audit F011). Extracted
 * so ``addNotification`` stays a thin store-update + route call.
 * admin_broadcast is intentionally NOT routed — BroadcastProvider owns its own
 * SSE/FCM listeners. */
export function routeNotification(notification: Notification, h: NotificationRouteHandlers): void {
  // proactive_* is a family (interest, heartbeat, …) matched by prefix.
  if ((notification.type as string).startsWith('proactive_') && notification.target_id) {
    h.onProactiveNotification?.(
      notification.content,
      notification.target_id,
      notification.metadata
    );
    return;
  }
  if (Object.hasOwn(NOTIFICATION_ROUTES, notification.type)) {
    NOTIFICATION_ROUTES[notification.type](notification, h);
  }
}

/** Rebuild proactive/scheduled metadata from the flat FCM data fields. */
function buildFcmMetadata(
  fcmType: NotificationType | undefined,
  d: Record<string, string>
): Record<string, unknown> | undefined {
  if (fcmType && (fcmType as string).startsWith('proactive_')) {
    return {
      type: fcmType,
      target_id: d.target_id,
      feedback_enabled: d.feedback_enabled === 'true',
      // The push half of a card must describe the same notification as the
      // archived half. Without it, a verdict given here names no notification:
      // nothing reaches the audit trail, and — an interest card's `target_id`
      // being the INTEREST — the backend would lock every other card of that
      // interest rather than this one. Spread so an absent run_id leaves no
      // key at all: `proactiveFeedbackProps` reads it as a string and would
      // forward '' as though it identified something.
      ...(d.run_id ? { run_id: d.run_id } : {}),
      ...(d.message_id ? { message_id: d.message_id } : {}),
      ...(d.sensitive_in_app_only === 'true' ? { sensitive_in_app_only: true } : {}),
    };
  }
  if (fcmType === 'scheduled_action') {
    return { type: 'scheduled_action', action_id: d.action_id, title: d.title };
  }
  return undefined;
}

/** Reconstruct a Notification from a flat FCM foreground payload (audit F011).
 * FCM sends flat ``data`` fields (not nested); the stable id resolves to the
 * first present entity id (falling back to a timestamped synthetic id). */
export function buildNotificationFromFcm(payload: MessagePayload): Notification {
  const d = (payload.data ?? {}) as Record<string, string>;
  const fcmType = d.type as NotificationType | undefined;
  return {
    id:
      d.reminder_id ||
      d.target_id ||
      d.action_id ||
      d.connector_id ||
      d.broadcast_id ||
      `fcm-${Date.now()}`,
    type: fcmType || 'system',
    content: payload.notification?.body || d.body || d.message || '',
    reminder_id: d.reminder_id,
    target_id: d.target_id,
    action_id: d.action_id,
    connector_id: d.connector_id,
    connector_type: d.connector_type,
    display_name: d.display_name,
    authorize_url: d.authorize_url,
    broadcast_id: d.broadcast_id,
    metadata: buildFcmMetadata(fcmType, d),
    timestamp: new Date(),
    read: false,
  };
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
const sseNotice = z.object({
  type: z
    .enum([
      'reminder',
      'system',
      'message',
      'oauth_health_warning',
      'oauth_health_critical',
      'proactive_interest',
      'proactive_heartbeat',
      'proactive_discussion',
      'scheduled_action',
      'subagent_result',
      'admin_broadcast',
    ])
    .default('system'),
  content: z.string().optional(),
  message: z.string().optional(),
  reminder_id: z.string().optional(),
  target_id: z.string().optional(),
  action_id: z.string().optional(),
  connector_id: z.string().optional(),
  connector_type: z.string().optional(),
  display_name: z.string().optional(),
  authorize_url: z.string().optional(),
  broadcast_id: z.string().optional(),
  title: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).optional(),
});
/** Runtime DTO at the untrusted SSE boundary; no payload is written to logs. */
export function buildNotificationFromSse(payload: unknown): Notification {
  const data = sseNotice.parse(payload);
  return {
    ...data,
    id:
      [data.reminder_id, data.target_id, data.action_id, data.connector_id, data.broadcast_id].find(
        Boolean
      ) ?? `notif-${Date.now()}`,
    content: data.content ?? data.message ?? '',
    metadata:
      data.type === 'scheduled_action'
        ? { type: data.type, action_id: data.action_id, title: data.title }
        : data.metadata,
    timestamp: new Date(),
    read: false,
  };
}

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const {
    ownerId,
    onSmsReceived,
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
    onConversationEvent,
    onReconnected,
  } = options;

  const { receiveSms, refreshSms } = useSmsNotificationSignals(ownerId, onSmsReceived);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttempts = useRef(0);
  const sessionRevokedRef = useRef(false);
  const clearNotifications = useCallback(() => {
    setNotifications(previous => (previous.length ? [] : previous));
  }, []);
  useEffect(() => {
    if (!isAuthenticated) {
      sessionRevokedRef.current = false;
      clearNotifications();
    }
  }, [isAuthenticated, clearNotifications]);
  // Closed while hidden (evicted by a newer stream, or dropped): resume on
  // the next visibility rather than retry for a tab nobody looks at.
  const resumeWhenVisibleRef = useRef(false);
  // Closed by a failure or an eviction — before its first open included: the
  // next open is announced, since nothing published meanwhile reached it.
  const droppedRef = useRef(false);
  // Read through refs: a new callback identity must never rebuild the stream.
  const onConversationEventRef = useRef(onConversationEvent);
  const onReconnectedRef = useRef(onReconnected);
  useEffect(() => {
    onConversationEventRef.current = onConversationEvent;
    onReconnectedRef.current = onReconnected;
  });

  /**
   * Add a new notification to the list.
   */
  const addNotification = useCallback(
    (notification: Notification) => {
      setNotifications(prev => {
        // Avoid duplicates by checking id
        if (prev.some(n => n.id === notification.id)) {
          return prev;
        }
        return [notification, ...prev].slice(0, 50); // Keep last 50
      });

      onNotification?.(notification);

      // Type-specific side effects (admin_broadcast handled by BroadcastProvider).
      routeNotification(notification, {
        onReminder,
        onProactiveNotification,
        onScheduledAction,
        onSubagentResult,
        onOAuthWarning,
        onOAuthCritical,
      });
    },
    [
      onNotification,
      onReminder,
      onProactiveNotification,
      onScheduledAction,
      onOAuthWarning,
      onOAuthCritical,
      onSubagentResult,
    ]
  );

  /**
   * Connect to SSE endpoint.
   */
  const connectSSE = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (sessionRevokedRef.current) return;
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
        if (eventSourceRef.current !== eventSource) return;
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;
        if (droppedRef.current) {
          droppedRef.current = false;
          refreshSms();
          onReconnectedRef.current?.();
        }

        logger.info('SSE: Connected to notifications stream', {
          component: 'useNotifications',
        });
      };

      // Handler for parsing notification events
      const handleNotificationEvent = (event: MessageEvent) => {
        if (eventSourceRef.current !== eventSource) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'sms_received') {
            receiveSms(data);
            return;
          }
          if (CONVERSATION_SIGNALS.has(data.type)) {
            // The thread's own sync signal, not a notification (ADR-320).
            onConversationEventRef.current?.(data.type as ConversationSignal);
            return;
          }

          const notification = buildNotificationFromSse(data);

          addNotification(notification);

          logger.debug('SSE: Notification received', {
            component: 'useNotifications',
            type: notification.type,
          });
        } catch (error) {
          logger.warn('SSE: Failed to parse message', {
            component: 'useNotifications',
            errorType: error instanceof Error ? error.name : typeof error,
          });
        }
      };

      // Listen for custom "notification" event type (backend sends: event: notification)
      eventSource.addEventListener('notification', handleNotificationEvent);

      // Also listen for default message events (fallback)
      eventSource.onmessage = handleNotificationEvent;

      // The backend caps concurrent streams per user (newest wins) and tells
      // an evicted stream so before closing it. This is a deliberate verdict,
      // not a failure: close without burning retry attempts or surfacing an
      // error. A visible tab is in active use and retakes a slot right away;
      // a hidden tab waits until the user looks at it again.
      eventSource.addEventListener('superseded', () => {
        if (eventSourceRef.current !== eventSource) return;
        logger.info('SSE: Stream superseded by a newer one', {
          component: 'useNotifications',
        });
        eventSource.close();
        eventSourceRef.current = null;
        setIsConnected(false);
        droppedRef.current = true;
        if (document.visibilityState === 'visible') {
          connectSSE();
        } else {
          resumeWhenVisibleRef.current = true;
        }
      });

      // « Sign out this device »: the server closed the stream because the
      // session is gone (point 22). Reconnecting would only meet a 401 at
      // every backoff step — close for good and send the page to the login.
      eventSource.addEventListener('session_revoked', () => {
        if (eventSourceRef.current !== eventSource) return;
        logger.info('SSE: Session revoked', { component: 'useNotifications' });
        sessionRevokedRef.current = true;
        resumeWhenVisibleRef.current = false;
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        eventSource.close();
        eventSourceRef.current = null;
        setIsConnected(false);
        redirectToLogin();
      });

      eventSource.onerror = _event => {
        if (eventSourceRef.current !== eventSource) return;
        logger.warn('SSE: Connection error', {
          component: 'useNotifications',
          readyState: eventSource.readyState,
        });

        setIsConnected(false);
        eventSource.close();
        eventSourceRef.current = null;
        droppedRef.current = true;

        if (document.visibilityState === 'hidden') {
          // Nobody looks at this tab: retrying would only load the server.
          resumeWhenVisibleRef.current = true;
          return;
        }
        // Never given up on: each failure waits longer, up to a ceiling.
        reconnectAttempts.current += 1;
        const delay = Math.min(
          RECONNECT_DELAY_MS * reconnectAttempts.current,
          RECONNECT_MAX_DELAY_MS
        );
        reconnectTimeoutRef.current = setTimeout(() => {
          logger.info('SSE: Attempting reconnect', {
            component: 'useNotifications',
            attempt: reconnectAttempts.current,
          });
          connectSSE();
        }, delay);
      };

      eventSourceRef.current = eventSource;
    } catch (err) {
      logger.error('SSE: Failed to create EventSource', err as Error, {
        component: 'useNotifications',
      });
      setError('Failed to connect to notification server');
    }
  }, [addNotification, receiveSms, refreshSms]);

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
    resumeWhenVisibleRef.current = false;
    droppedRef.current = false;
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

  // Resume a stream closed while hidden when the tab returns to the
  // foreground (an evicted one then wins a slot back, by design), and reopen
  // one at once when the device is back online — no need to wait a backoff
  // delay computed while the network was down.
  useEffect(() => {
    if (!enableSSE || !isAuthenticated) return;

    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && resumeWhenVisibleRef.current) {
        resumeWhenVisibleRef.current = false;
        connectSSE();
      }
    };
    const handleOnline = () => {
      if (eventSourceRef.current) return;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      reconnectAttempts.current = 0;
      if (document.visibilityState === 'hidden') {
        resumeWhenVisibleRef.current = true;
        return;
      }
      connectSSE();
    };
    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('online', handleOnline);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('online', handleOnline);
    };
  }, [enableSSE, isAuthenticated, connectSSE]);

  // Setup FCM foreground message handler
  useEffect(() => {
    if (!enableFCM || !isAuthenticated) return;
    if (typeof window === 'undefined') return;

    let subscribed = true;
    const unsubscribe = onForegroundMessage((payload: MessagePayload) => {
      if (!subscribed || sessionRevokedRef.current) return;
      logger.info('FCM: Foreground message received', {
        component: 'useNotifications',
      });

      if (payload.data?.type === 'sms_received') {
        receiveSms(payload.data);
        return;
      }
      // FCM sends flat data (not nested) — rebuild the Notification shape.
      addNotification(buildNotificationFromFcm(payload));
    });

    return () => {
      subscribed = false;
      unsubscribe?.();
    };
  }, [enableFCM, isAuthenticated, addNotification, receiveSms]);

  /**
   * Mark a notification as read.
   */
  const markAsRead = useCallback((id: string) => {
    setNotifications(prev => prev.map(n => (n.id === id ? { ...n, read: true } : n)));
  }, []);

  /**
   * Mark all notifications as read.
   */
  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  }, []);

  const unreadCount = notifications.filter(n => !n.read).length;

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
