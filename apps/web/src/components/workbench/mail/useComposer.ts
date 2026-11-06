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
 * second copy beside it. The files chosen ride on the draft from its first save,
 * and those it holds leave it by name, so a save names only what changed.
 *
 * A quiet composer saves by itself, the words and the files, and says so; it may
 * fail, and says that too, and the person goes on. One save at a time: a send
 * waits for the one on its way, and reads the fields and the last save as they
 * stand then, never as they stood when it was pressed, or a file already on the
 * draft would join it a second time.
 *
 * A reply opens at once: who it reaches is read beside it, and from then on what
 * leaves is what the person sees. Nothing read, the provider computes it as the
 * line above the words says.
 *
 * « Send » first HOLDS the message for the moment the instance publishes, and
 * the person can take it back: nothing has left, the key is unspent. A screen
 * going away meanwhile sends it, since the person pressed « Send », and what
 * then fails is handed to `onLost`, there being no composer left to say it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import {
  composeFailure,
  filesToSend,
  holdsWords,
  initialFields,
  keptFiles,
  localProblem,
  reachFields,
  recipientsOf,
  writes,
  type ComposeFailure,
  type ComposerFields,
  type ComposerTarget,
  type RecipientField,
} from '@/lib/workbench/mail-compose';
import type { AttachableFile, MailAttachment, MailDraft, MailSent } from '@/lib/workbench/types';
import { generateUUID } from '@/lib/utils';

export type ComposerStatus = 'editing' | 'holding' | 'sending' | 'saving' | 'unknown';

/** What became of the composer's last save by itself. */
export type ComposerAutosave = 'idle' | 'saving' | 'saved' | 'failed';

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
  /** A file arrived: it joins what the message carries, whatever arrived meanwhile. */
  addFile: (file: AttachableFile) => void;
  status: ComposerStatus;
  problem: ComposerProblem | null;
  /** What is written differs from what was opened or last saved. */
  dirty: boolean;
  /** What the draft carries already; a file taken off it is gone from here at once. */
  heldFiles: MailAttachment[];
  /** Takes a file off the draft, at its next save. */
  dropHeldFile: (name: string) => void;
  autosave: ComposerAutosave;
  /** Who a reply reaches is read: the fields hold it, and the person may change it. */
  answered: boolean;
  send: () => Promise<void>;
  /** Takes back a message held: it comes back as it was written. */
  undoSend: () => void;
  saveDraft: () => Promise<void>;
}

export interface UseComposerOptions {
  target: ComposerTarget;
  writing: WorkbenchMailWriting;
  recipientsMax: number;
  /** It left (or a first press had already sent it). */
  onSent: (alreadySent: boolean) => void;
  onDraftSaved: () => void;
  /** How long a message waits before it leaves (0: it leaves at once). */
  holdMs?: number;
  /** How long a quiet composer waits before it saves a draft (0: never by itself). */
  autosaveMs?: number;
  /** What a body gains to carry the person's signature. */
  signatureBlock?: string;
  /** What was held could not leave and its composer is gone: its words, and why. */
  onLost?: (words: ComposerFields, failure: ComposeFailure) => void;
}

function newKey(): string {
  return generateUUID();
}

/** The message's words as the send and the save take them. */
function draftWords(fields: ComposerFields) {
  return {
    to: recipientsOf(fields.to),
    cc: recipientsOf(fields.cc),
    bcc: recipientsOf(fields.bcc),
    subject: fields.subject,
    body: fields.body,
  };
}

/** The words with their formatting, when the person wrote them so. */
function formattingOf(fields: ComposerFields): { html?: string } {
  return fields.html === null ? {} : { html: fields.html };
}

/** What two states are compared on: formatting turned on over nothing is nothing written. */
function wordsKey(fields: ComposerFields): string {
  return JSON.stringify({ ...fields, html: fields.html || null });
}

/** The alias a message leaves from, when the person chose one. */
function senderOf(fields: ComposerFields): { send_as?: string } {
  return fields.sendAs ? { send_as: fields.sendAs } : {};
}

/** A save: the words, the files that join, those that leave, and an alias newly chosen. */
function draftSave(fields: ComposerFields, saved: ComposerFields) {
  return {
    ...draftWords(fields),
    ...formattingOf(fields),
    ...filesToSend(fields.files),
    removed_files: fields.removedFiles,
    ...(fields.sendAs === saved.sendAs ? {} : senderOf(fields)),
  };
}

