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
  birthdayLabel,
  contactChange,
  contactName,
  displayNameOf,
  fullBirthday,
  fieldsOfContact,
  newContactBody,
  valuesMax,
  contactInitials,
  contactLetters,
  historyDay,
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
  job_title: 'Engineer',
  website: 'https://ana.example.org',
  birthday: '1990-05-15',
  emails: [
    { value: 'ana@example.org', type: 'work' },
    { value: 'ana@home.example', type: 'home' },
  ],
  phones: [{ value: '+33 6 12', type: 'mobile' }],
  addresses: [{ formatted: '1 rue de la Paix, Paris', type: 'home' }],
  notes: 'Met at the fair.',
};

/** A contact holding nothing beyond its name and its lists. */
const BARE: WorkbenchContact = {
  ...ANA,
  given_name: null,
  family_name: null,
  job_title: null,
  website: null,
  birthday: null,
};

describe('contactInitials', () => {
  it('reads the initials a person is known by', () => {
    expect(contactInitials({ name: 'Ana Lima', given_name: null, family_name: null })).toBe('AL');
    expect(contactInitials({ name: 'x', given_name: 'Élodie', family_name: 'Roux' })).toBe('ÉR');
    expect(contactInitials({ name: 'Acme', given_name: null, family_name: null })).toBe('A');
    expect(contactInitials({ name: '', given_name: null, family_name: null })).toBe('');
  });
});

describe('contactLetters', () => {
  const named = (name: string, family_name: string | null = null) => ({
    id: name,
    name,
    given_name: null,
    family_name,
  });

  it('heads each letter once, on the contact it starts with', () => {
    const letters = contactLetters([named('Ana'), named('Anne'), named('Bob')], 'en');

    expect([...letters]).toEqual([
      ['Ana', 'A'],
      ['Bob', 'B'],
    ]);
  });

  it('reads the family name first, as the provider sorts', () => {
    const letters = contactLetters([named('Zoé Adam', 'Adam'), named('Ana Bloch', 'Bloch')], 'en');

    expect([...letters.values()]).toEqual(['A', 'B']);
  });

  it('folds accents, so É stands with E', () => {
    const letters = contactLetters([named('Émile'), named('Eve')], 'fr');

    expect([...letters.values()]).toEqual(['E']);
  });

  it('heads nothing in a list that is not in that order: a letter would lie', () => {
    expect(contactLetters([named('Bob'), named('Ana')], 'en').size).toBe(0);
  });

  it('heads nothing above a name with no letter', () => {
    expect(contactLetters([named('')], 'en').size).toBe(0);
  });
});

