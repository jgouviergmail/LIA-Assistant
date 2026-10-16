import type { ReactNode, Ref } from 'react';
import type { LucideIcon } from 'lucide-react';
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
    <header className={cn('min-w-0 space-y-3', className)}>
      <div className="flex min-w-0 items-center gap-3">
        <Heading
          id={id}
          ref={headingRef}
          tabIndex={headingRef ? -1 : undefined}
          className={cn(
            'flex min-w-0 items-center gap-2 font-semibold tracking-tight',
            level === 1 ? 'text-2xl' : 'text-lg'
          )}
        >
          <Icon className="h-6 w-6 shrink-0 text-primary" aria-hidden="true" />
          {title}
        </Heading>
        {accessory && <div className="ml-auto shrink-0">{accessory}</div>}
      </div>
      {description && (
        <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
      )}
      {actions && <div className="flex flex-col items-stretch gap-2 sm:items-start">{actions}</div>}
    </header>
  );
}
