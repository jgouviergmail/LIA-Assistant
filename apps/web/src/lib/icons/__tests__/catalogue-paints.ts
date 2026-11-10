/** Read reachable SVG paints; unused definitions cannot satisfy the color guard. */
export function parseArtwork(body: string): Document {
  return new DOMParser().parseFromString(
    `<svg xmlns="http://www.w3.org/2000/svg" fill="none">${body}</svg>`,
    'image/svg+xml'
  );
}

function inherited(element: Element, attribute: string, fallback: string): string {
  const value = element.getAttribute(attribute);
  if (value && value !== 'inherit') return value;
  return element.parentElement ? inherited(element.parentElement, attribute, fallback) : fallback;
}

function paintColors(value: string, document: Document, seen = new Set<string>()): string[] {
  if (/^#[\da-f]{3}(?:[\da-f]{3})?$/i.test(value)) return [value];
  const id = value.match(/^url\(#([^)]+)\)$/)?.[1];
  if (!id || seen.has(id)) return [];
  seen.add(id);
  const server = document.getElementById(id);
  if (!server) return [];
  const stops = [...server.querySelectorAll('stop')]
    .filter(stop => Number(stop.getAttribute('stop-opacity') ?? 1) > 0)
    .flatMap(stop => paintColors(stop.getAttribute('stop-color') ?? '', document, seen));
  const href = server.getAttribute('href') ?? server.getAttribute('xlink:href');
  return [...stops, ...(href ? paintColors(`url(${href})`, document, seen) : [])];
}

export function reachableColors(document: Document): string[] {
  return [...document.querySelectorAll('path,rect,circle,ellipse,line,polyline,polygon,use')]
    .filter(element => !element.closest('defs,clipPath,mask,filter'))
    .filter(element => inherited(element, 'opacity', '1') !== '0')
    .flatMap(element =>
      ['fill', 'stroke'].flatMap(attribute => {
        if (inherited(element, `${attribute}-opacity`, '1') === '0') return [];
        return paintColors(inherited(element, attribute, 'none'), document);
      })
    );
}

export function colorHue(color: string): number | null {
  const digits = color.slice(1);
  const hex = digits.length === 3 ? [...digits].map(value => value + value).join('') : digits;
  const [red, green, blue] = [0, 2, 4].map(
    index => parseInt(hex.slice(index, index + 2), 16) / 255
  );
  const high = Math.max(red, green, blue);
  const delta = high - Math.min(red, green, blue);
  // Saturated inks and visibly tinted pastel surfaces count; grayscale does not.
  if (delta < 0.08) return null;
  const sector =
    high === red
      ? (green - blue) / delta
      : high === green
        ? (blue - red) / delta + 2
        : (red - green) / delta + 4;
  return (sector * 60 + 360) % 360;
}

export function hasDifferentHues(colors: string[]): boolean {
  const hues = colors.map(colorHue).filter(hue => hue !== null);
  return hues.some((hue, index) =>
    hues.slice(index + 1).some(other => {
      const distance = Math.abs(hue - other);
      return Math.min(distance, 360 - distance) >= 25;
    })
  );
}

export function contrast(first: string, second: string): number {
  const luminance = (hex: string) => {
    const [red, green, blue] = [1, 3, 5].map(index => {
      const channel = parseInt(hex.slice(index, index + 2), 16) / 255;
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
    });
    return red * 0.2126 + green * 0.7152 + blue * 0.0722;
  };
  const values = [luminance(first), luminance(second)].sort((a, b) => a - b);
  return (values[1] + 0.05) / (values[0] + 0.05);
}
