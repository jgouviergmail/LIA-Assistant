'use client';

/**
 * The card every settings section renders itself in.
 *
 * ONE layout: header (icon, title, description) above always-visible content.
 * The master-detail shell (ADR-227) mounts exactly one section at a time and
 * shows it open, so the collapsible/accordion mode this component used to
 * carry lost its last production call site with the old page; it survived
 * purely in test scaffolding, which is dead code by the repo's own rule.
 *
 * Two details are load-bearing and belong to the shell contract:
 *   - `id="settings-section-<value>"` — the pane polls this anchor to tell a
 *     section that renders nothing from one that is still loading;
 *   - `tabIndex={-1}` — a search pick moves focus here, so the card must be a
 *     programmatic focus target without ever entering the tab order.
 */

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface SettingsSectionProps {
  /**
   * Stable section identifier — the suffix of the DOM anchor id, and the
   * `accordionValue` the deep-link table (`lib/settings-sections.ts`) points at.
   */
  value: string;

  /** Section title. */
  title: React.ReactNode;

  /** Section description (optional). */
  description?: React.ReactNode;

  /** Icon displayed next to the title (optional). */
  icon?: React.ComponentType<{ className?: string }>;

  /** Section body. */
  children: React.ReactNode;

  /** Additional className for the Card wrapper. */
  className?: string;

  /** Additional className for the CardContent. */
  contentClassName?: string;
}

export function SettingsSection({
  value,
  title,
  description,
  icon: Icon,
  children,
  className,
  contentClassName,
}: SettingsSectionProps) {
  return (
    <Card id={`settings-section-${value}`} tabIndex={-1} className={cn('overflow-hidden', className)}>
      <CardHeader className="flex-row items-center gap-3 space-y-0 px-4 py-4 sm:gap-4 sm:px-6 sm:py-6">
        {Icon && (
          <div className="flex rounded-lg bg-primary/10 p-2 sm:p-2.5">
            <Icon className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
          </div>
        )}
        <div className="flex-1">
          <h3 className="text-base font-semibold leading-none tracking-tight sm:text-lg">{title}</h3>
          {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
        </div>
      </CardHeader>
      <CardContent className={cn('px-4 pb-4 pt-0 sm:px-6 sm:pb-6', contentClassName)}>
        {children}
      </CardContent>
    </Card>
  );
}
