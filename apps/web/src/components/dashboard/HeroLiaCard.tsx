'use client';

import { ArrowRight, Plug, Sparkles, Zap } from 'lucide-react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { useLiaGender } from '@/hooks/useLiaGender';

/**
 * Marketing hero card with the LIA avatar — preserved from the previous
 * dashboard ("Puissant par nature. Privé par principe.") and now sits
 * between the synthesis and the cards grid.
 *
 * Click anywhere on the image (outside the CTA buttons) toggles the LIA gender
 * via useLiaGender — same behavior as before the refactor.
 */
export function HeroLiaCard() {
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lng = (i18n.language || 'fr').split('-')[0];
  const { liaImage, toggleGender: toggleLiaGender } = useLiaGender();

  const tagline = useMemo(() => {
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

  return (
    <Card
      variant="elevated"
      className="w-full border-0 overflow-hidden relative rounded-xl h-[420px] sm:h-[530px] cursor-pointer"
      onClick={toggleLiaGender}
    >
      <Image src={liaImage} alt="LIA" fill className="object-cover" priority />
      <div className="absolute inset-0 bg-gradient-to-t from-background via-background/30 to-background/60" />
      <CardContent className="flex flex-col items-center justify-between h-[420px] sm:h-[530px] py-6 px-6 relative z-10">
        <div className="text-center">
          <p
            className="text-xl sm:text-2xl font-semibold text-foreground/90 leading-relaxed max-w-md drop-shadow-sm"
            dangerouslySetInnerHTML={{ __html: tagline }}
          />
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
