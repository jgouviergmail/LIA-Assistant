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
  folderTree,
  initials,
  labelState,
  listingParams,
  cidsOf,
  actOfDrop,
  conversationAnchor,
  draggedIds,
  isPlace,
  lineMembers,
  mailLines,
  movesFrom,
  takesDrop,
  nextAfter,
  readMailDensity,
  readMailGrouping,
  receivedLabel,
  selectedMembers,
  subscribeMailDensity,
  subscribeMailGrouping,
  writeMailDensity,
  writeMailGrouping,
} from '../mail';
import type { MailSummary } from '../types';

const TODAY = '2026-10-31';

describe('folderTree', () => {
  const own = (...names: string[]) =>
    names.map(name => ({ id: name, kind: 'user' as const, role: null, name }));
  const shown = (names: string[]) =>
    folderTree(own(...names), 'en').map(node => [node.name, node.depth]);

  it('sets a folder under its parent, named by its last word', () => {
    expect(shown(['Clients', 'Clients/Acme', 'Clients/Acme/2026'])).toEqual([
      ['Clients', 0],
      ['Acme', 1],
      ['2026', 2],
    ]);
  });

  it('keeps children under their parent, whatever sorts between them', () => {
    expect(shown(['A-z', 'A/b', 'A', 'B'])).toEqual([
      ['A', 0],
      ['b', 1],
      ['A-z', 0],
      ['B', 0],
    ]);
  });

  it('keeps the whole name of a label whose parent does not exist', () => {
    expect(shown(['Trips/2026'])).toEqual([['Trips/2026', 0]]);
  });

  it('names what lies below the nearest parent that exists', () => {
    expect(shown(['A', 'A/b/c'])).toEqual([
      ['A', 0],
      ['b/c', 1],
    ]);
  });

  it('sorts as the reader reads, case aside', () => {
    expect(shown(['zèbre', 'Étude', 'avion']).map(([name]) => name)).toEqual([
      'avion',
      'Étude',
      'zèbre',
    ]);
  });

  it('leaves the folders it was given as they are', () => {
    const folders = own('B', 'A');

    const tree = folderTree(folders, 'en');

    expect(tree.map(node => node.folder)).toEqual([folders[1], folders[0]]);
    expect(folders.map(folder => folder.name)).toEqual(['B', 'A']);
  });
});

describe('cidsOf', () => {
  it('names each image a message carries, once, as its headers spell it', () => {
    expect(
      cidsOf('<img src="cid:a@x"><img src=\'cid:b%40x\'><td background=cid:a@x><img src="x.png">')
    ).toEqual(['a@x', 'b@x']);
  });

  it('asks for what the API may answer, no more', () => {
    const html = Array.from({ length: 40 }, (_, index) => `<img src="cid:i${index}">`).join('');

    expect(cidsOf(html)).toHaveLength(30);
  });

  it('keeps a name that does not decode as it is', () => {
    expect(cidsOf('<img src="cid:100%">')).toEqual(['100%']);
  });
});

describe('isPlace', () => {
  it.each(['system:inbox', 'system:archive', 'system:spam', 'system:trash', 'Label_1', 'Projets'])(
    '%s holds what it lists',
    folder => {
      expect(isPlace(folder)).toBe(true);
    }
  );

  it.each(['system:starred', 'system:sent', 'system:drafts', 'system:all'])(
    '%s is a view: it says nothing of where a message is',
    folder => {
      expect(isPlace(folder)).toBe(false);
    }
  );
});

