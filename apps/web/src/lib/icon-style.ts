/** Account-owned icon vocabulary, shared by the selector and every renderer. */
export const ICON_STYLES = ['lucide', 'fluent', 'flex'] as const;
export type IconStyle = (typeof ICON_STYLES)[number];
export const DEFAULT_ICON_STYLE: IconStyle = 'fluent';

/** Only the fields acknowledged by an icon preference mutation. */
export interface IconStyleUpdate {
  id: string;
  icon_style: IconStyle;
}

export function isIconStyle(value: unknown): value is IconStyle {
  return ICON_STYLES.some(style => style === value);
}

/** Reviewed, checked-in SVG artwork; never populated from a message or an API. */
export interface IconArtwork {
  readonly body: string;
  readonly viewBox: string;
}

/** SVG paint servers share the document namespace, even across separate SVGs. */
export function scopeIconArtwork(body: string, prefix: string): string {
  return body
    .replace(/\bid="([^"]+)"/g, (_, id: string) => `id="${prefix}-${id}"`)
    .replace(/url\(#([^)]+)\)/g, (_, id: string) => `url(#${prefix}-${id})`)
    .replace(
      /\b(xlink:href|href)="#([^"]+)"/g,
      (_, attr: string, id: string) => `${attr}="#${prefix}-${id}"`
    );
}
