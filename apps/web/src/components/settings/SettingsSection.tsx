'use client';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { AccordionContent, AccordionItem } from '@/components/ui/accordion';
import * as AccordionPrimitive from '@radix-ui/react-accordion';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSettingsShellMode } from './settings-shell-context';

// The master-detail shell scrolls the window to the top when a section opens,
// so sections no longer need the `scroll-mt` calibration the sticky tab bar
// era required (its 161 px chrome budget is documented in git history).

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
  const shellMode = useSettingsShellMode();

  // Non-collapsible mode: render simple Card. The master-detail pane forces it
  // through context so the 50 call sites need no prop change; `tabIndex={-1}`
  // makes the card a programmatic focus target (a search pick lands here).
  if (!collapsible || shellMode === 'pane') {
    return (
      <Card
        id={`settings-section-${value}`}
        tabIndex={-1}
        className={cn('overflow-hidden', className)}
      >
        <CardHeader className="flex-row items-center gap-3 space-y-0 px-4 py-4 sm:gap-4 sm:px-6 sm:py-6">
          {Icon && (
            <div className="flex rounded-lg bg-primary/10 p-2 sm:p-2.5">
              <Icon className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
            </div>
          )}
          <div className="flex-1">
            <h3 className="text-base font-semibold leading-none tracking-tight sm:text-lg">
              {title}
            </h3>
            {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
          </div>
        </CardHeader>
        <CardContent className={cn('px-4 pb-4 pt-0 sm:px-6 sm:pb-6', contentClassName)}>
          {children}
        </CardContent>
      </Card>
    );
  }

  // Collapsible mode: render AccordionItem. The stable id lets deep-links
  // (settings?section=<value>) scroll to the section after expanding it.
  //
  // Everything inside the trigger is a <span>: a <button> takes phrasing
  // content only, so the CardHeader/div/h3/p it used to hold were invalid
  // markup — and the <h3> in particular duplicated every section in the
  // screen-reader heading outline, since Radix's Header already wraps the
  // trigger in one.
  return (
    <AccordionItem
      id={`settings-section-${value}`}
      value={value}
      className={cn('border-none')}
    >
      <Card className={cn('overflow-hidden', className)}>
        <AccordionPrimitive.Header className="flex">
          <AccordionPrimitive.Trigger
            className={cn(
              'flex w-full flex-1 items-center px-4 py-4 transition-colors hover:bg-accent/50 sm:px-6 sm:py-6',
              '[&[data-state=open]]:bg-accent/30',
              // The chevron is a DIRECT child of the trigger. The former
              // `>div>svg.chevron` could never match, so it never rotated.
              '[&[data-state=open]>svg.chevron]:rotate-180'
            )}
          >
            <span className="flex flex-1 items-center gap-3 sm:gap-4">
              {Icon && (
                <span className="flex rounded-lg bg-primary/10 p-2 sm:p-2.5">
                  <Icon className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
                </span>
              )}
              <span className="block flex-1 text-left">
                <span className="block text-base font-semibold leading-none tracking-tight sm:text-lg">
                  {title}
                </span>
                {description && (
                  <span className="mt-1.5 block text-sm text-muted-foreground">{description}</span>
                )}
              </span>
            </span>
            <ChevronDown className="chevron ml-3 h-5 w-5 shrink-0 text-muted-foreground transition-transform duration-200" />
          </AccordionPrimitive.Trigger>
        </AccordionPrimitive.Header>
        <AccordionContent className="px-4 pb-4 sm:px-6 sm:pb-6">
          <CardContent className={cn('p-0 pt-3 sm:pt-4', contentClassName)}>{children}</CardContent>
        </AccordionContent>
      </Card>
    </AccordionItem>
  );
}
