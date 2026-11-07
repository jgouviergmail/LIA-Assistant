/**
 * The contact editor's model (ADR-369, D4).
 *
 * A contact's e-mails, phones and addresses are typed lists, and the write
 * contract is the read one: a list sent REPLACES that list, a list left out is
 * KEPT. So a change sends only the lists it changed — adding, removing or
 * retyping a value is a change; an untouched list never leaves, since it may
 * hold what LIA does not model (a Google source, a vCard preference). A value
 * left empty is not a value. How many a list may hold is the provider's bound
 * where it publishes one (Graph's slots), else the section's. The rest of a
 * contact goes by the same rule: left out it is kept, an empty text empties it,
 * and a birthday goes by a flag. A birthday with no year is held as `--MM-DD`,
 * shown and removed, never written: a date field cannot say it.
 */
import type { Language } from '@/i18n/settings';
import { apiEndpointUrl } from '@/lib/api-client';

import { MAIL_INBOX, MAIL_SENT, receivedLabel } from './mail';
import { hitHref } from './search';
import type {
  ContactAddress,
  ContactHistoryMeeting,
  ContactValue,
  SearchHit,
  WorkbenchContact,
  WorkbenchContactSummary,
} from './types';
import type { ProposedContact, ProposedValue } from './assist';

/** A line of a contact's history, as its tool's address reads it. */
const HISTORY_HIT: Omit<SearchHit, 'id'> = {
  title: '',
  subtitle: null,
  mail_folder: null,
  calendar_id: null,
  day: null,
  is_folder: false,
};

/** @returns Where a message exchanged with a contact opens. */
export function historyMailHref(id: string, sent: boolean, lng: Language): string {
  const mail_folder = sent ? MAIL_SENT : MAIL_INBOX;
  return hitHref('mail', { ...HISTORY_HIT, id, mail_folder }, lng);
}

/** @returns Where a meeting with a contact opens: on its day, in its calendar. */
export function historyMeetingHref(meeting: ContactHistoryMeeting, lng: Language): string {
  const { id, day, calendar_id } = meeting;
  return hitHref('calendar', { ...HISTORY_HIT, id, day, calendar_id }, lng);
}

/**
 * @returns When a line of a contact's history happened, told as the mail list tells it: a whole
 *   day keeps its own, in no zone.
 */
export function historyDay(
  row: { at: string | null; day?: string | null; all_day?: boolean },
  now: Date,
  zone: string | undefined,
  lng: Language
): string | null {
  const whole = row.all_day === true && Boolean(row.day);
  return whole
    ? receivedLabel(`${row.day}T00:00:00Z`, now, 'UTC', lng)
    : receivedLabel(row.at, now, zone, lng);
}

/** What the person writes. */
export interface ContactFields {
  name: string;
  given_name: string;
  family_name: string;
  organization: string;
  job_title: string;
  website: string;
  /** An ISO day, `--MM-DD` for one with no year, empty for none. */
  birthday: string;
  notes: string;
  emails: ContactValue[];
  phones: ContactValue[];
  addresses: ContactAddress[];
}

/** A contact to create (`schemas/contacts.NewContact`). */
export interface NewContactBody {
  name: string;
  emails: ContactValue[];
  phones: ContactValue[];
  addresses: ContactAddress[];
  given_name?: string;
  family_name?: string;
  organization?: string;
  job_title?: string;
  website?: string;
  birthday?: string;
  notes?: string;
  idempotency_key: string;
}

/** What changes on a contact (`schemas/contacts.ContactChange`): a list sent replaces it. */
export interface ContactChangeBody {
  id: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  organization?: string;
  job_title?: string;
  website?: string;
  birthday?: string;
  clear_birthday?: boolean;
  notes?: string;
  emails?: ContactValue[];
  phones?: ContactValue[];
  addresses?: ContactAddress[];
}

export type ContactList = 'emails' | 'phones' | 'addresses';

