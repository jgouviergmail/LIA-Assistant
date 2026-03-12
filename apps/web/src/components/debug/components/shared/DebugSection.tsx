/**
 * DebugSection - Generic wrapper for debug panel sections.
 *
 * Standardizes the Accordion structure used by all debug sections.
 * Reduces boilerplate while preserving flexibility for custom content.
 */

import React from 'react';
import {
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from '@/components/ui/accordion';

export interface DebugSectionProps {
  /** Unique value for accordion item */
  value: string;
  /** Section title displayed in trigger */
  title: string;
  /** Optional badge element(s) displayed after title */
  badge?: React.ReactNode;
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
 *   badge={<SectionBadge passed={passed} value={confidence} />}
 * >
 *   <MetricRow label="Action" value={intent} highlight />
 * </DebugSection>
 * ```
 */
export const DebugSection = React.memo(function DebugSection({
  value,
  title,
  badge,
  children,
  contentClassName = 'space-y-3',
}: DebugSectionProps) {
  return (
    <AccordionItem value={value}>
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>{title}</span>
          {badge}
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className={contentClassName}>{children}</div>
      </AccordionContent>
    </AccordionItem>
  );
});
