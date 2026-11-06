/**
 * What a composer does with a send that did not answer « sent » (ADR-369,
 * ADR-221, Review focus 3): pure.
 *
 * The server claims the submission's key before the provider is called. A
 * lost answer (`outcome_unknown`), or a second press while the first is still
 * on its way or lost (`already_submitted`, outcome `pending` or `unknown`), is
 * an outcome NOBODY knows: the page never presses again by itself, keeps what
 * was written and tells the person to look in Sent. A first submission
 * already done is a message sent. A recipient that cannot be read is said
 * under its own field, at its place. Anything else is a refusal the person may
 * fix and send again — the server freed the key.
 */
import { getApiErrorFields } from '@/lib/api-error';
import { parseRecipients } from '@/lib/email-share/share';

import { workbenchRefusal, type WorkbenchRefusal } from './errors';
import type {
  AttachableFile,
  MailAddress,
  MailAttachment,
  MailDraft,
  MailSender,
  MailMessage,
  MailReplyRecipients,
} from './types';

/** A recipient field of the composer, as the server names it. */
export type RecipientField = 'to' | 'cc' | 'bcc';

export type ComposeFailure =
  | { kind: 'unknown' }
  | { kind: 'already_sent' }
  | { kind: 'recipient'; field: RecipientField; refusal: WorkbenchRefusal }
  | { kind: 'refused'; refusal: WorkbenchRefusal | null };

const FIELDS: readonly RecipientField[] = ['to', 'cc', 'bcc'];
const UNSETTLED: ReadonlySet<string> = new Set([
  'workbench.errors.outcome_unknown',
  'workbench.errors.already_submitted_unknown',
  'workbench.errors.already_submitted_pending',
]);

/** @param error - What a send, a reply, a forward or a draft's send rejected with. */
export function composeFailure(error: unknown): ComposeFailure {
  const refusal = workbenchRefusal(error);
  if (refusal && UNSETTLED.has(refusal.key)) return { kind: 'unknown' };
  if (refusal?.key === 'workbench.errors.already_submitted_done') return { kind: 'already_sent' };
  const field = FIELDS.find(name => name === getApiErrorFields(error)?.field);
  if (refusal?.key.startsWith('workbench.errors.invalid_recipient') && field) {
    return { kind: 'recipient', field, refusal };
  }
  return { kind: 'refused', refusal };
}

/** A recipient field as the addresses typed, each once (commas, semicolons or spaces). */
export function recipientsOf(text: string): string[] {
  return parseRecipients(text);
}

/** What a composer was opened on. */
export type ComposerTarget =
  /** What the message opens on: an address another tool handed over, a list's request. */
  | { kind: 'new'; to?: string; subject?: string; body?: string; files?: AttachableFile[] }
  | { kind: 'reply'; message: MailMessage; all: boolean }
  | { kind: 'forward'; message: MailMessage }
  | { kind: 'draft'; draft: MailDraft };

/** What the person writes: recipient fields as typed, the files chosen and those taken off. */
export interface ComposerFields {
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body: string;
  files: AttachableFile[];
  /** The names of files a draft holds that it no longer carries, one file for each. */
  removedFiles: string[];
  /** The alias the person chose; empty: what the mailbox or the draft already says. */
  sendAs: string;
  /** The words with their formatting; null: `body` is all there is. */
  html: string | null;
}

/** Which parts a target writes (an answer's subject is its message's). */
export interface ComposerWrites {
  recipients: boolean;
  bcc: boolean;
  subject: boolean;
  /** The person's own files. */
  files: boolean;
}

/** What a file handed from the drive declares: it is read there when the message leaves. */
export const DRIVE_ORIGIN = 'drive';

/** The files a message carries, as the send names them. */
export function filesToSend(files: readonly AttachableFile[]): {
  attachment_ids: string[];
  drive_file_ids: string[];
} {
  const idsOf = (drive: boolean) =>
    files.filter(file => (file.origin === DRIVE_ORIGIN) === drive).map(file => file.id);
  return { attachment_ids: idsOf(false), drive_file_ids: idsOf(true) };
}

/** What a message may carry, as the send refuses beyond it. */
export interface FileBounds {
  maxFiles: number;
  maxBytes: number;
  /** What one file of the device may weigh. */
  eachMaxBytes: number;
}

/** The file a bound left out, and which bound. */
export interface FileOver {
  kind: 'count' | 'bytes' | 'each';
  name: string;
}

function boundMet(
  file: File,
  count: number,
  bytes: number,
  bounds: FileBounds
): FileOver['kind'] | null {
  if (file.size > bounds.eachMaxBytes) return 'each';
  if (count >= bounds.maxFiles) return 'count';
  return bytes + file.size > bounds.maxBytes ? 'bytes' : null;
}

/**
 * @param files - What the person brought from the device.
 * @param chosen - What the message already carries.
 * @param bounds - The published bounds.
 * @returns What still fits, in its order, and the first file left out: none goes unsaid.
 */
export function fittingFiles(
  files: readonly File[],
  chosen: readonly { size: number }[],
  bounds: FileBounds
): { fitting: File[]; over: FileOver | null } {
  const fitting: File[] = [];
  let bytes = chosen.reduce((sum, file) => sum + file.size, 0);
  let over: FileOver | null = null;
  for (const file of files) {
    const kind = boundMet(file, chosen.length + fitting.length, bytes, bounds);
    if (kind) {
      over ??= { kind, name: file.name };
    } else {
      fitting.push(file);
      bytes += file.size;
    }
  }
  return { fitting, over };
}

function typed(addresses: readonly MailAddress[]): string {
  return addresses.map(address => address.address).join(', ');
}

