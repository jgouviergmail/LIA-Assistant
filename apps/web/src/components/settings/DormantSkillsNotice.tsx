'use client';

/**
 * DormantSkillsNotice — the proposal to switch off the skills nobody uses (lot 14).
 *
 * A skill left on and unused still enters the skills LIA weighs for every
 * message. The server decides which ones sleep (`dormant`: on, observable,
 * unused or unkept for `days`); this panel names them and asks. Both answers
 * go to ONE door: « switch them off », or « keep them » — the proposal then
 * waits a whole period again, on every device, so declining is never a nag.
 *
 * A busy answer stays focused and inert (`aria-disabled` plus a guard): a
 * `disabled` button would drop the keyboard user back on the page.
 */

import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Hourglass } from '@/lib/icons';
import type { DormantDecision, Skill } from '@/hooks/useSkills';
import type { SkillLifeTranslator } from '@/lib/skill-life';

export function DormantSkillsNotice({
  skills,
  days,
  t,
  busy,
  onDecide,
}: {
  /** The skills proposed (see `dormantSkills`). */
  skills: Skill[];
  /** `SKILLS_DORMANT_AFTER_DAYS`, as the server measured with; absent from an older API. */
  days: number | undefined;
  t: SkillLifeTranslator;
  busy: boolean;
  onDecide: (decision: DormantDecision) => void;
}) {
  const headingId = useId();
  if (skills.length === 0 || days === undefined) return null;
  const count = skills.length;
  const answer = (decision: DormantDecision) => () => {
    if (!busy) onDecide(decision);
  };
  return (
    <section
      aria-labelledby={headingId}
      aria-busy={busy || undefined}
      className="space-y-2 rounded-lg border bg-card p-3"
    >
      <h3 id={headingId} className="flex items-center gap-2 text-sm font-medium">
        <Hourglass className="h-4 w-4 shrink-0 text-primary" aria-hidden />
        {t('settings.skills.dormant.title')}
      </h3>
      <p className="text-sm text-muted-foreground">
        {t('settings.skills.dormant.description', { count, days })}
      </p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
        {skills.map(skill => (
          <li key={skill.name} className="font-medium">
            {skill.name}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="sm" aria-disabled={busy || undefined} onClick={answer('switch_off')}>
          {t('settings.skills.dormant.switch_off', { count })}
        </Button>
        <Button
          size="sm"
          variant="outline"
          aria-disabled={busy || undefined}
          onClick={answer('keep')}
        >
          {t('settings.skills.dormant.keep', { count })}
        </Button>
      </div>
    </section>
  );
}
