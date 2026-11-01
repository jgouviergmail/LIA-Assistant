'use client';

/**
 * Composer — a new message, a reply, a forward or a draft (ADR-369, Task 4.7).
 *
 * A dialog on a large screen, the whole screen on a phone. The recipients are
 * typed with the account's contacts suggested (the Tools door, which files
 * nothing: the person types); the subject and the text are bounded by the
 * very limits the send refuses beyond (ADR-184); a new message may carry the
 * person's own files. « Send » is held while the message leaves; when nobody
 * knows whether it left, what was written stays and the person is told to look
 * in Sent — the page never sends it again by itself (ADR-221). Closing with
 * words not sent nor saved asks first.
 */
import { Paperclip, Send, X } from 'lucide-react';
import { useId, useState } from 'react';

import { RecipientCombobox } from '@/components/email-share/RecipientCombobox';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useConfirm } from '@/components/ui/use-confirm';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { addressLabel, fileSize } from '@/lib/workbench/mail';
import { writes, type ComposerTarget, type RecipientField } from '@/lib/workbench/mail-compose';
import { WORKBENCH_RECIPIENTS_PATH } from '@/lib/workbench/recipients';
import type { AttachableFile, WorkbenchToolAvailability } from '@/lib/workbench/types';

import { AttachablePicker } from './AttachablePicker';
import { useComposer, type ComposerState } from './useComposer';

/** The published bounds the composer draws, each with a fallback the send would refuse anyway. */
function boundsOf(tool: WorkbenchToolAvailability) {
  const bound = (name: string) => tool.bounds[name];
  return {
    recipientsMax: bound('recipients_max') ?? Number.POSITIVE_INFINITY,
    subjectMax: bound('subject_max_chars'),
    bodyMax: bound('body_max_chars'),
    filesMax: bound('attachments_max') ?? 0,
    filesMaxBytes: bound('attachments_max_bytes') ?? 0,
    queryMin: bound('recipient_query_min_chars') ?? 2,
  };
}

export interface ComposerProps {
  lng: Language;
  target: ComposerTarget;
  tool: WorkbenchToolAvailability;
  writing: WorkbenchMailWriting;
  onClose: () => void;
  onSent: (alreadySent: boolean) => void;
  onDraftSaved: () => void;
}

export function Composer({
  lng,
  target,
  tool,
  writing,
  onClose,
  onSent,
  onDraftSaved,
}: ComposerProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const [picking, setPicking] = useState(false);
  const bounds = boundsOf(tool);
  const parts = writes(target);
  const offersFiles = parts.files && tool.features.includes('attachments');
  const state = useComposer({
    target,
    writing,
    recipientsMax: bounds.recipientsMax,
    onSent,
    onDraftSaved,
  });
  const { fields, set } = state;
  const context = contextOf(target);

  const requestClose = async () => {
    if (state.status === 'sending') return;
    const discard =
      !state.dirty ||
      (await confirm({
        title: t('workbench.mail.compose.discard_title'),
        description: t('workbench.mail.compose.discard_description'),
        confirmLabel: t('workbench.mail.compose.discard'),
      }));
    if (discard) onClose();
  };

  return (
    <Dialog open onOpenChange={open => !open && void requestClose()}>
      <DialogContent className="max-sm:inset-0 max-sm:left-0 max-sm:top-0 max-sm:h-dvh max-sm:max-h-none max-sm:w-screen max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-none max-sm:border-0 sm:max-w-2xl">
        <form
          className="flex min-h-0 flex-col gap-4"
          onSubmit={event => {
            event.preventDefault();
            void state.send();
          }}
        >
          <DialogHeader>
            <DialogTitle>{t(`workbench.mail.compose.title_${titleOf(target)}`)}</DialogTitle>
            <DialogDescription>{t(context.key, context.values)}</DialogDescription>
          </DialogHeader>
          {parts.recipients && (
            <RecipientFields lng={lng} target={target} state={state} queryMin={bounds.queryMin} />
          )}
          {parts.subject && (
            <Input
              label={t('workbench.mail.compose.subject')}
              value={fields.subject}
              maxLength={bounds.subjectMax}
              onChange={event => set({ subject: event.target.value })}
            />
          )}
          <Textarea
            label={t('workbench.mail.compose.body')}
            value={fields.body}
            maxLength={bounds.bodyMax}
            rows={10}
            onChange={event => set({ body: event.target.value })}
            className="min-h-48"
          />
          {offersFiles && !state.drafted && (
            <FilesField
              lng={lng}
              files={fields.files}
              onRemove={id => set({ files: fields.files.filter(file => file.id !== id) })}
              onPick={() => setPicking(true)}
            />
          )}
          <ComposerNotices lng={lng} state={state} />
          <ComposerFooter
            lng={lng}
            state={state}
            offersDrafts={parts.bcc && tool.features.includes('drafts')}
            onCancel={() => void requestClose()}
          />
        </form>
        {offersFiles && (
          <AttachablePicker
            lng={lng}
            open={picking}
            onOpenChange={setPicking}
            chosen={fields.files}
            maxFiles={bounds.filesMax}
            maxBytes={bounds.filesMaxBytes}
            onToggle={file => set({ files: toggleFile(fields.files, file) })}
          />
        )}
        {confirmDialog}
      </DialogContent>
    </Dialog>
  );
}

/** A file chosen once, or taken back. */
function toggleFile(files: readonly AttachableFile[], file: AttachableFile): AttachableFile[] {
  return files.some(item => item.id === file.id)
    ? files.filter(item => item.id !== file.id)
    : [...files, file];
}

