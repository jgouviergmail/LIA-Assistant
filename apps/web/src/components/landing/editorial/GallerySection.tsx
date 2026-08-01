'use client';

import { useTranslation } from 'react-i18next';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { ScreenshotsSection } from '../ScreenshotsSection';
import { PresentationSection } from '../PresentationSection';
import { Tabs } from './Tabs';

/**
 * "See LIA for real." — the 12 app screenshots and the 15-slide deck in one
 * tabbed gallery, the deck selected on arrival (see the `defaultTabId` note
 * below). Both tabs render the same shared carousel.
 */
export function GallerySection() {
  const { t } = useTranslation();

  return (
    <section
      id="gallery"
      aria-labelledby="gallery-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card py-24"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <FadeInOnScroll>
          <div className="mb-4 text-center">
            <h2 id="gallery-title" className="text-3xl font-bold tracking-tight mobile:text-4xl">
              {t('landing.gallery.title')}
            </h2>
            <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">
              {t('landing.gallery.sub')}
            </p>
          </div>
          <Tabs
            label={t('landing.gallery.tabs_label')}
            // The deck opens the section: it tells the product's story in
            // order, where the captures answer "show me a screen" on demand.
            defaultTabId="slides"
            items={[
              {
                id: 'screens',
                label: t('landing.gallery.tab_screens'),
                content: <ScreenshotsSection />,
              },
              {
                id: 'slides',
                label: t('landing.gallery.tab_slides'),
                content: <PresentationSection />,
              },
            ]}
          />
        </FadeInOnScroll>
      </div>
    </section>
  );
}
