'use client';

/**
 * Composer — a new message, a reply, a forward or a draft (ADR-369, Task 4.7).
 *
 * A window docked at the corner of a large screen, so the mail stays readable and
 * usable behind it; the whole screen on a phone, where a reply and a forward
 * keep the message in sight above their own words. Nothing behind it is hidden
 * or trapped: its focus is its own, and given back when it closes. The recipients
 * are typed with the account's contacts suggested (the Tools door, which files
 * nothing: the person types); the subject and the text are bounded by the
 * very limits the send refuses beyond (ADR-184); a message and an answer may carry
 * the person's own files and those of the device, chosen or dropped, and nothing
 * leaves while one is on its way; who a reply reaches shows as soon as it is read.
 * « Send » is held while the message leaves; when nobody
 * knows whether it left, what was written stays and the person is told to look
 * in Sent — the page never sends it again by itself (ADR-221). Closing with
 * words not sent nor saved asks first, and so does the browser leaving the page;
 * words a quiet composer saved by itself are in the drafts, and closing says so.
 * « Send » first holds the message for a moment, the composer aside and « Undo »
 * in its place (`useComposer`). LIA writes from the end of the subject's label and of the
 * message's: what it proposes changes nothing until the person says so. An answer is kept as a
 * draft in its thread, and the composer closes on it. On a phone every button of the page's end
 * stands on its own line, the whole width (owner, 2026-11-06).
 */
import { Paperclip, Send, Type, Upload, X } from 'lucide-react';
import {
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type RefObject,
} from 'react';

import { RecipientCombobox } from '@/components/email-share/RecipientCombobox';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LinkedText } from '@/components/ui/linked-text';
import { NativeSelect } from '@/components/ui/native-select';
import { Textarea } from '@/components/ui/textarea';
import type { WorkbenchMailWriting } from '@/hooks/useWorkbenchMailWriting';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { addressLabel, fileSize } from '@/lib/workbench/mail';
import {
  senderShown,
  textToHtml,
  withProposal,
  writes,
  type ComposeFailure,
  type ComposerFields,
  type ComposerTarget,
  type RecipientField,
} from '@/lib/workbench/mail-compose';
import { WORKBENCH_RECIPIENTS_PATH } from '@/lib/workbench/recipients';
import type {
  AttachableFile,
  MailAttachment,
  MailSender,
  WorkbenchToolAvailability,
} from '@/lib/workbench/types';

import { ComposerAssist, type ComposerAssistProps } from '../assist/ComposerAssist';
import { FileSendingLine, useFileDrop } from '../files/FileSending';
import { CancelButton, ToolActions, useToolConfirm } from '../ToolForm';
import { AttachablePicker } from './AttachablePicker';
import { RichBody } from './RichBody';
import { useComposer, type ComposerState } from './useComposer';
import { useDeviceFiles } from './useDeviceFiles';

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
  /** What one file of the device may weigh. */
  uploadMaxBytes: number;
  /** How long « Send » waits before the message leaves (0: at once). */
  holdMs?: number;
  /** How long a quiet composer waits before it saves a draft (0: never by itself). */
  autosaveMs?: number;
  /** What a body gains to carry the person's signature. */
  signatureBlock?: string;
  /** The addresses the mailbox sends from: a choice from two up. */
  senders?: readonly MailSender[];
  /** What was held could not leave and the composer is gone. */
  onLost?: (words: ComposerFields, failure: ComposeFailure) => void;
}

/** A small button that takes a line of its own on a phone, as the page's last ones do. */
const WHOLE_ON_A_PHONE = 'max-sm:h-9 max-sm:w-full';
/** The first field to write in: the recipients, or the words of a reply. */
const FIRST_FIELD = 'input, textarea';
/** Where the words are written, whichever the person chose. */
const BODY_FIELD = 'textarea, [contenteditable="true"]';