describe('what a contact holds beyond its lists', () => {
  const base = fieldsOfContact(ANA);

  it('opens on what the contact holds', () => {
    expect(base).toMatchObject({
      given_name: 'Ana',
      family_name: 'Lima',
      job_title: 'Engineer',
      website: 'https://ana.example.org',
      birthday: '1990-05-15',
    });
  });

  it('sends a job and a website it changed, trimmed, and nothing else', () => {
    expect(contactChange(ANA.id, base, { ...base, job_title: ' CTO ' })).toEqual({
      id: ANA.id,
      job_title: 'CTO',
    });
    expect(contactChange(ANA.id, base, { ...base, website: 'https://new.example.org' })).toEqual({
      id: ANA.id,
      website: 'https://new.example.org',
    });
  });

  it('empties a field by sending an empty text', () => {
    expect(contactChange(ANA.id, base, { ...base, website: '  ' })).toEqual({
      id: ANA.id,
      website: '',
    });
  });

  it('writes a birthday typed, and takes it off when it is emptied', () => {
    expect(contactChange(ANA.id, base, { ...base, birthday: '1991-06-16' })).toEqual({
      id: ANA.id,
      birthday: '1991-06-16',
    });
    expect(contactChange(ANA.id, base, { ...base, birthday: '' })).toEqual({
      id: ANA.id,
      clear_birthday: true,
    });
  });

  it('leaves a birthday with no year alone, and takes it off when told', () => {
    const noYear = { ...base, birthday: '--05-15' };

    expect(contactChange(ANA.id, noYear, noYear)).toBeNull();
    expect(contactChange(ANA.id, noYear, { ...noYear, birthday: '' })).toEqual({
      id: ANA.id,
      clear_birthday: true,
    });
  });

  it('keeps the whole name in step when the parts change and it followed them', () => {
    expect(contactChange(ANA.id, base, { ...base, family_name: 'Silva' })).toEqual({
      id: ANA.id,
      family_name: 'Silva',
      name: 'Ana Silva',
    });
  });

  it('leaves a name of the person’s own alone when the parts change', () => {
    const own = { ...base, name: 'Dr Ana Lima' };

    expect(contactChange(ANA.id, own, { ...own, family_name: 'Silva' })).toEqual({
      id: ANA.id,
      family_name: 'Silva',
    });
  });

  it('never leaves a contact with no name when both parts are emptied', () => {
    expect(contactChange(ANA.id, base, { ...base, given_name: '', family_name: '' })).toEqual({
      id: ANA.id,
      given_name: '',
      family_name: '',
      name: 'Ana Lima',
    });
  });

  it('never empties the name while its parts can stand for it', () => {
    expect(contactChange(ANA.id, base, { ...base, name: '  ' })).toEqual({
      id: ANA.id,
      name: 'Ana Lima',
    });
  });

  it('keeps a name changed by hand beside the parts', () => {
    expect(contactChange(ANA.id, base, { ...base, name: 'Ana', family_name: 'Silva' })).toEqual({
      id: ANA.id,
      name: 'Ana',
      family_name: 'Silva',
    });
  });

  it('carries on a new contact what it was given, and no empties', () => {
    const fields = { ...fieldsOfContact(ANA), emails: [], phones: [], addresses: [] };

    expect(newContactBody(fields, KEY)).toMatchObject({
      given_name: 'Ana',
      family_name: 'Lima',
      job_title: 'Engineer',
      website: 'https://ana.example.org',
      birthday: '1990-05-15',
    });
    const bare = newContactBody({ ...fields, given_name: ' ', website: '', birthday: '' }, KEY);
    expect(bare).not.toHaveProperty('given_name');
    expect(bare).not.toHaveProperty('website');
    expect(bare).not.toHaveProperty('birthday');
  });

  it('names a new contact from its parts when the name is left empty', () => {
    const fields = { ...base, name: ' ', given_name: 'Ana', family_name: 'Lima' };

    expect(displayNameOf(fields)).toBe('Ana Lima');
    expect(newContactBody(fields, KEY).name).toBe('Ana Lima');
    expect(displayNameOf({ ...fields, given_name: '', family_name: '' })).toBe('');
  });

  it('reads a day the date field can hold', () => {
    expect(fullBirthday('1990-05-15')).toBe('1990-05-15');
    expect(fullBirthday('--05-15')).toBe('');
    expect(fullBirthday('')).toBe('');
  });
});

describe('birthdayLabel', () => {
  it('writes a birthday in the reader’s language', () => {
    expect(birthdayLabel('1990-05-15', 'en')).toBe('May 15, 1990');
    expect(birthdayLabel('1990-05-15', 'fr')).toBe('15 mai 1990');
  });

  it('writes one with no year without one', () => {
    expect(birthdayLabel('--05-15', 'en')).toBe('May 15');
    expect(birthdayLabel('--02-29', 'fr')).toBe('29 février');
  });

  it('never moves a day to the one before, whatever the reader’s clock', () => {
    const zone = process.env.TZ;
    process.env.TZ = 'America/New_York';
    try {
      expect(birthdayLabel('1990-01-01', 'en')).toBe('January 1, 1990');
    } finally {
      process.env.TZ = zone;
    }
  });
});

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
      ...fieldsOfContact({ ...BARE, notes: null, organization: null }),
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
describe('historyDay', () => {
  const NOW = new Date('2026-11-05T12:00:00Z');

  it('tells a line as the mail list does: its time today', () => {
    expect(historyDay({ at: '2026-11-05T09:30:00Z' }, NOW, 'UTC', 'en')).toBe('09:30 AM');
  });

  it('tells its day this year, with no year to read', () => {
    expect(historyDay({ at: '2026-03-03T09:00:00Z' }, NOW, 'UTC', 'fr')).toBe('3 mars');
  });

  it('tells its date before', () => {
    expect(historyDay({ at: '2024-03-03T09:00:00Z' }, NOW, 'UTC', 'fr')).toBe('03/03/2024');
  });

  it('reads an instant in the account’s zone', () => {
    const late = { at: '2026-03-03T23:30:00Z' };

    expect(historyDay(late, NOW, 'Asia/Tokyo', 'fr')).toBe('4 mars');
  });

  it('keeps a whole day its own, in no zone', () => {
    const whole = { at: '2026-03-02T23:00:00Z', day: '2026-03-03', all_day: true };

    expect(historyDay(whole, NOW, 'Pacific/Honolulu', 'fr')).toBe('3 mars');
  });

  it('draws nothing of a line with no date', () => {
    expect(historyDay({ at: null }, NOW, 'UTC', 'fr')).toBeNull();
  });
});

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
