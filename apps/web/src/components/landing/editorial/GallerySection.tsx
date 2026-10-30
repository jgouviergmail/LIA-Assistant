'use client';

import { useTranslation } from 'react-i18next';
import { FadeInOnScroll } from '../FadeInOnScroll';
import { ScreenshotsSection } from '../ScreenshotsSection';
import { PresentationSection } from '../PresentationSection';
import { Tabs } from './Tabs';

/**
 * Actual application workflows and the existing presentation deck in one
 * tabbed gallery. Workflow captures are selected on arrival.
 */
export function GallerySection() {
  const { t } = useTranslation();

  return (
    <section
      id="gallery"
      aria-labelledby="gallery-title"
      className="landing-section scroll-mt-24 border-y border-border/60 bg-card py-12 sm:py-20"
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
            // Actual workflows are the proof on arrival; the deck remains
            // available as the visitor's second reading depth.
            defaultTabId="screens"
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
          <p className="mx-auto mt-4 max-w-3xl text-center text-xs leading-5 text-muted-foreground">
            {t('landing.gallery.provenance')}
          </p>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
