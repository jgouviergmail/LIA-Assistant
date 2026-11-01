/**
 * The contact editor's model (ADR-369, Task 7.2, D4).
 *
 * A list sent REPLACES that list and a list left out is KEPT: the editor sends
 * only the lists it changed — adding, removing or retyping a value is a
 * change, an untouched list never leaves (it may hold what LIA does not
 * model). A value left empty is not a value. How many values a list may hold
 * is the provider's published bound.
 */

import { describe, expect, it } from 'vitest';

import type { WorkbenchContact } from '@/lib/workbench/types';

import {
  contactChange,
  contactName,
  fieldsOfContact,
  newContactBody,
  valuesMax,
} from '../contacts';

const KEY = '11111111-1111-4111-8111-111111111111';

const ANA: WorkbenchContact = {
  id: 'people/c1',
  name: 'Ana Lima',
  given_name: 'Ana',
  family_name: 'Lima',
  email: 'ana@example.org',
  phone: '+33 6 12',
  organization: 'Atlas',
  name_key: 'ana lima',
  emails: [
    { value: 'ana@example.org', type: 'work' },
    { value: 'ana@home.example', type: 'home' },
  ],
  phones: [{ value: '+33 6 12', type: 'mobile' }],
  addresses: [{ formatted: '1 rue de la Paix, Paris', type: 'home' }],
  notes: 'Met at the fair.',
};

describe('contactChange', () => {
  const initial = fieldsOfContact(ANA);

  it('sends nothing when nothing changed', () => {
    expect(contactChange(ANA.id, initial, { ...initial })).toBeNull();
  });

  it('sends only the list it changed — a value added', () => {
    const phones = [...initial.phones, { value: '+33 1 00', type: 'work' }];

    expect(contactChange(ANA.id, initial, { ...initial, phones })).toEqual({ id: ANA.id, phones });
  });

  it('counts a value removed or retyped as a change of its list', () => {
    expect(contactChange(ANA.id, initial, { ...initial, emails: initial.emails.slice(1) })).toEqual(
      {
        id: ANA.id,
        emails: [{ value: 'ana@home.example', type: 'home' }],
      }
    );
    const retyped = [{ formatted: '1 rue de la Paix, Paris', type: 'work' }];
    expect(contactChange(ANA.id, initial, { ...initial, addresses: retyped })).toEqual({
      id: ANA.id,
      addresses: retyped,
    });
  });

  it('drops a value left empty, and a list emptied to nothing is an emptied list', () => {
    const emails = [{ value: '  ', type: 'work' }];

    expect(contactChange(ANA.id, initial, { ...initial, emails })).toEqual({
      id: ANA.id,
      emails: [],
    });
  });

  it('sends a changed name, organization or notes, trimmed', () => {
    expect(contactChange(ANA.id, initial, { ...initial, name: ' Ana Lima-Costa ' })).toEqual({
      id: ANA.id,
      name: 'Ana Lima-Costa',
    });
  });
});

describe('newContactBody', () => {
  it('carries every list, its empty values dropped, and the submission’s key', () => {
    const fields = {
      ...fieldsOfContact({ ...ANA, notes: null, organization: null }),
      phones: [{ value: '', type: 'mobile' }],
    };

    expect(newContactBody(fields, KEY)).toEqual({
      name: 'Ana Lima',
      emails: ANA.emails,
      phones: [],
      addresses: ANA.addresses,
      idempotency_key: KEY,
    });
  });
});

describe('valuesMax', () => {
  it('reads the provider’s own bound before the section’s', () => {
    expect(valuesMax({ values_max: 20, emails_max: 3 }, 'emails')).toBe(3);
    expect(valuesMax({ values_max: 20 }, 'emails')).toBe(20);
    expect(valuesMax({ values_max: 20, emails_max: 3 }, 'phones')).toBe(20);
  });
});

/** Owner request (2026-10-31): a contact reads « Given Family », whatever its provider shows. */
describe('contactName', () => {
  it('reads « Given Family » when the provider holds both parts', () => {
    expect(contactName({ name: 'Lima, Ana', given_name: 'Ana', family_name: 'Lima' })).toBe(
      'Ana Lima'
    );
  });

  it('keeps the name the provider shows when a part is missing', () => {
    expect(contactName({ name: 'Madonna', given_name: 'Madonna', family_name: null })).toBe(
      'Madonna'
    );
    expect(contactName({ name: 'Dr Lima', given_name: '  ', family_name: 'Lima' })).toBe('Dr Lima');
    expect(contactName({ name: 'Atlas', given_name: null, family_name: null })).toBe('Atlas');
  });
});
