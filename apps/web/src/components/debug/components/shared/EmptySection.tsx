/**
 * Empty Section Component
 *
 * Renders a collapsed AccordionItem placeholder when a section has no data.
 * Ensures all sections remain visible in the debug panel regardless of data availability.
 */

import React from 'react';
import { AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { SectionBadge } from './badges/SectionBadge';
import { INFO_SECTION_CLASSES } from '../../utils/constants';

export interface EmptySectionProps {
  /** Unique accordion value */
  value: string;
  /** Section title */
  title: string;
}

/**
 * Placeholder for sections with no data.
 *
 * Displays a dimmed section header with "N/A" badge and a short message
 * inside the collapsible content area.
 */
export const EmptySection = React.memo(function EmptySection({ value, title }: EmptySectionProps) {
  return (
    <AccordionItem value={value}>
      <AccordionTrigger className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <span>{title}</span>
          <SectionBadge passed={false} label="N/A" />
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className={INFO_SECTION_CLASSES}>No data available for this section.</div>
      </AccordionContent>
    </AccordionItem>
  );
});
