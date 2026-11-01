'use client';

/**
 * The mail screen's writing acts (ADR-369, Task 4.7): a new message, a reply,
 * a forward, a draft saved or sent.
 *
 * Each carries the key of its submission, minted once per open composer and
 * kept until it closes: the server claims the key before the provider is
 * called, frees it on a CERTAIN failure (the person may fix and press « Send »
 * again) and keeps it when the outcome is unknown, so a second press is told
 * what became of the first and never sends twice (ADR-221). Nothing here
 * retries: a refusal is rethrown for the composer to say.
 */
import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import type { MailDraft, MailSent } from '@/lib/workbench/types';

const MAIL = '/workbench/mail';

/** A new message (`schemas/mail_compose.NewMessage`): recipients one per entry, as typed. */
export interface NewMailBody {
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body: string;
  attachment_ids: string[];
  idempotency_key: string;
}

/** A reply to a message: its thread and its subject are the message's. */
export interface MailReplyBody {
  message_id: string;
  body: string;
  reply_all: boolean;
  idempotency_key: string;
}

/** A message forwarded with its files. */
export interface MailForwardBody {
  message_id: string;
  to: string[];
  cc: string[];
  body: string;
  idempotency_key: string;
}

/** A draft created (no `draft_id`, a key) or changed against its revision. */
export interface MailDraftSaveBody {
  draft_id?: string;
  expected_revision?: string;
  to?: string[];
  cc?: string[];
  bcc?: string[];
  subject?: string;
  body?: string;
  idempotency_key?: string;
}

/** A draft sent as the editor last saw it. */
export interface MailDraftSendBody {
  draft_id: string;
  expected_revision: string;
  idempotency_key: string;
}

export interface WorkbenchMailWriting {
  send: (body: NewMailBody) => Promise<MailSent | undefined>;
  reply: (body: MailReplyBody) => Promise<MailSent | undefined>;
  forward: (body: MailForwardBody) => Promise<MailSent | undefined>;
  saveDraft: (body: MailDraftSaveBody) => Promise<MailDraft | undefined>;
  sendDraft: (body: MailDraftSendBody) => Promise<MailSent | undefined>;
}

export function useWorkbenchMailWriting(): WorkbenchMailWriting {
  const { mutate: postSent } = useApiMutation<object, MailSent>({
    method: 'POST',
    componentName: 'WorkbenchMailWriting',
    retainResponse: false,
  });
  const { mutate: postDraft } = useApiMutation<MailDraftSaveBody, MailDraft>({
    method: 'POST',
    componentName: 'WorkbenchMailWriting',
    retainResponse: false,
  });

  const send = useCallback((body: NewMailBody) => postSent(`${MAIL}/send`, body), [postSent]);
  const reply = useCallback((body: MailReplyBody) => postSent(`${MAIL}/reply`, body), [postSent]);
  const forward = useCallback(
    (body: MailForwardBody) => postSent(`${MAIL}/forward`, body),
    [postSent]
  );
  const saveDraft = useCallback(
    (body: MailDraftSaveBody) => postDraft(`${MAIL}/drafts`, body),
    [postDraft]
  );
  const sendDraft = useCallback(
    (body: MailDraftSendBody) => postSent(`${MAIL}/drafts/send`, body),
    [postSent]
  );
  return { send, reply, forward, saveDraft, sendDraft };
}