/** Who a reply reaches, as the fields hold it. */
export function reachFields(reach: MailReplyRecipients): Pick<ComposerFields, 'to' | 'cc'> {
  return { to: typed(reach.to), cc: typed(reach.cc) };
}

/**
 * @param target - What the composer was opened on.
 * @param signature - What a body gains to carry the person's signature; a draft has its own.
 * @returns What the composer opens on.
 */
export function initialFields(target: ComposerTarget, signature = ''): ComposerFields {
  if (target.kind === 'new') {
    const { to = '', subject = '', body = '', files = [] } = target;
    return {
      to,
      cc: '',
      bcc: '',
      subject,
      body: body + signature,
      files,
      removedFiles: [],
      sendAs: '',
      html: null,
    };
  }
  if (target.kind !== 'draft') {
    return {
      to: '',
      cc: '',
      bcc: '',
      subject: '',
      body: signature,
      files: [],
      removedFiles: [],
      sendAs: '',
      html: null,
    };
  }
  const { draft } = target;
  return {
    to: typed(draft.to),
    cc: typed(draft.cc),
    bcc: typed(draft.bcc),
    subject: draft.subject,
    body: draft.body,
    files: [],
    removedFiles: [],
    sendAs: '',
    html: null,
  };
}

/** Plain words as the editor opens on them: their marks are words, their lines kept. */
export function textToHtml(text: string): string {
  const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped.replace(/\n/g, '<br>');
}

const OWN_SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const FOLLOWABLE = /^(https?|mailto):/i;

/**
 * @param typed - A link's address as people type it.
 * @returns The address, a scheme added where none was typed; null when nobody should follow it.
 */
export function linkOf(typed: string): string | null {
  const address = typed.trim();
  if (!address) return null;
  if (OWN_SCHEME.test(address)) return FOLLOWABLE.test(address) ? address : null;
  return address.includes('@') ? `mailto:${address}` : `https://${address}`;
}

/**
 * @param fields - What is written.
 * @param target - What the composer was opened on.
 * @param senders - The addresses the mailbox sends from.
 * @returns The address shown as where the message leaves from.
 */
export function senderShown(
  fields: ComposerFields,
  target: ComposerTarget,
  senders: readonly MailSender[]
): string {
  if (fields.sendAs) return fields.sendAs;
  const saved = target.kind === 'draft' ? target.draft.sender?.address : undefined;
  return saved ?? senders.find(sender => sender.is_default)?.address ?? '';
}

/** Anything worth keeping as a draft: an empty message is none. */
export function holdsWords(fields: ComposerFields): boolean {
  const { to, cc, bcc, subject, body, files } = fields;
  return files.length > 0 || [to, cc, bcc, subject, body].some(text => text.trim() !== '');
}

/**
 * @param held - The files a draft holds.
 * @param removed - The names taken off it, not saved yet.
 * @returns What it still carries: each name takes one file, the first bearing it.
 */
export function keptFiles(
  held: readonly MailAttachment[],
  removed: readonly string[]
): MailAttachment[] {
  const left = [...held];
  for (const name of removed) {
    const index = left.findIndex(file => file.filename === name);
    if (index >= 0) left.splice(index, 1);
  }
  return left;
}

/**
 * @param target - What the composer was opened on.
 * @param reachRead - Who a reply reaches is known: only then can the person change it.
 * @returns What the composer writes for it.
 */
export function writes(target: ComposerTarget, reachRead = false): ComposerWrites {
  switch (target.kind) {
    case 'new':
      return { recipients: true, bcc: true, subject: true, files: true };
    case 'draft':
      return { recipients: true, bcc: true, subject: true, files: true };
    case 'forward':
      return { recipients: true, bcc: false, subject: false, files: true };
    case 'reply':
      return { recipients: reachRead, bcc: false, subject: false, files: true };
  }
}

/**
 * A list's `mailto:` is a stranger's words: its address, subject and body are what a
 * person reads before sending, and any copy it asks for is left out.
 *
 * @param mailTo - What follows `mailto:`.
 * @returns What the message opens on.
 */
export function parseMailTo(mailTo: string): { to: string; subject: string; body: string } {
  const [to, query = ''] = mailTo.split('?', 2);
  const params = new URLSearchParams(query);
  return { to, subject: params.get('subject') ?? '', body: params.get('body') ?? '' };
}

/** A problem the page sees before sending, said under its field. */
export interface LocalProblem {
  field: RecipientField;
  key: string;
  values?: Record<string, number>;
}

/**
 * @param fields - What is written.
 * @param target - What the composer was opened on.
 * @param recipientsMax - The published bound on one recipient field.
 * @param reachRead - Who a reply reaches is known, and the person's to change.
 * @returns Nobody to write to, or a field past the bound; null when it may leave.
 */
export function localProblem(
  fields: ComposerFields,
  target: ComposerTarget,
  recipientsMax: number,
  reachRead = false
): LocalProblem | null {
  const parts = writes(target, reachRead);
  if (!parts.recipients) return null;
  const named: [RecipientField, string][] = [
    ['to', fields.to],
    ['cc', fields.cc],
    ['bcc', parts.bcc ? fields.bcc : ''],
  ];
  const counts = named.map(([field, text]) => [field, recipientsOf(text).length] as const);
  // An answer goes to someone in To (the server's rule); a message, to anyone in any field.
  const reached = parts.bcc ? counts : counts.slice(0, 1);
  if (reached.every(([, count]) => count === 0)) {
    return { field: 'to', key: 'workbench.mail.compose.no_recipient' };
  }
  const over = counts.find(([, count]) => count > recipientsMax);
  return over
    ? { field: over[0], key: 'workbench.mail.compose.too_many', values: { count: recipientsMax } }
    : null;
}
