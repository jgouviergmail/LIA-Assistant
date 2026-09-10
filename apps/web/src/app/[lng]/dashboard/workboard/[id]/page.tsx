'use client';
/**
 * One ticket, opened from its own URL (ADR-276).
 *
 * `domains/workboard/notifications.py::ticket_url` builds
 * `<frontend>/dashboard/workboard/<id>` and puts it in EVERY ticket
 * notification — a path segment, not a query parameter. Without this route
 * those links answer 404, which is exactly what the board answered before this
 * lot (measured 2026-09-09).
 *
 * It mounts the same `WorkboardPage` as the board itself, with the ticket
 * pre-opened: the reader lands on the board they know, with the panel already
 * showing what the notification was about.
 */
import { use } from 'react';

import { WorkboardPage } from '@/components/workboard/WorkboardPage';
import type { Language } from '@/i18n/settings';

export default function WorkboardTicketRoute({
  params,
}: {
  params: Promise<{ lng: string; id: string }>;
}) {
  const { lng, id } = use(params);
  return <WorkboardPage lng={lng as Language} initialTicketId={id} />;
}