describe('movesFrom', () => {
  const archive = {
    id: 'system:archive',
    kind: 'system',
    role: 'archive',
    name: null,
  } as const;
  const WITH_ARCHIVE = [archive];
  const NO_ARCHIVE: readonly (typeof archive)[] = [];

  it('sends a message of the inbox anywhere', () => {
    expect(movesFrom('system:inbox', NO_ARCHIVE, false)).toEqual({
      archive: true,
      spam: true,
      notSpam: false,
      restore: false,
      forever: false,
      move: true,
    });
  });

  it('archives from a folder only where a mailbox has an archive folder', () => {
    expect(movesFrom('Projets', WITH_ARCHIVE, false).archive).toBe(true);
    // Gmail: a label view's message may not be in the inbox, and would stay listed.
    expect(movesFrom('Label_1', NO_ARCHIVE, false).archive).toBe(false);
  });

  it('offers no archive from the archive', () => {
    expect(movesFrom('system:archive', WITH_ARCHIVE, false)).toMatchObject({
      archive: false,
      move: true,
    });
  });

  it('takes a message out of the spam by saying it is none', () => {
    expect(movesFrom('system:spam', WITH_ARCHIVE, false)).toEqual({
      archive: false,
      spam: false,
      notSpam: true,
      restore: false,
      forever: false,
      move: false,
    });
  });

  it('restores from the trash, and deletes for good where the provider can', () => {
    expect(movesFrom('system:trash', NO_ARCHIVE, false)).toMatchObject({
      restore: true,
      forever: false,
      move: false,
    });
    expect(movesFrom('system:trash', WITH_ARCHIVE, true).forever).toBe(true);
  });

  it('moves from a view, and reports nothing as spam from the sent', () => {
    expect(movesFrom('system:sent', WITH_ARCHIVE, false)).toMatchObject({
      move: true,
      spam: false,
      archive: false,
    });
    expect(movesFrom('system:starred', NO_ARCHIVE, false).move).toBe(true);
  });

  it('reads the folders it does not know yet as a mailbox without an archive', () => {
    expect(movesFrom('Projets', undefined, false).archive).toBe(false);
  });
});

describe('dropping on the pane', () => {
  const folder = (id: string, kind: 'system' | 'user' = 'system') =>
    ({ id, kind, role: null, name: null }) as const;

  it.each([
    ['system:trash', 'trash'],
    ['system:archive', 'archive'],
    ['system:spam', 'spam'],
    ['system:inbox', 'move'],
    ['Projets', 'move'],
  ])('a drop on %s is told as %s', (id, act) => {
    expect(actOfDrop(id)).toBe(act);
  });

  it('takes a place or a folder, never what is listed nor a view', () => {
    expect(takesDrop(folder('Projets', 'user'), 'system:inbox')).toBe(true);
    expect(takesDrop(folder('system:trash'), 'system:inbox')).toBe(true);
    expect(takesDrop(folder('system:inbox'), 'system:inbox')).toBe(false);
    expect(takesDrop(folder('system:starred'), 'system:inbox')).toBe(false);
    expect(takesDrop(folder('system:sent'), 'system:inbox')).toBe(false);
  });

  it('carries the selection when the drag starts on it, else the row alone', () => {
    expect(draggedIds('a', new Set(['a', 'b']))).toEqual(['a', 'b']);
    expect(draggedIds('c', new Set(['a', 'b']))).toEqual(['c']);
  });
});

describe('nextAfter', () => {
  const rows = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];

  it('is the row below, the row above at the end, nothing alone', () => {
    expect(nextAfter(rows, 'a')?.id).toBe('b');
    expect(nextAfter(rows, 'c')?.id).toBe('b');
    expect(nextAfter([{ id: 'a' }], 'a')).toBeNull();
    expect(nextAfter(rows, 'gone')).toBeNull();
  });
});

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

function summary(id: string, thread: string, overrides: Partial<MailSummary> = {}): MailSummary {
  return {
    id,
    thread_id: thread,
    sender: null,
    subject: id,
    snippet: '',
    received_at: null,
    is_read: true,
    is_starred: false,
    has_attachments: false,
    label_ids: [],
    ...overrides,
  };
}

