'use client';

import { useTranslation } from 'react-i18next';

/**
 * The single spoken "loading" of a route-level skeleton.
 *
 * `Skeleton` is decorative on purpose — a screen reader gains nothing from
 * hearing about each grey rectangle, and the settings skeleton draws fourteen
 * of them. But silence is not the answer either: React renders `loading.tsx`
 * without moving focus and without any native announcement, so a screen-reader
 * user would get no signal at all that the route is loading.
 *
 * So the announcement is made ONCE, here. This is a client component precisely
 * so it can reach the active locale: `loading.tsx` files are App Router SERVER
 * components, which cannot call a translation hook themselves — they render
 * this instead.
 */
export function LoadingAnnouncement() {
  const { t } = useTranslation();

  return (
    <span role="status" className="sr-only">
      {t('common.loading')}
    </span>
  );
}
