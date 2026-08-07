'use client';

/**
 * The showroom honesty contract, always visible: guided demonstration,
 * synthetic data, no external action. Rendered on the mission picker AND
 * inside every mission header — a visitor never sees showroom content
 * without these three statements on screen.
 *
 * Presented as a panel of three list items rather than one grey sentence
 * (owner request 2026-08-07: "trop condensé et peu lisible"). The previous
 * single line ran the three facts together with `·` separators and wrapped
 * mid-sentence on a phone, so the most important promise of the page — no
 * external action is ever sent — read as trailing decoration.
 *
 * Three consequences, all deliberate:
 *  - a LIST, so assistive technology announces three facts, not one run-on
 *    sentence, and the `·` glyphs that only ever meant "line break here"
 *    disappear;
 *  - one column on phones, three side by side from `sm` up, which is what
 *    stops a statement from breaking across lines;
 *  - the leading glyphs stay MUTED: they sit inside muted text and are not
 *    title icons (apps/web CLAUDE.md — "metadata glyphs inside muted text
 *    lines are not titles and keep their line's colour").
 */

import { FlaskConical, Info, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/** Distinct shapes: recognisable at a glance even without colour. */
const STATEMENTS = [
  { key: 'showroom.honesty.guided', Icon: Info },
  { key: 'showroom.honesty.synthetic', Icon: FlaskConical },
  { key: 'showroom.honesty.no_external', Icon: ShieldCheck },
] as const;

export function HonestyStrip() {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-border/60 bg-muted/30 px-3.5 py-3">
      <ul
        aria-label={t('showroom.honesty.title')}
        className="grid gap-2.5 text-xs leading-relaxed text-muted-foreground sm:grid-cols-3 sm:gap-x-4"
      >
        {STATEMENTS.map(({ key, Icon }) => (
          <li key={key} className="flex items-start gap-2">
            <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>{t(key)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