export function Composer({
  lng,
  target,
  tool,
  writing,
  onClose,
  onSent,
  onDraftSaved,
  uploadMaxBytes,
  holdMs = 0,
  autosaveMs = 0,
  signatureBlock = '',
  senders = [],
  onLost,
}: ComposerProps) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useToolConfirm();
  const [picking, setPicking] = useState(false);
  // The formatted field reads its words once: words LIA wrote open a new one.
  const [edition, setEdition] = useState(0);
  const bounds = boundsOf(tool);
  const state = useComposer({
    target,
    writing,
    recipientsMax: bounds.recipientsMax,
    onSent,
    onDraftSaved: () => {
      onDraftSaved();
      if (target.kind === 'reply' || target.kind === 'forward') onClose();
    },
    holdMs,
    autosaveMs: tool.features.includes('drafts') ? autosaveMs : 0,
    signatureBlock,
    onLost,
  });
  const { fields, set } = state;
  const parts = writes(target, state.answered);
  const offersFiles = parts.files && tool.features.includes('attachments');
  const carried = state.heldFiles.map(file => ({ size: file.size ?? 0 }));
  const device = useDeviceFiles({
    lng,
    chosen: [...fields.files, ...carried],
    bounds: {
      maxFiles: bounds.filesMax,
      maxBytes: bounds.filesMaxBytes,
      eachMaxBytes: Math.min(uploadMaxBytes, bounds.filesMaxBytes),
    },
    onKept: state.addFile,
  });
  const drop = useFileDrop({ lng, enabled: offersFiles, onFiles: device.send });
  const uploading = device.now !== null;
  const context = contextOf(target, state.answered);
  const assisted: Omit<ComposerAssistProps, 'field'> = {
    lng,
    target,
    fields,
    signature: signatureBlock,
    writesSubject: parts.subject,
    onBody: (answer, use) => {
      // A subject the person wrote stays unless they chose to replace what they wrote.
      const free = use === 'replace' || fields.subject.trim() === '';
      const subject = parts.subject && answer.subject && free ? { subject: answer.subject } : {};
      set({ ...withProposal(fields, signatureBlock, answer.text, use), ...subject });
      setEdition(previous => previous + 1);
    },
    onSubject: subject => set({ subject }),
  };
  const panel = useRef<HTMLElement>(null);
  const undo = useRef<HTMLButtonElement>(null);
  const wasHolding = useRef(false);
  const titleId = useId();
  const lineId = useId();
  const holding = state.status === 'holding';
  const atStake = holding || state.dirty;

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.querySelector<HTMLElement>(FIRST_FIELD)?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, []);
  useEffect(() => {
    if (holding) undo.current?.focus();
    else if (wasHolding.current) panel.current?.querySelector<HTMLElement>(BODY_FIELD)?.focus();
    wasHolding.current = holding;
  }, [holding]);
  useEffect(() => {
    if (!atStake) return;
    const guard = (event: Event) => event.preventDefault();
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [atStake]);

  const requestClose = async () => {
    if (state.status === 'sending') return;
    const discard =
      !state.dirty ||
      (await confirm({
        title: t('workbench.mail.compose.discard_title'),
        description: t('workbench.mail.compose.discard_description'),
        confirmLabel: t('workbench.mail.compose.discard'),
      }));
    if (!discard) return;
    if (state.autosave === 'saved') onDraftSaved();
    onClose();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Escape' || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    void requestClose();
  };

  return (
    <>
      <HoldingNotice lng={lng} holding={holding} undo={undo} onUndo={state.undoSend} />
      <section
        ref={panel}
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        aria-describedby={lineId}
        hidden={holding}
        onKeyDown={onKeyDown}
        {...drop.handlers}
        className={cn(
          'fixed z-50 flex-col bg-card shadow-2xl max-sm:inset-0 sm:bottom-4 sm:right-4 sm:max-h-[calc(100dvh-2rem)] sm:w-[min(42rem,calc(100vw-2rem))] sm:rounded-lg sm:border',
          holding ? 'hidden' : 'flex'
        )}
      >
        <form
          className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4"
          onSubmit={event => {
            event.preventDefault();
            if (!uploading) void state.send();
          }}
        >
          <div className="space-y-1">
            <h2 id={titleId} className="text-base font-semibold">
              {t(`workbench.mail.compose.title_${titleOf(target)}`)}
            </h2>
            <p id={lineId} className="text-sm text-muted-foreground">
              {t(context.key, context.values)}
            </p>
          </div>
          {parts.recipients && (
            <RecipientFields
              lng={lng}
              target={target}
              state={state}
              senders={senders}
              queryMin={bounds.queryMin}
            />
          )}
          {parts.subject && (
            <Input
              label={t('workbench.mail.compose.subject')}
              labelEnd={<ComposerAssist field="subject" {...assisted} />}
              value={fields.subject}
              maxLength={bounds.subjectMax}
              onChange={event => set({ subject: event.target.value })}
            />
          )}
          <BodyField
            lng={lng}
            state={state}
            maxLength={bounds.bodyMax}
            edition={edition}
            assist={<ComposerAssist field="body" {...assisted} />}
          />
          <AnsweredMessage lng={lng} target={target} />
          {offersFiles && (
            <FilesField
              lng={lng}
              files={fields.files}
              held={state.heldFiles}
              onRemove={id => set({ files: fields.files.filter(file => file.id !== id) })}
              onDropHeld={state.dropHeldFile}
              onPick={() => setPicking(true)}
              onDevice={device.send}
            />
          )}
          {device.now && <FileSendingLine lng={lng} now={device.now} onStop={device.stop} />}
          <ComposerNotices lng={lng} state={state} />
          <ComposerFooter
            lng={lng}
            state={state}
            uploading={uploading}
            offersDrafts={tool.features.includes('drafts')}
            onCancel={() => void requestClose()}
          />
        </form>
        <DropVeil lng={lng} dragging={drop.dragging} />
        {offersFiles && (
          <AttachablePicker
            lng={lng}
            open={picking}
            onOpenChange={setPicking}
            chosen={fields.files}
            carried={carried}
            maxFiles={bounds.filesMax}
            maxBytes={bounds.filesMaxBytes}
            onToggle={file => set({ files: toggleFile(fields.files, file) })}
          />
        )}
        {confirmDialog}
      </section>
    </>
  );
}

