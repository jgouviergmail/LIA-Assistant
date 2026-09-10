'use client';
/**
 * How LIA runs a ticket, chosen per ticket (ADR-276).
 *
 * The two options carry the header toggle's own names — « Mode ReAct »,
 * « Mode Pipeline » — and its own marks (lot 21, D81), and nothing else: the
 * owner asked for the choice without a paragraph under it (2026-09-09). The
 * loop stays the default because a ticket is a multi-step task with nobody
 * there to steer a plan; the pipeline stays offered because it is four to
 * eight times cheaper in tokens.
 *
 * One component for the creation form, the detail panel and the routines: the
 * choice is the same choice, and a ticket engaged for days is exactly when a
 * person changes their mind about it.
 */
import { useTranslation } from 'react-i18next';

import { GlyphSelect } from '@/components/workboard/GlyphSelect';
import { modeIcon } from '@/lib/workboard/icons';
import { EXECUTION_MODES, type ExecutionMode } from '@/types/workboard';

export interface ExecutionModeFieldProps {
  /** Id of the control, so its label points at it. */
  id: string;
  value: ExecutionMode;
  onChange: (mode: ExecutionMode) => void;
}

const GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

export function ExecutionModeField({ id, value, onChange }: ExecutionModeFieldProps) {
  const { t } = useTranslation();
  const items = EXECUTION_MODES.map(mode => ({
    value: mode,
    glyph: modeIcon(mode, GLYPH),
    text: t(`workboard.execution_mode.${mode}`),
  }));

  return (
    <div className="space-y-2">
      <GlyphSelect
        id={id}
        hideLabel={false}
        label={t('workboard.form.execution_mode')}
        value={value}
        items={items}
        className="h-10 px-3 text-sm"
        onChange={chosen => {
          // The list only ever offers the two modes; narrowing by lookup keeps
          // the type honest without a cast.
          const mode = EXECUTION_MODES.find(candidate => candidate === chosen);
          if (mode) onChange(mode);
        }}
      />
    </div>
  );
}
