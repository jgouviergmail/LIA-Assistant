'use client';

/**
 * WorkbenchToolHeader — a tool page's heading (ADR-369, ADR-227 §7).
 *
 * The page's one h1, for the outline and the ear: the eye reads the open pill of
 * the rail, so nothing repeats it and the tool keeps that height. The tool's own
 * actions and « Refresh » follow the rail (`WorkbenchActionsSlot`, filled by a
 * portal), in the order the keyboard walks, with the tool's shortcuts
 * and their help where it has some (`ShortcutsHelp`). The rail is the way
 * between tools at every width, so no « all tools » link is needed. Opening a
 * tool moves focus to its heading — after a switch the reader lands on the screen
 * they asked for, never on the rail they left.
 */
import { RefreshCw } from 'lucide-react';
import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toolSpec } from '@/lib/workbench/tools';
import type { WorkbenchToolId } from '@/lib/workbench/types';

import { ShortcutsHelp } from './ShortcutsHelp';
import { useToolRefresh, type ToolRefresh } from './useToolRefresh';
import type { ToolShortcut } from './useToolShortcuts';

/** Where a tool's actions are drawn: the end of the rail's row, once it is in the page. */
export const WorkbenchActionsSlot = createContext<HTMLElement | null>(null);

export interface WorkbenchToolHeaderProps {
  lng: Language;
  tool: WorkbenchToolId;
  /** Re-reads what the screen shows; left out where nothing is on screen yet. */
  onRefresh?: ToolRefresh;
  /** What the tool's keys do, here and in its help. */
  shortcuts?: readonly ToolShortcut[];
  /** The tool's own actions, at the end of the row. */
  children?: ReactNode;
}

export function WorkbenchToolHeader({
  lng,
  tool,
  onRefresh,
  shortcuts,
  children,
}: WorkbenchToolHeaderProps) {
  const { t } = useTranslation(lng);
  const heading = useRef<HTMLHeadingElement>(null);
  const { labelKey } = toolSpec(tool);
  const { refreshing, refresh } = useToolRefresh(onRefresh);
  const slot = useContext(WorkbenchActionsSlot);

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [tool]);

  const actions = (onRefresh || children || shortcuts) && (
    <>
      {shortcuts && <ShortcutsHelp lng={lng} shortcuts={shortcuts} />}
      {onRefresh && (
        <Button
          variant="outline"
          size="sm"
          className="min-h-10 min-w-10 px-0 xl:px-3"
          isLoading={refreshing}
          onClick={() => void refresh()}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only xl:not-sr-only">{t('workbench.states.refresh')}</span>
        </Button>
      )}
      {children}
    </>
  );

  return (
    <>
      <h1 ref={heading} tabIndex={-1} className="sr-only">
        {t(labelKey)}
      </h1>
      {slot ? createPortal(actions, slot) : actions}
    </>
  );
}
