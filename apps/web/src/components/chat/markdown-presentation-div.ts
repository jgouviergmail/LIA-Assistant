import { MarkdownCardBinding } from './markdown-card-actions';
import { MarkdownWeatherSeries } from './markdown-weather-series';
import { MarkdownRouteMap } from './markdown-route-map';

/** One dispatch seam keeps presentation branches outside the Markdown parser. */
export function cardDivComponent(className: string | undefined) {
  const classes = new Set(className?.split(/\s+/));
  if (classes.has('lia-card-binding')) return MarkdownCardBinding;
  if (classes.has('lia-weather-series')) return MarkdownWeatherSeries;
  if (classes.has('lia-route-map')) return MarkdownRouteMap;
  return null;
}
