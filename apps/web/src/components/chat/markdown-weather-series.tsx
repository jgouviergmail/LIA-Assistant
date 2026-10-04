'use client';

import { createContext, useContext, useId, type ComponentPropsWithoutRef } from 'react';
import type { ExtraProps } from 'react-markdown';
import { hasSearchMatch } from './markdown-search-matches';

const WeatherSeriesName = createContext<string | undefined>(undefined);

export function useWeatherSeriesName(): string | undefined {
  return useContext(WeatherSeriesName);
}

/** Native exclusive disclosures are scoped to this mounted, immutable message. */
export function MarkdownWeatherSeries({
  node,
  ...props
}: ComponentPropsWithoutRef<'div'> & ExtraProps) {
  const name = useId();
  return (
    <WeatherSeriesName.Provider value={hasSearchMatch(node) ? undefined : name}>
      <div {...props} />
    </WeatherSeriesName.Provider>
  );
}
