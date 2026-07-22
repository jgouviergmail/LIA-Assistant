'use client';

/**
 * PortraitHint — "I refined my understanding of you" dashboard line (QW-10).
 *
 * A discreet row under the hero, shown when the compiled portrait was
 * refreshed within `PORTRAIT_HINT_RECENT_DAYS` and the user has not seen or
 * dismissed THAT compilation yet (localStorage keyed by `compiled_at`, so a
 * newer compilation re-surfaces the hint). Clicking opens the portrait in
 * the settings via the `?section=journals` deep link; dismissing remembers
 * the compilation without navigating.
 */

import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';

import { useAppConfig } from '@/hooks/useAppConfig';
import { useJournalPortrait } from '@/hooks/useJournalPortrait';
import { PORTRAIT_HINT_RECENT_DAYS, PORTRAIT_HINT_STORAGE_KEY } from '@/lib/constants';

function readSeenCompiledAt(): string | null {
  try {
    return window.localStorage.getItem(PORTRAIT_HINT_STORAGE_KEY);
  } catch {
    return null;
  }
}

function rememberCompiledAt(compiledAt: string): void {
  try {
    window.localStorage.setItem(PORTRAIT_HINT_STORAGE_KEY, compiledAt);
  } catch {
    // Storage unavailable (private mode) — the hint simply reappears.
  }
}

/** Pure visibility rule — exported for direct testing. */
export function isPortraitHintVisible(
  compiledAt: string | null | undefined,
  seenCompiledAt: string | null,
  now: Date
): boolean {
  if (!compiledAt) return false;
  if (seenCompiledAt === compiledAt) return false;
  const ageMs = now.getTime() - new Date(compiledAt).getTime();
  return ageMs >= 0 && ageMs <= PORTRAIT_HINT_RECENT_DAYS * 24 * 60 * 60 * 1000;
}

export function PortraitHint() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const { config } = useAppConfig(true);
  const journalsEnabled = config?.features?.journals_enabled ?? false;
  const { portrait } = useJournalPortrait(journalsEnabled);
  const [dismissed, setDismissed] = useState(false);

  const compiledAt = portrait?.compiled_at ?? null;
  if (dismissed || !isPortraitHintVisible(compiledAt, readSeenCompiledAt(), new Date())) {
    return null;
  }

  const markSeen = () => {
    if (compiledAt) rememberCompiledAt(compiledAt);
    setDismissed(true);
  };

  return (
    <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
      <Sparkles className="h-4 w-4 shrink-0 text-primary/70" aria-hidden />
      <span>{t('dashboard.portrait_hint.text')}</span>
      <button
        type="button"
        onClick={() => {
          markSeen();
          router.push(`/${lng}/dashboard/settings?section=journals`);
        }}
        className="font-semibold text-primary hover:text-primary/80 underline decoration-primary/40 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t('dashboard.portrait_hint.cta')}
      </button>
      <button
        type="button"
        onClick={markSeen}
        aria-label={t('dashboard.portrait_hint.dismiss')}
        className="p-1 rounded-full hover:bg-muted"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
