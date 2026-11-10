/** Deterministic LIA Soft/Flat painting of explicitly registered Lucide geometry. */
import { renderSpecialArtwork } from './lia-special-artwork.mjs';
import { renderControlArtwork } from './lia-control-artwork.mjs';

export const LIA_PALETTES = {
  general: { primary: '#2469A3', secondary: '#965BC2', surface: '#E0CEED', detail: '#356B98' },
  document: { primary: '#31719E', secondary: '#A467C8', surface: '#E4D1EF', detail: '#3D729A' },
  people: { primary: '#23786F', secondary: '#7A64B9', surface: '#D7D1EA', detail: '#397D79' },
  health: { primary: '#AB546E', secondary: '#5A7CC3', surface: '#CED8ED', detail: '#6A659F' },
  nature: { primary: '#23778C', secondary: '#A571C6', surface: '#E4D4EE', detail: '#38768B' },
  communication: {
    primary: '#336DA8',
    secondary: '#A868BD',
    surface: '#E5D2EB',
    detail: '#426BA5',
  },
  type: { primary: '#4069A3', secondary: '#AA62B1', surface: '#E6D0E8', detail: '#6B5BA7' },
  money: { primary: '#2E7C65', secondary: '#CC8D2C', surface: '#F0DDC0', detail: '#418879' },
  travel: { primary: '#307E82', secondary: '#9670BD', surface: '#E0D4EB', detail: '#4B78A2' },
  danger: { primary: '#AC454F', secondary: '#E79838', surface: '#F8E0C3', detail: '#B9595D' },
  warning: { primary: '#A96014', secondary: '#CD515F', surface: '#F0CBCF', detail: '#AA5D42' },
  success: { primary: '#207A60', secondary: '#497EC5', surface: '#C8D8EE', detail: '#317D78' },
};

export function svgNode([tag, attributes], extra = {}) {
  const attrs = Object.entries({ ...attributes, ...extra })
    .map(
      ([key, value]) => `${key.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`)}="${value}"`
    )
    .join(' ');
  return `<${tag} ${attrs}/>`;
}

export function liaArtwork(name, geometry, recipe, style) {
  const data = geometry[name];
  if (!data || !recipe) throw new Error(`Missing explicit LIA recipe: ${name}`);
  const paint = LIA_PALETTES[recipe.family];
  if (!paint) throw new Error(`Unknown paint family: ${name}/${recipe.family}`);
  const definitions = new Map();
  const gradient = (key, first, last, force = false) => {
    if (style === 'flex' && !force) return last;
    const id = `lia-${key}`;
    definitions.set(
      id,
      `<linearGradient id="${id}" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse"><stop stop-color="${first}"/><stop offset="1" stop-color="${last}"/></linearGradient>`
    );
    return `url(#${id})`;
  };
  const clip = (body, key = 'shape') => {
    const id = `lia-clip-${key}`;
    definitions.set(id, `<clipPath id="${id}">${body}</clipPath>`);
    return `url(#${id})`;
  };
  const context = {
    data,
    geometry,
    paint,
    node: svgNode,
    clip,
    gradient: (key, first, last) => gradient(key, first, last, key === 'outline'),
  };
  let body = renderControlArtwork(name, context) ?? renderSpecialArtwork(name, context);
  if (body === null) {
    if (recipe.parts.length !== data.node.length)
      throw new Error(`Paint parts differ from geometry: ${name}`);
    const oneContour = data.node.length === 1;
    const multicolorStroke = oneContour
      ? gradient('contour', paint.primary, paint.secondary, true)
      : null;
    const parts = recipe.parts.map(part => {
      const entry = data.node[part.index];
      if (!entry) throw new Error(`Missing paint part ${name}/${part.index}`);
      if (!['surface', 'detail'].includes(part.layer))
        throw new Error(`Missing paint layer ${name}/${part.index}`);
      return {
        entry,
        layer: part.layer,
        fill:
          part.fill === 'surface'
            ? gradient(`surface-${part.index}`, '#F9F6FC', paint.surface)
            : (paint[part.fill] ?? 'none'),
        stroke: oneContour ? multicolorStroke : paint[part.stroke],
      };
    });
    // Source node order assumes transparent strokes. Paint surfaces underneath
    // every detail so a later enclosure cannot erase its keys, windows or arrow.
    body =
      ['surface', 'detail']
        .map(layer =>
          parts
            .filter(part => part.layer === layer && part.fill !== 'none')
            .map(part => svgNode(part.entry, { fill: part.fill, stroke: 'none' }))
            .join('')
        )
        .join('') +
      parts.map(part => svgNode(part.entry, { fill: 'none', stroke: part.stroke })).join('');
  }
  // No fill on this ancestor: stateful paths inherit the SVG root's fill,
  // including CSS rules applied through their containing button.
  return {
    body: `<defs>${[...definitions.values()].join('')}</defs><g stroke-linecap="round" stroke-linejoin="round" stroke-width="${style === 'fluent' ? 1.65 : 1.8}">${body}</g>`,
    viewBox: `0 0 ${data.size} ${data.size}`,
  };
}
