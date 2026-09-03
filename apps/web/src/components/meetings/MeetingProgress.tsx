'use client';

/**
 * The four processing stages as a progress list (ADR-258).
 *
 * The server publishes ONE stage at a time; earlier stages are shown done,
 * later ones pending. A `stopped` meeting (queued, nobody claimed it yet) shows
 * every stage pending with a spinner on the first.
 */

import { Check, Loader2 } from 'lucide-react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import type { MeetingStage, MeetingStatus } from '@/types/meetings';

const STAGES: readonly MeetingStage[] = ['normalizing', 'transcribing', 'synthesizing', 'indexing'];

interface MeetingProgressProps {
  lng: Language;
  status: MeetingStatus;
  stage: MeetingStage | null;
}

export function MeetingProgress({ lng, status, stage }: MeetingProgressProps) {
  const { t } = useTranslation(lng);
  const current = stage ? STAGES.indexOf(stage) : status === 'ready' ? STAGES.length : 0;
  return (
    <ol className="space-y-1.5" aria-label={t('meetings.detail.progress_title')}>
      {STAGES.map((item, index) => {
        const done = index < current || status === 'ready';
        const active = !done && index === current && status !== 'failed';
        return (
          <li
            key={item}
            className={cn(
              'flex items-center gap-2 text-sm',
              done ? 'text-foreground' : active ? 'text-primary' : 'text-muted-foreground'
            )}
            aria-current={active ? 'step' : undefined}
          >
            {done ? (
              <Check className="h-4 w-4 text-success" aria-hidden="true" />
            ) : active ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <span
                className="inline-block h-4 w-4 rounded-full border border-current/40"
                aria-hidden="true"
              />
            )}
            {t(`meetings.stage.${item}`)}
          </li>
        );
      })}
    </ol>
  );
}
