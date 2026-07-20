import type { LucideIcon } from 'lucide-react';

interface GuideTocProps {
  items: { id: string; label: string; icon?: LucideIcon }[];
}

export function GuideToc({ items }: GuideTocProps) {
  return (
    <nav className="mb-12 p-6 rounded-xl bg-muted/40 border border-border/50">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">
        Table des matières
      </h2>
      <ol className="columns-1 sm:columns-2 gap-x-8 space-y-1.5">
        {items.map((item, i) => {
          const Icon = item.icon;
          return (
            <li key={item.id} className="break-inside-avoid">
              <a
                href={`#${item.id}`}
                className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors"
              >
                {Icon && <Icon className="w-3.5 h-3.5 shrink-0 text-primary/60" />}
                <span>
                  {i + 1}. {item.label}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
