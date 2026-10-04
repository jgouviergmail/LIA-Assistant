import type { ReactNode } from 'react';

import { initI18next } from '@/i18n';

import { LandingVideoHost } from './LandingVideoHost';

/**
 * The landing video's server half in the layout: the player's translated
 * labels, around every page of the language (ADR-330, amended). The host
 * mounts a player only once the landing's section has registered its frame.
 */
export async function LandingVideoHostSection({
  lng,
  children,
}: {
  lng: string;
  children: ReactNode;
}) {
  const { t } = await initI18next(lng);

  return (
    <LandingVideoHost
      lng={lng}
      labels={{
        ariaLabel: t('landing.video.aria_label'),
        play: t('landing.video.play'),
        pause: t('landing.video.pause'),
        next: t('landing.video.next'),
        unmute: t('landing.video.unmute'),
        mute: t('landing.video.mute'),
        nowPlaying: t('landing.video.now_playing'),
        backToVideo: t('landing.video.back_to_video'),
        close: t('landing.video.close'),
      }}
    >
      {children}
    </LandingVideoHost>
  );
}
