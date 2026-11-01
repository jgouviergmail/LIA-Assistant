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
import type { AttachableFile, MailAddress, MailDraft, MailMessage } from './types';

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
  | { kind: 'new' }
  | { kind: 'reply'; message: MailMessage; all: boolean }
  | { kind: 'forward'; message: MailMessage }
  | { kind: 'draft'; draft: MailDraft };

/** What the person writes: recipient fields as typed, and the files chosen. */
export interface ComposerFields {
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  body: string;
  files: AttachableFile[];
}

/** Which parts a target writes (a reply's recipients and subject are its message's). */
export interface ComposerWrites {
  recipients: boolean;
  bcc: boolean;
  subject: boolean;
  /** The person's own files (a new message only: a draft's are kept as they are). */
  files: boolean;
}

function typed(addresses: readonly MailAddress[]): string {
  return addresses.map(address => address.address).join(', ');
}

export function initialFields(target: ComposerTarget): ComposerFields {
  if (target.kind !== 'draft') {
    return { to: '', cc: '', bcc: '', subject: '', body: '', files: [] };
  }
  const { draft } = target;
  return {
    to: typed(draft.to),
    cc: typed(draft.cc),
    bcc: typed(draft.bcc),
    subject: draft.subject,
    body: draft.body,
    files: [],
  };
}

export function writes(target: ComposerTarget): ComposerWrites {
  switch (target.kind) {
    case 'new':
      return { recipients: true, bcc: true, subject: true, files: true };
    case 'draft':
      return { recipients: true, bcc: true, subject: true, files: false };
    case 'forward':
      return { recipients: true, bcc: false, subject: false, files: false };
    case 'reply':
      return { recipients: false, bcc: false, subject: false, files: false };
  }
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
 * @returns Nobody to write to, or a field past the bound; null when it may leave.
 */
export function localProblem(
  fields: ComposerFields,
  target: ComposerTarget,
  recipientsMax: number
): LocalProblem | null {
  const parts = writes(target);
  if (!parts.recipients) return null;
  const named: [RecipientField, string][] = [
    ['to', fields.to],
    ['cc', fields.cc],
    ['bcc', parts.bcc ? fields.bcc : ''],
  ];
  const counts = named.map(([field, text]) => [field, recipientsOf(text).length] as const);
  // A forward goes to someone in To (the server's rule); a message, to anyone in any field.
  const reached = target.kind === 'forward' ? counts.slice(0, 1) : counts;
  if (reached.every(([, count]) => count === 0)) {
    return { field: 'to', key: 'workbench.mail.compose.no_recipient' };
  }
  const over = counts.find(([, count]) => count > recipientsMax);
  return over
    ? { field: over[0], key: 'workbench.mail.compose.too_many', values: { count: recipientsMax } }
    : null;
}
