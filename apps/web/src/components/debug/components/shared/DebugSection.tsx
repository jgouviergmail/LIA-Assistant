/**
 * DebugSection — the single section wrapper of the debug panel.
 *
 * Standardizes the Accordion structure for every section: themed title icon
 * (title-icon doctrine: lucide, `text-primary`, never grey), badge slot,
 * and an optional anomaly indicator surfaced on the trigger so a section
 * carrying an error is visible without unfolding it.
 */

import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';

export interface DebugSectionProps {
  /** Unique value for accordion item */
  value: string;
  /** Section title displayed in trigger */
  title: string;
  /** Themed title icon (rendered decorative, `text-primary`). */
  icon?: LucideIcon;
  /** Optional badge element(s) displayed after title */
  badge?: React.ReactNode;
  /** Surface an anomaly dot on the trigger (section carries an error). */
  anomaly?: boolean;
  /** Section content */
  children: React.ReactNode;
  /** Optional custom className for content wrapper */
  contentClassName?: string;
}

/**
 * Generic debug section wrapper.
 *
 * Usage:
 * ```tsx
 * <DebugSection
 *   value="intent"
 *   title="Intent Detection"
 *   icon={Brain}
 *   badge={<SectionBadge passed={passed} value={confidence} />}
 * >
 *   <MetricRow label="Action" value={intent} highlight />
 * </DebugSection>
 * ```
 */
export const DebugSection = React.memo(function DebugSection({
  value,
  title,
  icon: Icon,
  badge,
  anomaly = false,
  children,
  contentClassName = 'space-y-3',
}: DebugSectionProps) {
  return (
    <AccordionItem value={value}>
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />}
          <span>{title}</span>
          {anomaly && (
            <span
              title="This section contains an error"
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-destructive"
            />
          )}
          {badge}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className={contentClassName}>{children}</div>
      </AccordionContent>
    </AccordionItem>
  );
});
