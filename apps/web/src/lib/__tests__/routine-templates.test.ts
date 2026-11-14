import { describe, expect, it } from 'vitest';

import { recurrenceIsComplete } from '@/lib/recurrence';
import {
  ROUTINE_TEMPLATE_KEYS,
  applyRoutineTemplate,
  blankRoutineFields,
  clearRoutineTemplate,
  routineTemplateOf,
  type RoutineTemplateFields,
} from '@/lib/routine-templates';

const TODAY = '2026-11-13';
/** The key itself: the oracle is WHICH text a field takes, not its wording. */
const t = (key: string) => key;

interface Form extends RoutineTemplateFields {
  execution_mode: string;
}

function blank(): Form {
  return { ...blankRoutineFields(TODAY), execution_mode: 'pipeline' };
}

describe('routine templates', () => {
  it('offers the four ready-made routines, in this order', () => {
    expect(ROUTINE_TEMPLATE_KEYS).toEqual([
      'morning_briefing',
      'inbox_triage',
      'weekly_review',
      'overdue_tasks',
    ]);
  });

  it('fills the words of the template, in the reader language', () => {
    const form = applyRoutineTemplate(blank(), 'weekly_review', TODAY, t);
    expect(form.title).toBe('scheduled_actions.templates.weekly_review.title');
    expect(form.action_prompt).toBe('scheduled_actions.templates.weekly_review.prompt');
  });

  it('runs the morning briefing every day at 7:30, from today', () => {
    const form = applyRoutineTemplate(blank(), 'morning_briefing', TODAY, t);
    expect(form.trigger_kind).toBe('time');
    expect(form.recurrence).toMatchObject({
      freq: 'daily',
      interval: 1,
      anchor_date: TODAY,
      times: { mode: 'at', at: [{ hour: 7, minute: 30 }] },
    });
    expect(form.notify_only_when_new).toBe(false);
  });

  it('sorts the inbox on weekdays at 8:00, and only tells of something new', () => {
    const form = applyRoutineTemplate(
      { ...blank(), requires_approval: true },
      'inbox_triage',
      TODAY,
      t
    );
    expect(form.recurrence).toMatchObject({
      freq: 'weekly',
      byweekday: [1, 2, 3, 4, 5],
      times: { mode: 'at', at: [{ hour: 8, minute: 0 }] },
    });
    // The two delivery choices exclude each other (RoutineDeliveryFields).
    expect(form.notify_only_when_new).toBe(true);
    expect(form.requires_approval).toBe(false);
  });

  it('reviews the week on Sunday at 18:00', () => {
    const form = applyRoutineTemplate(blank(), 'weekly_review', TODAY, t);
    expect(form.recurrence).toMatchObject({
      freq: 'weekly',
      byweekday: [7],
      times: { mode: 'at', at: [{ hour: 18, minute: 0 }] },
    });
  });

  it('watches the tasks for one that falls overdue', () => {
    const form = applyRoutineTemplate(blank(), 'overdue_tasks', TODAY, t);
    expect(form.trigger_kind).toBe('condition');
    expect(form.condition_type).toBe('task_overdue');
    expect(form.condition_query).toBe('');
    expect(form.condition_until).toBe('');
  });

  it('builds schedules the editor and the API accept', () => {
    for (const key of ROUTINE_TEMPLATE_KEYS) {
      const form = applyRoutineTemplate(blank(), key, TODAY, t);
      expect(recurrenceIsComplete(form.recurrence), key).toBe(true);
    }
  });

  it('leaves alone what a template does not own', () => {
    expect(applyRoutineTemplate(blank(), 'inbox_triage', TODAY, t).execution_mode).toBe(
      'pipeline'
    );
  });

  it('knows the template a form holds, and none once its instruction is edited', () => {
    const picked = applyRoutineTemplate(blank(), 'inbox_triage', TODAY, t);
    const retitled: Form = { ...picked, title: 'Mon tri' };
    const reworded: Form = { ...picked, action_prompt: 'Autre chose' };
    expect(routineTemplateOf(picked, t)).toBe('inbox_triage');
    expect(routineTemplateOf(retitled, t)).toBe('inbox_triage');
    expect(routineTemplateOf(reworded, t)).toBeNull();
    expect(routineTemplateOf(blank(), t)).toBeNull();
  });

  it('empties what a template filled, and only that', () => {
    const picked = applyRoutineTemplate(blank(), 'overdue_tasks', TODAY, t);
    const cleared = clearRoutineTemplate(picked, TODAY, t);
    expect(cleared).toEqual(blank());
    // A routine written by hand is never emptied by the list.
    const handWritten = { ...blank(), title: 'Arroser', action_prompt: 'Rappelle-moi' };
    expect(clearRoutineTemplate(handWritten, TODAY, t)).toBe(handWritten);
  });
});