describe('mailLines', () => {
  const rows = [summary('m3', 't1'), summary('m2', 't2'), summary('m1', 't1')];
  const shown = (grouped: boolean) => mailLines(rows, grouped).map(line => line.message.id);

  it('keeps a line per message when nothing is grouped', () => {
    expect(shown(false)).toEqual(['m3', 'm2', 'm1']);
  });

  it('puts a conversation under its newest message, in the order of the listing', () => {
    expect(shown(true)).toEqual(['m3', 'm2']);
    expect(mailLines(rows, true)[0].members.map(member => member.id)).toEqual(['m3', 'm1']);
  });

  it('reads as unread while one of its messages is', () => {
    const line = mailLines([summary('m2', 't1'), summary('m1', 't1', { is_read: false })], true)[0];

    expect(line.message.is_read).toBe(false);
    expect(line.message.id).toBe('m2');
  });

  it('carries what any of its messages carries', () => {
    const [line] = mailLines(
      [
        summary('m2', 't1', { label_ids: ['a'] }),
        summary('m1', 't1', { is_starred: true, has_attachments: true, label_ids: ['a', 'b'] }),
      ],
      true
    );

    expect(line.message.is_starred).toBe(true);
    expect(line.message.has_attachments).toBe(true);
    expect(line.message.label_ids).toEqual(['a', 'b']);
  });

  it('leaves a message alone as it was', () => {
    const lone = summary('m1', 't1', { is_read: false });

    expect(mailLines([lone], true)[0].message).toEqual(lone);
  });
});

describe('what a line stands for', () => {
  const lines = mailLines([summary('m3', 't1'), summary('m2', 't2'), summary('m1', 't1')], true);

  it('a selection covers every message of the lines ticked', () => {
    expect(selectedMembers(lines, new Set(['m3'])).map(member => member.id)).toEqual(['m3', 'm1']);
  });

  it('a line is named by what it shows, never by a message under it', () => {
    expect(selectedMembers(lines, new Set(['m1']))).toEqual([]);
  });

  it('a drag carries the messages of the line it starts on', () => {
    expect(lineMembers(lines, 'm3')).toEqual(['m3', 'm1']);
  });

  it('a message no line shows stands for itself', () => {
    expect(lineMembers(lines, 'gone')).toEqual(['gone']);
  });
});

describe('conversationAnchor', () => {
  const rows = [summary('m1', 't1'), summary('m2', 't1')];

  it('starts from the message once it landed', () => {
    expect(conversationAnchor(null, undefined, true, 'm1')).toBe('m1');
  });

  it('waits for the message to land', () => {
    expect(conversationAnchor(null, undefined, true, undefined)).toBeNull();
  });

  it('holds while the person walks what was read', () => {
    expect(conversationAnchor('m1', rows, true, 'm2')).toBe('m1');
  });

  it('holds while the next message is on its way', () => {
    expect(conversationAnchor('m1', rows, true, undefined)).toBe('m1');
  });

  it('leaves for a message outside it', () => {
    expect(conversationAnchor('m1', rows, true, 'm9')).toBe('m9');
  });

  it('leaves a read still under way for the message that replaced it', () => {
    expect(conversationAnchor('m1', undefined, true, 'm2')).toBe('m2');
  });

  it('stays on a message its own conversation leaves out', () => {
    expect(conversationAnchor('d1', rows, true, 'd1')).toBe('d1');
  });

  it('lets go when the reader closes', () => {
    expect(conversationAnchor('m1', rows, false, undefined)).toBeNull();
  });
});

describe('the grouping, a per-device preference', () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('starts flat, remembers the choice and tells who listens', () => {
    const listener = vi.fn();
    const stop = subscribeMailGrouping(listener);
    expect(readMailGrouping()).toBe('flat');

    writeMailGrouping('grouped');

    expect(readMailGrouping()).toBe('grouped');
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
  });

  it('reads anything else as flat', () => {
    window.localStorage.setItem('lia_workbench_mail_grouping', 'tiny');

    expect(readMailGrouping()).toBe('flat');
  });

  it('lives through a storage that refuses', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('refused');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('refused');
    });

    expect(readMailGrouping()).toBe('flat');
    expect(() => writeMailGrouping('grouped')).not.toThrow();
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
