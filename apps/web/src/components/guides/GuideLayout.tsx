interface GuideSectionProps {
  id: string;
  title: string;
  children: React.ReactNode;
}

export function GuideSection({ id, title, children }: GuideSectionProps) {
  return (
    <section id={id} className="mb-12 scroll-mt-24">
      <h2 className="text-xl sm:text-2xl font-bold tracking-tight mb-6 text-foreground border-b border-border/50 pb-3">
        {title}
      </h2>
      <div className="space-y-4 text-[0.938rem] leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  );
}

interface GuideSubSectionProps {
  title: string;
  children: React.ReactNode;
}

export function GuideSubSection({ title, children }: GuideSubSectionProps) {
  return (
    <div className="mt-6 mb-4">
      <h3 className="text-base sm:text-lg font-semibold tracking-tight mb-3 text-foreground">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

export function GuideP({ children }: { children: React.ReactNode }) {
  return <p className="text-muted-foreground leading-relaxed">{children}</p>;
}

export function GuideBold({ children }: { children: React.ReactNode }) {
  return <strong className="text-foreground font-semibold">{children}</strong>;
}

export function GuideQuote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote className="border-l-4 border-primary/30 pl-4 py-2 my-4 italic text-muted-foreground bg-muted/30 rounded-r-lg">
      {children}
    </blockquote>
  );
}

interface GuideTableProps {
  headers: string[];
  rows: string[][];
}

export function GuideTable({ headers, rows }: GuideTableProps) {
  return (
    <div className="overflow-x-auto my-4">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-border">
            {headers.map((h, i) => (
              <th key={i} className="text-left py-2 px-3 font-semibold text-foreground">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50">
              {row.map((cell, j) => (
                <td
                  key={j}
                  className="py-2 px-3 text-muted-foreground"
                  dangerouslySetInnerHTML={{ __html: cell }}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GuideList({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="list-disc list-outside ml-5 space-y-1.5 text-muted-foreground">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

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

export function GuideCode({ children }: { children: string }) {
  return (
    <pre className="my-4 p-4 rounded-lg bg-muted/60 border border-border/50 overflow-x-auto text-xs leading-relaxed font-mono text-foreground">
      {children}
    </pre>
  );
}
