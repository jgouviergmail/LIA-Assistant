'use client';

import { useTranslation } from 'react-i18next';
import { LandingCarousel, type CarouselSlide } from './LandingCarousel';

/**
 * The 15-slide deck of the "LIA, en vrai" gallery, rendered by the shared
 * {@link LandingCarousel}. The section owns the content (how many slides,
 * where they live); the carousel owns the presentation.
 */

const TOTAL_SLIDES = 15;

const SLIDE_SOURCES = Array.from({ length: TOTAL_SLIDES }, (_, i) => ({
  number: i + 1,
  src: `/presentation/slide-${String(i + 1).padStart(2, '0')}.png`,
}));

export function PresentationSection() {
  const { t } = useTranslation();

  const slides: CarouselSlide[] = SLIDE_SOURCES.map(({ number, src }) => ({
    key: String(number),
    src,
    label: t('landing.presentation.slide_alt', { number }),
    // A slide has no title of its own: its position IS what identifies it,
    // so the counter sentence is the line worth reading and announcing.
    caption: t('landing.presentation.slide_counter', { current: number, total: TOTAL_SLIDES }),
  }));

  return <LandingCarousel slides={slides} variant="wide" label={t('landing.gallery.tab_slides')} />;
}
