import { cn } from '@/lib/utils';

interface SettingsGroupLabelProps {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  className?: string;
}

/**
 * Lightweight visual separator for grouping settings sections within an accordion.
 * Renders a label with a horizontal divider line.
 */
export function SettingsGroupLabel({ label, icon: Icon, className }: SettingsGroupLabelProps) {
  return (
    <div className={cn('flex items-center gap-3 pt-6 pb-2 first:pt-0', className)}>
      {Icon && <Icon className="h-4 w-4 text-muted-foreground/70" />}
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70 whitespace-nowrap">
        {label}
      </span>
      <div className="flex-1 border-t border-border/50" />
    </div>
  );
}
