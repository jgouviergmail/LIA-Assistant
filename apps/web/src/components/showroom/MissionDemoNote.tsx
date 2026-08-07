'use client';

/**
 * The pedagogical bubble — deliberately SEPARATE from LIA's reply.
 *
 * The rich reply above it speaks as the assistant would in a real exchange
 * (task tone, no product talk); this bubble is the demo narrator explaining
 * what mechanism the visitor just saw and where it lives in the product.
 * Mixing the two voices in one block made the reply read like marketing —
 * owner arbitration 2026-08-06. Visually distinct on purpose: dashed
 * border, muted tone, a graduation-cap glyph, and an explicit label.
 */

import { GraduationCap } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface MissionDemoNoteProps {
  noteKey: string;
}

export function MissionDemoNote({ noteKey }: MissionDemoNoteProps) {
  const { t } = useTranslation();
  return (
    <aside
      aria-label={t('showroom.note.label')}
      data-testid="showroom-demo-note"
      className="rounded-2xl border border-dashed border-border/80 bg-muted/30 p-4"
    >
      <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <GraduationCap className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('showroom.note.label')}
      </p>
      <p className="mt-1.5 text-sm text-muted-foreground">{t(noteKey)}</p>
    </aside>
  );
}
