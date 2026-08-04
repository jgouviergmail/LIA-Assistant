/**
 * useNotifications pure helpers — unit tests (audit F011).
 *
 * routeNotification (the type→handler dispatch) and buildNotificationFromFcm
 * (the flat-FCM-payload reconstruction) were extracted from the hook's
 * CC-20 addNotification and CC-35 FCM handler. These pin their behavior.
 */

import { describe, it, expect, vi } from 'vitest';
import type { MessagePayload } from 'firebase/messaging';

import {
  routeNotification,
  buildNotificationFromFcm,
  type Notification,
  type NotificationRouteHandlers,
} from '../useNotifications';

function notif(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 'n1',
    type: 'system',
    content: 'hello',
    timestamp: new Date(),
    read: false,
    ...overrides,
  };
}

function handlers() {
  return {
    onReminder: vi.fn(),
    onProactiveNotification: vi.fn(),
    onScheduledAction: vi.fn(),
    onSubagentResult: vi.fn(),
    onOAuthWarning: vi.fn(),
    onOAuthCritical: vi.fn(),
  } satisfies Required<NotificationRouteHandlers>;
}

describe('routeNotification', () => {
  it('routes a reminder with its id', () => {
    const h = handlers();
    routeNotification(notif({ type: 'reminder', reminder_id: 'r1', content: 'wake up' }), h);
    expect(h.onReminder).toHaveBeenCalledWith('wake up', 'r1');
    expect(h.onProactiveNotification).not.toHaveBeenCalled();
  });

  it('routes any proactive_* type with a target', () => {
    const h = handlers();
    const meta = { k: 1 };
    routeNotification(
      notif({ type: 'proactive_heartbeat', target_id: 't1', content: 'ping', metadata: meta }),
      h
    );
    expect(h.onProactiveNotification).toHaveBeenCalledWith('ping', 't1', meta);
  });

  it('routes a scheduled_action, defaulting the title to the action id', () => {
    const h = handlers();
    routeNotification(notif({ type: 'scheduled_action', action_id: 'a1', content: 'done' }), h);
    expect(h.onScheduledAction).toHaveBeenCalledWith('done', 'a1', 'a1');
    // Uses metadata.title when present.
    routeNotification(
      notif({ type: 'scheduled_action', action_id: 'a2', content: 'x', metadata: { title: 'T' } }),
      h
    );
    expect(h.onScheduledAction).toHaveBeenLastCalledWith('x', 'a2', 'T');
  });

  it('routes a subagent_result with its target', () => {
    const h = handlers();
    routeNotification(notif({ type: 'subagent_result', target_id: 's1', content: 'res' }), h);
    expect(h.onSubagentResult).toHaveBeenCalledWith('res', 's1', undefined);
  });

  it('routes oauth health warning/critical to their handlers', () => {
    const h = handlers();
    const warn = notif({ type: 'oauth_health_warning' });
    const crit = notif({ type: 'oauth_health_critical' });
    routeNotification(warn, h);
    routeNotification(crit, h);
    expect(h.onOAuthWarning).toHaveBeenCalledWith(warn);
    expect(h.onOAuthCritical).toHaveBeenCalledWith(crit);
  });

  it('does nothing for a reminder missing its id, or an unhandled type', () => {
    const h = handlers();
    routeNotification(notif({ type: 'reminder' }), h); // no reminder_id
    routeNotification(notif({ type: 'message' }), h); // unhandled
    routeNotification(notif({ type: 'admin_broadcast' }), h); // owned by BroadcastProvider
    for (const fn of Object.values(h)) expect(fn).not.toHaveBeenCalled();
  });

  it('tolerates missing optional handlers (optional chaining)', () => {
    expect(() =>
      routeNotification(notif({ type: 'reminder', reminder_id: 'r1' }), {})
    ).not.toThrow();
  });
});

