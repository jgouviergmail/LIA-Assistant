import Link from 'next/link';
import { initI18next } from '@/i18n';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import type { Language } from '@/i18n/settings';

interface CtaSectionProps {
  lng: string;
}

export async function CtaSection({ lng }: CtaSectionProps) {
  const { t } = await initI18next(lng);
  const registerHref = buildLocalizedPath('/register', lng as Language);

  return (
    <section className="relative py-24 overflow-hidden">
      {/* Gradient background */}
      <div
        className="absolute inset-0 bg-gradient-to-br from-[#2563eb] via-[#5b3fce] to-[#7c3aed] opacity-90"
        aria-hidden="true"
      />

      {/* Subtle constellation overlay */}
      <div className="absolute inset-0 opacity-10" aria-hidden="true">
        <svg className="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
          {[
            [10, 8], [25, 15], [40, 5], [55, 20], [70, 10], [85, 18],
            [15, 30], [35, 35], [50, 25], [65, 32], [80, 28], [95, 35],
          ].map(([cx, cy], i) => (
            <circle key={i} cx={cx} cy={cy} r="0.8" fill="white" opacity="0.6" />
          ))}
          {[
            [10, 8, 25, 15], [25, 15, 40, 5], [40, 5, 55, 20], [55, 20, 70, 10],
            [70, 10, 85, 18], [15, 30, 35, 35], [35, 35, 50, 25], [50, 25, 65, 32],
          ].map(([x1, y1, x2, y2], i) => (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="white" strokeWidth="0.2" opacity="0.3" />
          ))}
        </svg>
      </div>

      <div className="relative z-10 max-w-3xl mx-auto px-4 text-center">
        <Badge className="bg-white/20 text-white border-white/30 mb-6">
          {t('landing.hero.badge_beta')}
        </Badge>
        <h2 className="text-3xl mobile:text-4xl lg:text-5xl font-bold text-white tracking-tight mb-6">
          {t('landing.cta.title')}
        </h2>
        <p className="text-lg text-white/80 mb-8 max-w-xl mx-auto">
          {t('landing.cta.subtitle')}
        </p>
        <Button
          asChild
          size="lg"
          className="bg-white text-[#2563eb] hover:bg-white/90 text-base px-10 font-semibold shadow-lg"
        >
          <Link href={registerHref}>
            {t('landing.cta.button')}
          </Link>
        </Button>
        <p className="text-sm text-white/60 mt-6">
          {t('landing.cta.note_beta')}
        </p>
      </div>
    </section>
  );
}
