/**
 * What the page does with one search across the tools (ADR-369, lot 13): where a
 * hit opens, and whether anything can be searched at all.
 */
import { describe, expect, it } from 'vitest';

import { hitHref, searchOffered, toolHref } from '../search';
import type { SearchHit, WorkbenchAvailability, WorkbenchToolId } from '../types';

const HIT: SearchHit = {
  id: 'x/1',
  title: 'Budget',
  subtitle: null,
  mail_folder: null,
  calendar_id: null,
  day: null,
  is_folder: false,
};

function query(href: string): URLSearchParams {
  return new URLSearchParams(href.slice(href.indexOf('?')));
}

function rail(ready: readonly WorkbenchToolId[]): WorkbenchAvailability {
  const tools: readonly WorkbenchToolId[] = ['mail', 'tasks', 'lights', 'files'];
  return {
    tools: tools.map(tool => ({
      tool,
      state: ready.includes(tool) ? 'ready' : 'not_connected',
      provider: null,
      features: [],
      bounds: {},
    })),
    limits: {
      page_size: 25,
      bulk_max_items: 50,
      download_max_bytes: 1,
      upload_max_bytes: 1,
      calendar_window_max_events: 500,
      send_undo_seconds: 0,
      draft_autosave_seconds: 0,
      search_max_chars: 500,
    },
  };
}

describe('hitHref', () => {
  it('opens a message in the place it was found', () => {
    const href = hitHref('mail', { ...HIT, mail_folder: 'system:all' }, 'en');

    expect(href.startsWith('/en/dashboard/tools/mail?')).toBe(true);
    expect(query(href).get('folder')).toBe('system:all');
    expect(query(href).get('id')).toBe('x/1');
  });

  it('opens an event on its day, in its calendar', () => {
    const href = hitHref('calendar', { ...HIT, calendar_id: 'c 1', day: '2027-01-04' }, 'en');

    expect(href.startsWith('/en/dashboard/tools/calendar?')).toBe(true);
    expect(query(href).get('day')).toBe('2027-01-04');
    expect(query(href).get('cal')).toBe('c 1');
    expect(query(href).get('event')).toBe('x/1');
  });

  it('opens a contact', () => {
    const href = hitHref('contacts', HIT, 'en');

    expect(href.startsWith('/en/dashboard/tools/contacts?')).toBe(true);
    expect(query(href).get('contact')).toBe('x/1');
  });

  it('opens a file beside its list, and a folder as a place', () => {
    const file = hitHref('files', HIT, 'fr');
    const folder = hitHref('files', { ...HIT, is_folder: true }, 'fr');

    expect(query(file).get('file')).toBe('x/1');
    expect(query(file).get('folder')).toBeNull();
    expect(query(folder).get('folder')).toBe('x/1');
    expect(query(folder).get('file')).toBeNull();
  });

  it('never lets an id break out of its value', () => {
    const href = hitHref('contacts', { ...HIT, id: 'a&b=c#d' }, 'fr');

    expect(query(href).get('contact')).toBe('a&b=c#d');
    expect(query(href).get('b')).toBeNull();
  });
});

describe('toolHref', () => {
  it('opens the tool itself', () => {
    expect(toolHref('files', 'en')).toBe('/en/dashboard/tools/files');
  });
});

describe('searchOffered', () => {
  it('holds as soon as one tool that can search is ready', () => {
    expect(searchOffered(rail(['files']))).toBe(true);
  });

  it('does not hold on tools no search reaches', () => {
    expect(searchOffered(rail(['tasks', 'lights']))).toBe(false);
  });

  it('does not hold on a tool that is not ready', () => {
    expect(searchOffered(rail([]))).toBe(false);
  });
});
