/**
 * Where a home card's item opens in the Tools, and the plain links its menu holds (2026-11-07).
 *
 * An item opens on the address its tool already reads, so a link from the home works like any
 * link of that tool; an item that lacks what its tool needs (a payload cached before the ids
 * joined it) opens nothing there, and the card keeps the chat.
 */
import { describe, expect, it } from 'vitest';

import {
  birthdayHref,
  directionsHref,
  documentHref,
  eventHref,
  homeLanguage,
  mailHref,
  postponedDay,
  taskHref,
  telHref,
} from '../briefing-tools';

const query = (href: string) => new URL(href, 'https://lia.test').searchParams;

describe('eventHref', () => {
  const EVENT = {
    title: 'Comité',
    start_local: '00:30',
    end_local: null,
    location: null,
    id: 'evt/1',
    calendar_id: 'work@group',
    // 00:30 in Paris on the 8th is still the 7th in UTC.
    start_at: '2026-11-07T23:30:00Z',
  };

  it('opens the event on its day in the account zone, in its calendar', () => {
    const href = eventHref(EVENT, 'en', 'Europe/Paris');

    expect(href?.startsWith('/en/dashboard/tools/calendar?')).toBe(true);
    expect(query(href!).get('day')).toBe('2026-11-08');
    expect(query(href!).get('cal')).toBe('work@group');
    expect(query(href!).get('event')).toBe('evt/1');
  });

  it.each([
    ['id', { id: null }],
    ['calendar', { calendar_id: null }],
    ['start', { start_at: null }],
  ])('opens nothing without its %s', (_, missing) => {
    expect(eventHref({ ...EVENT, ...missing }, 'fr', 'Europe/Paris')).toBeNull();
  });
});

describe('mailHref, taskHref, documentHref, birthdayHref', () => {
  it('opens an unread message in the inbox', () => {
    const href = mailHref({ id: 'm/1' }, 'en');

    expect(href?.startsWith('/en/dashboard/tools/mail?')).toBe(true);
    expect(query(href!).get('folder')).toBe('system:inbox');
    expect(query(href!).get('id')).toBe('m/1');
  });

  it('opens a task in its own list', () => {
    const href = taskHref({ id: 't1', list_id: 'L 1' }, 'en');

    expect(href?.startsWith('/en/dashboard/tools/tasks?')).toBe(true);
    expect(query(href!).get('list')).toBe('L 1');
    expect(query(href!).get('task')).toBe('t1');
  });

  it('names no list it could not read: the tool opens its own default', () => {
    const href = taskHref({ id: 't1', list_id: null }, 'en');

    expect(query(href!).has('list')).toBe(false);
    expect(query(href!).get('task')).toBe('t1');
  });

  it('opens a file and a contact', () => {
    expect(query(documentHref({ id: 'f1' }, 'en')!).get('file')).toBe('f1');
    expect(documentHref({ id: 'f1' }, 'en')?.startsWith('/en/dashboard/tools/files?')).toBe(true);
    expect(query(birthdayHref({ contact_id: 'people/c42' }, 'en')!).get('contact')).toBe(
      'people/c42'
    );
  });

  it('opens nothing for an item that carries no id', () => {
    expect(mailHref({ id: null }, 'en')).toBeNull();
    expect(taskHref({ id: undefined, list_id: 'L' }, 'en')).toBeNull();
    expect(documentHref({}, 'en')).toBeNull();
    expect(birthdayHref({ contact_id: null }, 'en')).toBeNull();
  });
});

describe('plain links', () => {
  it('asks a map for the way to a place', () => {
    const href = directionsHref('12 rue de la Paix, Paris');

    expect(href.startsWith('https://www.google.com/maps/dir/?')).toBe(true);
    expect(query(href).get('destination')).toBe('12 rue de la Paix, Paris');
  });

  it.each([
    ['+33 6 12 34 56 78', 'tel:+33612345678'],
    ['06.12.34.56.78', 'tel:0612345678'],
  ])('dials %s', (number, expected) => {
    expect(telHref(number)).toBe(expected);
  });

  it.each(['AMAZON', 'Info-SMS', '', '12'])('dials nothing for %j', sender => {
    expect(telHref(sender)).toBeNull();
  });

  it.each([
    ['fr-FR', 'fr'],
    ['zh', 'zh'],
    ['pt-BR', 'fr'],
    [undefined, 'fr'],
  ])('reads the page language %j as %j', (raw, expected) => {
    expect(homeLanguage(raw)).toBe(expected);
  });

  it('postpones to the account’s tomorrow, whatever the browser’s day', () => {
    // 23:30 UTC on the 7th is already the 8th in Paris: tomorrow is the 9th.
    expect(postponedDay('Europe/Paris', new Date('2026-11-07T23:30:00Z'))).toBe('2026-11-09');
  });
});
