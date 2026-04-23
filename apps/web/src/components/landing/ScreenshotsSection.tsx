'use client';

import { useState } from 'react';
import Image from 'next/image';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { APP_VERSION } from '@/lib/version';
import { FadeInOnScroll } from './FadeInOnScroll';

interface ScreenshotItem {
  key: string;
  src: string;
}

// Cache-busting query string: bumped with every release so the browser, the
// Next.js Image optimizer and any upstream CDN immediately re-fetch the new
// PNG instead of serving a stale optimized variant.
const CACHE_BUST = `?v=${APP_VERSION}`;

const SCREENSHOTS: ScreenshotItem[] = [
  { key: 'homepage', src: `/screenshots/homepage.png${CACHE_BUST}` },
  { key: 'chat', src: `/screenshots/chat.png${CACHE_BUST}` },
  { key: 'chat_debug_panel', src: `/screenshots/chat-debug-panel.png${CACHE_BUST}` },
  {
    key: 'chat_interactive_skills',
    src: `/screenshots/chat-interactive-skills.png${CACHE_BUST}`,
  },
  { key: 'settings_preferences', src: `/screenshots/settings-preferences.png${CACHE_BUST}` },
  { key: 'settings_features', src: `/screenshots/settings-features.png${CACHE_BUST}` },
  {
    key: 'settings_features_memory',
    src: `/screenshots/settings-features-memory.png${CACHE_BUST}`,
  },
  {
    key: 'settings_features_psyche',
    src: `/screenshots/settings-features-psyche.png${CACHE_BUST}`,
  },
  { key: 'settings_administration', src: `/screenshots/settings-administration.png${CACHE_BUST}` },
  {
    key: 'settings_administration_oneclick',
    src: `/screenshots/settings-administration-oneclick.png${CACHE_BUST}`,
  },
  {
    key: 'settings_administration_llm',
    src: `/screenshots/settings-administration-llm.png${CACHE_BUST}`,
  },
  { key: 'faq', src: `/screenshots/faq.png${CACHE_BUST}` },
];

export function ScreenshotsSection() {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);

  const goTo = (index: number) => {
    setActiveIndex((index + SCREENSHOTS.length) % SCREENSHOTS.length);
  };

  const active = SCREENSHOTS[activeIndex];

  return (
    <section
      id="screenshots"
      className="landing-section py-24 bg-card"
      aria-labelledby="screenshots-title"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="text-center mb-12">
            <h2
              id="screenshots-title"
              className="text-3xl mobile:text-4xl font-bold tracking-tight mb-4"
            >
              {t('landing.screenshots.title')}
            </h2>
            <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
              {t('landing.screenshots.subtitle')}
            </p>
          </div>
        </FadeInOnScroll>

        <FadeInOnScroll delay={100}>
          {/* Main screenshot display */}
          <div className="relative group">
            <div className="relative aspect-[16/10] w-full max-w-5xl mx-auto rounded-xl overflow-hidden border border-border/60 shadow-2xl bg-background">
              <Image
                src={active.src}
                alt={t(`landing.screenshots.items.${active.key}`)}
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

          {/* Caption */}
          <p className="text-center text-sm text-muted-foreground mt-4 font-medium">
            {t(`landing.screenshots.items.${active.key}`)}
          </p>

          {/* Thumbnail navigation (desktop only) */}
          <div className="hidden mobile:flex justify-center gap-3 mt-6 flex-wrap">
            {SCREENSHOTS.map((screenshot, i) => (
              <button
                key={screenshot.key}
                onClick={() => setActiveIndex(i)}
                className={cn(
                  'relative w-20 h-14 mobile:w-24 mobile:h-16 rounded-lg overflow-hidden border-2 transition-all',
                  i === activeIndex
                    ? 'border-primary shadow-md scale-105'
                    : 'border-border/40 opacity-60 hover:opacity-100 hover:border-border'
                )}
                aria-label={t(`landing.screenshots.items.${screenshot.key}`)}
                aria-current={i === activeIndex ? 'true' : undefined}
              >
                <Image src={screenshot.src} alt="" fill className="object-cover" sizes="96px" />
              </button>
            ))}
          </div>

          {/* Dot indicators (mobile) */}
          <div className="flex justify-center gap-2 mt-4 mobile:hidden">
            {SCREENSHOTS.map((screenshot, i) => (
              <button
                key={screenshot.key}
                onClick={() => setActiveIndex(i)}
                className={cn(
                  'w-2 h-2 rounded-full transition-all',
                  i === activeIndex ? 'bg-primary w-6' : 'bg-border'
                )}
                aria-label={t(`landing.screenshots.items.${screenshot.key}`)}
              />
            ))}
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
