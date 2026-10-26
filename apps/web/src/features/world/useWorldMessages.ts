'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import {
  WorldMailboxClient,
  type MailboxClientState,
  type MailboxPayload,
  type SendOutcome,
} from './mailbox-client';
import type { MailboxScope, MessageWrite } from './message-protocol';
import { useWorldAccountIdentity } from './WorldAccountGuard';

const INITIAL: MailboxClientState = {
  mailbox: null,
  status: 'connecting',
  sending: 'idle',
  unread: 0,
  unreadByRecipient: {},
  operation: null,
};

export function useWorldMessages(
  ownerId: string,
  enabled: boolean,
  getScope: () => MailboxScope | null,
  onAccepted: (message: Readonly<MessageWrite>) => void
) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const { verify } = useWorldAccountIdentity();
  const resource = useRef<WorldMailboxClient | null>(null);
  const lifetime = useMemo(() => ({ ownerId, enabled }), [ownerId, enabled]);
  const [stored, setStored] = useState({ lifetime, value: INITIAL });
  const { mutate } = useApiMutation<MailboxPayload, unknown>({
    method: 'POST',
    componentName: 'WorldMessages',
    retainResponse: false,
  });
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const client = new WorldMailboxClient({
      getScope,
      request: (endpoint, body, signal) => mutate(endpoint, body, { signal }),
      onState: value => {
        if (active && isCurrent()) setStored({ lifetime, value });
      },
      onAccepted: message => {
        if (active && isCurrent()) onAccepted(message);
      },
      onRevoked: () => {
        if (active && isCurrent()) void verify();
      },
    });
    resource.current = client;
    client.start();
    return () => {
      active = false;
      client.stop();
      if (resource.current === client) resource.current = null;
    };
  }, [enabled, lifetime, getScope, isCurrent, mutate, onAccepted, verify]);
  const send = useCallback(
    (recipient: string, text: string, consent: boolean) =>
      isCurrent()
        ? (resource.current?.send(recipient, text, consent) ??
          Promise.resolve<SendOutcome>('unavailable'))
        : Promise.resolve<SendOutcome>('unavailable'),
    [isCurrent]
  );
  const sendPublic = useCallback(
    (text: string, consent: boolean) =>
      isCurrent()
        ? (resource.current?.sendPublic(text, consent) ??
          Promise.resolve<SendOutcome>('unavailable'))
        : Promise.resolve<SendOutcome>('unavailable'),
    [isCurrent]
  );
  const translate = useCallback(
    (message: string, consent: boolean) =>
      isCurrent()
        ? (resource.current?.translate(message, consent) ??
          Promise.resolve<SendOutcome>('unavailable'))
        : Promise.resolve<SendOutcome>('unavailable'),
    [isCurrent]
  );
  const check = useCallback(
    () =>
      isCurrent() ? (resource.current?.check() ?? Promise.resolve(false)) : Promise.resolve(false),
    [isCurrent]
  );
  const discard = useCallback(() => {
    if (isCurrent()) resource.current?.discard();
  }, [isCurrent]);
  const retry = useCallback(() => {
    if (isCurrent()) resource.current?.retry();
  }, [isCurrent]);
  const setReading = useCallback(
    (value: boolean, recipient: string | null = null) => {
      if (isCurrent()) resource.current?.setReading(value, recipient);
    },
    [isCurrent]
  );
  return {
    state: enabled && stored.lifetime === lifetime ? stored.value : INITIAL,
    send,
    sendPublic,
    translate,
    check,
    discard,
    retry,
    setReading,
  };
}
