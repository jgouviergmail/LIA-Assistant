import { initI18next } from '@/i18n';

import { LandingVideo } from './LandingVideo';

/**
 * The landing video's server half on the page: the section's translated
 * labels, nothing else. The section itself mounts in the browser, once
 * `/api/landing-media` says this deployment shows a video (ADR-330) — the page
 * is prebuilt and host-neutral. The player's labels travel with the layout
 * (`LandingVideoHostSection`).
 */
export async function LandingVideoSection({ lng }: { lng: string }) {
  const { t } = await initI18next(lng);

  return (
    <LandingVideo
      labels={{
        ariaLabel: t('landing.video.aria_label'),
        aiDisclosure: t('landing.video.ai_disclosure'),
        creditPrefix: t('landing.video.credit_before'),
        externalLink: t('landing.video.external_link'),
      }}
    />
  );
}
