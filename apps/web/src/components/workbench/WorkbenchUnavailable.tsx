'use client';

/**
 * WorkbenchUnavailable — why the « Tools » section, or one of its tools, shows
 * nothing, and the way out (ADR-369).
 *
 * One decision table: each situation names what happened and offers the one
 * exit that fixes it — Settings › Connectors for a tool to connect or to
 * reconnect, the dashboard for a section or a tool this instance does not
 * offer, a retry for a rail that could not be read. A page-level empty state
 * always offers an action (`EmptyState variant="page"`).
 */
import { PlugZap, TriangleAlert, Wrench, type LucideIcon } from '@/lib/icons';

import { EmptyState } from '@/components/ui/empty-state';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
import { toolSpec } from '@/lib/workbench/tools';
import type { WorkbenchToolAvailability, WorkbenchToolId } from '@/lib/workbench/types';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

/** What the reader is told, and offered. */
export type WorkbenchUnavailableKind =
  | 'section_off'
  | 'none_ready'
  | 'reconnect_required'
  | 'not_connected'
  | 'unavailable'
  | 'error';

/** What a tool that is not ready shows instead of itself. */
export function unavailableKind(
  tool: WorkbenchToolAvailability | undefined
): WorkbenchUnavailableKind {
  if (tool?.state === 'not_connected') return 'not_connected';
  if (tool?.state === 'reconnect_required') return 'reconnect_required';
  return 'unavailable';
}

type Exit = 'connectors' | 'dashboard' | 'retry';

const SITUATIONS: Readonly<
  Record<WorkbenchUnavailableKind, { icon: LucideIcon; state: string; exit: Exit }>
> = {
  section_off: { icon: Wrench, state: 'section_off', exit: 'dashboard' },
  none_ready: { icon: PlugZap, state: 'none_ready', exit: 'connectors' },
  reconnect_required: { icon: TriangleAlert, state: 'reconnect', exit: 'connectors' },
  not_connected: { icon: PlugZap, state: 'not_connected', exit: 'connectors' },
  unavailable: { icon: Wrench, state: 'unavailable', exit: 'dashboard' },
  error: { icon: TriangleAlert, state: 'error', exit: 'retry' },
};

export interface WorkbenchUnavailableProps {
  lng: Language;
  kind: WorkbenchUnavailableKind;
  /** The tool concerned, for the tool-level situations. */
  tool?: WorkbenchToolId;
  /** What « Try again » does (the `error` situation). */
  onRetry?: () => void;
}

export function WorkbenchUnavailable({ lng, kind, tool, onRetry }: WorkbenchUnavailableProps) {
  const { t } = useTranslation(lng);
  const situation = SITUATIONS[kind];
  const values = tool ? { tool: t(toolSpec(tool).labelKey) } : undefined;
  const title = t(`workbench.states.${situation.state}_title`, values);
  const description = t(`workbench.states.${situation.state}_description`, values);

  if (situation.exit === 'retry') {
    return (
      <EmptyState
        variant="page"
        icon={situation.icon}
        title={title}
        description={description}
        action={{ label: t('workbench.states.retry'), onClick: () => onRetry?.() }}
      />
    );
  }
  const action =
    situation.exit === 'connectors'
      ? {
          label: t('workbench.states.open_connectors'),
          href: settingsSectionHref(lng, 'connectors'),
        }
      : {
          label: t('workbench.states.back_to_dashboard'),
          href: buildLocalizedPath('/dashboard', lng),
        };
  return (
    <EmptyState
      variant="page"
      icon={situation.icon}
      title={title}
      description={description}
      action={action}
    />
  );
}
