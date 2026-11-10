'use client';

/**
 * WorkbenchShell — the « Tools » section's frame (ADR-369, ADR-227 §7).
 *
 * The rail is read ONCE here (`useWorkbenchAvailability`) and handed to every
 * page under the section through context: a tool page reads its own state,
 * gestures and bounds from it, never a second request. The rail is a row
 * ABOVE the open tool at every width (owner, 2026-10-31): beside it, a
 * vertical rail took a quarter of a laptop's width from tools that need it,
 * and a phone had to go back to a list screen to change tool. The open tool's
 * actions end that row, so a tool starts right under it; below `xl` they stand on
 * a line of their own, the search and « Refresh » at its start and the act the tool
 * leads with at its end. A re-read (a connector changed elsewhere) keeps what is on
 * screen and says it is busy; only the FIRST load draws a placeholder. The dialogs any tool can
 * open (`useAssistHost`) are held here once.
 */
import { Wrench } from '@/lib/icons';
import { usePathname } from 'next/navigation';
import { createContext, useContext, useState, type ReactNode } from 'react';

import { HeadingRule } from '@/components/ui/heading-rule';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useAuth } from '@/hooks/useAuth';
import {
  useWorkbenchAvailability,
  type WorkbenchAvailabilityState,
} from '@/hooks/useWorkbenchAvailability';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { useMailCounts, type MailCountsState } from '@/hooks/useMailCounts';
import { toolAssistsAvailable, workbenchAvailable } from '@/lib/workbench/availability';
import { MAIL_INBOX } from '@/lib/workbench/mail';
import { toolOfPathname } from '@/lib/workbench/tools';
import type { WorkbenchAvailability } from '@/lib/workbench/types';

import { useAssistHost, type AssistDoors } from './assist/useAssistHost';
import { WorkbenchRail } from './WorkbenchRail';
import { WorkbenchSearch } from './WorkbenchSearch';
import { WorkbenchActionsSlot } from './WorkbenchToolHeader';
import { WorkbenchUnavailable } from './WorkbenchUnavailable';

/** What every page of the section reads: the rail, once read. */
export interface WorkbenchContextValue extends WorkbenchAvailabilityState {
  availability: WorkbenchAvailability;
  /** What the mailbox leaves unread: the rail draws it on every tool's page. */
  mailCounts: MailCountsState;
  /** The dialogs any tool can open. */
  doors: AssistDoors;
  /** A click may ask a model from these screens (ADR-372). */
  assists: boolean;
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

/** What a writing helper may take, published. */
export interface AssistBounds {
  textMax: number;
  instructionMax: number;
  /** Words can be said into a field here. */
  dictates: boolean;
}

/**
 * Whether a click may ask a model here, for a control that may stand outside the section.
 *
 * @returns The published bounds; null off, or outside `WorkbenchShell`.
 */
export function useAssistBounds(): AssistBounds | null {
  const value = useContext(WorkbenchContext);
  if (!value?.assists) return null;
  const { assist_text_max_chars, assist_instruction_max_chars } = value.availability.limits;
  return {
    textMax: assist_text_max_chars,
    instructionMax: assist_instruction_max_chars,
    dictates: value.doors.dictates,
  };
}

export interface WorkbenchShellProps {
  lng: Language;
  children: ReactNode;
}

export function WorkbenchShell({ lng, children }: WorkbenchShellProps) {
  const { user } = useAuth();
  return (
    <AccountWorkbenchShell key={user?.id ?? 'signed-out'} lng={lng}>
      {children}
    </AccountWorkbenchShell>
  );
}

function AccountWorkbenchShell({ lng, children }: WorkbenchShellProps) {
  const { t } = useTranslation(lng);
  const { config } = useAppConfig();
  const offered = workbenchAvailable(config);
  const state = useWorkbenchAvailability(offered);
  const activeTool = toolOfPathname(usePathname());
  const [actions, setActions] = useState<HTMLElement | null>(null);
  const host = useAssistHost(lng, config);
  const mailReady = state.availability?.tools.some(
    item => item.tool === 'mail' && item.state === 'ready'
  );
  const mailCounts = useMailCounts(mailReady ?? false);

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
    <WorkbenchContext.Provider
      value={{
        ...state,
        availability,
        mailCounts,
        doors: host.doors,
        assists: toolAssistsAvailable(config),
      }}
    >
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
        <div className="mb-3 flex min-h-11 flex-wrap items-center gap-2 lg:mb-8">
          <WorkbenchRail
            lng={lng}
            availability={availability}
            activeTool={activeTool}
            mailUnread={mailCounts.counts?.[MAIL_INBOX]}
          />
          <div className="flex w-full min-w-0 flex-wrap items-center gap-1.5 xl:ml-auto xl:w-auto xl:justify-end">
            <WorkbenchSearch lng={lng} availability={availability} />
            <div
              ref={setActions}
              className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 xl:flex-none xl:justify-end"
            />
          </div>
        </div>
        {/* On the root the landing opens the first ready tool, or names the
            exit when none is. */}
        <WorkbenchActionsSlot.Provider value={actions}>
          <div className="min-w-0">{children}</div>
        </WorkbenchActionsSlot.Provider>
      </div>
      {host.dialogs}
    </WorkbenchContext.Provider>
  );
}

/** The first load: the rail's geometry, announced once for the route. */
function ShellPlaceholder() {
  return (
    <div>
      <LoadingAnnouncement />
      <div className="mb-3 flex gap-1.5 overflow-hidden lg:mb-8">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-9 w-28 shrink-0 rounded-full" />
        ))}
      </div>
      <Skeleton className="h-64 w-full" />
    </div>
  );
}
