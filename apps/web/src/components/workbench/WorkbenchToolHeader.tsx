'use client';

/**
 * WorkbenchToolHeader — a tool page's heading (ADR-369, ADR-227 §7).
 *
 * The page's one h1: the tool's name with its theme-coloured icon, the tool's
 * own actions at the end of the row. The rail above is the way between tools at
 * every width, so no « all tools » link is needed. Opening a tool moves focus
 * to its heading — after a switch the reader lands on the screen they asked
 * for, never on the rail they left.
 */
import { useEffect, useRef, type ReactNode } from 'react';

import { HeadingRule } from '@/components/ui/heading-rule';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toolSpec } from '@/lib/workbench/tools';
import type { WorkbenchToolId } from '@/lib/workbench/types';

export interface WorkbenchToolHeaderProps {
  lng: Language;
  tool: WorkbenchToolId;
  /** The tool's own actions, at the end of the row. */
  children?: ReactNode;
}

export function WorkbenchToolHeader({ lng, tool, children }: WorkbenchToolHeaderProps) {
  const { t } = useTranslation(lng);
  const heading = useRef<HTMLHeadingElement>(null);
  const { icon: Icon, labelKey } = toolSpec(tool);

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [tool]);

  return (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <h1
        ref={heading}
        tabIndex={-1}
        className="flex items-center gap-2 text-xl font-semibold text-foreground focus:outline-none"
      >
        <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
        {t(labelKey)}
      </h1>
      <HeadingRule />
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
