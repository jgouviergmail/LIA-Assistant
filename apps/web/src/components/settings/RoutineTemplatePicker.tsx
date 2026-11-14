'use client';

import { useId, type Dispatch, type SetStateAction } from 'react';
import type { TFunction } from 'i18next';

import { NativeSelect } from '@/components/ui/native-select';
import {
  ROUTINE_TEMPLATE_KEYS,
  applyRoutineTemplate,
  clearRoutineTemplate,
  routineTemplateOf,
  type RoutineTemplateFields,
  type RoutineTemplateKey,
} from '@/lib/routine-templates';

interface Props<F extends RoutineTemplateFields> {
  /** False where a routine is edited or duplicated: a template starts a NEW one. */
  offered: boolean;
  form: F;
  setForm: Dispatch<SetStateAction<F>>;
  /** The reader's today, `YYYY-MM-DD`: a template's schedule starts there. */
  today: string;
  t: TFunction;
}

function isTemplateKey(value: string): value is RoutineTemplateKey {
  return (ROUTINE_TEMPLATE_KEYS as readonly string[]).includes(value);
}

/**
 * The ready-made routines of the create form (lot 13): one choice fills its
 * words, its clock and its delivery; nothing is scheduled until it is saved.
 *
 * It holds no state of its own: the template picked is READ off the form (its
 * instruction), so an instruction edited by hand is no template any more. What
 * the list is for, then what the routine picked does, is ONE line under it:
 * attached as its description and announced when it changes, the focus staying
 * on the list.
 */
export function RoutineTemplatePicker<F extends RoutineTemplateFields>({
  offered,
  form,
  setForm,
  today,
  t,
}: Props<F>) {
  const descriptionId = useId();
  if (!offered) return null;
  const picked = routineTemplateOf(form, t);
  return (
    <div className="space-y-3">
      <NativeSelect
        label={t('scheduled_actions.templates.label')}
        value={picked ?? ''}
        aria-describedby={descriptionId}
        onChange={event => {
          const chosen = event.target.value;
          setForm(current =>
            isTemplateKey(chosen)
              ? applyRoutineTemplate(current, chosen, today, t)
              : clearRoutineTemplate(current, today, t)
          );
        }}
      >
        <option value="">{t('scheduled_actions.templates.none')}</option>
        {ROUTINE_TEMPLATE_KEYS.map(key => (
          <option key={key} value={key}>
            {t(`scheduled_actions.templates.${key}.title`)}
          </option>
        ))}
      </NativeSelect>
      <p id={descriptionId} aria-live="polite" className="text-xs text-muted-foreground">
        {t(
          picked
            ? `scheduled_actions.templates.${picked}.description`
            : 'scheduled_actions.templates.hint'
        )}
      </p>
    </div>
  );
}
