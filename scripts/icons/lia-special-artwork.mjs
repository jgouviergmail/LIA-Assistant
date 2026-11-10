/** Authored LIA color zones for objects and stateful shapes; source geometry is Lucide ISC. */
function splitContour(entry, { node, paint, clip }) {
  return (
    node(entry, {
      fill: 'none',
      stroke: paint.primary,
      'stroke-width': 1.8,
      'clip-path': clip('<rect x="0" y="0" width="12" height="24"/>', 'left'),
    }) +
    node(entry, {
      fill: 'none',
      stroke: paint.secondary,
      'stroke-width': 1.8,
      'clip-path': clip('<rect x="12" y="0" width="12" height="24"/>', 'right'),
    })
  );
}

function stateShape(context) {
  return (
    context.draw(0, { fill: 'inherit', stroke: 'none' }) +
    splitContour(context.data.node[0], context)
  );
}

function halfStar(context) {
  const { draw, geometry } = context;
  return (
    draw(0, { fill: 'inherit', stroke: 'none' }) +
    '<path d="M12 2v16.338" fill="none" stroke="#965BC2" stroke-width="1.25"/>' +
    splitContour(geometry.Star.node[0], context)
  );
}

function pin(context) {
  const { draw, paint, data } = context;
  return (
    draw(0, { fill: 'none', stroke: paint.secondary }) +
    draw(1, { fill: 'inherit', stroke: 'none' }) +
    splitContour(data.node[1], context)
  );
}

function recordingDisc({ draw }) {
  // The caller owns the recording ring's live red/pulse state. Its center
  // remains genuinely colored even when that ring follows a neutral color.
  return (
    draw(0, { fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8 }) +
    '<circle cx="12" cy="12" r="7.2" fill="#6267BB" stroke="#2875B5" stroke-width="1.5"/>' +
    draw(1, { fill: '#F8C86A', stroke: '#2875B5', 'stroke-width': 1.6 })
  );
}

function circleDot({ draw, paint }) {
  return (
    draw(1, { fill: paint.surface, stroke: 'currentColor' }) +
    draw(0, { fill: paint.primary, stroke: paint.primary, 'stroke-width': 2.1 })
  );
}

function copy({ draw, gradient }) {
  return (
    `<rect x="2" y="2" width="14" height="14" rx="2" fill="${gradient('rear', '#D9B4FF', '#8854BA')}" stroke="#8854BA"/>` +
    draw(0, { fill: gradient('front', '#C8EEFF', '#55A8EB'), stroke: '#2875B5' })
  );
}

function bookmark({ data, node, clip, gradient, draw }) {
  const boundary = node(data.node[0]);
  return (
    `<rect x="4" y="2" width="16" height="5.5" fill="${gradient('band', '#DDB7FF', '#8854BA')}" clip-path="${clip(boundary)}"/>` +
    draw(0, { fill: 'none', stroke: '#2875B5', 'stroke-width': 1.8 })
  );
}

function bookmarkCheck({ draw }) {
  return (
    draw(0, { fill: '#D7C7EE', stroke: '#2875B5', 'stroke-width': 1.8 }) +
    draw(1, { fill: 'none', stroke: '#278568', 'stroke-width': 2.2 })
  );
}

function thumb({ name, data, node, clip, gradient, draw }) {
  const clipping = clip(node(data.node[0]));
  const down = name === 'ThumbsDown';
  return (
    draw(0, { fill: gradient('skin', '#FFDFAB', '#EAAF6C'), stroke: '#B27539' }) +
    `<rect x="${down ? 17 : 0}" y="${down ? 0 : 10}" width="7" height="24" fill="${gradient('cuff', '#A6BBFF', '#6179CE')}" clip-path="${clipping}"/>` +
    draw(0, { fill: 'none', stroke: '#B27539' }) +
    draw(1, { fill: 'none', stroke: '#425CA9' }) +
    `<circle cx="${down ? 19.7 : 4.3}" cy="${down ? 5.2 : 18.8}" r=".65" fill="#EEF3FF" stroke="none"/>`
  );
}

function radio({ data, node }) {
  return data.node
    .map((entry, index) =>
      node(
        entry,
        index === 4
          ? { fill: '#F8C86A', stroke: '#D28A2C', 'stroke-width': 1.2 }
          : {
              fill: 'none',
              stroke: index === 0 || index === 3 ? '#8854BA' : '#2875B5',
              'stroke-width': 2.3,
            }
      )
    )
    .join('');
}

function moon({ data, node, clip, gradient, draw }) {
  const clipping = clip(node(data.node[0]));
  return (
    draw(0, {
      fill: gradient('moon', '#FFE69E', '#F8C86A'),
      stroke: '#2875B5',
      'stroke-width': 1.3,
    }) +
    `<path d="M3 12a9 9 0 0 0 18 0" fill="none" stroke="#D28A2C" stroke-width="3.3" clip-path="${clipping}"/>` +
    draw(0, { fill: 'none', stroke: '#2875B5', 'stroke-width': 1.2 })
  );
}

function foldedMap({ data, node, clip, gradient, draw }) {
  const clipping = clip(node(data.node[0]));
  return (
    `<g clip-path="${clipping}"><rect x="0" y="0" width="9" height="24" fill="${gradient('west', '#9CE9CD', '#58B59D')}"/><rect x="9" y="0" width="6" height="24" fill="${gradient('middle', '#B7DFFF', '#55A8EB')}"/><rect x="15" y="0" width="9" height="24" fill="${gradient('east', '#D9BAF2', '#AB82C7')}"/></g>` +
    draw(0, { fill: 'none', stroke: '#426C85', 'stroke-width': 1.1 }) +
    draw(1, { fill: 'none', stroke: '#5F82A8', 'stroke-width': 1.1 }) +
    draw(2, { fill: 'none', stroke: '#5F82A8', 'stroke-width': 1.1 })
  );
}

function clipboardList({ draw, gradient }) {
  return (
    draw(1, { fill: '#E5F2FF', stroke: '#2875B5' }) +
    draw(0, { fill: gradient('clip', '#FFE199', '#F8C86A'), stroke: '#D28A2C' }) +
    draw(2, { fill: 'none', stroke: '#2875B5', 'stroke-width': 1.8 }) +
    draw(3, { fill: 'none', stroke: '#2875B5', 'stroke-width': 1.8 }) +
    draw(4, { fill: 'none', stroke: '#8854BA', 'stroke-width': 2.5 }) +
    draw(5, { fill: 'none', stroke: '#8854BA', 'stroke-width': 2.5 })
  );
}

const OBJECT_RENDERERS = {
  Star: stateShape,
  Heart: stateShape,
  Circle: stateShape,
  Square: stateShape,
  StarHalf: halfStar,
  Pin: pin,
  Disc: recordingDisc,
  Copy: copy,
  Bookmark: bookmark,
  BookmarkCheck: bookmarkCheck,
  ThumbsUp: thumb,
  ThumbsDown: thumb,
  Radio: radio,
  Moon: moon,
  Map: foldedMap,
  ClipboardList: clipboardList,
  CircleDot: circleDot,
};

export function renderSpecialArtwork(name, context) {
  const renderer = OBJECT_RENDERERS[name];
  if (!renderer) return null;
  const { data, node, paint, gradient } = context;
  return renderer({
    ...context,
    name,
    draw: (index, extra) => node(data.node[index], extra),
    outline: () => gradient('outline', paint.primary, paint.secondary),
  });
}
