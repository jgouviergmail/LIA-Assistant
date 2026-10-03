'use client';

import { SpacesManager } from '@/components/spaces/SpacesManager';

/**
 * The knowledge spaces page. The screen itself lives in `SpacesManager`,
 * which the settings section « Knowledge spaces » mounts too — one
 * implementation for both doors.
 */
export default function SpacesPage() {
  return <SpacesManager variant="page" />;
}
