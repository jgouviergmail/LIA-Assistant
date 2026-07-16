'use client';

import { useCallback, useId, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Minimal accessible tabs for the editorial landing (day timeline, gallery,
 * under-the-hood). Native WAI-ARIA tabs pattern: roving tabindex, arrow-key
 * navigation with Home/End, `aria-selected`, labelled panels. Panels stay in
 * the DOM (hidden attribute) so crawlers index every tab's content.
 */

export interface TabItem {
  id: string;
  label: string;
  content: React.ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  /** Accessible name of the tablist. */
  label: string;
  className?: string;
  /** Center (default) or left-align the tab bar. */
  align?: 'center' | 'start';
}

export function Tabs({ items, label, className, align = 'center' }: TabsProps) {
  const [active, setActive] = useState(0);
  const baseId = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const focusTab = useCallback(
    (index: number) => {
      const next = (index + items.length) % items.length;
      setActive(next);
      tabRefs.current[next]?.focus();
    },
    [items.length]
  );

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault();
        focusTab(index + 1);
        break;
      case 'ArrowLeft':
        event.preventDefault();
        focusTab(index - 1);
        break;
      case 'Home':
        event.preventDefault();
        focusTab(0);
        break;
      case 'End':
        event.preventDefault();
        focusTab(items.length - 1);
        break;
    }
  };

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        className={cn(
          'flex flex-wrap gap-2',
          align === 'center' ? 'justify-center' : 'justify-start'
        )}
      >
        {items.map((item, i) => (
          <button
            key={item.id}
            ref={el => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            id={`${baseId}-tab-${item.id}`}
            aria-selected={i === active}
            aria-controls={`${baseId}-panel-${item.id}`}
            tabIndex={i === active ? 0 : -1}
            onClick={() => setActive(i)}
            onKeyDown={e => onKeyDown(e, i)}
            className={cn(
              'rounded-full border px-4 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              i === active
                ? 'border-primary bg-primary font-semibold text-primary-foreground'
                : 'border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground'
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map((item, i) => (
        <div
          key={item.id}
          role="tabpanel"
          id={`${baseId}-panel-${item.id}`}
          aria-labelledby={`${baseId}-tab-${item.id}`}
          hidden={i !== active}
          tabIndex={0}
          className="mt-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
        >
          {item.content}
        </div>
      ))}
    </div>
  );
}
