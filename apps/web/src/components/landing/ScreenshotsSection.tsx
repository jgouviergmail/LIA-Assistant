'use client';

import { useTranslation } from 'react-i18next';
import { LandingCarousel, type CarouselSlide } from './LandingCarousel';
import {
  APPLICATION_VIEWS,
  CAPTURE_STAGE_DEFAULT_WIDTH,
  CAPTURE_THUMB_WIDTH,
  CHAPTER_VIEWS,
  MONITORING_VIEWS,
  captureFileName,
  captureOriginalPath,
  captureStageSrcSet,
  captureVariantPath,
  type ApplicationView,
  type CaptureCampaign,
} from '@/lib/landing/captures';
import homeProof from '../../../public/screenshots/manifest.json';
import applicationProof from '../../../public/screenshots/proof/manifest.json';
import extendedProof from '../../../public/screenshots/proof/extended-manifest.json';
import monitoringProof from '../../../public/screenshots/proof/grafana-manifest.json';
import worldProof from '../../../public/screenshots/proof/world-manifest.json';

/**
 * Real frontend views with fictional data, plus World and Grafana captures
 * supplied by the project. Each campaign records its own provenance.
 * The shared carousel provides navigation and full-screen inspection; the
 * views and their static variants are declared in `lib/landing/captures.ts`.
 */

interface CaptureManifest {
  revision: string;
  images: { file: string; width: number; height: number }[];
}

// Every view keeps the revision and native dimensions of its capture campaign.
const CAPTURE_MANIFESTS: Record<CaptureCampaign, CaptureManifest> = {
  home: homeProof,
  application: applicationProof,
  extended: extendedProof,
  monitoring: monitoringProof,
  world: worldProof,
};

export function ScreenshotsSection({
  monitoring = false,
  view,
}: {
  monitoring?: boolean;
  /** A chapter can inspect its actual workflow without repeating the demo. */
  view?: ApplicationView;
}) {
  const { t } = useTranslation();

  const views = monitoring
    ? MONITORING_VIEWS
    : view
      ? [...APPLICATION_VIEWS, ...CHAPTER_VIEWS].filter(item => item.key === view)
      : APPLICATION_VIEWS;
  const slides: CarouselSlide[] = views.map(item => {
    const label = t(`landing.screenshots.proof.${item.key}`);
    const manifest = CAPTURE_MANIFESTS[item.campaign];
    const capture = manifest.images.find(image => image.file === captureFileName(item));
    const query = `?v=${manifest.revision}`;
    return {
      key: item.key,
      src: `${captureOriginalPath(item)}${query}`,
      label,
      caption: label,
      aspectRatio: capture ? capture.width / capture.height : undefined,
      variants: {
        src: `${captureVariantPath(item.file, CAPTURE_STAGE_DEFAULT_WIDTH)}${query}`,
        srcSet: captureStageSrcSet(item.file, capture?.width, query),
        thumbSrc: `${captureVariantPath(item.file, CAPTURE_THUMB_WIDTH)}${query}`,
      },
    };
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
