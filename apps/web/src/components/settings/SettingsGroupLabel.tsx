import { cn } from '@/lib/utils';

interface SettingsGroupLabelProps {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  className?: string;
}

/**
 * Group separator for the settings sections — a real heading, not a decoration.
 *
 * It looks like a divider, but it is what turns ~30 stacked sections into a few
 * named groups. As a `<span>` it was invisible to a screen reader's heading
 * navigation, which then jumped straight from the page `<h1>` to each section's
 * `<h3>` with nothing in between. `<h2>` restores h1 → h2 → h3 and makes the
 * page navigable by structure. Styling is unchanged.
 */
export function SettingsGroupLabel({ label, icon: Icon, className }: SettingsGroupLabelProps) {
  return (
    <div className={cn('flex items-center gap-3 pt-6 pb-2 first:pt-0', className)}>
      {Icon && <Icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />}
      <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground whitespace-nowrap">
        {label}
      </h2>
      <div className="flex-1 border-t border-border/50" aria-hidden="true" />
    </div>
  );
}