export function useComposer({
  target,
  writing,
  recipientsMax,
  onSent,
  onDraftSaved,
  holdMs = 0,
  autosaveMs = 0,
  signatureBlock = '',
  onLost,
}: UseComposerOptions): ComposerState {
  const [key] = useState(newKey);
  const [draftKey] = useState(newKey);
  const [fields, setFields] = useState<ComposerFields>(() => initialFields(target, signatureBlock));
  const [saved, setSaved] = useState<ComposerFields>(() => initialFields(target, signatureBlock));
  const [status, setStatus] = useState<ComposerStatus>('editing');
  const [problem, setProblem] = useState<ComposerProblem | null>(null);
  const [held, setHeld] = useState<MailAttachment[]>(
    target.kind === 'draft' ? target.draft.attachments : []
  );
  const [autosave, setAutosave] = useState<ComposerAutosave>('idle');
  const [answered, setAnswered] = useState(false);
  const draft = useRef<DraftHandle | null>(
    target.kind === 'draft' ? { id: target.draft.id, revision: target.draft.revision } : null
  );
  // Set synchronously: a second press lands before the render that shows the first.
  const busy = useRef(false);
  const holding = useRef<{ timer: number; leave: () => void } | null>(null);
  const mounted = useRef(true);
  // What a send that waited reads: the state as it stands, never as a closure saw it.
  const fieldsNow = useRef(fields);
  const savedNow = useRef(saved);
  const saving = useRef<Promise<void> | null>(null);
  const dirty = wordsKey(fields) !== wordsKey(saved);
  const { replyRecipients, saveDraft: saveToMailbox } = writing;

  const change = useCallback((next: (previous: ComposerFields) => ComposerFields) => {
    fieldsNow.current = next(fieldsNow.current);
    setFields(fieldsNow.current);
  }, []);

  const settle = useCallback((next: (previous: ComposerFields) => ComposerFields) => {
    savedNow.current = next(savedNow.current);
    setSaved(savedNow.current);
  }, []);

  useEffect(() => {
    if (target.kind !== 'reply') return;
    let open = true;
    replyRecipients(target.message.id, target.all).then(
      reach => {
        if (!open) return;
        const read = reachFields(reach);
        change(previous => ({ ...previous, ...read }));
        settle(previous => ({ ...previous, ...read }));
        setAnswered(true);
      },
      // Nothing read: the provider computes whom it answers, as it always has.
      () => undefined
    );
    return () => {
      open = false;
    };
  }, [change, replyRecipients, settle, target]);

  const set = useCallback(
    (fresh: Partial<ComposerFields>) => change(previous => ({ ...previous, ...fresh })),
    [change]
  );

  const addFile = useCallback(
    (file: AttachableFile) =>
      change(previous => ({ ...previous, files: [...previous.files, file] })),
    [change]
  );

  const dropHeldFile = useCallback(
    (name: string) =>
      change(previous => ({ ...previous, removedFiles: [...previous.removedFiles, name] })),
    [change]
  );

  /** What a save took: only what came after it is still to save. */
  const keep = useCallback(
    (stored: MailDraft | undefined, words: ComposerFields) => {
      if (!stored) return;
      draft.current = { id: stored.id, revision: stored.revision };
      change(previous => ({
        ...previous,
        files: previous.files.filter(file => !words.files.some(item => item.id === file.id)),
        removedFiles: previous.removedFiles.slice(words.removedFiles.length),
      }));
      settle(() => ({ ...words, files: [], removedFiles: [] }));
      setHeld(stored.attachments);
    },
    [change, settle]
  );

  /** Saves the message as a draft: created once, then changed against its revision. */
  const store = useCallback(
    async (words: ComposerFields) => {
      const handle = draft.current;
      const save = draftSave(words, savedNow.current);
      const stored = handle
        ? await saveToMailbox({
            draft_id: handle.id,
            expected_revision: handle.revision,
            ...save,
          })
        : await saveToMailbox({ ...save, idempotency_key: draftKey });
      keep(stored, words);
    },
    [draftKey, keep, saveToMailbox]
  );

  const quiet =
    autosaveMs > 0 && writes(target).bcc && dirty && holdsWords(fields) && status === 'editing';

  useEffect(() => {
    if (!quiet) return;
    const timer = window.setTimeout(() => {
      if (busy.current || saving.current) return;
      setAutosave('saving');
      saving.current = store(fieldsNow.current).then(
        () => {
          saving.current = null;
          setAutosave('saved');
        },
        () => {
          saving.current = null;
          setAutosave('failed');
        }
      );
    }, autosaveMs);
    return () => window.clearTimeout(timer);
  }, [autosaveMs, fields, quiet, store]);

  /** Sends the draft held: its latest words saved first, then that revision, once. */
  const sendStored = useCallback(
    async (words: ComposerFields, stored: DraftHandle): Promise<MailSent | undefined> => {
      let handle = stored;
      if (wordsKey(words) !== wordsKey(savedNow.current)) {
        await store(words);
        handle = draft.current ?? stored;
      }
      return writing.sendDraft({
        draft_id: handle.id,
        expected_revision: handle.revision,
        idempotency_key: key,
      });
    },
    [key, store, writing]
  );

  const deliver = useCallback(
    async (words: ComposerFields): Promise<MailSent | undefined> => {
      switch (target.kind) {
        case 'new': {
          const stored = draft.current;
          if (stored) return sendStored(words, stored);
          return writing.send({
            ...draftWords(words),
            ...formattingOf(words),
            ...filesToSend(words.files),
            ...senderOf(words),
            idempotency_key: key,
          });
        }
        case 'reply':
          return writing.reply({
            message_id: target.message.id,
            body: words.body,
            reply_all: target.all,
            ...(answered ? { to: recipientsOf(words.to), cc: recipientsOf(words.cc) } : {}),
            ...formattingOf(words),
            ...filesToSend(words.files),
            ...senderOf(words),
            idempotency_key: key,
          });
        case 'forward':
          return writing.forward({
            message_id: target.message.id,
            to: recipientsOf(words.to),
            cc: recipientsOf(words.cc),
            body: words.body,
            ...formattingOf(words),
            ...filesToSend(words.files),
            ...senderOf(words),
            idempotency_key: key,
          });
        case 'draft':
          return sendStored(
            words,
            draft.current ?? { id: target.draft.id, revision: target.draft.revision }
          );
      }
    },
    [answered, key, sendStored, target, writing]
  );

  const leave = useCallback(
    async (words: ComposerFields) => {
      busy.current = true;
      setStatus('sending');
      setProblem(null);
      try {
        await deliver(words);
        onSent(false);
      } catch (error: unknown) {
        const failure = composeFailure(error);
        if (failure.kind === 'already_sent') {
          onSent(true);
          return;
        }
        if (!mounted.current) {
          onLost?.(words, failure);
          return;
        }
        if (failure.kind === 'unknown') {
          setStatus('unknown');
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
    },
    [deliver, onLost, onSent]
  );

  const send = useCallback(async () => {
    if (busy.current || status === 'unknown') return;
    busy.current = true;
    await saving.current;
    const words = fieldsNow.current;
    const local = localProblem(words, target, recipientsMax, answered);
    if (local) {
      busy.current = false;
      setProblem(local);
      return;
    }
    if (holdMs <= 0) {
      await leave(words);
      return;
    }
    setProblem(null);
    setStatus('holding');
    const go = () => {
      holding.current = null;
      void leave(words);
    };
    holding.current = { timer: window.setTimeout(go, holdMs), leave: go };
  }, [answered, holdMs, leave, recipientsMax, status, target]);

  const undoSend = useCallback(() => {
    if (!holding.current) return;
    window.clearTimeout(holding.current.timer);
    holding.current = null;
    busy.current = false;
    setStatus('editing');
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (!holding.current) return;
      window.clearTimeout(holding.current.timer);
      holding.current.leave();
    };
  }, []);

  const saveDraft = useCallback(async () => {
    // A draft is written from a new message or a draft (Bcc and subject are theirs).
    if (busy.current || !writes(target).bcc) return;
    busy.current = true;
    setStatus('saving');
    setProblem(null);
    try {
      await saving.current;
      await store(fieldsNow.current);
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
  }, [onDraftSaved, store, target]);

  return {
    fields,
    set,
    addFile,
    status,
    problem,
    dirty,
    heldFiles: keptFiles(held, fields.removedFiles),
    dropHeldFile,
    autosave,
    answered,
    send,
    undoSend,
    saveDraft,
  };
}
