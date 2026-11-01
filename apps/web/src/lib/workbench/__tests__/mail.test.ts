/**
 * The mail screen's model (ADR-369, Task 4.7): pure, read by the screen.
 *
 * A listing's params say only what was asked (nothing for an empty box or an
 * unpressed chip); a period is a range of the ACCOUNT's days, the last one
 * included on screen and excluded on the wire (`before` is the first day NOT
 * included); a row's date reads against the account's today, in its zone; an
 * act on a selection is told as it went — never all-or-nothing.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  EMPTY_MAIL_SEARCH,
  actReport,
  addDays,
  attachmentUrl,
  fileSize,
  initials,
  labelState,
  listingParams,
  readMailDensity,
  receivedLabel,
  subscribeMailDensity,
  writeMailDensity,
} from '../mail';

const TODAY = '2026-10-31';

describe('listingParams', () => {
  it('names the folder alone when nothing narrows it', () => {
    expect(listingParams('system:inbox', EMPTY_MAIL_SEARCH, TODAY)).toEqual({
      folder: 'system:inbox',
    });
  });

  it('carries the words trimmed and the pressed chips only', () => {
    const search = { ...EMPTY_MAIL_SEARCH, q: '  budget  ', unread: true };

    expect(listingParams('Label_7', search, TODAY)).toEqual({
      folder: 'Label_7',
      q: 'budget',
      unread: true,
    });
    expect(listingParams('Label_7', { ...EMPTY_MAIL_SEARCH, q: '   ' }, TODAY)).toEqual({
      folder: 'Label_7',
    });
  });

  it.each([
    ['week', '2026-10-25'],
    ['month', '2026-10-02'],
    ['year', '2025-11-01'],
  ] as const)('reads « the last %s » as the days up to today, today included', (period, after) => {
    expect(listingParams('system:inbox', { ...EMPTY_MAIL_SEARCH, period }, TODAY)).toEqual({
      folder: 'system:inbox',
      after,
    });
  });

  it('sends a chosen range with its last day included (before = the day after)', () => {
    const search = {
      ...EMPTY_MAIL_SEARCH,
      period: 'custom' as const,
      from: '2026-02-20',
      to: '2026-02-28',
    };

    expect(listingParams('system:inbox', search, TODAY)).toEqual({
      folder: 'system:inbox',
      after: '2026-02-20',
      before: '2026-03-01',
    });
    expect(listingParams('system:inbox', { ...search, from: '' }, TODAY), 'an open start').toEqual({
      folder: 'system:inbox',
      before: '2026-03-01',
    });
  });
});

describe('addDays', () => {
  it('crosses months and years on the calendar, never on a clock', () => {
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(addDays('2024-02-28', 1)).toBe('2024-02-29');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-03-29', 1), 'a DST change is not a day of 23 hours here').toBe(
      '2026-03-30'
    );
  });
});

describe('receivedLabel', () => {
  // 10:00 in Paris (UTC+1 since 25 October).
  const now = new Date('2026-10-31T09:00:00Z');
  const zone = 'Europe/Paris';

  it('tells today by its time, in the account’s zone', () => {
    expect(receivedLabel('2026-10-31T07:42:00Z', now, zone, 'fr')).toBe('08:42');
    expect(
      receivedLabel('2026-10-30T23:30:00Z', now, zone, 'fr'),
      'already today in Paris, still yesterday in UTC'
    ).toBe('00:30');
  });

  it('tells yesterday, this week, this year and before, each its own way', () => {
    expect(receivedLabel('2026-10-30T12:00:00Z', now, zone, 'fr')).toBe('hier');
    expect(receivedLabel('2026-10-27T12:00:00Z', now, zone, 'fr')).toBe('mar.');
    expect(receivedLabel('2026-03-05T12:00:00Z', now, zone, 'fr')).toBe('5 mars');
    expect(receivedLabel('2025-12-24T12:00:00Z', now, zone, 'fr')).toBe('24/12/2025');
  });

  it('draws nothing for a message without a date', () => {
    expect(receivedLabel(null, now, zone, 'fr')).toBeNull();
    expect(receivedLabel('not a date', now, zone, 'fr')).toBeNull();
  });
});

describe('actReport', () => {
  it('tells an act as it went', () => {
    expect(actReport({ done: ['a', 'b'], failed: [] })).toEqual({
      tone: 'success',
      done: 2,
      failed: 0,
    });
    expect(actReport({ done: ['a'], failed: [{ id: 'b', status: 'failed' }] })).toEqual({
      tone: 'partial',
      done: 1,
      failed: 1,
    });
    expect(actReport({ done: [], failed: [{ id: 'b', status: 'not_found' }] })).toEqual({
      tone: 'failed',
      done: 0,
      failed: 1,
    });
  });
});

describe('labelState', () => {
  const rows = [{ label_ids: ['L1', 'L2'] }, { label_ids: ['L1'] }];

  it('says whether every, some or none of the messages carry a label', () => {
    expect(labelState(rows, 'L1')).toBe('all');
    expect(labelState(rows, 'L2')).toBe('some');
    expect(labelState(rows, 'L3')).toBe('none');
    expect(labelState([], 'L1')).toBe('none');
  });
});

describe('initials', () => {
  it('reads the name, else the address, else nothing', () => {
    expect(initials({ name: 'Camille Martin', address: 'c@example.org' })).toBe('CM');
    expect(initials({ name: 'Ana', address: 'a@example.org' })).toBe('A');
    expect(initials({ name: '', address: 'bob@example.org' })).toBe('B');
    expect(initials({ name: '"Lima, Ana"', address: 'a@example.org' })).toBe('LA');
    expect(initials(null)).toBe('');
  });
});

describe('fileSize', () => {
  it('speaks the reader’s language and unit', () => {
    // French typography: a narrow no-break space between a figure and its unit.
    expect(fileSize(182 * 1024, 'fr')).toBe('182 ko');
    expect(fileSize(182 * 1024, 'en')).toBe('182 kB');
    expect(fileSize(3.5 * 1024 * 1024, 'en')).toBe('3.5 MB');
    expect(fileSize(512, 'en')).toBe('512 byte');
  });
});

describe('attachmentUrl', () => {
  it('names the message, the handle and the name — the name finds an expired handle', () => {
    const url = new URL(
      attachmentUrl('m1', {
        id: 'ANGj',
        filename: 'été & co.pdf',
        mime_type: 'application/pdf',
        size: 1,
      }),
      'https://api.example.org'
    );

    expect(url.pathname.endsWith('/workbench/mail/attachment')).toBe(true);
    expect(Object.fromEntries(url.searchParams)).toEqual({
      message_id: 'm1',
      attachment_id: 'ANGj',
      filename: 'été & co.pdf',
    });
  });

  it('goes by the name alone when the provider gave no handle', () => {
    const url = new URL(
      attachmentUrl('m1', { id: null, filename: 'a.txt', mime_type: 'text/plain', size: null }),
      'https://api.example.org'
    );

    expect(url.searchParams.has('attachment_id')).toBe(false);
    expect(url.searchParams.get('filename')).toBe('a.txt');
  });
});

describe('the list density, a per-device preference', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it('starts comfortable, remembers a choice and tells who listens', () => {
    const listener = vi.fn();
    const stop = subscribeMailDensity(listener);
    expect(readMailDensity()).toBe('comfortable');

    writeMailDensity('compact');

    expect(readMailDensity()).toBe('compact');
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
    writeMailDensity('comfortable');
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('reads an unknown value as the default', () => {
    window.localStorage.setItem('lia_workbench_mail_density', 'tiny');

    expect(readMailDensity()).toBe('comfortable');
  });

  it('never throws when storage is refused', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });

    expect(readMailDensity()).toBe('comfortable');
    expect(() => writeMailDensity('compact')).not.toThrow();
  });
});
