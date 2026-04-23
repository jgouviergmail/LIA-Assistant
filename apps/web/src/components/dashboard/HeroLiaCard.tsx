'use client';

import { ArrowRight, Plug, Sparkles, Zap } from 'lucide-react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useLiaGender } from '@/hooks/useLiaGender';
import { LLMUsageBadge } from './LLMUsageBadge';
import type { TextSection } from '@/types/briefing';

interface HeroLiaCardProps {
  /** LLM-generated greeting from the briefing — preferred over random taglines. */
  greeting?: TextSection | null;
  /** When true, the briefing greeting is still loading (shows a placeholder). */
  isLoadingGreeting?: boolean;
}

/**
 * Marketing hero card with the LIA avatar — preserved from the previous
 * dashboard and now sits between the Quick Access and the cards grid.
 *
 * Headline:
 *  - When the briefing greeting is available, it replaces the rotating
 *    random taglines (one personalized sentence per page load instead of
 *    a generic marketing line).
 *  - During the LLM call, a static fallback tagline is shown so the area
 *    is never empty.
 *  - The LLMUsageBadge surfaces tokens + cost just below the greeting,
 *    consistent with the inline badge used elsewhere on the dashboard.
 *
 * Click anywhere on the image (outside the CTA buttons) toggles the LIA gender
 * via useLiaGender — same behavior as before the refactor.
 */
export function HeroLiaCard({
  greeting = null,
  isLoadingGreeting = false,
}: HeroLiaCardProps = {}) {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const { liaImage, toggleGender: toggleLiaGender } = useLiaGender();

  // Static fallback tagline — only shown while the LLM greeting is in flight
  // (or when no greeting is provided at all). The random pick stays stable
  // for the lifetime of the component so it doesn't flicker on re-render.
  const fallbackTagline = useMemo(() => {
    const taglines = t('dashboard.welcome_banner.taglines', {
      returnObjects: true,
    }) as string[];
    if (Array.isArray(taglines) && taglines.length > 0) {
      const randomIndex = Math.floor(Math.random() * taglines.length);
      return taglines[randomIndex];
    }
    return '';
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lng]);

  const headlineText = greeting?.text ?? fallbackTagline;
  const usingGreeting = Boolean(greeting?.text);

  return (
    <Card
      variant="elevated"
      className="w-full border-0 overflow-hidden relative rounded-xl h-[420px] sm:h-[530px] cursor-pointer"
      onClick={toggleLiaGender}
    >
      <Image src={liaImage} alt="LIA" fill className="object-cover" priority />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-background/60" />
      <CardContent className="flex flex-col items-center justify-between h-[420px] sm:h-[530px] py-6 px-6 relative z-10">
        <div className="text-center flex flex-col items-center gap-2 max-w-md">
          <p
            key={headlineText}
            className="text-xl sm:text-2xl font-semibold text-foreground/90 leading-relaxed drop-shadow-sm motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-500"
            style={{ textWrap: 'balance' } as React.CSSProperties}
            dangerouslySetInnerHTML={{ __html: headlineText }}
          />
          {usingGreeting && greeting?.usage && (
            <LLMUsageBadge
              usage={greeting.usage}
              className="motion-safe:animate-in motion-safe:fade-in motion-safe:duration-700 motion-safe:[animation-delay:200ms]"
            />
          )}
          {!usingGreeting && isLoadingGreeting && (
            <span
              className="text-[10px] uppercase tracking-wider text-muted-foreground/60"
              aria-live="polite"
            >
              {t('dashboard.briefing.refreshing')}
            </span>
          )}
        </div>

        <div
          className="flex flex-col items-center gap-3 w-[250px]"
          onClick={e => e.stopPropagation()}
        >
          <Button
            onClick={() => router.push(`/${lng}/dashboard/settings?section=connectors`)}
            variant="default"
            size="lg"
            className="w-full"
          >
            <Plug className="h-5 w-5" />
            {t('dashboard.actions.connect')}
          </Button>
          <Button
            onClick={() => router.push(`/${lng}/dashboard/chat`)}
            variant="default"
            size="lg"
            className="w-full"
          >
            <Sparkles className="h-5 w-5" />
            {t('dashboard.actions.open_chat')}
            <ArrowRight className="h-4 w-4" />
          </Button>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Zap className="h-3.5 w-3.5 text-warning" />
            <span>{t('dashboard.main_feature.powered_by')}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