/** The kinds the editor offers per list (the providers' common words). */
/**
 * A contact as the list and its detail name it (owner request 2026-10-31): « Given Family »
 * when the provider holds both parts, else the name the provider shows — a company, a
 * single name, or a name whose parts nobody filled.
 *
 * @param contact - Its name and its parts.
 * @returns The name to draw (empty when the provider holds none).
 */
export function contactName(
  contact: Pick<WorkbenchContactSummary, 'name' | 'given_name' | 'family_name'>
): string {
  const given = contact.given_name?.trim() ?? '';
  const family = contact.family_name?.trim() ?? '';
  return given && family ? `${given} ${family}` : contact.name;
}

type Named = Pick<WorkbenchContactSummary, 'name' | 'given_name' | 'family_name'>;

/**
 * @param contact - Its name and its parts.
 * @returns The initials it is known by, one or two (none for a contact with no name).
 */
export function contactInitials(contact: Named): string {
  const given = contact.given_name?.trim();
  const family = contact.family_name?.trim();
  const words = given && family ? [given, family] : contact.name.trim().split(/\s+/);
  return words
    .filter(Boolean)
    .slice(0, 2)
    .map(word => [...word][0].toUpperCase())
    .join('');
}

/** The letter a contact is filed under: its family name's, accents folded. */
function fileLetter(contact: Named): string {
  const source = contact.family_name?.trim() || contact.name.trim();
  const first = [...source][0] ?? '';
  return first.normalize('NFD').replace(/\p{M}/gu, '').toUpperCase();
}

/**
 * The letters heading an alphabetical list: on the first contact of each. Providers
 * do not all sort alike, so a list that is not in that order gets none, since a
 * letter would then say what is not so.
 *
 * @param contacts - A listing, in the provider's order.
 * @param language - The reader's (how letters compare).
 * @returns Each heading, by the id of the contact it stands above.
 */
export function contactLetters(
  contacts: readonly (Named & { id: string })[],
  language: string
): Map<string, string> {
  const collator = new Intl.Collator(language, { sensitivity: 'base' });
  const heads = new Map<string, string>();
  let last = '';
  for (const contact of contacts) {
    const letter = fileLetter(contact);
    if (!letter) continue;
    if (last && collator.compare(letter, last) < 0) return new Map();
    if (letter !== last) heads.set(contact.id, letter);
    last = letter;
  }
  return heads;
}

/**
 * @param address - An address, as a person wrote it.
 * @returns It on a map, a link every device opens.
 */
