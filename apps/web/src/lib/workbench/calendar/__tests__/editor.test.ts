/**
 * The event editor's model (ADR-369, Task 5.2, spec §14).
 *
 * What leaves is the WALL time and the account's zone id, never an offset; an
 * all-day event's last day, included in the form, becomes the exclusive end on
 * the wire. A change sends only what moved: an untouched guest list is never
 * rewritten, and bounds travel with whether they are days.
 */

import { describe, expect, it } from 'vitest';

import type { CalendarEventDetail } from '@/lib/workbench/types';

import { changeBody, endsAfterStart, fieldsOf, newEventBody, newEventFields } from '../editor';

const PARIS = 'Europe/Paris';
const KEY = '11111111-1111-4111-8111-111111111111';

const MEETING: CalendarEventDetail = {
  id: 'e1_20261102T090000Z',
  calendar_id: 'primary',
  summary: 'Revue',
  all_day: false,
  start: '2026-11-02T09:00:00Z',
  end: '2026-11-02T10:30:00Z',
  location: 'Salle Atlas',
  recurring: true,
  conference_url: null,
  description: null,
  attendees: [
    { email: 'ana@example.org', name: 'Ana', response: 'accepted' },
    { email: 'bob@example.org', name: null, response: 'needsAction' },
  ],
  organizer: 'ana@example.org',
  link: null,
};

describe('a new event', () => {
  it('leaves as wall times and the account’s zone, never an offset', () => {
    const fields = { ...newEventFields('primary', '2026-11-02', '10:00'), summary: ' Revue ' };

    expect(newEventBody(fields, PARIS, { conference: false, idempotencyKey: KEY })).toEqual({
      calendar_id: 'primary',
      summary: 'Revue',
      start: '2026-11-02T10:00',
      end: '2026-11-02T11:00',
      all_day: false,
      timezone: PARIS,
      idempotency_key: KEY,
    });
  });

  it('turns an all-day event’s last day, included, into the exclusive end', () => {
    const fields = {
      ...newEventFields('primary', '2026-11-02', '10:00'),
      summary: 'Congé',
      allDay: true,
      endDate: '2026-11-04',
    };

    const body = newEventBody(fields, PARIS, { conference: true, idempotencyKey: KEY });

    expect([body.start, body.end, body.all_day, body.conference]).toEqual([
      '2026-11-02',
      '2026-11-05',
      true,
      true,
    ]);
  });

  it('starts an hour long, the next day when the hour passes midnight', () => {
    const late = newEventFields('primary', '2026-11-02', '23:30');

    expect([late.endDate, late.endTime]).toEqual(['2026-11-03', '00:30']);
  });

  it('carries its guests each once', () => {
    const fields = {
      ...newEventFields('primary', '2026-11-02', '10:00'),
      summary: 'x',
      attendees: 'ana@example.org; bob@example.org, ana@example.org',
    };

    expect(
      newEventBody(fields, PARIS, { conference: false, idempotencyKey: KEY }).attendees
    ).toEqual(['ana@example.org', 'bob@example.org']);
  });
});

describe('an existing event', () => {
  it('opens on the account’s wall', () => {
    const fields = fieldsOf(MEETING, PARIS);

    expect([fields.startDate, fields.startTime, fields.endDate, fields.endTime]).toEqual([
      '2026-11-02',
      '10:00',
      '2026-11-02',
      '11:30',
    ]);
  });

  it('opens an all-day event on its last day, included', () => {
    const fields = fieldsOf(
      { ...MEETING, all_day: true, start: '2026-11-02', end: '2026-11-05' },
      PARIS
    );

    expect([fields.allDay, fields.startDate, fields.endDate]).toEqual([
      true,
      '2026-11-02',
      '2026-11-04',
    ]);
  });

  it('sends only what moved, on the occurrence’s own id', () => {
    const initial = fieldsOf(MEETING, PARIS);

    expect(
      changeBody(MEETING, initial, { ...initial, summary: 'Revue 2' }, PARIS, undefined)
    ).toEqual({
      calendar_id: 'primary',
      event_id: 'e1_20261102T090000Z',
      summary: 'Revue 2',
    });
  });

  it('sends the bounds together with whether they are days, and the zone', () => {
    const initial = fieldsOf(MEETING, PARIS);

    expect(changeBody(MEETING, initial, { ...initial, endTime: '12:00' }, PARIS, true)).toEqual({
      calendar_id: 'primary',
      event_id: 'e1_20261102T090000Z',
      start: '2026-11-02T10:00',
      end: '2026-11-02T12:00',
      all_day: false,
      timezone: PARIS,
      notify: true,
    });
  });

  it('says nothing changed when nothing did', () => {
    const initial = fieldsOf(MEETING, PARIS);

    expect(changeBody(MEETING, initial, { ...initial }, PARIS, true)).toBeNull();
  });
});

describe('endsAfterStart', () => {
  it('judges wall times as instants in the zone, and lets an all-day event last one day', () => {
    const fields = newEventFields('primary', '2026-11-02', '10:00');

    expect(endsAfterStart(fields, PARIS)).toBe(true);
    expect(endsAfterStart({ ...fields, endTime: '09:00' }, PARIS)).toBe(false);
    expect(endsAfterStart({ ...fields, allDay: true, endDate: '2026-11-02' }, PARIS)).toBe(true);
    expect(endsAfterStart({ ...fields, allDay: true, endDate: '2026-11-01' }, PARIS)).toBe(false);
  });
});
