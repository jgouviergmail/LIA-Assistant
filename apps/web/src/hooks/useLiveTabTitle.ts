/**
 * useLiveTabTitle — alternates the document title while a run streams and the
 * tab is hidden (micro-interactions batch I5), so background runs stay
 * visible from any tab. Restores the exact original title when the stream
 * ends, the tab becomes visible, or the caller unmounts.
 */

'use client';

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const BLINK_INTERVAL_MS = 1500;

export function useLiveTabTitle(active: boolean): void {
  const { t } = useTranslation();

  useEffect(() => {
    if (!active || typeof document === 'undefined') return;

    const originalTitle = document.title;
    const liveTitle = `✦ ${t('chat.tab_title_writing')}`;
    let showLive = false;

    const tick = () => {
      if (document.hidden) {
        showLive = !showLive;
        document.title = showLive ? liveTitle : originalTitle;
      } else if (document.title !== originalTitle) {
        showLive = false;
        document.title = originalTitle;
      }
    };

    const interval = window.setInterval(tick, BLINK_INTERVAL_MS);
    const onVisibilityChange = () => {
      if (!document.hidden) {
        showLive = false;
        document.title = originalTitle;
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      document.title = originalTitle;
    };
  }, [active, t]);
}
