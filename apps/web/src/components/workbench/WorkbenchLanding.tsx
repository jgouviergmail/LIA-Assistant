'use client';

/**
 * WorkbenchLanding — what `/dashboard/tools` shows (ADR-369, spec §13).
 *
 * The section opens the first READY tool in rail order, at every width (a
 * client `replace`, so « back » does not bounce through the root): the rail
 * above every tool is the way between them, so no list screen is needed even
 * on a phone. When none is ready, the pane names the exit — connect a service.
 */
import { useEffect } from 'react';

import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import type { Language } from '@/i18n/settings';
import { landingTool, toolPath } from '@/lib/workbench/tools';

import { useWorkbench } from './WorkbenchShell';
import { WorkbenchUnavailable } from './WorkbenchUnavailable';

export function WorkbenchLanding({ lng }: { lng: Language }) {
  const { availability } = useWorkbench();
  const router = useLocalizedRouter();
  const landing = landingTool(availability);

  useEffect(() => {
    if (landing) router.replace(toolPath(landing));
  }, [landing, router]);

  return landing ? null : <WorkbenchUnavailable lng={lng} kind="none_ready" />;
}
