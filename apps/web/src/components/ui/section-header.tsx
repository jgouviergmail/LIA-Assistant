import type { ReactNode, Ref } from 'react';
import type { LucideIcon } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface SectionHeaderProps {
  id?: string;
  headingRef?: Ref<HTMLHeadingElement>;
  title: ReactNode;
  icon: LucideIcon;
  level: 1 | 2 | 3;
  description?: ReactNode;
  accessory?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Native heading and independently stacked actions. Domain state stays with its caller. */
export function SectionHeader({
  id,
  headingRef,
  title,
  icon: Icon,
  level,
  description,
  accessory,
  actions,
  className,
}: SectionHeaderProps) {
  const Heading = level === 1 ? 'h1' : level === 2 ? 'h2' : 'h3';
  return (
    <header
      className={cn(
        'min-w-0',
        level === 1 ? 'grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start' : 'space-y-3',
        className
      )}
    >
      <div className="min-w-0 space-y-2">
        <div className="flex min-w-0 items-center gap-3">
          <Heading
            id={id}
            ref={headingRef}
            tabIndex={headingRef ? -1 : undefined}
            className={cn(
              'flex min-w-0 items-center gap-2 font-semibold tracking-tight',
              level === 1 ? 'items-start text-2xl sm:text-3xl' : 'text-lg'
            )}
          >
            <Icon
              className={cn(
                'shrink-0 text-primary',
                level === 1 ? 'mt-0.5 h-7 w-7 sm:h-8 sm:w-8' : 'h-6 w-6'
              )}
              aria-hidden="true"
            />
            <span className="min-w-0 break-words">{title}</span>
          </Heading>
          {accessory && <div className="ml-auto shrink-0">{accessory}</div>}
        </div>
        {description && (
          <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <HeaderActions>{actions}</HeaderActions>}
    </header>
  );
}

/** Page actions wrap together, with equal touch targets on narrow screens. */
export function HeaderActions({ children }: { children: ReactNode }) {
  return (
    <div className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:w-auto [&>*]:min-h-11 [&>*]:flex-1 sm:[&>*]:flex-none [&_button]:min-h-11 [&_a]:min-h-11">
      {children}
    </div>
  );
}
