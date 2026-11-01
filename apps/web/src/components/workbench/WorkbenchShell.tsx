'use client';

/**
 * WorkbenchShell — the « Tools » section's frame (ADR-369, ADR-227 §7).
 *
 * The rail is read ONCE here (`useWorkbenchAvailability`) and handed to every
 * page under the section through context: a tool page reads its own state,
 * gestures and bounds from it, never a second request. The rail is a row
 * ABOVE the open tool at every width (owner, 2026-10-31): beside it, a
 * vertical rail took a quarter of a laptop's width from tools that need it,
 * and a phone had to go back to a list screen to change tool. A re-read (a
 * connector changed elsewhere) keeps what is on screen and says it is busy;
 * only the FIRST load draws a placeholder.
 */
import { Wrench } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { createContext, useContext, type ReactNode } from 'react';

import { HeadingRule } from '@/components/ui/heading-rule';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useAppConfig } from '@/hooks/useAppConfig';
import {
  useWorkbenchAvailability,
  type WorkbenchAvailabilityState,
} from '@/hooks/useWorkbenchAvailability';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { workbenchAvailable } from '@/lib/workbench/availability';
import { toolOfPathname } from '@/lib/workbench/tools';
import type { WorkbenchAvailability } from '@/lib/workbench/types';

import { WorkbenchRail } from './WorkbenchRail';
import { WorkbenchUnavailable } from './WorkbenchUnavailable';

/** What every page of the section reads: the rail, once read. */
export interface WorkbenchContextValue extends WorkbenchAvailabilityState {
  availability: WorkbenchAvailability;
}

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);

/**
 * The rail the shell read, for a page under the section.
 *
 * @throws Error - Outside `WorkbenchShell` (a page of the section always has one).
 */
export function useWorkbench(): WorkbenchContextValue {
  const value = useContext(WorkbenchContext);
  if (!value) throw new Error('useWorkbench is only available under WorkbenchShell');
  return value;
}

export interface WorkbenchShellProps {
  lng: Language;
  children: ReactNode;
}

export function WorkbenchShell({ lng, children }: WorkbenchShellProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const offered = workbenchAvailable(config);
  const state = useWorkbenchAvailability(offered);
  const activeTool = toolOfPathname(usePathname());

  if (config && !offered) return <WorkbenchUnavailable lng={lng} kind="section_off" />;
  const { availability } = state;
  if (!availability) {
    // A retry that fails again is already said by the error state it leaves.
    return state.error ? (
      <WorkbenchUnavailable
        lng={lng}
        kind="error"
        onRetry={() => void state.refetch().catch(() => undefined)}
      />
    ) : (
      <ShellPlaceholder />
    );
  }

  return (
    <WorkbenchContext.Provider value={{ ...state, availability }}>
      {activeTool === null && (
        <div className="mb-4 flex items-center gap-3">
          <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
            <Wrench className="h-5 w-5 text-primary" aria-hidden="true" />
            {t('navigation.tools')}
          </h1>
          <HeadingRule />
        </div>
      )}
      <div aria-busy={state.loading || undefined}>
        <WorkbenchRail lng={lng} availability={availability} activeTool={activeTool} />
        {/* On the root the landing opens the first ready tool, or names the
            exit when none is. */}
        <div className="min-w-0">{children}</div>
      </div>
    </WorkbenchContext.Provider>
  );
}

/** The first load: the rail's geometry, announced once for the route. */
function ShellPlaceholder() {
  return (
    <div>
      <LoadingAnnouncement />
      <div className="mb-3 flex gap-1.5 overflow-hidden">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-9 w-28 shrink-0 rounded-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
