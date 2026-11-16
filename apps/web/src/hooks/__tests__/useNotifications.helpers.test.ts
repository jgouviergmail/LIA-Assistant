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
  buildNotificationFromSse,
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
    // No occurrence recorded: nothing to offer beside the id.
    expect(h.onReminder).toHaveBeenCalledWith('wake up', 'r1', undefined);
    expect(h.onProactiveNotification).not.toHaveBeenCalled();
  });

  it('routes a reminder with the occurrence its toast may postpone (ADR-268)', () => {
    const h = handlers();
    const received = buildNotificationFromSse({
      type: 'reminder',
      reminder_id: 'r1',
      content: 'wake up',
      firing_id: 'f1',
      snooze_short_minutes: 10,
    });
    routeNotification(received, h);
    expect(h.onReminder).toHaveBeenCalledWith('wake up', 'r1', {
      firingId: 'f1',
      shortMinutes: 10,
    });
  });

  it('routes a reminder whose occurrence was not recorded with no offer', () => {
    const h = handlers();
    routeNotification(notif({ type: 'reminder', reminder_id: 'r1', firing_id: 'f1' }), h);
    expect(h.onReminder).toHaveBeenCalledWith('hello', 'r1', undefined);
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
    expect(h.onScheduledAction).toHaveBeenCalledWith('done', 'a1', 'a1', undefined);
    // Uses metadata.title when present, and hands the metadata on: it names
    // the annex a run asked there answered in.
    const metadata = { title: 'T', conversation_id: 'annex-1' };
    routeNotification(
      notif({ type: 'scheduled_action', action_id: 'a2', content: 'x', metadata }),
      h
    );
    expect(h.onScheduledAction).toHaveBeenLastCalledWith('x', 'a2', 'T', metadata);
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

  it('keeps the occurrence a reminder push names', () => {
    const n = buildNotificationFromFcm(fcm({ type: 'reminder', reminder_id: 'r', firing_id: 'f' }));
    expect(n.firing_id).toBe('f');
    expect(n.id).toBe('r');
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

  // ADR-378 amendment 2026-11-14: both halves of one notification name the
  // same discussion, or the toast would say where it went on one road only.
  it('names the annex a push went to, as the live event does', () => {
    const call = buildNotificationFromFcm(
      fcm({
        type: 'proactive_phone_call',
        target_id: 'call-1',
        feedback_enabled: 'false',
        conversation_id: 'annex-1',
        url: '/dashboard/chat?conversation=annex-1',
      })
    );
    const routine = buildNotificationFromFcm(
      fcm({ type: 'scheduled_action', action_id: 'a1', title: 'Run', conversation_id: 'annex-2' })
    );
    expect(call.metadata).toMatchObject({ conversation_id: 'annex-1' });
    expect(routine.metadata).toMatchObject({ conversation_id: 'annex-2' });
  });

  it('names no discussion for a push that went to Main (absent, never empty)', () => {
    const call = buildNotificationFromFcm(
      fcm({ type: 'proactive_phone_call', target_id: 'call-1', feedback_enabled: 'false' })
    );
    const routine = buildNotificationFromFcm(
      fcm({ type: 'scheduled_action', action_id: 'a1', title: 'Run', conversation_id: '' })
    );
    expect(call.metadata && 'conversation_id' in call.metadata).toBe(false);
    expect(routine.metadata && 'conversation_id' in routine.metadata).toBe(false);
  });
});

describe('the live event boundary', () => {
  // The dispatcher publishes `proactive_<task>` for every task it serves. The
  // boundary used to list three members, and every other one — a call's
  // return, a meeting's minutes, a peer's message — died here with no toast.
  it.each(['proactive_phone_call', 'proactive_meeting', 'proactive_peer_message'])(
    'accepts %s, a member of the proactive family, and routes it',
    type => {
      const received = buildNotificationFromSse({
        type,
        target_id: 'target-1',
        content: 'Retour',
        metadata: { type, conversation_id: 'annex-1' },
      });
      const h = handlers();
      routeNotification(received, h);
      expect(received.type).toBe(type);
      expect(h.onProactiveNotification).toHaveBeenCalledWith(
        'Retour',
        'target-1',
        received.metadata
      );
    }
  );

  it.each(['proactive_', 'proactive phone', 'PROACTIVE_PHONE', 'bogus'])(
    'still refuses %s, which no dispatcher publishes',
    type => {
      expect(() => buildNotificationFromSse({ type, content: 'x' })).toThrow();
    }
  );

  it('keeps the annex a routine result names beside its identity', () => {
    const received = buildNotificationFromSse({
      type: 'scheduled_action',
      action_id: 'a1',
      title: 'Run',
      content: 'done',
      metadata: { conversation_id: 'annex-1' },
    });
    expect(received.metadata).toEqual({
      conversation_id: 'annex-1',
      type: 'scheduled_action',
      action_id: 'a1',
      title: 'Run',
    });
  });

  it('never lets the metadata overwrite a routine result identity', () => {
    const received = buildNotificationFromSse({
      type: 'scheduled_action',
      action_id: 'a1',
      title: 'Run',
      content: 'done',
      metadata: { action_id: 'forged', title: 'Forged', type: 'reminder' },
    });
    expect(received.metadata).toEqual({ type: 'scheduled_action', action_id: 'a1', title: 'Run' });
  });
});

describe('proactive discussion transport', () => {
  it('accepts the archived discussion notification and routes its stable identity', () => {
    const received = buildNotificationFromSse({
      type: 'proactive_discussion',
      target_id: 'opening',
      content: 'Bonjour',
      metadata: {
        type: 'proactive_discussion',
        message_id: 'archived-row',
        sensitive_in_app_only: true,
      },
    });
    const h = handlers();
    routeNotification(received, h);
    expect(received.id).toBe('opening');
    expect(h.onProactiveNotification).toHaveBeenCalledWith('Bonjour', 'opening', received.metadata);
  });
  it('keeps the privacy and archive identity on the FCM half', () => {
    const received = buildNotificationFromFcm(
      fcm({
        type: 'proactive_discussion',
        target_id: 'opening',
        message_id: 'archived-row',
        sensitive_in_app_only: 'true',
        feedback_enabled: 'false',
      })
    );
    expect(received.metadata).toMatchObject({
      message_id: 'archived-row',
      sensitive_in_app_only: true,
      feedback_enabled: false,
    });
  });
});
