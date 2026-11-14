'use client';
/** One owner of World notification arrival and read acknowledgment. */
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useAppConfig } from '@/hooks/useAppConfig';
import { capabilityMounted } from '@/lib/capability-availability';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useNotifications, type Notification } from '@/hooks/useNotifications';
import { smsAvailable } from '@/lib/sms/availability';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
import { workboardAvailable } from '@/lib/workboard/availability';
import { DeviceInbox, type DeviceNotice } from './device-inbox';
import { WORLD } from './definition';
import { projectPrivateSignals, signalPresentation } from './private-signal-projection';
import { useWorldSignalReads } from './useWorldSignalReads';

export type WorldPrivateSignalsControl = ReturnType<typeof useWorldPrivateSignals>;
export function useWorldPrivateSignals(
  ownerId: string,
  enabled: boolean,
  onProactive?: (notice: Notification) => void
) {
  const { user } = useAuth();
  const { config } = useAppConfig();
  const authorized = enabled && user?.id === ownerId && user.is_active;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(authorized ? ownerId : undefined);
  const inbox = useMemo(() => new DeviceInbox(ownerId), [ownerId]);
  const notices = useSyncExternalStore(inbox.subscribe, inbox.snapshot, inbox.snapshot);
  const [gap, setGap] = useState<typeof inbox | null>(null);
  // What the instance offers NOW (the operator's switch included): a signal
  // must not point at a workspace the switch closed, nor read its routes.
  const smsEnabled = smsAvailable(config);
  const { isCurrent: isSmsCurrent } = useApplicationAccountLifetime(
    authorized && smsEnabled ? ownerId : undefined
  );
  const workboardEnabled = workboardAvailable(config);
  // The files LIA produced are a RECORD, read under the deployment ceiling
  // whatever a switch says (ADR-279): only uploading is an ability.
  const assetsEnabled = capabilityMounted(config, 'attachments');
  const resources = useWorldSignalReads(ownerId, authorized, workboardEnabled, assetsEnabled);
  const [acknowledged, setAcknowledged] = useState({
    inbox,
    revision: 0,
    props: new Set<string>(),
  });
  const receiveSms = useCallback(
    (signal: SmsReceivedSignal) => {
      if (isSmsCurrent()) inbox.receiveSms(signal);
    },
    [isSmsCurrent, inbox]
  );
  const receiveNotice = useCallback(
    (notice: Notification) => {
      if (!isCurrent()) return;
      if (notice.type.startsWith('proactive_')) onProactive?.(notice);
      inbox.receiveReminder(notice, performance.now());
    },
    [isCurrent, inbox, onProactive]
  );
  const refreshDurable = resources.refreshDurable;
  const reconnected = useCallback(() => {
    if (!isCurrent()) return;
    setGap(inbox);
    refreshDurable();
  }, [isCurrent, inbox, refreshDurable]);
  const { isConnected } = useNotifications({
    ownerId: authorized ? ownerId : undefined,
    isAuthenticated: authorized,
    onSmsReceived: receiveSms,
    onNotification: receiveNotice,
    onReconnected: reconnected,
  });
  useEffect(() => {
    if (smsEnabled) return;
    inbox.clearSms();
  }, [smsEnabled, inbox]);
  const entries = useMemo(() => {
    if (!authorized) return [];
    return smsEnabled ? notices : notices.filter(notice => notice.kind !== 'sms');
  }, [authorized, notices, smsEnabled]);
  const read = useCallback(
    (key: string): DeviceNotice | null => {
      if (!isCurrent()) return null;
      const notice = inbox.snapshot().find(item => item.key === key);
      if (!notice || (notice.kind === 'sms' && !isSmsCurrent())) return null;
      inbox.read(key);
      return notice;
    },
    [isCurrent, inbox, isSmsCurrent]
  );
  const signals = useMemo(
    () =>
      projectPrivateSignals(WORLD, {
        ownerId,
        snapshotOwnerId: ownerId,
        enabled: authorized,
        smsEnabled,
        workboardEnabled,
        assetsEnabled,
        entries,
        workboard: resources.workboard,
        images: resources.images,
        documents: resources.documents,
        screenshots: resources.screenshots,
      }).filter(
        signal =>
          !(
            acknowledged.inbox === inbox &&
            acknowledged.revision === resources.galleryRevision &&
            acknowledged.props.has(signal.propId)
          )
      ),
    [
      ownerId,
      authorized,
      smsEnabled,
      workboardEnabled,
      assetsEnabled,
      entries,
      resources,
      acknowledged,
      inbox,
    ]
  );
  const acknowledge = useCallback(
    (propId: string) => {
      if (
        !isCurrent() ||
        !signals.some(signal => signal.propId === propId && signal.target?.kind === 'gallery')
      )
        return;
      setAcknowledged(previous => ({
        inbox,
        revision: resources.galleryRevision,
        props: new Set(
          previous.inbox === inbox && previous.revision === resources.galleryRevision
            ? previous.props
            : []
        ).add(propId),
      }));
    },
    [isCurrent, signals, inbox, resources.galleryRevision]
  );
  const presentation = useMemo(() => signalPresentation(signals), [signals]);
  return {
    connected: isConnected,
    entries,
    read,
    acknowledge,
    signals,
    presentation,
    smsEnabled,
    remindersUncertain: gap === inbox,
    authorized,
    lifetime,
  };
}
