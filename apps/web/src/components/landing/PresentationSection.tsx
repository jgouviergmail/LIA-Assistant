'use client';

import { useState, useCallback } from 'react';
import Image from 'next/image';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FadeInOnScroll } from './FadeInOnScroll';

const TOTAL_SLIDES = 13;

const SLIDES = Array.from({ length: TOTAL_SLIDES }, (_, i) => ({
  index: i + 1,
  src: `/presentation/slide-${String(i + 1).padStart(2, '0')}.png`,
}));

export function PresentationSection() {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);

  const goTo = useCallback((index: number) => {
    setActiveIndex((index + TOTAL_SLIDES) % TOTAL_SLIDES);
  }, []);

  const active = SLIDES[activeIndex];

  return (
    <section
      id="presentation"
      className="landing-section py-24"
      aria-labelledby="presentation-title"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-12">
            <h2
              id="presentation-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.presentation.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.presentation.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        <FadeInOnScroll delay={100}>
          {/* Main slide display */}
          <div className="relative group">
            <div className="relative aspect-[16/9] w-full max-w-5xl mx-auto rounded-xl overflow-hidden border border-border/60 shadow-2xl bg-background">
              <Image
                src={active.src}
                alt={t('landing.presentation.slide_alt', { number: active.index })}
                fill
                className="object-contain"
                sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 1024px"
                priority={activeIndex === 0}
              />
            </div>

            {/* Navigation arrows */}
            <button
              onClick={() => goTo(activeIndex - 1)}
              className="absolute left-2 mobile:left-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-background/80 backdrop-blur-sm border border-border/60 flex items-center justify-center shadow-lg opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background"
              aria-label={t('common.previous')}
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              onClick={() => goTo(activeIndex + 1)}
              className="absolute right-2 mobile:right-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-background/80 backdrop-blur-sm border border-border/60 flex items-center justify-center shadow-lg opacity-0 group-hover:opacity-100 transition-opacity hover:bg-background"
              aria-label={t('common.next')}
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Slide counter */}
          <p className="text-center text-sm text-muted-foreground mt-4 font-medium">
            {t('landing.presentation.slide_counter', {
              current: activeIndex + 1,
              total: TOTAL_SLIDES,
            })}
          </p>

          {/* Thumbnail navigation (desktop only) */}
          <div className="hidden mobile:flex justify-center gap-2 mt-6 flex-wrap">
            {SLIDES.map((slide, i) => (
              <button
                key={slide.index}
                onClick={() => setActiveIndex(i)}
                className={cn(
                  'relative w-20 h-12 mobile:w-24 mobile:h-14 rounded-lg overflow-hidden border-2 transition-all',
                  i === activeIndex
                    ? 'border-primary shadow-md scale-105'
                    : 'border-border/40 opacity-60 hover:opacity-100 hover:border-border'
                )}
                aria-label={t('landing.presentation.slide_alt', { number: slide.index })}
                aria-current={i === activeIndex ? 'true' : undefined}
              >
                <Image src={slide.src} alt="" fill className="object-cover" sizes="96px" />
              </button>
            ))}
          </div>

          {/* Dot indicators (mobile) */}
          <div className="flex justify-center gap-2 mt-4 mobile:hidden">
            {SLIDES.map((slide, i) => (
              <button
                key={slide.index}
                onClick={() => setActiveIndex(i)}
                className={cn(
                  'w-2 h-2 rounded-full transition-all',
                  i === activeIndex ? 'bg-primary w-6' : 'bg-border'
                )}
                aria-label={t('landing.presentation.slide_alt', { number: slide.index })}
              />
            ))}
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
