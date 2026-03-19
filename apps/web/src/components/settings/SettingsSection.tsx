'use client';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { AccordionContent, AccordionItem } from '@/components/ui/accordion';
import * as AccordionPrimitive from '@radix-ui/react-accordion';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SettingsSectionProps {
  /**
   * Unique value for accordion state management.
   * Required when collapsible=true, ignored when collapsible=false.
   */
  value: string;

  /**
   * Section title
   */
  title: React.ReactNode;

  /**
   * Section description (optional)
   */
  description?: React.ReactNode;

  /**
   * Icon component to display next to title (optional)
   */
  icon?: React.ComponentType<{ className?: string }>;

  /**
   * Content to display when section is expanded (or always visible when not collapsible)
   */
  children: React.ReactNode;

  /**
   * Additional className for the Card wrapper
   */
  className?: string;

  /**
   * Additional className for the CardContent
   */
  contentClassName?: string;

  /**
   * If true (default), renders as a collapsible accordion item.
   * If false, renders as a static Card with always-visible content.
   * @default true
   */
  collapsible?: boolean;
}

/**
 * Generic settings section component with optional collapsible behavior.
 *
 * When collapsible=true (default):
 * - Wraps content in a Card with an Accordion trigger
 * - Must be used inside an Accordion component
 *
 * When collapsible=false:
 * - Renders a simple Card with always-visible content
 * - Does not require an Accordion parent
 *
 * Usage (collapsible):
 * ```tsx
 * <Accordion type="multiple" defaultValue={[]}>
 *   <SettingsSection
 *     value="theme"
 *     title="Theme"
 *     description="Choose your color theme"
 *     icon={Palette}
 *   >
 *     <ThemeOptions />
 *   </SettingsSection>
 * </Accordion>
 * ```
 *
 * Usage (non-collapsible):
 * ```tsx
 * <SettingsSection
 *   value="theme"
 *   title="Theme"
 *   description="Choose your color theme"
 *   icon={Palette}
 *   collapsible={false}
 * >
 *   <ThemeOptions />
 * </SettingsSection>
 * ```
 */
export function SettingsSection({
  value,
  title,
  description,
  icon: Icon,
  children,
  className,
  contentClassName,
  collapsible = true,
}: SettingsSectionProps) {
  // Non-collapsible mode: render simple Card
  if (!collapsible) {
    return (
      <Card className={cn('overflow-hidden', className)}>
        <CardHeader className="px-6 py-6 flex-row items-center gap-4 space-y-0">
          {Icon && (
            <div className="rounded-lg bg-primary/10 p-2.5">
              <Icon className="h-6 w-6 text-primary" />
            </div>
          )}
          <div className="flex-1">
            <h3 className="text-lg font-semibold leading-none tracking-tight">{title}</h3>
            {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
          </div>
        </CardHeader>
        <CardContent className={cn('px-6 pb-6 pt-0', contentClassName)}>{children}</CardContent>
      </Card>
    );
  }

  // Collapsible mode: render AccordionItem
  return (
    <AccordionItem value={value} className="border-none">
      <Card className={cn('overflow-hidden', className)}>
        <AccordionPrimitive.Header className="flex">
          <AccordionPrimitive.Trigger
            className={cn(
              'flex flex-1 items-center w-full px-6 py-6 hover:bg-accent/50 transition-colors',
              '[&[data-state=open]]:bg-accent/30',
              '[&[data-state=open]>div>svg.chevron]:rotate-180'
            )}
          >
            <CardHeader className="p-0 flex-row items-center gap-4 space-y-0 flex-1">
              {Icon && (
                <div className="rounded-lg bg-primary/10 p-2.5">
                  <Icon className="h-6 w-6 text-primary" />
                </div>
              )}
              <div className="flex-1 text-left">
                <h3 className="text-lg font-semibold leading-none tracking-tight">{title}</h3>
                {description && (
                  <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
                )}
              </div>
            </CardHeader>
            <ChevronDown className="chevron h-5 w-5 shrink-0 text-muted-foreground transition-transform duration-200 ml-3" />
          </AccordionPrimitive.Trigger>
        </AccordionPrimitive.Header>
        <AccordionContent className="px-6 pb-6">
          <CardContent className={cn('p-0 pt-4', contentClassName)}>{children}</CardContent>
        </AccordionContent>
      </Card>
    </AccordionItem>
  );
}
