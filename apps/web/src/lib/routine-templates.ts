/**
 * Ready-made routines the studio offers (lot 13): a template fills the create
 * form, nothing is scheduled until the person saves, and every field stays theirs
 * to change.
 *
 * A template is words in the reader's language (`scheduled_actions.templates.<key>.*`)
 * and a clock: a schedule starting today, or a watched condition. The morning
 * briefing, the weekly review and the inbox triage ask, in words, for what the
 * system skills of the same purpose answer (`data/skills/system/`), so a run of
 * theirs takes the skill's fixed plan when the analyzer recognises it.
 *
 * Which template a form holds is READ off the form — its instruction is the
 * template's — so an instruction edited by hand is no template any more, and
 * going back to « no template » empties only what a template filled.
 */

import type { ConditionType, RecurrenceSpec, TriggerKind } from '@/hooks/useScheduledActions';
import { emptyRecurrence } from '@/lib/recurrence';

export const ROUTINE_TEMPLATE_KEYS = [
  'morning_briefing',
  'inbox_triage',
  'weekly_review',
  'overdue_tasks',
] as const;

export type RoutineTemplateKey = (typeof ROUTINE_TEMPLATE_KEYS)[number];

/** The fields of the create form a template sets. */
export interface RoutineTemplateFields {
  title: string;
  action_prompt: string;
  trigger_kind: TriggerKind;
  recurrence: RecurrenceSpec;
  condition_type: ConditionType;
  condition_query: string;
  /** A watched page's address (ADR-387); '' for every other condition. */
  condition_url: string;
  condition_until: string;
  requires_approval: boolean;
  notify_only_when_new: boolean;
}

type Translate = (key: string) => string;

/** ISO weekdays, 1 = Monday … 7 = Sunday. */
const WEEKDAYS = [1, 2, 3, 4, 5];
const SUNDAY = 7;

/** The form's template fields when nothing was chosen: a daily routine from today. */
export function blankRoutineFields(today: string): RoutineTemplateFields {
  return {
    title: '',
    action_prompt: '',
    trigger_kind: 'time',
    recurrence: emptyRecurrence(today),
    condition_type: 'task_overdue',
    condition_query: '',
    condition_url: '',
    condition_until: '',
    requires_approval: false,
    notify_only_when_new: false,
  };
}

function at(hour: number, minute: number): RecurrenceSpec['times'] {
  return { mode: 'at', at: [{ hour, minute }] };
}

/** What each template sets beside its words. */
function clockOf(key: RoutineTemplateKey, today: string): Partial<RoutineTemplateFields> {
  const daily = emptyRecurrence(today);
  switch (key) {
    case 'morning_briefing':
      return { recurrence: { ...daily, times: at(7, 30) } };
    case 'inbox_triage':
      return {
        recurrence: { ...daily, freq: 'weekly', byweekday: WEEKDAYS, times: at(8, 0) },
        // Quiet unless something needs the person; never with asking first.
        notify_only_when_new: true,
      };
    case 'weekly_review':
      return { recurrence: { ...daily, freq: 'weekly', byweekday: [SUNDAY], times: at(18, 0) } };
    case 'overdue_tasks':
      return { trigger_kind: 'condition', condition_type: 'task_overdue' };
  }
}

/** The form once a template is chosen: its words and its clock, the rest kept. */
export function applyRoutineTemplate<F extends RoutineTemplateFields>(
  form: F,
  key: RoutineTemplateKey,
  today: string,
  t: Translate
): F {
  return {
    ...form,
    ...blankRoutineFields(today),
    title: t(`scheduled_actions.templates.${key}.title`),
    action_prompt: t(`scheduled_actions.templates.${key}.prompt`),
    ...clockOf(key, today),
  };
}

/** The template whose instruction the form holds, if it still holds one. */
export function routineTemplateOf(
  form: Pick<RoutineTemplateFields, 'action_prompt'>,
  t: Translate
): RoutineTemplateKey | null {
  return (
    ROUTINE_TEMPLATE_KEYS.find(
      key => form.action_prompt === t(`scheduled_actions.templates.${key}.prompt`)
    ) ?? null
  );
}

/** The form once « no template » is chosen: what a template filled is emptied. */
export function clearRoutineTemplate<F extends RoutineTemplateFields>(
  form: F,
  today: string,
  t: Translate
): F {
  if (routineTemplateOf(form, t) === null) return form;
  return { ...form, ...blankRoutineFields(today) };
}
