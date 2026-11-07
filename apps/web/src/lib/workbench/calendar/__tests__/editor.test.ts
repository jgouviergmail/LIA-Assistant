/**
 * The event editor's model (ADR-369, Task 5.2, spec §14).
 *
 * What leaves is the WALL time and the account's zone id, never an offset; an
 * all-day event's last day, included in the form, becomes the exclusive end on
 * the wire. A change sends only what moved: an untouched guest list is never
 * rewritten, and bounds travel with whether they are days.
 */

import { emptyRecurrence, withFreq } from '@/lib/recurrence';
import { describe, expect, it } from 'vitest';

import type { CalendarEventDetail } from '@/lib/workbench/types';

import {
  allDayFields,
  changeBody,
  duplicateFields,
  editorFieldsOf,
  endsAfterStart,
  fieldsOf,
  newEventBody,
  NO_REMINDER,
  newEventFields,
  withProposedEvent,
} from '../editor';
import type { ProposedEvent } from '../../assist';

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
  reminder_minutes: null,
  busy: true,
  private: false,
  zone: null,
  my_response: null,
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

describe('what an event says beyond its time', () => {
  const event = { calendar_id: 'primary', id: 'e1' };
  const initial = newEventFields('primary', '2026-11-05', '09:00');

  it('leaves out of a new event what the person did not touch', () => {
    const body = newEventBody(initial, 'Europe/Paris', { conference: false, idempotencyKey: 'k' });

    expect(body).not.toHaveProperty('reminder_minutes');
    expect(body).not.toHaveProperty('busy');
    expect(body).not.toHaveProperty('private');
  });

  it('carries what the person chose on a new event', () => {
    const body = newEventBody(
      { ...initial, reminder: 15, busy: false, private: true },
      'Europe/Paris',
      { conference: false, idempotencyKey: 'k' }
    );

    expect(body).toMatchObject({ reminder_minutes: 15, busy: false, private: true });
  });

  it('says only what changed', () => {
    const change = changeBody(
      event,
      initial,
      { ...initial, busy: false },
      'Europe/Paris',
      undefined
    );

    expect(change).toEqual({ calendar_id: 'primary', event_id: 'e1', busy: false });
  });

  it('takes a reminder off', () => {
    const had = { ...initial, reminder: 30 };

    const change = changeBody(event, had, { ...had, reminder: null }, 'Europe/Paris', undefined);

    expect(change?.reminder_minutes).toBe(NO_REMINDER);
  });

  it('adds a call to an event, and that alone is a change', () => {
    const change = changeBody(event, initial, initial, 'Europe/Paris', undefined, true);

    expect(change).toEqual({ calendar_id: 'primary', event_id: 'e1', conference: true });
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

describe('allDayFields', () => {
  it('is one day long, on the day picked', () => {
    expect(allDayFields('primary', '2026-11-02')).toMatchObject({
      allDay: true,
      startDate: '2026-11-02',
      endDate: '2026-11-02',
    });
  });
});

describe('duplicateFields', () => {
  it('keeps what the event says, in the calendar it is copied to', () => {
    const copy = duplicateFields(MEETING, PARIS, 'family');

    expect(copy).toMatchObject({
      calendarId: 'family',
      summary: 'Revue',
      location: 'Salle Atlas',
      attendees: 'ana@example.org, bob@example.org',
      startDate: '2026-11-02',
      startTime: '10:00',
      endTime: '11:30',
    });
  });
});

describe('an event’s own zone', () => {
  const NEW_YORK = 'America/New_York';
  const SET_THERE: CalendarEventDetail = {
    ...MEETING,
    start: '2026-11-02T14:00:00Z',
    end: '2026-11-02T15:00:00Z',
    zone: NEW_YORK,
  };

  it('opens the form on the clock it was set on', () => {
    const fields = editorFieldsOf(SET_THERE, PARIS);

    expect(fields).toMatchObject({ zone: NEW_YORK, startTime: '09:00', endTime: '10:00' });
  });

  it('opens on the account’s clock when it says none, or the account’s own', () => {
    expect(editorFieldsOf({ ...SET_THERE, zone: null }, PARIS)).toMatchObject({
      zone: null,
      startTime: '15:00',
    });
    expect(editorFieldsOf({ ...SET_THERE, zone: PARIS }, PARIS)).toMatchObject({
      zone: null,
      startTime: '15:00',
    });
  });

  it('leaves a zone this browser does not know to the account’s clock', () => {
    const unknown = { ...SET_THERE, zone: 'Mars/Olympus_Mons' };

    expect(editorFieldsOf(unknown, PARIS)).toMatchObject({ zone: null, startTime: '15:00' });
  });

  it('gives a day no clock', () => {
    const day = { ...SET_THERE, all_day: true, start: '2026-11-02', end: '2026-11-03' };

    expect(editorFieldsOf(day, PARIS)).toMatchObject({ zone: null, startDate: '2026-11-02' });
  });

  it('keeps the account’s clock outside the form: a drop reads the view', () => {
    expect(fieldsOf(SET_THERE, PARIS)).toMatchObject({ zone: null, startTime: '15:00' });
  });

  it('sends nothing for an event left as it opened', () => {
    const fields = editorFieldsOf(SET_THERE, PARIS);

    expect(changeBody(SET_THERE, fields, fields, PARIS, undefined)).toBeNull();
  });

  it('keeps the zone when a time changes', () => {
    const initial = editorFieldsOf(SET_THERE, PARIS);

    const change = changeBody(
      SET_THERE,
      initial,
      { ...initial, startTime: '08:00' },
      PARIS,
      undefined
    );

    expect(change).toMatchObject({ start: '2026-11-02T08:00', timezone: NEW_YORK });
  });

  it('moves the event when the zone alone changes: its wall times are read on the new one', () => {
    const initial = editorFieldsOf(SET_THERE, PARIS);

    const change = changeBody(SET_THERE, initial, { ...initial, zone: null }, PARIS, undefined);

    expect(change).toMatchObject({
      start: '2026-11-02T09:00',
      end: '2026-11-02T10:00',
      all_day: false,
      timezone: PARIS,
    });
  });

  it('leaves with the zone chosen on a new event', () => {
    const fields = { ...newEventFields('primary', '2026-11-02', '10:00'), zone: NEW_YORK };

    expect(newEventBody(fields, PARIS, { conference: false, idempotencyKey: KEY }).timezone).toBe(
      NEW_YORK
    );
  });

  it('reads an end after the start on the clock chosen', () => {
    const fields = {
      ...newEventFields('primary', '2026-03-08', '02:30'),
      endTime: '03:00',
      endDate: '2026-03-08',
    };

    // That night New York has no 02:30: it starts when it ends. Paris has both.
    expect(endsAfterStart(fields, PARIS)).toBe(true);
    expect(endsAfterStart({ ...fields, zone: NEW_YORK }, PARIS)).toBe(false);
  });
});

describe('a repeating event', () => {
  const weekly = (fields: ReturnType<typeof newEventFields>) => ({
    ...fields,
    repeat: { ...withFreq(emptyRecurrence(fields.startDate), 'weekly') },
  });

  it('leaves as it was asked, from the event\u2019s own day', () => {
    const fields = weekly(newEventFields('primary', '2027-01-04', '09:00'));

    const body = newEventBody(fields, 'Europe/Paris', { conference: false, idempotencyKey: 'k' });

    expect(body.recurrence?.freq).toBe('weekly');
    expect(body.recurrence?.anchor_date).toBe('2027-01-04');
  });

  it('says nothing of a one-off', () => {
    const fields = newEventFields('primary', '2027-01-04', '09:00');

    const body = newEventBody(fields, 'Europe/Paris', { conference: false, idempotencyKey: 'k' });

    expect(body).not.toHaveProperty('recurrence');
  });

  it('follows the event when its day moves', () => {
    const fields = { ...weekly(newEventFields('primary', '2027-01-04', '09:00')) };
    const moved = { ...fields, startDate: '2027-01-05', endDate: '2027-01-05' };

    const body = newEventBody(moved, 'Europe/Paris', { conference: false, idempotencyKey: 'k' });

    expect(body.recurrence?.anchor_date).toBe('2027-01-05');
  });

  const event = { calendar_id: 'primary', id: 'e1_1' };

  it('reaches a whole series when asked, and says so', () => {
    const initial = newEventFields('primary', '2027-01-04', '09:00');

    const change = changeBody(
      event,
      initial,
      { ...initial, summary: 'Retro' },
      'Europe/Paris',
      undefined,
      false,
      true
    );

    expect(change).toMatchObject({ summary: 'Retro', scope: 'series' });
  });

  it('carries a new rule for a whole series, read in its zone', () => {
    const initial = newEventFields('primary', '2027-01-04', '09:00');

    const change = changeBody(
      event,
      initial,
      weekly(initial),
      'Europe/Paris',
      undefined,
      false,
      true
    );

    expect(change?.recurrence?.freq).toBe('weekly');
    expect(change?.timezone).toBe('Europe/Paris');
  });

  it('asks nothing of a series when nothing changed', () => {
    const initial = newEventFields('primary', '2027-01-04', '09:00');

    expect(changeBody(event, initial, initial, 'Europe/Paris', undefined, false, true)).toBeNull();
  });

  it('never carries a rule on one occurrence', () => {
    const initial = newEventFields('primary', '2027-01-04', '09:00');

    const change = changeBody(
      event,
      initial,
      { ...weekly(initial), summary: 'Retro' },
      'Europe/Paris',
      undefined
    );

    expect(change).not.toHaveProperty('recurrence');
    expect(change).not.toHaveProperty('scope');
  });
});

describe('an event LIA read, in the form', () => {
  const BASE = newEventFields('c1', '2026-11-04', '10:00');
  const NOTHING: ProposedEvent = {
    summary: 'Lunch',
    start_date: null,
    start_time: null,
    end_date: null,
    end_time: null,
    all_day: false,
    location: '',
    description: '',
    attendees: [],
    repeat: 'none',
  };

  it('keeps the form’s day and hour where nothing was said', () => {
    const fields = withProposedEvent(BASE, NOTHING);

    expect(fields.summary).toBe('Lunch');
    expect(fields.startDate).toBe('2026-11-04');
    expect(fields.startTime).toBe('10:00');
  });

  it('takes the day and hour it read, an hour long when no end was said', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      start_date: '2026-11-05',
      start_time: '12:30',
    });

    expect(fields.startDate).toBe('2026-11-05');
    expect(fields.startTime).toBe('12:30');
    expect(fields.endDate).toBe('2026-11-05');
    expect(fields.endTime).toBe('13:30');
  });

  it('moves into the next day when an hour long crosses midnight', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      start_date: '2026-11-05',
      start_time: '23:30',
    });

    expect(fields.endDate).toBe('2026-11-06');
    expect(fields.endTime).toBe('00:30');
  });

  it('takes an end it read', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      start_date: '2026-11-05',
      start_time: '09:00',
      end_date: '2026-11-05',
      end_time: '17:00',
    });

    expect(fields.endTime).toBe('17:00');
  });

  it('keeps the form’s hour on a day read alone', () => {
    const fields = withProposedEvent(BASE, { ...NOTHING, start_date: '2026-11-05' });

    expect(fields.startDate).toBe('2026-11-05');
    expect(fields.startTime).toBe('10:00');
    expect(fields.endDate).toBe('2026-11-05');
  });

  it('makes whole days of an all-day event, its last day kept', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      all_day: true,
      start_date: '2026-11-05',
      end_date: '2026-11-07',
    });

    expect(fields.allDay).toBe(true);
    expect(fields.startDate).toBe('2026-11-05');
    expect(fields.endDate).toBe('2026-11-07');
  });

  it('writes the guests as the field takes them', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      attendees: ['ana@example.org', 'paul@example.org'],
    });

    expect(fields.attendees).toBe('ana@example.org, paul@example.org');
  });

  it('keeps a title and a repetition the person chose where it read none', () => {
    const typed = {
      ...BASE,
      summary: 'Mine',
      repeat: withFreq(emptyRecurrence('2026-11-04'), 'weekly'),
    };

    const fields = withProposedEvent(typed, { ...NOTHING, summary: '', start_date: '2026-11-09' });

    expect(fields.summary).toBe('Mine');
    expect(fields.repeat.freq).toBe('weekly');
    expect(fields.repeat.anchor_date).toBe('2026-11-09');
  });

  it('keeps what the person already typed where nothing was read', () => {
    const typed = { ...BASE, location: 'Office', description: 'Mine' };

    const fields = withProposedEvent(typed, NOTHING);

    expect(fields.location).toBe('Office');
    expect(fields.description).toBe('Mine');
  });

  it('repeats on the rule it read, from the event’s own day', () => {
    const fields = withProposedEvent(BASE, {
      ...NOTHING,
      start_date: '2026-11-05',
      repeat: 'weekly',
    });

    expect(fields.repeat.freq).toBe('weekly');
    expect(fields.repeat.anchor_date).toBe('2026-11-05');
  });

  it('does not repeat where no rule was read', () => {
    expect(withProposedEvent(BASE, NOTHING).repeat.freq).toBe('once');
  });
});