/** The words of the message, plain or formatted: the person's choice, for this message. */
function BodyField({
  lng,
  state,
  maxLength,
  edition,
  assist,
}: {
  lng: Language;
  state: ComposerState;
  maxLength: number | undefined;
  /** How many times LIA's words opened a new formatted field. */
  edition: number;
  /** Outside whichever field is drawn: a line asked at the opening is asked once. */
  assist: ReactNode;
}) {
  const { t } = useTranslation(lng);
  const { fields, set } = state;
  const formatted = fields.html !== null;
  const fieldId = useId();
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={formatted ? undefined : fieldId}>{t('workbench.mail.compose.body')}</Label>
        {assist}
      </div>
      {fields.html !== null ? (
        <RichBody
          key={edition}
          lng={lng}
          html={fields.html}
          onChange={(html, body) => set({ html, body })}
        />
      ) : (
        <Textarea
          id={fieldId}
          value={fields.body}
          maxLength={maxLength}
          rows={8}
          onChange={event => set({ body: event.target.value })}
          className="min-h-36"
        />
      )}
      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn('gap-1.5', WHOLE_ON_A_PHONE)}
          aria-pressed={formatted}
          onClick={() => set({ html: formatted ? null : textToHtml(fields.body) })}
        >
          <Type className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.compose.format')}
        </Button>
      </div>
    </div>
  );
}