export function mapHref(address: string): string {
  const query = address.replace(/\s*\n\s*/g, ', ');
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

/**
 * @param id - One contact; the whole book when left out.
 * @returns Its download, through the API's own origin. A cut is said in the file's name.
 */
export function contactsExportUrl(id?: string): string {
  const query = id ? `?${new URLSearchParams({ id })}` : '';
  return apiEndpointUrl(`/workbench/contacts/export${query}`);
}

/** What names a contact Google lists and searches, and never reads, changes or deletes. */
const OTHER_CONTACT_PREFIX = 'otherContacts/';

/**
 * @param id - A contact.
 * @returns Whether it is one met in mail and never saved.
 */
export function isOtherContact(id: string): boolean {
  return id.startsWith(OTHER_CONTACT_PREFIX);
}

/**
 * @param summary - A row of a listing.
 * @returns It as a contact: what the search said is all there is to show.
 */
export function contactOfSummary(summary: WorkbenchContactSummary): WorkbenchContact {
  return {
    ...summary,
    emails: summary.email ? [{ value: summary.email, type: null }] : [],
    phones: summary.phone ? [{ value: summary.phone, type: null }] : [],
    addresses: [],
    notes: null,
    job_title: null,
    website: null,
    birthday: null,
  };
}

export const CONTACT_KINDS: Readonly<Record<ContactList, readonly string[]>> = {
  emails: ['home', 'work', 'other'],
  phones: ['mobile', 'home', 'work', 'other'],
  addresses: ['home', 'work', 'other'],
};

/**
 * @param fields - The card as it stands.
 * @param values - What the person kept of what their messages say.
 * @returns The card with them: a phone joins the others, anything else fills its blank.
 */
export function withFoundValues(
  fields: ContactFields,
  values: readonly ProposedValue[]
): ContactFields {
  const said = (field: string) => values.find(found => found.field === field)?.value;
  const address = said('address');
  return {
    ...fields,
    organization: fields.organization || said('organization') || '',
    job_title: fields.job_title || said('job_title') || '',
    website: fields.website || said('website') || '',
    phones: [
      ...fields.phones,
      ...values
        .filter(found => found.field === 'phone')
        .map(found => ({ value: found.value, type: 'work' })),
    ],
    addresses:
      fields.addresses.length === 0 && address
        ? [{ formatted: address, type: 'work' }]
        : fields.addresses,
  };
}

/** @returns A list with the values it does not hold yet: reading a card twice adds nothing twice. */
function withNewValues(list: readonly ContactValue[], values: readonly string[]): ContactValue[] {
  const held = new Set(list.map(entry => entry.value.trim().toLowerCase()));
  const fresh = values.filter(value => !held.has(value.trim().toLowerCase()));
  return [...list, ...fresh.map(value => ({ value, type: 'work' }))];
}

/**
 * @param fields - The form as the person left it.
 * @param card - A business card read.
 * @returns The form with it: what they typed stays, a value joins a list.
 */
export function withCard(fields: ContactFields, card: ProposedContact): ContactFields {
  const named = [card.given_name, card.family_name].filter(Boolean).join(' ');
  return {
    ...fields,
    given_name: fields.given_name || card.given_name,
    family_name: fields.family_name || card.family_name,
    name: fields.name || named || card.organization,
    organization: fields.organization || card.organization,
    job_title: fields.job_title || card.job_title,
    website: fields.website || card.website,
    emails: withNewValues(fields.emails, card.emails),
    phones: withNewValues(fields.phones, card.phones),
    addresses: card.address
      ? [...fields.addresses, { formatted: card.address, type: 'work' }]
      : fields.addresses,
  };
}

export const EMPTY_CONTACT: ContactFields = {
  name: '',
  given_name: '',
  family_name: '',
  organization: '',
  job_title: '',
  website: '',
  birthday: '',
  notes: '',
  emails: [],
  phones: [],
  addresses: [],
};

/** @returns The fields a contact opens on. */
export function fieldsOfContact(contact: WorkbenchContact): ContactFields {
  return {
    name: contact.name,
    given_name: contact.given_name ?? '',
    family_name: contact.family_name ?? '',
    organization: contact.organization ?? '',
    job_title: contact.job_title ?? '',
    website: contact.website ?? '',
    birthday: contact.birthday ?? '',
    notes: contact.notes ?? '',
    emails: contact.emails.map(item => ({ ...item })),
    phones: contact.phones.map(item => ({ ...item })),
    addresses: contact.addresses.map(item => ({ ...item })),
  };
}

function cleanValues(values: readonly ContactValue[]): ContactValue[] {
  return values
    .map(item => ({ value: item.value.trim(), type: item.type }))
    .filter(item => item.value);
}

function cleanAddresses(addresses: readonly ContactAddress[]): ContactAddress[] {
  return addresses
    .map(item => ({ formatted: item.formatted.trim(), type: item.type }))
    .filter(item => item.formatted);
}

function same(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

type NameParts = Pick<ContactFields, 'given_name' | 'family_name'>;

function nameOfParts(parts: NameParts): string {
  return [parts.given_name.trim(), parts.family_name.trim()].filter(Boolean).join(' ');
}

/**
 * @param fields - What the person wrote.
 * @returns The name a contact goes by: the one written, else its parts together.
 */
export function displayNameOf(fields: NameParts & Pick<ContactFields, 'name'>): string {
  return fields.name.trim() || nameOfParts(fields);
}

/**
 * @param birthday - A birthday as it is held.
 * @returns It as a date field holds it: a birthday with no year has no such form.
 */
export function fullBirthday(birthday: string): string {
  return birthday.startsWith('--') ? '' : birthday;
}

/**
 * A birthday in the reader's words, on UTC so no timezone moves the day. One with no year is
 * read in a leap year, or the 29th of February would not exist.
 *
 * @param birthday - An ISO day, or `--MM-DD`.
 * @param language - The reader's.
 * @returns It written out.
 */
export function birthdayLabel(birthday: string, language: string): string {
  const noYear = birthday.startsWith('--');
  const day = new Date(`${noYear ? `2000-${birthday.slice(2)}` : birthday}T00:00:00Z`);
  return new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'long',
    ...(noYear ? {} : { year: 'numeric' }),
    timeZone: 'UTC',
  }).format(day);
}

