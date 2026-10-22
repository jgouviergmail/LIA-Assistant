'use client';

import type { ReactNode } from 'react';
import { ArrowRight, Plug, Sparkles } from 'lucide-react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useLiaGender } from '@/hooks/useLiaGender';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';
import { LLMUsageBadge } from '@/components/ui/llm-usage-badge';
import type { TextSection } from '@/types/briefing';

// Reuse the native miniature without eagerly adding the facial rig to the
// dashboard bundle. It already suspends offscreen and honors reduced motion.
const SelectedCompanionPortrait = dynamic(
  () =>
    import('@/components/psyche/SelectedCompanionPortrait').then(
      module => module.SelectedCompanionPortrait
    ),
  { ssr: false }
);

interface HeroLiaCardProps {
  greeting?: TextSection | null;
  isLoadingGreeting?: boolean;
  /** The existing synthesis owner stays mounted across greeting refreshes. */
  children?: ReactNode;
}

/** Compact welcome: real greeting and costs, portrait choices, then navigation. */
export function HeroLiaCard({
  greeting = null,
  isLoadingGreeting = false,
  children,
}: HeroLiaCardProps = {}) {
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const { isMale, mounted, setGender } = useLiaGender();
  const styleId = useEyesWidgetStore(state => state.style);
  const currentVariant = isMale ? 'male' : 'female';
  const oppositeVariant = isMale ? 'female' : 'male';

  return (
    <Card className="group relative min-w-0 overflow-hidden rounded-2xl border-primary/15 bg-card shadow-sm">
      <CardContent className="p-4 sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3 sm:gap-4">
            <div
              role="group"
              aria-label={t('dashboard.avatar_picker.group_label')}
              className="flex shrink-0 flex-col items-center gap-1.5"
            >
              <div
                role="img"
                aria-label={t(`dashboard.avatar_picker.${currentVariant}`)}
                className="relative flex h-14 w-14 items-center justify-center sm:h-16 sm:w-16"
              >
                <span className="inline-flex scale-[1.4]">
                  <SelectedCompanionPortrait
                    styleId={styleId}
                    variant={currentVariant}
                    expression="neutral"
                    animate={mounted}
                  />
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (mounted) setGender(!isMale);
                }}
                aria-disabled={!mounted || undefined}
                aria-label={t(`dashboard.avatar_picker.${oppositeVariant}`)}
                title={t(`dashboard.avatar_picker.${oppositeVariant}`)}
                className="relative flex h-11 w-11 items-center justify-center rounded-full transition-colors hover:bg-primary/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {/* The opposite identity is a still preview, sharing the current
                    skin without running a second facial animation clock. */}
                <span className="pointer-events-none inline-flex scale-[0.7]">
                  <SelectedCompanionPortrait
                    styleId={styleId}
                    variant={oppositeVariant}
                    expression="neutral"
                    animate={false}
                  />
                </span>
              </button>
            </div>
            <div className="min-w-0 flex-1 basis-40 space-y-2">
              {greeting?.text ? (
                <>
                  {/* LLM output is plain React text, including hostile source titles. */}
                  <p className="break-words text-base font-semibold leading-relaxed text-foreground sm:text-lg">
                    {greeting.text}
                  </p>
                  {greeting.usage && <LLMUsageBadge usage={greeting.usage} />}
                </>
              ) : isLoadingGreeting ? (
                <p className="text-sm text-muted-foreground" role="status">
                  {t('dashboard.briefing.refreshing')}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex w-full shrink-0 flex-col gap-2 lg:w-48">
            <Button asChild className="h-auto min-h-11 whitespace-normal px-3 py-2">
              <Link href={`/${lng}/dashboard/chat`}>
                <Sparkles aria-hidden="true" />
                {t('dashboard.actions.open_chat')}
                <ArrowRight aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild className="h-auto min-h-11 whitespace-normal px-3 py-2">
              <Link href={`/${lng}/dashboard/settings?section=connectors`}>
                <Plug aria-hidden="true" />
                {t('dashboard.actions.services')}
              </Link>
            </Button>
          </div>
        </div>
        {children && <div className="mt-4 border-t border-border pt-4">{children}</div>}
      </CardContent>
    </Card>
  );
}
