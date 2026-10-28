'use client';

import { useEffect, useId, useState } from 'react';
import { LoaderCircle, Minus, Plus, Sparkles, Square, Volume2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import { UpdatedAtBadge } from './UpdatedAtBadge';
import { useBriefingAudio } from '@/hooks/useBriefingAudio';
import { useFlashOnChange } from '@/hooks/useFlashOnChange';
import { useLiaGender } from '@/hooks/useLiaGender';
import type { TextSection } from '@/types/briefing';

interface BriefingSynthesisProps {
  synthesis: TextSection;
}

const JUST_UPDATED_VISIBLE_MS = 1500;

/** Readable point with independent audio/fold controls and its real generation cost. */
export function BriefingSynthesis({ synthesis }: BriefingSynthesisProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const contentId = useId();
  const titleId = useId();
  // « Just updated » for a moment after a NEW synthesis replaced the one shown.
  const showJustUpdated = useFlashOnChange(synthesis.generated_at, JUST_UPDATED_VISIBLE_MS);
  // A2: read the displayed synthesis aloud (server-side TTS, cost-tracked).
  const { playing, loading, error, toggle } = useBriefingAudio();
  const { isMale: liaIsMale } = useLiaGender();

  useEffect(() => {
    if (error) toast.error(t('dashboard.briefing.synthesis_audio_error'));
  }, [error, t]);

  return (
    <section aria-labelledby={titleId} className="min-w-0 space-y-2">
      <div className="grid grid-cols-[minmax(0,1fr)_44px_44px] items-center gap-1">
        <h3 id={titleId} className="flex min-w-0 items-center gap-2 text-sm font-semibold">
          <Sparkles className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          {t('dashboard.briefing.synthesis_title')}
        </h3>
        <Button
          variant="ghost"
          size="icon"
          className="h-11 w-11 justify-self-center text-primary"
          aria-disabled={loading}
          aria-busy={loading}
          aria-label={t(
            playing ? 'dashboard.briefing.synthesis_stop' : 'dashboard.briefing.synthesis_listen'
          )}
          aria-pressed={playing}
          onClick={() => {
            if (!loading) void toggle(synthesis.text, liaIsMale ? 'male' : 'female');
          }}
        >
          {loading ? (
            <LoaderCircle className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          ) : playing ? (
            <Square className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Volume2 className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-11 w-11 text-primary"
          aria-label={t(
            expanded
              ? 'dashboard.briefing.synthesis_collapse'
              : 'dashboard.briefing.synthesis_expand'
          )}
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded(value => !value)}
        >
          {expanded ? <Minus aria-hidden="true" /> : <Plus aria-hidden="true" />}
        </Button>
      </div>
      {/* Folding the text keeps its single audio owner and controls mounted. */}
      <p
        id={contentId}
        hidden={!expanded}
        className="break-words text-sm leading-relaxed text-foreground/90 sm:text-base"
      >
        {synthesis.text}
      </p>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <UpdatedAtBadge generatedAt={synthesis.generated_at} showJustUpdated={showJustUpdated} />
        {synthesis.usage && <LLMUsageBadge usage={synthesis.usage} />}
      </div>
    </section>
  );
}