/**
 * The whole name follows its parts when it was theirs, and stands when both are emptied: Google
 * derives its name from the parts, so a contact would otherwise be left with none.
 */
function nameBesideParts(initial: ContactFields, fields: ContactFields): string | undefined {
  const named = nameOfParts(fields);
  if (!named) return fields.name.trim();
  return initial.name.trim() === nameOfParts(initial) ? named : undefined;
}

/** @returns What changed from `initial`, or null when nothing did. */
export function contactChange(
  id: string,
  initial: ContactFields,
  fields: ContactFields
): ContactChangeBody | null {
  const change: ContactChangeBody = { id };
  const texts = [
    'name',
    'given_name',
    'family_name',
    'organization',
    'job_title',
    'website',
    'notes',
  ] as const;
  for (const key of texts) {
    const now = fields[key].trim();
    if (now !== initial[key].trim()) change[key] = now;
  }
  if (change.name === '') change.name = nameOfParts(fields);
  const partsChanged = change.given_name !== undefined || change.family_name !== undefined;
  if (partsChanged && change.name === undefined) {
    const name = nameBesideParts(initial, fields);
    if (name !== undefined) change.name = name;
  }
  if (fields.birthday !== initial.birthday) {
    if (fields.birthday) change.birthday = fields.birthday;
    else change.clear_birthday = true;
  }
  const emails = cleanValues(fields.emails);
  if (!same(emails, cleanValues(initial.emails))) change.emails = emails;
  const phones = cleanValues(fields.phones);
  if (!same(phones, cleanValues(initial.phones))) change.phones = phones;
  const addresses = cleanAddresses(fields.addresses);
  if (!same(addresses, cleanAddresses(initial.addresses))) change.addresses = addresses;
  return Object.keys(change).length === 1 ? null : change;
}

/** @returns The new contact's body: every list cleaned, and the submission's key. */
export function newContactBody(fields: ContactFields, idempotencyKey: string): NewContactBody {
  const organization = fields.organization.trim();
  const notes = fields.notes.trim();
  const texts = ['given_name', 'family_name', 'job_title', 'website'] as const;
  const details = Object.fromEntries(
    texts.map(key => [key, fields[key].trim()]).filter(([, value]) => value)
  );
  return {
    name: displayNameOf(fields),
    ...details,
    ...(fields.birthday ? { birthday: fields.birthday } : {}),
    emails: cleanValues(fields.emails),
    phones: cleanValues(fields.phones),
    addresses: cleanAddresses(fields.addresses),
    ...(organization ? { organization } : {}),
    ...(notes ? { notes } : {}),
    idempotency_key: idempotencyKey,
  };
}

/** @returns How many values a list may hold: the provider's bound, else the section's. */
export function valuesMax(bounds: Readonly<Record<string, number>>, list: ContactList): number {
  const own = list === 'emails' ? bounds.emails_max : undefined;
  return own ?? bounds.values_max;
}