interface RecipientFieldsProps {
  lng: Language;
  target: ComposerTarget;
  state: ComposerState;
  queryMin: number;
}

/** To, and on demand Cc (and Bcc where the target carries it), contacts suggested. */
function RecipientFields({ lng, target, state, queryMin }: RecipientFieldsProps) {
  const { t } = useTranslation(lng);
  const [shown, setShown] = useState(target.kind === 'draft' && target.draft.cc.length > 0);
  const copiesId = useId();
  const { fields, set, problem } = state;
  const withBcc = writes(target).bcc;
  const field = (name: RecipientField, labelKey: string) => (
    <RecipientCombobox
      value={fields[name]}
      onChange={value => set({ [name]: value })}
      label={t(labelKey)}
      placeholder={t('workbench.mail.compose.recipients_placeholder')}
      error={problem?.field === name ? t(problem.key, problem.values) : undefined}
      minChars={queryMin}
      suggestionsPath={WORKBENCH_RECIPIENTS_PATH}
    />
  );
  return (
    <div className="space-y-3">
      {field('to', 'workbench.mail.compose.to')}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setShown(open => !open)}
        aria-expanded={shown}
        aria-controls={copiesId}
      >
        {t(withBcc ? 'workbench.mail.compose.show_cc_bcc' : 'workbench.mail.compose.show_cc')}
      </Button>
      {shown && (
        <div id={copiesId} className="space-y-3">
          {field('cc', 'workbench.mail.compose.cc')}
          {withBcc && field('bcc', 'workbench.mail.compose.bcc')}
        </div>
      )}
    </div>
  );
}

/** A refusal said above the form, and what to do when nobody knows whether it left. */
function ComposerNotices({ lng, state }: { lng: Language; state: ComposerState }) {
  const { t } = useTranslation(lng);
  const { problem, status } = state;
  return (
    <>
      {problem && !problem.field && (
        <p role="alert" className="text-sm text-destructive">
          {t(problem.key, problem.values)}
        </p>
      )}
      {status === 'unknown' && (
        <p role="alert" className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
          {t('workbench.mail.compose.unknown')}
        </p>
      )}
    </>
  );
}

interface ComposerFooterProps {
  lng: Language;
  state: ComposerState;
  offersDrafts: boolean;
  onCancel: () => void;
}

/** Save as a draft (where the provider keeps drafts), cancel, send — held while busy. */
function ComposerFooter({ lng, state, offersDrafts, onCancel }: ComposerFooterProps) {
  const { t } = useTranslation(lng);
  const { status } = state;
  const settled = status === 'unknown';
  return (
    <DialogFooter className="gap-2 max-sm:mt-auto">
      {offersDrafts && (
        <Button
          type="button"
          variant="outline"
          isLoading={status === 'saving'}
          aria-disabled={status === 'sending' || settled || undefined}
          onClick={() => void state.saveDraft()}
        >
          {t('workbench.mail.compose.save_draft')}
        </Button>
      )}
      <Button type="button" variant="ghost" onClick={onCancel}>
        <X className="h-4 w-4" aria-hidden="true" />
        {t('common.cancel')}
      </Button>
      <Button
        type="submit"
        isLoading={status === 'sending'}
        aria-disabled={settled || status === 'saving' || undefined}
        className="gap-1.5"
      >
        <Send className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.compose.send')}
      </Button>
    </DialogFooter>
  );
}

function titleOf(target: ComposerTarget): string {
  if (target.kind === 'reply') return target.all ? 'reply_all' : 'reply';
  return target.kind;
}

/** Whom a reply goes to, what a forward carries, or what a new message is (a key and its values). */
function contextOf(target: ComposerTarget): {
  key: string;
  values?: Record<string, string | number>;
} {
  if (target.kind === 'reply') {
    const { message } = target;
    const to =
      message.reply_to.length > 0 ? message.reply_to : message.sender ? [message.sender] : [];
    return {
      key: target.all
        ? 'workbench.mail.compose.reply_all_line'
        : 'workbench.mail.compose.reply_line',
      values: { names: to.map(addressLabel).join(', '), subject: message.subject },
    };
  }
  if (target.kind === 'forward') {
    const count = target.message.attachments.length;
    return count === 0
      ? { key: 'workbench.mail.compose.forward_line', values: { subject: target.message.subject } }
      : {
          key: 'workbench.mail.compose.forward_files',
          values: { subject: target.message.subject, count },
        };
  }
  if (target.kind === 'draft' && target.draft.attachments.length > 0) {
    return {
      key: 'workbench.mail.compose.draft_files',
      values: { count: target.draft.attachments.length },
    };
  }
  return { key: 'workbench.mail.compose.new_line' };
}

function FilesField({
  lng,
  files,
  onRemove,
  onPick,
}: {
  lng: Language;
  files: readonly { id: string; filename: string; size: number }[];
  onRemove: (id: string) => void;
  onPick: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <div className="space-y-2">
      {files.length > 0 && (
        <ul aria-label={t('workbench.mail.files.chosen')} className="flex flex-wrap gap-2">
          {files.map(file => (
            <li
              key={file.id}
              className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card py-1 pl-3 pr-1 text-sm"
            >
              <span className="truncate">{file.filename}</span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {fileSize(file.size, lng)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => onRemove(file.id)}
                aria-label={t('workbench.mail.files.remove', { name: file.filename })}
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={onPick}>
        <Paperclip className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.files.add')}
      </Button>
    </div>
  );
}
