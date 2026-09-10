'use client';
/**
 * The board (ADR-276). A thin shell: everything lives in `WorkboardPage`.
 *
 * This route reads `?ticket=` — the deep link the board itself writes when a
 * panel opens, so a panel is a link somebody can send. The path form
 * `/dashboard/workboard/<id>`, which the backend builds in every ticket
 * notification, is the sibling route; both mount the same component.
 */
import { use } from 'react';

import { WorkboardPage } from '@/components/workboard/WorkboardPage';
import type { Language } from '@/i18n/settings';

export default function WorkboardRoute({ params }: { params: Promise<{ lng: string }> }) {
  const { lng } = use(params);
  return <WorkboardPage lng={lng as Language} />;
}
