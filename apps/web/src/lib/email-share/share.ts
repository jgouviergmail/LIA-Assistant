/**
 * Sending a generated file or an answer by e-mail (ADR-321) — the pure half.
 *
 * The chat's answers and file cards, the gallery and the bookmarks all offer
 * the action; what they need to know lives here once: whether the instance
 * offers it, how the typed recipients are read, what a file weighs (the way
 * the server counts it), the request the API reads, and which sentence each
 * refusal becomes.
 */

import type { TFunction } from 'i18next';

import type { AppConfig } from '@/hooks/useAppConfig';

/**
 * « Settings › Connectors », the place a mailbox is connected — built from the
 * real translations, never typed (a typed name drifts from the menu it names).
 *
 * @param t - The translator.
 * @returns The path as the person reads it in their language.
 */
export function connectorsSettingsPath(t: TFunction): string {
  return `${t('settings.title')} › ${t('settings.connectors.title')}`;
}

/** Where a send leaves from: the person's mailbox, or LIA's relay to their own address. */
export type EmailShareRoute = 'mailbox' | 'relay' | 'unavailable';

/** What `GET /email-share/options` publishes — every bound the send will meet. */
export interface EmailShareOptions {
  route: EmailShareRoute;
  /** The relay's one recipient: the account's verified address. */
  own_address: string | null;
  /** A mailbox is connected but broken. */
  mailbox_needs_reconnect: boolean;
  /** The largest file this road carries, derived from its provider. */
  max_file_bytes: number | null;
  max_recipients: number;
  subject_max_chars: number;
  message_max_chars: number;
}

/** What `POST /email-share` answers. */
export interface EmailShareResult {
  route: 'mailbox' | 'relay';
  recipients: number;
}

/** What is sent: one of the person's generated files, or an answer as its `.md` file. */
export type EmailShareSource =
  | { kind: 'file'; attachmentId: string; name: string; sizeBytes?: number }
  | { kind: 'markdown'; filename: string; text: string };

/** The part of the app configuration the availability reads. */
export interface EmailShareConfig {
  features?: { email_share_enabled?: boolean };
  capabilities?: AppConfig['capabilities'];
}

/**
 * Whether sending by e-mail is offered on this instance — the EFFECTIVE state.
 *
 * The capability map carries the operator's switch as well as the deployment
 * ceiling; an older API that omits it falls back to the ceiling alone.
 *
 * @param config - The app configuration, or null while it loads.
 * @returns True when a send could leave.
 */
export function emailShareAvailable(config: EmailShareConfig | null): boolean {
  const capability = config?.capabilities?.email_share;
  return capability ? capability.enabled : Boolean(config?.features?.email_share_enabled);
}

/**
 * The addresses a typed field names, each once (compared without case).
 *
 * @param raw - What the person typed: commas, semicolons or spaces between.
 * @returns The addresses in the order typed.
 */
export function parseRecipients(raw: string): string[] {
  const seen = new Set<string>();
  const addresses: string[] = [];
  for (const candidate of raw.split(/[\s,;]+/)) {
    const address = candidate.trim();
    const key = address.toLowerCase();
    if (address && !seen.has(key)) {
      seen.add(key);
      addresses.push(address);
    }
  }
  return addresses;
}

/** One `@`, something before it, and a domain with a dot — the server holds the real rule. */
const ADDRESS = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * The entries that are not an address — named, so the field can say which.
 *
 * @param addresses - The parsed recipients.
 * @returns The offending entries, in order.
 */
export function invalidRecipients(addresses: readonly string[]): string[] {
  return addresses.filter(address => !ADDRESS.test(address));
}

/**
 * What the file weighs, in the bytes the server compares with the road's ceiling.
 *
 * @param source - The file or the answer.
 * @returns The size, or null when the card that offered the file did not know it.
 */
export function sourceSize(source: EmailShareSource): number | null {
  if (source.kind === 'markdown') return new TextEncoder().encode(source.text).length;
  return source.sizeBytes ?? null;
}

/**
 * The name the recipient will see.
 *
 * @param source - The file or the answer.
 * @returns The file name.
 */
export function sourceName(source: EmailShareSource): string {
  return source.kind === 'markdown' ? `${source.filename}.md` : source.name;
}

/**
 * The request `POST /email-share` reads.
 *
 * @param source - What is sent.
 * @param recipients - Whom it reaches (empty on the relay road).
 * @param subject - The subject as typed.
 * @param message - The words as typed; blank means none.
 * @returns The request body.
 */
export function requestBody(
  source: EmailShareSource,
  recipients: string[],
  subject: string,
  message: string
) {
  return {
    recipients,
    subject: subject.trim(),
    message: message.trim() || null,
    attachment:
      source.kind === 'file'
        ? { kind: 'file' as const, attachment_id: source.attachmentId }
        : { kind: 'markdown' as const, filename: source.filename, text: source.text },
  };
}

/** What the form may send, and what it must say before it can. */
export interface ShareCheck {
  /** The recipients the request carries (none on the relay road). */
  recipients: string[];
  /** Entries of the field that are not an address. */
  invalid: string[];
  /** More recipients than the published cap. */
  tooMany: boolean;
  /** A file heavier than the road's published ceiling (when its size is known). */
  tooLarge: boolean;
  /** Everything the API will check first is met. */
  ready: boolean;
}

/**
 * Check the form against the options the API published.
 *
 * @param options - The road and its bounds.
 * @param source - What is sent.
 * @param rawRecipients - The recipients field as typed.
 * @param subject - The subject as typed.
 * @returns What the request carries and what stops it.
 */
export function checkShare(
  options: EmailShareOptions,
  source: EmailShareSource,
  rawRecipients: string,
  subject: string
): ShareCheck {
  const recipients = options.route === 'mailbox' ? parseRecipients(rawRecipients) : [];
  const invalid = invalidRecipients(recipients);
  const tooMany = recipients.length > options.max_recipients;
  const size = sourceSize(source);
  const tooLarge =
    size !== null && options.max_file_bytes !== null && size > options.max_file_bytes;
  const recipientsOk =
    options.route === 'relay' || (recipients.length > 0 && invalid.length === 0 && !tooMany);
  return {
    recipients,
    invalid,
    tooMany,
    tooLarge,
    ready: options.route !== 'unavailable' && recipientsOk && !tooLarge && subject.trim() !== '',
  };
}

/** The refusals the API names (`detail.code`), each with its own sentence. */
const TRANSLATED_CODES: ReadonlySet<string> = new Set([
  'email_share_file_gone',
  'email_share_too_large',
  'email_share_no_recipient',
  'email_share_recipients_locked',
  'email_share_unavailable',
  'email_share_mailbox_reconnect',
  'email_share_refused',
  'email_share_failed',
]);

/**
 * The i18n key of a refusal.
 *
 * @param code - The refusal's `detail.code`, when it carries one.
 * @param status - The HTTP status, for the one refusal that carries no code
 *   (the per-account rate limit answers 429 with a sentence).
 * @returns `email_share.errors.<reason>`, or the generic sentence.
 */
export function emailShareErrorKey(code: string | undefined, status?: number): string {
  if (code && TRANSLATED_CODES.has(code)) {
    return `email_share.errors.${code.slice('email_share_'.length)}`;
  }
  if (status === 429) return 'email_share.errors.rate_limited';
  return 'email_share.errors.generic';
}
