'use client';

/**
 * PerformedEffects — what the turn actually DID, under the assistant bubble
 * (ADR-263).
 *
 * Deliberately NOT a disclosure like the ⚙ execution trace. A step is backstage
 * detail; an effect is a claim about the world — an email that left, a light
 * that switched — and a claim the user has to expand to see is a claim they
 * will miss. It renders as a short, always-visible list, and only when the
 * register recorded something: a pure-conversation turn shows nothing at all.
 *
 * The wording is resolved HERE from `label_key` + `values`, so a message
 * archived while the interface was in French reads in German after a switch.
 * A key with no translation renders nothing rather than its own name.
 */

import { CheckCircle2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { PerformedEffect } from '@/types/performed-effects';

export interface PerformedEffectsProps {
  effects?: PerformedEffect[];
}

export function PerformedEffects({ effects }: PerformedEffectsProps) {
  const { t } = useTranslation();

  if (!effects || effects.length === 0) return null;

  const lines = effects
    .map(effect => ({
      effect,
      label: t(effect.labelKey, { ...effect.values, defaultValue: '' }),
    }))
    .filter(line => line.label);

  if (lines.length === 0) return null;

  return (
    <section
      className="w-full mt-1 rounded-md border border-border/40 bg-muted/20 px-3 py-2"
      aria-label={t('chat.effects.title')}
    >
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('chat.effects.title')}
      </p>
      <ul className="mt-1 space-y-0.5">
        {lines.map(({ effect, label }, index) => {
          const failed = effect.status === 'failed';
          const Icon = failed ? XCircle : CheckCircle2;
          return (
            <li
              key={`${effect.labelKey}-${index}`}
              className={cn(
                'flex items-start gap-1.5 text-xs',
                failed ? 'text-destructive' : 'text-foreground/80'
              )}
            >
              <Icon className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
              {/* `min-w-0` + `break-words`: a value comes from a third party
                  (a subject, an address) and a long unbroken one would push
                  the bubble sideways on a phone. */}
              <span className="min-w-0 break-words">
                {label}
                {failed && (
                  <span className="ml-1 text-[10px] uppercase tracking-wide">
                    {t('chat.effects.failed')}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
