'use client';

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { AccordionContent, AccordionItem } from '@/components/ui/accordion';
import * as AccordionPrimitive from '@radix-ui/react-accordion';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Offset kept above a section when a deep link scrolls to it.
 *
 * `scrollIntoView({ block: 'start' })` lands the element at the very top of the
 * viewport — underneath the whole sticky chrome. Before ADR-171 nothing was
 * actually sticky, so this went unnoticed.
 *
 * The budget, in the order the pixels stack:
 *
 *   dashboard header  `h-16`                        64
 *   tab bar  `py-2` top                              8
 *            `TabsList h-9`                         36
 *            search row `mt-2`                       8
 *            search input `h-9`                     36
 *            `py-2` bottom                           8
 *            `border-b`                              1
 *   ------------------------------------------------
 *   bottom of the sticky chrome                    161
 *   `scroll-mt-44` (11rem)                         176  → 15 px of air
 *
 * Measured in the browser rather than trusted from the arithmetic (2026-07-28,
 * Chromium, `/fr/dashboard/settings?section=voice-mode`): the sticky bar spans
 * y 64 → 161 for a height of 97, `scroll-margin-top` resolves to 176 px, and the
 * deep-linked section lands at exactly 176 — 15 px clear of the bar.
 *
 * It was `scroll-mt-32` (128) against a 117 px chrome until the search field
 * joined the bar. Whatever that bar contains must keep a CONSTANT height, since
 * one number here serves every section.
 *
 * `e2e/smoke/settings-sticky-tabs.spec.ts` holds it, against the sticky
 * CONTAINER — deliberately not against the tab list, whose bottom edge stopped
 * being the bottom of the chrome the day this second row appeared.
 */
const SCROLL_MARGIN = 'scroll-mt-44';

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
      <Card
        id={`settings-section-${value}`}
        className={cn('overflow-hidden', SCROLL_MARGIN, className)}
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
      className={cn('border-none', SCROLL_MARGIN)}
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
