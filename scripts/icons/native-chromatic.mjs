/** Multicolor adaptations of trusted native artwork; the source geometry never changes. */
import { LIA_PALETTES } from './lia-artwork.mjs';

export function colorHue(hex) {
  const digits = hex.slice(1);
  const full = digits.length === 3 ? [...digits].map(value => value + value).join('') : digits;
  const [red, green, blue] = [0, 2, 4].map(
    index => parseInt(full.slice(index, index + 2), 16) / 255
  );
  const high = Math.max(red, green, blue);
  const low = Math.min(red, green, blue);
  const delta = high - low;
  if (delta < 0.08 || high === 0 || delta / high < 0.18) return null;
  const sector =
    high === red
      ? (green - blue) / delta
      : high === green
        ? (blue - red) / delta + 2
        : (red - green) / delta + 4;
  return (sector * 60 + 360) % 360;
}

export function hasChromaticPair(colors) {
  const hues = [...new Set(colors)].map(colorHue).filter(hue => hue !== null);
  return hues.some((hue, index) =>
    hues.slice(index + 1).some(other => {
      const difference = Math.abs(hue - other);
      return Math.min(difference, 360 - difference) >= 25;
    })
  );
}

const FLEX_FAMILIES = {
  lavender: 'general',
  chat: 'communication',
  world: 'travel',
  tools: 'money',
  people: 'people',
  blue: 'general',
  meetings: 'document',
  amber: 'warning',
  settings: 'general',
  help: 'communication',
  palette: 'communication',
  language: 'type',
  calendar: 'health',
  mail: 'communication',
  green: 'success',
  weather: 'nature',
  document: 'document',
  shield: 'success',
  destructive: 'danger',
};

// These native tones are two exposed objects/arms, not foreground over a panel.
const FLEX_TWO_INKS = {
  'button-power-1-flat': '#965BC2',
  'expand-crop-resize-flat': '#965BC2',
  'screwdriver-wrench-flat': '#A57122',
};

function gradient(primary, secondary, viewBox, id = 'lia-native-color') {
  const [, , width, height] = viewBox.split(' ').map(Number);
  return `<linearGradient id="${id}" x1="0" y1="0" x2="${width}" y2="${height}" gradientUnits="userSpaceOnUse"><stop stop-color="${primary}"/><stop offset="1" stop-color="${secondary}"/></linearGradient>`;
}

