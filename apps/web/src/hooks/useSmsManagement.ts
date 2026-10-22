'use client';

import { useCallback, useRef } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import {
  useApplicationAccountLifetime,
  type ApplicationAccountLifetime,
} from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountState } from '@/hooks/useApplicationAccountState';
import { publishApplicationResources } from '@/lib/application-resources';
import {
  smsCompletionSchema,
  smsProposalSchema,
  smsSingleEraseProposalSchema,
  type SmsJson,
  type SmsOperation,
  type SmsProposal,
} from '@/types/sms';

/** Only an explicit confirm sends the reviewed digest. Secret delivery is never retried. */
export function useSmsManagement() {
  const { user } = useAuth();
  const owner = user?.id;
  const { lifetime, isCurrent } = useApplicationAccountLifetime(owner);
  const [proposal, setProposal] = useApplicationAccountState<SmsProposal | null>(owner, null);
  const [secret, setSecret] = useApplicationAccountState<string | null>(owner, null);
  const [uncertain, setUncertain] = useApplicationAccountState(owner, false);
  const [error, setError] = useApplicationAccountState(owner, false);
  const [busy, setBusy] = useApplicationAccountState(owner, false);
  const inFlight = useRef<ApplicationAccountLifetime | null>(null);
  const { mutate } = useApiMutation<Record<string, SmsJson>, unknown>({
    method: 'POST',
    componentName: 'useSmsManagement',
    retainResponse: false,
  });
  const propose = useCallback(
    async (operation_id: SmsOperation, payload: Record<string, SmsJson>) => {
      if (!isCurrent() || inFlight.current === lifetime || proposal) return;
      inFlight.current = lifetime;
      setBusy(true);
      setError(false);
      setUncertain(false);
      try {
        const selected = smsProposalSchema.parse(
          await mutate('/sms/commands', { operation_id, payload })
        );
        if (isCurrent()) setProposal(selected);
      } catch {
        if (isCurrent()) setError(true);
      } finally {
        if (inFlight.current === lifetime) inFlight.current = null;
        setBusy(false);
      }
    },
    [isCurrent, lifetime, proposal, mutate, setBusy, setError, setUncertain, setProposal]
  );
  const confirm = useCallback(async () => {
    if (!isCurrent() || !proposal || inFlight.current === lifetime) return;
    const selected = proposal;
    if (Date.parse(selected.expires_at) <= Date.now()) {
      setProposal(null);
      setError(true);
      return;
    }
    inFlight.current = lifetime;
    setBusy(true);
    setError(false);
    try {
      const completed = smsCompletionSchema.parse(
        await mutate(`/sms/commands/${selected.command_id}/confirm`, {
          content_digest: selected.content_digest,
        })
      );
      if (!isCurrent()) return;
      if (completed.secret && selected.operation_id === 'sms_token.create')
        setSecret(completed.secret.token);
      if (owner) publishApplicationResources(owner, new Set(['sms']));
    } catch {
      if (isCurrent()) {
        setUncertain(true);
        if (owner) publishApplicationResources(owner, new Set(['sms']));
      }
    } finally {
      if (inFlight.current === lifetime) inFlight.current = null;
      setProposal(null);
      setBusy(false);
    }
  }, [
    isCurrent,
    proposal,
    lifetime,
    setProposal,
    setError,
    setBusy,
    mutate,
    setSecret,
    owner,
    setUncertain,
  ]);
  const cancel = useCallback(async () => {
    if (!isCurrent() || !proposal || inFlight.current === lifetime) return;
    const selected = proposal;
    setProposal(null);
    try {
      await mutate(`/sms/commands/${selected.command_id}/cancel`, {});
    } catch {
      if (isCurrent()) setError(true);
    }
  }, [isCurrent, proposal, lifetime, setProposal, mutate, setError]);
  const clearSecret = useCallback(() => {
    setSecret(null);
  }, [setSecret]);
  const eraseMessage = useCallback(
    async (messageId: string) => {
      if (!isCurrent() || proposal || inFlight.current === lifetime) return;
      inFlight.current = lifetime;
      setBusy(true);
      setError(false);
      setUncertain(false);
      let confirming = false;
      try {
        const selected = smsSingleEraseProposalSchema.parse(
          await mutate('/sms/commands', {
            operation_id: 'sms_messages.delete',
            payload: { message_ids: [messageId] },
          })
        );
        if (!isCurrent()) return;
        if (
          selected.before.sms_messages_to_delete.message_ids[0] !== messageId ||
          Date.parse(selected.expires_at) <= Date.now()
        )
          throw new Error('sms_single_delete_scope');
        confirming = true;
        smsCompletionSchema.parse(
          await mutate(`/sms/commands/${selected.command_id}/confirm`, {
            content_digest: selected.content_digest,
          })
        );
      } catch {
        if (isCurrent()) {
          if (confirming) setUncertain(true);
          else setError(true);
        }
      } finally {
        if (inFlight.current === lifetime) inFlight.current = null;
        if (isCurrent() && owner) publishApplicationResources(owner, new Set(['sms']));
        setBusy(false);
      }
    },
    [isCurrent, proposal, lifetime, mutate, owner, setBusy, setError, setUncertain]
  );
  return {
    proposal,
    secret,
    uncertain,
    error,
    busy,
    propose,
    confirm,
    cancel,
    clearSecret,
    eraseMessage,
  };
}
