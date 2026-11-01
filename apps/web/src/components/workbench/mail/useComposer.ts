'use client';

/**
 * The composer's state (ADR-369, Task 4.7, Review focus 3).
 *
 * ONE key per open composer, minted when it mounts and kept until it closes:
 * a certain refusal frees it on the server (the person fixes and presses
 * « Send » again with it), an outcome nobody knows keeps it (a second press is
 * told, never sent). A synchronous guard takes the second press that lands
 * before the render showing the first — Enter in a field submits the form,
 * past any button's own guard. Nothing is ever sent again by the page itself.
 *
 * A draft is created once (its own key) and then changed against the revision
 * the composer holds; sending a draft whose words changed saves them first,
 * then sends that revision — what leaves is what the person saw. A new message
 * once saved as a draft IS that draft from then on: « Send » sends it, never a
 * second copy beside it. A draft keeps no file of the person's (the drafts
 * route carries words only), so files and a draft never go together.
 */
import { useCallback, useRef, useState } from 'react';

import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import {
  composeFailure,
  initialFields,
  localProblem,
  recipientsOf,
  writes,
  type ComposerFields,
  type ComposerTarget,
  type RecipientField,
} from '@/lib/workbench/mail-compose';
import type { MailDraft, MailSent } from '@/lib/workbench/types';

export type ComposerStatus = 'editing' | 'sending' | 'saving' | 'unknown';

/** What the composer says under a field, or above the form. */
export interface ComposerProblem {
  field?: RecipientField;
  key: string;
  values?: Record<string, number>;
}

interface DraftHandle {
  id: string;
  revision: string;
}

export interface ComposerState {
  fields: ComposerFields;
  set: (change: Partial<ComposerFields>) => void;
  status: ComposerStatus;
  problem: ComposerProblem | null;
  /** What is written differs from what was opened or last saved. */
  dirty: boolean;
  /** The composer holds a draft (opened from one, or saved as one): it carries no file. */
  drafted: boolean;
  send: () => Promise<void>;
  saveDraft: () => Promise<void>;
}

export interface UseComposerOptions {
  target: ComposerTarget;
  writing: WorkbenchMailWriting;
  recipientsMax: number;
  /** It left (or a first press had already sent it). */
  onSent: (alreadySent: boolean) => void;
  onDraftSaved: () => void;
}

function newKey(): string {
  return crypto.randomUUID();
}

/** The draft's words as the save route takes them. */
function draftWords(fields: ComposerFields) {
  return {
    to: recipientsOf(fields.to),
    cc: recipientsOf(fields.cc),
    bcc: recipientsOf(fields.bcc),
    subject: fields.subject,
    body: fields.body,
  };
}

