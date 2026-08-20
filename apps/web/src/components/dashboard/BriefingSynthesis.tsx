'use client';

import { useEffect, useRef, useState } from 'react';
import { Square, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { LLMUsageBadge } from './LLMUsageBadge';
import { UpdatedAtBadge } from './UpdatedAtBadge';
import { useBriefingAudio } from '@/hooks/useBriefingAudio';
import { useLiaGender } from '@/hooks/useLiaGender';
import type { TextSection } from '@/types/briefing';

interface BriefingSynthesisProps {
  synthesis: TextSection;
}

const JUST_UPDATED_VISIBLE_MS = 1500;

/**
 * AI-generated 2-3 sentence synthesis — sits below the greeting.
 *
 * Iconless, sober design:
 *  - Glass-morphism background with subtle primary gradient
 *  - Left accent bar (primary, vertical gradient) — gives LIA "voice"
 *  - Decorative blur orb top-right (primary, 15% opacity)
 *  - Detects `generated_at` change to flash a "mis à jour ✨" badge for 1.5 s
 */
export function BriefingSynthesis({ synthesis }: BriefingSynthesisProps) {
  const { t } = useTranslation();
  const [showJustUpdated, setShowJustUpdated] = useState(false);
  const previousGeneratedAt = useRef<string | null>(null);
  // A2: read the displayed synthesis aloud (server-side TTS, cost-tracked).
  const { playing, loading, error, toggle } = useBriefingAudio();
  const { isMale: liaIsMale } = useLiaGender();

  useEffect(() => {
    if (error) toast.error(t('dashboard.briefing.synthesis_audio_error'));
  }, [error, t]);

  useEffect(() => {
    if (previousGeneratedAt.current === null) {
      previousGeneratedAt.current = synthesis.generated_at;
      return;
    }
    if (previousGeneratedAt.current !== synthesis.generated_at) {
      previousGeneratedAt.current = synthesis.generated_at;
      setShowJustUpdated(true);
      const id = setTimeout(() => setShowJustUpdated(false), JUST_UPDATED_VISIBLE_MS);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [synthesis.generated_at]);

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-2xl border border-primary/15',
        'bg-gradient-to-br from-primary/8 via-card/80 to-card backdrop-blur-md',
        'shadow-[var(--lia-shadow-lg)]',
        'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-500'
      )}
    >
      {/* Left accent bar — vertical primary gradient */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-primary via-primary/60 to-primary/30"
        aria-hidden="true"
      />
      {/* Decorative blur orb */}
      <div
        className="pointer-events-none absolute -top-10 -right-10 h-40 w-40 rounded-full bg-primary/15 blur-3xl"
        aria-hidden="true"
      />

      <div className="relative p-5 sm:p-6">
        <p
          className="text-[15px] sm:text-base leading-relaxed text-foreground/90"
          style={{ textWrap: 'pretty' } as React.CSSProperties}
        >
          {synthesis.text}
        </p>
        <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1 pt-3">
          {/* Row-level altitude (ADR-207): a ghost icon control on the badge
              line — listening is an accessory to reading, not a section CTA. */}
          <Button
            variant="ghost"
            size="icon"
            isLoading={loading}
            aria-label={t(playing ? 'dashboard.briefing.synthesis_stop' : 'dashboard.briefing.synthesis_listen')}
            aria-pressed={playing}
            onClick={() => void toggle(synthesis.text, liaIsMale ? 'male' : 'female')}
          >
            {playing ? (
              <Square className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Volume2 className="h-4 w-4" aria-hidden="true" />
            )}
          </Button>
          <UpdatedAtBadge generatedAt={synthesis.generated_at} showJustUpdated={showJustUpdated} />
          {synthesis.usage && <LLMUsageBadge usage={synthesis.usage} />}
        </div>
      </div>
    </div>
  );
}
