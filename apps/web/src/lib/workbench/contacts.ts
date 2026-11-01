/**
 * The contact editor's model (ADR-369, D4): pure.
 *
 * A contact's e-mails, phones and addresses are typed lists, and the write
 * contract is the read one: a list sent REPLACES that list, a list left out is
 * KEPT. So a change sends only the lists it changed — adding, removing or
 * retyping a value is a change; an untouched list never leaves, since it may
 * hold what LIA does not model (a Google source, a vCard preference). A value
 * left empty is not a value. How many a list may hold is the provider's bound
 * where it publishes one (Graph's slots), else the section's.
 */
import type {
  ContactAddress,
  ContactValue,
  WorkbenchContact,
  WorkbenchContactSummary,
} from './types';

/** What the person writes. */
export interface ContactFields {
  name: string;
  organization: string;
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
  organization?: string;
  notes?: string;
  idempotency_key: string;
}

/** What changes on a contact (`schemas/contacts.ContactChange`): a list sent replaces it. */
export interface ContactChangeBody {
  id: string;
  name?: string;
  organization?: string;
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

export const CONTACT_KINDS: Readonly<Record<ContactList, readonly string[]>> = {
  emails: ['home', 'work', 'other'],
  phones: ['mobile', 'home', 'work', 'other'],
  addresses: ['home', 'work', 'other'],
};

export const EMPTY_CONTACT: ContactFields = {
  name: '',
  organization: '',
  notes: '',
  emails: [],
  phones: [],
  addresses: [],
};

/** @returns The fields a contact opens on. */
export function fieldsOfContact(contact: WorkbenchContact): ContactFields {
  return {
    name: contact.name,
    organization: contact.organization ?? '',
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

/** @returns What changed from `initial`, or null when nothing did. */
export function contactChange(
  id: string,
  initial: ContactFields,
  fields: ContactFields
): ContactChangeBody | null {
  const change: ContactChangeBody = { id };
  for (const key of ['name', 'organization', 'notes'] as const) {
    const now = fields[key].trim();
    if (now !== initial[key].trim()) change[key] = now;
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
  return {
    name: fields.name.trim(),
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
