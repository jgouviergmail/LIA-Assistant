'use client';

import { useTranslation } from 'react-i18next';
import { LandingCarousel, type CarouselSlide } from './LandingCarousel';

/**
 * The app captures of the "LIA, en vrai" gallery — real screenshots, listed
 * here and rendered by the shared {@link LandingCarousel}. The section owns
 * the content (which capture, which translated name); the carousel owns the
 * presentation.
 */

const SCREENSHOT_KEYS: ReadonlyArray<{ key: string; src: string }> = [
  { key: 'homepage', src: '/screenshots/homepage.png' },
  { key: 'chat', src: '/screenshots/chat.png' },
  { key: 'chat_debug_panel', src: '/screenshots/chat-debug-panel.png' },
  { key: 'chat_interactive_skills', src: '/screenshots/chat-interactive-skills.png' },
  { key: 'settings_preferences', src: '/screenshots/settings-preferences.png' },
  { key: 'settings_features', src: '/screenshots/settings-features.png' },
  { key: 'settings_features_memory', src: '/screenshots/settings-features-memory.png' },
  { key: 'settings_features_psyche', src: '/screenshots/settings-features-psyche.png' },
  { key: 'settings_administration', src: '/screenshots/settings-administration.png' },
  {
    key: 'settings_administration_oneclick',
    src: '/screenshots/settings-administration-oneclick.png',
  },
  { key: 'settings_administration_llm', src: '/screenshots/settings-administration-llm.png' },
  { key: 'faq', src: '/screenshots/faq.png' },
];

export function ScreenshotsSection() {
  const { t } = useTranslation();

  const slides: CarouselSlide[] = SCREENSHOT_KEYS.map(({ key, src }) => {
    const label = t(`landing.screenshots.items.${key}`);
    // The name of the view IS the caption here: it says which screen is on
    // screen, which is exactly what changes when the carousel moves.
    return { key, src, label, caption: label };
  });

  return (
    <LandingCarousel
      slides={slides}
      variant="portrait"
      label={t('landing.gallery.tab_screens')}
      // Captures are dense UI shown at 544 px: full screen is where they
      // become readable, and each asset is light enough to fetch on demand.
      zoomable
    />
  );
}
