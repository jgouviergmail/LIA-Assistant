'use client';

import { useTranslation } from 'react-i18next';
import { LandingCarousel, type CarouselSlide } from './LandingCarousel';
import homeProof from '../../../public/screenshots/manifest.json';
import applicationProof from '../../../public/screenshots/proof/manifest.json';
import extendedProof from '../../../public/screenshots/proof/extended-manifest.json';
import monitoringProof from '../../../public/screenshots/proof/grafana-manifest.json';
import worldProof from '../../../public/screenshots/proof/world-manifest.json';

/**
 * Real frontend views with fictional data, plus World and Grafana captures
 * supplied by the project. Each campaign records its own provenance.
 * The shared carousel provides navigation and full-screen inspection.
 */

const APPLICATION_VIEWS = [
  { key: 'dashboard', file: 'dashboard-wide', campaign: 'home' },
  { key: 'world', file: 'lia-world', campaign: 'world' },
  { key: 'dossier', file: 'dossier', campaign: 'application' },
  { key: 'places', file: 'places', campaign: 'application' },
  { key: 'maps', file: 'maps', campaign: 'application' },
  { key: 'routes', file: 'routes', campaign: 'application' },
  { key: 'relations', file: 'relations', campaign: 'application' },
  { key: 'radio', file: 'radio', campaign: 'application' },
  { key: 'meetings', file: 'meetings', campaign: 'application' },
  { key: 'meetings_list', file: 'meetings-list', campaign: 'extended' },
  { key: 'approval', file: 'approval', campaign: 'application' },
  { key: 'knowledge', file: 'knowledge', campaign: 'application' },
  { key: 'memory', file: 'memory', campaign: 'application' },
  { key: 'skill', file: 'skill', campaign: 'application' },
  { key: 'administration', file: 'administration', campaign: 'application' },
  { key: 'psyche', file: 'psyche', campaign: 'extended' },
  { key: 'psyche_evolution', file: 'psyche-evolution', campaign: 'extended' },
  { key: 'memory_library', file: 'memory-library', campaign: 'extended' },
  { key: 'portrait', file: 'portrait', campaign: 'extended' },
  { key: 'avatar_picker', file: 'avatar-picker', campaign: 'extended' },
  { key: 'routine_studio', file: 'routine-studio', campaign: 'extended' },
  { key: 'routine_week', file: 'routine-week', campaign: 'extended' },
  { key: 'workboard', file: 'workboard', campaign: 'extended' },
  { key: 'workboard_dossier', file: 'workboard-dossier', campaign: 'extended' },
  { key: 'knowledge_library', file: 'knowledge-library', campaign: 'extended' },
  { key: 'meeting_transcript', file: 'meeting-transcript', campaign: 'extended' },
  { key: 'meeting_templates', file: 'meeting-templates', campaign: 'extended' },
  { key: 'connections', file: 'connections', campaign: 'extended' },
  { key: 'skills_library', file: 'skills-library', campaign: 'extended' },
  { key: 'model_routing', file: 'model-routing', campaign: 'extended' },
  { key: 'consumption', file: 'consumption', campaign: 'extended' },
  { key: 'journal', file: 'journal', campaign: 'extended' },
] as const;
const MONITORING_VIEWS = [
  { key: 'grafana_overview', file: 'grafana-overview', campaign: 'monitoring' },
  { key: 'grafana_costs', file: 'grafana-costs', campaign: 'monitoring' },
  { key: 'grafana_activity', file: 'grafana-activity', campaign: 'monitoring' },
] as const;

interface CaptureManifest {
  revision: string;
  images: { file: string; width: number; height: number }[];
}

// Every view keeps the revision and native dimensions of its capture campaign.
const CAPTURE_CAMPAIGNS: Record<
  string,
  { manifest: CaptureManifest; directory: string; extension?: string }
> = {
  home: { manifest: homeProof, directory: '/screenshots' },
  application: { manifest: applicationProof, directory: '/screenshots/proof' },
  extended: { manifest: extendedProof, directory: '/screenshots/proof' },
  monitoring: { manifest: monitoringProof, directory: '/screenshots/proof' },
  world: { manifest: worldProof, directory: '/screenshots/proof', extension: 'jpg' },
};

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

  const views = monitoring
    ? MONITORING_VIEWS
    : view
      ? APPLICATION_VIEWS.filter(item => item.key === view)
      : APPLICATION_VIEWS;
  const slides: CarouselSlide[] = views.map(({ key, file, campaign }) => {
    const label = t(`landing.screenshots.proof.${key}`);
    const { manifest, directory, extension = 'png' } = CAPTURE_CAMPAIGNS[campaign];
    const filename = `${file}.${extension}`;
    const capture = manifest.images.find(image => image.file === filename);
    return {
      key,
      src: `${directory}/${filename}?v=${manifest.revision}`,
      label,
      caption: label,
      aspectRatio: capture ? capture.width / capture.height : undefined,
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