function fcm(data?: Record<string, string>, body?: string): MessagePayload {
  return {
    notification: body ? { body } : undefined,
    data,
  } as unknown as MessagePayload;
}

describe('buildNotificationFromFcm', () => {
  it('resolves the id from the first present entity id (reminder wins)', () => {
    const n = buildNotificationFromFcm(fcm({ reminder_id: 'r', target_id: 't' }));
    expect(n.id).toBe('r');
    expect(n.reminder_id).toBe('r');
    expect(n.read).toBe(false);
  });

  it('falls back through target/action/connector/broadcast then a synthetic id', () => {
    expect(buildNotificationFromFcm(fcm({ target_id: 't' })).id).toBe('t');
    expect(buildNotificationFromFcm(fcm({ action_id: 'a' })).id).toBe('a');
    expect(buildNotificationFromFcm(fcm({ connector_id: 'c' })).id).toBe('c');
    expect(buildNotificationFromFcm(fcm({ broadcast_id: 'b' })).id).toBe('b');
    expect(buildNotificationFromFcm(fcm({})).id).toMatch(/^fcm-\d+$/);
  });

  it('defaults the type to system and content through the fallback chain', () => {
    expect(buildNotificationFromFcm(fcm({})).type).toBe('system');
    expect(buildNotificationFromFcm(fcm({ type: 'reminder' })).type).toBe('reminder');
    // notification.body wins, then data.body, then data.message, then ''.
    expect(buildNotificationFromFcm(fcm({}, 'notif body')).content).toBe('notif body');
    expect(buildNotificationFromFcm(fcm({ body: 'd body' })).content).toBe('d body');
    expect(buildNotificationFromFcm(fcm({ message: 'd msg' })).content).toBe('d msg');
    expect(buildNotificationFromFcm(fcm({})).content).toBe('');
  });

  it('rebuilds proactive metadata (feedback_enabled string → boolean)', () => {
    const n = buildNotificationFromFcm(
      fcm({ type: 'proactive_interest', target_id: 't1', feedback_enabled: 'true' })
    );
    expect(n.metadata).toEqual({
      type: 'proactive_interest',
      target_id: 't1',
      feedback_enabled: true,
    });
  });

  // The push half of a card must describe the same notification as the
  // archived half. Without the run_id, a verdict given on a push-built card
  // names no notification: it records nothing in the audit trail, and — since
  // an interest card's target_id is the INTEREST — it would lock every other
  // card of that interest instead of just this one.
  it('carries the run_id of a proactive push so its verdict can name the notification', () => {
    const n = buildNotificationFromFcm(
      fcm({
        type: 'proactive_interest',
        target_id: 't1',
        feedback_enabled: 'true',
        run_id: 'proactive_interest_abc_deadbeef',
      })
    );
    expect(n.metadata).toEqual({
      type: 'proactive_interest',
      target_id: 't1',
      feedback_enabled: true,
      run_id: 'proactive_interest_abc_deadbeef',
    });
  });

  // Absent, never an empty string: `proactiveFeedbackProps` reads `run_id`
  // as a string and would forward '' as if it identified a notification.
  it('omits the run_id when the push carried none', () => {
    const n = buildNotificationFromFcm(
      fcm({ type: 'proactive_heartbeat', target_id: 't1', feedback_enabled: 'false' })
    );
    expect(n.metadata).toEqual({
      type: 'proactive_heartbeat',
      target_id: 't1',
      feedback_enabled: false,
    });
    expect(n.metadata && 'run_id' in n.metadata).toBe(false);
  });

  it('rebuilds scheduled_action metadata, and leaves other types without metadata', () => {
    const sched = buildNotificationFromFcm(
      fcm({ type: 'scheduled_action', action_id: 'a1', title: 'Run' })
    );
    expect(sched.metadata).toEqual({ type: 'scheduled_action', action_id: 'a1', title: 'Run' });
    expect(buildNotificationFromFcm(fcm({ type: 'reminder' })).metadata).toBeUndefined();
  });
});
