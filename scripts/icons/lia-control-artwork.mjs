/** Filled, two-part LIA command glyphs; normalized directions and actions are explicit. */

function highlight(colour) {
  const channels = colour
    .slice(1)
    .match(/.{2}/g)
    .map(channel => Number.parseInt(channel, 16));
  return `#${channels
    .map(channel =>
      Math.round(channel + (255 - channel) * 0.18)
        .toString(16)
        .padStart(2, '0')
    )
    .join('')}`;
}

function colours({ paint, gradient }) {
  return {
    main: gradient('control-main', highlight(paint.primary), paint.primary),
    accent: gradient('control-accent', highlight(paint.secondary), paint.secondary),
  };
}

function path(d, fill) {
  return `<path d="${d}" fill="${fill}" stroke="none"/>`;
}

function transform(body, value) {
  return `<g transform="${value}">${body}</g>`;
}

function rightArrow(context, reversed = false) {
  const { main, accent } = colours(context);
  return (
    path('M3 10.4H12V13.6H3Z', reversed ? accent : main) +
    path('M11 4 21 12 11 20Z', reversed ? main : accent)
  );
}

function arrow(context, angle) {
  return transform(rightArrow(context), `rotate(${angle} 12 12)`);
}

function opposingArrows(context, angle) {
  const upper = transform(rightArrow(context), 'translate(2 0) scale(.8 .55)');
  const lower = transform(
    rightArrow(context, true),
    'translate(2 11) scale(.8 .55) rotate(180 12 12)'
  );
  return transform(upper + lower, `rotate(${angle} 12 12)`);
}

function rightChevron(context) {
  const { main, accent } = colours(context);
  return path('M7.7 5.7H10L16.3 12H13Z', main) + path('M13 12H16.3L10 18.3H7.7Z', accent);
}

function chevron(context, angle) {
  return transform(rightChevron(context), `rotate(${angle} 12 12)`);
}

function doubleUp(context) {
  const up = chevron(context, -90);
  return transform(up, 'translate(0 -4.8)') + transform(up, 'translate(0 4.8)');
}

function inwardChevrons(context) {
  return (
    transform(chevron(context, 90), 'translate(2.4 -1.8) scale(.8 .65)') +
    transform(chevron(context, -90), 'translate(2.4 10.2) scale(.8 .65)')
  );
}

function plus(context) {
  const { main, accent } = colours(context);
  return (
    `<rect x="10.5" y="4" width="3" height="16" rx="1.4" fill="${main}" stroke="none"/>` +
    `<rect x="4" y="10.5" width="16" height="3" rx="1.4" fill="${accent}" stroke="none"/>`
  );
}

function minus(context) {
  const { main, accent } = colours(context);
  return (
    path('M5.5 10.5H12V13.5H5.5A1.5 1.5 0 0 1 5.5 10.5Z', main) +
    path('M12 10.5H18.5A1.5 1.5 0 0 1 18.5 13.5H12Z', accent)
  );
}

function check(context, reversed = false) {
  const { main, accent } = colours(context);
  return (
    path('M2.8 11.9 5 9.7 9 13.7V18Z', reversed ? accent : main) +
    path('M9 13.7 19.5 3.2 21.7 5.4 9 18Z', reversed ? main : accent)
  );
}

function doubleCheck(context) {
  return (
    transform(check(context), 'translate(1 2) scale(.68 .85)') +
    transform(check(context, true), 'translate(7 2) scale(.68 .85)')
  );
}

function cross(context) {
  const { main, accent } = colours(context);
  const arm = fill =>
    `<rect x="10.5" y="3.5" width="3" height="17" rx="1.4" fill="${fill}" stroke="none"/>`;
  return transform(arm(main), 'rotate(45 12 12)') + transform(arm(accent), 'rotate(-45 12 12)');
}

function ellipsis(context, angle) {
  const { main, accent } = colours(context);
  const dots = [5, 12, 19]
    .map(
      (x, index) =>
        `<circle cx="${x}" cy="12" r="1.8" fill="${index === 1 ? accent : main}" stroke="none"/>`
    )
    .join('');
  return transform(dots, `rotate(${angle} 12 12)`);
}

function asterisk(context) {
  const { main, accent } = colours(context);
  return [0, 60, -60]
    .map((angle, index) =>
      transform(
        `<rect x="10.6" y="4.4" width="2.8" height="15.2" rx="1.3" fill="${index === 1 ? accent : main}" stroke="none"/>`,
        `rotate(${angle} 12 12)`
      )
    )
    .join('');
}

function corner(context, reflection) {
  const { main, accent } = colours(context);
  const shaft = path('M2.5 3.5H5.5V11A2.5 2.5 0 0 0 8 13.5H15V16.5H8A5.5 5.5 0 0 1 2.5 11Z', main);
  const head = path('M14 8.5 22 15 14 21.5Z', accent);
  return transform(shaft + head, reflection);
}

function circledDown(context) {
  const { paint } = context;
  return (
    `<circle cx="12" cy="12" r="9.5" fill="${paint.surface}" stroke="${paint.primary}" stroke-width="1.2"/>` +
    transform(arrow(context, 90), 'translate(4.2 4.2) scale(.65)')
  );
}

// One declared direction per export; no name heuristics can reverse an action.
const CONTROLS = {
  ArrowRight: context => arrow(context, 0),
  ArrowDown: context => arrow(context, 90),
  ArrowLeft: context => arrow(context, 180),
  ArrowUp: context => arrow(context, -90),
  ArrowUpRight: context => arrow(context, -45),
  ArrowUpLeft: context => arrow(context, -135),
  ArrowDownLeft: context => arrow(context, 135),
  ArrowDownCircle: circledDown,
  ArrowRightLeft: context => opposingArrows(context, 0),
  ArrowUpDown: context => opposingArrows(context, -90),
  ChevronRight: context => chevron(context, 0),
  ChevronDown: context => chevron(context, 90),
  ChevronLeft: context => chevron(context, 180),
  ChevronUp: context => chevron(context, -90),
  ChevronsUp: doubleUp,
  ChevronsDownUp: inwardChevrons,
  CornerDownRight: context => corner(context, 'translate(0 0)'),
  CornerDownLeft: context => corner(context, 'translate(24 0) scale(-1 1)'),
  CornerUpRight: context => corner(context, 'translate(0 24) scale(1 -1)'),
  CornerUpLeft: context => corner(context, 'translate(24 24) scale(-1 -1)'),
  Plus: plus,
  Minus: minus,
  Check: check,
  CheckCheck: doubleCheck,
  X: cross,
  Ellipsis: context => ellipsis(context, 0),
  MoreVertical: context => ellipsis(context, 90),
  Asterisk: asterisk,
};

export function renderControlArtwork(name, context) {
  return Object.hasOwn(CONTROLS, name) ? CONTROLS[name](context) : null;
}
