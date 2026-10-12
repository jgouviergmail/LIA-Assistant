'use client';

import { useTranslation } from 'react-i18next';
import { LandingCarousel, type CarouselSlide } from './LandingCarousel';
import homeProof from '../../../public/screenshots/manifest.json';
import applicationProof from '../../../public/screenshots/proof/manifest.json';
import monitoringProof from '../../../public/screenshots/proof/grafana-manifest.json';

/**
 * Real frontend views with fictional data and Grafana captures supplied by
 * the project. Each campaign's provenance is recorded in its own manifest.
 * The shared carousel provides navigation and full-screen inspection.
 */

const APPLICATION_VIEWS = [
  { key: 'dashboard', file: 'homepage' },
  { key: 'dossier', file: 'dossier' },
  { key: 'relations', file: 'relations' },
  { key: 'radio', file: 'radio' },
  { key: 'meetings', file: 'meetings' },
  { key: 'approval', file: 'approval' },
  { key: 'knowledge', file: 'knowledge' },
  { key: 'memory', file: 'memory' },
  { key: 'skill', file: 'skill' },
  { key: 'administration', file: 'administration' },
] as const;
const MONITORING_VIEWS = [
  { key: 'grafana_overview', file: 'grafana-overview' },
  { key: 'grafana_costs', file: 'grafana-costs' },
  { key: 'grafana_activity', file: 'grafana-activity' },
] as const;

type ApplicationView = (typeof APPLICATION_VIEWS)[number]['key'];

export function ScreenshotsSection({
  monitoring = false,
  view,
}: {
  monitoring?: boolean;
  /** A chapter can inspect its actual workflow without repeating the demo. */
  view?: ApplicationView;
}) {
  const { t } = useTranslation();
  const revision = monitoring ? monitoringProof.revision : applicationProof.revision;

  const views = monitoring
    ? MONITORING_VIEWS
    : view
      ? APPLICATION_VIEWS.filter(item => item.key === view)
      : APPLICATION_VIEWS;
  const slides: CarouselSlide[] = views.map(({ key, file }) => {
    const label = t(`landing.screenshots.proof.${key}`);
    // The retained home capture belongs to the earlier campaign. Preserve its
    // own revision and full-page ratio rather than attributing it to the new one.
    if (key === 'dashboard') {
      const capture = homeProof.images.find(image => image.file === `${file}.png`)!;
      return {
        key,
        src: `/screenshots/${file}.png?v=${homeProof.revision}`,
        label,
        caption: label,
        aspectRatio: capture.width / capture.height,
      };
    }
    return { key, src: `/screenshots/proof/${file}.png?v=${revision}`, label, caption: label };
  });

  return (
    <LandingCarousel
      slides={slides}
      variant="application"
      uniformFrame
      label={t(monitoring ? 'landing.platform.dashboard_title' : 'landing.gallery.tab_screens')}
      zoomable
    />
  );
}
