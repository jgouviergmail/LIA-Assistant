'use client';

import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowLeft, ArrowRight, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FEATURE_ICONS } from './chapters-data';
import { FeatureIllustration } from './FeatureIllustration';

export interface FeatureExplorerItem {
  id: string;
  title: string;
  description: string;
  sceneLabel: string;
  positionLabel: string;
}

export interface FeatureExplorerProps {
  items: readonly FeatureExplorerItem[];
  labels: { browse: string; hint: string; previous: string; next: string };
}

/**
 * A bounded visual index, followed by one complete capability at a time.
 * Two columns keep even a 17-item chapter scannable on a phone. The tablist
 * retains every title; inactive text panels stay in the DOM for indexing.
 */
export function FeatureExplorer({ items, labels }: FeatureExplorerProps) {
  const [activeId, setActiveId] = useState(items[0]?.id);
  const id = useId();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const active = Math.max(
    0,
    items.findIndex(item => item.id === activeId)
  );
  const current = items[active];

  function select(index: number, focus = false) {
    const next = (index + items.length) % items.length;
    setActiveId(items[next].id);
    if (focus) tabs.current[next]?.focus({ preventScroll: true });
    // Only reveal within the index. scrollIntoView would also move the page
    // when the reader uses the previous/next controls under the detail.
    const tab = tabs.current[next];
    const list = tab?.parentElement;
    if (tab && list) {
      const top = tab.offsetTop;
      if (top < list.scrollTop) list.scrollTop = top;
      if (top + tab.offsetHeight > list.scrollTop + list.clientHeight) {
        list.scrollTop = top + tab.offsetHeight - list.clientHeight;
      }
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const destinations: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      ArrowDown: index + 2,
      ArrowUp: index - 2,
      Home: 0,
      End: items.length - 1,
    };
    const destination = destinations[event.key];
    if (destination === undefined) return;
    event.preventDefault();
    select(destination, true);
  }

  if (!current) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-primary/20 bg-card/80">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border/60 px-5 py-4">
        <p id={`${id}-label`} className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles aria-hidden="true" className="h-4 w-4 text-primary" />
          {labels.browse}
        </p>
        <p className="text-xs leading-5 text-muted-foreground">{labels.hint}</p>
      </div>
      <div className="grid lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
        <div className="min-w-0 border-b border-border/60 bg-background/40 p-3 lg:border-b-0 lg:border-r">
          <div
            role="tablist"
            aria-labelledby={`${id}-label`}
            className="relative grid max-h-52 grid-cols-2 content-start gap-1.5 overflow-y-auto overscroll-contain p-1 lg:max-h-[29rem]"
          >
            {items.map((item, index) => {
              const Icon = FEATURE_ICONS[item.id] ?? Sparkles;
              return (
                <button
                  key={item.id}
                  ref={node => {
                    tabs.current[index] = node;
                  }}
                  id={`${id}-tab-${item.id}`}
                  type="button"
                  role="tab"
                  aria-selected={index === active}
                  aria-controls={`${id}-panel-${item.id}`}
                  tabIndex={index === active ? 0 : -1}
                  onClick={() => select(index)}
                  onKeyDown={event => onKeyDown(event, index)}
                  className={cn(
                    'flex min-h-16 items-start gap-2.5 rounded-xl border px-3 py-3 text-left text-xs leading-5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none',
                    index === active
                      ? 'border-primary/40 bg-primary/10 font-semibold text-foreground'
                      : 'border-transparent text-muted-foreground hover:border-border hover:bg-card hover:text-foreground'
                  )}
                >
                  <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 break-words">{item.title}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex min-w-0 flex-col">
          {items.map((item, index) => {
            const Icon = FEATURE_ICONS[item.id] ?? Sparkles;
            return (
              <div
                key={item.id}
                role="tabpanel"
                id={`${id}-panel-${item.id}`}
                aria-labelledby={`${id}-tab-${item.id}`}
                hidden={index !== active}
                tabIndex={0}
                className="flex-1 p-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:p-7"
              >
                {index === active && <FeatureIllustration featureKey={item.id} />}
                <p className="mt-3 text-xs font-medium text-primary">{item.sceneLabel}</p>
                <h4 className="mt-3 flex items-start gap-2.5 text-lg font-semibold leading-7 tracking-tight">
                  <Icon aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-primary" />
                  {item.title}
                </h4>
                <p className="mt-3 max-w-[65ch] text-sm leading-7 text-muted-foreground">
                  {item.description}
                </p>
              </div>
            );
          })}
          <div className="flex items-center justify-between gap-3 border-t border-border/60 px-5 py-3 sm:px-7">
            <button
              type="button"
              onClick={() => select(active - 1)}
              aria-label={labels.previous}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background text-primary transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            </button>
            <p
              aria-live="polite"
              aria-atomic="true"
              className="text-xs tabular-nums text-muted-foreground"
            >
              {current.positionLabel}
            </p>
            <button
              type="button"
              onClick={() => select(active + 1)}
              aria-label={labels.next}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-background text-primary transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
