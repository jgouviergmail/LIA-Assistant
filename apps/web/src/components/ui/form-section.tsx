/**
 * A named group of fields, carrying the theme icon its title owes.
 *
 * The pattern it replaces is written 68 times across this application by hand
 * — `<Icon className="h-4 w-4 text-primary" />` beside a heading — with no
 * shared component. This is that component; it does not migrate the other
 * sites, it gives them somewhere to converge.
 *
 * `fieldset`/`legend` rather than a styled `div`: it makes the fields inside
 * an announced GROUP, which is what a form asking two different questions
 * ("what to do", "when") needs to stop reading as one undifferentiated column
 * of inputs. No border on the fieldset, so the legend flows as a normal block
 * instead of sitting on a rule.
 *
 * It resolves no string of its own: it has no domain, therefore no vocabulary
 * — the caller passes an already-translated title, the way `Skeleton` takes
 * its label (`apps/web/CLAUDE.md`).
 */

import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

export interface FormSectionProps {
  /** The group's icon. Decorative: it repeats the title. */
  icon: LucideIcon;
  /** The group's name, already translated by the caller. */
  title: string;
  /** The fields. */
  children: ReactNode;
  /** Extra classes for the group's own spacing. */
  className?: string;
}

export function FormSection({ icon: Icon, title, children, className }: FormSectionProps) {
  return (
    <fieldset className={className ?? 'space-y-4'}>
      <legend className="mb-3 flex items-center gap-2 text-sm font-medium text-foreground">
        <Icon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {title}
      </legend>
      {children}
    </fieldset>
  );
}