function linearChannels(color) {
  const value = color.slice(1);
  const full =
    value.length === 3 ? [...value].map(character => character + character).join('') : value;
  return [0, 2, 4].map(index => {
    const channel = parseInt(full.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
}

const luminance = ([red, green, blue]) => red * 0.2126 + green * 0.7152 + blue * 0.0722;

/** Preserve each native paint's luminance so recoloring cannot erase its detail. */
export function tintWithOriginalLuminance(original, hue) {
  const target = luminance(linearChannels(original));
  const hueChannels = linearChannels(hue);
  const peak = Math.max(...hueChannels);
  const channels = hueChannels.map(channel => channel / peak);
  const base = luminance(channels);
  const tinted = channels.map(channel =>
    target >= base
      ? channel + ((1 - channel) * (target - base)) / (1 - base)
      : (channel * target) / base
  );
  return (
    '#' +
    tinted
      .map(channel => {
        const srgb = channel <= 0.0031308 ? channel * 12.92 : 1.055 * channel ** (1 / 2.4) - 0.055;
        return Math.round(srgb * 255)
          .toString(16)
          .padStart(2, '0');
      })
      .join('')
  );
}

function gearHub(body, viewBox) {
  const [, , width] = viewBox.split(' ').map(Number);
  const center = width / 2;
  const contour = body.match(/<path\b[^>]*\bd="[^"]+"[^>]*\/?\s*>/)?.[0];
  if (!contour) throw new Error('Native gear is missing its declared contour');
  // Color an annulus within the existing gear silhouette; its hole stays empty.
  const clipping = contour.replace(/\sfill="[^"]*"/g, '');
  return (
    `${body}<defs><clipPath id="lia-gear-hub">${clipping}</clipPath></defs>` +
    `<circle cx="${center}" cy="${center}" r="${width * 0.18}" fill="none" stroke="#E6A632" stroke-width="${width * 0.075}" clip-path="url(#lia-gear-hub)"/>`
  );
}

function recolorGradient(block, allNeutral, paint) {
  const colors = [...block.matchAll(/stop-color="(#[\da-f]{3,8})"/gi)].map(match => match[1]);
  // White/dark foreground gradients are legibility layers, not color surfaces.
  const lightForeground = colors.every(color =>
    linearChannels(color).every(channel => channel >= 0.54)
  );
  if (!allNeutral && (lightForeground || colors.every(color => colorHue(color) === null)))
    return block;
  let stop = 0;
  return block.replace(
    /stop-color="(#[\da-f]{3,8})"/gi,
    (_, color) =>
      `stop-color="${tintWithOriginalLuminance(color, stop++ % 2 === 0 ? paint.primary : paint.secondary)}"`
  );
}

function flexArtwork(source, artwork, paletteName) {
  const paint = LIA_PALETTES[FLEX_FAMILIES[paletteName] ?? 'general'];
  const twoParts = artwork.body.includes('#2859c5') && artwork.body.includes('#8fbffa');
  const body = twoParts
    ? artwork.body
        .replaceAll('#2859c5', paint.primary)
        .replaceAll('#8fbffa', FLEX_TWO_INKS[source] ?? paint.surface)
    : `<defs>${gradient(paint.primary, paint.secondary, artwork.viewBox)}</defs>` +
      artwork.body.replace(/fill="#(?:2859c5|8fbffa)"/g, 'fill="url(#lia-native-color)"');
  return {
    ...artwork,
    body: source === 'cog-flat' ? gearHub(body, artwork.viewBox) : body,
    adapted: true,
    adaptation:
      source === 'cog-flat'
        ? 'LIA two-hue gear with contrasting hub colored within its original silhouette'
        : twoParts
          ? FLEX_TWO_INKS[source]
            ? 'LIA distinct inks on separate visible arms/objects'
            : 'LIA contrasting ink and chromatic surface'
          : 'LIA two-hue paint across the original single-tone shape',
  };
}

function fluentArtwork(source, artwork) {
  const colors = [...artwork.body.matchAll(/(?:fill|stroke|stop-color)="(#[\da-f]{3,8})"/gi)].map(
    match => match[1]
  );
  if (hasChromaticPair(colors)) return { ...artwork, adapted: false };
  const family = /error|dismiss/.test(source)
    ? 'danger'
    : /warning|urgent/.test(source)
      ? 'warning'
      : /check/.test(source)
        ? 'success'
        : 'general';
  const paint = LIA_PALETTES[family];
  const allNeutral = colors.every(color => colorHue(color) === null);
  const directPaints = new Map();
  const body = artwork.body
    .replace(/<(linearGradient|radialGradient)\b[\s\S]*?<\/\1>/g, block =>
      recolorGradient(block, allNeutral, paint)
    )
    .replace(/(fill|stroke)="(#[\da-f]{3,8})"/gi, (match, attribute, color) => {
      if (!allNeutral && colorHue(color) === null) return match;
      if (!directPaints.has(color)) {
        const id = `lia-native-color-${directPaints.size}`;
        directPaints.set(color, {
          id,
          body: gradient(
            tintWithOriginalLuminance(color, paint.primary),
            tintWithOriginalLuminance(color, paint.secondary),
            artwork.viewBox,
            id
          ),
        });
      }
      return `${attribute}="url(#${directPaints.get(color).id})"`;
    });
  const painted = `<defs>${[...directPaints.values()].map(paint => paint.body).join('')}</defs>${body}`;
  return {
    ...artwork,
    body: source === 'settings' ? gearHub(painted, artwork.viewBox) : painted,
    adapted: true,
    adaptation:
      'LIA multicolor tint preserves each original paint luminance and contrasting foreground; original SVG geometry retained',
  };
}

export function nativeArtwork(style, source, artwork, paletteName) {
  return style === 'flex'
    ? flexArtwork(source, artwork, paletteName)
    : fluentArtwork(source, artwork);
}
