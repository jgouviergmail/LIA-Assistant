'use client';

import {
  Children,
  isValidElement,
  useState,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from 'react';
import type { ExtraProps } from 'react-markdown';
import { hasSearchMatch } from './markdown-search-matches';
import { useWeatherSeriesName } from './markdown-weather-series';

type DetailsProps = ComponentPropsWithoutRef<'details'>;

function DeferredCardDetails({
  summary,
  foldedChildren,
  ...props
}: DetailsProps & { summary: ReactNode; foldedChildren: ReactNode[] }) {
  // Monotone: preserve child state and cached media after the first reveal.
  const [activated, setActivated] = useState(Boolean(props.open));
  return (
    <details
      {...props}
      onToggle={event => {
        if (event.currentTarget.open) setActivated(true);
      }}
    >
      {summary}
      {activated || props.open ? foldedChildren : null}
    </details>
  );
}

export function MarkdownCardDetails({ node, children, ...props }: DetailsProps & ExtraProps) {
  const weatherSeriesName = useWeatherSeriesName();
  const parts = Children.toArray(children);
  const summary = parts.find(part => isValidElement(part) && part.type === 'summary');
  const open = hasSearchMatch(node) || props.open;
  if (props.className?.split(/\s+/).includes('lia-card-collection') && summary) {
    return (
      <DeferredCardDetails
        {...props}
        open={open}
        summary={summary}
        foldedChildren={parts.filter(part => part !== summary)}
      />
    );
  }
  return (
    <details
      {...props}
      name={
        props.className?.split(/\s+/).includes('lia-weather-slot') ? weatherSeriesName : undefined
      }
      open={open}
    >
      {children}
    </details>
  );
}