export function useComposer({
  target,
  writing,
  recipientsMax,
  onSent,
  onDraftSaved,
}: UseComposerOptions): ComposerState {
  const [key] = useState(newKey);
  const [draftKey] = useState(newKey);
  const [fields, setFields] = useState<ComposerFields>(() => initialFields(target));
  const [saved, setSaved] = useState<ComposerFields>(() => initialFields(target));
  const [status, setStatus] = useState<ComposerStatus>('editing');
  const [problem, setProblem] = useState<ComposerProblem | null>(null);
  const [drafted, setDrafted] = useState(target.kind === 'draft');
  const draft = useRef<DraftHandle | null>(
    target.kind === 'draft' ? { id: target.draft.id, revision: target.draft.revision } : null
  );
  // Set synchronously: a second press lands before the render that shows the first.
  const busy = useRef(false);
  const dirty = JSON.stringify(fields) !== JSON.stringify(saved);

  const set = useCallback((change: Partial<ComposerFields>) => {
    setFields(previous => ({ ...previous, ...change }));
  }, []);

  const keep = useCallback((stored: MailDraft | undefined, words: ComposerFields) => {
    if (!stored) return;
    draft.current = { id: stored.id, revision: stored.revision };
    setSaved(words);
    setDrafted(true);
  }, []);

  /** Saves the words as a draft: created once, then changed against its revision. */
  const store = useCallback(
    async (words: ComposerFields) => {
      const handle = draft.current;
      const stored = handle
        ? await writing.saveDraft({
            draft_id: handle.id,
            expected_revision: handle.revision,
            ...draftWords(words),
          })
        : await writing.saveDraft({ ...draftWords(words), idempotency_key: draftKey });
      keep(stored, words);
    },
    [draftKey, keep, writing]
  );

  /** Sends the draft held: its latest words saved first, then that revision, once. */
  const sendStored = useCallback(
    async (words: ComposerFields, held: DraftHandle): Promise<MailSent | undefined> => {
      let handle = held;
      if (JSON.stringify(words) !== JSON.stringify(saved)) {
        await store(words);
        handle = draft.current ?? held;
      }
      return writing.sendDraft({
        draft_id: handle.id,
        expected_revision: handle.revision,
        idempotency_key: key,
      });
    },
    [key, saved, store, writing]
  );

  const deliver = useCallback(
    async (words: ComposerFields): Promise<MailSent | undefined> => {
      switch (target.kind) {
        case 'new': {
          const held = draft.current;
          if (held) return sendStored(words, held);
          return writing.send({
            ...draftWords(words),
            attachment_ids: words.files.map(file => file.id),
            idempotency_key: key,
          });
        }
        case 'reply':
          return writing.reply({
            message_id: target.message.id,
            body: words.body,
            reply_all: target.all,
            idempotency_key: key,
          });
        case 'forward':
          return writing.forward({
            message_id: target.message.id,
            to: recipientsOf(words.to),
            cc: recipientsOf(words.cc),
            body: words.body,
            idempotency_key: key,
          });
        case 'draft':
          return sendStored(
            words,
            draft.current ?? { id: target.draft.id, revision: target.draft.revision }
          );
      }
    },
    [key, sendStored, target, writing]
  );

  const send = useCallback(async () => {
    if (busy.current || status === 'unknown') return;
    const local = localProblem(fields, target, recipientsMax);
    if (local) {
      setProblem(local);
      return;
    }
    busy.current = true;
    setStatus('sending');
    setProblem(null);
    try {
      await deliver(fields);
      onSent(false);
    } catch (error: unknown) {
      const failure = composeFailure(error);
      if (failure.kind === 'unknown') {
        setStatus('unknown');
        return;
      }
      if (failure.kind === 'already_sent') {
        onSent(true);
        return;
      }
      setStatus('editing');
      const refusal = failure.refusal;
      setProblem(
        refusal
          ? {
              field: failure.kind === 'recipient' ? failure.field : undefined,
              key: refusal.key,
              values: refusal.values,
            }
          : { key: 'workbench.mail.compose.failed' }
      );
    } finally {
      busy.current = false;
    }
  }, [deliver, fields, onSent, recipientsMax, status, target]);

  const saveDraft = useCallback(async () => {
    // A draft is written from a new message or a draft (Bcc and subject are theirs).
    if (busy.current || !writes(target).bcc) return;
    if (fields.files.length > 0) {
      setProblem({ key: 'workbench.mail.compose.draft_no_files' });
      return;
    }
    busy.current = true;
    setStatus('saving');
    setProblem(null);
    try {
      await store(fields);
      onDraftSaved();
    } catch (error: unknown) {
      const refusal = composeFailure(error);
      setProblem(
        refusal.kind === 'refused' && refusal.refusal
          ? { key: refusal.refusal.key, values: refusal.refusal.values }
          : { key: 'workbench.mail.compose.save_failed' }
      );
    } finally {
      busy.current = false;
      setStatus(previous => (previous === 'saving' ? 'editing' : previous));
    }
  }, [fields, onDraftSaved, store, target]);

  return { fields, set, status, problem, dirty, drafted, send, saveDraft };
}
