'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

/**
 * The single spoken "loading" of a route-level skeleton.
 *
 * `Skeleton` is decorative on purpose — a screen reader gains nothing from
 * hearing about each grey rectangle, and the settings skeleton draws fourteen
 * of them. But silence is not the answer either: React renders `loading.tsx`
 * without moving focus and without any native announcement, so a screen-reader
 * user would get no signal at all that the route was loading.
 *
 * So the announcement is made ONCE, here. This is a client component precisely
 * so it can reach the active locale: `loading.tsx` files are App Router SERVER
 * components, which cannot call a translation hook themselves — they render
 * this instead.
 *
 * The region is inserted EMPTY and receives its text one frame later: a live
 * region added to the page together with its content is often not read at all,
 * while a change inside a region that already exists is.
 */
export function LoadingAnnouncement() {
  const { t } = useTranslation();
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => setSpeaking(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <span role="status" className="sr-only">
      {speaking ? t('common.loading') : null}
    </span>
  );
}
