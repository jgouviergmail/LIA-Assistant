'use client';

import { ArrowRight, Plug, Sparkles, Zap } from 'lucide-react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
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
 *  - When the briefing greeting is available, it is rendered above the CTA
 *    buttons (with the LLMUsageBadge for tokens + cost).
 *  - While the LLM call is in flight, a discreet "refreshing" label is
 *    shown — no fallback marketing tagline (deliberate: the user wants
 *    the area empty until the personalized greeting arrives, not a
 *    rotating placeholder).
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

  const headlineText = greeting?.text ?? '';
  const usingGreeting = Boolean(greeting?.text);

  return (
    <Card
      variant="elevated"
      className="w-full border-0 overflow-hidden relative rounded-xl h-[420px] sm:h-[530px] cursor-pointer"
      onClick={toggleLiaGender}
    >
      <Image src={liaImage} alt="LIA" fill className="object-cover" priority />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-background/60" />
      <CardContent className="flex flex-col items-center justify-end gap-12 h-[420px] sm:h-[530px] py-6 px-6 relative z-10">
        {/* Greeting sits directly above the CTA buttons (no top spacer) so
            the LIA avatar fills the upper half of the card. Rendered only
            when the LLM greeting has arrived — no fallback tagline is
            shown while the call is in flight (deliberate: user prefers
            an empty area to a rotating placeholder). */}
        <div className="text-center flex flex-col items-center gap-2 max-w-md">
          {usingGreeting ? (
            <>
              <p
                key={headlineText}
                className="text-xl sm:text-2xl font-semibold text-foreground/90 leading-relaxed drop-shadow-sm motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-500"
                style={{ textWrap: 'balance' } as React.CSSProperties}
                dangerouslySetInnerHTML={{ __html: headlineText }}
              />
              {greeting?.usage && (
                <LLMUsageBadge
                  usage={greeting.usage}
                  className="motion-safe:animate-in motion-safe:fade-in motion-safe:duration-700 motion-safe:[animation-delay:200ms]"
                />
              )}
            </>
          ) : isLoadingGreeting ? (
            <span
              className="text-[10px] uppercase tracking-wider text-muted-foreground/60"
              aria-live="polite"
            >
              {t('dashboard.briefing.refreshing')}
            </span>
          ) : null}
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