/** The message held for its moment, and the way to take it back. */
function HoldingNotice({
  lng,
  holding,
  undo,
  onUndo,
}: {
  lng: Language;
  holding: boolean;
  undo: RefObject<HTMLButtonElement | null>;
  onUndo: () => void;
}) {
  const { t } = useTranslation(lng);
  if (!holding) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex items-center gap-3 rounded-lg border bg-card px-4 py-2 shadow-lg">
      <span role="status" className="text-sm">
        {t('workbench.mail.compose.holding')}
      </span>
      <CancelButton
        ref={undo}
        lng={lng}
        size="sm"
        label={t('workbench.mail.compose.undo')}
        onClick={onUndo}
      />
    </div>
  );
}

/** What a drag of files over the composer sees. */
function DropVeil({ lng, dragging }: { lng: Language; dragging: boolean }) {
  const { t } = useTranslation(lng);
  if (!dragging) return null;
  return (
    <div className="pointer-events-none absolute inset-2 flex items-center justify-center rounded-lg border-2 border-dashed border-primary bg-background/90 text-sm font-medium">
      {t('workbench.files.drop_here')}
    </div>
  );
}

/** The message a reply or a forward answers, kept in sight: a phone has nothing behind it. */
function AnsweredMessage({ lng, target }: { lng: Language; target: ComposerTarget }) {
  const { t } = useTranslation(lng);
  if (target.kind !== 'reply' && target.kind !== 'forward') return null;
  return (
    <details open className="rounded-md border bg-muted/30">
      <summary className="cursor-pointer px-3 py-2 text-xs text-muted-foreground">
        {t('workbench.mail.compose.answered')}
      </summary>
      <p className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words px-3 pb-3 text-sm">
        <LinkedText text={target.message.body} />
      </p>
    </details>
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
  senders: readonly MailSender[];
  queryMin: number;
}

/** Where the message leaves from, among the addresses the mailbox holds. */
function SenderField({
  lng,
  senders,
  value,
  onChange,
}: {
  lng: Language;
  senders: readonly MailSender[];
  value: string;
  onChange: (address: string) => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <NativeSelect
      label={t('workbench.mail.compose.from')}
      value={value}
      onChange={event => onChange(event.target.value)}
    >
      {senders.map(sender => (
        <option key={sender.address} value={sender.address}>
          {sender.name ? `${sender.name} <${sender.address}>` : sender.address}
        </option>
      ))}
    </NativeSelect>
  );
}

/** To, and on demand Cc (and Bcc where the target carries it), contacts suggested. */
function RecipientFields({ lng, target, state, senders, queryMin }: RecipientFieldsProps) {
  const { t } = useTranslation(lng);
  const { fields, set, problem } = state;
  // Drawn once its recipients are known: copies already there show from the start.
  const [shown, setShown] = useState(fields.cc !== '');
  const copiesId = useId();
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
      {senders.length > 1 && (
        <SenderField
          lng={lng}
          senders={senders}
          value={senderShown(fields, target, senders)}
          onChange={sendAs => set({ sendAs })}
        />
      )}
      {field('to', 'workbench.mail.compose.to')}
      {/* Its word starts where the labels above it do: the padding hangs out to the left. */}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="-ml-3"
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
  /** A file is on its way: nothing leaves without it. */
  uploading: boolean;
  offersDrafts: boolean;
  onCancel: () => void;
}

/** Cancel, keep as a draft (where the provider keeps drafts), send — held while busy. */
function ComposerFooter({ lng, state, uploading, offersDrafts, onCancel }: ComposerFooterProps) {
  const { t } = useTranslation(lng);
  const { status } = state;
  const settled = status === 'unknown';
  return (
    <ToolActions className="max-sm:mt-auto">
      <CancelButton lng={lng} onClick={onCancel} />
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
      <Button
        type="submit"
        isLoading={status === 'sending'}
        aria-disabled={settled || status === 'saving' || uploading || undefined}
        className="gap-1.5"
      >
        <Send className="h-4 w-4" aria-hidden="true" />
        {t('workbench.mail.compose.send')}
      </Button>
      <AutosaveLine lng={lng} state={state} />
    </ToolActions>
  );
}

/** Above the buttons on a phone, where the column ends on the last one; before them beyond. */
const AUTOSAVE_LINE = 'text-xs sm:order-first sm:mr-auto';

/** What the composer's last save by itself came to, while it still holds. */
function AutosaveLine({ lng, state }: { lng: Language; state: ComposerState }) {
  const { t } = useTranslation(lng);
  const { autosave, dirty } = state;
  if (autosave === 'failed') {
    return (
      <span role="status" className={cn(AUTOSAVE_LINE, 'text-destructive')}>
        {t('workbench.mail.compose.autosave_failed')}
      </span>
    );
  }
  if (autosave !== 'saved' || dirty) return null;
  return (
    <span role="status" className={cn(AUTOSAVE_LINE, 'text-muted-foreground')}>
      {t('workbench.mail.compose.autosaved')}
    </span>
  );
}

function titleOf(target: ComposerTarget): string {
  if (target.kind === 'reply') return target.all ? 'reply_all' : 'reply';
  return target.kind;
}

/** Whom a reply goes to, what a forward carries, or what a new message is (a key and its values). */
function contextOf(
  target: ComposerTarget,
  answered: boolean
): {
  key: string;
  values?: Record<string, string | number>;
} {
  if (target.kind === 'reply') {
    const { message } = target;
    if (answered) {
      return { key: 'workbench.mail.compose.reply_about', values: { subject: message.subject } };
    }
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
  return { key: 'workbench.mail.compose.new_line' };
}

/** A file on the message, and the way to take it off. */
function FileChip({
  lng,
  filename,
  size,
  onRemove,
}: {
  lng: Language;
  filename: string;
  size: number | null;
  onRemove: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <li className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card py-1 pl-3 pr-1 text-sm">
      <span className="truncate">{filename}</span>
      <span className="shrink-0 text-xs text-muted-foreground">
        {size ? fileSize(size, lng) : null}
      </span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        onClick={onRemove}
        aria-label={t('workbench.mail.files.remove', { name: filename })}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
    </li>
  );
}

function FilesField({
  lng,
  files,
  held,
  onRemove,
  onDropHeld,
  onPick,
  onDevice,
}: {
  lng: Language;
  files: readonly { id: string; filename: string; size: number }[];
  /** What a draft carries already. */
  held: readonly MailAttachment[];
  onRemove: (id: string) => void;
  onDropHeld: (name: string) => void;
  onPick: () => void;
  onDevice: (files: File[]) => void;
}) {
  const { t } = useTranslation(lng);
  const chooser = useRef<HTMLInputElement>(null);
  const chosen = (event: ChangeEvent<HTMLInputElement>) => {
    onDevice([...(event.target.files ?? [])]);
    // The same file chosen again is a new choice.
    event.target.value = '';
  };
  return (
    <div className="space-y-2">
      {files.length + held.length > 0 && (
        <ul aria-label={t('workbench.mail.files.chosen')} className="flex flex-wrap gap-2">
          {held.map((file, index) => (
            <FileChip
              key={`${file.filename}-${index}`}
              lng={lng}
              filename={file.filename}
              size={file.size}
              onRemove={() => onDropHeld(file.filename)}
            />
          ))}
          {files.map(file => (
            <FileChip
              key={file.id}
              lng={lng}
              filename={file.filename}
              size={file.size}
              onRemove={() => onRemove(file.id)}
            />
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn('gap-1.5', WHOLE_ON_A_PHONE)}
          onClick={onPick}
        >
          <Paperclip className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.files.add')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn('gap-1.5', WHOLE_ON_A_PHONE)}
          onClick={() => chooser.current?.click()}
        >
          <Upload className="h-4 w-4" aria-hidden="true" />
          {t('workbench.mail.files.from_device')}
        </Button>
        <input
          ref={chooser}
          type="file"
          multiple
          hidden
          aria-label={t('workbench.mail.files.from_device')}
          onChange={chosen}
        />
      </div>
    </div>
  );
}
